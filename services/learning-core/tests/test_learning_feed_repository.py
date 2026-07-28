from __future__ import annotations

from pathlib import Path

import pytest

from app.database import Database
from app.repositories.task_repository import TaskRepository


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "learning-feed.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def _create_task(
    repository: TaskRepository,
    *,
    task_id: str,
    priority: float,
    scheduled_for: str | None = None,
):
    return repository.create_task(
        task_id=task_id,
        course_id="course-calculus",
        concept_id="concept-chain-rule",
        title=f"Task {task_id}",
        reason="Deterministic candidate",
        due_at="2026-07-16T09:00:00+00:00",
        estimated_minutes=10,
        source_type="weak_concept",
        source_id="concept-chain-rule",
        priority_score=priority,
        priority_components={"weak_mastery": priority},
        recommended_reason="Chain rule mastery is below target.",
        scheduled_for=scheduled_for,
        idempotency_key=f"{task_id}-key",
        created_at="2026-07-16T07:00:00+00:00",
    )


def test_learning_feed_uses_persisted_priority_and_filters_snoozed_tasks(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = TaskRepository(connection)
        high, high_created = _create_task(repository, task_id="feed-high", priority=9.0)
        low, _ = _create_task(repository, task_id="feed-low", priority=3.0)
        _create_task(
            repository,
            task_id="feed-future",
            priority=20.0,
            scheduled_for="2026-07-20T00:00:00+00:00",
        )
        retried, retried_created = _create_task(
            repository, task_id="feed-high", priority=9.0
        )
        repository.snooze(
            low["id"],
            until="2026-07-18T00:00:00+00:00",
            expected_revision=0,
            updated_at="2026-07-16T08:00:00+00:00",
        )
        feed = repository.list_feed(as_of="2026-07-16T12:00:00+00:00")

    assert high_created is True
    assert retried_created is False
    assert retried == high
    assert [task["id"] for task in feed if task["id"].startswith("feed-")] == [
        "feed-high"
    ]
    assert high["priority_components"] == {"weak_mastery": 9.0}


def test_task_feedback_completion_and_idempotency_are_persisted(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = TaskRepository(connection)
        task, _ = _create_task(repository, task_id="feed-action", priority=5.0)
        feedback, feedback_created = repository.record_feedback(
            feedback_id="feedback-1",
            task_id=task["id"],
            feedback_type="too_hard",
            details={"previous_priority": 5.0},
            idempotency_key="feedback-1-key",
            created_at="2026-07-16T08:00:00+00:00",
        )
        retried, retried_created = repository.record_feedback(
            feedback_id="feedback-1",
            task_id=task["id"],
            feedback_type="too_hard",
            details={"previous_priority": 5.0},
            idempotency_key="feedback-1-key",
        )
        completed = repository.complete(
            task["id"],
            expected_revision=0,
            completed_at="2026-07-16T09:00:00+00:00",
        )
        feed = repository.list_feed(as_of="2026-07-16T12:00:00+00:00")

    assert feedback_created is True
    assert retried_created is False
    assert retried == feedback
    assert feedback["details"] == {"previous_priority": 5.0}
    assert completed["status"] == "completed"
    assert completed["completed_at"] == "2026-07-16T09:00:00+00:00"
    assert completed["id"] not in {item["id"] for item in feed}


def test_task_idempotency_conflict_is_rejected(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = TaskRepository(connection)
        _create_task(repository, task_id="feed-conflict", priority=5.0)
        with pytest.raises(ValueError, match="idempotency key was reused"):
            _create_task(repository, task_id="feed-conflict", priority=8.0)


def test_016_preserves_legacy_tasks_with_safe_defaults(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        legacy = TaskRepository(connection).get("task-chain-rule")

    assert legacy is not None
    assert legacy["source_type"] == "manual"
    assert legacy["priority_score"] == 0
    assert legacy["priority_components"] == {}
    assert legacy["revision"] == 0


def test_016_backfills_completion_time_on_an_existing_001_database(tmp_path):
    database = Database(tmp_path / "legacy-completed-task.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.executescript(
            (migrations / "001_initial.sql").read_text(encoding="utf-8")
        )
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("INSERT INTO schema_migrations(version) VALUES (1)")
        connection.execute(
            "INSERT INTO courses VALUES ('legacy', 'Legacy', '', '2026-07-01')"
        )
        connection.execute(
            """
            INSERT INTO study_tasks (
                id, course_id, concept_id, title, reason, due_at,
                estimated_minutes, status, created_at, updated_at
            ) VALUES (
                'legacy-completed', 'legacy', NULL, 'Done', 'Legacy task',
                '2026-07-02', 10, 'completed', '2026-07-01', '2026-07-03'
            )
            """
        )
        connection.commit()

    assert 16 in database.migrate()
    with database.connection() as connection:
        task = TaskRepository(connection).get("legacy-completed")

    assert task is not None
    assert task["status"] == "completed"
    assert task["completed_at"] == "2026-07-03"
    assert task["source_type"] == "manual"
