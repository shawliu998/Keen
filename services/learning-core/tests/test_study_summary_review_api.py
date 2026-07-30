"""HTTP boundary for the redacted, bounded recap handoff."""

from __future__ import annotations

import asyncio
import json

from app.request_guard import SMALL_JSON_REQUEST_BYTES, RequestGuardMiddleware
from conftest import TOKEN
from test_active_recall_api import AUTH
from test_targeted_practice_api import _begin_practice, _ready_practice


COURSE_ID = "course-calculus"


def _answered_practice(client):
    session, _ = _ready_practice(client)
    begun = _begin_practice(client, session).json()
    answer = client.post(
        f"/v1/study-sessions/{session['id']}/practice/{begun['run']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": begun["session"]["revision"],
            "idempotency_key": "practice-answer-summary-api-001",
            "response": "wrong",
        },
    )
    assert answer.status_code == 200
    studying = answer.json()["session"]
    assert studying["status"] == "studying"
    recall = client.post(
        f"/v1/study-sessions/{session['id']}/active-recall",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": studying["revision"],
            "idempotency_key": "active-recall-begin-summary-api-unit-2",
        },
    )
    assert recall.status_code == 201
    recall_body = recall.json()
    recalled = client.post(
        f"/v1/study-sessions/{session['id']}/active-recall/{recall_body['run']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": recall_body["session"]["revision"],
            "idempotency_key": "active-recall-answer-summary-api-unit-2",
            "response": "chain rule",
        },
    )
    assert recalled.status_code == 200
    practice = _begin_practice(
        client,
        recalled.json()["session"],
        "practice-begin-summary-api-unit-2",
    )
    assert practice.status_code == 201
    practice_body = practice.json()
    final_answer = client.post(
        f"/v1/study-sessions/{session['id']}/practice/{practice_body['run']['id']}/answer",
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": practice_body["session"]["revision"],
            "idempotency_key": "practice-answer-summary-api-unit-2",
            "response": "wrong",
        },
    )
    assert final_answer.status_code == 200
    return final_answer.json()["session"]


def test_summary_api_completes_once_and_hides_private_lineage(client) -> None:
    session = _answered_practice(client)
    url = f"/v1/study-sessions/{session['id']}/summary"
    ready = client.get(url, headers=AUTH, params={"course_id": COURSE_ID})
    assert ready.status_code == 200 and ready.json()["outcome"] == "ready"
    completed = client.post(
        url,
        headers=AUTH,
        json={
            "course_id": COURSE_ID,
            "expected_revision": session["revision"],
            "idempotency_key": "summary-complete-api-001",
        },
    )
    assert completed.status_code == 201
    body = completed.json()
    assert body["session"]["status"] == "completed"
    assert body["review"]["scheduler"] == "fsrs"
    assert body["summary"]["remaining_units"] == 0
    assert set(body["session"]) == {
        "id",
        "course_id",
        "status",
        "revision",
        "progress",
        "estimated_minutes",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    }
    assert set(body["summary"]) == {
        "active_recall_correct",
        "practice_correct",
        "practice_score",
        "practice_max_score",
        "task_completed",
        "remaining_units",
    }
    assert set(body["review"]) == {"due_at", "scheduler", "scheduler_version", "state"}
    serialized = json.dumps(body).casefold()
    for forbidden in (
        "answer_key",
        "source_chunk",
        "concept_id",
        "assessment_id",
        "item_id",
        "current_unit_id",
        "idempotency",
        "fingerprint",
    ):
        assert forbidden not in serialized
    assert (
        client.post(
            url,
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": session["revision"],
                "idempotency_key": "summary-complete-api-001",
            },
        ).json()["outcome"]
        == "replayed"
    )
    assert (
        client.post(
            url,
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": body["session"]["revision"],
                "idempotency_key": "summary-complete-other-api-001",
            },
        ).status_code
        == 409
    )


def test_summary_api_is_course_scoped_and_request_guarded(client) -> None:
    session = _answered_practice(client)
    url = f"/v1/study-sessions/{session['id']}/summary"
    assert (
        client.get(
            url, headers=AUTH, params={"course_id": "course-foreign"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            url,
            headers={**AUTH, "Content-Type": "application/json"},
            content=b"x" * (SMALL_JSON_REQUEST_BYTES + 1),
        ).status_code
        == 413
    )
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"x", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(*_args) -> None:
        raise AssertionError("unauthorized summary body reached FastAPI")

    asyncio.run(
        RequestGuardMiddleware(downstream, session_token=TOKEN, max_document_bytes=1)(
            {"type": "http", "method": "POST", "path": url, "headers": []},
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 401
