"""SQLite contracts for the immutable active-recall ledger.

These tests intentionally avoid HTTP and build the published assessment graph
inside SQLite.  The answer key is used only to construct an internal test
fixture; no service result is inspected for it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import Database
from app.repositories.study_repository import StudyRepository
from app.services.diagnostic_progression import DiagnosticProgressionService
from test_autonomous_study_session import NOW, _database
from test_diagnostic_progression import _ready


def _pending_run(tmp_path) -> tuple[Database, dict[str, str]]:
    database = _database(tmp_path)
    with database.connection() as connection:
        session_id, revision = _ready(database)
        diagnostic = DiagnosticProgressionService(connection)
        begun = diagnostic.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=revision,
            idempotency_key="active-recall-fixture-diagnostic-begin",
            now=NOW,
        )
        studying = diagnostic.answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(begun.checkpoint["id"]),
            expected_revision=int(begun.session["revision"]),
            idempotency_key="active-recall-fixture-diagnostic-answer",
            response="Ready for a source-bounded item.",
            self_assessment="partial",
            now=NOW,
        )
        repository = StudyRepository(connection)
        checkpoint_state = repository.transition_session(
            session_id,
            status="checkpoint",
            expected_revision=int(studying.session["revision"]),
            updated_at=NOW.isoformat(),
        )
        repository.transition_session(
            session_id,
            status="active_recall",
            expected_revision=int(checkpoint_state["revision"]),
            updated_at=NOW.isoformat(),
        )
        unit = connection.execute(
            "SELECT * FROM study_units WHERE id = ?", (studying.current_unit["id"],)
        ).fetchone()
        assert unit is not None
        source_ids = str(unit["source_chunk_ids_json"])
        mastery = connection.execute(
            "SELECT attempts FROM mastery WHERE concept_id = ?", (unit["concept_id"],)
        ).fetchone()
        assert mastery is not None
        created_at = NOW.isoformat()
        connection.execute(
            """
            INSERT INTO assessments
                (id, course_id, session_id, title, purpose, status, revision,
                 created_at, updated_at, published_at)
            VALUES ('active-recall-assessment', 'course-calculus', ?, 'Recall',
                    'checkpoint', 'published', 1, ?, ?, ?)
            """,
            (session_id, created_at, created_at, created_at),
        )
        connection.execute(
            """
            INSERT INTO assessment_items
                (id, assessment_id, ordinal, concept_id, item_type, difficulty,
                 prompt, options_json, answer_key_json, rubric_json,
                 source_chunk_ids_json, max_score, created_at)
            VALUES ('active-recall-item', 'active-recall-assessment', 0,
                    ?, 'fill_blank', 'easy', 'The [...] differentiates composite functions.',
                    NULL, '{"accepted_answers":["chain rule"]}', NULL, ?, 1, ?)
            """,
            (unit["concept_id"], source_ids, created_at),
        )
        connection.execute(
            """
            INSERT INTO study_checkpoints
                (id, session_id, unit_id, kind, prompt, response, status,
                 created_at, answered_at)
            VALUES ('active-recall-checkpoint', ?, ?, 'active_recall',
                    'The [...] differentiates composite functions.', NULL, 'pending', ?, NULL)
            """,
            (session_id, unit["id"], created_at),
        )
        connection.execute(
            """
            INSERT INTO study_active_recall_runs
                (id, course_id, session_id, unit_id, checkpoint_id, assessment_id,
                 item_id, concept_id, mastery_attempts_before, source_chunk_ids_json, generator_version,
                 status, begin_idempotency_key, begin_payload_fingerprint, created_at)
            VALUES ('active-recall-run', 'course-calculus', ?, ?,
                    'active-recall-checkpoint', 'active-recall-assessment',
                    'active-recall-item', ?, ?, ?, 'source-cloze/1.0.0', 'pending',
                    'active-recall-fixture-begin', ?, ?)
            """,
            (
                session_id,
                unit["id"],
                unit["concept_id"],
                mastery["attempts"],
                source_ids,
                "a" * 64,
                created_at,
            ),
        )
        connection.commit()
        return database, {
            "session_id": session_id,
            "unit_id": str(unit["id"]),
            "concept_id": str(unit["concept_id"]),
        }


def _answer_run(
    connection: sqlite3.Connection,
    graph: dict[str, str],
    *,
    score: float = 1.0,
    finalize: bool = True,
) -> int:
    timestamp = NOW.isoformat()
    connection.execute(
        """
        UPDATE study_checkpoints
        SET response = 'Objective response recorded.', status = 'answered', answered_at = ?
        WHERE id = 'active-recall-checkpoint'
        """,
        (timestamp,),
    )
    connection.execute(
        """
        INSERT INTO assessment_attempts
            (id, assessment_id, item_id, session_id, status, idempotency_key,
             answer_json, confidence, total_score, max_score, started_at,
             submitted_at, graded_at, updated_at)
        VALUES ('active-recall-attempt', 'active-recall-assessment',
                'active-recall-item', ?, 'graded', 'active-recall-fixture-answer',
                '["chain rule"]', NULL, 1, 1, ?, ?, ?, ?)
        """,
        (graph["session_id"], timestamp, timestamp, timestamp, timestamp),
    )
    connection.execute(
        """
        INSERT INTO answer_evaluations
            (id, attempt_id, item_id, answer_json, raw_score, hint_penalty,
             final_score, is_correct, correctness, score, independence,
             rubric_breakdown_json, evaluation_source, feedback,
             evaluator_version, grader_version, created_at)
        VALUES ('active-recall-evaluation', 'active-recall-attempt',
                'active-recall-item', '["chain rule"]', ?, 0, ?, 1, 'correct',
                ?, 1, '{}', 'deterministic', '', 'objective/1', 'objective/1', ?)
            """,
        (score, score, score, timestamp),
    )
    connection.execute(
        """
        INSERT INTO mastery_evidence
            (id, concept_id, attempt_id, session_id, evidence_type, correctness,
             independence, hint_level, confidence_calibration, weight,
             idempotency_key, created_at)
        VALUES ('active-recall-evidence', ?, 'active-recall-attempt', ?,
                'active_recall', 1, 1, 0, NULL, 0.8,
                'active-recall-fixture-evidence', ?)
        """,
        (graph["concept_id"], graph["session_id"], timestamp),
    )
    mastery = connection.execute(
        "SELECT probability FROM mastery WHERE concept_id = ?", (graph["concept_id"],)
    ).fetchone()
    assert mastery is not None
    event = connection.execute(
        """
        INSERT INTO mastery_events
            (concept_id, correct, probability_before, probability_after,
             observed_at, algorithm, algorithm_version, evidence_ids_json,
             idempotency_key)
        VALUES (?, 1, ?, ?, ?, 'weighted_bkt', 'weighted-bkt/1.0.0',
                '["active-recall-evidence"]', 'active-recall-fixture-event')
        """,
        (
            graph["concept_id"],
            mastery["probability"],
            mastery["probability"],
            timestamp,
        ),
    )
    event_id = int(event.lastrowid)
    connection.execute(
        "INSERT INTO mastery_event_evidence (event_id, evidence_id) VALUES (?, 'active-recall-evidence')",
        (event_id,),
    )
    connection.execute(
        "UPDATE mastery SET attempts = attempts + 1, updated_at = ? WHERE concept_id = ?",
        (timestamp, graph["concept_id"]),
    )
    chain = connection.execute(
        """
        SELECT at.id FROM assessment_attempts at
        JOIN answer_evaluations ev ON ev.attempt_id = at.id AND ev.item_id = at.item_id
        JOIN mastery_evidence me ON me.attempt_id = at.id
        JOIN mastery_event_evidence mee ON mee.evidence_id = me.id
        JOIN mastery_events event ON event.id = mee.event_id
        JOIN study_checkpoints cp ON cp.id = 'active-recall-checkpoint'
        WHERE at.id = 'active-recall-attempt' AND at.assessment_id = 'active-recall-assessment'
          AND at.item_id = 'active-recall-item' AND at.session_id = ?
          AND at.status = 'graded' AND ev.id = 'active-recall-evaluation'
          AND ev.evaluation_source = 'deterministic'
          AND me.id = 'active-recall-evidence'
          AND me.session_id = ? AND me.concept_id = ?
          AND me.evidence_type = 'active_recall'
          AND event.id = ? AND event.concept_id = ?
          AND json_array_length(event.evidence_ids_json) = 1
          AND json_extract(event.evidence_ids_json, '$[0]') = me.id
          AND cp.status = 'answered' AND cp.response = 'Objective response recorded.'
          AND cp.answered_at = ?
        """,
        (
            graph["session_id"],
            graph["session_id"],
            graph["concept_id"],
            event_id,
            graph["concept_id"],
            timestamp,
        ),
    ).fetchone()
    assert chain is not None
    if not finalize:
        return event_id
    connection.execute(
        """
        UPDATE study_active_recall_runs
        SET status = 'answered', answer_idempotency_key = ?,
            answer_payload_fingerprint = ?, attempt_id = 'active-recall-attempt',
            evaluation_id = 'active-recall-evaluation',
            mastery_evidence_id = 'active-recall-evidence', mastery_event_id = ?,
            answered_at = ?
        WHERE id = 'active-recall-run'
        """,
        ("active-recall-fixture-answer", "b" * 64, event_id, timestamp),
    )
    session = connection.execute(
        "SELECT revision FROM study_sessions WHERE id = ?", (graph["session_id"],)
    ).fetchone()
    assert session is not None
    StudyRepository(connection).transition_session(
        graph["session_id"],
        status="practicing",
        expected_revision=int(session["revision"]),
        updated_at=NOW.isoformat(),
    )
    connection.commit()
    return event_id


def test_024_upgrades_22_and_23_databases_and_retains_database_health(tmp_path) -> None:
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    for version in (22, 23):
        database = Database(tmp_path / f"schema-{version}.sqlite3")
        with database.connection() as connection:
            connection.execute(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            for number in range(1, version + 1):
                connection.executescript(
                    next(migrations.glob(f"{number:03d}_*.sql")).read_text(
                        encoding="utf-8"
                    )
                )
                connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES (?)", (number,)
                )
            connection.commit()

        assert database.migrate() == list(range(version + 1, 26))
        assert database.migrate() == []
        with database.connection() as connection:
            assert [row[0] for row in connection.execute("PRAGMA quick_check")] == [
                "ok"
            ]
            assert list(connection.execute("PRAGMA foreign_key_check")) == []


def test_024_requires_a_complete_current_published_pending_graph(tmp_path) -> None:
    database, graph = _pending_run(tmp_path)
    with database.connection() as connection:
        row = connection.execute(
            "SELECT status, begin_idempotency_key FROM study_active_recall_runs"
        ).fetchone()
        assert tuple(row) == ("pending", "active-recall-fixture-begin")

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE study_active_recall_runs SET begin_idempotency_key = 'active-recall-fixture-begin' WHERE id = 'active-recall-run'"
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="sources"):
            connection.execute(
                """
                INSERT INTO study_active_recall_runs
                    (id, course_id, session_id, unit_id, checkpoint_id, assessment_id,
                     item_id, concept_id, mastery_attempts_before, source_chunk_ids_json, generator_version,
                     status, begin_idempotency_key, begin_payload_fingerprint, created_at)
                SELECT 'broken-run', course_id, session_id, unit_id, checkpoint_id,
                       assessment_id, item_id, concept_id, mastery_attempts_before, '["outside-source"]',
                       generator_version, status, 'active-recall-broken-begin',
                       begin_payload_fingerprint, created_at
                FROM study_active_recall_runs WHERE id = 'active-recall-run'
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="attempt session"):
            connection.execute(
                """
                INSERT INTO assessment_attempts
                    (id, assessment_id, item_id, session_id, status, idempotency_key,
                     answer_json, started_at, updated_at)
                VALUES ('wrong-session-attempt', 'active-recall-assessment',
                        'active-recall-item', NULL, 'in_progress',
                        'active-recall-wrong-session', '[]', ?, ?)
                """,
                (NOW.isoformat(), NOW.isoformat()),
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE study_active_recall_runs SET status = 'answered' WHERE id = 'active-recall-run'"
            )
        connection.rollback()

        assert (
            connection.execute(
                "SELECT status FROM study_active_recall_runs WHERE id = 'active-recall-run'"
            ).fetchone()[0]
            == "pending"
        )
        assert graph["unit_id"]


