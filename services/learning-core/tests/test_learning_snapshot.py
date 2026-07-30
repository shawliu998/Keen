from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.database import Database
from app.repositories.misconception_repository import MisconceptionRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.review.scheduler import SCHEDULER_VERSION
from app.services.learning_snapshot import LearningSnapshotService


NOW = datetime(2026, 7, 16, 9, 0, tzinfo=UTC)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "snapshot.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def _create_due_review(
    connection, *, item_id: str, course_id: str, concept_id: str, due_at: datetime
) -> None:
    ReviewRepository(connection).create_item(
        item_id=item_id,
        course_id=course_id,
        concept_id=concept_id,
        item_type="free_recall",
        prompt=f"Recall {item_id}",
        expected_answer={"text": item_id},
        source_type="manual",
        source_id=None,
        due_at=due_at.isoformat(),
        scheduler_version=SCHEDULER_VERSION,
        idempotency_key=f"{item_id}-key",
        created_at=(NOW - timedelta(minutes=10)).isoformat(),
    )


def _create_repeated_misconception(connection) -> None:
    repository = MisconceptionRepository(connection)
    misconception, _ = repository.create_suspected(
        misconception_id="misconception-chain-rule",
        course_id="course-calculus",
        concept_id="concept-chain-rule",
        label="Reverses factors",
        description="Uses the inner derivative first.",
        confidence=0.6,
        idempotency_key="misconception-chain-rule-key",
        seen_at=(NOW - timedelta(minutes=2)).isoformat(),
    )
    for number in (1, 2):
        repository.add_evidence(
            evidence_id=f"misconception-evidence-{number}",
            misconception_id=misconception["id"],
            evidence_type="manual",
            confidence=0.6 + number / 100,
            details={"observation": number},
            idempotency_key=f"misconception-evidence-{number}-key",
            created_at=(NOW - timedelta(minutes=number)).isoformat(),
        )


