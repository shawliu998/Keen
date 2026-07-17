from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest

from app.database import Database
from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.services.autonomous_study_session import AutonomousStudySessionService
from app.services.study_session_read import StudySessionReadService


NOW = datetime(2026, 7, 17, 9, 0, tzinfo=UTC)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "autonomous-study-session.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def _recommendation_task(
    connection,
    *,
    task_id: str = "autonomous-task",
    course_id: str = "course-calculus",
    concept_id: str = "concept-chain-rule",
    status: str = "upcoming",
) -> dict:
    task, _ = TaskRepository(connection).create_task(
        task_id=task_id,
        course_id=course_id,
        concept_id=concept_id,
        title="Study chain rule",
        reason="Mastery needs source-grounded practice.",
        due_at="2026-07-17T23:59:59+00:00",
        estimated_minutes=20,
        source_type="weak_concept",
        source_id=concept_id,
        priority_score=0.8,
        priority_components={
            "recommendation_algorithm_version": "autonomous-recommendation/1.0.0",
            "candidate_id": f"concept:{concept_id}:study_weak_concept",
        },
        recommended_reason="Mastery needs source-grounded practice.",
        idempotency_key=f"{task_id}:key",
        created_at=NOW.isoformat(),
    )
    if status != "upcoming":
        connection.execute(
            "UPDATE study_tasks SET status = ? WHERE id = ?", (status, task_id)
        )
        connection.commit()
        task = TaskRepository(connection).get(task_id)
        assert task is not None
    return task


def _indexed_source(
    connection,
    *,
    course_id: str = "course-calculus",
    document_id: str = "source-document",
    chunk_ids: tuple[str, ...] = ("source-chunk-1", "source-chunk-2"),
) -> None:
    connection.execute(
        """
        INSERT INTO documents
            (id, course_id, name, mime_type, extension, status, page_count,
             chunk_count, error, created_at, updated_at)
        VALUES (?, ?, 'Chain rule source.md', 'text/markdown', '.md', 'indexed',
                1, ?, NULL, ?, ?)
        """,
        (document_id, course_id, len(chunk_ids), NOW.isoformat(), NOW.isoformat()),
    )
    connection.execute(
        """
        INSERT INTO document_versions
            (id, document_id, version_number, content_hash, storage_path,
             size_bytes, parser_version, page_count, created_at)
        VALUES (?, ?, 1, ?, 'source', 1, 'fixture', 1, ?)
        """,
        (f"version-{document_id}", document_id, "a" * 64, NOW.isoformat()),
    )
    connection.execute(
        "INSERT INTO course_documents (course_id, document_id, added_at) VALUES (?, ?, ?)",
        (course_id, document_id, NOW.isoformat()),
    )
    for ordinal, chunk_id in enumerate(chunk_ids):
        connection.execute(
            """
            INSERT INTO document_chunks
                (id, document_id, version_id, ordinal, page_number, section_path,
                 content, content_hash, text_location, parser_version,
                 embedding_version, created_at)
            VALUES (?, ?, ?, ?, 1, '[]', ?, ?, '{}', 'fixture', NULL, ?)
            """,
            (
                chunk_id,
                document_id,
                f"version-{document_id}",
                ordinal,
                f"Chain rule source excerpt {ordinal + 1}.",
                f"{ordinal + 1:064x}",
                NOW.isoformat(),
            ),
        )
    connection.commit()


