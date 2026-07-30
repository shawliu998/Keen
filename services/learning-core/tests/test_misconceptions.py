from __future__ import annotations

import sqlite3

import pytest

from app.database import Database
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.misconception_repository import MisconceptionRepository


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "misconceptions.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def test_misconception_evidence_is_traceable_and_idempotent(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        mastery = MasteryRepository(connection)
        mastery.record_evidence(
            evidence_id="mastery-error",
            concept_id="concept-chain-rule",
            evidence_type="quiz",
            correctness=0.0,
            independence=1.0,
            hint_level=0,
            weight=1.0,
            idempotency_key="mastery-error-key",
        )
        repository = MisconceptionRepository(connection)
        misconception, created = repository.create_suspected(
            misconception_id="misconception-chain-order",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            label="Reverses chain-rule factors",
            description="Multiplies derivatives in the wrong nesting order.",
            confidence=0.45,
            idempotency_key="misconception-chain-order-key",
            seen_at="2026-07-16T00:00:00+00:00",
        )
        _, retried_created = repository.create_suspected(
            misconception_id="misconception-chain-order",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            label="Reverses chain-rule factors",
            description="Multiplies derivatives in the wrong nesting order.",
            confidence=0.45,
            idempotency_key="misconception-chain-order-key",
        )
        with pytest.raises(ValueError, match="idempotency key was reused"):
            repository.create_suspected(
                misconception_id="misconception-chain-order",
                course_id="course-calculus",
                concept_id="concept-chain-rule",
                label="Reverses chain-rule factors",
                description="conflicting retry",
                confidence=0.45,
                idempotency_key="misconception-chain-order-key",
            )
        evidence, evidence_created = repository.add_evidence(
            evidence_id="misconception-evidence-1",
            misconception_id=misconception["id"],
            mastery_evidence_id="mastery-error",
            evidence_type="repeated_error",
            confidence=0.7,
            details={"rule": "same_error_twice"},
            idempotency_key="misconception-evidence-key",
            created_at="2026-07-16T00:01:00+00:00",
        )
        retried_evidence, retried_evidence_created = repository.add_evidence(
            evidence_id="misconception-evidence-1",
            misconception_id=misconception["id"],
            mastery_evidence_id="mastery-error",
            evidence_type="repeated_error",
            confidence=0.7,
            details={"rule": "same_error_twice"},
            idempotency_key="misconception-evidence-key",
        )
        updated = repository.get(misconception["id"])

    assert created is True
    assert retried_created is False
    assert evidence_created is True
    assert retried_evidence_created is False
    assert retried_evidence == evidence
    assert evidence["details"] == {"rule": "same_error_twice"}
    assert updated["confidence"] == 0.7
    assert updated["revision"] == 1


def test_confirmation_requires_deterministic_rule_or_user_and_uses_revision(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = MisconceptionRepository(connection)
        misconception, _ = repository.create_suspected(
            misconception_id="misconception-1",
            course_id="course-calculus",
            concept_id="concept-limits",
            label="Treats a limit as substitution",
            description="",
            confidence=0.6,
            idempotency_key="misconception-1-key",
        )
        with pytest.raises(ValueError, match="trusted source"):
            repository.transition(
                misconception["id"],
                to_status="confirmed",
                expected_revision=0,
            )
        confirmed = repository.transition(
            misconception["id"],
            to_status="confirmed",
            expected_revision=0,
            confirmation_source="deterministic_rule",
        )
        with pytest.raises(ValueError, match="concurrently"):
            repository.transition(
                misconception["id"],
                to_status="resolved",
                expected_revision=0,
            )
        resolved = repository.transition(
            misconception["id"],
            to_status="resolved",
            expected_revision=1,
            changed_at="2026-07-16T02:00:00+00:00",
        )

    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmation_source"] == "deterministic_rule"
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] == "2026-07-16T02:00:00+00:00"


def test_misconception_rejects_concept_from_another_course(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = MisconceptionRepository(connection)
        with pytest.raises(sqlite3.IntegrityError, match="does not belong"):
            repository.create_suspected(
                misconception_id="bad-course-link",
                course_id="course-calculus",
                concept_id="concept-newton-2",
                label="Invalid relationship",
                description="",
                confidence=0.5,
                idempotency_key="bad-course-link-key",
            )
