from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from app.agent.local_protocol import (
    TextRound,
    ToolRound,
    parse_openai_response,
)
from app.agent.provider import ProviderOutputError

MODEL = "local-model"
ALLOWED = {"list_due_reviews"}


def _text_response() -> dict[str, Any]:
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": 1,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Study this next."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
    }


def _tool_response(arguments: object = '{"limit":3}') -> dict[str, Any]:
    return {
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "list_due_reviews",
                                "arguments": arguments,
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }


def _parse(response: dict[str, Any], **kwargs: object) -> TextRound | ToolRound:
    return parse_openai_response(
        response,
        expected_model=MODEL,
        allowed_tool_names=ALLOWED,
        **kwargs,  # type: ignore[arg-type]
    )


def test_normalizes_text_round_and_drops_nonessential_wire_fields() -> None:
    round_result = _parse(_text_response())

    assert round_result == TextRound(
        content="Study this next.",
        wire_message={"role": "assistant", "content": "Study this next."},
    )
    assert "usage" not in round_result.wire_message


def test_accepts_and_drops_bounded_deepseek_compatibility_fields() -> None:
    response = _text_response()
    choice = response["choices"][0]
    choice["provider_specific_fields"] = {"finish_details": {"reason": "stop"}}
    choice["message"]["reasoning_content"] = "private model reasoning"
    response["usage"].update(
        prompt_cache_hit_tokens=2,
        prompt_cache_miss_tokens=2,
    )

    round_result = _parse(response)

    assert round_result.wire_message == {
        "role": "assistant",
        "content": "Study this next.",
    }
    assert "reasoning_content" not in str(round_result.wire_message)
    assert "provider_specific_fields" not in str(round_result.wire_message)


@pytest.mark.parametrize(
    "path,value",
    [
        (("choices", 0, "message", "reasoning_content"), "x" * 65_537),
        (("choices", 0, "message", "reasoning_content"), {"not": "text"}),
        (("choices", 0, "provider_specific_fields"), ["not", "an", "object"]),
        (("choices", 0, "provider_specific_fields"), {"value": "x" * 65_537}),
        (("usage", "prompt_cache_hit_tokens"), -1),
        (("usage", "prompt_cache_hit_tokens"), True),
        (("usage", "prompt_cache_miss_tokens"), 2**63),
        (("usage", "prompt_cache_miss_tokens"), "2"),
    ],
)
def test_rejects_invalid_deepseek_compatibility_fields(
    path: tuple[object, ...], value: object
) -> None:
    response = _text_response()
    target: object = response
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ProviderOutputError, match="structured-output contract"):
        _parse(response)


@pytest.mark.parametrize(
    "path",
    [
        ("choices", 0, "unexpected"),
        ("choices", 0, "message", "unexpected"),
        ("usage", "unexpected"),
    ],
)
def test_deepseek_compatibility_does_not_allow_other_unknown_fields(
    path: tuple[object, ...],
) -> None:
    response = _text_response()
    target: object = response
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[index]
    target[path[-1]] = "unexpected"  # type: ignore[index]

    with pytest.raises(ProviderOutputError, match="structured-output contract"):
        _parse(response)


def test_normalizes_exactly_one_allowed_tool_call() -> None:
    response = _tool_response()
    response["choices"][0]["message"]["tool_calls"][0]["index"] = 0

    round_result = _parse(response)

    assert isinstance(round_result, ToolRound)
    assert round_result.call_id == "call_1"
    assert round_result.tool_name == "list_due_reviews"
    assert round_result.arguments == {"limit": 3}
    assert round_result.wire_message["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "list_due_reviews",
                "arguments": '{"limit":3}',
            },
        }
    ]
    assert "index" not in round_result.wire_message["tool_calls"][0]


