from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator

from app.repositories.review_repository import ReviewRepository
from app.repositories.task_repository import TaskRepository

from ..registry import ToolRegistry
from ..types import (
    SAFE_IDENTIFIER_PATTERN,
    PermissionLevel,
    StateMutation,
    ToolArguments,
    ToolContext,
    ToolEffect,
    ToolOutput,
    ToolResult,
    is_safe_identifier,
)
from ..transaction import SQLiteToolSession

ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection]]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("datetime must be UTC")
    return value.astimezone(UTC)


def _require_trusted_course_id(value: str) -> str:
    if not is_safe_identifier(value):
        raise ValueError("course_id must be a safe identifier")
    return value


class ListStudyFeedArguments(ToolArguments):
    limit: int = Field(default=20, ge=1, le=50)


class StudyFeedTaskOutput(ToolOutput):
    task_id: str = Field(min_length=1, max_length=256, pattern=SAFE_IDENTIFIER_PATTERN)
    course_id: str = Field(
        min_length=1, max_length=256, pattern=SAFE_IDENTIFIER_PATTERN
    )
    concept_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=SAFE_IDENTIFIER_PATTERN,
    )
    title: str = Field(min_length=1, max_length=65_536)
    reason: str = Field(min_length=1, max_length=65_536)
    status: Literal["upcoming", "overdue"]
    due_at: str = Field(min_length=1, max_length=64)
    estimated_minutes: int = Field(ge=0)
    priority_score: float
    revision: int = Field(ge=0)


class ListStudyFeedOutput(ToolOutput):
    tasks: list[StudyFeedTaskOutput] = Field(max_length=50)


class ListStudyFeedTool:
    name = "list_study_feed"
    description = (
        "List prioritized study tasks for the trusted current course "
        "as of the fixed run time."
    )
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = ListStudyFeedArguments
    result_model = ListStudyFeedOutput

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        course_id: str,
        as_of: datetime,
    ) -> None:
        self._connection_factory = connection_factory
        self._course_id = _require_trusted_course_id(course_id)
        self._as_of = _require_utc(as_of)

    async def execute(
        self, arguments: ListStudyFeedArguments, context: ToolContext
    ) -> ToolResult:
        context.raise_if_cancelled()
        with self._connection_factory() as connection:
            tasks = TaskRepository(connection).list_feed(
                as_of=self._as_of.isoformat(),
                course_id=self._course_id,
                limit=arguments.limit,
            )
        context.raise_if_cancelled()
        return ToolResult(
            output={
                "tasks": [
                    {
                        "task_id": task["id"],
                        "course_id": task["course_id"],
                        "concept_id": task["concept_id"],
                        "title": task["title"],
                        "reason": task["reason"],
                        "status": task["status"],
                        "due_at": task["due_at"],
                        "estimated_minutes": task["estimated_minutes"],
                        "priority_score": task["priority_score"],
                        "revision": task["revision"],
                    }
                    for task in tasks
                ]
            }
        )


class ListDueReviewsArguments(ToolArguments):
    limit: int = Field(default=20, ge=1, le=50)


class DueReviewItemOutput(ToolOutput):
    review_item_id: str = Field(
        min_length=1, max_length=256, pattern=SAFE_IDENTIFIER_PATTERN
    )
    course_id: str = Field(
        min_length=1, max_length=256, pattern=SAFE_IDENTIFIER_PATTERN
    )
    concept_id: str = Field(
        min_length=1, max_length=256, pattern=SAFE_IDENTIFIER_PATTERN
    )
    item_type: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=65_536)
    due_at: str = Field(min_length=1, max_length=64)
    state: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=0)


class ListDueReviewsOutput(ToolOutput):
    review_items: list[DueReviewItemOutput] = Field(max_length=50)


