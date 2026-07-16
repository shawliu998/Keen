from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.agent import SQLiteAuditSink, ToolContext, ToolRegistry
from app.agent.tools import (
    CompleteStudyTaskArguments,
    CompleteStudyTaskTool,
    ListDueReviewsArguments,
    ListDueReviewsTool,
    ListStudyFeedArguments,
    ListStudyFeedTool,
    register_initial_product_tools,
)
from app.database import Database
from app.repositories.review_repository import ReviewRepository
from app.repositories.task_repository import TaskRepository
from app.review.scheduler import SCHEDULER_VERSION

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "agent-product-tools.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def _create_task(database: Database, *, task_id: str = "agent-task") -> None:
    with database.connection() as connection:
        TaskRepository(connection).create_task(
            task_id=task_id,
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            title="Practice the chain rule",
            reason="Weak concept",
            due_at=NOW.isoformat(),
            estimated_minutes=15,
            source_type="weak_concept",
            source_id="concept-chain-rule",
            priority_score=0.8,
            priority_components={"mastery_weakness": 0.8},
            recommended_reason="Mastery is weak",
            idempotency_key=f"{task_id}-key",
        )


def _context(*, transaction=None) -> ToolContext:
    return ToolContext(
        run_id="run-product-tools",
        step_id="step-product-tools",
        cancellation_event=asyncio.Event(),
        transaction=transaction,
    )


def test_initial_product_tools_register_with_closed_permission_boundaries(tmp_path):
    database = _database(tmp_path)
    registry = ToolRegistry()
    register_initial_product_tools(registry, connection_factory=database.connection)

    assert set(registry) == {
        "list_study_feed",
        "list_due_reviews",
        "complete_study_task",
        "export_study_data",
    }
    assert "update_mastery" not in registry.tools
    with pytest.raises(ValueError, match="extra_forbidden"):
        registry.validate_arguments(
            "list_study_feed",
            {
                "as_of": NOW.isoformat(),
                "raw_sql": "DELETE FROM mastery",
            },
        )


def test_list_study_feed_reads_real_scoped_rows(tmp_path):
    database = _database(tmp_path)
    _create_task(database)
    tool = ListStudyFeedTool(database.connection)

    result = asyncio.run(
        tool.execute(
            ListStudyFeedArguments(
                as_of=NOW,
                course_id="course-calculus",
                limit=10,
            ),
            _context(),
        )
    )

    task_ids = {task["task_id"] for task in result.output["tasks"]}
    assert "agent-task" in task_ids
    assert all(
        task["course_id"] == "course-calculus" for task in result.output["tasks"]
    )


def test_list_due_reviews_reads_real_scoped_schedule(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        ReviewRepository(connection).create_item(
            item_id="agent-review",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            item_type="flashcard",
            prompt="State the chain rule",
            expected_answer="Differentiate the outer and inner functions",
            source_type="manual",
            source_id=None,
            due_at=NOW.isoformat(),
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key="agent-review-key",
        )

    result = asyncio.run(
        ListDueReviewsTool(database.connection).execute(
            ListDueReviewsArguments(
                due_at=NOW,
                course_id="course-calculus",
                limit=10,
            ),
            _context(),
        )
    )

    assert result.output["review_items"] == [
        {
            "review_item_id": "agent-review",
            "course_id": "course-calculus",
            "concept_id": "concept-chain-rule",
            "item_type": "flashcard",
            "prompt": "State the chain rule",
            "due_at": NOW.isoformat(),
            "state": "new",
            "revision": 0,
        }
    ]


def test_complete_task_uses_caller_transaction_and_returns_executable_undo(tmp_path):
    database = _database(tmp_path)
    _create_task(database)
    tool = CompleteStudyTaskTool()
    arguments = CompleteStudyTaskArguments(
        task_id="agent-task",
        course_id="course-calculus",
        expected_revision=0,
        completed_at=NOW,
    )

    with pytest.raises(RuntimeError, match="SQLite transaction"):
        asyncio.run(tool.execute(arguments, _context()))

    async def exercise(connection):
        sink = SQLiteAuditSink(connection)
        try:
            async with sink.transaction() as transaction:
                result = await tool.execute(
                    arguments, _context(transaction=transaction)
                )
                raise RuntimeError("force test rollback")
        except RuntimeError as error:
            if str(error) != "force test rollback":
                raise
            return result

    with database.connection() as connection:
        result = asyncio.run(exercise(connection))
        assert result.output == {
            "task_id": "agent-task",
            "status": "completed",
            "revision": 1,
        }
        mutation = result.mutations[0]
        assert mutation.before["status"] == "upcoming"
        assert mutation.after["status"] == "completed"
        assert mutation.undo.restore == mutation.before

    with database.connection() as connection:
        assert TaskRepository(connection).get("agent-task")["status"] == "upcoming"


def test_complete_task_rejects_cross_course_scope_before_mutation(tmp_path):
    database = _database(tmp_path)
    _create_task(database)

    async def exercise(connection):
        async with SQLiteAuditSink(connection).transaction() as transaction:
            await CompleteStudyTaskTool().execute(
                CompleteStudyTaskArguments(
                    task_id="agent-task",
                    course_id="course-physics",
                    expected_revision=0,
                    completed_at=NOW,
                ),
                _context(transaction=transaction),
            )

    with database.connection() as connection:
        with pytest.raises(LookupError, match="requested course"):
            asyncio.run(exercise(connection))

    with database.connection() as connection:
        assert TaskRepository(connection).get("agent-task")["status"] == "upcoming"


def test_product_tool_datetimes_must_be_utc() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        ListStudyFeedArguments(as_of=datetime(2026, 7, 16, 8, 0))
