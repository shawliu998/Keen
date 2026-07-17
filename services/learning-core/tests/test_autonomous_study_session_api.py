from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.request_guard import (
    BOUNDED_JSON_PATHS,
    SMALL_JSON_REQUEST_BYTES,
    RequestGuardMiddleware,
)
from app.services.autonomous_study_session import AutonomousStudySessionService

from conftest import TOKEN


AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 7, 17, 9, 0, tzinfo=UTC).isoformat()
COURSE_ID = "course-autonomous-api"
CONCEPT_ID = "concept-autonomous-api"


def _course_and_concept(client: TestClient) -> None:
    with client.app.state.database.connection() as connection:
        connection.execute(
            "INSERT INTO courses (id, title, description, created_at) VALUES (?, ?, '', ?)",
            (COURSE_ID, "Autonomous API course", NOW),
        )
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name, bkt_slip, bkt_guess, bkt_transit)
            VALUES (?, ?, 'Autonomous API concept', 0.1, 0.2, 0.1)
            """,
            (CONCEPT_ID, COURSE_ID),
        )
        connection.commit()


def _indexed_source(client: TestClient) -> None:
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            INSERT INTO documents
                (id, course_id, name, mime_type, extension, status, page_count,
                 chunk_count, error, created_at, updated_at)
            VALUES ('document-autonomous-api', ?, 'Source.md', 'text/markdown',
                    '.md', 'indexed', 1, 2, NULL, ?, ?)
            """,
            (COURSE_ID, NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO document_versions
                (id, document_id, version_number, content_hash, storage_path,
                 size_bytes, parser_version, page_count, created_at)
            VALUES ('version-autonomous-api', 'document-autonomous-api', 1, ?,
                    'private-path-must-not-leak', 1, 'fixture', 1, ?)
            """,
            ("a" * 64, NOW),
        )
        connection.execute(
            """
            INSERT INTO course_documents (course_id, document_id, added_at)
            VALUES (?, 'document-autonomous-api', ?)
            """,
            (COURSE_ID, NOW),
        )
        for ordinal in range(2):
            connection.execute(
                """
                INSERT INTO document_chunks
                    (id, document_id, version_id, ordinal, page_number, section_path,
                     content, content_hash, text_location, parser_version,
                     embedding_version, created_at)
                VALUES (?, 'document-autonomous-api', 'version-autonomous-api', ?, 1,
                        '[]', ?, ?, '{}', 'fixture', NULL, ?)
                """,
                (
                    f"chunk-autonomous-api-{ordinal}",
                    ordinal,
                    f"Cited source excerpt {ordinal + 1}.",
                    f"{ordinal + 1:064x}",
                    NOW,
                ),
            )
        connection.commit()


def _task(
    client: TestClient,
    *,
    task_id: str,
    concept_id: str | None = CONCEPT_ID,
    source_type: str = "weak_concept",
    source_id: str | None = CONCEPT_ID,
    autonomous: bool = True,
    status: str = "upcoming",
) -> None:
    with client.app.state.database.connection() as connection:
        task, _ = TaskRepository(connection).create_task(
            task_id=task_id,
            course_id=COURSE_ID,
            concept_id=concept_id,
            title="Study autonomous API concept",
            reason="Persisted local recommendation.",
            due_at=NOW,
            estimated_minutes=20,
            source_type=source_type,
            source_id=source_id,
            priority_score=0.8,
            priority_components=(
                {"recommendation_algorithm_version": "autonomous-recommendation/1.0.0"}
                if autonomous
                else {}
            ),
            recommended_reason="Persisted local recommendation.",
            idempotency_key=f"{task_id}:key",
            created_at=NOW,
        )
        if status != "upcoming":
            connection.execute(
                "UPDATE study_tasks SET status = ? WHERE id = ?", (status, task["id"])
            )
        connection.commit()


def _start(client: TestClient, task_id: str, *, course_id: str = COURSE_ID):
    return client.post(
        "/v1/autonomous-study-sessions",
        headers=AUTH,
        json={"course_id": course_id, "task_id": task_id},
    )


def test_start_api_creates_source_grounded_session_and_replays(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id="task-api-create")

    created = _start(client, "task-api-create")
    assert created.status_code == 201
    body = created.json()
    assert body["outcome"] == "session_created"
    assert body["blocked_reason"] is None
    assert body["task"] == {
        "id": "task-api-create",
        "course_id": COURSE_ID,
        "concept_id": CONCEPT_ID,
        "title": "Study autonomous API concept",
        "reason": "Persisted local recommendation.",
        "estimated_minutes": 20,
        "status": "upcoming",
        "source_type": "weak_concept",
    }
    assert body["session"]["status"] == "goal_confirmation"
    assert body["session"]["originating_task_id"] == "task-api-create"
    assert len(body["plan"]["units"]) == 2
    assert {unit["source_chunk_ids"][0] for unit in body["plan"]["units"]} == {
        "chunk-autonomous-api-0",
        "chunk-autonomous-api-1",
    }
    assert all(
        unit["content"].startswith("Cited source excerpt")
        for unit in body["plan"]["units"]
    )
    assert "private-path-must-not-leak" not in created.text
    assert "goal_scope" not in body["session"]

    replay = _start(client, "task-api-create")
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "resumed"
    assert replay.json()["session"]["id"] == body["session"]["id"]
    assert replay.json()["plan"] is None


def test_start_api_returns_truthful_blocked_outcomes_without_cross_course_leakage(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    _task(client, task_id="task-api-completed", status="completed")
    _task(client, task_id="task-api-manual", autonomous=False)
    _task(
        client,
        task_id="task-api-no-concept",
        concept_id=None,
        source_type="manual",
        source_id=None,
    )
    _task(client, task_id="task-api-no-source")
    with client.app.state.database.connection() as connection:
        unavailable = StudyRepository(connection).create_session(
            session_id="unavailable-source-session",
            course_id=COURSE_ID,
            title="Unavailable source session",
            mode="study",
            goal="Already terminal.",
            estimated_minutes=20,
            created_at=NOW,
        )
        StudyRepository(connection).transition_session(
            unavailable["id"],
            status="cancelled",
            expected_revision=int(unavailable["revision"]),
            updated_at=NOW,
        )
    _task(
        client,
        task_id="task-api-missing-source-session",
        source_type="study_session",
        source_id="unavailable-source-session",
    )
    _task(client, task_id="task-api-terminal")
    with client.app.state.database.connection() as connection:
        session = StudyRepository(connection).create_session(
            session_id="terminal-autonomous-session",
            course_id=COURSE_ID,
            originating_task_id="task-api-terminal",
            title="Terminal session",
            mode="study",
            goal="Already terminal.",
            estimated_minutes=20,
            created_at=NOW,
        )
        StudyRepository(connection).transition_session(
            session["id"],
            status="cancelled",
            expected_revision=int(session["revision"]),
            updated_at=NOW,
        )

    samples = {
        "missing-task": "task_not_found",
        "task-api-completed": "task_not_actionable",
        "task-api-manual": "task_not_autonomous",
        "task-api-no-concept": "task_missing_concept",
        "task-api-no-source": "no_indexed_source",
        "task-api-missing-source-session": "source_session_unavailable",
        "task-api-terminal": "originating_session_terminal",
    }
    for task_id, reason in samples.items():
        response = _start(client, task_id)
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "blocked"
        assert body["blocked_reason"] == reason
        assert body["session"] is None
        assert body["plan"] is None
        assert body["recovery_action"]

    outside = _start(client, "task-api-no-source", course_id="course-other")
    assert outside.status_code == 200
    assert outside.json()["outcome"] == "blocked"
    assert outside.json()["blocked_reason"] == "task_outside_course"
    assert outside.json()["task"] is None
    assert COURSE_ID not in outside.text
    assert "task-api-no-source" not in outside.text


def test_start_api_rejects_invalid_payload_and_enforces_authenticated_64kib_limit(
    client: TestClient,
) -> None:
    assert "/v1/autonomous-study-sessions" in BOUNDED_JSON_PATHS
    for payload in (
        {"course_id": COURSE_ID},
        {"course_id": COURSE_ID, "task_id": "task", "extra": True},
        {"course_id": "invalid course", "task_id": "task"},
        {"course_id": COURSE_ID, "task_id": True},
    ):
        assert (
            client.post(
                "/v1/autonomous-study-sessions", headers=AUTH, json=payload
            ).status_code
            == 422
        )

    oversized = b"x" * (SMALL_JSON_REQUEST_BYTES + 1)
    headers = {**AUTH, "Content-Type": "application/json"}
    assert (
        client.post(
            "/v1/autonomous-study-sessions", headers=headers, content=oversized
        ).status_code
        == 413
    )
    chunks = [b"x" * SMALL_JSON_REQUEST_BYTES, b"x"]
    sent: list[dict] = []

    async def receive() -> dict:
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(_scope: dict, receive, _send) -> None:
        while (await receive()).get("more_body"):
            pass

    async def exercise_chunked_guard() -> None:
        middleware = RequestGuardMiddleware(
            downstream, session_token=TOKEN, max_document_bytes=1024
        )
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/v1/autonomous-study-sessions",
                "headers": [(b"authorization", AUTH["Authorization"].encode())],
            },
            receive,
            send,
        )

    asyncio.run(exercise_chunked_guard())
    assert sent[0]["status"] == 413
    assert (
        client.post(
            "/v1/autonomous-study-sessions",
            headers={"Content-Type": "application/json"},
            content=oversized,
        ).status_code
        == 401
    )


def test_corrupt_cross_course_originating_session_fails_closed(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    _task(client, task_id="task-api-corrupt-cross-course")
    with client.app.state.database.connection() as connection:
        connection.execute("DROP TRIGGER study_sessions_originating_task_course_insert")
        StudyRepository(connection).create_session(
            session_id="external-secret-session-id",
            course_id="course-physics",
            originating_task_id="task-api-corrupt-cross-course",
            title="EXTERNAL SECRET SESSION TITLE",
            mode="study",
            goal="EXTERNAL SECRET SESSION GOAL",
            estimated_minutes=20,
            created_at=NOW,
        )

    response = _start(client, "task-api-corrupt-cross-course")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "autonomous_study_session_temporarily_unavailable"
    assert detail["outcomeMayBeDurable"] is True
    for secret in (
        "course-physics",
        "task-api-corrupt-cross-course",
        "external-secret-session-id",
        "EXTERNAL SECRET SESSION TITLE",
        "EXTERNAL SECRET SESSION GOAL",
    ):
        assert secret not in response.text


def test_start_api_normalizes_legacy_session_timestamps_to_aware_utc(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id="task-api-legacy-time")
    created = _start(client, "task-api-legacy-time")
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            UPDATE study_sessions
            SET created_at = '2026-07-17',
                updated_at = '2026-07-17T09:30:00',
                started_at = '2026-07-17T09:00:00'
            WHERE id = ?
            """,
            (session_id,),
        )
        connection.commit()

    replay = _start(client, "task-api-legacy-time")
    assert replay.status_code == 200
    session = replay.json()["session"]
    assert session["created_at"] == "2026-07-17T00:00:00Z"
    assert session["updated_at"] == "2026-07-17T09:30:00Z"
    assert session["started_at"] == "2026-07-17T09:00:00Z"


