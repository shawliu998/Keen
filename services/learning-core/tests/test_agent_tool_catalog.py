from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.agent import (
    MAX_TOOL_DESCRIPTION_CHARS,
    AgentStepExecutor,
    PermissionLevel,
    ProviderToolPolicy,
    ProviderToolRuntime,
    ProviderToolSpec,
    ToolContext,
    ToolEffect,
    ToolRegistry,
    ToolResult,
)
from app.agent.tools import (
    CompleteStudyTaskTool,
    ExportStudyDataTool,
    ListDueReviewsTool,
    ListStudyFeedArguments,
    ListStudyFeedTool,
    SearchCourseKnowledgeTool,
    register_initial_product_tools,
    register_readonly_product_tools,
)
from app.agent.tools.product import ListStudyFeedOutput
from app.agent.provider import ProviderRequest

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def _unusable_connection_factory():
    raise AssertionError("tool construction must not open a connection")


def _readonly_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_readonly_product_tools(
        registry,
        connection_factory=_unusable_connection_factory,
        course_id="course-calculus",
        as_of=NOW,
    )
    return registry


class _UndescribedReadTool:
    name = "undescribed_read"
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = ListStudyFeedArguments
    result_model = ListStudyFeedOutput

    async def execute(
        self, arguments: ListStudyFeedArguments, context: ToolContext
    ) -> ToolResult:
        raise NotImplementedError


class _BlankDescriptionReadTool(_UndescribedReadTool):
    name = "blank_description_read"
    description = "  \n  "


class _LongDescriptionReadTool(_UndescribedReadTool):
    name = "long_description_read"
    description = "x" * (MAX_TOOL_DESCRIPTION_CHARS + 1)


def test_readonly_registration_registers_exactly_the_scoped_read_tools() -> None:
    registry = _readonly_registry()

    assert list(registry) == [
        "list_study_feed",
        "list_due_reviews",
        "search_course_knowledge",
    ]
    feed = registry.get("list_study_feed")
    reviews = registry.get("list_due_reviews")
    knowledge = registry.get("search_course_knowledge")
    assert isinstance(feed, ListStudyFeedTool)
    assert isinstance(reviews, ListDueReviewsTool)
    assert isinstance(knowledge, SearchCourseKnowledgeTool)
    for tool in (feed, reviews, knowledge):
        assert tool.permission_level is PermissionLevel.AUTOMATIC
        assert tool.effect is ToolEffect.READ


def test_initial_registration_reuses_readonly_registration() -> None:
    registry = ToolRegistry()
    register_initial_product_tools(
        registry,
        connection_factory=_unusable_connection_factory,
        course_id="course-calculus",
        as_of=NOW,
    )

    assert list(registry) == [
        "list_study_feed",
        "list_due_reviews",
        "search_course_knowledge",
        "complete_study_task",
        "export_study_data",
    ]
    assert isinstance(registry.get("complete_study_task"), CompleteStudyTaskTool)
    assert isinstance(registry.get("export_study_data"), ExportStudyDataTool)


def test_read_tool_descriptions_are_fixed_and_hide_trusted_scope() -> None:
    later = NOW + timedelta(days=30)
    tools = [
        ListStudyFeedTool(
            _unusable_connection_factory, course_id="course-calculus", as_of=NOW
        ),
        ListStudyFeedTool(
            _unusable_connection_factory, course_id="course-physics", as_of=later
        ),
        ListDueReviewsTool(
            _unusable_connection_factory, course_id="course-calculus", due_at=NOW
        ),
        ListDueReviewsTool(
            _unusable_connection_factory, course_id="course-physics", due_at=later
        ),
        SearchCourseKnowledgeTool(
            _unusable_connection_factory, course_id="course-calculus"
        ),
        SearchCourseKnowledgeTool(
            _unusable_connection_factory, course_id="course-physics"
        ),
    ]

    assert tools[0].description == tools[1].description
    assert tools[2].description == tools[3].description
    assert tools[4].description == tools[5].description
    for tool in tools:
        description = tool.description
        assert 0 < len(description) <= MAX_TOOL_DESCRIPTION_CHARS
        assert description == description.strip()
        for leaked in (
            "course-calculus",
            "course-physics",
            "course_id",
            "as_of",
            "due_at",
            NOW.isoformat(),
            later.isoformat(),
        ):
            assert leaked not in description


def test_policy_catalog_names_match_registry_names_in_order() -> None:
    registry = _readonly_registry()
    policy = ProviderToolPolicy.from_readonly_registry(registry)

    assert [spec.name for spec in policy.catalog] == list(registry)
    assert [spec.name for spec in policy.catalog] == [
        "list_study_feed",
        "list_due_reviews",
        "search_course_knowledge",
    ]


