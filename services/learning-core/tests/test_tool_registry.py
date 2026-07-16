from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent import (
    PermissionLevel,
    ToolArguments,
    ToolContext,
    ToolEffect,
    ToolRegistrationError,
    ToolRegistry,
    ToolResult,
)
from app.agent.types import ToolOutput


class SearchArguments(ToolArguments):
    query: str
    limit: int = 10


class SearchOutput(ToolOutput):
    count: int


class SearchTool:
    name = "search_notes"
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = SearchArguments
    result_model = SearchOutput

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


def test_registry_requires_a_closed_declared_result_model():
    class MissingResultTool:
        name = "missing_result"
        permission_level = PermissionLevel.AUTOMATIC
        effect = ToolEffect.READ
        arguments_model = SearchArguments

    with pytest.raises(ToolRegistrationError, match="result_model"):
        ToolRegistry().register(MissingResultTool())  # type: ignore[arg-type]

    class OpenResult(ToolOutput):
        model_config = ConfigDict(extra="allow")

        count: int

    class OpenResultTool(SearchTool):
        name = "open_result"
        result_model = OpenResult

    with pytest.raises(ToolRegistrationError, match="extra='forbid'"):
        ToolRegistry().register(OpenResultTool())


def test_registry_recursively_rejects_unbounded_or_hidden_result_fields():
    class LooseNestedResult(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=False)

        count: int

    class LooseContainerResult(ToolOutput):
        item: LooseNestedResult

    class LooseResultTool(SearchTool):
        name = "loose_result"
        result_model = LooseContainerResult

    with pytest.raises(ToolRegistrationError, match="strict=True"):
        ToolRegistry().register(LooseResultTool())

    class MappingResult(ToolOutput):
        payload: dict[str, str]

    class MappingResultTool(SearchTool):
        name = "mapping_result"
        result_model = MappingResult

    with pytest.raises(ToolRegistrationError, match="arbitrary mappings"):
        ToolRegistry().register(MappingResultTool())

    class AnyResult(ToolOutput):
        payload: Any

    class AnyResultTool(SearchTool):
        name = "any_result"
        result_model = AnyResult

    with pytest.raises(ToolRegistrationError, match="Any/object"):
        ToolRegistry().register(AnyResultTool())

    class HiddenNestedResult(ToolOutput):
        reasoning_trace: str

    class NestedResult(ToolOutput):
        item: HiddenNestedResult

    class HiddenResultTool(SearchTool):
        name = "hidden_result"
        result_model = NestedResult

    with pytest.raises(ToolRegistrationError, match="hidden model reasoning"):
        ToolRegistry().register(HiddenResultTool())

    class AliasedHiddenResult(ToolOutput):
        trace: str = Field(alias="chainOfThought")

    class AliasedHiddenResultTool(SearchTool):
        name = "aliased_hidden_result"
        result_model = AliasedHiddenResult

    with pytest.raises(ToolRegistrationError, match="hidden model reasoning"):
        ToolRegistry().register(AliasedHiddenResultTool())


@pytest.mark.parametrize("value", [True, "1", 1.2])
def test_tool_outputs_reject_numeric_coercion(value: object):
    with pytest.raises(ValidationError):
        SearchOutput.model_validate({"count": value})


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
