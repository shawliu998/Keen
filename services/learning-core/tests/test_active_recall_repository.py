from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.database import Database
from app.repositories.active_recall_repository import ActiveRecallRepository


NOW = "2026-07-18T00:00:00+00:00"
BEGIN_KEY = "begin-active-recall-key-0001"
ANSWER_KEY = "answer-active-recall-key-0001"
FINGERPRINT = "a" * 64
ANSWER_FINGERPRINT = "b" * 64


@pytest.fixture
def repository(tmp_path):
    database = Database(tmp_path / "active-recall.sqlite3")
    database.migrate()
    connection = database.connect()
    _seed_pending_run_dependencies(connection)
    try:
        yield ActiveRecallRepository(connection), connection
    finally:
        connection.close()


def _seed_pending_run_dependencies(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        INSERT INTO courses (id, title, created_at)
        VALUES ('course', 'Course', '{NOW}');
        INSERT INTO concepts (id, course_id, name) VALUES ('concept', 'course', 'Concept');
        INSERT INTO mastery (concept_id, probability, attempts, updated_at)
        VALUES ('concept', 0.4, 0, '{NOW}');
        INSERT INTO study_sessions
            (id, course_id, title, mode, goal, status, estimated_minutes, created_at, updated_at)
        VALUES ('session', 'course', 'Session', 'study', 'Goal', 'active_recall', 10, '{NOW}', '{NOW}');
        INSERT INTO study_plan_versions (id, session_id, version, created_at)
        VALUES ('plan', 'session', 1, '{NOW}');
        INSERT INTO study_units
            (id, plan_version_id, ordinal, concept_id, concept_ids_json, source_chunk_ids_json,
             title, objective, estimated_minutes, status, created_at, updated_at)
        VALUES ('unit', 'plan', 0, 'concept', '["concept"]', '["chunk-1"]',
                'Unit', 'Recall it', 10, 'active', '{NOW}', '{NOW}');
        UPDATE study_sessions SET current_unit_id = 'unit' WHERE id = 'session';
        INSERT INTO study_checkpoints
            (id, session_id, unit_id, kind, prompt, response, status, created_at, answered_at)
        VALUES ('checkpoint', 'session', 'unit', 'active_recall', 'What is it?', NULL,
                'pending', '{NOW}', NULL);
        INSERT INTO assessments
            (id, course_id, session_id, title, purpose, status, revision, created_at, updated_at, published_at)
        VALUES ('assessment', 'course', 'session', 'Recall', 'checkpoint', 'published', 2,
                '{NOW}', '{NOW}', '{NOW}');
        INSERT INTO assessment_items
            (id, assessment_id, ordinal, concept_id, item_type, difficulty, prompt,
             answer_key_json, source_chunk_ids_json, max_score, created_at)
        VALUES ('item', 'assessment', 0, 'concept', 'fill_blank', 'easy', 'What is it?',
                '"answer"', '["chunk-1"]', 1, '{NOW}');
        """
    )
    connection.commit()


def _create(
    repository: ActiveRecallRepository, **overrides: object
) -> tuple[dict, bool]:
    values: dict[str, object] = {
        "run_id": "run",
        "course_id": "course",
        "session_id": "session",
        "unit_id": "unit",
        "checkpoint_id": "checkpoint",
        "assessment_id": "assessment",
        "item_id": "item",
        "concept_id": "concept",
        "mastery_attempts_before": 0,
        "source_chunk_ids": ["chunk-1"],
        "generator_version": "cloze/1",
        "idempotency_key": BEGIN_KEY,
        "payload_fingerprint": FINGERPRINT,
        "created_at": NOW,
    }
    values.update(overrides)
    return repository.create_run(**values)  # type: ignore[arg-type]


def test_create_replays_exact_request_and_hides_idempotency_material(repository):
    repo, _ = repository

    created, applied = _create(repo)
    replayed, replayed_applied = _create(repo)

    assert applied is True
    assert replayed_applied is False
    assert created == replayed
    assert created["status"] == "pending"
    assert created["source_chunk_ids"] == ["chunk-1"]
    assert not {key for key in created if "idempotency" in key or "fingerprint" in key}
    assert (
        repo.find_by_begin_idempotency_key(
            course_id="course", session_id="session", key=BEGIN_KEY
        )
        == created
    )
    assert (
        repo.replay_begin(
            course_id="course",
            session_id="session",
            idempotency_key=BEGIN_KEY,
            payload_fingerprint=FINGERPRINT,
        )
        == created
    )
    assert (
        repo.replay_begin(
            course_id="outside",
            session_id="session",
            idempotency_key=BEGIN_KEY,
            payload_fingerprint=FINGERPRINT,
        )
        is None
    )
    with pytest.raises(ValueError, match="idempotency key was reused"):
        repo.replay_begin(
            course_id="course",
            session_id="session",
            idempotency_key=BEGIN_KEY,
            payload_fingerprint="c" * 64,
        )
    with pytest.raises(ValueError, match="idempotency key was reused"):
        _create(repo, generator_version="cloze/2")


def test_create_rejects_sources_that_are_only_a_subset_of_the_unit(repository):
    repo, _ = repository

    with pytest.raises(sqlite3.IntegrityError, match="sources do not match"):
        _create(repo, source_chunk_ids=[])


def test_commit_false_requires_owned_transaction_and_rolls_back(repository):
    repo, connection = repository

    with pytest.raises(RuntimeError, match="caller-owned transaction"):
        _create(repo, commit=False)
    connection.execute("BEGIN IMMEDIATE")
    created, applied = _create(repo, commit=False)
    assert applied is True
    assert created["id"] == "run"
    connection.rollback()
    assert repo.get_run("run") is None


def test_ledger_rejects_attempt_outside_its_session_bound_assessment(repository):
    repo, connection = repository
    _create(repo)

    with pytest.raises(sqlite3.IntegrityError, match="attempt session does not match"):
        connection.execute(
            """
            INSERT INTO assessment_attempts
                (id, assessment_id, item_id, session_id, status, idempotency_key,
                 answer_json, started_at, updated_at)
            VALUES ('wrong-attempt', 'assessment', 'item', NULL, 'in_progress',
                    'wrong-attempt-key', '"answer"', ?, ?)
            """,
            (NOW, NOW),
        )


def test_mark_answered_replays_only_full_chain_and_hides_answer_key(repository):
    repo, connection = repository
    _create(repo)
    _seed_answer_chain(connection)

    answered, applied = repo.mark_answered(
        run_id="run",
        idempotency_key=ANSWER_KEY,
        payload_fingerprint=ANSWER_FINGERPRINT,
        attempt_id="attempt",
        evaluation_id="evaluation",
        mastery_evidence_id="evidence",
        mastery_event_id=1,
        answered_at=NOW,
    )
    replayed, replayed_applied = repo.mark_answered(
        run_id="run",
        idempotency_key=ANSWER_KEY,
        payload_fingerprint=ANSWER_FINGERPRINT,
        attempt_id="attempt",
        evaluation_id="evaluation",
        mastery_evidence_id="evidence",
        mastery_event_id=1,
        answered_at=NOW,
    )

    assert applied is True
    assert replayed_applied is False
    assert replayed == answered
    assert answered["status"] == "answered"
    assert "answer_idempotency_key" not in answered
    assert (
        repo.find_by_answer_idempotency_key(
            course_id="course", session_id="session", key=ANSWER_KEY
        )
        == answered
    )
    assert (
        repo.replay_answer(
            run_id="run",
            course_id="course",
            session_id="session",
            idempotency_key=ANSWER_KEY,
            payload_fingerprint=ANSWER_FINGERPRINT,
        )
        == answered
    )
    with pytest.raises(ValueError, match="already recorded"):
        repo.mark_answered(
            run_id="run",
            idempotency_key=ANSWER_KEY,
            payload_fingerprint="c" * 64,
            attempt_id="attempt",
            evaluation_id="evaluation",
            mastery_evidence_id="evidence",
            mastery_event_id=1,
        )


def test_mark_answered_rejects_scoring_chain_that_does_not_match_evidence(repository):
    repo, connection = repository
    _create(repo)
    _seed_answer_chain(connection)
    connection.execute(
        "UPDATE answer_evaluations SET independence = 0.5 WHERE id = 'evaluation'"
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="scoring chain is invalid"):
        repo.mark_answered(
            run_id="run",
            idempotency_key=ANSWER_KEY,
            payload_fingerprint=ANSWER_FINGERPRINT,
            attempt_id="attempt",
            evaluation_id="evaluation",
            mastery_evidence_id="evidence",
            mastery_event_id=1,
            answered_at=NOW,
        )


def test_answer_replay_is_scoped_and_rejects_changed_fingerprint(repository):
    repo, connection = repository
    _create(repo)
    _seed_answer_chain(connection)
    repo.mark_answered(
        run_id="run",
        idempotency_key=ANSWER_KEY,
        payload_fingerprint=ANSWER_FINGERPRINT,
        attempt_id="attempt",
        evaluation_id="evaluation",
        mastery_evidence_id="evidence",
        mastery_event_id=1,
        answered_at=NOW,
    )

    assert (
        repo.replay_answer(
            run_id="run",
            course_id="outside",
            session_id="session",
            idempotency_key=ANSWER_KEY,
            payload_fingerprint=ANSWER_FINGERPRINT,
        )
        is None
    )
    with pytest.raises(ValueError, match="already recorded"):
        repo.replay_answer(
            run_id="run",
            course_id="course",
            session_id="session",
            idempotency_key=ANSWER_KEY,
            payload_fingerprint="c" * 64,
        )


def test_concurrent_create_converges_to_one_run_and_one_replay(tmp_path):
    database = Database(tmp_path / "concurrent-begin.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _seed_pending_run_dependencies(connection)

    barrier = threading.Barrier(2)

    def begin() -> tuple[dict, bool]:
        connection = database.connect()
        try:
            barrier.wait()
            return _create(ActiveRecallRepository(connection))
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: begin(), range(2)))

    assert sorted(applied for _, applied in results) == [False, True]
    assert results[0][0] == results[1][0]
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM study_active_recall_runs"
            ).fetchone()[0]
            == 1
        )


def test_concurrent_mark_answered_converges_to_one_answer_and_one_replay(tmp_path):
    database = Database(tmp_path / "concurrent-answer.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _seed_pending_run_dependencies(connection)
        _create(ActiveRecallRepository(connection))
        _seed_answer_chain(connection)

    barrier = threading.Barrier(2)

    def answer() -> tuple[dict, bool]:
        connection = database.connect()
        try:
            barrier.wait()
            return ActiveRecallRepository(connection).mark_answered(
                run_id="run",
                idempotency_key=ANSWER_KEY,
                payload_fingerprint=ANSWER_FINGERPRINT,
                attempt_id="attempt",
                evaluation_id="evaluation",
                mastery_evidence_id="evidence",
                mastery_event_id=1,
                answered_at=NOW,
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: answer(), range(2)))

    assert sorted(applied for _, applied in results) == [False, True]
    assert results[0][0] == results[1][0]
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM study_active_recall_runs WHERE status = 'answered'"
            ).fetchone()[0]
            == 1
        )


def _seed_answer_chain(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        INSERT INTO assessment_attempts
            (id, assessment_id, item_id, session_id, status, idempotency_key, answer_json,
             confidence, total_score, max_score, started_at, submitted_at, graded_at, updated_at)
        VALUES ('attempt', 'assessment', 'item', 'session', 'graded', 'attempt-key', '"answer"',
                NULL, 1, 1, '{NOW}', '{NOW}', '{NOW}', '{NOW}');
        INSERT INTO answer_evaluations
            (id, attempt_id, item_id, answer_json, raw_score, hint_penalty, final_score,
             is_correct, correctness, score, independence, rubric_breakdown_json,
             evaluation_source, feedback, evaluator_version, grader_version, created_at)
        VALUES ('evaluation', 'attempt', 'item', '"answer"', 1, 0, 1, 1, 'correct', 1, 1,
                '{{}}', 'deterministic', '', 'objective/1', 'objective/1', '{NOW}');
        INSERT INTO mastery_evidence
            (id, concept_id, attempt_id, session_id, evidence_type, correctness, independence,
             hint_level, confidence_calibration, weight, idempotency_key, created_at)
        VALUES ('evidence', 'concept', 'attempt', 'session', 'active_recall', 1, 1, 0,
                NULL, 0.9, 'evidence-key', '{NOW}');
        INSERT INTO mastery_events
            (concept_id, correct, probability_before, probability_after, observed_at,
             algorithm, algorithm_version, evidence_ids_json, idempotency_key)
        VALUES ('concept', 1, 0.4, 0.7, '{NOW}', 'weighted_bkt',
                'weighted-bkt/1.0.0', '["evidence"]', 'event-key');
        UPDATE mastery SET probability = 0.7, attempts = 1, updated_at = '{NOW}'
        WHERE concept_id = 'concept';
        INSERT INTO mastery_event_evidence (event_id, evidence_id) VALUES (1, 'evidence');
        UPDATE study_checkpoints
        SET status = 'answered', response = 'Objective response recorded.', answered_at = '{NOW}'
        WHERE id = 'checkpoint';
        """
    )
    connection.commit()
