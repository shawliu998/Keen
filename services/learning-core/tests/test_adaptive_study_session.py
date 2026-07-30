"""Focused contracts for the persisted adaptive Study Session branch."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.repositories.study_repository import StudyRepository
from app.services.active_recall_progression import ActiveRecallProgressionService
from app.services.adaptive_study_session import (
    ADAPTIVE_SESSION_POLICY_VERSION,
    AdaptiveStudyConflictError,
    AdaptiveStudySessionService,
)
from app.services.autonomous_study_session import AutonomousStudySessionService
from app.services.diagnostic_progression import DiagnosticProgressionService
from app.services.study_session_control import StudySessionControlService
from app.services.targeted_practice_progression import (
    TargetedPracticeConflictError,
    TargetedPracticeProgressionService,
)
from conftest import TOKEN
from test_autonomous_study_session import (
    NOW,
    _database,
    _indexed_source,
    _recommendation_task,
)


AUTH = {"Authorization": f"Bearer {TOKEN}"}
COURSE_ID = "course-calculus"


def _pending_recall(database):
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id=COURSE_ID, task_id="autonomous-task", now=NOW
        )
        assert created.session is not None
        session_id = str(created.session["id"])
        diagnostic = DiagnosticProgressionService(connection).begin(
            course_id=COURSE_ID,
            session_id=session_id,
            expected_revision=int(created.session["revision"]),
            idempotency_key="adaptive-diagnostic-begin-001",
            now=NOW,
        )
        studying = DiagnosticProgressionService(connection).answer(
            course_id=COURSE_ID,
            session_id=session_id,
            checkpoint_id=str(diagnostic.checkpoint["id"]),
            expected_revision=int(diagnostic.session["revision"]),
            idempotency_key="adaptive-diagnostic-answer-001",
            response="Ready for source-bounded recall.",
            self_assessment="partial",
            now=NOW,
        )
        recall = ActiveRecallProgressionService(connection).begin(
            course_id=COURSE_ID,
            session_id=session_id,
            expected_revision=int(studying.session["revision"]),
            idempotency_key="adaptive-active-recall-begin-001",
            now=NOW,
        )
        return session_id, recall


def _answer_recall(database, *, response: str):
    session_id, recall = _pending_recall(database)
    with database.connection() as connection:
        answered = ActiveRecallProgressionService(connection).answer(
            course_id=COURSE_ID,
            session_id=session_id,
            run_id=str(recall.run["id"]),
            expected_revision=int(recall.session["revision"]),
            idempotency_key="adaptive-active-recall-answer-001",
            response=response,
            now=NOW,
        )
    return session_id, answered


@pytest.mark.parametrize(
    ("response", "kind", "reason"),
    [
        ("chain rule", "practice", "active_recall_correct"),
        ("definitely wrong", "remediate", "active_recall_incorrect"),
    ],
)
def test_recall_result_creates_one_durable_versioned_action(
    tmp_path, response: str, kind: str, reason: str
) -> None:
    database = _database(tmp_path)
    session_id, answered = _answer_recall(database, response=response)

    with database.connection() as reopened:
        state = AdaptiveStudySessionService(reopened).get(
            course_id=COURSE_ID, session_id=session_id
        )
        run_id = reopened.execute(
            "SELECT id FROM study_active_recall_runs WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        replay = ActiveRecallProgressionService(reopened).answer(
            course_id=COURSE_ID,
            session_id=session_id,
            run_id=str(run_id),
            expected_revision=int(answered.session["revision"]) - 1,
            idempotency_key="adaptive-active-recall-answer-001",
            response=response,
            now=NOW + timedelta(minutes=1),
        )
        rows = reopened.execute(
            "SELECT * FROM study_adaptive_actions WHERE session_id = ?", (session_id,)
        ).fetchall()
        recall_evidence = reopened.execute(
            """SELECT COUNT(*) FROM mastery_evidence
               WHERE session_id = ? AND evidence_type = 'active_recall'""",
            (session_id,),
        ).fetchone()[0]

    assert answered.session["status"] == "practicing"
    assert replay.outcome == "replayed"
    assert state.state == "action_required"
    assert state.action is not None
    assert state.action["kind"] == kind
    assert state.action["reason_code"] == reason
    assert state.action["policy_version"] == ADAPTIVE_SESSION_POLICY_VERSION
    assert state.action["revision"] == 0
    assert len(rows) == recall_evidence == 1


def test_remediation_gates_practice_then_completes_without_learning_mutation(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    session_id, answered = _answer_recall(database, response="definitely wrong")
    with database.connection() as connection:
        state = AdaptiveStudySessionService(connection).get(
            course_id=COURSE_ID, session_id=session_id
        )
        assert state.action is not None
        action_id = str(state.action["id"])
        before = tuple(
            connection.execute(
                """SELECT
                    (SELECT COUNT(*) FROM study_sessions),
                    (SELECT COUNT(*) FROM study_plan_versions),
                    (SELECT COUNT(*) FROM study_units),
                    (SELECT COUNT(*) FROM mastery_evidence),
                    (SELECT COUNT(*) FROM mastery_events),
                    (SELECT COUNT(*) FROM review_items),
                    (SELECT COUNT(*) FROM study_tasks)"""
            ).fetchone()
        )
        with pytest.raises(TargetedPracticeConflictError, match="blocked"):
            TargetedPracticeProgressionService(connection).begin(
                course_id=COURSE_ID,
                session_id=session_id,
                expected_revision=int(answered.session["revision"]),
                idempotency_key="adaptive-practice-blocked-001",
                now=NOW,
            )
        completed = AdaptiveStudySessionService(connection).complete_remediation(
            course_id=COURSE_ID,
            session_id=session_id,
            action_id=action_id,
            expected_action_revision=0,
            idempotency_key="adaptive-remediation-complete-001",
            now=NOW,
        )
        after = tuple(
            connection.execute(
                """SELECT
                    (SELECT COUNT(*) FROM study_sessions),
                    (SELECT COUNT(*) FROM study_plan_versions),
                    (SELECT COUNT(*) FROM study_units),
                    (SELECT COUNT(*) FROM mastery_evidence),
                    (SELECT COUNT(*) FROM mastery_events),
                    (SELECT COUNT(*) FROM review_items),
                    (SELECT COUNT(*) FROM study_tasks)"""
            ).fetchone()
        )

    with database.connection() as reopened:
        replay = AdaptiveStudySessionService(reopened).complete_remediation(
            course_id=COURSE_ID,
            session_id=session_id,
            action_id=action_id,
            expected_action_revision=0,
            idempotency_key="adaptive-remediation-complete-001",
            now=NOW + timedelta(minutes=1),
        )
        with pytest.raises(AdaptiveStudyConflictError):
            AdaptiveStudySessionService(reopened).complete_remediation(
                course_id=COURSE_ID,
                session_id=session_id,
                action_id=action_id,
                expected_action_revision=1,
                idempotency_key="adaptive-remediation-stale-002",
                now=NOW,
            )
        practice = TargetedPracticeProgressionService(reopened).begin(
            course_id=COURSE_ID,
            session_id=session_id,
            expected_revision=int(answered.session["revision"]),
            idempotency_key="adaptive-practice-after-remediation-001",
            now=NOW,
        )
        late_replay = AdaptiveStudySessionService(reopened).complete_remediation(
            course_id=COURSE_ID,
            session_id=session_id,
            action_id=action_id,
            expected_action_revision=0,
            idempotency_key="adaptive-remediation-complete-001",
            now=NOW + timedelta(minutes=2),
        )

    assert before == after
    assert completed.outcome == "applied"
    assert replay.outcome == "replayed"
    assert completed.completed_action["status"] == "completed"
    assert completed.current_action["kind"] == "practice"
    assert completed.current_action["status"] == "pending"
    assert replay.current_action == completed.current_action
    assert practice.outcome == "applied"
    assert late_replay.outcome == "replayed"
    assert late_replay.current_action["status"] == "completed"


def test_pending_action_survives_pause_reopen_and_terminalization(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, answered = _answer_recall(database, response="definitely wrong")
    with database.connection() as connection:
        paused = StudySessionControlService(connection).apply(
            command="pause",
            course_id=COURSE_ID,
            session_id=session_id,
            expected_revision=int(answered.session["revision"]),
            idempotency_key="adaptive-pause-session-001",
            now=NOW,
        )
    with database.connection() as reopened:
        state = AdaptiveStudySessionService(reopened).get(
            course_id=COURSE_ID, session_id=session_id
        )
        assert state.action is not None
        assert state.state == "paused"
        with pytest.raises(AdaptiveStudyConflictError, match="paused"):
            AdaptiveStudySessionService(reopened).complete_remediation(
                course_id=COURSE_ID,
                session_id=session_id,
                action_id=str(state.action["id"]),
                expected_action_revision=0,
                idempotency_key="adaptive-paused-complete-001",
                now=NOW,
            )
        resumed = StudySessionControlService(reopened).apply(
            command="resume",
            course_id=COURSE_ID,
            session_id=session_id,
            expected_revision=int(paused.session["revision"]),
            idempotency_key="adaptive-resume-session-001",
            now=NOW,
        )
        StudyRepository(reopened).transition_session(
            session_id,
            status="cancelled",
            expected_revision=int(resumed.session["revision"]),
            updated_at=NOW.isoformat(),
        )
        terminal = AdaptiveStudySessionService(reopened).get(
            course_id=COURSE_ID, session_id=session_id
        )
        stored_status = reopened.execute(
            "SELECT status FROM study_adaptive_actions WHERE id = ?",
            (state.action["id"],),
        ).fetchone()[0]

    assert terminal.state == "terminal"
    assert terminal.action is None
    assert stored_status == "cancelled"


def test_legacy_session_keeps_canonical_practice_behavior(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, recall = _pending_recall(database)
    with database.connection() as connection:
        # Model a row that existed before migration 028; the forward migration
        # leaves its policy NULL, while new production sessions are versioned.
        connection.execute("DROP TRIGGER study_sessions_adaptive_policy_immutable")
        connection.execute(
            "UPDATE study_sessions SET adaptive_policy_version = NULL WHERE id = ?",
            (session_id,),
        )
        connection.commit()
        answered = ActiveRecallProgressionService(connection).answer(
            course_id=COURSE_ID,
            session_id=session_id,
            run_id=str(recall.run["id"]),
            expected_revision=int(recall.session["revision"]),
            idempotency_key="legacy-active-recall-answer-001",
            response="definitely wrong",
            now=NOW,
        )
        state = AdaptiveStudySessionService(connection).get(
            course_id=COURSE_ID, session_id=session_id
        )
        practice = TargetedPracticeProgressionService(connection).begin(
            course_id=COURSE_ID,
            session_id=session_id,
            expected_revision=int(answered.session["revision"]),
            idempotency_key="legacy-practice-begin-001",
            now=NOW,
        )
        action_count = connection.execute(
            "SELECT COUNT(*) FROM study_adaptive_actions WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]

    assert state.state == "legacy_canonical"
    assert state.action is None
    assert action_count == 0
    assert practice.outcome == "applied"


def test_adaptive_http_contract_scope_replay_and_strict_body(
    client: TestClient,
) -> None:
    session_id, _ = _answer_recall(
        client.app.state.database, response="definitely wrong"
    )
    restored = client.get(
        f"/v1/study-sessions/{session_id}/adaptive-state",
        headers=AUTH,
        params={"course_id": COURSE_ID},
    )
    assert restored.status_code == 200
    body = restored.json()
    assert body["state"] == "action_required"
    assert body["action"]["kind"] == "remediate"
    request = {
        "course_id": COURSE_ID,
        "expected_action_revision": body["action"]["revision"],
        "idempotency_key": "adaptive-http-complete-001",
    }
    path = (
        f"/v1/study-sessions/{session_id}/adaptive-actions/"
        f"{body['action']['id']}/complete"
    )
    applied = client.post(path, headers=AUTH, json=request)
    replay = client.post(path, headers=AUTH, json=request)
    assert applied.status_code == replay.status_code == 200
    assert applied.json()["outcome"] == "applied"
    assert replay.json()["outcome"] == "replayed"
    assert applied.json()["current_action"]["kind"] == "practice"
    assert (
        client.post(path, headers=AUTH, json={**request, "extra": True}).status_code
        == 422
    )
    assert (
        client.get(
            f"/v1/study-sessions/{session_id}/adaptive-state",
            headers=AUTH,
            params={"course_id": "course-foreign"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/study-sessions/{session_id}/adaptive-state",
            params={"course_id": COURSE_ID},
        ).status_code
        == 401
    )