def test_autonomous_task_creates_two_cited_source_units_and_replays(tmp_path) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        service = AutonomousStudySessionService(connection)

        created = service.start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        replay = service.start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )

        assert created.session is not None
        session_id = created.session["id"]
        source_ids = connection.execute(
            """
            SELECT source_chunk_ids_json FROM study_units u
            JOIN study_plan_versions p ON p.id = u.plan_version_id
            WHERE p.session_id = ? ORDER BY u.ordinal
            """,
            (session_id,),
        ).fetchall()
        evidence_count = connection.execute(
            "SELECT COUNT(*) FROM mastery_evidence"
        ).fetchone()[0]

    assert created.outcome == "session_created"
    assert created.session["status"] == "goal_confirmation"
    assert created.session["originating_task_id"] == "autonomous-task"
    assert created.session["created_at"] == NOW.isoformat()
    assert created.session["updated_at"] == NOW.isoformat()
    assert created.plan is not None
    assert len(created.plan["units"]) == 2
    assert all(unit["source_chunk_ids"] for unit in created.plan["units"])
    assert {row["source_chunk_ids_json"] for row in source_ids} <= {
        '["source-chunk-1"]',
        '["source-chunk-2"]',
    }
    assert evidence_count == 0
    assert replay.outcome == "resumed"
    assert replay.session is not None
    assert replay.session["id"] == session_id


def test_study_session_read_service_restores_persisted_plan_after_reopen(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        assert created.session is not None
        session_id = str(created.session["id"])

    with database.connection() as reopened:
        restored = StudySessionReadService(reopened).get(
            course_id="course-calculus", session_id=session_id
        )
        outside = StudySessionReadService(reopened).get(
            course_id="course-physics", session_id=session_id
        )

    assert restored is not None
    assert restored.outcome == "ready"
    assert restored.session["id"] == session_id
    assert restored.plan is not None
    assert restored.plan["session_id"] == session_id
    assert len(restored.plan["units"]) == 2
    assert outside is None


@pytest.mark.parametrize(
    "corruption",
    (
        "originating_task_missing",
        "originating_task_cross_course",
        "foreign_current_unit",
        "unit_count_invalid",
        "ordinal_invalid",
        "primary_concept_not_in_concept_ids",
        "concept_json_malformed",
        "concept_json_duplicate",
        "concept_json_empty",
        "source_json_malformed",
        "source_json_duplicate",
        "source_json_empty",
    ),
)
def test_study_session_read_service_fails_closed_for_corrupt_relationships(
    tmp_path, corruption: str
) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        assert created.session is not None
        assert created.plan is not None
        session_id = str(created.session["id"])
        plan_id = str(created.plan["id"])

        if corruption == "originating_task_missing":
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DELETE FROM study_tasks WHERE id = 'autonomous-task'")
            connection.commit()
            connection.execute("PRAGMA foreign_keys = ON")
        elif corruption == "originating_task_cross_course":
            connection.execute(
                "DROP TRIGGER study_tasks_originating_session_course_update"
            )
            connection.execute(
                "UPDATE study_tasks SET course_id = 'course-physics' WHERE id = 'autonomous-task'"
            )
            connection.commit()
        elif corruption == "foreign_current_unit":
            repository = StudyRepository(connection)
            foreign = repository.create_session(
                session_id="foreign-current-session",
                course_id="course-calculus",
                title="Different session",
                mode="study",
                goal="Keep its unit outside the requested session.",
                estimated_minutes=20,
                created_at=NOW.isoformat(),
            )
            repository.save_plan(
                plan_id="foreign-current-plan",
                session_id=foreign["id"],
                version=1,
                rationale="Different session plan.",
                units=_read_test_units("foreign-current"),
                created_at=NOW.isoformat(),
            )
            connection.execute("DROP TRIGGER study_sessions_current_unit_update")
            connection.execute(
                "UPDATE study_sessions SET current_unit_id = 'foreign-current-unit-1' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        elif corruption == "unit_count_invalid":
            connection.execute(
                "DELETE FROM study_units WHERE plan_version_id = ? AND ordinal = 1",
                (plan_id,),
            )
            connection.commit()
        elif corruption == "ordinal_invalid":
            connection.execute(
                "UPDATE study_units SET ordinal = 3 WHERE plan_version_id = ? AND ordinal = 1",
                (plan_id,),
            )
            connection.commit()
        elif corruption == "primary_concept_not_in_concept_ids":
            connection.execute(
                "UPDATE study_units SET concept_ids_json = '[\"concept-limits\"]' WHERE plan_version_id = ? AND ordinal = 0",
                (plan_id,),
            )
            connection.commit()
        else:
            column, value = {
                "concept_json_malformed": ("concept_ids_json", "{"),
                "concept_json_duplicate": (
                    "concept_ids_json",
                    '["concept-chain-rule","concept-chain-rule"]',
                ),
                "concept_json_empty": ("concept_ids_json", "[]"),
                "source_json_malformed": ("source_chunk_ids_json", "{"),
                "source_json_duplicate": (
                    "source_chunk_ids_json",
                    '["source-chunk-1","source-chunk-1"]',
                ),
                "source_json_empty": ("source_chunk_ids_json", "[]"),
            }[corruption]
            if value == "{":
                connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                f"UPDATE study_units SET {column} = ? WHERE plan_version_id = ? AND ordinal = 0",
                (value, plan_id),
            )
            connection.commit()

        with pytest.raises((RuntimeError, ValueError, KeyError, TypeError)):
            StudySessionReadService(connection).get(
                course_id="course-calculus", session_id=session_id
            )


def _read_test_units(prefix: str) -> list[dict]:
    return [
        {
            "id": f"{prefix}-unit-{ordinal}",
            "title": f"Source unit {ordinal}",
            "objective": "Read the persisted source.",
            "content": f"Persisted source excerpt {ordinal}.",
            "estimated_minutes": 10,
            "concept_id": "concept-chain-rule",
            "concept_ids": ["concept-chain-rule"],
            "source_chunk_ids": [f"source-chunk-{ordinal}"],
            "status": "ready" if ordinal == 1 else "locked",
        }
        for ordinal in (1, 2)
    ]


def test_concurrent_start_creates_one_session_then_resumes(tmp_path) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)

    barrier = Barrier(2)

    def invoke() -> str:
        with database.connection() as connection:
            barrier.wait(timeout=5)
            return (
                AutonomousStudySessionService(connection)
                .start_or_resume(
                    course_id="course-calculus", task_id="autonomous-task", now=NOW
                )
                .outcome
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: invoke(), range(2)))
    with database.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM study_sessions WHERE originating_task_id = 'autonomous-task'"
        ).fetchone()[0]

    assert sorted(outcomes) == ["resumed", "session_created"]
    assert count == 1