def test_policy_derivation_is_deterministic_and_follows_registry_order() -> None:
    first = ProviderToolPolicy.from_readonly_registry(_readonly_registry())
    second = ProviderToolPolicy.from_readonly_registry(_readonly_registry())
    assert first == second

    reversed_registry = ToolRegistry()
    reversed_registry.register(
        ListDueReviewsTool(
            _unusable_connection_factory, course_id="course-calculus", due_at=NOW
        )
    )
    reversed_registry.register(
        ListStudyFeedTool(
            _unusable_connection_factory, course_id="course-calculus", as_of=NOW
        )
    )
    reversed_policy = ProviderToolPolicy.from_readonly_registry(reversed_registry)

    assert [spec.name for spec in reversed_policy.catalog] == [
        "list_due_reviews",
        "list_study_feed",
    ]
    assert reversed_policy != first


def test_catalog_schemas_expose_only_bounded_non_scope_arguments() -> None:
    policy = ProviderToolPolicy.from_readonly_registry(_readonly_registry())

    for spec in policy.catalog:
        assert spec.parameters["type"] == "object"
        assert spec.parameters["additionalProperties"] is False
        properties = spec.parameters["properties"]
        if spec.name == "search_course_knowledge":
            assert set(properties) == {"query", "limit"}
            assert properties["query"]["type"] == "string"
            assert properties["query"]["minLength"] == 1
            assert properties["query"]["maxLength"] == 512
            assert properties["limit"] == {
                "default": 3,
                "maximum": 5,
                "minimum": 1,
                "title": "Limit",
                "type": "integer",
            }
        else:
            assert set(properties) == {"limit"}
            limit = properties["limit"]
            assert limit["type"] == "integer"
            assert limit["default"] == 20
            assert limit["minimum"] == 1
            assert limit["maximum"] == 50
        serialized = json.dumps(spec.parameters)
        for forged in ("course_id", "as_of", "due_at", "file_path", "raw_sql"):
            assert forged not in serialized


def test_allowed_tool_names_is_derived_and_cannot_drift() -> None:
    policy = ProviderToolPolicy.from_readonly_registry(_readonly_registry())

    assert isinstance(policy.allowed_tool_names, frozenset)
    assert policy.allowed_tool_names == frozenset(spec.name for spec in policy.catalog)
    assert policy.allowed_tool_names == frozenset(
        {"list_study_feed", "list_due_reviews", "search_course_knowledge"}
    )

    with pytest.raises(TypeError, match="must be derived"):
        ProviderToolPolicy(
            catalog=policy.catalog,
            allowed_tool_names=frozenset({"list_study_feed"}),
        )
    with pytest.raises(ValueError, match="frozen_instance"):
        policy.allowed_tool_names = frozenset()
    with pytest.raises(ValueError, match="frozen_instance"):
        policy.catalog = ()
    with pytest.raises(ValueError, match="frozen_instance"):
        policy.catalog[0].name = "forged_tool"


def test_policy_rejects_empty_registry() -> None:
    with pytest.raises(ValueError, match="at least one tool"):
        ProviderToolPolicy.from_readonly_registry(ToolRegistry())


def test_policy_rejects_empty_catalog() -> None:
    with pytest.raises(TypeError, match="must be derived"):
        ProviderToolPolicy(catalog=())


def test_policy_rejects_level2_and_level3_tools() -> None:
    registry = _readonly_registry()
    registry.register(CompleteStudyTaskTool())
    with pytest.raises(ValueError, match="read-only"):
        ProviderToolPolicy.from_readonly_registry(registry)

    level3_only = ToolRegistry()
    level3_only.register(ExportStudyDataTool())
    with pytest.raises(ValueError, match="read-only"):
        ProviderToolPolicy.from_readonly_registry(level3_only)


def test_policy_rejects_the_full_initial_registry() -> None:
    registry = ToolRegistry()
    register_initial_product_tools(
        registry,
        connection_factory=_unusable_connection_factory,
        course_id="course-calculus",
        as_of=NOW,
    )

    with pytest.raises(ValueError, match="read-only"):
        ProviderToolPolicy.from_readonly_registry(registry)


@pytest.mark.parametrize(
    "tool",
    [
        _UndescribedReadTool(),
        _BlankDescriptionReadTool(),
        _LongDescriptionReadTool(),
    ],
    ids=["missing", "blank", "overlong"],
)
def test_policy_rejects_tools_without_a_safe_description(tool) -> None:
    registry = ToolRegistry()
    registry.register(tool)

    with pytest.raises(ValueError, match="description"):
        ProviderToolPolicy.from_readonly_registry(registry)


def test_provider_tool_spec_accepts_a_bounded_closed_schema() -> None:
    spec = ProviderToolSpec(
        name="list_study_feed",
        description="List prioritized study tasks for the trusted current course.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 50,
                }
            },
        },
    )

    assert spec.parameters["additionalProperties"] is False


@pytest.mark.parametrize(
    "name", ["", "ListStudyFeed", "list-study-feed", "9tools", "list files"]
)
def test_provider_tool_spec_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValueError):
        ProviderToolSpec(name=name, description="d", parameters={})


