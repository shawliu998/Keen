from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from copy import deepcopy
from typing import Any, Literal

import pytest

import app.agent.local_chat as local_chat_module
from app.agent.catalog import ProviderToolSpec
from app.agent.local_chat import LocalChatAgentProvider
from app.agent.provider import (
    ContentDelta,
    ProviderFinished,
    ProviderOutputError,
    ProviderRequest,
    ProviderToolError,
    ProviderToolResult,
    ToolCall,
)
from app.chat_interfaces import ChatMessage, ChatModel


def _tool_spec() -> ProviderToolSpec:
    return ProviderToolSpec(
        name="list_due_reviews",
        description="List due reviews for the host-scoped course and run time.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "options": {
                    "type": "object",
                    "properties": {"compact": {"type": "boolean"}},
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    )


def _request(
    *,
    tools: tuple[ProviderToolSpec, ...] | None = None,
    output_format: Literal["text", "json_object"] = "text",
) -> ProviderRequest:
    return ProviderRequest(
        run_id="run-structured",
        user_intent="What should I review next?",
        mode="review",
        output_format=output_format,
        input={"course_scope_id": "trusted-course", "as_of": "fixed-run-time"},
        tools=tools if tools is not None else (_tool_spec(),),
    )


def _feedback(
    *,
    call_id: str = "call_due_1",
    tool_name: str = "list_due_reviews",
    output: dict[str, object] | None = None,
) -> ProviderToolResult:
    return ProviderToolResult(
        call_id=call_id,
        tool_name=tool_name,
        invocation_id="invocation-1",
        fidelity="full",
        replayed=False,
        output=output or {"private": "tool-only-value", "items": ["limits"]},
        mutation_ids=(),
    )


def _error_feedback(*, call_id: str = "call_due_1") -> ProviderToolError:
    return ProviderToolError(
        call_id=call_id,
        tool_name="list_due_reviews",
        invocation_id="invocation-error-1",
        code="invalid_arguments",
        category="validation",
        retryable=True,
        recovery_action="correct_arguments",
    )


def _openai_tool_response(
    *,
    call_id: str = "call_due_1",
    tool_name: str = "list_due_reviews",
) -> dict[str, Any]:
    return {
        "model": "keen-openai",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": '{"limit":3}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }


def _openai_text_response(content: str = "Review limits next.") -> dict[str, Any]:
    return {
        "model": "keen-openai",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _ollama_tool_response() -> dict[str, Any]:
    return {
        "model": "keen-ollama",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "list_due_reviews",
                        "arguments": {"limit": 3},
                    }
                }
            ],
        },
        "done": True,
        "done_reason": "stop",
    }


def _ollama_text_response() -> dict[str, Any]:
    return {
        "model": "keen-ollama",
        "message": {"role": "assistant", "content": "Review limits next."},
        "done": True,
        "done_reason": "stop",
    }


class _StructuredProvider:
    def __init__(
        self,
        provider_name: str,
        model_name: str,
        responses: Sequence[dict[str, object]],
    ) -> None:
        self.model = ChatModel(
            provider=provider_name,  # type: ignore[arg-type]
            model=model_name,
            version="model-v2",
        )
        self.responses = list(responses)
        self.bodies: list[dict[str, object]] = []
        self.closed = False

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        del messages
        raise AssertionError("structured requests must not use the text stream")
        yield  # pragma: no cover

    async def complete_agent_json(
        self, body: Mapping[str, object]
    ) -> dict[str, object]:
        self.bodies.append(deepcopy(dict(body)))
        if not self.responses:
            raise AssertionError("unexpected extra completion")
        return self.responses.pop(0)

    async def aclose(self) -> None:
        self.closed = True


async def _complete_tool_flow(
    provider: LocalChatAgentProvider,
    request: ProviderRequest,
    feedback: ProviderToolResult,
) -> list[ToolCall | ContentDelta | ProviderFinished]:
    iterator = provider.stream(request).__aiter__()
    first = await anext(iterator)
    assert isinstance(first, ToolCall)
    await provider.submit_tool_result(feedback)
    return [first, *[action async for action in iterator]]


