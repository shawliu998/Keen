"""Service contracts for deterministic targeted practice."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import sqlite3
from threading import Barrier

import pytest

from app.database import Database
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.study_repository import StudyRepository
from app.services.active_recall_progression import ActiveRecallProgressionService
from app.services.autonomous_study_session import AutonomousStudySessionService
from app.services.diagnostic_progression import DiagnosticProgressionService
from app.services.targeted_practice_progression import (
    TargetedPracticeConflictError,
    TargetedPracticeProgressionService,
)
from test_autonomous_study_session import (
    NOW,
    _database,
    _indexed_source,
    _recommendation_task,
)


def _ready_for_practice(database: Database) -> tuple[str, int]:
    """Build the canonical predecessor chain through answered active recall."""

    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        assert created.session is not None
        session_id = str(created.session["id"])
        diagnostic = DiagnosticProgressionService(connection)
        diagnostic_run = diagnostic.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(created.session["revision"]),
            idempotency_key="diagnostic-begin-targeted-practice-001",
            now=NOW,
        )
        diagnostic_answer = diagnostic.answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(diagnostic_run.checkpoint["id"]),
            expected_revision=int(diagnostic_run.session["revision"]),
            idempotency_key="diagnostic-answer-targeted-practice-001",
            response="Ready to practise the source.",
            self_assessment="partial",
            now=NOW,
        )
        recall = ActiveRecallProgressionService(connection).begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(diagnostic_answer.session["revision"]),
            idempotency_key="active-recall-begin-targeted-practice-001",
            now=NOW,
        )
        recalled = ActiveRecallProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(recall.run["id"]),
            expected_revision=int(recall.session["revision"]),
            idempotency_key="active-recall-answer-targeted-practice-001",
            response="chain rule",
            now=NOW,
        )
        return session_id, int(recalled.session["revision"])


def _begin(database: Database, *, key: str = "practice-begin-service-001"):
    session_id, revision = _ready_for_practice(database)
    with database.connection() as connection:
        result = TargetedPracticeProgressionService(connection).begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key=key,
            now=NOW,
        )
    return session_id, result


def _hidden_answer(connection: sqlite3.Connection, item_id: str) -> str:
    row = connection.execute(
        "SELECT answer_key_json FROM assessment_items WHERE id = ?", (item_id,)
    ).fetchone()
    assert row is not None
    return str(json.loads(row["answer_key_json"])["accepted_answers"][0])


def _practice_item_id(connection: sqlite3.Connection, run_id: str) -> str:
    row = connection.execute(
        "SELECT item_id FROM study_practice_runs WHERE id = ?", (run_id,)
    ).fetchone()
    assert row is not None
    return str(row["item_id"])


def test_begin_freezes_distinct_source_practice_and_exact_replay(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        replay = TargetedPracticeProgressionService(connection).begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-begin-service-001",
            now=NOW,
        )
        with pytest.raises(
            TargetedPracticeConflictError, match="idempotency key was reused"
        ):
            TargetedPracticeProgressionService(connection).begin(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=int(begun.session["revision"]) - 1,
                idempotency_key="practice-begin-service-001",
                now=NOW,
            )
        with pytest.raises(TargetedPracticeConflictError, match="already exists"):
            TargetedPracticeProgressionService(connection).begin(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=int(begun.session["revision"]),
                idempotency_key="practice-begin-service-different-002",
                now=NOW,
            )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM study_practice_runs WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            == 1
        )
        practice_answer = _hidden_answer(
            connection, _practice_item_id(connection, str(begun.run["id"]))
        )
        ar_answer = connection.execute(
            """SELECT i.answer_key_json FROM study_active_recall_runs r
               JOIN assessment_items i ON i.id = r.item_id
               WHERE r.session_id = ?""",
            (session_id,),
        ).fetchone()
        assert ar_answer is not None
        assert (
            practice_answer.casefold()
            not in str(ar_answer["answer_key_json"]).casefold()
        )

    assert begun.outcome == "applied"
    assert replay.outcome == "replayed"
    assert begun.session["status"] == "practicing"
    assert begun.checkpoint["kind"] == "practice"
    assert begun.checkpoint["status"] == "pending"
    assert "[...]" in begun.checkpoint["prompt"]
    public = {**begun.session, **begun.checkpoint, **begun.run}
    assert not {
        name for name in public if "idempotency" in name or "fingerprint" in name
    }
    assert not {"concept_id", "assessment_id", "item_id", "source_chunk_ids"} & set(
        begun.run
    )
    serialized = json.dumps(asdict(begun), ensure_ascii=False).casefold()
    assert practice_answer.casefold() not in serialized
    assert "content" not in begun.plan["units"][0]


def test_source_content_tampering_fails_closed_on_restore_and_answer(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        answer = _hidden_answer(
            connection, _practice_item_id(connection, str(begun.run["id"]))
        )
        connection.execute(
            "UPDATE document_chunks SET content = 'unrelated replacement' "
            "WHERE id IN (SELECT value FROM json_each((SELECT source_chunk_ids_json "
            "FROM study_practice_runs WHERE id = ?)))",
            (begun.run["id"],),
        )
        connection.commit()
        service = TargetedPracticeProgressionService(connection)
        with pytest.raises(RuntimeError, match="source content fingerprint"):
            service.get(course_id="course-calculus", session_id=session_id)
        with pytest.raises(RuntimeError, match="source content fingerprint"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="practice-answer-source-tamper-001",
                response=answer,
                now=NOW,
            )
        assert (
            connection.execute(
                "SELECT status FROM study_practice_runs WHERE id = ?",
                (begun.run["id"],),
            ).fetchone()["status"]
            == "pending"
        )


def test_begin_exact_replay_survives_a_later_current_unit(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        service = TargetedPracticeProgressionService(connection)
        answer = _hidden_answer(
            connection, _practice_item_id(connection, str(begun.run["id"]))
        )
        answered = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-answer-before-late-begin-replay-001",
            response=answer,
            now=NOW,
        )
        units = connection.execute(
            """SELECT u.id FROM study_units u
               JOIN study_plan_versions p ON p.id = u.plan_version_id
               WHERE p.session_id = ? ORDER BY u.ordinal""",
            (session_id,),
        ).fetchall()
        assert len(units) >= 2
        replay = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-begin-service-001",
            now=NOW,
        )

    assert replay.outcome == "replayed"
    assert replay.run["id"] == begun.run["id"]
    assert replay.run["status"] == "answered"
    assert answered.session["status"] == "studying"
    assert replay.current_unit is not None
    assert replay.current_unit["id"] == units[1]["id"]


@pytest.mark.parametrize("terminal_status", ["cancelled", "failed"])
def test_terminal_before_begin_restores_as_cancelled_without_a_run(
    tmp_path, terminal_status
) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready_for_practice(database)
    with database.connection() as connection:
        StudyRepository(connection).transition_session(
            session_id,
            status=terminal_status,
            expected_revision=revision,
            updated_at=NOW.isoformat(),
        )
        restored = TargetedPracticeProgressionService(connection).get(
            course_id="course-calculus", session_id=session_id
        )

    assert restored.outcome == "cancelled"
    assert restored.session["status"] == terminal_status
    assert restored.session["finished_at"] == NOW.isoformat()
    assert restored.run is None
    assert restored.checkpoint is None
    assert restored.grade is None


@pytest.mark.parametrize("correct", [True, False])
def test_answer_applies_one_practice_bkt_event_not_fsrs_and_replays(
    tmp_path, correct
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        answer = _hidden_answer(
            connection, _practice_item_id(connection, str(begun.run["id"]))
        )
        response = answer if correct else "definitely not the accepted answer"
        before = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        fsrs_before = connection.execute(
            "SELECT COUNT(*) FROM review_schedules"
        ).fetchone()[0]
        service = TargetedPracticeProgressionService(connection)
        answered = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-answer-service-001",
            response=response,
            now=NOW,
        )
        replay = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(begun.run["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-answer-service-001",
            response=f"  {response.upper()}  ",
            now=NOW,
        )
        with pytest.raises(TargetedPracticeConflictError, match="already recorded"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="practice-answer-service-001",
                response="changed answer",
                now=NOW,
            )
        after = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        evidence = connection.execute(
            """SELECT me.evidence_type, me.correctness, me.weight, me.created_at
               FROM mastery_evidence me JOIN study_practice_runs r
                 ON r.mastery_evidence_id = me.id WHERE r.id = ?""",
            (begun.run["id"],),
        ).fetchone()
        graph = connection.execute(
            """SELECT cp.created_at, cp.answered_at, a.created_at, a.published_at,
                      at.started_at, at.graded_at, ev.created_at, me.created_at, event.observed_at,
                      r.created_at, r.answered_at
               FROM study_practice_runs r JOIN study_checkpoints cp ON cp.id = r.checkpoint_id
               JOIN assessments a ON a.id = r.assessment_id
               JOIN assessment_attempts at ON at.id = r.attempt_id
               JOIN answer_evaluations ev ON ev.id = r.evaluation_id
               JOIN mastery_evidence me ON me.id = r.mastery_evidence_id
               JOIN mastery_events event ON event.id = r.mastery_event_id WHERE r.id = ?""",
            (begun.run["id"],),
        ).fetchone()
        fsrs_after = connection.execute(
            "SELECT COUNT(*) FROM review_schedules"
        ).fetchone()[0]
        restored = service.get(course_id="course-calculus", session_id=session_id)
        units = connection.execute(
            """SELECT u.id, u.status FROM study_units u
               JOIN study_plan_versions p ON p.id = u.plan_version_id
               WHERE p.session_id = ? ORDER BY u.ordinal""",
            (session_id,),
        ).fetchall()

    assert answered.outcome == "applied"
    assert replay.outcome == "replayed"
    assert answered.session["status"] == "studying"
    assert answered.session["progress"] == 0.5
    assert answered.session["current_unit_id"] == units[1]["id"]
    assert [(unit["status"]) for unit in units] == ["completed", "active"]
    assert answered.grade is not None and answered.grade["correct"] is correct
    assert replay.grade == answered.grade
    assert int(after["attempts"]) == int(before["attempts"]) + 1
    assert float(after["probability"]) != float(before["probability"])
    assert tuple(evidence[:2]) == ("practice", float(correct))
    assert float(evidence["weight"]) > 0
    assert evidence["created_at"] == NOW.isoformat()
    assert graph is not None and set(graph) == {NOW.isoformat()}
    assert fsrs_before == fsrs_after
    assert "answer_key" not in answered.run
    assert restored.outcome == "not_started"
    assert restored.run is None and restored.grade is None


def test_paused_new_write_conflicts_but_read_and_exact_replay_restore(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        StudyRepository(connection).transition_session(
            session_id,
            status="paused",
            expected_revision=int(begun.session["revision"]),
            updated_at=NOW.isoformat(),
        )
        service = TargetedPracticeProgressionService(connection)
        restored = service.get(course_id="course-calculus", session_id=session_id)
        replay = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-begin-service-001",
            now=NOW,
        )
        with pytest.raises(TargetedPracticeConflictError, match="paused"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="practice-answer-paused-001",
                response="nope",
                now=NOW,
            )
    assert restored.outcome == "pending"
    assert restored.session["status"] == "paused"
    assert replay.outcome == "replayed"


@pytest.mark.parametrize("terminal_status", ["cancelled", "failed"])
def test_terminal_session_cancels_pending_run_without_scoring_and_later_reads_work(
    tmp_path, terminal_status
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        before = connection.execute(
            "SELECT COUNT(*) AS attempts FROM assessment_attempts"
        ).fetchone()
        assert before is not None
        StudyRepository(connection).transition_session(
            session_id,
            status=terminal_status,
            expected_revision=int(begun.session["revision"]),
            updated_at=NOW.isoformat(),
        )
        restored = TargetedPracticeProgressionService(connection).get(
            course_id="course-calculus", session_id=session_id
        )
        counts = connection.execute(
            """SELECT
                 (SELECT COUNT(*) FROM assessment_attempts at
                    JOIN study_practice_runs r ON r.attempt_id = at.id),
                 (SELECT COUNT(*) FROM mastery_evidence me
                    JOIN study_practice_runs r ON r.mastery_evidence_id = me.id),
                 (SELECT COUNT(*) FROM mastery_events event
                    JOIN study_practice_runs r ON r.mastery_event_id = event.id)"""
        ).fetchone()
    assert restored.outcome == "cancelled"
    assert restored.run is not None and restored.run["status"] == "cancelled"
    assert restored.run["cancellation_reason"] == f"session_{terminal_status}"
    assert (
        restored.checkpoint is not None and restored.checkpoint["status"] == "skipped"
    )
    assert tuple(counts) == (0, 0, 0)


def test_answer_rolls_back_and_concurrent_same_key_converges(
    tmp_path, monkeypatch
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        answer = _hidden_answer(
            connection, _practice_item_id(connection, str(begun.run["id"]))
        )
        monkeypatch.setattr(
            MasteryRepository,
            "record_evidence",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fault")),
        )
        with pytest.raises(RuntimeError, match="fault"):
            TargetedPracticeProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="practice-answer-fault-001",
                response=answer,
                now=NOW,
            )
        pending = connection.execute(
            "SELECT status FROM study_practice_runs WHERE id = ?", (begun.run["id"],)
        ).fetchone()
        assert pending is not None and pending["status"] == "pending"
    monkeypatch.undo()
    barrier = Barrier(2)

    def answer_once() -> str:
        connection = database.connect()
        try:
            barrier.wait()
            return (
                TargetedPracticeProgressionService(connection)
                .answer(
                    course_id="course-calculus",
                    session_id=session_id,
                    run_id=str(begun.run["id"]),
                    expected_revision=int(begun.session["revision"]),
                    idempotency_key="practice-answer-concurrent-001",
                    response=answer,
                    now=NOW,
                )
                .outcome
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: answer_once(), range(2)))
    with database.connection() as connection:
        counts = connection.execute(
            """SELECT (SELECT COUNT(*) FROM assessment_attempts at
                         JOIN study_practice_runs r ON r.attempt_id = at.id),
                      (SELECT COUNT(*) FROM mastery_events me
                         JOIN study_practice_runs r ON r.mastery_event_id = me.id)"""
        ).fetchone()
    assert sorted(outcomes) == ["applied", "replayed"]
    assert tuple(counts) == (1, 1)


def test_unit_advance_failure_rolls_back_the_entire_practice_observation(
    tmp_path, monkeypatch
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        answer = _hidden_answer(
            connection, _practice_item_id(connection, str(begun.run["id"]))
        )
        mastery_before = tuple(
            connection.execute(
                "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
            ).fetchone()
        )
        monkeypatch.setattr(
            StudyRepository,
            "advance_current_unit",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("forced unit advance fault")
            ),
        )
        with pytest.raises(RuntimeError, match="forced unit advance fault"):
            TargetedPracticeProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="practice-answer-advance-fault-001",
                response=answer,
                now=NOW,
            )
        run = connection.execute(
            "SELECT status, attempt_id FROM study_practice_runs WHERE id = ?",
            (begun.run["id"],),
        ).fetchone()
        session = connection.execute(
            "SELECT status, current_unit_id, revision FROM study_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        units = connection.execute(
            """SELECT u.status FROM study_units u
               JOIN study_plan_versions p ON p.id = u.plan_version_id
               WHERE p.session_id = ? ORDER BY u.ordinal""",
            (session_id,),
        ).fetchall()
        mastery_after = tuple(
            connection.execute(
                "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
            ).fetchone()
        )
        practice_attempts = connection.execute(
            """SELECT COUNT(*) FROM assessment_attempts at
               JOIN study_practice_runs r ON r.attempt_id = at.id"""
        ).fetchone()[0]

    assert tuple(run) == ("pending", None)
    assert session["status"] == "practicing"
    assert session["revision"] == begun.session["revision"]
    assert [row["status"] for row in units] == ["active", "locked"]
    assert mastery_after == mastery_before
    assert practice_attempts == 0


@pytest.mark.parametrize("damage", ["ordinal_gap", "successor_ready"])
def test_damaged_successor_fails_closed_without_partial_practice_writes(
    tmp_path, damage
) -> None:
    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        successor = connection.execute(
            """SELECT u.id FROM study_units u
               JOIN study_plan_versions p ON p.id = u.plan_version_id
               WHERE p.session_id = ? ORDER BY u.ordinal LIMIT 1 OFFSET 1""",
            (session_id,),
        ).fetchone()
        assert successor is not None
        if damage == "ordinal_gap":
            connection.execute(
                "UPDATE study_units SET ordinal = 2 WHERE id = ?", (successor["id"],)
            )
        else:
            connection.execute(
                "UPDATE study_units SET status = 'ready' WHERE id = ?",
                (successor["id"],),
            )
        connection.commit()
        answer = _hidden_answer(
            connection, _practice_item_id(connection, str(begun.run["id"]))
        )
        with pytest.raises(RuntimeError):
            TargetedPracticeProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=session_id,
                run_id=str(begun.run["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key=f"practice-answer-damaged-{damage}-001",
                response=answer,
                now=NOW,
            )
        run = connection.execute(
            "SELECT status, attempt_id FROM study_practice_runs WHERE id = ?",
            (begun.run["id"],),
        ).fetchone()
        session = connection.execute(
            "SELECT status, current_unit_id FROM study_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    assert tuple(run) == ("pending", None)
    assert session["status"] == "practicing"
    assert session["current_unit_id"] == begun.current_unit["id"]


def test_025_seals_answered_practice_ledger_edges_and_event_evidence(tmp_path) -> None:
    """A completed practice run cannot be quietly reparented or rewritten."""

    database = _database(tmp_path)
    session_id, begun = _begin(database)
    with database.connection() as connection:
        run_id = str(begun.run["id"])
        answer = _hidden_answer(connection, _practice_item_id(connection, run_id))
        TargetedPracticeProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=run_id,
            expected_revision=int(begun.session["revision"]),
            idempotency_key="practice-answer-ledger-seal-001",
            response=answer,
            now=NOW,
        )
        graph = connection.execute(
            """SELECT r.unit_id, r.assessment_id, r.item_id, r.checkpoint_id,
                      r.attempt_id, r.evaluation_id, r.mastery_evidence_id,
                      r.mastery_event_id
               FROM study_practice_runs r WHERE r.id = ?""",
            (run_id,),
        ).fetchone()
        assert graph is not None
        connection.commit()

        tamper_statements = (
            (
                "UPDATE assessment_items SET answer_key_json = '[\"tampered\"]' "
                "WHERE id = ?",
                (graph["item_id"],),
                "practice item is immutable",
            ),
            (
                "UPDATE assessment_items SET prompt = 'tampered' WHERE id = ?",
                (graph["item_id"],),
                "practice item is immutable",
            ),
            (
                "UPDATE study_units SET source_chunk_ids_json = '[\"tampered\"]' "
                "WHERE id = ?",
                (graph["unit_id"],),
                "practice unit semantics are immutable",
            ),
            (
                "UPDATE study_units SET content = 'tampered' WHERE id = ?",
                (graph["unit_id"],),
                "practice unit semantics are immutable",
            ),
            (
                "UPDATE assessment_attempts SET answer_json = '[\"tampered\"]' "
                "WHERE id = ?",
                (graph["attempt_id"],),
                "practice attempt is immutable",
            ),
            (
                "UPDATE answer_evaluations SET score = 0 WHERE id = ?",
                (graph["evaluation_id"],),
                "practice evaluation is immutable",
            ),
            (
                "UPDATE mastery_evidence SET weight = 0 WHERE id = ?",
                (graph["mastery_evidence_id"],),
                "practice evidence is immutable",
            ),
            (
                "UPDATE mastery_events SET probability_after = 0 WHERE id = ?",
                (graph["mastery_event_id"],),
                "practice mastery event is immutable",
            ),
        )
        for statement, params, trigger in tamper_statements:
            with pytest.raises(sqlite3.IntegrityError, match=trigger):
                connection.execute(statement, params)
            connection.rollback()

        with pytest.raises(
            sqlite3.IntegrityError,
            match="practice attempt already has mastery evidence",
        ):
            connection.execute(
                """INSERT INTO mastery_evidence
                    (id, concept_id, attempt_id, session_id, evidence_type, correctness,
                     independence, hint_level, confidence_calibration, weight,
                     idempotency_key, created_at)
                    SELECT 'duplicate-practice-evidence', concept_id, attempt_id,
                           session_id, evidence_type, correctness, independence,
                           hint_level, confidence_calibration, weight,
                           'duplicate-practice-evidence-key', created_at
                    FROM mastery_evidence WHERE id = ?""",
                (graph["mastery_evidence_id"],),
            )
        connection.rollback()

        for statement in (
            "INSERT INTO mastery_event_evidence (event_id, evidence_id) VALUES (?, ?)",
            "UPDATE mastery_event_evidence SET event_id = event_id "
            "WHERE event_id = ? AND evidence_id = ?",
            "DELETE FROM mastery_event_evidence WHERE event_id = ? AND evidence_id = ?",
        ):
            with pytest.raises(
                sqlite3.IntegrityError,
                match="practice mastery-event evidence is immutable",
            ):
                connection.execute(
                    statement,
                    (graph["mastery_event_id"], graph["mastery_evidence_id"]),
                )
            connection.rollback()

        assert (
            connection.execute(
                "SELECT status FROM study_practice_runs WHERE id = ?", (run_id,)
            ).fetchone()["status"]
            == "answered"
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_025_rejects_pending_practice_cancellation_and_checkpoint_bypass(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _, begun = _begin(database)
    with database.connection() as connection:
        run_id = str(begun.run["id"])
        checkpoint_id = str(begun.checkpoint["id"])
        with pytest.raises(
            sqlite3.IntegrityError, match="practice cancellation is invalid"
        ):
            connection.execute(
                """UPDATE study_practice_runs
                   SET status = 'cancelled', cancelled_at = ?,
                       cancellation_reason = 'session_cancelled'
                   WHERE id = ?""",
                (NOW.isoformat(), run_id),
            )
        connection.rollback()
        with pytest.raises(
            sqlite3.IntegrityError, match="practice checkpoint is immutable"
        ):
            connection.execute(
                "UPDATE study_checkpoints SET status = 'skipped' WHERE id = ?",
                (checkpoint_id,),
            )
        connection.rollback()

        assert (
            connection.execute(
                "SELECT status FROM study_practice_runs WHERE id = ?", (run_id,)
            ).fetchone()["status"]
            == "pending"
        )
        assert (
            connection.execute(
                "SELECT status FROM study_checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()["status"]
            == "pending"
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
