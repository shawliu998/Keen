"""Service contracts for deterministic source-grounded active recall."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import sqlite3
from threading import Barrier

import pytest

from app.database import Database
from app.repositories.mastery_repository import MasteryRepository
from app.services.active_recall_progression import (
    ActiveRecallConflictError,
    ActiveRecallProgressionService,
)
from app.services.autonomous_study_session import AutonomousStudySessionService
from app.services.diagnostic_progression import DiagnosticProgressionService
from test_autonomous_study_session import (
    NOW,
    _database,
    _indexed_source,
    _recommendation_task,
)


def _ready_for_recall(database: Database) -> tuple[str, int]:
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        assert created.session is not None
        diagnostic = DiagnosticProgressionService(connection)
        begun = diagnostic.begin(
            course_id="course-calculus",
            session_id=str(created.session["id"]),
            expected_revision=int(created.session["revision"]),
            idempotency_key="diagnostic-begin-active-recall-001",
            now=NOW,
        )
        answered = diagnostic.answer(
            course_id="course-calculus",
            session_id=str(created.session["id"]),
            checkpoint_id=str(begun.checkpoint["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="diagnostic-answer-active-recall-001",
            response="Ready to recall the source.",
            self_assessment="partial",
            now=NOW,
        )
        return str(created.session["id"]), int(answered.session["revision"])


def _begin(database: Database, *, key: str = "active-recall-begin-service-001"):
    session_id, revision = _ready_for_recall(database)
    with database.connection() as connection:
        result = ActiveRecallProgressionService(connection).begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key=key,
            now=NOW,
        )
    return session_id, result


def test_begin_creates_one_learner_safe_source_cloze_and_exact_replay(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        service = ActiveRecallProgressionService(connection)
        replay = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(begun.session["revision"]) - 2,
            idempotency_key="active-recall-begin-service-001",
            now=NOW,
        )
        with pytest.raises(
            ActiveRecallConflictError, match="idempotency key was reused"
        ):
            service.begin(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=int(begun.session["revision"]),
                idempotency_key="active-recall-begin-service-001",
                now=NOW,
            )
        checkpoint = connection.execute(
            "SELECT response, status FROM study_checkpoints WHERE id = ?",
            (begun.checkpoint["id"],),
        ).fetchone()
        item = connection.execute(
            "SELECT answer_key_json FROM assessment_items WHERE id = ?",
            (begun.run["item_id"],),
        ).fetchone()

    assert begun.outcome == "applied"
    assert replay.outcome == "replayed"
    assert begun.session["status"] == "active_recall"
    assert begun.checkpoint["status"] == "pending"
    assert "[...]" in begun.checkpoint["prompt"]
    assert tuple(checkpoint) == (None, "pending")
    assert item is not None and "chain rule" in item["answer_key_json"].casefold()
    public = {**begun.checkpoint, **begun.run, **begun.session}
    assert not {
        name for name in public if "idempotency" in name or "fingerprint" in name
    }
    assert "answer_key" not in begun.run
    serialized = json.dumps(asdict(begun), ensure_ascii=False).casefold()
    assert "chain rule" not in serialized
    assert "chain-rule" not in serialized
    assert "content" not in begun.plan["units"][0]
    assert "objective" not in begun.plan["units"][0]
    assert "concept_id" not in begun.run


def test_begin_rejects_unit_text_outside_cited_source_without_partial_writes(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready_for_recall(database)
    with database.connection() as connection:
        connection.execute(
            """
            UPDATE study_units SET content = 'Fabricated material not present in the chunk.'
            WHERE id = (SELECT current_unit_id FROM study_sessions WHERE id = ?)
            """,
            (session_id,),
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="not in its cited source"):
            ActiveRecallProgressionService(connection).begin(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=revision,
                idempotency_key="active-recall-begin-untrusted-source-001",
                now=NOW,
            )
        state = connection.execute(
            "SELECT status, revision FROM study_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        counts = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM study_active_recall_runs),
              (SELECT COUNT(*) FROM assessments WHERE purpose = 'checkpoint'),
              (SELECT COUNT(*) FROM study_checkpoints WHERE kind = 'active_recall')
            """
        ).fetchone()

    assert tuple(state) == ("studying", revision)
    assert tuple(counts) == (0, 0, 0)