def test_cross_course_and_non_actionable_tasks_are_blocked_without_sessions(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        cross_course = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-physics", task_id="autonomous-task", now=NOW
        )
        _recommendation_task(connection, task_id="completed-task", status="completed")
        completed = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="completed-task", now=NOW
        )
        count = connection.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]

    assert cross_course.blocked_reason == "task_outside_course"
    assert cross_course.task is None
    assert completed.blocked_reason == "task_not_actionable"
    assert count == 0


def test_session_source_task_resumes_its_real_incomplete_session(tmp_path) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        existing = StudyRepository(connection).create_session(
            session_id="resume-source-session",
            course_id="course-calculus",
            title="Existing study work",
            mode="study",
            goal="Continue the existing source-grounded work.",
            estimated_minutes=20,
            created_at=NOW.isoformat(),
        )
        TaskRepository(connection).create_task(
            task_id="resume-source-task",
            course_id="course-calculus",
            title="Resume existing study work",
            reason="The session is incomplete.",
            due_at="2026-07-17T23:59:59+00:00",
            estimated_minutes=20,
            source_type="study_session",
            source_id=existing["id"],
            priority_score=0.8,
            priority_components={
                "recommendation_algorithm_version": "autonomous-recommendation/1.0.0"
            },
            recommended_reason="The session is incomplete.",
            idempotency_key="resume-source-task:key",
            created_at=NOW.isoformat(),
        )
        result = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="resume-source-task", now=NOW
        )
        count = connection.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]

    assert result.outcome == "resumed"
    assert result.session is not None
    assert result.session["id"] == "resume-source-session"
    assert count == 1