def test_snapshot_orders_real_components_by_fixed_priority_and_explains_why(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        connection.execute(
            "UPDATE mastery SET probability = 0.20 WHERE concept_id = 'concept-chain-rule'"
        )
        connection.execute(
            "UPDATE mastery SET probability = 0.60 WHERE concept_id = 'concept-limits'"
        )
        connection.commit()
        _create_due_review(
            connection,
            item_id="review-due",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            due_at=NOW,
        )
        StudyRepository(connection).create_session(
            session_id="session-incomplete",
            course_id="course-calculus",
            title="Continue derivatives",
            mode="study",
            goal="Practice derivatives",
            estimated_minutes=30,
        )
        _create_repeated_misconception(connection)

        snapshot = LearningSnapshotService(connection).build(
            course_id="course-calculus", now=NOW, available_minutes=20
        )

    assert [candidate.action for candidate in snapshot.candidates] == [
        "review_due",
        "resume_study_session",
        "study_very_weak_concept",
        "address_repeated_misconception",
        "study_weak_concept",
    ]
    assert [candidate.priority_tier for candidate in snapshot.candidates] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert [candidate.concept_id for candidate in snapshot.candidates] == [
        "concept-chain-rule",
        None,
        "concept-chain-rule",
        "concept-chain-rule",
        "concept-limits",
    ]
    assert snapshot.candidates[0].target_id == "review-due"
    assert snapshot.candidates[0].component == "review_items"
    assert (
        snapshot.candidates[0].why == "Review is due since 2026-07-16T09:00:00+00:00."
    )
    assert snapshot.candidates[1].fits_available_minutes is False
    assert snapshot.candidates[2].priority_score > 0
    assert snapshot.candidates[0].priority_algorithm_version == "feed-priority/1.0.0"
    assert snapshot.candidates[0].priority_unclamped_score == 0.645833
    assert snapshot.candidates[0].priority_explanation[0] == (
        "deadline_urgency: 1.000 × 0.250 = +0.250"
    )
    review_components = {
        component.name: component
        for component in snapshot.candidates[0].priority_components
    }
    session_components = {
        component.name: component
        for component in snapshot.candidates[1].priority_components
    }
    mastery_components = {
        component.name: component
        for component in snapshot.candidates[2].priority_components
    }
    assert review_components["deadline_urgency"].raw_value == 1.0
    assert review_components["effort_penalty"].raw_value == 0.041667
    assert session_components["effort_penalty"].raw_value == 0.25
    assert mastery_components["mastery_weakness"].raw_value == 0.8
    assert [task["course_id"] for task in snapshot.pending_tasks] == ["course-calculus"]


def test_snapshot_is_course_scoped_and_empty_unknown_course_is_honest(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO courses (id, title, description, created_at)
            VALUES ('course-empty', 'Empty course', '', ?)
            """,
            (NOW.isoformat(),),
        )
        connection.commit()
        _create_due_review(
            connection,
            item_id="review-physics",
            course_id="course-physics",
            concept_id="concept-newton-2",
            due_at=NOW - timedelta(seconds=1),
        )
        calculus = LearningSnapshotService(connection).build(
            course_id="course-calculus", now=NOW, available_minutes=30
        )
        empty = LearningSnapshotService(connection).build(
            course_id="unknown-course", now=NOW, available_minutes=30
        )
        no_state = LearningSnapshotService(connection).build(
            course_id="course-empty", now=NOW, available_minutes=30
        )

    assert all(item["course_id"] == "course-calculus" for item in calculus.due_reviews)
    assert "review-physics" not in [
        candidate.target_id for candidate in calculus.candidates
    ]
    assert empty.course_exists is False
    assert empty.due_reviews == ()
    assert empty.incomplete_sessions == ()
    assert empty.mastery == ()
    assert empty.misconceptions == ()
    assert empty.pending_tasks == ()
    assert empty.completed_tasks == ()
    assert empty.candidates == ()
    assert no_state.course_exists is True
    assert no_state.candidates == ()


def test_snapshot_lists_only_the_50_most_recent_course_completed_tasks(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = TaskRepository(connection)
        for number in range(52):
            task, _ = repository.create_task(
                task_id=f"completed-{number:02d}",
                course_id="course-calculus",
                title=f"Completed task {number}",
                reason="Persisted completion.",
                due_at=(NOW - timedelta(days=1)).isoformat(),
                estimated_minutes=10,
                source_type="manual",
                source_id=None,
                priority_score=0,
                priority_components={},
                recommended_reason="",
                idempotency_key=f"completed-task-key-{number:02d}",
            )
            repository.complete(
                task["id"],
                expected_revision=int(task["revision"]),
                completed_at=(NOW + timedelta(minutes=number)).isoformat(),
            )
        other, _ = repository.create_task(
            task_id="completed-other-course",
            course_id="course-physics",
            title="Other course completion",
            reason="Must remain out of scope.",
            due_at=NOW.isoformat(),
            estimated_minutes=10,
            source_type="manual",
            source_id=None,
            priority_score=0,
            priority_components={},
            recommended_reason="",
            idempotency_key="completed-other-course-key",
        )
        repository.complete(
            other["id"],
            expected_revision=int(other["revision"]),
            completed_at=(NOW + timedelta(hours=2)).isoformat(),
        )

        snapshot = LearningSnapshotService(connection).build(
            course_id="course-calculus", now=NOW, available_minutes=30
        )

    assert len(snapshot.completed_tasks) == 50
    assert snapshot.completed_tasks[0]["id"] == "completed-51"
    assert snapshot.completed_tasks[-1]["id"] == "completed-02"
    assert all(
        task["course_id"] == "course-calculus" for task in snapshot.completed_tasks
    )
    assert all(task["status"] == "completed" for task in snapshot.completed_tasks)
    assert all(task["completed_at"] for task in snapshot.completed_tasks)


def test_snapshot_exposes_missing_mastery_without_creating_a_concept_action(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name, bkt_slip, bkt_guess, bkt_transit)
            VALUES ('concept-uninitialized', 'course-calculus', 'Uninitialized', 0.1, 0.2, 0.1)
            """
        )
        connection.commit()

        snapshot = LearningSnapshotService(connection).build(
            course_id="course-calculus", now=NOW, available_minutes=30
        )

    gap = next(
        item
        for item in snapshot.mastery
        if item["concept_id"] == "concept-uninitialized"
    )
    assert gap["probability"] is None
    assert gap["attempts"] is None
    assert snapshot.mastery_gap_count == 1
    assert [item["concept_id"] for item in snapshot.mastery_gaps] == [
        "concept-uninitialized"
    ]
    assert "concept-uninitialized" not in [
        candidate.target_id for candidate in snapshot.candidates
    ]


def test_snapshot_is_stable_and_includes_reviews_due_at_exact_time_only(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _create_due_review(
            connection,
            item_id="review-z-exact",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            due_at=NOW,
        )
        _create_due_review(
            connection,
            item_id="review-a-exact",
            course_id="course-calculus",
            concept_id="concept-limits",
            due_at=NOW,
        )
        _create_due_review(
            connection,
            item_id="review-a-later",
            course_id="course-calculus",
            concept_id="concept-limits",
            due_at=NOW + timedelta(microseconds=1),
        )
        service = LearningSnapshotService(connection)
        first = service.build(course_id="course-calculus", now=NOW, available_minutes=5)
        second = service.build(
            course_id="course-calculus", now=NOW, available_minutes=5
        )

    assert first == second
    assert [item["id"] for item in first.due_reviews] == [
        "review-a-exact",
        "review-z-exact",
    ]
    assert [
        candidate.target_id
        for candidate in first.candidates
        if candidate.action == "review_due"
    ] == ["review-a-exact", "review-z-exact"]
    assert first.candidates[0].fits_available_minutes is True


def test_snapshot_owns_and_closes_its_read_transaction_but_keeps_callers_open(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        assert connection.in_transaction is False

        LearningSnapshotService(connection).build(
            course_id="course-calculus", now=NOW, available_minutes=30
        )

        assert connection.in_transaction is False
        begin_index = statements.index("BEGIN")
        rollback_index = statements.index("ROLLBACK")
        assert begin_index < rollback_index
        assert any(
            "FROM review_items" in statement
            for statement in statements[begin_index + 1 : rollback_index]
        )

        statements.clear()
        connection.execute("BEGIN")
        LearningSnapshotService(connection).build(
            course_id="course-calculus", now=NOW, available_minutes=30
        )
        assert connection.in_transaction is True
        assert "ROLLBACK" not in statements
        connection.rollback()


@pytest.mark.parametrize(
    ("now", "available_minutes", "message"),
    [
        (datetime(2026, 7, 16, 9, 0), 10, "timezone-aware UTC"),
        (
            datetime(2026, 7, 16, 17, 0, tzinfo=timezone(timedelta(hours=8))),
            10,
            "now must be UTC",
        ),
        (NOW, 0, "available_minutes"),
    ],
)
def test_snapshot_rejects_ambiguous_time_or_capacity(
    tmp_path, now, available_minutes, message
):
    database = _database(tmp_path)
    with database.connection() as connection:
        with pytest.raises(ValueError, match=message):
            LearningSnapshotService(connection).build(
                course_id="course-calculus",
                now=now,
                available_minutes=available_minutes,
            )
