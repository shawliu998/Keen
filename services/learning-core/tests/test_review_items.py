from __future__ import annotations

import sqlite3

import pytest

from app.database import Database
from app.repositories.review_repository import ReviewRepository


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "reviews.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def _create_item(repository: ReviewRepository):
    return repository.create_item(
        item_id="review-chain-rule",
        course_id="course-calculus",
        concept_id="concept-chain-rule",
        item_type="free_recall",
        prompt="Explain the chain rule.",
        expected_answer={"required_terms": ["inner", "outer"]},
        source_type="manual",
        source_id=None,
        due_at="2026-07-16T08:00:00+00:00",
        scheduler_version="persistence-fixture-1",
        idempotency_key="review-chain-rule-key",
        created_at="2026-07-16T07:00:00+00:00",
    )


def test_review_item_and_fsrs_state_are_separate_and_idempotent(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = ReviewRepository(connection)
        item, created = _create_item(repository)
        retried, retried_created = _create_item(repository)
        attempt, attempt_created = repository.record_attempt(
            attempt_id="review-attempt-1",
            item_id=item["id"],
            rating="good",
            response={"text": "differentiate outer, then multiply by inner"},
            idempotency_key="review-attempt-1-key",
            expected_revision=0,
            difficulty=4.8,
            stability=3.2,
            due_at="2026-07-19T08:00:00+00:00",
            repetitions=1,
            lapses=0,
            state="review",
            scheduler_version="persistence-fixture-1",
            scheduler_state={"card_state": "review"},
            reviewed_at="2026-07-16T08:00:00+00:00",
        )
        retried_attempt, retried_attempt_created = repository.record_attempt(
            attempt_id="review-attempt-1",
            item_id=item["id"],
            rating="good",
            response={"text": "differentiate outer, then multiply by inner"},
            idempotency_key="review-attempt-1-key",
            expected_revision=0,
            difficulty=4.8,
            stability=3.2,
            due_at="2026-07-19T08:00:00+00:00",
            repetitions=1,
            lapses=0,
            state="review",
            scheduler_version="persistence-fixture-1",
            scheduler_state={"card_state": "review"},
        )
        post_review_retry, post_review_created = _create_item(repository)
        persisted = repository.get_item(item["id"])
        mastery = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = ?",
            ("concept-chain-rule",),
        ).fetchone()
        attempt_count = connection.execute(
            "SELECT COUNT(*) FROM review_attempts"
        ).fetchone()[0]

    assert created is True
    assert retried_created is False
    assert retried == item
    assert attempt_created is True
    assert retried_attempt_created is False
    assert retried_attempt == attempt
    assert post_review_created is False
    assert post_review_retry["id"] == item["id"]
    assert attempt["schedule_before"]["state"] == "new"
    assert attempt["schedule_after"]["state"] == "review"
    assert persisted["difficulty"] == 4.8
    assert persisted["stability"] == 3.2
    assert persisted["revision"] == 1
    assert dict(mastery) == {"probability": 0.42, "attempts": 2}
    assert attempt_count == 1


def test_review_attempt_rejects_stale_revision_without_partial_insert(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = ReviewRepository(connection)
        item, _ = _create_item(repository)
        connection.execute(
            "UPDATE review_schedules SET revision = 1 WHERE review_item_id = ?",
            (item["id"],),
        )
        connection.commit()

        with pytest.raises(ValueError, match="concurrently"):
            repository.record_attempt(
                attempt_id="stale-attempt",
                item_id=item["id"],
                rating="again",
                response={},
                idempotency_key="stale-attempt-key",
                expected_revision=0,
                difficulty=6.0,
                stability=0.5,
                due_at="2026-07-16T09:00:00+00:00",
                repetitions=0,
                lapses=1,
                state="relearning",
                scheduler_version="persistence-fixture-1",
                scheduler_state={},
            )
        count = connection.execute(
            "SELECT COUNT(*) FROM review_attempts WHERE id = 'stale-attempt'"
        ).fetchone()[0]

    assert count == 0


def test_review_constraints_reject_cross_course_concept_and_invalid_state(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = ReviewRepository(connection)
        with pytest.raises(sqlite3.IntegrityError, match="does not belong"):
            repository.create_item(
                item_id="bad-review",
                course_id="course-calculus",
                concept_id="concept-newton-2",
                item_type="flashcard",
                prompt="Bad link",
                expected_answer="",
                source_type="manual",
                source_id=None,
                due_at="2026-07-16T08:00:00+00:00",
                scheduler_version="test",
                idempotency_key="bad-review-key",
            )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
            connection.execute(
                """
                INSERT INTO review_schedules (
                    review_item_id, difficulty, stability, due_at,
                    repetitions, lapses, state, scheduler_version, updated_at
                ) VALUES ('missing', 5, 0, '2026-07-16', 0, 0,
                          'invalid', 'test', '2026-07-16')
                """
            )


def test_repository_write_can_be_rolled_back_by_outer_transaction(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = ReviewRepository(connection)
        connection.execute("BEGIN IMMEDIATE")
        repository.create_item(
            item_id="outer-transaction-review",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            item_type="flashcard",
            prompt="What is the chain rule?",
            expected_answer="A derivative rule",
            source_type="manual",
            source_id=None,
            due_at="2026-07-16T08:00:00+00:00",
            scheduler_version="test",
            idempotency_key="outer-transaction-key",
            commit=False,
        )
        connection.rollback()
        assert repository.get_item("outer-transaction-review") is None
