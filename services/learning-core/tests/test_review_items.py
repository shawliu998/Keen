from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from app.database import Database
from app.repositories.review_repository import ReviewRepository
from app.review import FSRSReviewScheduler, Rating, Schedule
from app.review.scheduler import SCHEDULER_VERSION


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
        scheduler_version=SCHEDULER_VERSION,
        idempotency_key="review-chain-rule-key",
        created_at="2026-07-16T07:00:00+00:00",
    )


def test_review_item_and_fsrs_state_are_separate_and_idempotent(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = ReviewRepository(connection)
        item, created = _create_item(repository)
        retried, retried_created = _create_item(repository)
        initial_schedule = Schedule.from_record(item)
        reviewed_at = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
        scheduled = FSRSReviewScheduler().review(
            current=initial_schedule,
            rating=Rating.GOOD,
            reviewed_at=reviewed_at,
        )
        scheduled_record = scheduled.to_record()
        attempt, attempt_created = repository.record_attempt(
            attempt_id="review-attempt-1",
            item_id=item["id"],
            rating="good",
            response={"text": "differentiate outer, then multiply by inner"},
            idempotency_key="review-attempt-1-key",
            expected_revision=0,
            difficulty=scheduled.difficulty,
            stability=scheduled.stability,
            due_at=str(scheduled_record["due_at"]),
            repetitions=scheduled.repetitions,
            lapses=scheduled.lapses,
            state=scheduled.state.value,
            scheduler_version=scheduled.scheduler_version,
            scheduler_state=dict(scheduled.scheduler_state),
            reviewed_at=reviewed_at.isoformat(),
        )
        retried_attempt, retried_attempt_created = repository.record_attempt(
            attempt_id="review-attempt-1",
            item_id=item["id"],
            rating="good",
            response={"text": "differentiate outer, then multiply by inner"},
            idempotency_key="review-attempt-1-key",
            expected_revision=0,
            difficulty=scheduled.difficulty,
            stability=scheduled.stability,
            due_at=str(scheduled_record["due_at"]),
            repetitions=scheduled.repetitions,
            lapses=scheduled.lapses,
            state=scheduled.state.value,
            scheduler_version=scheduled.scheduler_version,
            scheduler_state=dict(scheduled.scheduler_state),
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
        reloaded_schedule = Schedule.from_record(persisted)

    assert created is True
    assert retried_created is False
    assert retried == item
    assert attempt_created is True
    assert retried_attempt_created is False
    assert retried_attempt == attempt
    assert post_review_created is False
    assert post_review_retry["id"] == item["id"]
    assert attempt["schedule_before"]["state"] == "new"
    assert attempt["schedule_before"]["fsrs_card_id"] == item["fsrs_card_id"]
    assert attempt["schedule_after"]["fsrs_card_id"] == item["fsrs_card_id"]
    assert (
        attempt["schedule_after"]["scheduler_state"]["card_id"] == item["fsrs_card_id"]
    )
    assert reloaded_schedule == scheduled
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
                scheduler_version=SCHEDULER_VERSION,
                idempotency_key="bad-review-key",
            )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
            connection.execute(
                """
                INSERT INTO review_schedules (
                    review_item_id, fsrs_card_id, difficulty, stability, due_at,
                    repetitions, lapses, state, scheduler_version,
                    scheduler_state_json, updated_at
                ) VALUES ('missing', 999, 5, 0, '2026-07-16', 0, 0,
                          'invalid', 'test', '{"card_id":999,"step":0}',
                          '2026-07-16')
                """
            )


def test_repository_write_can_be_rolled_back_by_outer_transaction(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = ReviewRepository(connection)
        connection.execute("BEGIN IMMEDIATE")
        rolled_back, _ = repository.create_item(
            item_id="outer-transaction-review",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            item_type="flashcard",
            prompt="What is the chain rule?",
            expected_answer="A derivative rule",
            source_type="manual",
            source_id=None,
            due_at="2026-07-16T08:00:00+00:00",
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key="outer-transaction-key",
            commit=False,
        )
        connection.rollback()
        assert repository.get_item("outer-transaction-review") is None
        recreated, created = repository.create_item(
            item_id="outer-transaction-review",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            item_type="flashcard",
            prompt="What is the chain rule?",
            expected_answer="A derivative rule",
            source_type="manual",
            source_id=None,
            due_at="2026-07-16T08:00:00+00:00",
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key="outer-transaction-key",
        )

    assert created is True
    assert recreated["fsrs_card_id"] == rolled_back["fsrs_card_id"]


def test_review_repository_rejects_invalid_time_version_and_identity(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        repository = ReviewRepository(connection)
        with pytest.raises(ValueError, match="due_at.*timezone-aware UTC"):
            repository.create_item(
                item_id="bad-due-review",
                course_id="course-calculus",
                concept_id="concept-chain-rule",
                item_type="flashcard",
                prompt="Bad due",
                expected_answer="answer",
                source_type="manual",
                source_id=None,
                due_at="2026-07-16T08:00:00",
                scheduler_version=SCHEDULER_VERSION,
                idempotency_key="bad-due-review-key",
            )
        with pytest.raises(ValueError, match="scheduler_version"):
            repository.create_item(
                item_id="bad-version-review",
                course_id="course-calculus",
                concept_id="concept-chain-rule",
                item_type="flashcard",
                prompt="Bad version",
                expected_answer="answer",
                source_type="manual",
                source_id=None,
                due_at="2026-07-16T08:00:00+00:00",
                scheduler_version="unknown-fsrs-version",
                idempotency_key="bad-version-review-key",
            )
        item, _ = _create_item(repository)
        with pytest.raises(sqlite3.IntegrityError, match="FSRS"):
            connection.execute(
                """
                UPDATE review_schedules
                SET fsrs_card_id = 0,
                    scheduler_state_json = json_set(
                        scheduler_state_json, '$.card_id', 0
                    )
                WHERE review_item_id = ?
                """,
                (item["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="state is inconsistent"):
            connection.execute(
                """
                UPDATE review_schedules
                SET scheduler_state_json = json_object(
                    'card_id', fsrs_card_id, 'step', 1
                )
                WHERE review_item_id = ?
                """,
                (item["id"],),
            )
        connection.rollback()

        scheduled = FSRSReviewScheduler().review(
            current=Schedule.from_record(item),
            rating=Rating.GOOD,
            reviewed_at=datetime(2026, 7, 16, 8, 0, tzinfo=UTC),
        )
        scheduled_record = scheduled.to_record()
        with pytest.raises(ValueError, match="reviewed_at.*timezone-aware UTC"):
            repository.record_attempt(
                attempt_id="bad-time-attempt",
                item_id=item["id"],
                rating="good",
                response={},
                idempotency_key="bad-time-attempt-key",
                expected_revision=0,
                difficulty=scheduled.difficulty,
                stability=scheduled.stability,
                due_at=str(scheduled_record["due_at"]),
                repetitions=scheduled.repetitions,
                lapses=scheduled.lapses,
                state=scheduled.state.value,
                scheduler_version=scheduled.scheduler_version,
                scheduler_state=dict(scheduled.scheduler_state),
                reviewed_at="2026-07-16T08:00:00",
            )
        invalid_identity = dict(scheduled.scheduler_state)
        invalid_identity["card_id"] = int(item["fsrs_card_id"]) + 1
        with pytest.raises(ValueError, match="card id cannot change"):
            repository.record_attempt(
                attempt_id="bad-identity-attempt",
                item_id=item["id"],
                rating="good",
                response={},
                idempotency_key="bad-identity-attempt-key",
                expected_revision=0,
                difficulty=scheduled.difficulty,
                stability=scheduled.stability,
                due_at=str(scheduled_record["due_at"]),
                repetitions=scheduled.repetitions,
                lapses=scheduled.lapses,
                state=scheduled.state.value,
                scheduler_version=scheduled.scheduler_version,
                scheduler_state=invalid_identity,
                reviewed_at="2026-07-16T08:00:00+00:00",
            )

        connection.execute(
            """
            UPDATE review_fsrs_identity_sequence
            SET next_card_id = 9223372036854775807
            WHERE singleton = 1
            """
        )
        connection.commit()
        with pytest.raises(OverflowError, match="space is exhausted"):
            repository.create_item(
                item_id="overflow-review",
                course_id="course-calculus",
                concept_id="concept-chain-rule",
                item_type="flashcard",
                prompt="Overflow prompt",
                expected_answer="answer",
                source_type="manual",
                source_id=None,
                due_at="2026-07-16T08:00:00+00:00",
                scheduler_version=SCHEDULER_VERSION,
                idempotency_key="overflow-review-key",
            )
        assert repository.get_item("overflow-review") is None


def test_017_upgrades_default_015_fsrs_state_without_data_loss(tmp_path):
    database = Database(tmp_path / "review-017-upgrade.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 17):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute(
            """
            INSERT INTO courses (id, title, description, created_at)
            VALUES ('review-upgrade-course', 'Review upgrade', '',
                    '2026-07-16T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name)
            VALUES ('review-upgrade-concept', 'review-upgrade-course', 'Concept')
            """
        )
        for suffix in ("b", "a"):
            item_id = f"legacy-review-{suffix}"
            connection.execute(
                """
                INSERT INTO review_items (
                    id, course_id, concept_id, item_type, prompt,
                    expected_answer_json, source_type, source_id, status,
                    idempotency_key, creation_payload_json, created_at, updated_at
                ) VALUES (?, 'review-upgrade-course', 'review-upgrade-concept',
                          'flashcard', 'Prompt', '{}', 'manual', NULL, 'active',
                          ?, '{}', '2026-07-16T00:00:00+00:00',
                          '2026-07-16T00:00:00+00:00')
                """,
                (item_id, f"{item_id}-key"),
            )
            connection.execute(
                """
                INSERT INTO review_schedules (
                    review_item_id, difficulty, stability, due_at,
                    repetitions, lapses, state, scheduler_version, updated_at
                ) VALUES (?, 5, 0, '2026-07-16T08:00:00+00:00',
                          0, 0, 'new', 'pre-adapter-default',
                          '2026-07-16T00:00:00+00:00')
                """,
                (item_id,),
            )
        connection.commit()

    assert database.migrate() == [17, 18, 19]
    assert database.migrate() == []
    database.verify_consistency()
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT * FROM review_schedules ORDER BY review_item_id"
        ).fetchall()

    assert [row["fsrs_card_id"] for row in rows] == [1, 2]
    for row in rows:
        scheduler_state = json.loads(row["scheduler_state_json"])
        assert scheduler_state == {"card_id": row["fsrs_card_id"], "step": 0}
        assert row["scheduler_version"] == SCHEDULER_VERSION
        restored = Schedule.from_record(
            {
                **dict(row),
                "scheduler_state": scheduler_state,
            }
        )
        assert restored.state.value == "new"


def test_fsrs_card_ids_are_collision_free_and_not_reused(tmp_path):
    database = _database(tmp_path)
    start = Barrier(2)

    def create(suffix: str) -> tuple[str, int]:
        start.wait()
        item_id = f"concurrent-review-{suffix}"
        with database.connection() as connection:
            item, _ = ReviewRepository(connection).create_item(
                item_id=item_id,
                course_id="course-calculus",
                concept_id="concept-chain-rule",
                item_type="flashcard",
                prompt=f"Concurrent prompt {suffix}",
                expected_answer="answer",
                source_type="manual",
                source_id=None,
                due_at="2026-07-16T08:00:00+00:00",
                scheduler_version=SCHEDULER_VERSION,
                idempotency_key=f"concurrent-review-{suffix}-key",
            )
            return item_id, int(item["fsrs_card_id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(create, ("a", "b")))

    card_ids = [card_id for _, card_id in created]
    assert len(set(card_ids)) == 2
    assert min(card_ids) > 0

    highest_item_id, highest_card_id = max(created, key=lambda value: value[1])
    with database.connection() as connection:
        connection.execute("DELETE FROM review_items WHERE id = ?", (highest_item_id,))
        connection.commit()
        replacement, _ = ReviewRepository(connection).create_item(
            item_id="replacement-review",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            item_type="flashcard",
            prompt="Replacement prompt",
            expected_answer="answer",
            source_type="manual",
            source_id=None,
            due_at="2026-07-16T08:00:00+00:00",
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key="replacement-review-key",
        )

    assert replacement["fsrs_card_id"] > highest_card_id


def test_concurrent_review_attempt_idempotency_replays_after_write_lock(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        item, _ = _create_item(ReviewRepository(connection))
    reviewed_at = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    scheduled = FSRSReviewScheduler().review(
        current=Schedule.from_record(item),
        rating=Rating.GOOD,
        reviewed_at=reviewed_at,
    )
    scheduled_record = scheduled.to_record()
    start = Barrier(2)

    def record() -> tuple[dict, bool]:
        start.wait()
        with database.connection() as connection:
            return ReviewRepository(connection).record_attempt(
                attempt_id="concurrent-review-attempt",
                item_id=item["id"],
                rating="good",
                response={"text": "same response"},
                idempotency_key="concurrent-review-attempt-key",
                expected_revision=0,
                difficulty=scheduled.difficulty,
                stability=scheduled.stability,
                due_at=str(scheduled_record["due_at"]),
                repetitions=scheduled.repetitions,
                lapses=scheduled.lapses,
                state=scheduled.state.value,
                scheduler_version=scheduled.scheduler_version,
                scheduler_state=dict(scheduled.scheduler_state),
                reviewed_at=reviewed_at.isoformat(),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: record(), range(2)))

    assert sorted(created for _, created in results) == [False, True]
    assert results[0][0] == results[1][0]
    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM review_attempts) AS attempts,
                (SELECT revision FROM review_schedules WHERE review_item_id = ?)
                    AS revision
            """,
            (item["id"],),
        ).fetchone()
        assert dict(row) == {"attempts": 1, "revision": 1}

        with pytest.raises(ValueError, match="reviewed_at.*timezone-aware UTC"):
            ReviewRepository(connection).record_attempt(
                attempt_id="concurrent-review-attempt",
                item_id=item["id"],
                rating="good",
                response={"text": "same response"},
                idempotency_key="concurrent-review-attempt-key",
                expected_revision=0,
                difficulty=scheduled.difficulty,
                stability=scheduled.stability,
                due_at=str(scheduled_record["due_at"]),
                repetitions=scheduled.repetitions,
                lapses=scheduled.lapses,
                state=scheduled.state.value,
                scheduler_version=scheduled.scheduler_version,
                scheduler_state=dict(scheduled.scheduler_state),
                reviewed_at="2026-07-16T08:00:00",
            )
