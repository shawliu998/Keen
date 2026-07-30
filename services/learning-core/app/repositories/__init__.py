"""Persistence primitives for the durable learning-loop domains.

Write methods in this package accept ``commit=False`` when a caller needs to
compose mutations across repositories. In that mode the caller must already
own a transaction and is responsible for committing or rolling it back.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import TypeAlias

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_MAX_JSON_DEPTH = 12
_MAX_JSON_ITEMS = 2_000
_MAX_JSON_STRING = 100_000


def validate_json(
    value: object, *, _depth: int = 0, _budget: list[int] | None = None
) -> JsonValue:
    """Return a JSON-safe copy while rejecting unbounded or ambiguous values."""

    if _budget is None:
        _budget = [_MAX_JSON_ITEMS]
    if _depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON value exceeds maximum nesting depth")
    _budget[0] -= 1
    if _budget[0] < 0:
        raise ValueError("JSON value exceeds maximum item count")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, str):
        if len(value) > _MAX_JSON_STRING:
            raise ValueError("JSON string exceeds maximum length")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ValueError("JSON object keys must be non-empty strings")
            result[key] = validate_json(child, _depth=_depth + 1, _budget=_budget)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            validate_json(child, _depth=_depth + 1, _budget=_budget) for child in value
        ]
    raise ValueError(f"unsupported JSON value type: {type(value).__name__}")


def dump_json(value: object) -> str:
    return json.dumps(
        validate_json(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def load_json(value: str) -> JsonValue:
    try:
        decoded: object = json.loads(value)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("stored JSON is malformed") from error
    return validate_json(decoded)


@contextmanager
def write_scope(connection: sqlite3.Connection, *, commit: bool) -> Iterator[None]:
    """Own a transaction, or participate explicitly in the caller's transaction."""

    owns_transaction = commit and not connection.in_transaction
    if owns_transaction:
        connection.execute("BEGIN IMMEDIATE")
    elif not connection.in_transaction:
        raise RuntimeError("commit=False requires a caller-owned transaction")
    try:
        yield
    except Exception:
        if owns_transaction and connection.in_transaction:
            connection.rollback()
        raise
    else:
        if owns_transaction:
            connection.commit()


__all__ = [
    "JsonValue",
    "dump_json",
    "load_json",
    "validate_json",
    "write_scope",
]
