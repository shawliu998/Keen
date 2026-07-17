from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.agent import (
    AgentStepExecutor,
    AgentTool,
    SQLiteAuditSink,
    StateMutation,
    ToolAuditStart,
    ToolAuditSuccess,
    ToolAuditTerminal,
    ToolContext,
    ToolRegistry,
)
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
from app.repositories import review_repository
from app.repositories.review_repository import ReviewRepository
from app.repositories.task_repository import TaskRepository
from app.review.scheduler import SCHEDULER_VERSION

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "agent-product-tools.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def _unusable_connection_factory():
    raise AssertionError("tool construction must not open a connection")


def _create_task(
    database: Database,
    *,
    task_id: str = "agent-task",
    course_id: str = "course-calculus",
    concept_id: str = "concept-chain-rule",
    scheduled_for: str | None = None,
) -> None:
    with database.connection() as connection:
        TaskRepository(connection).create_task(
            task_id=task_id,
            course_id=course_id,
            concept_id=concept_id,
            title="Practice the chain rule",
            reason="Weak concept",
            due_at=NOW.isoformat(),
            estimated_minutes=15,
            source_type="weak_concept",
            source_id=concept_id,
            priority_score=0.8,
            priority_components={"mastery_weakness": 0.8},
            recommended_reason="Mastery is weak",
            scheduled_for=scheduled_for,
            idempotency_key=f"{task_id}-key",
        )


def _create_review_item(
    database: Database,
    *,
    item_id: str = "agent-review",
    course_id: str = "course-calculus",
    concept_id: str = "concept-chain-rule",
    due_at: datetime = NOW,
) -> None:
    with database.connection() as connection:
        ReviewRepository(connection).create_item(
            item_id=item_id,
            course_id=course_id,
            concept_id=concept_id,
            item_type="flashcard",
            prompt="State the chain rule",
            expected_answer="Differentiate the outer and inner functions",
            source_type="manual",
            source_id=None,
            due_at=due_at.isoformat(),
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key=f"{item_id}-key",
        )


def _context(*, transaction=None) -> ToolContext:
    return ToolContext(
        run_id="run-product-tools",
        step_id="step-product-tools",
        cancellation_event=asyncio.Event(),
        transaction=transaction,
    )


class _ReadAuditSink:
    async def record_started(self, record: ToolAuditStart) -> None:
        del record

    async def record_succeeded(
        self,
        record: ToolAuditSuccess,
        *,
        mutations: tuple[StateMutation, ...],
        transaction: object | None,
    ) -> None:
        del record
        assert mutations == ()
        assert transaction is None

    async def record_failed(self, record: ToolAuditTerminal) -> None:
        del record

    async def record_cancelled(self, record: ToolAuditTerminal) -> None:
        del record

    async def record_rejected(self, record: ToolAuditTerminal) -> None:
        del record


def _read_executor(tool: AgentTool) -> AgentStepExecutor:
    registry = ToolRegistry()
    registry.register(tool)
    return AgentStepExecutor(registry, _ReadAuditSink())


def test_initial_product_tools_register_with_closed_permission_boundaries(tmp_path):
    database = _database(tmp_path)
    registry = ToolRegistry()
    register_initial_product_tools(
        registry,
        connection_factory=database.connection,
        course_id="course-calculus",
        as_of=NOW,
    )

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
                "limit": 10,
                "raw_sql": "DELETE FROM mastery",
            },
        )


def test_read_tool_arguments_accept_only_limit() -> None:
    assert ListStudyFeedArguments().limit == 20
    assert ListDueReviewsArguments().limit == 20
    assert ListStudyFeedArguments(limit=50).limit == 50
    assert ListDueReviewsArguments(limit=1).limit == 1

    for arguments_model in (ListStudyFeedArguments, ListDueReviewsArguments):
        with pytest.raises(ValueError):
            arguments_model(limit=0)
        with pytest.raises(ValueError):
            arguments_model(limit=51)


@pytest.mark.parametrize(
    ("tool_name", "forged"),
    [
        ("list_study_feed", {"course_id": "course-physics"}),
        ("list_study_feed", {"as_of": NOW.isoformat()}),
        ("list_due_reviews", {"course_id": "course-physics"}),
        ("list_due_reviews", {"due_at": NOW.isoformat()}),
    ],
)
def test_read_tools_reject_forged_scope_arguments(tool_name, forged) -> None:
    registry = ToolRegistry()
    register_initial_product_tools(
        registry,
        connection_factory=_unusable_connection_factory,
        course_id="course-calculus",
        as_of=NOW,
    )

    with pytest.raises(ValueError, match="extra_forbidden"):
        registry.validate_arguments(tool_name, {"limit": 10, **forged})