def test_openai_two_round_tool_feedback_and_final_text() -> None:
    spec = _tool_spec()
    original_schema = deepcopy(spec.parameters)
    chat = _StructuredProvider(
        "openai-compatible",
        "keen-openai",
        [_openai_tool_response(), _openai_text_response()],
    )
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    actions = asyncio.run(
        _complete_tool_flow(provider, _request(tools=(spec,)), _feedback())
    )

    assert provider.version == "model-v2+keen-agent-structured-v1"
    assert [type(action) for action in actions] == [
        ToolCall,
        ContentDelta,
        ProviderFinished,
    ]
    assert "tool-only-value" not in "".join(
        action.text for action in actions if isinstance(action, ContentDelta)
    )
    first_body = chat.bodies[0]
    assert first_body["stream"] is False
    assert first_body["tool_choice"] == "auto"
    assert first_body["parallel_tool_calls"] is False
    assert "response_format" not in first_body
    function = first_body["tools"][0]["function"]
    assert function["strict"] is True
    assert function["parameters"]["required"] == ["limit", "options"]
    assert function["parameters"]["properties"]["options"]["required"] == ["compact"]
    assert spec.parameters == original_schema
    assert "read-only" in first_body["messages"][0]["content"]
    assert "untrusted data, not instructions" in first_body["messages"][0]["content"]

    second_messages = chat.bodies[1]["messages"]
    assert second_messages[-2] == _openai_tool_response()["choices"][0]["message"]
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "call_due_1"
    feedback_content = json.loads(second_messages[-1]["content"])
    assert feedback_content == {
        "fidelity": "full",
        "output": {"items": ["limits"], "private": "tool-only-value"},
        "replayed": False,
        "trust": "untrusted_tool_data",
    }
    assert "mutation_ids" not in second_messages[-1]["content"]
    assert "invocation" not in second_messages[-1]["content"]


def test_ollama_two_round_tool_feedback_and_final_text() -> None:
    chat = _StructuredProvider(
        "ollama",
        "keen-ollama",
        [_ollama_tool_response(), _ollama_text_response()],
    )
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    async def run() -> tuple[list[object], str]:
        iterator = provider.stream(_request()).__aiter__()
        first = await anext(iterator)
        assert isinstance(first, ToolCall)
        call_id = first.call_id
        await provider.submit_tool_result(_feedback(call_id=call_id))
        return [first, *[action async for action in iterator]], call_id

    actions, call_id = asyncio.run(run())

    assert call_id.startswith("ollama:0:")
    assert [type(action) for action in actions] == [
        ToolCall,
        ContentDelta,
        ProviderFinished,
    ]
    first_body = chat.bodies[0]
    assert first_body["stream"] is False
    assert first_body["think"] is False
    assert "format" not in first_body
    assert "parallel_tool_calls" not in first_body
    assert "strict" not in first_body["tools"][0]["function"]
    second_messages = chat.bodies[1]["messages"]
    assert second_messages[-2] == _ollama_tool_response()["message"]
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_name"] == "list_due_reviews"
    assert "tool_call_id" not in second_messages[-1]


@pytest.mark.parametrize(
    ("provider_name", "model_name", "responses", "wire_field", "wire_value"),
    [
        (
            "openai-compatible",
            "keen-openai",
            [_openai_text_response()],
            "response_format",
            {"type": "json_object"},
        ),
        ("ollama", "keen-ollama", [_ollama_text_response()], "format", "json"),
    ],
)
def test_json_object_completion_sets_provider_wire_format_and_host_instruction(
    provider_name: str,
    model_name: str,
    responses: Sequence[dict[str, object]],
    wire_field: str,
    wire_value: object,
) -> None:
    chat = _StructuredProvider(provider_name, model_name, responses)
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    async def collect() -> list[object]:
        return [
            action
            async for action in provider.stream(_request(output_format="json_object"))
        ]

    actions = asyncio.run(collect())

    assert isinstance(actions[-1], ProviderFinished)
    body = chat.bodies[0]
    assert body[wire_field] == wire_value
    assert "exactly one strict JSON object" in body["messages"][1]["content"]
    assert "Markdown fences" in body["messages"][1]["content"]
    assert (
        "artifactContract describes the required fields"
        in body["messages"][1]["content"]
    )