@pytest.mark.parametrize(
    "description",
    ["", "   ", "x" * (MAX_TOOL_DESCRIPTION_CHARS + 1)],
    ids=["empty", "blank", "overlong"],
)
def test_provider_tool_spec_rejects_unsafe_descriptions(description: str) -> None:
    with pytest.raises(ValueError):
        ProviderToolSpec(name="list_study_feed", description=description, parameters={})


@pytest.mark.parametrize(
    "key", ["reasoning", "chain_of_thought", "scratchpad", "reasoningTrace"]
)
def test_provider_tool_spec_rejects_hidden_reasoning_keys(key: str) -> None:
    parameters = {
        "type": "object",
        "properties": {"nested": {"items": [{key: "x"}]}},
    }

    with pytest.raises(ValueError, match="hidden reasoning"):
        ProviderToolSpec(name="list_study_feed", description="d", parameters=parameters)


def test_provider_tool_spec_rejects_unbounded_parameters() -> None:
    parameters: dict[str, object] = {}
    current = parameters
    for _ in range(20):
        child: dict[str, object] = {}
        current["child"] = child
        current = child

    with pytest.raises(ValueError, match="nesting depth"):
        ProviderToolSpec(name="list_study_feed", description="d", parameters=parameters)


def test_provider_tool_spec_is_frozen_and_closed() -> None:
    spec = ProviderToolSpec(name="list_study_feed", description="d", parameters={})

    with pytest.raises(ValueError, match="frozen_instance"):
        spec.description = "other"
    with pytest.raises(ValueError, match="extra_forbidden"):
        ProviderToolSpec(
            name="list_study_feed",
            description="d",
            parameters={},
            allowlist=["list_study_feed"],
        )


def test_provider_tool_parameters_are_deeply_frozen_and_wire_copy_is_detached() -> None:
    source = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"limit": {"type": "integer"}},
        "required": ["limit"],
    }
    spec = ProviderToolSpec(name="list_study_feed", description="d", parameters=source)

    source["properties"]["forged"] = {"type": "string"}
    with pytest.raises(TypeError, match="immutable"):
        spec.parameters["forged"] = True
    properties = spec.parameters["properties"]
    assert isinstance(properties, dict)
    with pytest.raises(TypeError, match="immutable"):
        properties["forged"] = {"type": "string"}
    with pytest.raises(TypeError, match="immutable"):
        properties |= {"forged": {"type": "string"}}
    required = spec.parameters["required"]
    assert isinstance(required, tuple)

    wire = spec.parameters_for_wire()
    wire_properties = wire["properties"]
    assert isinstance(wire_properties, dict)
    wire_properties["wire_only"] = {"type": "string"}
    assert "wire_only" not in properties
    assert "forged" not in properties


class _UnusedAuditSink:
    pass


def test_runtime_capability_rejects_mismatched_or_transactional_executor() -> None:
    registry = _readonly_registry()
    other_registry = _readonly_registry()
    mismatched = AgentStepExecutor(other_registry, _UnusedAuditSink())

    with pytest.raises(ValueError, match="same non-transactional"):
        ProviderToolRuntime.from_readonly_registry(registry, mismatched)

    transactional = AgentStepExecutor(
        registry,
        _UnusedAuditSink(),
        transaction_factory=lambda: None,
    )
    with pytest.raises(ValueError, match="same non-transactional"):
        ProviderToolRuntime.from_readonly_registry(registry, transactional)


def test_runtime_capability_cannot_bind_level_two_registry() -> None:
    registry = _readonly_registry()
    registry.register(CompleteStudyTaskTool())
    executor = AgentStepExecutor(registry, _UnusedAuditSink())

    with pytest.raises(ValueError, match="read-only"):
        ProviderToolRuntime.from_readonly_registry(registry, executor)


def test_runtime_capability_cannot_be_rebound_or_subclassed() -> None:
    registry = _readonly_registry()
    executor = AgentStepExecutor(registry, _UnusedAuditSink())
    runtime = ProviderToolRuntime.from_readonly_registry(registry, executor)

    with pytest.raises(AttributeError, match="immutable"):
        runtime._executor = AgentStepExecutor(registry, _UnusedAuditSink())
    with pytest.raises(AttributeError, match="immutable"):
        runtime._policy = ProviderToolPolicy.from_readonly_registry(registry)

    class _RuntimeSubclass(ProviderToolRuntime):
        pass

    with pytest.raises(TypeError, match="subclasses"):
        _RuntimeSubclass.from_readonly_registry(registry, executor)


def test_provider_request_rejects_duplicate_catalog_names() -> None:
    spec = ProviderToolSpec(
        name="list_study_feed",
        description="List current study tasks.",
        parameters={"type": "object", "additionalProperties": False},
    )

    with pytest.raises(ValueError, match="must be unique"):
        ProviderRequest(
            run_id="run-catalog-duplicate",
            user_intent="List study tasks",
            mode="study",
            tools=(spec, spec),
        )