def test_024_rejects_a_non_binary_deterministic_scoring_chain(tmp_path) -> None:
    database, graph = _pending_run(tmp_path)
    with database.connection() as connection:
        event_id = _answer_run(connection, graph, score=0.5, finalize=False)
        with pytest.raises(sqlite3.IntegrityError, match="scoring chain"):
            connection.execute(
                """
                UPDATE study_active_recall_runs
                SET status = 'answered', answer_idempotency_key = ?,
                    answer_payload_fingerprint = ?, attempt_id = 'active-recall-attempt',
                    evaluation_id = 'active-recall-evaluation',
                    mastery_evidence_id = 'active-recall-evidence', mastery_event_id = ?,
                    answered_at = ?
                WHERE id = 'active-recall-run'
                """,
                ("active-recall-fixture-answer", "b" * 64, event_id, NOW.isoformat()),
            )


def test_024_rejects_mislabeled_or_miscounted_mastery_application(tmp_path) -> None:
    database, graph = _pending_run(tmp_path)
    with database.connection() as connection:
        event_id = _answer_run(connection, graph, finalize=False)
        connection.execute(
            "UPDATE mastery_events SET algorithm = 'llm_guess', algorithm_version = 'unknown' WHERE id = ?",
            (event_id,),
        )
        connection.execute(
            "UPDATE mastery SET attempts = 999 WHERE concept_id = ?",
            (graph["concept_id"],),
        )
        with pytest.raises(sqlite3.IntegrityError, match="scoring chain"):
            connection.execute(
                """
                UPDATE study_active_recall_runs
                SET status = 'answered', answer_idempotency_key = ?,
                    answer_payload_fingerprint = ?, attempt_id = 'active-recall-attempt',
                    evaluation_id = 'active-recall-evaluation',
                    mastery_evidence_id = 'active-recall-evidence', mastery_event_id = ?,
                    answered_at = ?
                WHERE id = 'active-recall-run'
                """,
                ("active-recall-fixture-answer", "b" * 64, event_id, NOW.isoformat()),
            )


