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
)


MESSAGES = (
    ChatMessage(role="system", content="System"),
    ChatMessage(role="user", content="Question"),
)


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
