from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .registry import ToolRegistry
from .types import (
    PermissionLevel,
    ToolEffect,
    is_hidden_reasoning_key,
    validate_bounded_json_object,
)

_TOOL_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,79}$"
MAX_TOOL_DESCRIPTION_CHARS = 512


class _FrozenDict(dict[str, object]):
    """JSON-object-compatible mapping that rejects mutation at every depth."""

    @staticmethod
    def _immutable(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("tool catalog parameters are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __deepcopy__(self, memo: dict[int, object]) -> _FrozenDict:
        del memo
        return self


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return _FrozenDict((key, _freeze_json(child)) for key, child in value.items())
    if isinstance(value, list):
        return tuple(_freeze_json(child) for child in value)
    return value


def _copy_json_for_wire(value: object) -> object:
    if isinstance(value, dict):
        return {key: _copy_json_for_wire(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_json_for_wire(child) for child in value]
    return value


def _reject_hidden_reasoning(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if is_hidden_reasoning_key(key):
                raise ValueError(
                    "tool catalog parameters must not expose hidden reasoning"
                )
            _reject_hidden_reasoning(child)
    elif isinstance(value, list):
        for child in value:
            _reject_hidden_reasoning(child)


class ProviderToolSpec(BaseModel):
    """One provider-facing tool definition with a closed argument schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=80, pattern=_TOOL_NAME_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_TOOL_DESCRIPTION_CHARS)
    parameters: dict[str, object]

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool description must not be blank")
        return value

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        _reject_hidden_reasoning(value)
        frozen = _freeze_json(value)
        if not isinstance(frozen, dict):  # pragma: no cover - field type invariant
            raise TypeError("tool catalog parameters must be a JSON object")
        return frozen

    def parameters_for_wire(self) -> dict[str, object]:
        """Return a detached mutable JSON object for provider serialization."""

        copied = _copy_json_for_wire(self.parameters)
        if not isinstance(copied, dict):  # pragma: no cover - field type invariant
            raise TypeError("tool catalog parameters must be a JSON object")
        return copied


class ProviderToolPolicy(BaseModel):
    """The read-only tool catalog a provider may see for one run.

    The catalog is derived from a host-trusted registry. The allowed tool
    names are always derived from the catalog, so the two cannot drift apart.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog: tuple[ProviderToolSpec, ...] = Field(min_length=1)

    def __init__(self, **data: object) -> None:
        del data
        raise TypeError(
            "ProviderToolPolicy must be derived from a validated read-only registry"
        )

    @classmethod
    def model_construct(cls, _fields_set=None, **values: object):
        del _fields_set, values
        raise TypeError(
            "ProviderToolPolicy must be derived from a validated read-only registry"
        )

    @classmethod
    def from_readonly_registry(cls, registry: ToolRegistry) -> ProviderToolPolicy:
        if not registry.tools:
            raise ValueError("read-only registry must register at least one tool")
        specs: list[ProviderToolSpec] = []
        for tool in registry.tools.values():
            if (
                tool.permission_level is not PermissionLevel.AUTOMATIC
                or tool.effect is not ToolEffect.READ
            ):
                raise ValueError(
                    f"tool '{tool.name}' is not an automatic read-only tool"
                )
            description = getattr(tool, "description", None)
            if (
                not isinstance(description, str)
                or not description.strip()
                or len(description) > MAX_TOOL_DESCRIPTION_CHARS
            ):
                raise ValueError(
                    f"tool '{tool.name}' must declare a nonblank bounded description"
                )
            parameters = tool.arguments_model.model_json_schema()
            if parameters.get("type") != "object":
                raise ValueError(
                    f"tool '{tool.name}' arguments schema must be a JSON object"
                )
            if parameters.get("additionalProperties") is not False:
                raise ValueError(f"tool '{tool.name}' arguments schema must be closed")
            specs.append(
                ProviderToolSpec(
                    name=tool.name,
                    description=description,
                    parameters=parameters,
                )
            )
        return super().model_construct(catalog=tuple(specs))

    @property
    def allowed_tool_names(self) -> frozenset[str]:
        return frozenset(spec.name for spec in self.catalog)