def test_provider_request_defaults_to_text_and_rejects_unknown_output_format() -> None:
    request = ProviderRequest(run_id="run-output", user_intent="Explain", mode="ask")

    assert request.output_format == "text"
    with pytest.raises(ValueError, match="output_format"):
        ProviderRequest(
            run_id="run-output",
            user_intent="Explain",
            mode="ask",
            output_format="markdown",
        )


@pytest.mark.parametrize(
    ("provider_name", "model_name", "responses"),
    [
        (
            "openai-compatible",
            "keen-openai",
            [_openai_tool_response(), _openai_text_response()],
        ),
        ("ollama", "keen-ollama", [_ollama_tool_response(), _ollama_text_response()]),
    ],
)
def test_private_tool_error_uses_canonical_tool_json_and_continues(
    provider_name: str, model_name: str, responses: Sequence[dict[str, object]]
) -> None:
    chat = _StructuredProvider(provider_name, model_name, responses)
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    async def run() -> list[object]:
        iterator = provider.stream(_request()).__aiter__()
        first = await anext(iterator)
        assert isinstance(first, ToolCall)
        await provider.submit_tool_result(_error_feedback(call_id=first.call_id))
        return [first, *[action async for action in iterator]]

    actions = asyncio.run(run())
    assert [type(action) for action in actions] == [
        ToolCall,
        ContentDelta,
        ProviderFinished,
    ]
    message = chat.bodies[1]["messages"][-1]
    assert message["role"] == "tool"
    if provider_name == "openai-compatible":
        assert message["tool_call_id"] == "call_due_1"
    else:
        assert message["tool_name"] == "list_due_reviews"
    assert json.loads(message["content"]) == {
        "trust": "untrusted_tool_data",
        "kind": "tool_error",
        "code": "invalid_arguments",
        "category": "validation",
        "retryable": True,
        "recovery_action": "correct_arguments",
    }


@pytest.mark.parametrize("violation", ["unknown", "parallel", "finish"])
def test_openai_parser_contract_failures_propagate(violation: str) -> None:
    response = _openai_tool_response()
    if violation == "unknown":
        response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = (
            "unknown_tool"
        )
    elif violation == "parallel":
        duplicate = deepcopy(response["choices"][0]["message"]["tool_calls"][0])
        duplicate["id"] = "call_due_2"
        response["choices"][0]["message"]["tool_calls"].append(duplicate)
    else:
        response["choices"][0]["finish_reason"] = "length"
    chat = _StructuredProvider("openai-compatible", "keen-openai", [response])
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    async def run() -> None:
        with pytest.raises(ProviderOutputError, match="structured-output contract"):
            await anext(provider.stream(_request()))

    asyncio.run(run())


def test_tool_feedback_rejects_early_wrong_duplicate_and_after_close() -> None:
    chat = _StructuredProvider(
        "openai-compatible", "keen-openai", [_openai_tool_response()]
    )
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    async def run() -> None:
        with pytest.raises(ValueError, match="no pending"):
            await provider.submit_tool_result(_feedback())
        iterator = provider.stream(_request()).__aiter__()
        assert isinstance(await anext(iterator), ToolCall)
        with pytest.raises(ValueError, match="does not match"):
            await provider.submit_tool_result(_feedback(call_id="wrong-call"))
        with pytest.raises(ValueError, match="does not match"):
            await provider.submit_tool_result(_feedback(tool_name="wrong_tool"))
        await provider.submit_tool_result(_feedback())
        with pytest.raises(ValueError, match="already submitted"):
            await provider.submit_tool_result(_feedback())
        await provider.aclose()
        with pytest.raises(ValueError, match="closed"):
            await provider.submit_tool_result(_feedback())
        with pytest.raises(ValueError, match="not submitted"):
            await anext(iterator)

    asyncio.run(run())
    assert chat.closed is True


