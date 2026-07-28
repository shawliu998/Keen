from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import httpx

from .chat_interfaces import ChatMessage, ChatModel
from .local_providers import (
    LocalProviderError,
    LocalProviderResponseError,
    LocalProviderSecurityError,
    LocalProviderTimeoutError,
    LocalProviderTimeouts,
)
from .provider_endpoints import (
    ProviderEndpoint,
    ProviderEndpointError,
    ProviderKind,
    validate_ollama_endpoint,
    validate_openai_compatible_endpoint,
    validate_provider_endpoint,
    validate_redirect_target,
)


class _LocalChatProvider:
    _MAX_REDIRECTS = 5
    _MAX_RESPONSE_BYTES = 16 * 1024 * 1024
    _MAX_LINE_BYTES = 1024 * 1024
    _MAX_AGENT_JSON_RESPONSE_BYTES = 1024 * 1024

    def __init__(
        self,
        *,
        endpoint: ProviderEndpoint,
        model: ChatModel,
        endpoint_suffix: str,
        api_base_suffix: str,
        timeouts: LocalProviderTimeouts,
        max_redirects: int,
        transport: httpx.AsyncBaseTransport | None,
        headers: Mapping[str, str] | None = None,
        probe_endpoint_suffix: str,
    ) -> None:
        if model.provider != endpoint.provider.value:
            raise ValueError("chat model provider does not match endpoint provider")
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
        self._probe_endpoint = _append_endpoint_suffix(
            endpoint,
            endpoint_suffix=probe_endpoint_suffix,
            api_base_suffix=api_base_suffix,
        )
        self._max_redirects = max_redirects
        self._headers = dict(headers or {})
        self._total_timeout = timeouts.total
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeouts.to_httpx(),
            transport=transport,
            trust_env=False,
        )

    @property
    def model(self) -> ChatModel:
        return self._model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _open_response(self, body: Mapping[str, object]) -> httpx.Response:
        return await self._open_request("POST", self._endpoint, body)

    async def _open_request(
        self,
        method: str,
        initial_endpoint: ProviderEndpoint,
        body: Mapping[str, object] | None = None,
    ) -> httpx.Response:
        endpoint = initial_endpoint
        redirects_followed = 0
        while True:
            try:
                request = self._client.build_request(
                    method, endpoint.url, json=body, headers=self._headers or None
                )
                response = await self._client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise LocalProviderTimeoutError(
                    "local chat provider request timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise LocalProviderError("local chat provider request failed") from exc

            if response.status_code not in {301, 302, 303, 307, 308}:
                if not 200 <= response.status_code < 300:
                    await response.aclose()
                    raise LocalProviderError(
                        f"local chat provider returned HTTP {response.status_code}"
                    )
                return response

            location = response.headers.get("location")
            await response.aclose()
            if not location:
                raise LocalProviderResponseError(
                    "local chat provider redirect is missing a location"
                )
            if redirects_followed >= self._max_redirects:
                raise LocalProviderSecurityError(
                    "local chat provider redirect limit was exceeded"
                )
            try:
                endpoint = validate_redirect_target(endpoint, location)
            except ProviderEndpointError as exc:
                raise LocalProviderSecurityError(
                    "local chat provider redirect target is not permitted"
                ) from exc
            redirects_followed += 1

    async def probe_model(self) -> None:
        response: httpx.Response | None = None
        try:
            response = await self._open_request("GET", self._probe_endpoint)
            payload = await self._read_agent_json_response(response)
            if self.model.provider == ProviderKind.OLLAMA.value:
                models = payload.get("models")
                matches = isinstance(models, list) and any(
                    isinstance(item, dict) and item.get("name") == self.model.model
                    for item in models
                )
            else:
                models = payload.get("data")
                matches = isinstance(models, list) and any(
                    isinstance(item, dict) and item.get("id") == self.model.model
                    for item in models
                )
            if not matches:
                raise LocalProviderResponseError(
                    "configured chat model was not returned by the provider"
                )
        finally:
            if response is not None:
                await response.aclose()

    async def complete_agent_json(
        self, body: Mapping[str, object]
    ) -> dict[str, object]:
        """Send a bounded non-streaming JSON request for a structured Agent run.

        This intentionally validates only the transport envelope. Callers own the
        provider-specific response and tool-call protocol validation.
        """

        response: httpx.Response | None = None
        try:
            async with asyncio.timeout(self._total_timeout):
                response = await self._open_response(body)
                return await self._read_agent_json_response(response)
        except TimeoutError as exc:
            raise LocalProviderTimeoutError(
                "local chat provider exceeded the total time limit"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LocalProviderTimeoutError(
                "local chat provider response timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalProviderError("local chat provider response failed") from exc
        finally:
            if response is not None:
                active_exception = sys.exception()
                try:
                    await response.aclose()
                except BaseException as exc:
                    if active_exception is not None:
                        # Cleanup is best-effort once a request has already failed or
                        # been cancelled. Preserve that primary outcome for the caller.
                        pass
                    elif isinstance(exc, httpx.TimeoutException):
                        raise LocalProviderTimeoutError(
                            "local chat provider response close timed out"
                        ) from exc
                    elif isinstance(exc, httpx.HTTPError):
                        raise LocalProviderError(
                            "local chat provider response close failed"
                        ) from exc
                    else:
                        raise

    async def _read_agent_json_response(
        self, response: httpx.Response
    ) -> dict[str, object]:
        content_type = response.headers.get("content-type", "")
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type != "application/json":
            raise LocalProviderResponseError(
                "local chat provider returned a non-JSON response"
            )

        content_encoding = response.headers.get("content-encoding")
        if (
            content_encoding is not None
            and content_encoding.strip().lower() != "identity"
        ):
            raise LocalProviderResponseError(
                "local chat provider returned an unsupported content encoding"
            )

        content_length = response.headers.get("content-length")
        if content_length is not None:
            length = content_length.strip()
            if (
                not length
                or not length.isascii()
                or not length.isdigit()
                or int(length) > self._MAX_AGENT_JSON_RESPONSE_BYTES
            ):
                raise LocalProviderResponseError(
                    "local chat provider response exceeded the size limit"
                )

        if response.is_stream_consumed:
            raw_body = response.content
            if len(raw_body) > self._MAX_AGENT_JSON_RESPONSE_BYTES:
                raise LocalProviderResponseError(
                    "local chat provider response exceeded the size limit"
                )
        else:
            chunks: list[bytes] = []
            received = 0
            async for chunk in response.aiter_raw():
                received += len(chunk)
                if received > self._MAX_AGENT_JSON_RESPONSE_BYTES:
                    raise LocalProviderResponseError(
                        "local chat provider response exceeded the size limit"
                    )
                chunks.append(chunk)
            raw_body = b"".join(chunks)

        try:
            payload = json.loads(
                raw_body.decode("utf-8"),
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise LocalProviderResponseError(
                "local chat provider returned malformed JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise LocalProviderResponseError(
                "local chat provider response must be an object"
            )
        return cast(dict[str, object], payload)

    async def _response_lines(
        self, response: httpx.Response, *, media_types: frozenset[str]
    ) -> AsyncIterator[str]:
        content_type = response.headers.get("content-type", "")
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type not in media_types:
            raise LocalProviderResponseError(
                "local chat provider returned an unsupported streaming response"
            )
        received = 0
        buffered = bytearray()
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > self._MAX_RESPONSE_BYTES:
                raise LocalProviderResponseError(
                    "local chat provider response exceeded the size limit"
                )
            buffered.extend(chunk)
            if len(buffered) > self._MAX_LINE_BYTES and b"\n" not in buffered:
                raise LocalProviderResponseError(
                    "local chat provider response line exceeded the size limit"
                )
            while b"\n" in buffered:
                raw_line, _, remainder = buffered.partition(b"\n")
                buffered = bytearray(remainder)
                if len(raw_line) > self._MAX_LINE_BYTES:
                    raise LocalProviderResponseError(
                        "local chat provider response line exceeded the size limit"
                    )
                try:
                    yield raw_line.rstrip(b"\r").decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise LocalProviderResponseError(
                        "local chat provider returned invalid UTF-8"
                    ) from exc
        if buffered:
            if len(buffered) > self._MAX_LINE_BYTES:
                raise LocalProviderResponseError(
                    "local chat provider response line exceeded the size limit"
                )
            try:
                yield bytes(buffered).rstrip(b"\r").decode("utf-8")
            except UnicodeDecodeError as exc:
                raise LocalProviderResponseError(
                    "local chat provider returned invalid UTF-8"
                ) from exc

    def _validate_response_identity(self, payload: Mapping[str, Any]) -> None:
        if payload.get("model") != self._model.model:
            raise LocalProviderResponseError(
                "provider response model does not match the configured chat model"
            )
        if "version" in payload and payload["version"] != self._model.version:
            raise LocalProviderResponseError(
                "provider response version does not match the configured chat version"
            )


class OpenAICompatibleChatProvider(_LocalChatProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        version: str,
        api_key: str | None = None,
        timeouts: LocalProviderTimeouts | None = None,
        max_redirects: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            endpoint=validate_openai_compatible_endpoint(base_url),
            model=ChatModel(
                provider=ProviderKind.OPENAI_COMPATIBLE.value,
                model=model,
                version=version,
            ),
            endpoint_suffix="/v1/chat/completions",
            api_base_suffix="/v1",
            timeouts=timeouts or LocalProviderTimeouts(total=180.0),
            max_redirects=max_redirects,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
            probe_endpoint_suffix="/v1/models",
        )

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        values = _validate_messages(messages)
        response: httpx.Response | None = None
        completed = False
        finish_reason: str | None = None
        try:
            async with asyncio.timeout(self._total_timeout):
                response = await self._open_response(
                    {
                        "model": self.model.model,
                        "messages": [
                            {"role": item.role, "content": item.content}
                            for item in values
                        ],
                        "stream": True,
                    }
                )
                async for line in self._response_lines(
                    response,
                    media_types=frozenset(
                        {"text/event-stream", "application/x-ndjson"}
                    ),
                ):
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        if finish_reason != "stop":
                            raise LocalProviderResponseError(
                                "local chat provider ended without a normal stop reason"
                            )
                        completed = True
                        return
                    payload = _parse_object(data)
                    self._validate_response_identity(payload)
                    choices = payload.get("choices")
                    if not isinstance(choices, list) or len(choices) != 1:
                        raise LocalProviderResponseError(
                            "local chat provider returned invalid choices"
                        )
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise LocalProviderResponseError(
                            "local chat provider returned an invalid choice"
                        )
                    reason = choice.get("finish_reason")
                    if reason is not None:
                        if reason != "stop" or finish_reason is not None:
                            raise LocalProviderResponseError(
                                "local chat provider returned a non-normal stop reason"
                            )
                        finish_reason = reason
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        raise LocalProviderResponseError(
                            "local chat provider returned an invalid delta"
                        )
                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str):
                            raise LocalProviderResponseError(
                                "local chat provider returned non-text content"
                            )
                        if content:
                            yield content
                if not completed:
                    raise LocalProviderResponseError(
                        "local chat provider stream ended before the completion marker"
                    )
        except TimeoutError as exc:
            raise LocalProviderTimeoutError(
                "local chat provider exceeded the total time limit"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LocalProviderTimeoutError(
                "local chat provider response timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalProviderError("local chat provider response failed") from exc
        finally:
            if response is not None:
                await response.aclose()


class OllamaChatProvider(_LocalChatProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        version: str,
        timeouts: LocalProviderTimeouts | None = None,
        max_redirects: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            endpoint=validate_ollama_endpoint(base_url),
            model=ChatModel(
                provider=ProviderKind.OLLAMA.value,
                model=model,
                version=version,
            ),
            endpoint_suffix="/api/chat",
            api_base_suffix="/api",
            timeouts=timeouts or LocalProviderTimeouts(total=180.0),
            max_redirects=max_redirects,
            transport=transport,
            probe_endpoint_suffix="/api/tags",
        )

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        values = _validate_messages(messages)
        response: httpx.Response | None = None
        completed = False
        try:
            async with asyncio.timeout(self._total_timeout):
                response = await self._open_response(
                    {
                        "model": self.model.model,
                        "messages": [
                            {"role": item.role, "content": item.content}
                            for item in values
                        ],
                        "stream": True,
                    }
                )
                async for line in self._response_lines(
                    response,
                    media_types=frozenset({"application/x-ndjson", "application/json"}),
                ):
                    if not line.strip():
                        continue
                    payload = _parse_object(line)
                    self._validate_response_identity(payload)
                    message = payload.get("message")
                    if not isinstance(message, dict):
                        raise LocalProviderResponseError(
                            "local chat provider returned an invalid message"
                        )
                    content = message.get("content")
                    if not isinstance(content, str):
                        raise LocalProviderResponseError(
                            "local chat provider returned non-text content"
                        )
                    if content:
                        yield content
                    if payload.get("done") is True:
                        if payload.get("done_reason") != "stop":
                            raise LocalProviderResponseError(
                                "local chat provider returned a non-normal stop reason"
                            )
                        completed = True
                        return
                if not completed:
                    raise LocalProviderResponseError(
                        "local chat provider stream ended before the completion marker"
                    )
        except TimeoutError as exc:
            raise LocalProviderTimeoutError(
                "local chat provider exceeded the total time limit"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LocalProviderTimeoutError(
                "local chat provider response timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalProviderError("local chat provider response failed") from exc
        finally:
            if response is not None:
                await response.aclose()


def _append_endpoint_suffix(
    endpoint: ProviderEndpoint,
    *,
    endpoint_suffix: str,
    api_base_suffix: str,
) -> ProviderEndpoint:
    parts = urlsplit(endpoint.url)
    path = parts.path.rstrip("/")
    resource_suffix = endpoint_suffix.removeprefix(api_base_suffix)
    if path.endswith(endpoint_suffix):
        target_path = path
    elif path.endswith(api_base_suffix):
        target_path = path + resource_suffix
    elif path:
        # A non-empty path is an explicit API base contract, for example
        # /api/v1, /openai/v1, /v1beta/openai or /api/paas/v4. Preserve it
        # verbatim and append only the requested resource.
        target_path = path + resource_suffix
    else:
        # Root endpoints keep the legacy OpenAI/Ollama default API prefix.
        target_path = endpoint_suffix
    target_url = urlunsplit((parts.scheme, parts.netloc, target_path, parts.query, ""))
    return validate_provider_endpoint(endpoint.provider, target_url)


def _validate_messages(messages: Sequence[ChatMessage]) -> tuple[ChatMessage, ...]:
    if isinstance(messages, (str, bytes)):
        raise ValueError("chat messages must be a sequence")
    values = tuple(messages)
    if not values or any(not isinstance(item, ChatMessage) for item in values):
        raise ValueError("chat messages must not be empty")
    if len(values) > 64:
        raise ValueError("chat message count must not exceed 64")
    if sum(len(item.content) for item in values) > 256_000:
        raise ValueError("chat message content exceeds the size limit")
    return values


def _parse_object(value: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except ValueError as exc:
        raise LocalProviderResponseError(
            "local chat provider returned malformed JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise LocalProviderResponseError(
            "local chat provider response must be an object"
        )
    return parsed


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = item
    return result


def _reject_json_constant(_value: str) -> object:
    raise ValueError("non-finite JSON number")
