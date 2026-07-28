"""Durable, redacted summary-to-FSRS handoff contracts."""

from __future__ import annotations

import json

import pytest

from app.repositories.study_repository import StudyRepository
from app.services.active_recall_progression import ActiveRecallProgressionService
from app.services.study_summary_review import (
    StudySummaryConflictError,
    StudySummaryReviewService,
)
from app.services.targeted_practice_progression import (
    TargetedPracticeProgressionService,
)
from test_autonomous_study_session import NOW, _database
from test_targeted_practice_service import _begin


def _answered(database):
    session_id, begun = _begin(database)
    with database.connection() as connection:
        before = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        first_answered = TargetedPracticeProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=begun.run["id"],
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-answer-summary-001",
            response="wrong",
            now=NOW,
        )
        assert first_answered.session["status"] == "studying"
        recall = ActiveRecallProgressionService(connection).begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(first_answered.session["revision"]),
            idempotency_key="active-recall-begin-summary-unit-2",
            now=NOW,
        )
        recalled = ActiveRecallProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(recall.run["id"]),
            expected_revision=int(recall.session["revision"]),
            idempotency_key="active-recall-answer-summary-unit-2",
            response="chain rule",
            now=NOW,
        )
        practice = TargetedPracticeProgressionService(connection).begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(recalled.session["revision"]),
            idempotency_key="practice-begin-summary-unit-2",
            now=NOW,
        )
        answered = TargetedPracticeProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(practice.run["id"]),
            expected_revision=int(practice.session["revision"]),
            idempotency_key="practice-answer-summary-unit-2",
            response="wrong",
            now=NOW,
        )
        after = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
    return session_id, answered, tuple(before), tuple(after)


def test_summary_handoff_is_redacted_replay_safe_and_does_not_change_mastery(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    session_id, answered, before, after = _answered(database)
    assert before != after  # the predecessor practice, not summary, owns this delta
    with database.connection() as connection:
        mastery_before_summary = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        service = StudySummaryReviewService(connection)
        ready = service.get(course_id="course-calculus", session_id=session_id)
        assert ready.outcome == "ready" and ready.review is None
        result = service.complete(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(answered.session["revision"]),
            idempotency_key="study-summary-complete-001",
            now=NOW,
        )
        assert result.outcome == "applied"
        assert result.session["status"] == "completed"
        assert result.summary["remaining_units"] == 0
        assert result.review["scheduler"] == "fsrs"
        assert result.review["state"] == "new"
        assert tuple(
            connection.execute(
                "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
            ).fetchone()
        ) == tuple(mastery_before_summary)
        assert (
            connection.execute("SELECT COUNT(*) FROM review_items").fetchone()[0] == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM review_schedules").fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT status FROM study_units WHERE id = ?",
                (answered.session["current_unit_id"],),
            ).fetchone()[0]
            == "completed"
        )
        assert (
            connection.execute(
                "SELECT status FROM study_tasks WHERE id = 'autonomous-task'"
            ).fetchone()[0]
            == "completed"
        )
        task_revision = connection.execute(
            "SELECT revision FROM study_tasks WHERE id = 'autonomous-task'"
        ).fetchone()[0]
        replay = service.complete(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(answered.session["revision"]),
            idempotency_key="study-summary-complete-001",
            now=NOW,
        )
        assert replay.outcome == "replayed"
        assert (
            connection.execute(
                "SELECT revision FROM study_tasks WHERE id = 'autonomous-task'"
            ).fetchone()[0]
            == task_revision
        )
        with pytest.raises(StudySummaryConflictError, match="already completed"):
            service.complete(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=int(result.session["revision"]),
                idempotency_key="study-summary-complete-other-001",
                now=NOW,
            )
        restored = service.get(course_id="course-calculus", session_id=session_id)
        assert restored.outcome == "completed"
        assert restored.review == result.review
        with pytest.raises(Exception, match="summary handoff is immutable"):
            connection.execute(
                "UPDATE study_summary_review_handoffs SET task_completed = 0"
            )
        serialized = json.dumps(
            {"summary": restored.summary, "review": restored.review}
        ).casefold()
        for forbidden in (
            "answer",
            "source",
            "concept",
            "assessment",
            "item",
            "idempotency",
            "fingerprint",
        ):
            assert forbidden not in serialized


