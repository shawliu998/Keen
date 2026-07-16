from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from typing import Annotated, Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from .types import is_hidden_reasoning_key, validate_bounded_json_object

_PROVIDER_CLOSE_TIMEOUT_SECONDS = 1.0


def _consume_close_result(task: asyncio.Task[None]) -> None:
    with contextlib.suppress(BaseException):
        task.exception()


async def close_provider_safely(
    provider: AgentProvider, *, timeout: float = _PROVIDER_CLOSE_TIMEOUT_SECONDS
) -> bool:
    """Best-effort bounded cleanup that never exposes provider close details."""

    if timeout <= 0:
        raise ValueError("provider close timeout must be positive")
    close_task = asyncio.create_task(provider.aclose())
    try:
        done, _ = await asyncio.wait({close_task}, timeout=timeout)
    except asyncio.CancelledError:
        close_task.cancel()
        close_task.add_done_callback(_consume_close_result)
        raise
    if close_task not in done:
        close_task.cancel()
        close_task.add_done_callback(_consume_close_result)
        return False
    try:
        close_task.result()
    except BaseException:
        return False
    return True


def _reject_hidden_reasoning(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if is_hidden_reasoning_key(key):
                raise ValueError("provider data must not contain hidden reasoning")
            _reject_hidden_reasoning(child)
    elif isinstance(value, list):
        for child in value:
            _reject_hidden_reasoning(child)


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    user_intent: str = Field(min_length=1, max_length=5_000)
    mode: Literal["ask", "teach", "study", "review", "plan"]
    input: dict[str, object] = Field(default_factory=dict)

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        _reject_hidden_reasoning(value)
        return value


class ContentDelta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["content_delta"] = "content_delta"
    text: str = Field(min_length=1, max_length=16_384)


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["tool_call"] = "tool_call"
    call_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    tool_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]{0,79}$",
    )
    arguments: dict[str, object] = Field(default_factory=dict)

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        _reject_hidden_reasoning(value)
        return value


class ProviderCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["checkpoint"] = "checkpoint"
    label: str = Field(min_length=1, max_length=200)
    data: dict[str, object] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        _reject_hidden_reasoning(value)
        return value


class ProviderWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["warning"] = "warning"
    code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]{0,79}$",
    )
    message: str = Field(min_length=1, max_length=1_000)


class ProviderFinished(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["finished"] = "finished"


ProviderAction: TypeAlias = Annotated[
    ContentDelta | ToolCall | ProviderCheckpoint | ProviderWarning | ProviderFinished,
    Field(discriminator="kind"),
]
_PROVIDER_ACTION_ADAPTER = TypeAdapter(ProviderAction)


class AgentProvider(Protocol):
    """Provider-neutral single-Agent action stream.

    A clean stream must emit ``ProviderFinished``. Iterator exhaustion without
    that marker is a disconnect, not successful completion.
    """

    name: str
    model: str
    version: str

    def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]: ...

    async def aclose(self) -> None: ...


class FixedAutomationProvider:
    """Deterministic provider fixture for automation and E2E tests only."""

    name = "automation"
    model = "fixed-actions"
    version = "v1"

    def __init__(self, actions: Sequence[ProviderAction | dict[str, object]]) -> None:
        if len(actions) > 1_000:
            raise ValueError("automation action sequence is too large")
        self._actions = tuple(
            _PROVIDER_ACTION_ADAPTER.validate_python(action) for action in actions
        )
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]:
        del request
        for action in self._actions:
            await asyncio.sleep(0)
            yield action

    async def aclose(self) -> None:
        self.closed = True


class ProviderDisconnectedError(ConnectionError):
    pass


class ProviderOutputError(RuntimeError):
    """A provider completed transport but produced unsafe or unusable output."""


__all__ = [
    "AgentProvider",
    "close_provider_safely",
    "ContentDelta",
    "FixedAutomationProvider",
    "ProviderAction",
    "ProviderCheckpoint",
    "ProviderDisconnectedError",
    "ProviderFinished",
    "ProviderOutputError",
    "ProviderRequest",
    "ProviderWarning",
    "ToolCall",
]