def test_024_freezes_every_published_answered_ledger_edge(tmp_path) -> None:
    database, graph = _pending_run(tmp_path)
    with database.connection() as connection:
        _answer_run(connection, graph)
        connection.execute(
            "INSERT INTO courses (id, title, created_at) VALUES ('other-course', 'Other', ?)",
            (NOW.isoformat(),),
        )
        connection.commit()
        tamper_statements = (
            "UPDATE concepts SET course_id = 'other-course' WHERE id = '"
            + graph["concept_id"]
            + "'",
            "UPDATE assessments SET title = 'tampered' WHERE id = 'active-recall-assessment'",
            "UPDATE assessment_items SET prompt = 'tampered' WHERE id = 'active-recall-item'",
            "UPDATE study_units SET source_chunk_ids_json = '[\"tampered\"]' WHERE id = '"
            + graph["unit_id"]
            + "'",
            "UPDATE study_units SET content = 'tampered' WHERE id = '"
            + graph["unit_id"]
            + "'",
            "UPDATE study_checkpoints SET response = 'tampered' WHERE id = 'active-recall-checkpoint'",
            "UPDATE assessment_attempts SET answer_json = '[\"tampered\"]' WHERE id = 'active-recall-attempt'",
            "UPDATE answer_evaluations SET score = 0 WHERE id = 'active-recall-evaluation'",
            "UPDATE mastery_evidence SET weight = 0 WHERE id = 'active-recall-evidence'",
            "UPDATE mastery_events SET probability_after = 0 WHERE id = (SELECT mastery_event_id FROM study_active_recall_runs)",
            "UPDATE study_active_recall_runs SET generator_version = 'tampered' WHERE id = 'active-recall-run'",
            f"""INSERT INTO assessment_attempts
                (id, assessment_id, item_id, session_id, status, idempotency_key,
                 answer_json, started_at, updated_at)
                VALUES ('duplicate-active-recall-attempt', 'active-recall-assessment',
                        'active-recall-item', '{graph["session_id"]}', 'in_progress',
                        'duplicate-active-recall-attempt-key',
                        '\"duplicate\"', '2026-07-18T00:00:00+00:00',
                        '2026-07-18T00:00:00+00:00')""",
            """INSERT INTO mastery_evidence
                (id, concept_id, attempt_id, session_id, evidence_type, correctness,
                 independence, hint_level, confidence_calibration, weight,
                 idempotency_key, created_at)
                SELECT 'duplicate-active-recall-evidence', concept_id, attempt_id,
                       session_id, evidence_type, correctness, independence,
                       hint_level, confidence_calibration, weight,
                       'duplicate-active-recall-evidence-key', created_at
                FROM mastery_evidence WHERE id = 'active-recall-evidence'""",
        )
        for statement in tamper_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
            connection.rollback()

        assert (
            connection.execute(
                "SELECT status FROM study_active_recall_runs WHERE id = 'active-recall-run'"
            ).fetchone()[0]
            == "answered"
        )
