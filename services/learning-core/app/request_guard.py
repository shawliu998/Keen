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


class RequestGuardMiddleware:
    """Authenticate before body parsing and cap the document-import request stream."""

    def __init__(self, app: AsgiApp, *, session_token: str, max_document_bytes: int) -> None:
        self.app = app
        self.session_token = session_token
        self.max_import_request_bytes = max_document_bytes + MULTIPART_ENVELOPE_BYTES

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
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
        if not is_document_import:
            await self.app(scope, receive, send)
            return

        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_bytes = int(content_length)
            except ValueError:
                declared_bytes = -1
            if declared_bytes > self.max_import_request_bytes:
                await self._send_too_large(scope, receive, send)
                return

        received_bytes = 0
        buffered_messages: list[AsgiMessage] = []
        while True:
            message = await receive()
            buffered_messages.append(message)
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_import_request_bytes:
                    await self._send_too_large(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            elif message.get("type") == "http.disconnect":
                break

        next_message = 0

        async def replay_receive() -> AsgiMessage:
            nonlocal next_message
            if next_message < len(buffered_messages):
                message = buffered_messages[next_message]
                next_message += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _send_too_large(
        self, scope: dict[str, Any], receive: Receive, send: Send
    ) -> None:
        await JSONResponse(
            {
                "detail": {
                    "message": "document upload request exceeds the configured size limit",
                    "retryable": True,
                    "recovery": "Choose a smaller supported document and retry.",
                }
            },
            status_code=413,
        )(scope, receive, send)
