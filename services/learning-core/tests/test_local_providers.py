from __future__ import annotations

import asyncio
import json
import math

import httpx
import pytest

from app.local_providers import (
    LocalProviderError,
    LocalProviderResponseError,
    LocalProviderSecurityError,
    LocalProviderTimeoutError,
    LocalProviderTimeouts,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.retrieval_interfaces import EmbeddingProvider


def _run(coroutine):
    return asyncio.run(coroutine)


class _FailingResponseStream(httpx.AsyncByteStream):
    def __init__(self, error: httpx.HTTPError) -> None:
        self.error = error

    async def __aiter__(self):
        raise self.error
        yield b""  # pragma: no cover


class _SlowResponseStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        while True:
            await asyncio.sleep(0.02)
            yield b" "


def test_openai_compatible_protocol_and_model_identity() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "nomic-embed-text-v1.5",
                "version": "sha256:fixture",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [4, 5, 6]},
                    {"object": "embedding", "index": 0, "embedding": [1, 2, 3]},
                ],
            },
        )

    async def exercise() -> None:
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="http://127.0.0.1:1234/v1",
            model="nomic-embed-text-v1.5",
            version="sha256:fixture",
            dimensions=3,
            transport=httpx.MockTransport(handler),
        )
        assert isinstance(provider, EmbeddingProvider)
        assert provider.model.provider == "openai-compatible"
        assert provider.model.version == "sha256:fixture"
        try:
            assert await provider.embed_documents(("first", "second")) == (
                (1.0, 2.0, 3.0),
                (4.0, 5.0, 6.0),
            )
        finally:
            await provider.aclose()

    _run(exercise())
    assert requests[0].url == "http://127.0.0.1:1234/v1/embeddings"
    assert json.loads(requests[0].content) == {
        "input": ["first", "second"],
        "model": "nomic-embed-text-v1.5",
    }
    assert requests[0].extensions["timeout"] == {
        "connect": 5.0,
        "read": 60.0,
        "write": 15.0,
        "pool": 5.0,
    }


def test_ollama_protocol_and_query_embedding() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"model": "embeddinggemma:300m", "embeddings": [[0.25, -0.5]]},
        )

    async def exercise() -> tuple[float, ...]:
        async with OllamaEmbeddingProvider(
            base_url="http://127.0.0.2:11434/api/",
            model="embeddinggemma:300m",
            version="digest:fixture",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        ) as provider:
            return tuple(await provider.embed_query("what is inertia?"))

    assert _run(exercise()) == (0.25, -0.5)
    assert requests[0].url == "http://127.0.0.2:11434/api/embed"
    assert json.loads(requests[0].content) == {
        "input": ["what is inertia?"],
        "model": "embeddinggemma:300m",
    }


def test_external_redirect_is_rejected_before_a_second_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(307, headers={"location": "http://example.com:80/steal"})

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderSecurityError, match="not permitted"):
                await provider.embed_query("private document text")
        finally:
            await provider.aclose()

    _run(exercise())
    assert len(requests) == 1


def test_loopback_redirect_is_manually_revalidated_and_bounded() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(307, headers={"location": "/redirected/embed"})
        return httpx.Response(307, headers={"location": "/again"})

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            max_redirects=1,
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderSecurityError, match="limit"):
                await provider.embed_query("text")
        finally:
            await provider.aclose()

    _run(exercise())
    assert [request.url.path for request in requests] == [
        "/api/embed",
        "/redirected/embed",
    ]


def test_timeout_is_mapped_to_a_safe_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret response detail", request=request)

    async def exercise() -> None:
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="http://127.0.0.1:8080",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderTimeoutError) as failure:
                await provider.embed_query("private text")
            assert "secret" not in str(failure.value)
            assert "private text" not in str(failure.value)
        finally:
            await provider.aclose()

    _run(exercise())


