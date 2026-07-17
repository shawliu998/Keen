from __future__ import annotations

import asyncio
import contextlib
import json

import httpx
import pytest

from app.chat_interfaces import ChatMessage
from app.local_chat_providers import (
    OllamaChatProvider,
    OpenAICompatibleChatProvider,
)
from app.local_providers import (
    LocalProviderResponseError,
    LocalProviderSecurityError,
    LocalProviderTimeoutError,
    LocalProviderTimeouts,
)


MESSAGES = (
    ChatMessage(role="system", content="System"),
    ChatMessage(role="user", content="Question"),
)


class _BytesStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def __aiter__(self):
        yield self._content

    async def aclose(self) -> None:
        pass


async def _collect(provider) -> str:
    try:
        return "".join([delta async for delta in provider.stream(MESSAGES)])
    finally:
        await provider.aclose()


def test_openai_compatible_stream_protocol_and_request_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        chunks = [
            {"model": "local-chat", "choices": [{"delta": {"content": "Hi "}}]},
            {"model": "local-chat", "choices": [{"delta": {"content": "there"}}]},
            {
                "model": "local-chat",
                "choices": [{"delta": {}, "finish_reason": "stop"}],
            },
        ]
        content = (
            "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
            + "data: [DONE]\n\n"
        )
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=content
        )

    provider = OpenAICompatibleChatProvider(
        base_url="http://127.0.0.1:8080",
        model="local-chat",
        version="v1",
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(_collect(provider)) == "Hi there"
    assert requests[0].url == "http://127.0.0.1:8080/v1/chat/completions"
    body = json.loads(requests[0].content)
    assert body == {
        "model": "local-chat",
        "messages": [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Question"},
        ],
        "stream": True,
    }
    assert requests[0].headers.get("authorization") is None


def test_ollama_stream_protocol_and_request_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = "\n".join(
            json.dumps(item)
            for item in (
                {
                    "model": "llama-local",
                    "message": {"role": "assistant", "content": "Local "},
                    "done": False,
                },
                {
                    "model": "llama-local",
                    "message": {"role": "assistant", "content": "answer"},
                    "done": True,
                    "done_reason": "stop",
                },
            )
        )
        return httpx.Response(
            200, headers={"content-type": "application/x-ndjson"}, content=content
        )

    provider = OllamaChatProvider(
        base_url="http://127.0.0.1:11434/api",
        model="llama-local",
        version="sha-local",
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(_collect(provider)) == "Local answer"
    assert requests[0].url == "http://127.0.0.1:11434/api/chat"
    assert json.loads(requests[0].content)["stream"] is True


def test_chat_provider_rejects_redirect_to_non_loopback() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"location": "http://example.com/chat"})

    provider = OpenAICompatibleChatProvider(
        base_url="http://127.0.0.1:8080",
        model="local-chat",
        version="v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LocalProviderSecurityError):
        asyncio.run(_collect(provider))


def test_chat_provider_rejects_wrong_model_and_non_stream_content_type() -> None:
    responses = iter(
        (
            httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    'data: {"model":"wrong","choices":[{"delta":{"content":"x"}}]}\n\n'
                ),
            ),
            httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content="not a stream",
            ),
        )
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return next(responses)

    async def exercise() -> None:
        for _ in range(2):
            provider = OpenAICompatibleChatProvider(
                base_url="http://127.0.0.1:8080",
                model="local-chat",
                version="v1",
                transport=httpx.MockTransport(handler),
            )
            with pytest.raises(LocalProviderResponseError):
                await _collect(provider)

    asyncio.run(exercise())


def test_chat_providers_reject_truncated_streams_without_completion_markers() -> None:
    responses = iter(
        (
            httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    'data: {"model":"local-chat","choices":[{"delta":{"content":"partial"}}]}\n\n'
                ),
            ),
            httpx.Response(
                200,
                headers={"content-type": "application/x-ndjson"},
                content=(
                    '{"model":"local-chat","message":{"content":"partial"},"done":false}\n'
                ),
            ),
        )
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return next(responses)

    async def exercise() -> None:
        providers = (
            OpenAICompatibleChatProvider(
                base_url="http://127.0.0.1:8080",
                model="local-chat",
                version="v1",
                transport=httpx.MockTransport(handler),
            ),
            OllamaChatProvider(
                base_url="http://127.0.0.1:11434",
                model="local-chat",
                version="v1",
                transport=httpx.MockTransport(handler),
            ),
        )
        for provider in providers:
            with pytest.raises(LocalProviderResponseError, match="completion marker"):
                await _collect(provider)

    asyncio.run(exercise())


