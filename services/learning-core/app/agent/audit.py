from __future__ import annotations

import hashlib
import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .types import (
    PermissionLevel,
    StateMutation,
    canonicalize_key,
    is_hidden_reasoning_key,
    is_safe_identifier,
)

MAX_AUDIT_BYTES = 4_096
_MAX_COLLECTION_ITEMS = 24
_MAX_DEPTH = 8
_SENSITIVE_KEYS = {
    "analysis",
    "answer",
    "api_key",
    "body",
    "chain_of_thought",
    "chunks",
    "content",
    "document",
    "document_text",
    "full_text",
    "hidden_reasoning",
    "internal_reasoning",
    "password",
    "path",
    "private_data",
    "prompt",
    "reasoning",
    "reasoning_trace",
    "scratchpad",
    "secret",
    "source_content",
    "text",
    "token",
    "thoughts",
}
_SENSITIVE_SUFFIXES = (
    "_answer",
    "_body",
    "_content",
    "_password",
    "_path",
    "_prompt",
    "_secret",
    "_text",
    "_token",
)
_SAFE_TEXT_KEYS = {
    "effect",
    "entity_type",
    "format",
    "kind",
    "mode",
    "operation",
    "status",
    "tool_name",
    "type",
}


class AuditSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: dict[str, object]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truncated: bool


class ToolAuditStart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    run_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    step_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    tool_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]{0,79}$",
    )
    permission_level: PermissionLevel
    arguments: AuditSummary


class ToolAuditSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    result: AuditSummary
    mutations: tuple[AuditSummary, ...]


class ToolAuditTerminal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    error_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$",
    )


class AuditSink(Protocol):
    """Persistence boundary implemented by a repository adapter.

    For Level 2, ``record_succeeded`` receives the exact transaction object
    and typed mutations provided to the tool. Implementations persist the raw
    mutation only in the controlled undo store, use the redacted record for
    logs/events, and join the transaction rather than commit independently.
    """

    async def record_started(self, record: ToolAuditStart) -> None: ...

    async def record_succeeded(
        self,
        record: ToolAuditSuccess,
        *,
        mutations: tuple[StateMutation, ...],
        transaction: object | None,
    ) -> None: ...

    async def record_failed(self, record: ToolAuditTerminal) -> None: ...

    async def record_cancelled(self, record: ToolAuditTerminal) -> None: ...

    async def record_rejected(self, record: ToolAuditTerminal) -> None: ...


def _canonical_json(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _is_sensitive_key(key: str) -> bool:
    lowered = canonicalize_key(key)
    is_identifier = lowered.endswith("_id") or lowered.endswith("_ids")
    return not is_identifier and (
        is_hidden_reasoning_key(key)
        or lowered in _SENSITIVE_KEYS
        or lowered.endswith(_SENSITIVE_SUFFIXES)
    )


def _summarize(value: object, *, key: str = "", depth: int = 0) -> tuple[object, bool]:
    if _is_sensitive_key(key):
        return "[REDACTED]", True
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED:DEPTH]", True
    if value is None or isinstance(value, (bool, int, float)):
        return value, False
    if isinstance(value, str):
        lowered = canonicalize_key(key)
        if lowered.endswith(("_id", "_ids")):
            if not is_safe_identifier(value):
                return "[REDACTED:INVALID_ID]", True
            return value, False
        if lowered in _SAFE_TEXT_KEYS:
            if len(value) <= 256:
                return value, False
            return f"{value[:128]}...[TRUNCATED]", True
        return "[REDACTED:TEXT]", True
    if isinstance(value, list):
        items = value[:_MAX_COLLECTION_ITEMS]
        summarized: list[object] = []
        truncated = len(items) != len(value)
        normalized_key = canonicalize_key(key)
        item_key = normalized_key[:-1] if normalized_key.endswith("_ids") else ""
        for item in items:
            child, child_truncated = _summarize(
                item,
                key=item_key,
                depth=depth + 1,
            )
            summarized.append(child)
            truncated = truncated or child_truncated
        return summarized, truncated
    if isinstance(value, dict):
        summarized_object: dict[str, object] = {}
        items = sorted(value.items())[:_MAX_COLLECTION_ITEMS]
        truncated = len(items) != len(value)
        for child_key, child_value in items:
            child, child_truncated = _summarize(
                child_value, key=child_key, depth=depth + 1
            )
            summarized_object[child_key] = child
            truncated = truncated or child_truncated
        return summarized_object, truncated
    return f"[REDACTED:{type(value).__name__.upper()}]", True


def summarize_for_audit(value: dict[str, object]) -> AuditSummary:
    canonical = _canonical_json(value)
    summarized, truncated = _summarize(value)
    if not isinstance(summarized, dict):  # pragma: no cover - object input above
        raise TypeError("audit input must be an object")
    encoded = _canonical_json(summarized)
    if len(encoded) > MAX_AUDIT_BYTES:
        summarized = {
            "field_count": len(value),
            "summary": "[REDACTED:OVERSIZE]",
        }
        truncated = True
    return AuditSummary(
        summary=summarized,
        sha256=hashlib.sha256(canonical).hexdigest(),
        truncated=truncated,
    )


def summarize_mutation(mutation: StateMutation) -> AuditSummary:
    return summarize_for_audit(mutation.model_dump(mode="json"))
