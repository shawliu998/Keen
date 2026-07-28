from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.agent.provider import (
    ContentDelta,
    FixedAutomationProvider,
    ProviderFinished,
    ProviderRequest,
    ProviderToolResult,
)


def _feedback(**overrides: object) -> ProviderToolResult:
    values: dict[str, object] = {
        "call_id": "call-1",
        "tool_name": "search_notes",
        "invocation_id": "invocation-1",
        "trust": "untrusted_tool_data",
        "fidelity": "full",
        "replayed": False,
        "output": {"matches": [{"note_id": "note-1"}]},
        "mutation_ids": (),
    }
    values.update(overrides)
    return ProviderToolResult.model_validate(values)


def test_provider_tool_result_is_closed_bounded_and_serializable() -> None:
    feedback = _feedback(mutation_ids=("mutation-1", "mutation:2"))

    assert feedback.model_dump(mode="json") == {
        "call_id": "call-1",
        "tool_name": "search_notes",
        "invocation_id": "invocation-1",
        "trust": "untrusted_tool_data",
        "fidelity": "full",
        "replayed": False,
        "output": {"matches": [{"note_id": "note-1"}]},
        "mutation_ids": ["mutation-1", "mutation:2"],
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _feedback(private_trace="not allowed")

    with pytest.raises(ValidationError):
        _feedback(replayed="false")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("call_id", "invalid/call"),
        ("call_id", "x" * 129),
        ("tool_name", "SearchNotes"),
        ("tool_name", "x" * 81),
        ("invocation_id", " invalid"),
        ("invocation_id", "x" * 129),
        ("mutation_ids", ("invalid/mutation",)),
        ("mutation_ids", ("x" * 257,)),
        ("mutation_ids", tuple(f"mutation-{index}" for index in range(101))),
    ],
)
def test_provider_tool_result_rejects_unsafe_or_unbounded_ids(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        _feedback(**{field: value})


@pytest.mark.parametrize(
    "output",
    [
        {"reasoning": "private"},
        {"nested": [{"chainOfThought": "private"}]},
        {"value": float("nan")},
        {"value": "x" * 65_537},
    ],
)
def test_provider_tool_result_rejects_unsafe_output(
    output: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _feedback(output=output)


def test_fixed_automation_provider_records_read_only_feedback_and_keeps_stream() -> (
    None
):
    provider = FixedAutomationProvider(
        [ContentDelta(text="answer"), ProviderFinished()]
    )
    first = _feedback()
    second = _feedback(
        call_id="call-2",
        invocation_id="invocation-2",
        replayed=True,
        fidelity="audit_summary",
        output={"recovered": True},
        mutation_ids=("mutation-1",),
    )

    async def exercise() -> list[object]:
        await provider.submit_tool_result(first)
        await provider.submit_tool_result(second)
        request = ProviderRequest(
            run_id="run-1",
            user_intent="Explain limits",
            mode="teach",
        )
        return [action async for action in provider.stream(request)]

    actions = asyncio.run(exercise())

    assert provider.tool_results == (first, second)
    assert isinstance(provider.tool_results, tuple)
    assert actions == [ContentDelta(text="answer"), ProviderFinished()]
