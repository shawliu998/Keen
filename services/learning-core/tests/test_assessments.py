from __future__ import annotations

import pytest

from app.database import Database
from app.repositories.assessment_repository import AssessmentRepository


def _seed_source(connection):
    now = "2026-07-16T00:00:00+00:00"
    connection.execute(
        "INSERT INTO documents VALUES ('doc', 'course-calculus', 'source.txt', 'text/plain', '.txt', 'indexed', 1, 1, NULL, ?, ?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO document_versions VALUES ('version', 'doc', 1, ?, '/tmp/source', 1, 'fixture', 1, ?)",
        ("a" * 64, now),
    )
    connection.execute(
        "INSERT INTO document_chunks (id, document_id, version_id, ordinal, page_number, section_path, content, content_hash, text_location, parser_version, embedding_version, created_at) VALUES ('chunk', 'doc', 'version', 0, 1, '[]', 'limits', ?, '{}', 'fixture', NULL, ?)",
        ("b" * 64, now),
    )
    connection.execute(
        "INSERT INTO course_documents VALUES ('course-calculus', 'doc', ?)", (now,)
    )
    connection.commit()


@pytest.fixture
def repository(tmp_path):
    database = Database(tmp_path / "assessment.sqlite3")
    database.migrate()
    database.seed_demo()
    with database.connection() as connection:
        _seed_source(connection)
        yield AssessmentRepository(connection), connection


def _create(repo: AssessmentRepository):
    assessment = repo.create_assessment(
        assessment_id="assessment-1",
        course_id="course-calculus",
        title="Limits quiz",
        purpose="quiz",
        items=[
            {
                "id": "item-1",
                "item_type": "single_choice",
                "difficulty": "medium",
                "prompt": "Which describes a limit?",
                "options": ["Nearby behavior", "Exact value"],
                "answer_key": 0,
                "rubric": {"exact": True},
                "max_score": 10,
                "source_chunk_ids": ["chunk"],
                "concept_id": "concept-limits",
            }
        ],
    )
    return repo.publish_assessment(assessment["id"], expected_revision=1)


def test_attempt_hint_and_evaluation_persist_deterministically(repository):
    repo, _ = repository
    _create(repo)
    attempt = repo.start_attempt(
        attempt_id="attempt-1",
        assessment_id="assessment-1",
        item_id="item-1",
        answer=0,
        confidence=0.8,
        idempotency_key="answer-1",
    )
    replay = repo.start_attempt(
        attempt_id="ignored",
        assessment_id="assessment-1",
        item_id="item-1",
        answer=0,
        confidence=0.8,
        idempotency_key="answer-1",
    )
    assert replay["id"] == attempt["id"]
    repo.record_hint(
        hint_id="hint-1",
        attempt_id=attempt["id"],
        item_id="item-1",
        level=1,
        penalty=1,
        content="Think about nearby inputs.",
        idempotency_key="hint-1",
    )
    evaluation = repo.grade_attempt(
        evaluation_id="evaluation-1",
        attempt_id=attempt["id"],
        item_id="item-1",
        raw_score=10,
        final_score=9,
        correctness="correct",
        independence=0.8,
        rubric_breakdown={"answer": 10},
        evaluation_source="deterministic",
        feedback="Correct",
        grader_version="deterministic-v1",
    )
    assert evaluation["hint_penalty"] == 1
    assert evaluation["rubric_breakdown"] == {"answer": 10}
    assert repo.get_attempt(attempt["id"])["status"] == "graded"


def test_attempt_idempotency_and_score_invariants_are_enforced(repository):
    repo, _ = repository
    _create(repo)
    repo.start_attempt(
        attempt_id="attempt",
        assessment_id="assessment-1",
        item_id="item-1",
        answer=0,
        idempotency_key="answer",
    )
    with pytest.raises(ValueError, match="different attempt payload"):
        repo.start_attempt(
            attempt_id="changed",
            assessment_id="assessment-1",
            item_id="item-1",
            answer=1,
            idempotency_key="answer",
        )
    with pytest.raises(ValueError, match="exceeds item maximum"):
        repo.grade_attempt(
            evaluation_id="bad",
            attempt_id="attempt",
            item_id="item-1",
            raw_score=11,
            final_score=11,
            correctness="correct",
            independence=1,
            rubric_breakdown={},
            evaluation_source="deterministic",
            feedback="",
            grader_version="v1",
        )


def test_cross_assessment_item_and_unpublished_attempt_are_rejected(repository):
    repo, _ = repository
    _create(repo)
    repo.create_assessment(
        assessment_id="draft",
        course_id="course-calculus",
        title="Draft",
        purpose="practice",
        items=[
            {
                "id": "draft-item",
                "item_type": "true_false",
                "difficulty": "easy",
                "prompt": "True?",
                "answer_key": True,
                "max_score": 1,
                "source_chunk_ids": [],
            }
        ],
    )
    with pytest.raises(ValueError, match="not published"):
        repo.start_attempt(
            attempt_id="draft-attempt",
            assessment_id="draft",
            item_id="draft-item",
            answer=True,
            idempotency_key="draft-answer",
        )
    with pytest.raises(Exception, match="does not belong"):
        repo.start_attempt(
            attempt_id="cross",
            assessment_id="assessment-1",
            item_id="draft-item",
            answer=True,
            idempotency_key="cross",
        )


def test_assessment_course_is_immutable_after_items_are_added(repository):
    repo, connection = repository
    _create(repo)
    with pytest.raises(Exception, match="course is immutable"):
        connection.execute(
            "UPDATE assessments SET course_id = 'course-physics' WHERE id = 'assessment-1'"
        )
    connection.rollback()
    assert repo.get_assessment("assessment-1")["course_id"] == "course-calculus"
