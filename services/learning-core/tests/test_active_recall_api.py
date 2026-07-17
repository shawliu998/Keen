"""HTTP contracts for source-grounded active recall."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.repositories.study_repository import StudyRepository
from app.request_guard import SMALL_JSON_REQUEST_BYTES, RequestGuardMiddleware
from app.services.active_recall_progression import ActiveRecallProgressionService
from conftest import TOKEN
from test_autonomous_study_session_api import (
    AUTH,
    COURSE_ID,
    _course_and_concept,
    _indexed_source,
    _start,
    _task,
)


def _ready_session(client: TestClient, task_id: str = "task-active-recall-api") -> dict:
    _course_and_concept(client)
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            INSERT INTO mastery (concept_id, probability, attempts, updated_at)
            VALUES ('concept-autonomous-api', 0.4, 0, ?)
            """,
            (datetime.now(UTC).isoformat(),),
        )
        connection.commit()
    _indexed_source(client)
    _task(client, task_id=task_id)
    created = _start(client, task_id)
    assert created.status_code == 201
    session = created.json()["session"]
    diagnostic = client.post(
        f"/v1/study-sessions/{session['id']}/diagnostic",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": "diagnostic-begin-active-api-001",
        },
    )
    assert diagnostic.status_code == 201
    diagnostic_body = diagnostic.json()
    answered = client.post(
        f"/v1/study-sessions/{session['id']}/diagnostic/{diagnostic_body['checkpoint']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": diagnostic_body["session"]["revision"],
            "idempotency_key": "diagnostic-answer-active-api-001",
            "response": "A bounded prior-knowledge reflection.",
            "self_assessment": "partial",
        },
    )
    assert answered.status_code == 201
    return answered.json()["session"]


def _begin(client: TestClient, session: dict, key: str = "active-recall-begin-api-001"):
    return client.post(
        f"/v1/study-sessions/{session['id']}/active-recall",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": key,
        },
    )


def _get(client: TestClient, session_id: str, *, course_id: str = COURSE_ID):
    return client.get(
        f"/v1/study-sessions/{session_id}/active-recall",
        headers=AUTH,
        params={"course_id": course_id},
    )


def _answer(client: TestClient, begun: dict, key: str = "active-recall-answer-api-001"):
    return client.post(
        f"/v1/study-sessions/{begun['session']['id']}/active-recall/{begun['run']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": begun["session"]["revision"],
            "idempotency_key": key,
            "response": "not-a-source-answer",
        },
    )


def test_active_recall_http_begin_answer_replay_and_safe_projection(
    client: TestClient,
) -> None:
    session = _ready_session(client)
    assert _get(client, session["id"]).json()["outcome"] == "not_started"

    begun = _begin(client, session)
    assert begun.status_code == 201
    begun_body = begun.json()
    assert _get(client, session["id"]).json()["outcome"] == "pending"

    replay_begin = _begin(client, session)
    assert replay_begin.status_code == 200
    assert replay_begin.json()["outcome"] == "replayed"

    answered = _answer(client, begun_body)
    # Answer updates the existing run, so the applied operation is 200.
    assert answered.status_code == 200
    body = answered.json()
    assert body["outcome"] == "applied"
    assert body["grade"]["correct"] is False
    restored = _get(client, session["id"])
    assert restored.status_code == 200
    assert restored.json()["outcome"] == "answered"

    replay_answer = _answer(client, begun_body)
    assert replay_answer.status_code == 200
    assert replay_answer.json()["outcome"] == "replayed"
    changed = client.post(
        f"/v1/study-sessions/{session['id']}/active-recall/{begun_body['run']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": begun_body["session"]["revision"],
            "idempotency_key": "active-recall-answer-api-001",
            "response": "different learner answer",
        },
    )
    assert changed.status_code == 409

    serialized = str(body).casefold()
    for forbidden in (
        "not-a-source-answer",
        "answer_key",
        "source_chunk",
        "concept_id",
        "assessment_id",
        "item_id",
        "idempotency",
        "fingerprint",
    ):
        assert forbidden not in serialized


