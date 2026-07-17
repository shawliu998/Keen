from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from app.database import Database
from app.repositories.misconception_repository import MisconceptionRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.review.scheduler import SCHEDULER_VERSION
from app.services.autonomous_recommendation import (
    AutonomousRecommendationCoordinator,
)


NOW = datetime(2026, 7, 17, 9, 0, tzinfo=UTC)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "autonomous-recommendation.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def _insert_course(connection, course_id: str) -> None:
    connection.execute(
        """
        INSERT INTO courses (id, title, description, created_at)
        VALUES (?, ?, '', ?)
        """,
        (course_id, f"Course {course_id}", NOW.isoformat()),
    )
    connection.commit()


def _insert_indexed_document(connection, *, course_id: str, document_id: str) -> None:
    connection.execute(
        """
        INSERT INTO documents
            (id, course_id, name, mime_type, extension, status, page_count,
             chunk_count, error, created_at, updated_at)
        VALUES (?, ?, 'Bootstrap limits.md', 'text/markdown', '.md', 'indexed',
                1, 1, NULL, ?, ?)
        """,
        (document_id, course_id, NOW.isoformat(), NOW.isoformat()),
    )
    connection.execute(
        """
        INSERT INTO document_versions
            (id, document_id, version_number, content_hash, storage_path,
             size_bytes, parser_version, page_count, created_at)
        VALUES (?, ?, 1, ?, 'documents/source', 1, 'fixture', 1, ?)
        """,
        (f"version-{document_id}", document_id, "a" * 64, NOW.isoformat()),
    )
    connection.execute(
        """
        INSERT INTO course_documents (course_id, document_id, added_at)
        VALUES (?, ?, ?)
        """,
        (course_id, document_id, NOW.isoformat()),
    )
    connection.execute(
        """
        INSERT INTO document_chunks
            (id, document_id, version_id, ordinal, page_number, section_path,
             content, content_hash, text_location, parser_version,
             embedding_version, created_at)
        VALUES (?, ?, ?, 0, 1, '["Bootstrap limits"]', 'source text', ?, '{}',
                'fixture', NULL, ?)
        """,
        (
            f"chunk-{document_id}",
            document_id,
            f"version-{document_id}",
            "b" * 64,
            NOW.isoformat(),
        ),
    )
    connection.commit()


def _due_review(connection, *, item_id: str, course_id: str, concept_id: str) -> None:
    ReviewRepository(connection).create_item(
        item_id=item_id,
        course_id=course_id,
        concept_id=concept_id,
        item_type="free_recall",
        prompt="Recall the concept",
        expected_answer={"text": "answer"},
        source_type="manual",
        source_id=None,
        due_at=(NOW - timedelta(minutes=1)).isoformat(),
        scheduler_version=SCHEDULER_VERSION,
        idempotency_key=f"{item_id}-key",
        created_at=NOW.isoformat(),
    )


def test_indexed_document_bootstraps_then_persists_weak_concept_recommendation(
    tmp_path,
):
    database = _database(tmp_path)
    with database.connection() as connection:
        _insert_course(connection, "course-bootstrap")
        _insert_indexed_document(
            connection, course_id="course-bootstrap", document_id="document-bootstrap"
        )

        result = AutonomousRecommendationCoordinator(connection).observe_and_recommend(
            course_id="course-bootstrap",
            document_id="document-bootstrap",
            now=NOW,
            available_minutes=10,
        )

    assert result.outcome == "task_created"
    assert result.bootstrap is not None
    assert result.bootstrap.concept_created is True
    assert result.candidate is not None
    assert result.candidate.action == "study_very_weak_concept"
    assert result.task is not None
    assert result.task["source_type"] == "weak_concept"
    assert result.task["source_id"] == result.bootstrap.concept_id
    assert result.task["title"] == "Study very weak concept: Bootstrap limits"
    assert result.task["recommended_reason"] == result.candidate.why
    assert result.task["priority_components"] == {
        "recommendation_algorithm_version": "autonomous-recommendation/1.0.0",
        "feed_priority": {
            "version": result.candidate.priority_algorithm_version,
            "components": [
                {
                    "name": component.name,
                    "raw_value": component.raw_value,
                    "weight": component.weight,
                    "contribution": component.contribution,
                }
                for component in result.candidate.priority_components
            ],
            "explanation": list(result.candidate.priority_explanation),
            "unclamped_score": result.candidate.priority_unclamped_score,
        },
        "candidate_id": result.candidate.id,
        "action": "study_very_weak_concept",
        "target_type": "concept",
        "target_id": result.bootstrap.concept_id,
        "component": "mastery",
        "priority_tier": 3,
        "priority_score": result.candidate.priority_score,
        "estimated_minutes": 15,
        "available_minutes": 10,
        "fits_available_minutes": False,
    }