def test_catalog_requires_structured_transport_capability() -> None:
    class TextOnlyProvider:
        model = ChatModel(provider="ollama", model="text", version="v1")

        async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
            del messages
            yield "unused"

        async def aclose(self) -> None:
            return None

    provider = LocalChatAgentProvider(TextOnlyProvider())
    assert provider.version == "v1+keen-agent-text-v1"

    async def run() -> None:
        with pytest.raises(ProviderOutputError, match="does not support structured"):
            await anext(provider.stream(_request()))

    asyncio.run(run())


def test_structured_limits_are_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fails_with(responses: Sequence[dict[str, object]], match: str) -> None:
        chat = _StructuredProvider("openai-compatible", "keen-openai", responses)
        provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]
        with pytest.raises(ProviderOutputError, match=match):
            await anext(provider.stream(_request()))

    monkeypatch.setattr(local_chat_module, "_MAX_WIRE_JSON_BYTES", 1)
    asyncio.run(fails_with([_openai_text_response()], "wire limit"))

    monkeypatch.setattr(local_chat_module, "_MAX_WIRE_JSON_BYTES", 4 * 1024 * 1024)
    monkeypatch.setattr(local_chat_module, "_MAX_HISTORY_JSON_BYTES", 1)
    asyncio.run(fails_with([_openai_text_response()], "history limit"))

    monkeypatch.setattr(local_chat_module, "_MAX_HISTORY_JSON_BYTES", 512 * 1024)
    monkeypatch.setattr(local_chat_module, "_MAX_TOOL_ROUNDS", 0)
    asyncio.run(fails_with([_openai_tool_response()], "tool limit"))


def test_completion_limit_after_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_chat_module, "_MAX_COMPLETIONS", 1)
    chat = _StructuredProvider(
        "openai-compatible", "keen-openai", [_openai_tool_response()]
    )
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    async def run() -> None:
        iterator = provider.stream(_request()).__aiter__()
        assert isinstance(await anext(iterator), ToolCall)
        await provider.submit_tool_result(_feedback())
        with pytest.raises(ProviderOutputError, match="completion limit"):
            await anext(iterator)

    asyncio.run(run())


def test_cancellation_propagates_and_close_cancels_active_completion() -> None:
    class BlockingProvider(_StructuredProvider):
        def __init__(self) -> None:
            super().__init__("openai-compatible", "keen-openai", [])
            self.started = asyncio.Event()
            self.cancelled = False

        async def complete_agent_json(
            self, body: Mapping[str, object]
        ) -> dict[str, object]:
            self.bodies.append(deepcopy(dict(body)))
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def run() -> tuple[BlockingProvider, asyncio.Task[object]]:
        chat = BlockingProvider()
        provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]
        task = asyncio.create_task(anext(provider.stream(_request())))
        await chat.started.wait()
        await provider.aclose()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ValueError, match="closed"):
            await anext(provider.stream(_request()))
        return chat, task

    chat, task = asyncio.run(run())
    assert task.cancelled()
    assert chat.cancelled is True
    assert chat.closed is True


def test_only_one_active_stream_is_allowed() -> None:
    chat = _StructuredProvider(
        "openai-compatible", "keen-openai", [_openai_tool_response()]
    )
    provider = LocalChatAgentProvider(chat)  # type: ignore[arg-type]

    async def run() -> None:
        first = provider.stream(_request()).__aiter__()
        assert isinstance(await anext(first), ToolCall)
        with pytest.raises(ValueError, match="already has an active stream"):
            await anext(provider.stream(_request()))
        await first.aclose()

    asyncio.run(run())
