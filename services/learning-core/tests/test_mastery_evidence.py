from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import Database
from app.repositories.mastery_repository import MasteryRepository


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "mastery-evidence.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def test_mastery_event_is_traceable_and_idempotent(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = MasteryRepository(connection)
        evidence, created = repository.record_evidence(
            evidence_id="evidence-1",
            concept_id="concept-chain-rule",
            evidence_type="quiz",
            correctness=1.0,
            independence=0.8,
            hint_level=1,
            confidence_calibration=0.9,
            weight=0.75,
            idempotency_key="attempt-1:evidence",
            created_at="2026-07-16T00:00:00+00:00",
        )
        retried_evidence, retried_created = repository.record_evidence(
            evidence_id="evidence-1",
            concept_id="concept-chain-rule",
            evidence_type="quiz",
            correctness=1.0,
            independence=0.8,
            hint_level=1,
            confidence_calibration=0.9,
            weight=0.75,
            idempotency_key="attempt-1:evidence",
        )

        event, event_created = repository.apply_event(
            concept_id="concept-chain-rule",
            correct=True,
            probability_before=0.42,
            probability_after=0.61,
            algorithm="weighted_bkt",
            algorithm_version="1.0.0",
            evidence_ids=["evidence-1"],
            idempotency_key="attempt-1:mastery",
            observed_at="2026-07-16T00:01:00+00:00",
        )
        retried_event, retried_event_created = repository.apply_event(
            concept_id="concept-chain-rule",
            correct=True,
            probability_before=0.42,
            probability_after=0.61,
            algorithm="weighted_bkt",
            algorithm_version="1.0.0",
            evidence_ids=["evidence-1"],
            idempotency_key="attempt-1:mastery",
        )
        mastery = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = ?",
            ("concept-chain-rule",),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM mastery_events WHERE idempotency_key IS NOT NULL"
        ).fetchone()[0]

    assert created is True
    assert retried_created is False
    assert retried_evidence == evidence
    assert event_created is True
    assert retried_event_created is False
    assert retried_event == event
    assert event["evidence_ids"] == ["evidence-1"]
    assert event["algorithm"] == "weighted_bkt"
    assert mastery["probability"] == 0.61
    assert mastery["attempts"] == 3
    assert event_count == 1


def test_mastery_event_rejects_evidence_from_another_concept_and_rolls_back(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = MasteryRepository(connection)
        repository.record_evidence(
            evidence_id="limits-evidence",
            concept_id="concept-limits",
            evidence_type="manual",
            correctness=0.0,
            independence=1.0,
            hint_level=0,
            weight=1.0,
            idempotency_key="limits-evidence-key",
        )

        with pytest.raises(ValueError, match="missing or mismatched"):
            repository.apply_event(
                concept_id="concept-chain-rule",
                correct=False,
                probability_before=0.42,
                probability_after=0.3,
                algorithm="weighted_bkt",
                algorithm_version="1.0.0",
                evidence_ids=["limits-evidence"],
                idempotency_key="mismatched-event",
            )

        mastery = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = ?",
            ("concept-chain-rule",),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM mastery_events WHERE idempotency_key = ?",
            ("mismatched-event",),
        ).fetchone()[0]

    assert dict(mastery) == {"probability": 0.42, "attempts": 2}
    assert event_count == 0


def test_zero_weight_user_report_is_audited_without_changing_mastery(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = MasteryRepository(connection)
        evidence, created = repository.record_evidence(
            evidence_id="user-report-1",
            concept_id="concept-chain-rule",
            evidence_type="user_report",
            correctness=1.0,
            independence=1.0,
            hint_level=0,
            weight=0.0,
            idempotency_key="user-report-1-key",
        )
        mastery = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = ?",
            ("concept-chain-rule",),
        ).fetchone()

    assert created is True
    assert evidence["weight"] == 0.0
    assert dict(mastery) == {"probability": 0.42, "attempts": 2}


def test_mastery_evidence_cannot_be_consumed_by_two_events(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = MasteryRepository(connection)
        repository.record_evidence(
            evidence_id="single-use-evidence",
            concept_id="concept-chain-rule",
            evidence_type="quiz",
            correctness=1.0,
            independence=1.0,
            hint_level=0,
            weight=1.0,
            idempotency_key="single-use-evidence-key",
        )
        repository.apply_event(
            concept_id="concept-chain-rule",
            correct=True,
            probability_before=0.42,
            probability_after=0.61,
            algorithm="weighted_bkt",
            algorithm_version="1.0.0",
            evidence_ids=["single-use-evidence"],
            idempotency_key="first-event-key",
        )
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"):
            repository.apply_event(
                concept_id="concept-chain-rule",
                correct=True,
                probability_before=0.61,
                probability_after=0.7,
                algorithm="weighted_bkt",
                algorithm_version="1.0.0",
                evidence_ids=["single-use-evidence"],
                idempotency_key="second-event-key",
            )
        mastery = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = ?",
            ("concept-chain-rule",),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM mastery_events WHERE idempotency_key IS NOT NULL"
        ).fetchone()[0]

    assert dict(mastery) == {"probability": 0.61, "attempts": 3}
    assert event_count == 1


def test_013_upgrades_legacy_mastery_events_without_data_loss(tmp_path):
    database = Database(tmp_path / "legacy-mastery.sqlite3")
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
            """
            INSERT INTO courses VALUES ('legacy-course', 'Legacy', '', '2026-07-01')
            """
        )
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name)
            VALUES ('legacy-concept', 'legacy-course', 'Legacy concept')
            """
        )
        connection.execute(
            """
            INSERT INTO mastery_events (
                concept_id, correct, probability_before,
                probability_after, observed_at
            ) VALUES ('legacy-concept', 1, 0.2, 0.5, '2026-07-02')
            """
        )
        connection.commit()

    assert 13 in database.migrate()
    with database.connection() as connection:
        legacy = connection.execute(
            "SELECT * FROM mastery_events WHERE concept_id = 'legacy-concept'"
        ).fetchone()

    assert legacy["correct"] == 1
    assert legacy["probability_before"] == 0.2
    assert legacy["algorithm"] == "legacy_bkt"
    assert legacy["algorithm_version"] == "1"
    assert legacy["evidence_ids_json"] == "[]"
    assert legacy["idempotency_key"] is None