def test_chat_providers_reject_non_normal_or_missing_stop_reasons() -> None:
    responses = iter(
        (
            httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    'data: {"model":"local-chat","choices":[{"delta":{},'
                    '"finish_reason":"length"}]}\n\n'
                    "data: [DONE]\n\n"
                ),
            ),
            httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="data: [DONE]\n\n",
            ),
            httpx.Response(
                200,
                headers={"content-type": "application/x-ndjson"},
                content=(
                    '{"model":"local-chat","message":{"content":"partial"},'
                    '"done":true,"done_reason":"length"}\n'
                ),
            ),
            httpx.Response(
                200,
                headers={"content-type": "application/x-ndjson"},
                content=(
                    '{"model":"local-chat","message":{"content":"answer"},'
                    '"done":true}\n'
                ),
            ),
        )
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return next(responses)

    async def exercise() -> None:
        providers = (
            OpenAICompatibleChatProvider(
                base_url="http://127.0.0.1:8080",
                model="local-chat",
                version="v1",
                transport=httpx.MockTransport(handler),
            ),
            OpenAICompatibleChatProvider(
                base_url="http://127.0.0.1:8080",
                model="local-chat",
                version="v1",
                transport=httpx.MockTransport(handler),
            ),
            OllamaChatProvider(
                base_url="http://127.0.0.1:11434",
                model="local-chat",
                version="v1",
                transport=httpx.MockTransport(handler),
            ),
            OllamaChatProvider(
                base_url="http://127.0.0.1:11434",
                model="local-chat",
                version="v1",
                transport=httpx.MockTransport(handler),
            ),
        )
        for provider in providers:
            with pytest.raises(LocalProviderResponseError, match="stop reason"):
                await _collect(provider)

    asyncio.run(exercise())


def test_cancelling_chat_stream_cancels_transport_and_closes_response() -> None:
    async def exercise() -> tuple[bool, bool]:
        started = asyncio.Event()
        transport_cancelled = asyncio.Event()
        response_closed = asyncio.Event()
        never = asyncio.Event()

        class BlockingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                started.set()
                try:
                    await never.wait()
                except asyncio.CancelledError:
                    transport_cancelled.set()
                    raise
                yield b"must-not-arrive"

            async def aclose(self) -> None:
                response_closed.set()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=BlockingStream(),
            )

        provider = OpenAICompatibleChatProvider(
            base_url="http://127.0.0.1:8080",
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        stream = provider.stream(MESSAGES)
        next_delta = asyncio.create_task(anext(stream))
        await asyncio.wait_for(started.wait(), timeout=1)
        next_delta.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await next_delta
        await stream.aclose()
        await provider.aclose()
        return transport_cancelled.is_set(), response_closed.is_set()

    assert asyncio.run(exercise()) == (True, True)


@pytest.mark.parametrize(
    ("provider_type", "base_url", "expected_url"),
    (
        (
            OpenAICompatibleChatProvider,
            "http://127.0.0.1:8080",
            "http://127.0.0.1:8080/v1/chat/completions",
        ),
        (
            OllamaChatProvider,
            "http://127.0.0.1:11434/api",
            "http://127.0.0.1:11434/api/chat",
        ),
    ),
)
def test_complete_agent_json_uses_configured_provider_endpoint(
    provider_type, base_url: str, expected_url: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            stream=_BytesStream(b'{"result":"ok"}'),
        )

    async def exercise() -> dict[str, object]:
        provider = provider_type(
            base_url=base_url,
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        try:
            return await provider.complete_agent_json({"messages": [], "tools": []})
        finally:
            await provider.aclose()

    assert asyncio.run(exercise()) == {"result": "ok"}
    assert str(requests[0].url) == expected_url
    assert json.loads(requests[0].content) == {"messages": [], "tools": []}


@pytest.mark.parametrize(
    ("headers", "content"),
    (
        ({"content-type": "text/plain"}, b"{}"),
        ({"content-type": "application/json", "content-encoding": "gzip"}, b"{}"),
        ({"content-type": "application/json", "content-encoding": ""}, b"{}"),
        ({"content-type": "application/json", "content-length": "invalid"}, b"{}"),
        ({"content-type": "application/json", "content-length": "-1"}, b"{}"),
        (
            {
                "content-type": "application/json",
                "content-length": str(1024 * 1024 + 1),
            },
            b"{}",
        ),
        ({"content-type": "application/json"}, b"x" * (1024 * 1024 + 1)),
        ({"content-type": "application/json"}, b"\xff"),
        ({"content-type": "application/json"}, b"not json"),
        ({"content-type": "application/json"}, b'{"model":"a","model":"b"}'),
        ({"content-type": "application/json"}, b'{"value":NaN}'),
        ({"content-type": "application/json"}, b"[]"),
    ),
)
def test_complete_agent_json_rejects_invalid_or_unbounded_responses(
    headers: dict[str, str], content: bytes
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, stream=_BytesStream(content))

    async def exercise() -> None:
        provider = OpenAICompatibleChatProvider(
            base_url="http://127.0.0.1:8080",
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderResponseError):
                await provider.complete_agent_json({})
        finally:
            await provider.aclose()

    asyncio.run(exercise())


def test_complete_agent_json_rejects_redirects_outside_loopback() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"location": "http://example.com/chat"})

    async def exercise() -> None:
        provider = OllamaChatProvider(
            base_url="http://127.0.0.1:11434",
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderSecurityError):
                await provider.complete_agent_json({})
        finally:
            await provider.aclose()

    asyncio.run(exercise())