@pytest.mark.parametrize(
    ("response", "correct"), [("chain rule", True), ("product rule", False)]
)
def test_answer_grades_deterministically_updates_mastery_not_fsrs_and_replays(
    tmp_path, response, correct
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        before = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        fsrs_before = connection.execute(
            "SELECT COUNT(*) FROM review_schedules"
        ).fetchone()[0]
        service = ActiveRecallProgressionService(connection)
        answered = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="active-recall-answer-service-001",
            response=response,
            now=NOW,
        )
        replay = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="active-recall-answer-service-001",
            response=f"  {response.upper()}  ",
            now=NOW,
        )
        with pytest.raises(ActiveRecallConflictError, match="already recorded"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="active-recall-answer-service-001",
                response="a changed answer",
                now=NOW,
            )
        after = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        evidence = connection.execute(
            "SELECT evidence_type, correctness, independence, weight FROM mastery_evidence WHERE attempt_id = ?",
            (answered.run["attempt_id"],),
        ).fetchone()
        fsrs_after = connection.execute(
            "SELECT COUNT(*) FROM review_schedules"
        ).fetchone()[0]
        checkpoint = connection.execute(
            "SELECT response FROM study_checkpoints WHERE id = ?",
            (begun.checkpoint["id"],),
        ).fetchone()

    assert answered.outcome == "applied"
    assert replay.outcome == "replayed"
    assert answered.session["status"] == "practicing"
    assert answered.grade is not None and answered.grade["correct"] is correct
    assert replay.grade == answered.grade
    assert int(after["attempts"]) == int(before["attempts"]) + 1
    assert float(after["probability"]) != float(before["probability"])
    assert tuple(evidence[:3]) == ("active_recall", float(correct), 1.0)
    assert float(evidence["weight"]) > 0
    assert fsrs_before == fsrs_after
    assert checkpoint["response"] == "Objective response recorded."
    assert "answer_key" not in answered.run


def test_active_recall_graph_uses_the_injected_request_timestamp(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        answered = ActiveRecallProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="active-recall-answer-timestamp-001",
            response="chain rule",
            now=NOW,
        )
        row = connection.execute(
            """
            SELECT a.created_at, a.updated_at, a.published_at, i.created_at,
                   cp.created_at, cp.answered_at,
                   at.started_at, at.submitted_at, at.graded_at, at.updated_at,
                   ev.created_at, me.created_at, event.observed_at,
                   r.created_at, r.answered_at
            FROM study_active_recall_runs r
            JOIN assessments a ON a.id = r.assessment_id
            JOIN assessment_items i ON i.id = r.item_id
            JOIN study_checkpoints cp ON cp.id = r.checkpoint_id
            JOIN assessment_attempts at ON at.id = r.attempt_id
            JOIN answer_evaluations ev ON ev.id = r.evaluation_id
            JOIN mastery_evidence me ON me.id = r.mastery_evidence_id
            JOIN mastery_events event ON event.id = r.mastery_event_id
            WHERE r.id = ?
            """,
            (begun.run["id"],),
        ).fetchone()
        checkpoint_event = connection.execute(
            """
            SELECT created_at FROM study_session_events
            WHERE session_id = ? AND event_type = 'checkpoint_created'
              AND json_extract(payload_json, '$.checkpoint_id') = ?
            """,
            (session_id, begun.checkpoint["id"]),
        ).fetchone()

    assert answered.outcome == "applied"
    assert row is not None
    assert set(row) == {NOW.isoformat()}
    assert checkpoint_event is not None
    assert checkpoint_event["created_at"] == NOW.isoformat()