def test_read_tool_constructors_reject_invalid_trusted_course() -> None:
    with pytest.raises(ValueError, match="safe identifier"):
        ListStudyFeedTool(
            _unusable_connection_factory,
            course_id="course-calculus'; DROP TABLE mastery; --",
            as_of=NOW,
        )
    with pytest.raises(ValueError, match="safe identifier"):
        ListDueReviewsTool(_unusable_connection_factory, course_id="", due_at=NOW)


def test_read_tool_constructors_require_utc_datetimes() -> None:
    naive = datetime(2026, 7, 16, 8, 0)
    non_utc = datetime(2026, 7, 16, 10, 0, tzinfo=timezone(timedelta(hours=2)))

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        ListStudyFeedTool(
            _unusable_connection_factory, course_id="course-calculus", as_of=naive
        )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        ListDueReviewsTool(
            _unusable_connection_factory, course_id="course-calculus", due_at=naive
        )
    with pytest.raises(ValueError, match="must be UTC"):
        ListStudyFeedTool(
            _unusable_connection_factory, course_id="course-calculus", as_of=non_utc
        )
    with pytest.raises(ValueError, match="must be UTC"):
        ListDueReviewsTool(
            _unusable_connection_factory, course_id="course-calculus", due_at=non_utc
        )


def test_list_study_feed_reads_real_scoped_rows(tmp_path):
    database = _database(tmp_path)
    _create_task(database)
    _create_task(
        database,
        task_id="agent-task-other-course",
        course_id="course-physics",
        concept_id="concept-newton-2",
    )
    _create_task(
        database,
        task_id="agent-task-not-yet-scheduled",
        scheduled_for=(NOW + timedelta(days=1)).isoformat(),
    )

    result = asyncio.run(
        _read_executor(
            ListStudyFeedTool(
                database.connection, course_id="course-calculus", as_of=NOW
            )
        ).execute_step(
            invocation_id="invocation-list-study-feed",
            tool_name="list_study_feed",
            arguments={"limit": 10},
            context=_context(),
        )
    )

    task_ids = {task["task_id"] for task in result.output["tasks"]}
    assert "agent-task" in task_ids
    assert "agent-task-other-course" not in task_ids
    assert "agent-task-not-yet-scheduled" not in task_ids
    assert all(
        task["course_id"] == "course-calculus" for task in result.output["tasks"]
    )


def test_list_due_reviews_reads_real_scoped_schedule(tmp_path):
    database = _database(tmp_path)
    _create_review_item(database)
    _create_review_item(
        database,
        item_id="agent-review-other-course",
        course_id="course-physics",
        concept_id="concept-newton-2",
    )
    _create_review_item(
        database,
        item_id="agent-review-not-due",
        due_at=NOW + timedelta(days=1),
    )

    result = asyncio.run(
        _read_executor(
            ListDueReviewsTool(
                database.connection, course_id="course-calculus", due_at=NOW
            )
        ).execute_step(
            invocation_id="invocation-list-due-reviews",
            tool_name="list_due_reviews",
            arguments={"limit": 10},
            context=_context(),
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


def test_list_due_reviews_limits_before_decoding_later_rows(tmp_path, monkeypatch):
    database = _database(tmp_path)
    _create_review_item(database, item_id="agent-review-first")
    _create_review_item(
        database,
        item_id="agent-review-undecoded",
        due_at=NOW + timedelta(minutes=1),
    )
    decoded_ids: list[str] = []
    original_decode_item = review_repository._decode_item

    def record_decode(row):
        decoded_ids.append(str(row["id"]))
        return original_decode_item(row)

    monkeypatch.setattr(review_repository, "_decode_item", record_decode)

    result = asyncio.run(
        _read_executor(
            ListDueReviewsTool(
                database.connection, course_id="course-calculus", due_at=NOW
            )
        ).execute_step(
            invocation_id="invocation-list-due-reviews-limit",
            tool_name="list_due_reviews",
            arguments={"limit": 1},
            context=_context(),
        )
    )

    assert [item["review_item_id"] for item in result.output["review_items"]] == [
        "agent-review-first"
    ]
    assert decoded_ids == ["agent-review-first"]


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
