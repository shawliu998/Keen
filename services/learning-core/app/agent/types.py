from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass, replace
from enum import Enum, IntEnum
from typing import Generic, Literal, Protocol, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PermissionLevel(IntEnum):
    """Keen's fail-closed tool permission levels."""

    AUTOMATIC = 1
    LOCAL_REVERSIBLE = 2
    CONFIRM_FIRST = 3


class ToolEffect(str, Enum):
    READ = "read"
    GENERATE = "generate"
    LOCAL_WRITE = "local_write"
    EXTERNAL_OR_DESTRUCTIVE = "external_or_destructive"


class ToolArguments(BaseModel):
    """Base class for every tool's closed, typed input schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)


_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 2_048
_MAX_JSON_STRING_CHARS = 131_072
_MAX_SINGLE_STRING_CHARS = 65_536
SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
_SAFE_IDENTIFIER_RE = re.compile(SAFE_IDENTIFIER_PATTERN)
_CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALPHANUMERIC_RE = re.compile(r"[^A-Za-z0-9]+")


def is_safe_identifier(value: object) -> bool:
    """Return whether a value is safe to retain as an audit correlation ID."""

    return isinstance(value, str) and _SAFE_IDENTIFIER_RE.fullmatch(value) is not None


def canonicalize_key(value: str) -> str:
    """Normalize mapping keys before applying privacy policy."""

    with_boundaries = _CAMEL_CASE_BOUNDARY_RE.sub("_", value)
    return _NON_ALPHANUMERIC_RE.sub("_", with_boundaries).strip("_").lower()


@dataclass(slots=True)
class _JsonBudget:
    nodes: int = 0
    string_chars: int = 0


def _validate_json_value(
    value: object, *, depth: int = 0, budget: _JsonBudget | None = None
) -> None:
    budget = budget or _JsonBudget()
    budget.nodes += 1
    if budget.nodes > _MAX_JSON_NODES:
        raise ValueError("JSON value exceeds the maximum item count")
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON value exceeds the maximum nesting depth")
    if isinstance(value, str):
        if len(value) > _MAX_SINGLE_STRING_CHARS:
            raise ValueError("JSON string exceeds the maximum length")
        budget.string_chars += len(value)
        if budget.string_chars > _MAX_JSON_STRING_CHARS:
            raise ValueError("JSON value exceeds the total text limit")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth=depth + 1, budget=budget)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            budget.string_chars += len(key)
            if budget.string_chars > _MAX_JSON_STRING_CHARS:
                raise ValueError("JSON value exceeds the total text limit")
            _validate_json_value(item, depth=depth + 1, budget=budget)
        return
    raise ValueError(f"unsupported JSON value: {type(value).__name__}")


def validate_bounded_json_object(value: dict[str, object]) -> None:
    _validate_json_value(value)


class UndoInstruction(BaseModel):
    """A bounded, executable inverse for a local state mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["create", "update", "delete"]
    entity_type: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    entity_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=SAFE_IDENTIFIER_PATTERN,
    )
    restore: dict[str, object] | None = None


class StateMutation(BaseModel):
    """A reversible Level 2 state change.

    ``before`` and ``after`` are deliberately required even when one side is
    ``None`` (for create/delete). This keeps undo records explicit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    entity_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=SAFE_IDENTIFIER_PATTERN,
    )
    operation: Literal["create", "update", "delete"]
    before: dict[str, object] | None
    after: dict[str, object] | None
    undo: UndoInstruction

    @model_validator(mode="after")
    def validate_mutation_payload(self) -> Self:
        budget = _JsonBudget()
        for value in (self.before, self.after, self.undo.model_dump(mode="python")):
            if value is not None:
                _validate_json_value(value, budget=budget)
                _reject_hidden_reasoning(value)
        expected_shape = {
            "create": self.before is None and self.after is not None,
            "update": self.before is not None and self.after is not None,
            "delete": self.before is not None and self.after is None,
        }
        if not expected_shape[self.operation]:
            raise ValueError(
                f"{self.operation} mutation has inconsistent before/after state"
            )
        expected_inverse = {
            "create": "delete",
            "update": "update",
            "delete": "create",
        }[self.operation]
        if self.undo.operation != expected_inverse:
            raise ValueError("undo operation is not the inverse of the mutation")
        if (
            self.undo.entity_type != self.entity_type
            or self.undo.entity_id != self.entity_id
        ):
            raise ValueError("undo target must match the mutation target")
        expected_restore = None if self.operation == "create" else self.before
        if self.undo.restore != expected_restore:
            raise ValueError("undo restore state does not match the mutation")
        return self


_HIDDEN_REASONING_KEYS = {
    "chain_of_thought",
    "hidden_reasoning",
    "internal_reasoning",
    "reasoning",
    "reasoning_trace",
    "scratchpad",
    "thoughts",
}
_HIDDEN_REASONING_COMPACT_KEYS = {
    key.replace("_", "") for key in _HIDDEN_REASONING_KEYS
}


def is_hidden_reasoning_key(key: str) -> bool:
    normalized = canonicalize_key(key)
    return (
        normalized in _HIDDEN_REASONING_KEYS
        or normalized.replace("_", "") in _HIDDEN_REASONING_COMPACT_KEYS
    )


def _reject_hidden_reasoning(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if is_hidden_reasoning_key(key):
                raise ValueError("tool results must not expose hidden model reasoning")
            _reject_hidden_reasoning(item)
    elif isinstance(value, list):
        for item in value:
            _reject_hidden_reasoning(item)


class ToolResult(BaseModel):
    """Provider-neutral output from a single registered tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output: dict[str, object] = Field(default_factory=dict)
    mutations: tuple[StateMutation, ...] = Field(default=(), max_length=100)

    @field_validator("output")
    @classmethod
    def validate_output(cls, value: dict[str, object]) -> dict[str, object]:
        _validate_json_value(value)
        _reject_hidden_reasoning(value)
        return value


class UntrustedDocument(BaseModel):
    """Document material is data only; it never carries tool instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=SAFE_IDENTIFIER_PATTERN,
    )
    content: str = Field(max_length=262_144)
    trust: Literal["untrusted_data"] = "untrusted_data"


@dataclass(frozen=True, slots=True)
class ToolContext:
    run_id: str
    step_id: str
    cancellation_event: asyncio.Event
    untrusted_documents: tuple[UntrustedDocument, ...] = ()
    transaction: object | None = None

    def __post_init__(self) -> None:
        for label, value in (("run_id", self.run_id), ("step_id", self.step_id)):
            if not is_safe_identifier(value):
                raise ValueError(f"{label} is not a safe identifier")
        if not isinstance(self.cancellation_event, asyncio.Event):
            raise TypeError("cancellation_event must be an asyncio.Event")
        if (
            not isinstance(self.untrusted_documents, tuple)
            or len(self.untrusted_documents) > 64
            or any(
                not isinstance(document, UntrustedDocument)
                for document in self.untrusted_documents
            )
        ):
            raise ValueError(
                "untrusted_documents must contain at most 64 typed data records"
            )

    def raise_if_cancelled(self) -> None:
        if self.cancellation_event.is_set():
            raise asyncio.CancelledError

    def with_transaction(self, transaction: object) -> ToolContext:
        return replace(self, transaction=transaction)


ArgumentsT = TypeVar("ArgumentsT", bound=ToolArguments)


class AgentTool(Protocol, Generic[ArgumentsT]):
    name: str
    permission_level: PermissionLevel
    effect: ToolEffect
    arguments_model: type[ArgumentsT]

    async def execute(
        self, arguments: ArgumentsT, context: ToolContext
    ) -> ToolResult: ...