@pytest.mark.parametrize(
    ("column", "stored_secret"),
    (
        ("updated_at", "SECRET_INVALID_TIMESTAMP"),
        ("goal_scope_json", "SECRET_INVALID_INTERNAL_JSON"),
    ),
)
def test_invalid_stored_session_state_returns_redacted_503(
    client: TestClient,
    column: str,
    stored_secret: str,
) -> None:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id="task-api-invalid-stored-state")
    created = _start(client, "task-api-invalid-stored-state")
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]
    with client.app.state.database.connection() as connection:
        if column == "goal_scope_json":
            connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            f"UPDATE study_sessions SET {column} = ? WHERE id = ?",
            (stored_secret, session_id),
        )
        connection.commit()

    response = _start(client, "task-api-invalid-stored-state")
    assert response.status_code == 503
    assert response.json()["detail"]["outcomeMayBeDurable"] is True
    assert stored_secret not in response.text
    assert session_id not in response.text
    assert "goal_scope" not in response.text


def test_sqlite_write_failure_returns_redacted_may_be_durable_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_start(*_args, **_kwargs):
        raise sqlite3.OperationalError(
            "PRIVATE /Users/learner/Keen.sqlite3 database is locked"
        )

    monkeypatch.setattr(AutonomousStudySessionService, "start_or_resume", fail_start)
    response = _start(client, "task-private-failure")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "autonomous_study_session_temporarily_unavailable"
    assert detail["retryable"] is True
    assert detail["automaticRecovery"] is False
    assert detail["outcomeMayBeDurable"] is True
    assert "PRIVATE" not in response.text
    assert "sqlite" not in response.text.casefold()
    assert "locked" not in response.text.casefold()
