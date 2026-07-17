"""Hard persistence contracts for the opening diagnostic transition.

These tests intentionally exercise the service against a real migrated SQLite
database: replay, atomicity, and trigger guarantees are part of the local
restart contract rather than router-only behavior.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from pathlib import Path
from threading import Barrier

import pytest

from app.repositories.mastery_repository import MasteryRepository
from app.repositories.study_repository import StudyRepository
from app.database import Database
from app.services.autonomous_study_session import AutonomousStudySessionService
from app.services.diagnostic_progression import (
    DiagnosticConflictError,
    DiagnosticProgressionService,
)
from test_autonomous_study_session import (
    NOW,
    _database,
    _indexed_source,
    _recommendation_task,
)


def _ready(database):
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        assert created.session is not None
        return str(created.session["id"]), int(created.session["revision"])


def test_begin_and_answer_replay_are_durable_and_payload_bound(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        service = DiagnosticProgressionService(connection)
        begun = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key="diagnostic-begin-replay",
            now=NOW,
        )
        begin_replay = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key="diagnostic-begin-replay",
            now=NOW,
        )
        with pytest.raises(DiagnosticConflictError):
            service.begin(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=revision + 1,
                idempotency_key="diagnostic-begin-replay",
                now=NOW,
            )
        with pytest.raises(DiagnosticConflictError):
            service.begin(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=revision,
                idempotency_key="diagnostic-begin-other",
                now=NOW,
            )
        answered = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(begun.checkpoint["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="diagnostic-answer-replay",
            response="I know the outer rule.",
            self_assessment="partial",
            now=NOW,
        )

    # A fresh connection is the important restart boundary for replay.
    with database.connection() as connection:
        replay = DiagnosticProgressionService(connection).answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(begun.checkpoint["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="diagnostic-answer-replay",
            response="I know the outer rule.",
            self_assessment="partial",
            now=NOW,
        )
        with pytest.raises(DiagnosticConflictError):
            DiagnosticProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=session_id,
                checkpoint_id=str(begun.checkpoint["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="diagnostic-answer-replay",
                response="Changed reflection.",
                self_assessment="partial",
                now=NOW,
            )
        counts = connection.execute(
            "SELECT (SELECT COUNT(*) FROM study_checkpoints), (SELECT COUNT(*) FROM mastery_evidence)"
        ).fetchone()

    assert begun.outcome == "applied"
    assert begin_replay.outcome == replay.outcome == "replayed"
    assert answered.outcome == "applied"
    assert tuple(counts) == (1, 1)


@pytest.mark.parametrize(
    "assessment, correctness", [("not_yet", 0.0), ("partial", 0.5), ("confident", 1.0)]
)
def test_diagnostic_reflections_never_change_scored_learning_state(
    tmp_path, assessment, correctness
) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        before = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        service = DiagnosticProgressionService(connection)
        begun = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key=f"diagnostic-begin-{assessment}-x",
            now=NOW,
        )
        service.answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(begun.checkpoint["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key=f"diagnostic-answer-{assessment}-x",
            response="Unscored reflection.",
            self_assessment=assessment,
            now=NOW,
        )
        after = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()
        evidence = connection.execute(
            "SELECT correctness, weight, evidence_type FROM mastery_evidence"
        ).fetchone()
        side_effects = connection.execute(
            "SELECT (SELECT COUNT(*) FROM mastery_events), (SELECT COUNT(*) FROM review_schedules), (SELECT COUNT(*) FROM misconceptions)"
        ).fetchone()

    assert before == after
    assert tuple(evidence) == (correctness, 0.0, "user_report")
    assert tuple(side_effects) == (0, 0, 0)


@pytest.mark.parametrize("fault", ["evidence", "checkpoint", "activate", "planning"])
def test_answer_rolls_back_every_intermediate_write_on_fault(
    tmp_path, monkeypatch, fault
) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        service = DiagnosticProgressionService(connection)
        begun = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key=f"diagnostic-fault-begin-{fault}",
            now=NOW,
        )
        if fault == "evidence":
            monkeypatch.setattr(
                MasteryRepository,
                "record_evidence",
                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fault")),
            )
        elif fault == "checkpoint":
            monkeypatch.setattr(
                StudyRepository,
                "answer_diagnostic_checkpoint",
                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fault")),
            )
        elif fault == "activate":
            monkeypatch.setattr(
                StudyRepository,
                "activate_first_unit",
                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fault")),
            )
        else:
            original = StudyRepository.transition_session
            calls = {"count": 0}

            def fail_planning(*args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("fault")
                return original(*args, **kwargs)

            monkeypatch.setattr(StudyRepository, "transition_session", fail_planning)
        with pytest.raises(RuntimeError, match="fault"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                checkpoint_id=str(begun.checkpoint["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key=f"diagnostic-fault-answer-{fault}",
                response="No partial durable write.",
                self_assessment="partial",
                now=NOW,
            )
        checkpoint = connection.execute(
            "SELECT status, response, mastery_evidence_id FROM study_checkpoints WHERE id = ?",
            (begun.checkpoint["id"],),
        ).fetchone()
        session = connection.execute(
            "SELECT status, current_unit_id FROM study_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        assert tuple(checkpoint) == ("pending", None, None)
        assert tuple(session) == ("diagnosing", None)
        assert (
            connection.execute("SELECT COUNT(*) FROM mastery_evidence").fetchone()[0]
            == 0
        )


def test_simultaneous_begin_has_one_winner_and_one_replay(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    barrier = Barrier(2)

    def invoke() -> str:
        with database.connection() as connection:
            barrier.wait(timeout=5)
            return (
                DiagnosticProgressionService(connection)
                .begin(
                    course_id="course-calculus",
                    session_id=session_id,
                    expected_revision=revision,
                    idempotency_key="diagnostic-concurrent-key",
                    now=NOW,
                )
                .outcome
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: invoke(), range(2)))
    with database.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM study_checkpoints WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
    assert sorted(outcomes) == ["applied", "replayed"]
    assert count == 1


def test_simultaneous_answer_has_one_apply_one_replay_and_one_event(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        begun = DiagnosticProgressionService(connection).begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key="diagnostic-concurrent-answer-begin",
            now=NOW,
        )
    barrier = Barrier(2)

    def invoke() -> str:
        with database.connection() as connection:
            barrier.wait(timeout=5)
            return (
                DiagnosticProgressionService(connection)
                .answer(
                    course_id="course-calculus",
                    session_id=session_id,
                    checkpoint_id=str(begun.checkpoint["id"]),
                    expected_revision=int(begun.session["revision"]),
                    idempotency_key="diagnostic-concurrent-answer-key",
                    response="Same reflection.",
                    self_assessment="partial",
                    now=NOW,
                )
                .outcome
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: invoke(), range(2)))
    with database.connection() as connection:
        counts = connection.execute(
            "SELECT (SELECT COUNT(*) FROM mastery_evidence), "
            "(SELECT COUNT(*) FROM study_session_events WHERE session_id = ? AND event_type = 'checkpoint_answered')",
            (session_id,),
        ).fetchone()
    assert sorted(outcomes) == ["applied", "replayed"]
    assert tuple(counts) == (1, 1)


def test_final_studying_transition_fault_rolls_back_activation(
    tmp_path, monkeypatch
) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        service = DiagnosticProgressionService(connection)
        begun = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key="diagnostic-final-transition-begin",
            now=NOW,
        )
        original = StudyRepository.transition_session
        calls = {"count": 0}

        def fail_final_transition(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("final transition fault")
            return original(*args, **kwargs)

        monkeypatch.setattr(
            StudyRepository, "transition_session", fail_final_transition
        )
        with pytest.raises(RuntimeError, match="final transition fault"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                checkpoint_id=str(begun.checkpoint["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="diagnostic-final-transition-answer",
                response="No partial activation.",
                self_assessment="partial",
                now=NOW,
            )
        unit = connection.execute(
            "SELECT u.status FROM study_units u JOIN study_plan_versions p ON p.id = u.plan_version_id "
            "WHERE p.session_id = ? ORDER BY u.ordinal LIMIT 1",
            (session_id,),
        ).fetchone()
        checkpoint = connection.execute(
            "SELECT status, mastery_evidence_id FROM study_checkpoints WHERE id = ?",
            (begun.checkpoint["id"],),
        ).fetchone()
    assert unit["status"] == "ready"
    assert tuple(checkpoint) == ("pending", None)


def test_migration_023_preserves_legacy_answered_diagnostic_and_database_health(
    tmp_path,
) -> None:
    path = tmp_path / "schema-22.sqlite3"
    database = Database(path)
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for version in range(1, 23):
            script = next(migrations.glob(f"{version:03d}_*.sql")).read_text(
                encoding="utf-8"
            )
            connection.executescript(script)
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.commit()
    database.seed_demo()
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        assert created.plan is not None and created.session is not None
        connection.execute(
            "INSERT INTO study_checkpoints (id, session_id, unit_id, kind, prompt, response, status, created_at, answered_at) "
            "VALUES ('legacy-answered-diagnostic', ?, ?, 'diagnostic', 'Legacy prompt', 'Legacy answer', 'answered', ?, ?)",
            (
                created.session["id"],
                created.plan["units"][0]["id"],
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
        connection.commit()
    assert database.migrate() == [23, 24]
    assert database.migrate() == []
    with database.connection() as connection:
        legacy = connection.execute(
            "SELECT response, diagnostic_begin_idempotency_key, diagnostic_answer_idempotency_key, mastery_evidence_id "
            "FROM study_checkpoints WHERE id = 'legacy-answered-diagnostic'"
        ).fetchone()
        quick_check = [row[0] for row in connection.execute("PRAGMA quick_check")]
        foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
    assert tuple(legacy) == ("Legacy answer", None, None, None)
    assert quick_check == ["ok"]
    assert foreign_keys == []


def test_answered_diagnostic_freezes_unit_concepts_and_revalidates_evidence(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        service = DiagnosticProgressionService(connection)
        begun = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key="diagnostic-freeze-begin",
            now=NOW,
        )
        answered = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(begun.checkpoint["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="diagnostic-freeze-answer",
            response="A durable unscored reflection.",
            self_assessment="partial",
            now=NOW,
        )
        unit_id = str(answered.current_unit["id"])
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE study_units SET concept_ids_json = '[\"concept-limits\"]' WHERE id = ?",
                (unit_id,),
            )
        connection.rollback()

        connection.execute(
            "DROP TRIGGER study_units_answered_diagnostic_concepts_immutable"
        )
        connection.execute(
            "UPDATE study_units SET concept_id = 'concept-limits', concept_ids_json = '[\"concept-limits\"]' WHERE id = ?",
            (unit_id,),
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="evidence relationship"):
            service.get(course_id="course-calculus", session_id=session_id)
        with pytest.raises(RuntimeError, match="evidence relationship"):
            service.answer(
                course_id="course-calculus",
                session_id=session_id,
                checkpoint_id=str(begun.checkpoint["id"]),
                expected_revision=int(begun.session["revision"]),
                idempotency_key="diagnostic-freeze-answer",
                response="A durable unscored reflection.",
                self_assessment="partial",
                now=NOW,
            )


@pytest.mark.parametrize(
    ("stage", "expected_outcome"),
    [
        ("goal_confirmation", "not_started"),
        ("diagnosing", "pending"),
        ("studying", "answered"),
    ],
)
def test_get_restores_paused_diagnostic_from_resume_stage(
    tmp_path, stage: str, expected_outcome: str
) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        service = DiagnosticProgressionService(connection)
        current_revision = revision
        if stage in {"diagnosing", "studying"}:
            begun = service.begin(
                course_id="course-calculus",
                session_id=session_id,
                expected_revision=revision,
                idempotency_key=f"paused-{stage}-begin",
                now=NOW,
            )
            current_revision = int(begun.session["revision"])
            if stage == "studying":
                answered = service.answer(
                    course_id="course-calculus",
                    session_id=session_id,
                    checkpoint_id=str(begun.checkpoint["id"]),
                    expected_revision=current_revision,
                    idempotency_key="paused-studying-answer",
                    response="Pause after this reflection.",
                    self_assessment="partial",
                    now=NOW,
                )
                current_revision = int(answered.session["revision"])
        paused = StudyRepository(connection).transition_session(
            session_id,
            status="paused",
            expected_revision=current_revision,
            updated_at=NOW.isoformat(),
        )
        restored = service.get(course_id="course-calculus", session_id=session_id)

    assert paused["resume_from_status"] == stage
    assert restored.outcome == expected_outcome
    assert restored.session["status"] == "paused"
    if expected_outcome == "not_started":
        assert restored.checkpoint is restored.current_unit is None
    elif expected_outcome == "pending":
        assert restored.checkpoint["status"] == "pending"
        assert restored.current_unit is None
    else:
        assert restored.checkpoint["status"] == "answered"
        assert restored.current_unit["status"] == "active"


def test_clear_current_unit_cannot_commit_a_half_transition(tmp_path) -> None:
    database = _database(tmp_path)
    session_id, revision = _ready(database)
    with database.connection() as connection:
        service = DiagnosticProgressionService(connection)
        begun = service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key="clear-current-begin",
            now=NOW,
        )
        answered = service.answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(begun.checkpoint["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="clear-current-answer",
            response="Keep this transition atomic.",
            self_assessment="partial",
            now=NOW,
        )
        with pytest.raises(ValueError, match="commit=False"):
            StudyRepository(connection).clear_current_unit(
                session_id=session_id,
                expected_revision=int(answered.session["revision"]),
            )
        persisted = StudyRepository(connection).get_session(session_id)

    assert persisted["current_unit_id"] == answered.current_unit["id"]
    assert persisted["revision"] == answered.session["revision"]