def test_active_recall_scope_validation_and_cancelled_restore(
    client: TestClient,
) -> None:
    session = _ready_session(client, "task-active-recall-scope-api")
    begun = _begin(client, session).json()
    foreign = _get(client, session["id"], course_id="course-foreign")
    missing = _get(client, "missing-session", course_id="course-foreign")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()

    for payload in (
        {"course_id": COURSE_ID, "expected_revision": 0, "idempotency_key": "short"},
        {
            "course_id": COURSE_ID,
            "expected_revision": 0,
            "idempotency_key": "active-recall-extra-001",
            "unexpected": True,
        },
    ):
        assert (
            client.post(
                f"/v1/study-sessions/{session['id']}/active-recall",
                headers=AUTH,
                json=payload,
            ).status_code
            == 422
        )

    with client.app.state.database.connection() as connection:
        StudyRepository(connection).transition_session(
            session["id"],
            status="cancelled",
            expected_revision=begun["session"]["revision"],
            updated_at=datetime.now(UTC).isoformat(),
        )
    cancelled = _get(client, session["id"])
    assert cancelled.status_code == 200
    assert cancelled.json()["outcome"] == "cancelled"
    assert cancelled.json()["run"]["status"] == "cancelled"
    assert cancelled.json()["checkpoint"]["status"] == "skipped"
    replay_cancelled_begin = _begin(client, session)
    assert replay_cancelled_begin.status_code == 200
    assert replay_cancelled_begin.json()["outcome"] == "replayed"
    assert replay_cancelled_begin.json()["run"]["status"] == "cancelled"
    assert replay_cancelled_begin.json()["checkpoint"]["status"] == "skipped"


def test_active_recall_guard_authenticates_before_reading_and_caps_body() -> None:
    path = "/v1/study-sessions/session-guard/active-recall"
    reads = 0
    sent: list[dict] = []

    async def unauthorized_receive() -> dict:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"x", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(*_args) -> None:  # pragma: no cover - must not run
        raise AssertionError("unauthorized active-recall body reached FastAPI")

    middleware = RequestGuardMiddleware(
        downstream, session_token=TOKEN, max_document_bytes=1
    )
    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    asyncio.run(middleware(scope, unauthorized_receive, send))
    assert reads == 0
    assert sent[0]["status"] == 401

    chunks = [b"x" * SMALL_JSON_REQUEST_BYTES, b"x"]
    sent.clear()

    async def receive() -> dict:
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def consume(_scope, receive, _send) -> None:
        while (await receive()).get("more_body"):
            pass

    scope["headers"] = [(b"authorization", f"Bearer {TOKEN}".encode())]
    asyncio.run(
        RequestGuardMiddleware(consume, session_token=TOKEN, max_document_bytes=1)(
            scope, receive, send
        )
    )
    assert sent[0]["status"] == 413


def test_active_recall_router_redacts_unknown_write_failure_and_replay_converges(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _ready_session(client, "task-active-recall-unknown-api")
    original = ActiveRecallProgressionService.begin

    def save_then_fail(self, **kwargs):
        original(self, **kwargs)
        raise sqlite3.OperationalError("private active recall SQLite failure")

    monkeypatch.setattr(ActiveRecallProgressionService, "begin", save_then_fail)
    uncertain = _begin(client, session, "active-recall-unknown-write-001")
    assert uncertain.status_code == 503
    detail = uncertain.json()["detail"]
    assert detail["outcomeMayBeDurable"] is True
    assert "private active recall SQLite failure" not in str(detail)
    monkeypatch.setattr(ActiveRecallProgressionService, "begin", original)

    replay = _begin(client, session, "active-recall-unknown-write-001")
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "replayed"