def test_changed_answer_payload_and_paused_new_writes_conflict_but_read_restores(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        service = ActiveRecallProgressionService(connection)
        study = connection.execute(
            "SELECT revision FROM study_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert study is not None
        from app.repositories.study_repository import StudyRepository

        StudyRepository(connection).transition_session(
            session_id,
            status="paused",
            expected_revision=int(study["revision"]),
            updated_at=NOW.isoformat(),
        )
        restored = service.get(course_id="course-calculus", session_id=session_id)
        begin_replay = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(begun.session["revision"]) - 2,
            idempotency_key="active-recall-begin-service-001",
            now=NOW,
        )
        with pytest.raises(ActiveRecallConflictError, match="paused"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="active-recall-answer-paused-001",
                response="chain rule",
                now=NOW,
            )

    assert restored.outcome == "pending"
    assert restored.session["status"] == "paused"
    assert begin_replay.outcome == "replayed"


def test_pending_run_cannot_be_skipped_and_answered_run_restores_later_loop(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    from app.repositories.study_repository import StudyRepository

    with database.connection() as connection:
        study = StudyRepository(connection)
        with pytest.raises(
            sqlite3.IntegrityError, match="pending active recall cannot be skipped"
        ):
            study.transition_session(
                session_id,
                status="summarizing",
                expected_revision=int(begun.session["revision"]),
                updated_at=NOW.isoformat(),
            )
        connection.rollback()
        answered = ActiveRecallProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="active-recall-answer-later-read-001",
            response="chain rule",
            now=NOW,
        )
        study.transition_session(
            session_id,
            status="studying",
            expected_revision=int(answered.session["revision"]),
            updated_at=NOW.isoformat(),
        )
        restored = ActiveRecallProgressionService(connection).get(
            course_id="course-calculus", session_id=session_id
        )

    assert restored.outcome == "answered"
    assert restored.session["status"] == "studying"
    assert restored.grade == answered.grade


@pytest.mark.parametrize(
    ("terminal_status", "reason"),
    [("cancelled", "session_cancelled"), ("failed", "session_failed")],
)
def test_pending_run_terminalizes_truthfully_with_its_session(
    tmp_path, terminal_status, reason
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    from app.repositories.study_repository import StudyRepository

    with database.connection() as connection:
        StudyRepository(connection).transition_session(
            session_id,
            status=terminal_status,
            expected_revision=int(begun.session["revision"]),
            updated_at=NOW.isoformat(),
        )
        restored = ActiveRecallProgressionService(connection).get(
            course_id="course-calculus", session_id=session_id
        )
        counts = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM assessment_attempts),
                   (SELECT COUNT(*) FROM answer_evaluations),
                   (SELECT COUNT(*) FROM mastery_events)
            """
        ).fetchone()

    assert restored.outcome == "cancelled"
    assert restored.session["status"] == terminal_status
    assert restored.run is not None
    assert restored.run["status"] == "cancelled"
    assert restored.run["cancellation_reason"] == reason
    assert restored.run["cancelled_at"] == NOW.isoformat()
    assert restored.checkpoint is not None
    assert restored.checkpoint["status"] == "skipped"
    assert tuple(counts) == (0, 0, 0)


def test_answer_rolls_back_on_evidence_fault(tmp_path, monkeypatch) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        monkeypatch.setattr(
            MasteryRepository,
            "record_evidence",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fault")),
        )
        with pytest.raises(RuntimeError, match="fault"):
            ActiveRecallProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="active-recall-answer-fault-001",
                response="chain rule",
                now=NOW,
            )
        counts = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM assessment_attempts),
                   (SELECT COUNT(*) FROM answer_evaluations),
                   (SELECT COUNT(*) FROM mastery_evidence),
                   (SELECT status FROM study_active_recall_runs WHERE id = ?),
                   (SELECT status FROM study_sessions WHERE id = ?)
            """,
            (begun.run["id"], session_id),
        ).fetchone()

    assert tuple(counts) == (0, 0, 1, "pending", "active_recall")


def test_concurrent_answer_converges_to_one_applied_and_one_replay(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    barrier = Barrier(2)

    def answer() -> str:
        connection = database.connect()
        try:
            barrier.wait()
            result = ActiveRecallProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="active-recall-answer-concurrent-001",
                response="chain rule",
                now=NOW,
            )
            return result.outcome
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: answer(), range(2)))
    with database.connection() as connection:
        attempts = connection.execute(
            "SELECT COUNT(*) FROM assessment_attempts"
        ).fetchone()[0]
        events = connection.execute("SELECT COUNT(*) FROM mastery_events").fetchone()[0]

    assert sorted(outcomes) == ["applied", "replayed"]
    assert (attempts, events) == (1, 1)
