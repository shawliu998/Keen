"""HTTP contracts for deterministic targeted practice."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json

from fastapi.testclient import TestClient
import pytest

from app.request_guard import SMALL_JSON_REQUEST_BYTES, RequestGuardMiddleware
from app.repositories.study_repository import StudyRepository
from conftest import TOKEN
from test_active_recall_api import AUTH
from test_targeted_practice_service import _ready_for_practice


COURSE_ID = "course-calculus"


def _ready_practice(client: TestClient) -> tuple[dict, dict]:
    session_id, revision = _ready_for_practice(client.app.state.database)
    restored = _get_practice(client, session_id)
    assert restored.status_code == 200
    session = restored.json()["session"]
    assert session["revision"] == revision
    return session, restored.json()


def _begin_practice(
    client: TestClient, session: dict, key: str = "practice-begin-api-001"
):
    return client.post(
        f"/v1/study-sessions/{session['id']}/practice",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": key,
        },
    )


def _get_practice(client: TestClient, session_id: str, course_id: str = COURSE_ID):
    return client.get(
        f"/v1/study-sessions/{session_id}/practice",
        headers=AUTH,
        params={"course_id": course_id},
    )


def test_practice_http_begin_answer_replay_restore_and_safe_projection(
    client: TestClient,
) -> None:
    session, _ = _ready_practice(client)
    assert _get_practice(client, session["id"]).json()["outcome"] == "not_started"
    begun = _begin_practice(client, session)
    assert begun.status_code == 201
    body = begun.json()
    assert _get_practice(client, session["id"]).json()["outcome"] == "pending"
    assert _begin_practice(client, session).status_code == 200
    wrong_revision = _begin_practice(
        client,
        {**session, "revision": session["revision"] + 1},
        "practice-wrong-revision-api-001",
    )
    assert wrong_revision.status_code == 409
    answer = client.post(
        f"/v1/study-sessions/{session['id']}/practice/{body['run']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": body["session"]["revision"],
            "idempotency_key": "practice-answer-api-001",
            "response": "not an answer",
        },
    )
    assert answer.status_code == 200
    assert answer.json()["outcome"] == "applied"
    assert answer.json()["grade"]["correct"] is False
    assert _get_practice(client, session["id"]).json()["outcome"] == "answered"
    assert (
        client.post(
            f"/v1/study-sessions/{session['id']}/practice/missing-run/answer",
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": body["session"]["revision"],
                "idempotency_key": "practice-missing-run-api-001",
                "response": "not an answer",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/study-sessions/{session['id']}/practice/{body['run']['id']}/answer",
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": body["session"]["revision"],
                "idempotency_key": "practice-answer-api-001",
                "response": "  NOT AN ANSWER ",
            },
        ).json()["outcome"]
        == "replayed"
    )
    serialized = json.dumps(answer.json()).casefold()
    for forbidden in (
        "answer_key",
        "source_chunk",
        "concept_id",
        "assessment_id",
        "item_id",
        "idempotency",
        "fingerprint",
        "not an answer",
    ):
        assert forbidden not in serialized


def test_practice_api_scope_strict_schema_and_guard(client: TestClient) -> None:
    session, _ = _ready_practice(client)
    foreign = _get_practice(client, session["id"], "course-foreign")
    missing = _get_practice(client, "missing-session", "course-foreign")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    for payload in (
        {
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": "short",
        },
        {
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": "practice-extra-api-001",
            "extra": True,
        },
    ):
        assert (
            client.post(
                f"/v1/study-sessions/{session['id']}/practice",
                headers=AUTH,
                json=payload,
            ).status_code
            == 422
        )

    path = "/v1/study-sessions/session-guard/practice"
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"x", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(*_args) -> None:
        raise AssertionError("unauthorized practice body reached FastAPI")

    asyncio.run(
        RequestGuardMiddleware(downstream, session_token=TOKEN, max_document_bytes=1)(
            {"type": "http", "method": "POST", "path": path, "headers": []},
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 401
    oversized = client.post(
        f"/v1/study-sessions/{session['id']}/practice",
        headers={**AUTH, "Content-Type": "application/json"},
        content=b"x" * (SMALL_JSON_REQUEST_BYTES + 1),
    )
    assert oversized.status_code == 413


@pytest.mark.parametrize("terminal_status", ["cancelled", "failed"])
def test_practice_api_restores_terminal_session_before_begin(
    client: TestClient, terminal_status: str
) -> None:
    session, _ = _ready_practice(client)
    with client.app.state.database.connection() as connection:
        StudyRepository(connection).transition_session(
            session["id"],
            status=terminal_status,
            expected_revision=session["revision"],
            updated_at=datetime.now(UTC).isoformat(),
        )

    response = _get_practice(client, session["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "cancelled"
    assert body["session"]["status"] == terminal_status
    assert body["session"]["finished_at"] is not None
    assert body["checkpoint"] is None
    assert body["run"] is None
    assert body["grade"] is None
