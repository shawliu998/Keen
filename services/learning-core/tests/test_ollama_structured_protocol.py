from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import pytest

from app.agent.local_protocol import TextRound, ToolRound, parse_ollama_response
from app.agent.provider import ProviderOutputError

MODEL = "qwen-local"
ALLOWED = {"list_study_feed"}


def _text_response() -> dict[str, Any]:
    return {
        "model": MODEL,
        "created_at": "2026-07-17T00:00:00Z",
        "message": {"role": "assistant", "content": "Review algebra."},
        "done": True,
        "done_reason": "stop",
        "total_duration": 10,
        "eval_count": 2,
    }


def _tool_response(arguments: object | None = None) -> dict[str, Any]:
    return {
        "model": MODEL,
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "list_study_feed",
                        "arguments": {"limit": 4} if arguments is None else arguments,
                    }
                }
            ],
        },
        "done": True,
        "done_reason": "stop",
    }


def _parse(response: dict[str, Any], *, round_index: int = 2) -> TextRound | ToolRound:
    return parse_ollama_response(
        response,
        expected_model=MODEL,
        allowed_tool_names=ALLOWED,
        round_index=round_index,
    )


def test_normalizes_text_round() -> None:
    round_result = _parse(_text_response())

    assert round_result == TextRound(
        content="Review algebra.",
        wire_message={"role": "assistant", "content": "Review algebra."},
    )


def test_normalizes_tool_round_and_generates_stable_internal_call_id() -> None:
    first = _parse(_tool_response(), round_index=7)
    second = _parse(_tool_response(), round_index=7)

    assert isinstance(first, ToolRound)
    assert first.call_id == second.call_id
    assert first.call_id.startswith("ollama:7:")
    assert first.tool_name == "list_study_feed"
    assert first.arguments == {"limit": 4}
    assert "id" not in first.wire_message["tool_calls"][0]


def test_internal_call_id_uses_round_name_and_canonical_arguments() -> None:
    baseline = _parse(_tool_response({"a": 1, "b": 2}), round_index=3)
    reordered = _parse(_tool_response({"b": 2, "a": 1}), round_index=3)
    next_round = _parse(_tool_response({"a": 1, "b": 2}), round_index=4)

    assert isinstance(baseline, ToolRound)
    assert baseline.call_id == reordered.call_id
    assert baseline.call_id != next_round.call_id


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(model="wrong"),
        lambda value: value.update(done=False),
        lambda value: value.update(done_reason="length"),
        lambda value: value["message"].update(role="tool"),
        lambda value: value.update(unknown="field"),
        lambda value: value["message"].update(unknown="field"),
        lambda value: value["message"].update(images=[]),
        lambda value: value["message"].update(thinking="private reasoning"),
    ],
)
def test_rejects_invalid_or_unsupported_response_shapes(
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    response = _text_response()
    mutate(response)

    with pytest.raises(ProviderOutputError, match="structured-output contract"):
        _parse(response)


@pytest.mark.parametrize("content", ["", "  ", "\n"])
def test_text_round_requires_nonblank_content(content: str) -> None:
    response = _text_response()
    response["message"]["content"] = content

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_tool_round_rejects_mixed_visible_content() -> None:
    response = _tool_response()
    response["message"]["content"] = "I will call a tool"

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_rejects_parallel_tool_calls() -> None:
    response = _tool_response()
    calls = response["message"]["tool_calls"]
    calls.append(deepcopy(calls[0]))

    with pytest.raises(ProviderOutputError):
        _parse(response)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda call: call["function"].update(name="unknown_tool"),
        lambda call: call["function"].update(arguments='{"limit":4}'),
        lambda call: call.update(id="provider-supplied-id"),
        lambda call: call.update(type="function"),
    ],
)
def test_rejects_invalid_tool_call_shape(
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    response = _tool_response()
    call = response["message"]["tool_calls"][0]
    mutation(call)

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_rejects_argument_object_over_64_kib() -> None:
    response = _tool_response({"value": "x" * (64 * 1024)})

    with pytest.raises(ProviderOutputError):
        _parse(response)


def test_rejects_negative_round_index() -> None:
    with pytest.raises(ProviderOutputError):
        _parse(_tool_response(), round_index=-1)


def test_does_not_retain_empty_thinking_field() -> None:
    response = _text_response()
    response["message"]["thinking"] = ""

    round_result = _parse(response)

    assert "thinking" not in round_result.wire_message