def test_summary_transaction_rolls_back_review_and_task_when_unit_completion_fails(
    tmp_path, monkeypatch
) -> None:
    database = _database(tmp_path)
    session_id, answered, _, _ = _answered(database)
    with database.connection() as connection:
        service = StudySummaryReviewService(connection)
        from app.repositories.study_repository import StudyRepository

        monkeypatch.setattr(
            StudyRepository,
            "complete_current_unit",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("forced rollback")
            ),
        )
        with pytest.raises(RuntimeError, match="forced rollback"):
            service.complete(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=int(answered.session["revision"]),
                idempotency_key="study-summary-rollback-001",
                now=NOW,
            )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM study_summary_review_handoffs"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM review_items").fetchone()[0] == 0
        )
        assert (
            connection.execute(
                "SELECT status FROM study_tasks WHERE id = 'autonomous-task'"
            ).fetchone()[0]
            != "completed"
        )


def test_summary_rejects_a_legacy_nonfinal_summarizing_state_without_writes(
    tmp_path, monkeypatch
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        monkeypatch.setattr(
            StudyRepository, "get_locked_successor", lambda *_args, **_kwargs: None
        )
        answered = TargetedPracticeProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-answer-legacy-summary-001",
            response="wrong",
            now=NOW,
        )
        assert answered.session["status"] == "summarizing"
        monkeypatch.undo()

        with pytest.raises(StudySummaryConflictError, match="final planned unit"):
            StudySummaryReviewService(connection).complete(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=int(answered.session["revision"]),
                idempotency_key="study-summary-nonfinal-001",
                now=NOW,
            )
        counts = connection.execute(
            """SELECT (SELECT COUNT(*) FROM study_summary_review_handoffs),
                      (SELECT COUNT(*) FROM review_items),
                      (SELECT COUNT(*) FROM review_schedules)"""
        ).fetchone()
        task = connection.execute(
            "SELECT status FROM study_tasks WHERE id = 'autonomous-task'"
        ).fetchone()

    assert tuple(counts) == (0, 0, 0)
    assert task["status"] != "completed"


def test_paused_summarizing_session_rejects_completion_without_any_write(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    session_id, answered, _, _ = _answered(database)
    with database.connection() as connection:
        paused = StudyRepository(connection).transition_session(
            session_id,
            status="paused",
            expected_revision=int(answered.session["revision"]),
            updated_at=NOW.isoformat(),
        )
        before = {
            "revision": paused["revision"],
            "status": paused["status"],
            "resume_from_status": paused["resume_from_status"],
            "task": connection.execute(
                "SELECT status, revision FROM study_tasks WHERE id = 'autonomous-task'"
            ).fetchone(),
            "handoffs": connection.execute(
                "SELECT COUNT(*) FROM study_summary_review_handoffs"
            ).fetchone()[0],
            "reviews": connection.execute(
                "SELECT COUNT(*) FROM review_items"
            ).fetchone()[0],
            "schedules": connection.execute(
                "SELECT COUNT(*) FROM review_schedules"
            ).fetchone()[0],
        }

        with pytest.raises(StudySummaryConflictError, match="paused"):
            StudySummaryReviewService(connection).complete(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=int(paused["revision"]),
                idempotency_key="study-summary-paused-001",
                now=NOW,
            )

        restored = StudyRepository(connection).get_session(session_id)
        task = connection.execute(
            "SELECT status, revision FROM study_tasks WHERE id = 'autonomous-task'"
        ).fetchone()
        after_counts = connection.execute(
            """SELECT (SELECT COUNT(*) FROM study_summary_review_handoffs),
                      (SELECT COUNT(*) FROM review_items),
                      (SELECT COUNT(*) FROM review_schedules)"""
        ).fetchone()

    assert restored is not None
    assert restored["status"] == before["status"] == "paused"
    assert (
        restored["resume_from_status"] == before["resume_from_status"] == "summarizing"
    )
    assert restored["revision"] == before["revision"]
    assert tuple(task) == tuple(before["task"])
    assert tuple(after_counts) == (
        before["handoffs"],
        before["reviews"],
        before["schedules"],
    )
