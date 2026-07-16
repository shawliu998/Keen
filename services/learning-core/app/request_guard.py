from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from .auth import is_session_authenticated

AsgiMessage = dict[str, Any]
Receive = Callable[[], Awaitable[AsgiMessage]]
Send = Callable[[AsgiMessage], Awaitable[None]]
AsgiApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]

MULTIPART_ENVELOPE_BYTES = 1024 * 1024
SMALL_JSON_REQUEST_BYTES = 64 * 1024
BOUNDED_JSON_PATHS = frozenset({"/v1/answer/stream", "/v1/search", "/v1/query"})


class _RequestBodyTooLarge(Exception):
    """Internal control flow used to stop downstream parsing immediately."""


class _CountingReceive:
    def __init__(self, receive: Receive, *, maximum_bytes: int) -> None:
        self._receive = receive
        self._maximum_bytes = maximum_bytes
        self._received_bytes = 0
        self._exceeded = False

    async def __call__(self) -> AsgiMessage:
        if self._exceeded:
            raise _RequestBodyTooLarge

        message = await self._receive()
        if message.get("type") != "http.request":
            return message

        body = message.get("body", b"")
        self._received_bytes += len(body)
        if self._received_bytes > self._maximum_bytes:
            self._exceeded = True
            raise _RequestBodyTooLarge
        return message


class RequestGuardMiddleware:
    """Authenticate before body parsing and cap bounded request streams."""

    def __init__(
        self, app: AsgiApp, *, session_token: str, max_document_bytes: int
    ) -> None:
        self.app = app
        self.session_token = session_token
        self.max_import_request_bytes = max_document_bytes + MULTIPART_ENVELOPE_BYTES

    async def __call__(
        self, scope: dict[str, Any], receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        headers = Headers(scope=scope)
        if method != "OPTIONS" and not is_session_authenticated(
            headers.get("authorization"), self.session_token
        ):
            await JSONResponse(
                {"detail": "invalid or missing session token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return

        is_document_import = (
            method == "POST" and scope.get("path") == "/v1/documents/import"
        )
        is_bounded_json = method == "POST" and scope.get("path") in BOUNDED_JSON_PATHS
        if not is_document_import and not is_bounded_json:
            await self.app(scope, receive, send)
            return

        maximum_bytes = (
            self.max_import_request_bytes
            if is_document_import
            else SMALL_JSON_REQUEST_BYTES
        )

        content_length = headers.get("content-length")
        if content_length is not None:
            if not content_length.isascii() or not content_length.isdigit():
                await self._send_invalid_content_length(
                    scope, receive, send, is_document_import=is_document_import
                )
                return
            try:
                declared_bytes = int(content_length)
            except ValueError:
                await self._send_invalid_content_length(
                    scope, receive, send, is_document_import=is_document_import
                )
                return
            if declared_bytes > maximum_bytes:
                await self._send_too_large(
                    scope, receive, send, is_document_import=is_document_import
                )
                return

        counting_receive = _CountingReceive(
            receive,
            maximum_bytes=maximum_bytes,
        )
        response_started = False
        response_completed = False

        async def tracked_send(message: AsgiMessage) -> None:
            nonlocal response_started, response_completed
            if message.get("type") == "http.response.start":
                response_started = True
            elif message.get("type") == "http.response.body" and not message.get(
                "more_body", False
            ):
                response_completed = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                if not response_completed:
                    await send(
                        {
                            "type": "http.response.body",
                            "body": b"",
                            "more_body": False,
                        }
                    )
                return
            await self._send_too_large(
                scope, receive, send, is_document_import=is_document_import
            )

    async def _send_invalid_content_length(
        self,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
        *,
        is_document_import: bool,
    ) -> None:
        request_kind = "document upload" if is_document_import else "JSON request"
        recovery = (
            "Retry the upload with a valid request length."
            if is_document_import
            else "Retry with a valid request length."
        )
        await JSONResponse(
            {
                "detail": {
                    "message": f"{request_kind} Content-Length must be a non-negative decimal integer",
                    "retryable": True,
                    "recovery": recovery,
                }
            },
            status_code=400,
        )(scope, receive, send)

    async def _send_too_large(
        self,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
        *,
        is_document_import: bool,
    ) -> None:
        message = (
            "document upload request exceeds the configured size limit"
            if is_document_import
            else "JSON request exceeds the configured size limit"
        )
        recovery = (
            "Choose a smaller supported document and retry."
            if is_document_import
            else "Reduce the request size and retry."
        )
        await JSONResponse(
            {
                "detail": {
                    "message": message,
                    "retryable": True,
                    "recovery": recovery,
                }
            },
            status_code=413,
        )(scope, receive, send)
