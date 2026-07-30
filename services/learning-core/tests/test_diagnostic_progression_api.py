"""HTTP contract coverage for the non-scored diagnostic progression."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

from app.request_guard import SMALL_JSON_REQUEST_BYTES, RequestGuardMiddleware
from app.services.diagnostic_progression import DiagnosticProgressionService
from conftest import TOKEN
from test_autonomous_study_session_api import (
    AUTH,
    COURSE_ID,
    _course_and_concept,
    _indexed_source,
    _start,
    _task,
)


def _new_session(client: TestClient, task_id: str = "task-diagnostic-contract") -> dict:
    _course_and_concept(client)
    _indexed_source(client)
    _task(client, task_id=task_id)
    created = _start(client, task_id)
    assert created.status_code == 201
    return created.json()["session"]


def _begin(
    client: TestClient, session: dict, key: str = "diagnostic-begin-contract-key"
):
    return client.post(
        f"/v1/study-sessions/{session['id']}/diagnostic",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": key,
        },
    )


def _answer(
    client: TestClient, begun: dict, key: str = "diagnostic-answer-contract-key"
):
    return client.post(
        f"/v1/study-sessions/{begun['session']['id']}/diagnostic/{begun['checkpoint']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": begun["session"]["revision"],
            "idempotency_key": key,
            "response": "I understand the idea but need a short refresher.",
            "self_assessment": "partial",
        },
    )


def _get(client: TestClient, session_id: str, *, course_id: str = COURSE_ID):
    return client.get(
        f"/v1/study-sessions/{session_id}/diagnostic",
        headers=AUTH,
        params={"course_id": course_id},
    )


def test_diagnostic_http_progression_replays_conflicts_and_never_echoes_response(
    client: TestClient,
) -> None:
    session = _new_session(client)
    assert _get(client, session["id"]).json()["outcome"] == "not_started"

    begun = _begin(client, session)
    assert begun.status_code == 201
    begin_body = begun.json()
    assert _get(client, session["id"]).json()["outcome"] == "pending"

    replay_begin = _begin(client, session)
    assert replay_begin.status_code == 200
    assert replay_begin.json()["outcome"] == "replayed"

    stale = client.post(
        f"/v1/study-sessions/{session['id']}/diagnostic/{begin_body['checkpoint']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": "diagnostic-answer-stale-key",
            "response": "A deliberately stale attempt.",
            "self_assessment": "partial",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "study_diagnostic_conflict"

    answered = _answer(client, begin_body)
    assert answered.status_code == 201
    assert answered.json()["outcome"] == "applied"
    assert answered.json()["mastery_changed"] is False
    assert "response" not in answered.text
    restored = _get(client, session["id"])
    assert restored.status_code == 200
    assert restored.json()["outcome"] == "answered"
    assert "response" not in restored.text

    replay_answer = _answer(client, begin_body)
    assert replay_answer.status_code == 200
    assert replay_answer.json()["outcome"] == "replayed"
    different_payload = client.post(
        f"/v1/study-sessions/{session['id']}/diagnostic/{begin_body['checkpoint']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": begin_body["session"]["revision"],
            "idempotency_key": "diagnostic-answer-contract-key",
            "response": "This must not replace the saved answer.",
            "self_assessment": "confident",
        },
    )
    assert different_payload.status_code == 409


def test_diagnostic_scope_and_validation_are_fail_closed(client: TestClient) -> None:
    session = _new_session(client, "task-diagnostic-scope-contract")
    begun = _begin(client, session).json()
    foreign_begin = client.post(
        f"/v1/study-sessions/{session['id']}/diagnostic",
        headers=AUTH,
        json={
            "course_id": "course-foreign",
            "expected_revision": session["revision"],
            "idempotency_key": "diagnostic-foreign-known-key",
        },
    )
    missing_begin = client.post(
        "/v1/study-sessions/missing-session/diagnostic",
        headers=AUTH,
        json={
            "course_id": "course-foreign",
            "expected_revision": session["revision"],
            "idempotency_key": "diagnostic-foreign-known-key",
        },
    )
    assert foreign_begin.status_code == missing_begin.status_code == 404
    assert foreign_begin.json() == missing_begin.json()

    foreign_answer = client.post(
        f"/v1/study-sessions/{session['id']}/diagnostic/{begun['checkpoint']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": "course-foreign",
            "expected_revision": begun["session"]["revision"],
            "idempotency_key": "diagnostic-foreign-answer-key",
            "response": "A scoped answer.",
            "self_assessment": "partial",
        },
    )
    missing_answer = client.post(
        "/v1/study-sessions/missing-session/diagnostic/missing-checkpoint/answer",
        headers=AUTH,
        json={
            "course_id": "course-foreign",
            "expected_revision": begun["session"]["revision"],
            "idempotency_key": "diagnostic-foreign-answer-key",
            "response": "A scoped answer.",
            "self_assessment": "partial",
        },
    )
    assert foreign_answer.status_code == missing_answer.status_code == 404
    assert foreign_answer.json() == missing_answer.json()

    for payload in (
        {"course_id": COURSE_ID, "expected_revision": 0, "idempotency_key": "short"},
        {
            "course_id": COURSE_ID,
            "expected_revision": 0,
            "idempotency_key": "bad key with spaces",
        },
        {
            "course_id": COURSE_ID,
            "expected_revision": 0,
            "idempotency_key": "diagnostic-extra-key",
            "extra": True,
        },
    ):
        assert (
            client.post(
                f"/v1/study-sessions/{session['id']}/diagnostic",
                headers=AUTH,
                json=payload,
            ).status_code
            == 422
        )


def test_diagnostic_body_guard_authenticates_before_reading_and_caps_chunked_stream() -> (
    None
):
    path = "/v1/study-sessions/session-guard/diagnostic"
    reads = 0
    sent: list[dict] = []

    async def unauthorized_receive() -> dict:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"x", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(*_args) -> None:  # pragma: no cover - must not run
        raise AssertionError("unauthorized diagnostic body reached FastAPI")

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


def test_diagnostic_router_errors_are_typed_and_unknown_write_converges(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _new_session(client, "task-diagnostic-router-contract")
    original_get = DiagnosticProgressionService.get

    def forged_get(self, **kwargs):
        result = original_get(self, **kwargs)
        return replace(result, course_id="course-forged")

    monkeypatch.setattr(DiagnosticProgressionService, "get", forged_get)
    read_failure = _get(client, session["id"])
    assert read_failure.status_code == 503
    assert "outcomeMayBeDurable" not in read_failure.json()["detail"]
    monkeypatch.setattr(DiagnosticProgressionService, "get", original_get)

    original_begin = DiagnosticProgressionService.begin

    def save_then_fail(self, **kwargs):
        original_begin(self, **kwargs)
        raise RuntimeError("synthetic unknown after durable commit")

    monkeypatch.setattr(DiagnosticProgressionService, "begin", save_then_fail)
    uncertain = _begin(client, session, "diagnostic-unknown-commit-key")
    assert uncertain.status_code == 503
    assert uncertain.json()["detail"]["outcomeMayBeDurable"] is True
    monkeypatch.setattr(DiagnosticProgressionService, "begin", original_begin)
    assert _get(client, session["id"]).json()["outcome"] == "pending"
    replay = _begin(client, session, "diagnostic-unknown-commit-key")
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "replayed"