def test_missing_indexed_source_blocks_with_zero_writes(tmp_path) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _recommendation_task(connection)
        before = connection.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
        result = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        after = connection.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
        plan_count = connection.execute(
            "SELECT COUNT(*) FROM study_plan_versions"
        ).fetchone()[0]

    assert result.outcome == "blocked"
    assert result.blocked_reason == "no_indexed_source"
    assert (before, after, plan_count) == (0, 0, 0)


def test_one_real_chunk_is_split_into_two_nonempty_cited_units(tmp_path) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection, chunk_ids=("only-source-chunk",))
        _recommendation_task(connection)
        result = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )

    assert result.plan is not None
    first, second = result.plan["units"]
    assert (
        first["source_chunk_ids"] == second["source_chunk_ids"] == ["only-source-chunk"]
    )
    assert first["content"] and second["content"]
    assert first["content"] != second["content"]
    assert "Part 1" in first["title"]
    assert "Part 2" in second["title"]


def test_too_short_single_chunk_blocks_without_writing_a_partial_session(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection, chunk_ids=("short-source-chunk",))
        connection.execute(
            "UPDATE document_chunks SET content = 'x' WHERE id = 'short-source-chunk'"
        )
        connection.commit()
        _recommendation_task(connection)
        result = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        count = connection.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]

    assert result.outcome == "blocked"
    assert result.blocked_reason == "no_indexed_source"
    assert count == 0


def test_terminal_originating_session_is_blocked_without_a_second_session(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        service = AutonomousStudySessionService(connection)
        created = service.start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        assert created.session is not None
        connection.execute(
            """
            UPDATE study_sessions
            SET status = 'completed', finished_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (NOW.isoformat(), NOW.isoformat(), created.session["id"]),
        )
        connection.commit()
        blocked = service.start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )
        count = connection.execute(
            "SELECT COUNT(*) FROM study_sessions WHERE originating_task_id = 'autonomous-task'"
        ).fetchone()[0]

    assert blocked.outcome == "blocked"
    assert blocked.blocked_reason == "originating_session_terminal"
    assert count == 1


def test_source_citations_never_escape_the_task_course(tmp_path) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection)
        _indexed_source(
            connection,
            course_id="course-physics",
            document_id="physics-source",
            chunk_ids=("physics-chunk",),
        )
        _recommendation_task(connection)
        result = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )

    assert result.plan is not None
    assert {
        chunk_id
        for unit in result.plan["units"]
        for chunk_id in unit["source_chunk_ids"]
    } <= {"source-chunk-1", "source-chunk-2"}


def test_source_units_use_only_the_latest_document_version(tmp_path) -> None:
    database = _database(tmp_path)
    with database.connection() as connection:
        _indexed_source(connection, chunk_ids=("old-version-chunk",))
        connection.execute(
            """
            INSERT INTO document_versions
                (id, document_id, version_number, content_hash, storage_path,
                 size_bytes, parser_version, page_count, created_at)
            VALUES ('version-source-document-v2', 'source-document', 2, ?,
                    'source-v2', 2, 'fixture', 1, ?)
            """,
            ("b" * 64, NOW.isoformat()),
        )
        for ordinal in range(2):
            connection.execute(
                """
                INSERT INTO document_chunks
                    (id, document_id, version_id, ordinal, page_number,
                     section_path, content, content_hash, text_location,
                     parser_version, embedding_version, created_at)
                VALUES (?, 'source-document', 'version-source-document-v2', ?,
                        1, '[]', ?, ?, '{}', 'fixture', NULL, ?)
                """,
                (
                    f"current-version-chunk-{ordinal}",
                    ordinal,
                    f"Current source excerpt {ordinal + 1}.",
                    f"{ordinal + 10:064x}",
                    NOW.isoformat(),
                ),
            )
        connection.commit()
        _recommendation_task(connection)
        result = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus", task_id="autonomous-task", now=NOW
        )

    assert result.plan is not None
    cited = {
        chunk_id
        for unit in result.plan["units"]
        for chunk_id in unit["source_chunk_ids"]
    }
    assert cited == {"current-version-chunk-0", "current-version-chunk-1"}
    assert "old-version-chunk" not in cited
