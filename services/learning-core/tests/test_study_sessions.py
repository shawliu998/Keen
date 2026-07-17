from __future__ import annotations

import pytest

from app.database import Database
from app.repositories.study_repository import StudyRepository


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
    database = Database(tmp_path / "study.sqlite3")
    database.migrate()
    database.seed_demo()
    with database.connection() as connection:
        _seed_source(connection)
        yield StudyRepository(connection), connection


def _create(repo: StudyRepository, session_id: str = "session-1"):
    return repo.create_session(
        session_id=session_id,
        course_id="course-calculus",
        title="Learn limits",
        mode="study",
        goal="Understand limits",
        estimated_minutes=30,
        goal_scope={"concepts": ["concept-limits"]},
        preferences={"pace": "steady"},
        difficulty={"target": "medium"},
    )


def test_session_plan_is_versioned_and_json_is_validated(repository):
    repo, _ = repository
    session = _create(repo)
    plan = repo.save_plan(
        plan_id="plan-1",
        session_id=session["id"],
        version=1,
        rationale="Build foundations",
        units=[
            {
                "id": "unit-1",
                "title": "Limits",
                "objective": "Explain a limit",
                "estimated_minutes": 15,
                "concept_id": "concept-limits",
                "concept_ids": ["concept-limits"],
                "source_chunk_ids": ["chunk"],
                "status": "ready",
            },
            {
                "id": "unit-2",
                "title": "Apply limits",
                "objective": "Solve a limit",
                "estimated_minutes": 15,
                "concept_id": "concept-limits",
                "concept_ids": ["concept-limits"],
                "source_chunk_ids": ["chunk"],
            },
        ],
    )
    replay = repo.save_plan(
        plan_id="plan-1",
        session_id=session["id"],
        version=1,
        rationale="Build foundations",
        units=[
            {
                "id": "unit-1",
                "title": "Limits",
                "objective": "Explain a limit",
                "estimated_minutes": 15,
                "concept_id": "concept-limits",
                "concept_ids": ["concept-limits"],
                "source_chunk_ids": ["chunk"],
                "status": "ready",
            },
            {
                "id": "unit-2",
                "title": "Apply limits",
                "objective": "Solve a limit",
                "estimated_minutes": 15,
                "concept_id": "concept-limits",
                "concept_ids": ["concept-limits"],
                "source_chunk_ids": ["chunk"],
            },
        ],
    )
    assert plan["units"][0]["concept_ids"] == ["concept-limits"]
    assert replay["id"] == "plan-1"
    with pytest.raises(ValueError, match="non-empty strings"):
        repo.save_plan(
            plan_id="bad",
            session_id=session["id"],
            version=2,
            rationale="bad",
            units=[
                {
                    "id": "bad-unit",
                    "title": "Bad",
                    "objective": "Bad",
                    "estimated_minutes": 1,
                    "concept_ids": [1],
                    "source_chunk_ids": ["chunk"],
                },  # type: ignore[list-item]
                {
                    "id": "unit-2",
                    "title": "Okay",
                    "objective": "Okay",
                    "estimated_minutes": 1,
                    "concept_ids": ["concept-limits"],
                    "source_chunk_ids": ["chunk"],
                },
            ],
        )


def test_repository_selects_latest_plan_or_plan_containing_current_unit(repository):
    repo, _ = repository
    session = _create(repo, session_id="session-plan-selection")

    def units(prefix: str):
        return [
            {
                "id": f"{prefix}-unit-1",
                "title": "Limits",
                "objective": "Explain a limit",
                "estimated_minutes": 15,
                "concept_id": "concept-limits",
                "concept_ids": ["concept-limits"],
                "source_chunk_ids": ["chunk"],
                "status": "ready",
            },
            {
                "id": f"{prefix}-unit-2",
                "title": "Apply limits",
                "objective": "Solve a limit",
                "estimated_minutes": 15,
                "concept_id": "concept-limits",
                "concept_ids": ["concept-limits"],
                "source_chunk_ids": ["chunk"],
            },
        ]

    repo.save_plan(
        plan_id="selection-plan-1",
        session_id=session["id"],
        version=1,
        rationale="Initial plan",
        units=units("selection-v1"),
    )
    repo.save_plan(
        plan_id="selection-plan-2",
        session_id=session["id"],
        version=2,
        rationale="Latest plan",
        units=units("selection-v2"),
    )
    assert repo.get_current_or_latest_plan(session["id"])["id"] == "selection-plan-2"

    repo.transition_session(
        session["id"],
        status="goal_confirmation",
        expected_revision=0,
        current_unit_id="selection-v1-unit-1",
    )
    current = repo.get_current_or_latest_plan(session["id"])
    assert current["id"] == "selection-plan-1"
    assert [unit["id"] for unit in current["units"]] == [
        "selection-v1-unit-1",
        "selection-v1-unit-2",
    ]


def test_session_transition_revision_pause_resume_and_recovery(repository):
    repo, _ = repository
    session = _create(repo)
    confirmed = repo.transition_session(
        session["id"], status="goal_confirmation", expected_revision=0
    )
    with pytest.raises(RuntimeError, match="revision conflict"):
        repo.transition_session(session["id"], status="diagnosing", expected_revision=0)
    paused = repo.transition_session(
        session["id"], status="paused", expected_revision=confirmed["revision"]
    )
    assert paused["resume_from_status"] == "goal_confirmation"
    with pytest.raises(ValueError, match="must resume"):
        repo.transition_session(
            session["id"], status="planning", expected_revision=paused["revision"]
        )
    resumed = repo.transition_session(
        session["id"], status="goal_confirmation", expected_revision=paused["revision"]
    )
    repo.transition_session(
        session["id"], status="diagnosing", expected_revision=resumed["revision"]
    )
    assert repo.recover_active_sessions() == [session["id"]]
    assert repo.get_session(session["id"])["status"] == "paused"


def test_cross_course_unit_is_rejected_by_database(repository):
    repo, _ = repository
    session = _create(repo)
    with pytest.raises(Exception, match="outside the course"):
        repo.save_plan(
            plan_id="cross-course",
            session_id=session["id"],
            version=1,
            rationale="invalid",
            units=[
                {
                    "id": "unit",
                    "title": "Newton",
                    "objective": "Wrong course",
                    "estimated_minutes": 10,
                    "concept_id": "concept-newton-2",
                    "concept_ids": ["concept-newton-2"],
                    "source_chunk_ids": ["chunk"],
                },
                {
                    "id": "unit-2",
                    "title": "Limits",
                    "objective": "Valid",
                    "estimated_minutes": 10,
                    "concept_id": "concept-limits",
                    "concept_ids": ["concept-limits"],
                    "source_chunk_ids": ["chunk"],
                },
            ],
        )
