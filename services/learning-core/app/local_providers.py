from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.provider_endpoints import (
    ProviderEndpoint,
    ProviderEndpointError,
    ProviderKind,
    validate_ollama_endpoint,
    validate_openai_compatible_endpoint,
    validate_provider_endpoint,
    validate_redirect_target,
)
from app.retrieval_interfaces import EmbeddingModel, validate_embedding


class LocalProviderError(RuntimeError):
    """Safe public failure for a local embedding provider."""


class LocalProviderSecurityError(LocalProviderError):
    """Raised when a provider attempts to leave the validated loopback boundary."""


class LocalProviderTimeoutError(LocalProviderError):
    """Raised when a bounded local provider operation times out."""


class LocalProviderResponseError(LocalProviderError):
    """Raised when a provider returns an invalid or incompatible response."""


@dataclass(frozen=True, slots=True)
class LocalProviderTimeouts:
    connect: float = 5.0
    read: float = 60.0
    write: float = 15.0
    pool: float = 5.0
    total: float = 90.0

    def __post_init__(self) -> None:
        for name in ("connect", "read", "write", "pool", "total"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"provider {name} timeout must be finite and positive")

    def to_httpx(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool,
        )


class _LocalEmbeddingProvider:
    _MAX_REDIRECTS = 5
    _MAX_RESPONSE_BYTES = 16 * 1024 * 1024

    def __init__(
        self,
        *,
        endpoint: ProviderEndpoint,
        model: EmbeddingModel,
        endpoint_suffix: str,
        api_base_suffix: str,
        timeouts: LocalProviderTimeouts,
        max_redirects: int,
        transport: httpx.AsyncBaseTransport | None,
    ) -> None:
        if model.provider != endpoint.provider.value:
            raise ValueError(
                "embedding model provider does not match endpoint provider"
            )
        if not isinstance(max_redirects, int) or isinstance(max_redirects, bool):
            raise ValueError("provider redirect limit must be an integer")
        if not 0 <= max_redirects <= self._MAX_REDIRECTS:
            raise ValueError(
                f"provider redirect limit must be between 0 and {self._MAX_REDIRECTS}"
            )
        self._model = model
        self._endpoint = _append_endpoint_suffix(
            endpoint,
            endpoint_suffix=endpoint_suffix,
            api_base_suffix=api_base_suffix,
        )
        self._max_redirects = max_redirects
        self._total_timeout = timeouts.total
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeouts.to_httpx(),
            transport=transport,
            trust_env=False,
        )

    @property
    def model(self) -> EmbeddingModel:
        return self._model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> _LocalEmbeddingProvider:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def _post_json(self, body: Mapping[str, object]) -> Mapping[str, Any]:
        try:
            async with asyncio.timeout(self._total_timeout):
                return await self._post_json_with_redirects(body)
        except TimeoutError as exc:
            raise LocalProviderTimeoutError(
                "local embedding provider exceeded the total time limit"
            ) from exc

    async def _post_json_with_redirects(
        self, body: Mapping[str, object]
    ) -> Mapping[str, Any]:
        endpoint = self._endpoint
        redirects_followed = 0
        while True:
            try:
                request = self._client.build_request("POST", endpoint.url, json=body)
                response = await self._client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise LocalProviderTimeoutError(
                    "local embedding provider request timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise LocalProviderError(
                    "local embedding provider request failed"
                ) from exc

            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise LocalProviderResponseError(
                            "local embedding provider redirect is missing a location"
                        )
                    if redirects_followed >= self._max_redirects:
                        raise LocalProviderSecurityError(
                            "local embedding provider redirect limit was exceeded"
                        )
                    try:
                        endpoint = validate_redirect_target(endpoint, location)
                    except ProviderEndpointError as exc:
                        raise LocalProviderSecurityError(
                            "local embedding provider redirect target is not permitted"
                        ) from exc
                    redirects_followed += 1
                    continue

                if not 200 <= response.status_code < 300:
                    raise LocalProviderError(
                        f"local embedding provider returned HTTP {response.status_code}"
                    )
                content_type = response.headers.get("content-type", "")
                media_type = content_type.partition(";")[0].strip().lower()
                if media_type != "application/json" and not media_type.endswith(
                    "+json"
                ):
                    raise LocalProviderResponseError(
                        "local embedding provider returned a non-JSON response"
                    )
                chunks: list[bytes] = []
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > self._MAX_RESPONSE_BYTES:
                        raise LocalProviderResponseError(
                            "local embedding provider response exceeded the size limit"
                        )
                    chunks.append(chunk)
                try:
                    payload = json.loads(b"".join(chunks))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise LocalProviderResponseError(
                        "local embedding provider returned malformed JSON"
                    ) from exc
            except httpx.TimeoutException as exc:
                raise LocalProviderTimeoutError(
                    "local embedding provider response timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise LocalProviderError(
                    "local embedding provider response failed"
                ) from exc
            finally:
                try:
                    await response.aclose()
                except httpx.TimeoutException as exc:
                    raise LocalProviderTimeoutError(
                        "local embedding provider response close timed out"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise LocalProviderError(
                        "local embedding provider response close failed"
                    ) from exc
            if not isinstance(payload, dict):
                raise LocalProviderResponseError(
                    "local embedding provider response must be an object"
                )
            return payload

    def _validate_response_identity(self, payload: Mapping[str, Any]) -> None:
        if payload.get("model") != self._model.model:
            raise LocalProviderResponseError(
                "provider response model does not match the configured embedding model"
            )
        if "version" in payload and payload["version"] != self._model.version:
            raise LocalProviderResponseError(
                "provider response version does not match the configured embedding version"
            )


class OpenAICompatibleEmbeddingProvider(_LocalEmbeddingProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        version: str,
        dimensions: int,
        timeouts: LocalProviderTimeouts | None = None,
        max_redirects: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            endpoint=validate_openai_compatible_endpoint(base_url),
            model=EmbeddingModel(
                provider=ProviderKind.OPENAI_COMPATIBLE.value,
                model=model,
                version=version,
                dimensions=dimensions,
            ),
            endpoint_suffix="/v1/embeddings",
            api_base_suffix="/v1",
            timeouts=timeouts or LocalProviderTimeouts(),
            max_redirects=max_redirects,
            transport=transport,
        )

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        values = _validate_text_batch(texts)
        if not values:
            return ()
        payload = await self._post_json(
            {"input": list(values), "model": self.model.model}
        )
        self._validate_response_identity(payload)
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(values):
            raise LocalProviderResponseError(
                "provider response embedding count does not match the request"
            )

        ordered: list[tuple[float, ...] | None] = [None] * len(values)
        for item in data:
            if not isinstance(item, dict):
                raise LocalProviderResponseError(
                    "provider response embedding item must be an object"
                )
            index = item.get("index")
            if not isinstance(index, int) or isinstance(index, bool):
                raise LocalProviderResponseError(
                    "provider response embedding index is invalid"
                )
            if not 0 <= index < len(values) or ordered[index] is not None:
                raise LocalProviderResponseError(
                    "provider response embedding indexes are invalid"
                )
            ordered[index] = _validate_response_vector(
                item.get("embedding"), self.model
            )
        if any(vector is None for vector in ordered):
            raise LocalProviderResponseError(
                "provider response embedding indexes are incomplete"
            )
        return tuple(vector for vector in ordered if vector is not None)

    async def embed_query(self, text: str) -> Sequence[float]:
        return (await self.embed_documents((text,)))[0]


class OllamaEmbeddingProvider(_LocalEmbeddingProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        version: str,
        dimensions: int,
        timeouts: LocalProviderTimeouts | None = None,
        max_redirects: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            endpoint=validate_ollama_endpoint(base_url),
            model=EmbeddingModel(
                provider=ProviderKind.OLLAMA.value,
                model=model,
                version=version,
                dimensions=dimensions,
            ),
            endpoint_suffix="/api/embed",
            api_base_suffix="/api",
            timeouts=timeouts or LocalProviderTimeouts(),
            max_redirects=max_redirects,
            transport=transport,
        )

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        values = _validate_text_batch(texts)
        if not values:
            return ()
        payload = await self._post_json(
            {"input": list(values), "model": self.model.model}
        )
        self._validate_response_identity(payload)
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(values):
            raise LocalProviderResponseError(
                "provider response embedding count does not match the request"
            )
        return tuple(
            _validate_response_vector(vector, self.model) for vector in embeddings
        )

    async def embed_query(self, text: str) -> Sequence[float]:
        return (await self.embed_documents((text,)))[0]


def _append_endpoint_suffix(
    endpoint: ProviderEndpoint,
    *,
    endpoint_suffix: str,
    api_base_suffix: str,
) -> ProviderEndpoint:
    parts = urlsplit(endpoint.url)
    path = parts.path.rstrip("/")
    if path.endswith(endpoint_suffix):
        target_path = path
    elif path.endswith(api_base_suffix):
        target_path = path + endpoint_suffix.removeprefix(api_base_suffix)
    else:
        target_path = path + endpoint_suffix
    target_url = urlunsplit((parts.scheme, parts.netloc, target_path, parts.query, ""))
    return validate_provider_endpoint(endpoint.provider, target_url)


def _validate_text_batch(texts: Sequence[str]) -> tuple[str, ...]:
    if isinstance(texts, (str, bytes)):
        raise ValueError("embedding document input must be a sequence of strings")
    values = tuple(texts)
    if any(not isinstance(text, str) or not text.strip() for text in values):
        raise ValueError("embedding input text must not be empty")
    if len(values) > 64:
        raise ValueError("embedding input batch must not exceed 64 texts")
    if sum(len(text) for text in values) > 2_000_000:
        raise ValueError("embedding input batch text exceeds the size limit")
    return values


def _validate_response_vector(
    value: object,
    model: EmbeddingModel,
) -> tuple[float, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, (int, float)) or isinstance(item, bool) for item in value
    ):
        raise LocalProviderResponseError(
            "provider response embedding must be a numeric array"
        )
    try:
        return validate_embedding(value, model=model)
    except (TypeError, ValueError) as exc:
        raise LocalProviderResponseError(
            "provider response embedding has invalid dimensions or values"
        ) from exc
