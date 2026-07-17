from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
import sqlite3
from threading import Barrier, Lock

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.request_guard import (
    BOUNDED_JSON_PATHS,
    SMALL_JSON_REQUEST_BYTES,
    RequestGuardMiddleware,
)
from app.services.autonomous_study_session import AutonomousStudySessionService
from app.services.study_session_read import (
    StudySessionReadResult,
    StudySessionReadService,
)
from app.routers.autonomous_study_sessions import _read_response
from app.schemas import AutonomousStudyTaskResponse

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


def _read_session(client: TestClient, session_id: str, *, course_id: str = COURSE_ID):
    return client.get(
        f"/v1/study-sessions/{session_id}",
        headers=AUTH,
        params={"course_id": course_id},
    )


def test_autonomous_study_task_response_bounds_source_id_without_rejecting_empty_legacy_value() -> None:
    task = {
        "id": "task-source-id-contract",
        "course_id": COURSE_ID,
        "concept_id": None,
        "title": "Legacy task",
        "reason": "Read a historical task without changing it.",
        "estimated_minutes": 20,
        "status": "upcoming",
        "source_type": "manual",
    }

    assert AutonomousStudyTaskResponse.model_validate(
        {**task, "source_id": ""}
    ).source_id == ""
    with pytest.raises(ValidationError):
        AutonomousStudyTaskResponse.model_validate(
            {**task, "source_id": "x" * 129}
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
        "source_id": CONCEPT_ID,
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

    restored = _read_session(client, body["session"]["id"])
    assert restored.status_code == 200
    restored_body = restored.json()
    assert restored_body["outcome"] == "ready"
    assert restored_body["course_id"] == COURSE_ID
    assert restored_body["session"] == body["session"]
    assert restored_body["plan"] == body["plan"]
    assert restored_body["current_unit_id"] is None
    assert restored_body["recovery_action"] is None
    assert "private-path-must-not-leak" not in restored.text
    assert "goal_scope" not in restored.text


def test_start_api_resumes_named_source_session_and_exposes_source_id(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    with client.app.state.database.connection() as connection:
        session = StudyRepository(connection).create_session(
            session_id="source-session-api",
            course_id=COURSE_ID,
            title="Existing source-grounded work",
            mode="study",
            goal="Continue the existing work.",
            estimated_minutes=20,
            created_at=NOW,
        )
    _task(
        client,
        task_id="task-api-resume-source",
        source_type="study_session",
        source_id=session["id"],
    )

    response = _start(client, "task-api-resume-source")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "resumed"
    assert body["task"]["source_type"] == "study_session"
    assert body["task"]["source_id"] == body["session"]["id"]


def test_read_session_returns_typed_plan_unavailable_without_fabricating_work(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    with client.app.state.database.connection() as connection:
        StudyRepository(connection).create_session(
            session_id="session-without-plan",
            course_id=COURSE_ID,
            title="Session awaiting a real plan",
            mode="study",
            goal="Wait for source-grounded planning.",
            estimated_minutes=20,
            created_at=NOW,
        )

    response = _read_session(client, "session-without-plan")
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "plan_unavailable",
        "course_id": COURSE_ID,
        "session": {
            "id": "session-without-plan",
            "course_id": COURSE_ID,
            "originating_task_id": None,
            "title": "Session awaiting a real plan",
            "mode": "study",
            "goal": "Wait for source-grounded planning.",
            "estimated_minutes": 20,
            "status": "draft",
            "progress": 0.0,
            "revision": 0,
            "created_at": "2026-07-17T09:00:00Z",
            "updated_at": "2026-07-17T09:00:00Z",
            "started_at": None,
        },
        "plan": None,
        "current_unit_id": None,
        "recovery_action": (
            "Return to the learning feed and start a source-grounded recommendation."
        ),
    }


def test_read_session_hides_not_found_and_cross_course_identically(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    with client.app.state.database.connection() as connection:
        StudyRepository(connection).create_session(
            session_id="foreign-secret-session",
            course_id=COURSE_ID,
            title="FOREIGN SECRET TITLE",
            mode="study",
            goal="FOREIGN SECRET GOAL",
            estimated_minutes=20,
            created_at=NOW,
        )

    missing = _read_session(client, "missing-session", course_id="course-other")
    outside = _read_session(client, "foreign-secret-session", course_id="course-other")
    assert missing.status_code == outside.status_code == 404
    assert missing.json() == outside.json()
    for secret in (
        COURSE_ID,
        "foreign-secret-session",
        "FOREIGN SECRET TITLE",
        "FOREIGN SECRET GOAL",
    ):
        assert secret not in outside.text


def test_read_session_authenticates_before_path_and_query_validation(
    client: TestClient,
) -> None:
    assert (
        client.get(
            "/v1/study-sessions/invalid%20id?course_id=invalid%20course"
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/v1/study-sessions/invalid%20id",
            headers=AUTH,
            params={"course_id": COURSE_ID},
        ).status_code
        == 422
    )


def test_read_session_corrupt_unit_relationship_returns_redacted_503(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id="task-api-corrupt-read")
    created = _start(client, "task-api-corrupt-read")
    session_id = created.json()["session"]["id"]
    with client.app.state.database.connection() as connection:
        connection.execute(
            "INSERT INTO courses (id, title, description, created_at) VALUES (?, ?, '', ?)",
            ("course-foreign-secret", "FOREIGN SECRET COURSE", NOW),
        )
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name, bkt_slip, bkt_guess, bkt_transit)
            VALUES (?, ?, ?, 0.1, 0.2, 0.1)
            """,
            (
                "concept-foreign-secret",
                "course-foreign-secret",
                "FOREIGN SECRET CONCEPT",
            ),
        )
        connection.execute(
            """
            UPDATE study_units
            SET concept_id = NULL, concept_ids_json = '["concept-foreign-secret"]'
            WHERE plan_version_id = ? AND ordinal = 0
            """,
            (created.json()["plan"]["id"],),
        )
        connection.commit()

    response = _read_session(client, session_id)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "study_session_temporarily_unavailable"
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            UPDATE study_units
            SET concept_id = ?, concept_ids_json = ?,
                source_chunk_ids_json = '["missing-secret-source-chunk"]'
            WHERE plan_version_id = ? AND ordinal = 0
            """,
            (CONCEPT_ID, f'["{CONCEPT_ID}"]', created.json()["plan"]["id"]),
        )
        connection.commit()
    source_response = _read_session(client, session_id)
    assert source_response.status_code == 503
    assert (
        source_response.json()["detail"]["code"]
        == "study_session_temporarily_unavailable"
    )
    for secret in (
        session_id,
        "course-foreign-secret",
        "concept-foreign-secret",
        "FOREIGN SECRET COURSE",
        "FOREIGN SECRET CONCEPT",
        "missing-secret-source-chunk",
    ):
        assert secret not in response.text
        assert secret not in source_response.text


def test_read_session_get_keeps_one_snapshot_during_concurrent_current_unit_update(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id="task-api-snapshot")
    created = _start(client, "task-api-snapshot").json()
    session_id = created["session"]["id"]
    current_unit_id = created["plan"]["units"][0]["id"]
    with client.app.state.database.connection() as connection:
        StudyRepository(connection).save_plan(
            plan_id="snapshot-plan-v2",
            session_id=session_id,
            version=2,
            rationale="A later plan used to verify snapshot selection.",
            units=[
                {
                    "id": f"snapshot-v2-unit-{ordinal}",
                    "title": unit["title"],
                    "objective": unit["objective"],
                    "content": unit["content"],
                    "estimated_minutes": unit["estimated_minutes"],
                    "concept_id": unit["concept_id"],
                    "concept_ids": unit["concept_ids"],
                    "source_chunk_ids": unit["source_chunk_ids"],
                    "status": unit["status"],
                }
                for ordinal, unit in enumerate(created["plan"]["units"])
            ],
        )

    session_read = Barrier(2, timeout=5)
    writer_committed = Barrier(2, timeout=5)
    pause_lock = Lock()
    should_pause = True
    original = StudyRepository.get_current_or_latest_plan

    def pause_after_session_read(repository: StudyRepository, selected_id: str):
        nonlocal should_pause
        with pause_lock:
            pause = should_pause and selected_id == session_id
            if pause:
                should_pause = False
        if pause:
            session_read.wait()
            writer_committed.wait()
        return original(repository, selected_id)

    monkeypatch.setattr(
        StudyRepository,
        "get_current_or_latest_plan",
        pause_after_session_read,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(_read_session, client, session_id)
        session_read.wait()
        with client.app.state.database.connection() as writer:
            writer.execute(
                """
                UPDATE study_sessions
                SET current_unit_id = ?, revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (current_unit_id, NOW, session_id),
            )
            writer.commit()
        writer_committed.wait()
        first = pending.result(timeout=5)

    assert first.status_code == 200
    assert first.json()["current_unit_id"] is None
    assert first.json()["plan"]["id"] == "snapshot-plan-v2"

    second = _read_session(client, session_id)
    assert second.status_code == 200
    assert second.json()["current_unit_id"] == current_unit_id
    assert second.json()["plan"]["id"] == created["plan"]["id"]


def test_read_response_rejects_inconsistent_service_results(
    client: TestClient,
) -> None:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id="task-api-invalid-read-result")
    created = _start(client, "task-api-invalid-read-result").json()
    with client.app.state.database.connection() as connection:
        valid = StudySessionReadService(connection).get(
            course_id=COURSE_ID, session_id=created["session"]["id"]
        )
    assert isinstance(valid, StudySessionReadResult)
    assert valid.plan is not None
    plan_outside_session = {
        **valid.plan,
        "session_id": "session-outside-result",
    }
    invalid_results = [
        replace(valid, course_id="course-outside-result"),
        replace(
            valid,
            session={**valid.session, "course_id": "course-outside-result"},
        ),
        replace(valid, outcome="unknown"),  # type: ignore[arg-type]
        replace(valid, plan=None),
        replace(valid, outcome="plan_unavailable"),
        replace(valid, plan=plan_outside_session),
        replace(valid, current_unit_id="unit-outside-result"),
    ]

    for invalid in invalid_results:
        with pytest.raises(ValueError):
            _read_response(invalid)


def test_read_endpoint_maps_inconsistent_service_result_to_redacted_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id="task-api-invalid-read-mapping")
    created = _start(client, "task-api-invalid-read-mapping").json()
    with client.app.state.database.connection() as connection:
        valid = StudySessionReadService(connection).get(
            course_id=COURSE_ID, session_id=created["session"]["id"]
        )
    assert isinstance(valid, StudySessionReadResult)
    invalid = replace(valid, course_id="course-secret-inconsistent-result")
    monkeypatch.setattr(
        StudySessionReadService,
        "get",
        lambda *_args, **_kwargs: invalid,
    )

    response = _read_session(client, created["session"]["id"])
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "study_session_temporarily_unavailable"
    assert "course-secret-inconsistent-result" not in response.text
    assert created["session"]["id"] not in response.text


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
        "missing-task": ("task_not_found", None),
        "task-api-completed": ("task_not_actionable", CONCEPT_ID),
        "task-api-manual": ("task_not_autonomous", CONCEPT_ID),
        "task-api-no-concept": ("task_missing_concept", None),
        "task-api-no-source": ("no_indexed_source", CONCEPT_ID),
        "task-api-missing-source-session": (
            "source_session_unavailable",
            "unavailable-source-session",
        ),
        "task-api-terminal": ("originating_session_terminal", CONCEPT_ID),
    }
    for task_id, (reason, source_id) in samples.items():
        response = _start(client, task_id)
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "blocked"
        assert body["blocked_reason"] == reason
        if task_id == "missing-task":
            assert body["task"] is None
        else:
            assert body["task"] is not None
            assert body["task"]["source_id"] == source_id
        assert body["session"] is None
        assert body["plan"] is None
        assert body["recovery_action"]

    outside = _start(client, "task-api-no-source", course_id="course-other")
    assert outside.status_code == 200
    assert outside.json()["outcome"] == "blocked"
    assert outside.json()["blocked_reason"] == "task_outside_course"
    assert outside.json()["task"] is None
    assert COURSE_ID not in outside.text
    assert CONCEPT_ID not in outside.text
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
