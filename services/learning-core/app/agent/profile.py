"""Trusted host-selected limits for a purpose-specific Agent run."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .registry import ToolRegistry


ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection]]


@dataclass(frozen=True, slots=True)
class AgentExecutionLimits:
    """Limits that may only narrow the existing global runtime ceilings."""

    maximum_provider_actions: int
    maximum_tool_calls: int
    maximum_content_bytes: int

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_provider_actions <= 32:
            raise ValueError("profile provider actions must be between 1 and 32")
        if not 0 <= self.maximum_tool_calls <= 8:
            raise ValueError("profile tool calls must be between 0 and 8")
        if not 1 <= self.maximum_content_bytes <= 131_072:
            raise ValueError("profile content bytes must be between 1 and 131072")


class AgentRunProfile(Protocol):
    """A trusted object selected by a domain service, never by provider input."""

    id: str
    definition_hash: str
    limits: AgentExecutionLimits
    output_format: Literal["text", "json_object"]

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        connection_factory: ConnectionFactory,
        course_id: str,
        as_of: datetime,
    ) -> None: ...

    async def publish_completion(
        self,
        *,
        run_id: str,
        content: str,
    ) -> dict[str, object]: ...


__all__ = ["AgentExecutionLimits", "AgentRunProfile", "ConnectionFactory"]