def test_due_review_then_incomplete_session_take_the_fixed_priority_order(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _due_review(
            connection,
            item_id="review-priority",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
        )
        review = AutonomousRecommendationCoordinator(connection).observe_and_recommend(
            course_id="course-calculus", now=NOW, available_minutes=30
        )
        StudyRepository(connection).create_session(
            session_id="session-priority",
            course_id="course-physics",
            title="Continue mechanics",
            mode="study",
            goal="Practice mechanics",
            estimated_minutes=20,
        )
        session = AutonomousRecommendationCoordinator(connection).observe_and_recommend(
            course_id="course-physics", now=NOW, available_minutes=30
        )

    assert review.candidate is not None
    assert review.candidate.action == "review_due"
    assert review.task is not None
    assert review.task["source_type"] == "review"
    assert session.candidate is not None
    assert session.candidate.action == "resume_study_session"
    assert session.task is not None
    assert session.task["source_type"] == "study_session"


def test_empty_course_returns_empty_without_creating_a_task(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _insert_course(connection, "course-empty")
        result = AutonomousRecommendationCoordinator(connection).observe_and_recommend(
            course_id="course-empty", now=NOW, available_minutes=30
        )

        count = connection.execute(
            "SELECT COUNT(*) FROM study_tasks WHERE course_id = 'course-empty'"
        ).fetchone()[0]

    assert result.outcome == "empty"
    assert result.task is None
    assert result.candidate is None
    assert count == 0


def test_same_day_replays_and_never_creates_a_second_active_task(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _due_review(
            connection,
            item_id="review-replay",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
        )
        coordinator = AutonomousRecommendationCoordinator(connection)
        created = coordinator.observe_and_recommend(
            course_id="course-calculus", now=NOW, available_minutes=30
        )
        replay = coordinator.observe_and_recommend(
            course_id="course-calculus",
            now=NOW + timedelta(hours=3),
            available_minutes=30,
        )
        assert created.candidate is not None
        count = connection.execute(
            """
            SELECT COUNT(*) FROM study_tasks
            WHERE course_id = 'course-calculus'
              AND json_extract(priority_components_json, '$.candidate_id') = ?
            """,
            (created.candidate.id,),
        ).fetchone()[0]

    assert created.outcome == "task_created"
    assert replay.outcome == "replay"
    assert created.task is not None and replay.task is not None
    assert replay.task["id"] == created.task["id"]
    assert created.task["id"] in {
        str(task["id"]) for task in created.snapshot.pending_tasks
    }
    assert replay.task["id"] in {
        str(task["id"]) for task in replay.snapshot.pending_tasks
    }
    assert count == 1


def test_concurrent_connections_create_once_and_replay_once(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _due_review(
            connection,
            item_id="review-concurrent",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
        )

    barrier = Barrier(2)

    def observe():
        with database.connection() as connection:
            barrier.wait(timeout=5)
            return AutonomousRecommendationCoordinator(
                connection
            ).observe_and_recommend(
                course_id="course-calculus", now=NOW, available_minutes=30
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _unused: observe(), range(2)))

    with database.connection() as connection:
        count = connection.execute(
            """
            SELECT COUNT(*) FROM study_tasks
            WHERE course_id = 'course-calculus'
              AND json_extract(priority_components_json, '$.candidate_id') = 'review:review-concurrent'
            """
        ).fetchone()[0]

    assert sorted(result.outcome for result in results) == ["replay", "task_created"]
    assert results[0].task is not None and results[1].task is not None
    assert results[0].task["id"] == results[1].task["id"]
    assert count == 1


def test_cross_midnight_concurrent_observers_create_once_and_replay_once(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _due_review(
            connection,
            item_id="review-cross-midnight",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
        )

    barrier = Barrier(2)
    times = (
        datetime(2026, 7, 17, 23, 59, 59, tzinfo=UTC),
        datetime(2026, 7, 18, 0, 0, 1, tzinfo=UTC),
    )

    def observe(now: datetime):
        with database.connection() as connection:
            barrier.wait(timeout=5)
            return AutonomousRecommendationCoordinator(
                connection
            ).observe_and_recommend(
                course_id="course-calculus", now=now, available_minutes=30
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(observe, times))

    with database.connection() as connection:
        active_count = connection.execute(
            """
            SELECT COUNT(*) FROM study_tasks
            WHERE course_id = 'course-calculus'
              AND source_type = 'review'
              AND source_id = 'review-cross-midnight'
              AND status IN ('upcoming', 'overdue')
            """
        ).fetchone()[0]

    assert sorted(result.outcome for result in results) == ["replay", "task_created"]
    assert results[0].task is not None and results[1].task is not None
    assert results[0].task["id"] == results[1].task["id"]
    assert active_count == 1


def test_course_and_target_identity_do_not_collide(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _due_review(
            connection,
            item_id="review-calculus",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
        )
        _due_review(
            connection,
            item_id="review-physics",
            course_id="course-physics",
            concept_id="concept-newton-2",
        )
        coordinator = AutonomousRecommendationCoordinator(connection)
        calculus = coordinator.observe_and_recommend(
            course_id="course-calculus", now=NOW, available_minutes=30
        )
        physics = coordinator.observe_and_recommend(
            course_id="course-physics", now=NOW, available_minutes=30
        )

    assert calculus.task is not None and physics.task is not None
    assert calculus.task["id"] != physics.task["id"]
    assert calculus.task["course_id"] == "course-calculus"
    assert physics.task["course_id"] == "course-physics"


def test_repeated_misconception_uses_its_real_concept_as_the_task_source(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        connection.execute(
            "UPDATE mastery SET probability = 0.9 WHERE concept_id IN (?, ?)",
            ("concept-chain-rule", "concept-limits"),
        )
        connection.execute(
            """
            UPDATE study_tasks
            SET status = 'completed', completed_at = ?, updated_at = ?
            WHERE id = 'task-chain-rule'
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
        connection.commit()
        misconceptions = MisconceptionRepository(connection)
        misconception, _ = misconceptions.create_suspected(
            misconception_id="misconception-chain-rule",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            label="Reverses factors",
            description="Uses the inner derivative first.",
            confidence=0.6,
            idempotency_key="misconception-chain-rule-key",
            seen_at=NOW.isoformat(),
        )
        for number in (1, 2):
            misconceptions.add_evidence(
                evidence_id=f"misconception-evidence-{number}",
                misconception_id=misconception["id"],
                evidence_type="manual",
                confidence=0.6,
                details={"observation": number},
                idempotency_key=f"misconception-evidence-{number}-key",
                created_at=NOW.isoformat(),
            )

        result = AutonomousRecommendationCoordinator(connection).observe_and_recommend(
            course_id="course-calculus", now=NOW, available_minutes=30
        )

    assert result.candidate is not None
    assert result.candidate.action == "address_repeated_misconception"
    assert result.task is not None
    assert result.task["source_type"] == "weak_concept"
    assert result.task["source_id"] == "concept-chain-rule"
    assert result.task["concept_id"] == "concept-chain-rule"
    assert result.task["priority_components"]["misconception_id"] == misconception["id"]


def test_existing_manual_concept_task_truthfully_covers_the_candidate(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        connection.execute(
            "UPDATE mastery SET probability = 0.2 WHERE concept_id = 'concept-chain-rule'"
        )
        connection.execute(
            "UPDATE mastery SET probability = 0.9 WHERE concept_id = 'concept-limits'"
        )
        connection.commit()

        result = AutonomousRecommendationCoordinator(connection).observe_and_recommend(
            course_id="course-calculus", now=NOW, available_minutes=30
        )
        count = connection.execute(
            """
            SELECT COUNT(*) FROM study_tasks
            WHERE course_id = 'course-calculus'
              AND json_extract(priority_components_json, '$.candidate_id')
                  = 'concept:concept-chain-rule:study_very_weak_concept'
            """
        ).fetchone()[0]

    assert result.outcome == "covered_by_active_task"
    assert result.task is not None
    assert result.task["id"] == "task-chain-rule"
    assert count == 0


def test_new_day_creates_new_task_only_after_previous_task_is_completed(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        _due_review(
            connection,
            item_id="review-next-day",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
        )
        coordinator = AutonomousRecommendationCoordinator(connection)
        first = coordinator.observe_and_recommend(
            course_id="course-calculus", now=NOW, available_minutes=30
        )
        assert first.task is not None
        still_active = coordinator.observe_and_recommend(
            course_id="course-calculus",
            now=NOW + timedelta(days=1),
            available_minutes=30,
        )
        TaskRepository(connection).complete(
            first.task["id"],
            expected_revision=first.task["revision"],
            completed_at=NOW.isoformat(),
        )
        second = coordinator.observe_and_recommend(
            course_id="course-calculus",
            now=NOW + timedelta(days=1),
            available_minutes=30,
        )

    assert first.outcome == "task_created"
    assert still_active.outcome == "replay"
    assert still_active.task is not None
    assert still_active.task["id"] == first.task["id"]
    assert second.outcome == "task_created"
    assert second.task is not None
    assert second.task["id"] != first.task["id"]


def test_failed_task_transaction_does_not_report_a_created_recommendation(
    tmp_path, monkeypatch
):
    database = _database(tmp_path)
    with database.connection() as connection:
        _insert_course(connection, "course-bootstrap-failure")
        _insert_indexed_document(
            connection,
            course_id="course-bootstrap-failure",
            document_id="document-bootstrap-failure",
        )

        def fail_create_task(*_args, **_kwargs):
            raise sqlite3.IntegrityError("synthetic task write failure")

        monkeypatch.setattr(TaskRepository, "create_task", fail_create_task)
        with pytest.raises(sqlite3.IntegrityError, match="task write failure"):
            AutonomousRecommendationCoordinator(connection).observe_and_recommend(
                course_id="course-bootstrap-failure",
                document_id="document-bootstrap-failure",
                now=NOW,
                available_minutes=30,
            )

        task_count = connection.execute(
            """
            SELECT COUNT(*) FROM study_tasks
            WHERE course_id = 'course-bootstrap-failure'
            """
        ).fetchone()[0]
        concept_count = connection.execute(
            "SELECT COUNT(*) FROM concepts WHERE course_id = 'course-bootstrap-failure'"
        ).fetchone()[0]
        mastery_count = connection.execute(
            """
            SELECT COUNT(*) FROM mastery AS m
            JOIN concepts AS c ON c.id = m.concept_id
            WHERE c.course_id = 'course-bootstrap-failure'
            """
        ).fetchone()[0]

    assert task_count == 0
    assert concept_count == 0
    assert mastery_count == 0
