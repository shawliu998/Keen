from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agent import (
    PermissionLevel,
    ToolArguments,
    ToolContext,
    ToolEffect,
    ToolRegistrationError,
    ToolRegistry,
    ToolResult,
)


class SearchArguments(ToolArguments):
    query: str
    limit: int = 10


class SearchTool:
    name = "search_notes"
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = SearchArguments

    async def execute(
        self, arguments: SearchArguments, context: ToolContext
    ) -> ToolResult:
        return ToolResult(output={"count": 0})


def test_registry_rejects_duplicate_names_and_unknown_arguments():
    registry = ToolRegistry()
    registry.register(SearchTool())
    with pytest.raises(ToolRegistrationError, match="duplicate tool name"):
        registry.register(SearchTool())
    with pytest.raises(ValidationError, match="extra_forbidden"):
        registry.validate_arguments(
            "search_notes", {"query": "limits", "unexpected": True}
        )


def test_registry_requires_closed_pydantic_schemas():
    class OpenArguments(BaseModel):
        model_config = ConfigDict(extra="allow")

        query: str

    class OpenTool(SearchTool):
        name = "open_search"
        arguments_model = OpenArguments

    with pytest.raises(ToolRegistrationError, match="extend ToolArguments"):
        ToolRegistry().register(OpenTool())  # type: ignore[arg-type]


def test_registry_rejects_arbitrary_sql_paths_and_untyped_payloads():
    class PathArguments(ToolArguments):
        source_path: str

    class PathTool(SearchTool):
        name = "unsafe_path"
        arguments_model = PathArguments

    with pytest.raises(ToolRegistrationError, match="SQL or a file path"):
        ToolRegistry().register(PathTool())  # type: ignore[arg-type]

    class PayloadArguments(ToolArguments):
        payload: dict[str, Any]

    class PayloadTool(SearchTool):
        name = "unsafe_payload"
        arguments_model = PayloadArguments

    with pytest.raises(ToolRegistrationError, match="arbitrary mappings"):
        ToolRegistry().register(PayloadTool())  # type: ignore[arg-type]

    class SqlTool(SearchTool):
        name = "execute_sql"

    with pytest.raises(ToolRegistrationError, match="arbitrary SQL"):
        ToolRegistry().register(SqlTool())


def test_registry_rejects_permission_effect_mismatches():
    class MutatingReadTool(SearchTool):
        name = "bad_read"
        effect = ToolEffect.LOCAL_WRITE

    with pytest.raises(ToolRegistrationError, match="permission level"):
        ToolRegistry().register(MutatingReadTool())


@pytest.mark.parametrize("name", ["1search", "Search", "search-notes", "a" * 81])
def test_registry_rejects_unsafe_or_oversized_tool_names(name: str):
    class InvalidNameTool(SearchTool):
        pass

    InvalidNameTool.name = name
    with pytest.raises(ToolRegistrationError, match="tool name must match"):
        ToolRegistry().register(InvalidNameTool())