@pytest.mark.parametrize("index", [-1, 1, True, "0"])
def test_rejects_invalid_tool_call_index(index: object) -> None:
    response = _tool_response()
    response["choices"][0]["message"]["tool_calls"][0]["index"] = index

    with pytest.raises(ProviderOutputError, match="structured-output contract"):
        _parse(response)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(model="wrong-model"),
        lambda value: value["choices"].append(deepcopy(value["choices"][0])),
        lambda value: value["choices"][0].update(index=1),
        lambda value: value["choices"][0].pop("finish_reason"),
        lambda value: value["choices"][0].update(finish_reason="length"),
        lambda value: value["choices"][0].update(finish_reason="content_filter"),
        lambda value: value.update(unexpected="field"),
        lambda value: value["choices"][0]["message"].update(role="tool"),
    ],
)
def test_rejects_invalid_response_envelopes(
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    response = _text_response()
    mutate(response)

    with pytest.raises(ProviderOutputError, match="structured-output contract"):
        _parse(response)


@pytest.mark.parametrize("content", [None, "", "   "])
def test_stop_requires_nonblank_text(content: str | None) -> None:
    response = _text_response()
    response["choices"][0]["message"]["content"] = content

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_stop_rejects_tool_calls() -> None:
    response = _text_response()
    response["choices"][0]["message"]["tool_calls"] = _tool_response()["choices"][0][
        "message"
    ]["tool_calls"]

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_rejects_legacy_function_call_even_when_null() -> None:
    response = _text_response()
    response["choices"][0]["message"]["function_call"] = None

    with pytest.raises(ProviderOutputError):
        _parse(response)


@pytest.mark.parametrize("content", ["mixed", " tool result "])
def test_tool_call_rejects_mixed_visible_content(content: str) -> None:
    response = _tool_response()
    response["choices"][0]["message"]["content"] = content

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_tool_call_allows_whitespace_only_content() -> None:
    response = _tool_response()
    response["choices"][0]["message"]["content"] = " \n"

    assert isinstance(_parse(response), ToolRound)


def test_rejects_parallel_tool_calls() -> None:
    response = _tool_response()
    calls = response["choices"][0]["message"]["tool_calls"]
    calls.append(deepcopy(calls[0]))
    calls[1]["id"] = "call_2"

    with pytest.raises(ProviderOutputError):
        _parse(response)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda call: call.update(id="unsafe id"),
        lambda call: call.update(type="custom"),
        lambda call: call["function"].update(name="unknown_tool"),
        lambda call: call["function"].update(arguments={"limit": 3}),
        lambda call: call.update(unexpected="field"),
    ],
)
def test_rejects_invalid_tool_call_shape(
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    response = _tool_response()
    call = response["choices"][0]["message"]["tool_calls"][0]
    mutation(call)

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_rejects_seen_call_id() -> None:
    with pytest.raises(ProviderOutputError):
        _parse(_tool_response(), seen_call_ids={"call_1"})


@pytest.mark.parametrize(
    "arguments",
    [
        '{"limit":1,"limit":2}',
        '{"outer":{"limit":1,"limit":2}}',
        "[]",
        "null",
        "{not-json}",
        '{"limit":NaN}',
    ],
)
def test_rejects_unsafe_argument_json(arguments: str) -> None:
    with pytest.raises(ProviderOutputError):
        _parse(_tool_response(arguments))


def test_rejects_argument_json_over_64_kib() -> None:
    arguments = '{"value":"' + ("x" * (64 * 1024)) + '"}'

    with pytest.raises(ProviderOutputError):
        _parse(_tool_response(arguments))


def test_errors_do_not_echo_response_or_argument_content() -> None:
    secret = "PRIVATE_ARGUMENT_CONTENT"

    with pytest.raises(ProviderOutputError) as error:
        _parse(_tool_response('{"secret":"' + secret + '","x":}'))

    assert secret not in str(error.value)


def test_round_models_are_frozen_and_forbid_extra_fields() -> None:
    round_result = _parse(_text_response())

    with pytest.raises(ValidationError):
        round_result.content = "changed"
    with pytest.raises(ValidationError):
        TextRound(content="ok", wire_message={}, unexpected=True)
