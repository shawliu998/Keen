from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import PurePath
from types import MappingProxyType, UnionType
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

from .types import (
    AgentTool,
    PermissionLevel,
    ToolArguments,
    ToolEffect,
    ToolOutput,
    is_hidden_reasoning_key,
    validate_bounded_json_object,
)


class ToolRegistrationError(ValueError):
    pass


class ToolNotFoundError(LookupError):
    pass


_FORBIDDEN_ARGUMENT_NAMES = {
    "file_path",
    "filesystem_path",
    "path",
    "raw_sql",
    "sql",
    "sql_statement",
    "statement",
}
_FORBIDDEN_TOOL_NAMES = {
    "delete_file",
    "execute_sql",
    "list_files",
    "open_path",
    "read_file",
    "run_sql",
    "write_file",
}


def _is_forbidden_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in _FORBIDDEN_ARGUMENT_NAMES or lowered.endswith(("_path", "_sql"))


def _validate_annotation(
    annotation: object,
    *,
    seen: set[type[BaseModel]],
    reject_unsafe_inputs: bool,
    reject_hidden_outputs: bool,
) -> None:
    if annotation in {Any, object}:
        raise ToolRegistrationError("tool schemas cannot contain Any/object")
    if (
        reject_unsafe_inputs
        and isinstance(annotation, type)
        and issubclass(annotation, PurePath)
    ):
        raise ToolRegistrationError("tool arguments cannot accept filesystem paths")
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        _validate_model(
            annotation,
            seen=seen,
            reject_unsafe_inputs=reject_unsafe_inputs,
            reject_hidden_outputs=reject_hidden_outputs,
        )
        return
    origin = get_origin(annotation)
    if origin in {dict, Mapping}:
        raise ToolRegistrationError(
            "tool schemas cannot contain arbitrary mappings; use a typed model"
        )
    if origin is None:
        return
    if origin is UnionType:
        arguments = get_args(annotation)
    else:
        arguments = get_args(annotation)
    for argument in arguments:
        if argument is not type(None):
            _validate_annotation(
                argument,
                seen=seen,
                reject_unsafe_inputs=reject_unsafe_inputs,
                reject_hidden_outputs=reject_hidden_outputs,
            )


def _validate_model(
    model: type[BaseModel],
    *,
    seen: set[type[BaseModel]] | None = None,
    reject_unsafe_inputs: bool = True,
    reject_hidden_outputs: bool = False,
) -> None:
    if model.model_config.get("extra") != "forbid":
        raise ToolRegistrationError("tool models must set extra='forbid'")
    if reject_hidden_outputs and model.model_config.get("strict") is not True:
        raise ToolRegistrationError("tool result models must set strict=True")
    seen = seen or set()
    if model in seen:
        return
    seen.add(model)
    for field_name, field in model.model_fields.items():
        names = (field_name,) if field.alias is None else (field_name, field.alias)
        if reject_hidden_outputs and any(
            is_hidden_reasoning_key(name) for name in names
        ):
            raise ToolRegistrationError(
                f"tool result '{field_name}' could expose hidden model reasoning"
            )
        if reject_unsafe_inputs and any(_is_forbidden_name(name) for name in names):
            raise ToolRegistrationError(
                f"tool argument '{field_name}' could accept arbitrary SQL or a file path"
            )
        _validate_annotation(
            field.annotation,
            seen=seen,
            reject_unsafe_inputs=reject_unsafe_inputs,
            reject_hidden_outputs=reject_hidden_outputs,
        )


def _validate_permission_effect(tool: AgentTool[ToolArguments]) -> None:
    allowed_effects = {
        PermissionLevel.AUTOMATIC: {ToolEffect.READ, ToolEffect.GENERATE},
        PermissionLevel.LOCAL_REVERSIBLE: {ToolEffect.LOCAL_WRITE},
        PermissionLevel.CONFIRM_FIRST: {ToolEffect.EXTERNAL_OR_DESTRUCTIVE},
    }
    if tool.effect not in allowed_effects.get(tool.permission_level, set()):
        raise ToolRegistrationError("tool effect does not match its permission level")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool[ToolArguments]] = {}

    @property
    def tools(self) -> Mapping[str, AgentTool[ToolArguments]]:
        return MappingProxyType(self._tools)

    def __iter__(self) -> Iterator[str]:
        return iter(self._tools)

    def register(self, tool: AgentTool[ToolArguments]) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", tool.name) is None:
            raise ToolRegistrationError("tool name must match ^[a-z][a-z0-9_]{0,79}$")
        if tool.name.lower() in _FORBIDDEN_TOOL_NAMES:
            raise ToolRegistrationError(
                "tools cannot expose arbitrary SQL or filesystem operations"
            )
        if tool.name in self._tools:
            raise ToolRegistrationError(f"duplicate tool name: {tool.name}")
        if not isinstance(tool.permission_level, PermissionLevel) or not isinstance(
            tool.effect, ToolEffect
        ):
            raise ToolRegistrationError(
                "tool permission_level and effect must use the declared enums"
            )
        if not isinstance(tool.arguments_model, type) or not issubclass(
            tool.arguments_model, ToolArguments
        ):
            raise ToolRegistrationError(
                "tool arguments_model must extend ToolArguments"
            )
        _validate_model(tool.arguments_model)
        result_model = getattr(tool, "result_model", None)
        if not isinstance(result_model, type) or not issubclass(
            result_model, ToolOutput
        ):
            raise ToolRegistrationError("tool result_model must extend ToolOutput")
        _validate_model(
            result_model,
            reject_unsafe_inputs=False,
            reject_hidden_outputs=True,
        )
        _validate_permission_effect(tool)
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool[ToolArguments]:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ToolNotFoundError(f"unregistered tool: {name}") from error

    def validate_arguments(
        self, name: str, arguments: Mapping[str, object]
    ) -> ToolArguments:
        tool = self.get(name)
        try:
            validated = tool.arguments_model.model_validate(dict(arguments))
            validate_bounded_json_object(validated.model_dump(mode="json"))
            return validated
        except ValidationError:
            raise