def test_task_cancellation_propagates_without_translation() -> None:
    started = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        task = asyncio.create_task(provider.embed_query("cancel me"))
        await started.wait()
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await provider.aclose()

    _run(exercise())


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"model": "local", "data": "not-a-list"},
        {"model": "local", "data": [{"index": 0, "embedding": [1, 2]}]},
        {
            "model": "local",
            "data": [
                {"index": 0, "embedding": [1, 2]},
                {"index": 0, "embedding": [3, 4]},
            ],
        },
        {
            "model": "local",
            "data": [
                {"index": True, "embedding": [1, 2]},
                {"index": 1, "embedding": [3, 4]},
            ],
        },
    ],
)
def test_openai_rejects_malformed_or_wrong_count_payloads(payload: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def exercise() -> None:
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="http://127.0.0.1:8080",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderResponseError):
                await provider.embed_documents(("one", "two"))
        finally:
            await provider.aclose()

    _run(exercise())


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "other", "embeddings": [[1, 2]]},
        {"model": "local", "version": "2", "embeddings": [[1, 2]]},
        {"model": "local", "embeddings": [[1]]},
        {"model": "local", "embeddings": [[1, 2, 3]]},
        {"model": "local", "embeddings": [[1, math.nan]]},
        {"model": "local", "embeddings": [[True, 2]]},
        {"model": "local", "embeddings": []},
    ],
)
def test_ollama_rejects_identity_dimension_value_and_count_mismatches(
    payload: object,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(payload).encode(),
        )

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderResponseError):
                await provider.embed_query("text")
        finally:
            await provider.aclose()

    _run(exercise())


def test_http_and_non_json_failures_do_not_include_response_body() -> None:
    responses = iter(
        [
            httpx.Response(500, text="private server traceback"),
            httpx.Response(200, text="private non-json content"),
        ]
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return next(responses)

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            for failure_type in (LocalProviderError, LocalProviderResponseError):
                with pytest.raises(failure_type) as failure:
                    await provider.embed_query("private request body")
                assert "private" not in str(failure.value)
        finally:
            await provider.aclose()

    _run(exercise())


def test_empty_batch_is_local_and_invalid_inputs_fail_before_network() -> None:
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise AssertionError("network should not be reached")

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            assert await provider.embed_documents(()) == ()
            with pytest.raises(ValueError, match="sequence"):
                await provider.embed_documents("text")
            with pytest.raises(ValueError, match="must not be empty"):
                await provider.embed_query(" ")
        finally:
            await provider.aclose()

    _run(exercise())
    assert request_count == 0


@pytest.mark.parametrize(
    ("error_type", "expected_type"),
    [
        (httpx.ReadTimeout, LocalProviderTimeoutError),
        (httpx.ReadError, LocalProviderError),
    ],
)
def test_response_stream_transport_failures_use_safe_provider_errors(
    error_type, expected_type
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=_FailingResponseStream(
                error_type("private stream failure", request=request)
            ),
            request=request,
        )

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(expected_type) as failure:
                await provider.embed_query("private request body")
            assert "private" not in str(failure.value)
        finally:
            await provider.aclose()

    _run(exercise())


def test_total_deadline_stops_a_drip_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=_SlowResponseStream(),
            request=request,
        )

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            timeouts=LocalProviderTimeouts(total=0.05),
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LocalProviderTimeoutError, match="total time limit"):
                await provider.embed_query("bounded request")
        finally:
            await provider.aclose()

    _run(exercise())


def test_input_batch_count_and_size_are_bounded_before_network() -> None:
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise AssertionError("network should not be reached")

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ValueError, match="64"):
                await provider.embed_documents(tuple("text" for _ in range(65)))
            with pytest.raises(ValueError, match="size limit"):
                await provider.embed_documents(("x" * 2_000_001,))
        finally:
            await provider.aclose()

    _run(exercise())
    assert request_count == 0


def test_provider_response_body_is_stream_counted(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"model":"local","embeddings":[[1,2]]}',
        )

    async def exercise() -> None:
        provider = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:11434",
            model="local",
            version="1",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        monkeypatch.setattr(type(provider), "_MAX_RESPONSE_BYTES", 16)
        try:
            with pytest.raises(LocalProviderResponseError, match="size limit"):
                await provider.embed_query("text")
        finally:
            await provider.aclose()

    _run(exercise())


@pytest.mark.parametrize("field", ["connect", "read", "write", "pool", "total"])
@pytest.mark.parametrize("value", [0, -1, math.inf, math.nan])
def test_all_timeout_fields_are_finite_and_positive(field: str, value: float) -> None:
    values = {"connect": 1.0, "read": 1.0, "write": 1.0, "pool": 1.0}
    values[field] = value
    with pytest.raises(ValueError, match=field):
        LocalProviderTimeouts(**values)
