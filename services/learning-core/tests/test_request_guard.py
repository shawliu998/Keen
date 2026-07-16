from __future__ import annotations

import asyncio

from app.request_guard import (
    MULTIPART_ENVELOPE_BYTES,
    SMALL_JSON_REQUEST_BYTES,
    RequestGuardMiddleware,
)
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


def _scope_for_path(path: str, headers: list[tuple[bytes, bytes]]) -> dict:
    scope = _scope(headers)
    scope["path"] = path
    scope["raw_path"] = path.encode()
    return scope


def test_bounded_json_content_length_and_chunked_stream_are_capped_before_parsing() -> (
    None
):
    async def exercise(*, path: str, declared: bool) -> tuple[list[dict], int]:
        chunks_read = 0
        sent: list[dict] = []
        chunks = [b"x" * SMALL_JSON_REQUEST_BYTES, b"overflow"]

        async def receive() -> dict:
            nonlocal chunks_read
            chunks_read += 1
            body = chunks.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(chunks)}

        async def send(message: dict) -> None:
            sent.append(message)

        async def downstream(scope, receive, send) -> None:
            while True:
                message = await receive()
                if not message.get("more_body"):
                    break

        headers = [(b"authorization", f"Bearer {TOKEN}".encode())]
        if declared:
            headers.append(
                (b"content-length", str(SMALL_JSON_REQUEST_BYTES + 1).encode())
            )
        middleware = RequestGuardMiddleware(
            downstream, session_token=TOKEN, max_document_bytes=1024
        )
        await middleware(_scope_for_path(path, headers), receive, send)
        return sent, chunks_read

    for path in (
        "/v1/answer/stream",
        "/v1/agent/runs/run-1/mutations/mutation-1/undo",
        "/v1/agent/runs/run-1/mutations/mutation-1/redo",
    ):
        declared_sent, declared_reads = asyncio.run(exercise(path=path, declared=True))
        chunked_sent, chunked_reads = asyncio.run(exercise(path=path, declared=False))

        assert declared_sent[0]["status"] == 413
        assert declared_reads == 0
        assert chunked_sent[0]["status"] == 413
        assert chunked_reads == 2