def test_complete_agent_json_enforces_total_timeout_and_closes_response() -> None:
    async def exercise() -> bool:
        response_closed = asyncio.Event()
        never = asyncio.Event()

        class BlockingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                await never.wait()
                yield b"{}"

            async def aclose(self) -> None:
                response_closed.set()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                stream=BlockingStream(),
            )

        provider = OpenAICompatibleChatProvider(
            base_url="http://127.0.0.1:8080",
            model="local-chat",
            version="v1",
            timeouts=LocalProviderTimeouts(total=0.01),
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderTimeoutError):
                await provider.complete_agent_json({})
        finally:
            await provider.aclose()
        return response_closed.is_set()

    assert asyncio.run(exercise())


def test_complete_agent_json_closes_response_after_validation_failure() -> None:
    async def exercise() -> bool:
        response_closed = asyncio.Event()

        class CloseTrackingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"{}"

            async def aclose(self) -> None:
                response_closed.set()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                stream=CloseTrackingStream(),
            )

        provider = OllamaChatProvider(
            base_url="http://127.0.0.1:11434",
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderResponseError):
                await provider.complete_agent_json({})
        finally:
            await provider.aclose()
        return response_closed.is_set()

    assert asyncio.run(exercise())


def test_complete_agent_json_keeps_primary_error_on_close_failure() -> None:
    async def exercise() -> bool:
        close_attempted = asyncio.Event()

        class CloseFailingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"{}"

            async def aclose(self) -> None:
                close_attempted.set()
                raise RuntimeError("close failed")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                stream=CloseFailingStream(),
            )

        provider = OllamaChatProvider(
            base_url="http://127.0.0.1:11434",
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderResponseError, match="non-JSON"):
                await provider.complete_agent_json({})
        finally:
            await provider.aclose()
        return close_attempted.is_set()

    assert asyncio.run(exercise())


def test_cancelling_complete_agent_json_cancels_transport_and_closes_response() -> None:
    async def exercise() -> tuple[bool, bool]:
        started = asyncio.Event()
        transport_cancelled = asyncio.Event()
        response_closed = asyncio.Event()
        never = asyncio.Event()

        class BlockingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                started.set()
                try:
                    await never.wait()
                except asyncio.CancelledError:
                    transport_cancelled.set()
                    raise
                yield b"{}"

            async def aclose(self) -> None:
                response_closed.set()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                stream=BlockingStream(),
            )

        provider = OllamaChatProvider(
            base_url="http://127.0.0.1:11434",
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        task = asyncio.create_task(provider.complete_agent_json({}))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await provider.aclose()
        return transport_cancelled.is_set(), response_closed.is_set()

    assert asyncio.run(exercise()) == (True, True)


def test_complete_agent_json_keeps_cancellation_on_close_failure() -> None:
    async def exercise() -> tuple[bool, bool, bool]:
        started = asyncio.Event()
        transport_cancelled = asyncio.Event()
        close_attempted = asyncio.Event()
        never = asyncio.Event()

        class BlockingCloseFailingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                started.set()
                try:
                    await never.wait()
                except asyncio.CancelledError:
                    transport_cancelled.set()
                    raise
                yield b"{}"

            async def aclose(self) -> None:
                close_attempted.set()
                raise RuntimeError("close failed")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                stream=BlockingCloseFailingStream(),
            )

        provider = OllamaChatProvider(
            base_url="http://127.0.0.1:11434",
            model="local-chat",
            version="v1",
            transport=httpx.MockTransport(handler),
        )
        task = asyncio.create_task(provider.complete_agent_json({}))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await provider.aclose()
        return (
            transport_cancelled.is_set(),
            close_attempted.is_set(),
            task.cancelled(),
        )

    assert asyncio.run(exercise()) == (True, True, True)
