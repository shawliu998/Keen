from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .provider import ProviderOutputError
from .types import is_safe_identifier, validate_bounded_json_object

_MAX_ARGUMENT_BYTES = 64 * 1024
_MAX_CALL_ID_CHARS = 128
_MAX_REASONING_CONTENT_CHARS = 65_536
_MAX_TOKEN_COUNT = 2**63 - 1
_OPENAI_ERROR = "OpenAI response violates the structured-output contract"
_OLLAMA_ERROR = "Ollama response violates the structured-output contract"


class TextRound(BaseModel):
    """A normalized provider round containing user-facing assistant text."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["text"] = "text"
    content: str = Field(min_length=1, max_length=131_072)
    wire_message: dict[str, object]

    @field_validator("content")
    @classmethod
    def validate_visible_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("assistant content must not be blank")
        return value

    @field_validator("wire_message")
    @classmethod
    def validate_wire_message(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        return value


class ToolRound(BaseModel):
    """A normalized single tool request plus its provider wire message."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["tool"] = "tool"
    call_id: str = Field(
        min_length=1,
        max_length=_MAX_CALL_ID_CHARS,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    tool_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]{0,79}$",
    )
    arguments: dict[str, object]
    wire_message: dict[str, object]

    @field_validator("arguments", "wire_message")
    @classmethod
    def validate_json_object(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        return value


StructuredRound: TypeAlias = TextRound | ToolRound


class _StrictWireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _OpenAIFunction(_StrictWireModel):
    name: str
    arguments: str


class _OpenAIToolCall(_StrictWireModel):
    id: str
    type: Literal["function"]
    function: _OpenAIFunction
    index: Literal[0] | None = None


class _OpenAIMessage(_StrictWireModel):
    role: Literal["assistant"]
    content: str | None
    tool_calls: list[_OpenAIToolCall] | None = None
    refusal: str | None = None
    # Some OpenAI-compatible providers expose hidden reasoning separately.  It
    # is validated only to keep the envelope bounded, then deliberately dropped.
    reasoning_content: str | None = Field(
        max_length=_MAX_REASONING_CONTENT_CHARS, default=None
    )


class _OpenAIChoice(_StrictWireModel):
    index: int
    message: _OpenAIMessage
    finish_reason: str
    logprobs: None = None
    provider_specific_fields: dict[str, object] | None = None

    @field_validator("provider_specific_fields")
    @classmethod
    def validate_provider_specific_fields(
        cls, value: dict[str, object] | None
    ) -> dict[str, object] | None:
        if value is not None:
            validate_bounded_json_object(value)
        return value


class _OpenAIPromptTokenDetails(_StrictWireModel):
    audio_tokens: int | None = None
    cached_tokens: int | None = None


class _OpenAICompletionTokenDetails(_StrictWireModel):
    accepted_prediction_tokens: int | None = None
    audio_tokens: int | None = None
    reasoning_tokens: int | None = None
    rejected_prediction_tokens: int | None = None


class _OpenAIUsage(_StrictWireModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: _OpenAIPromptTokenDetails | None = None
    completion_tokens_details: _OpenAICompletionTokenDetails | None = None
    prompt_cache_hit_tokens: int | None = Field(ge=0, le=_MAX_TOKEN_COUNT, default=None)
    prompt_cache_miss_tokens: int | None = Field(
        ge=0, le=_MAX_TOKEN_COUNT, default=None
    )


class _OpenAIResponse(_StrictWireModel):
    model: str
    choices: list[_OpenAIChoice]
    id: str | None = None
    object: Literal["chat.completion"] | None = None
    created: int | None = None
    service_tier: str | None = None
    system_fingerprint: str | None = None
    usage: _OpenAIUsage | None = None


class _OllamaFunction(_StrictWireModel):
    name: str
    arguments: dict[str, object]

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        return value


class _OllamaToolCall(_StrictWireModel):
    function: _OllamaFunction


class _OllamaMessage(_StrictWireModel):
    role: Literal["assistant"]
    content: str
    thinking: str | None = None
    tool_calls: list[_OllamaToolCall] | None = None


class _OllamaResponse(_StrictWireModel):
    model: str
    created_at: str | None = None
    message: _OllamaMessage
    done: bool
    done_reason: str
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None


class _DuplicateJsonKey(ValueError):
    pass


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> object:
    raise ValueError


def _decode_openai_arguments(value: str) -> dict[str, object]:
    if len(value.encode("utf-8")) > _MAX_ARGUMENT_BYTES:
        raise ValueError
    decoded = json.loads(
        value,
        object_pairs_hook=_object_without_duplicate_keys,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(decoded, dict):
        raise ValueError
    validate_bounded_json_object(decoded)
    return decoded


def _canonical_arguments(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _ollama_call_id(
    *, round_index: int, tool_name: str, arguments: dict[str, object]
) -> str:
    canonical_call = _canonical_arguments(
        {"arguments": arguments, "name": tool_name}
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_call).hexdigest()
    return f"ollama:{round_index}:{digest}"


def parse_openai_response(
    response: dict[str, object],
    *,
    expected_model: str,
    allowed_tool_names: Collection[str],
    seen_call_ids: Collection[str] = (),
) -> StructuredRound:
    """Normalize one complete OpenAI-compatible chat-completion response."""

    try:
        parsed = _OpenAIResponse.model_validate(response)
        if parsed.model != expected_model or len(parsed.choices) != 1:
            raise ValueError
        choice = parsed.choices[0]
        if choice.index != 0 or choice.message.refusal not in (None, ""):
            raise ValueError

        message = choice.message
        tool_calls = message.tool_calls or ()
        if choice.finish_reason == "stop":
            if tool_calls or message.content is None or not message.content.strip():
                raise ValueError
            return TextRound(
                content=message.content,
                wire_message={"role": "assistant", "content": message.content},
            )

        if choice.finish_reason != "tool_calls":
            raise ValueError
        if message.content is not None and message.content.strip():
            raise ValueError
        if len(tool_calls) != 1:
            raise ValueError

        tool_call = tool_calls[0]
        if (
            not is_safe_identifier(tool_call.id)
            or len(tool_call.id) > _MAX_CALL_ID_CHARS
            or tool_call.id in seen_call_ids
            or tool_call.function.name not in allowed_tool_names
        ):
            raise ValueError
        arguments = _decode_openai_arguments(tool_call.function.arguments)
        return ToolRound(
            call_id=tool_call.id,
            tool_name=tool_call.function.name,
            arguments=arguments,
            wire_message={
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                ],
            },
        )
    except (UnicodeError, ValueError, TypeError, ValidationError, json.JSONDecodeError):
        raise ProviderOutputError(_OPENAI_ERROR) from None


def parse_ollama_response(
    response: dict[str, object],
    *,
    expected_model: str,
    allowed_tool_names: Collection[str],
    round_index: int,
) -> StructuredRound:
    """Normalize one complete non-streaming Ollama chat response."""

    try:
        if round_index < 0:
            raise ValueError
        parsed = _OllamaResponse.model_validate(response)
        if (
            parsed.model != expected_model
            or parsed.done is not True
            or parsed.done_reason != "stop"
            or parsed.message.thinking not in (None, "")
        ):
            raise ValueError

        message = parsed.message
        tool_calls = message.tool_calls or ()
        if not tool_calls:
            if not message.content.strip():
                raise ValueError
            return TextRound(
                content=message.content,
                wire_message={"role": "assistant", "content": message.content},
            )

        if message.content.strip() or len(tool_calls) != 1:
            raise ValueError
        tool_call = tool_calls[0]
        name = tool_call.function.name
        arguments = tool_call.function.arguments
        if name not in allowed_tool_names:
            raise ValueError
        canonical_arguments = _canonical_arguments(arguments)
        if len(canonical_arguments.encode("utf-8")) > _MAX_ARGUMENT_BYTES:
            raise ValueError
        call_id = _ollama_call_id(
            round_index=round_index,
            tool_name=name,
            arguments=arguments,
        )
        return ToolRound(
            call_id=call_id,
            tool_name=name,
            arguments=arguments,
            wire_message={
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "function": {
                            "name": name,
                            "arguments": arguments,
                        }
                    }
                ],
            },
        )
    except (UnicodeError, ValueError, TypeError, ValidationError):
        raise ProviderOutputError(_OLLAMA_ERROR) from None


__all__ = [
    "StructuredRound",
    "TextRound",
    "ToolRound",
    "parse_ollama_response",
    "parse_openai_response",
]
