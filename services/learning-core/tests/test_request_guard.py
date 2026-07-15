from __future__ import annotations

import asyncio

from app.request_guard import MULTIPART_ENVELOPE_BYTES, RequestGuardMiddleware
from conftest import TOKEN


def _scope(headers: list[tuple[bytes, bytes]]) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/documents/import",
        "raw_path": b"/v1/documents/import",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 43125),
    }


def test_unauthorized_request_is_rejected_before_any_body_chunk_is_read() -> None:
    chunks_read = 0
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal chunks_read
        chunks_read += 1
        return {"type": "http.request", "body": b"untrusted", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:  # pragma: no cover - must not run
        raise AssertionError("unauthorized body reached the application")

    middleware = RequestGuardMiddleware(
        downstream,
        session_token=TOKEN,
        max_document_bytes=8,
    )
    asyncio.run(middleware(_scope([]), receive, send))

    assert chunks_read == 0
    assert sent[0]["status"] == 401


def test_authenticated_chunked_request_is_stopped_at_the_asgi_stream_limit() -> None:
    chunk_size = MULTIPART_ENVELOPE_BYTES // 2
    chunks = [b"a" * chunk_size, b"b" * chunk_size, b"overflow"]
    sent: list[dict] = []

    async def receive() -> dict:
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    middleware = RequestGuardMiddleware(
        downstream,
        session_token=TOKEN,
        max_document_bytes=1,
    )
    headers = [(b"authorization", f"Bearer {TOKEN}".encode())]
    asyncio.run(middleware(_scope(headers), receive, send))

    assert chunks == []
    assert sent[0]["status"] == 413