class ListDueReviewsTool:
    name = "list_due_reviews"
    description = (
        "List due review items for the trusted current course as of the fixed run time."
    )
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = ListDueReviewsArguments
    result_model = ListDueReviewsOutput

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        course_id: str,
        due_at: datetime,
    ) -> None:
        self._connection_factory = connection_factory
        self._course_id = _require_trusted_course_id(course_id)
        self._due_at = _require_utc(due_at)

    async def execute(
        self, arguments: ListDueReviewsArguments, context: ToolContext
    ) -> ToolResult:
        context.raise_if_cancelled()
        with self._connection_factory() as connection:
            items = ReviewRepository(connection).list_due(
                due_at=self._due_at.isoformat(),
                course_id=self._course_id,
                limit=arguments.limit,
            )
        context.raise_if_cancelled()
        return ToolResult(
            output={
                "review_items": [
                    {
                        "review_item_id": item["id"],
                        "course_id": item["course_id"],
                        "concept_id": item["concept_id"],
                        "item_type": item["item_type"],
                        "prompt": item["prompt"],
                        "due_at": item["due_at"],
                        "state": item["state"],
                        "revision": item["revision"],
                    }
                    for item in items
                ]
            }
        )


class CompleteStudyTaskArguments(ToolArguments):
    task_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=SAFE_IDENTIFIER_PATTERN,
    )
    course_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=SAFE_IDENTIFIER_PATTERN,
    )
    expected_revision: int = Field(ge=0)
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, value: datetime) -> datetime:
        return _require_utc(value)


class CompleteStudyTaskOutput(ToolOutput):
    task_id: str = Field(min_length=1, max_length=256, pattern=SAFE_IDENTIFIER_PATTERN)
    status: Literal["completed"]
    revision: int = Field(ge=1)


class CompleteStudyTaskTool:
    name = "complete_study_task"
    permission_level = PermissionLevel.LOCAL_REVERSIBLE
    effect = ToolEffect.LOCAL_WRITE
    arguments_model = CompleteStudyTaskArguments
    result_model = CompleteStudyTaskOutput

    async def execute(
        self, arguments: CompleteStudyTaskArguments, context: ToolContext
    ) -> ToolResult:
        context.raise_if_cancelled()
        if not isinstance(context.transaction, SQLiteToolSession):
            raise RuntimeError("complete_study_task requires a SQLite transaction")
        repository = TaskRepository(context.transaction)
        before = repository.get(arguments.task_id)
        if before is None or before["course_id"] != arguments.course_id:
            raise LookupError("study task was not found in the requested course")
        after = repository.complete(
            arguments.task_id,
            expected_revision=arguments.expected_revision,
            completed_at=arguments.completed_at.isoformat(),
            commit=False,
        )
        context.raise_if_cancelled()
        mutation = StateMutation(
            entity_type="study_task",
            entity_id=arguments.task_id,
            operation="update",
            before=before,
            after=after,
            undo={
                "operation": "update",
                "entity_type": "study_task",
                "entity_id": arguments.task_id,
                "restore": before,
            },
        )
        return ToolResult(
            output={
                "task_id": after["id"],
                "status": after["status"],
                "revision": after["revision"],
            },
            mutations=(mutation,),
        )


class ExportStudyDataArguments(ToolArguments):
    course_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=SAFE_IDENTIFIER_PATTERN,
    )
    format: Literal["json"] = "json"


class ExportStudyDataOutput(ToolOutput):
    pass


class ExportStudyDataTool:
    name = "export_study_data"
    permission_level = PermissionLevel.CONFIRM_FIRST
    effect = ToolEffect.EXTERNAL_OR_DESTRUCTIVE
    arguments_model = ExportStudyDataArguments
    result_model = ExportStudyDataOutput

    async def execute(
        self, arguments: ExportStudyDataArguments, context: ToolContext
    ) -> ToolResult:
        raise RuntimeError("Level 3 export is unavailable in this milestone")


def register_readonly_product_tools(
    registry: ToolRegistry,
    *,
    connection_factory: ConnectionFactory,
    course_id: str,
    as_of: datetime,
) -> None:
    registry.register(
        ListStudyFeedTool(connection_factory, course_id=course_id, as_of=as_of)
    )
    registry.register(
        ListDueReviewsTool(connection_factory, course_id=course_id, due_at=as_of)
    )


def register_initial_product_tools(
    registry: ToolRegistry,
    *,
    connection_factory: ConnectionFactory,
    course_id: str,
    as_of: datetime,
) -> None:
    register_readonly_product_tools(
        registry,
        connection_factory=connection_factory,
        course_id=course_id,
        as_of=as_of,
    )
    registry.register(CompleteStudyTaskTool())
    registry.register(ExportStudyDataTool())