def test_unauthorized_request_is_rejected_before_any_body_chunk_is_read() -> None:
    chunks_read = 0
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal chunks_read
        chunks_read += 1
        return {"type": "http.request", "body": b"untrusted", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(
        scope, receive, send
    ) -> None:  # pragma: no cover - must not run
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
    trailing = b"must-remain-unread"
    chunks = [b"a" * chunk_size, b"b" * chunk_size, b"overflow", trailing]
    sent: list[dict] = []
    downstream_bodies: list[bytes] = []
    downstream_completed = False

    async def receive() -> dict:
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        nonlocal downstream_completed
        while True:
            message = await receive()
            downstream_bodies.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        downstream_completed = True

    middleware = RequestGuardMiddleware(
        downstream,
        session_token=TOKEN,
        max_document_bytes=1,
    )
    headers = [(b"authorization", f"Bearer {TOKEN}".encode())]
    asyncio.run(middleware(_scope(headers), receive, send))

    assert chunks == [trailing]
    assert downstream_bodies == [b"a" * chunk_size, b"b" * chunk_size]
    assert downstream_completed is False
    assert sent[0]["status"] == 413


def test_invalid_or_negative_content_length_is_rejected_before_body_read() -> None:
    for invalid_length in (b"invalid", b"-1", b"+1", b"1.5", b"9" * 5000):
        chunks_read = 0
        sent: list[dict] = []

        async def receive() -> dict:
            nonlocal chunks_read
            chunks_read += 1
            return {
                "type": "http.request",
                "body": b"must-not-be-read",
                "more_body": False,
            }

        async def send(message: dict) -> None:
            sent.append(message)

        async def downstream(
            scope, receive, send
        ) -> None:  # pragma: no cover - must not run
            raise AssertionError("invalid Content-Length reached the application")

        middleware = RequestGuardMiddleware(
            downstream,
            session_token=TOKEN,
            max_document_bytes=8,
        )
        headers = [
            (b"authorization", f"Bearer {TOKEN}".encode()),
            (b"content-length", invalid_length),
        ]
        asyncio.run(middleware(_scope(headers), receive, send))

        assert chunks_read == 0
        assert sent[0]["status"] == 400


def test_oversized_content_length_is_rejected_without_reading_or_running_downstream() -> (
    None
):
    chunks_read = 0
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal chunks_read
        chunks_read += 1
        return {"type": "http.request", "body": b"must-not-be-read", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(
        scope, receive, send
    ) -> None:  # pragma: no cover - must not run
        raise AssertionError("oversized declared request reached the application")

    middleware = RequestGuardMiddleware(
        downstream,
        session_token=TOKEN,
        max_document_bytes=8,
    )
    declared = 8 + MULTIPART_ENVELOPE_BYTES + 1
    headers = [
        (b"authorization", f"Bearer {TOKEN}".encode()),
        (b"content-length", str(declared).encode()),
    ]
    asyncio.run(middleware(_scope(headers), receive, send))

    assert chunks_read == 0
    assert sent[0]["status"] == 413


def test_large_valid_request_is_streamed_to_downstream_without_prefetch_or_replay() -> (
    None
):
    chunk = b"x" * (64 * 1024)
    chunks = [chunk] * 32
    source_calls = 0
    downstream_lengths: list[int] = []
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal source_calls
        source_calls += 1
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        assert source_calls == 0
        while True:
            calls_before_receive = source_calls
            message = await receive()
            assert source_calls == calls_before_receive + 1
            downstream_lengths.append(len(message.get("body", b"")))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestGuardMiddleware(
        downstream,
        session_token=TOKEN,
        max_document_bytes=2 * 1024 * 1024,
    )
    headers = [(b"authorization", f"Bearer {TOKEN}".encode())]
    asyncio.run(middleware(_scope(headers), receive, send))

    assert chunks == []
    assert source_calls == 32
    assert downstream_lengths == [len(chunk)] * 32
    assert sent[0]["status"] == 204


def test_disconnect_is_propagated_immediately_without_synthetic_body_message() -> None:
    source_messages = [
        {"type": "http.request", "body": b"partial", "more_body": True},
        {"type": "http.disconnect"},
    ]
    downstream_messages: list[dict] = []
    sent: list[dict] = []

    async def receive() -> dict:
        return source_messages.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        downstream_messages.append(await receive())
        downstream_messages.append(await receive())

    middleware = RequestGuardMiddleware(
        downstream,
        session_token=TOKEN,
        max_document_bytes=8,
    )
    headers = [(b"authorization", f"Bearer {TOKEN}".encode())]
    asyncio.run(middleware(_scope(headers), receive, send))

    assert source_messages == []
    assert downstream_messages == [
        {"type": "http.request", "body": b"partial", "more_body": True},
        {"type": "http.disconnect"},
    ]
    assert sent == []


def test_overflow_after_downstream_response_start_never_sends_a_second_response() -> (
    None
):
    chunk_size = MULTIPART_ENVELOPE_BYTES
    trailing = b"must-remain-unread"
    chunks = [b"a" * chunk_size, b"overflow", trailing]
    sent: list[dict] = []

    async def receive() -> dict:
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 202, "headers": []})
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break

    middleware = RequestGuardMiddleware(
        downstream,
        session_token=TOKEN,
        max_document_bytes=1,
    )
    headers = [(b"authorization", f"Bearer {TOKEN}".encode())]
    asyncio.run(middleware(_scope(headers), receive, send))

    assert chunks == [trailing]
    assert [message["type"] for message in sent] == [
        "http.response.start",
        "http.response.body",
    ]
    assert sent[0]["status"] == 202
