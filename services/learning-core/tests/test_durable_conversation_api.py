from __future__ import annotations

import json
import sqlite3
import time
import uuid
from base64 import urlsafe_b64encode
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.chat_interfaces import ChatMessage, ChatModel
from app.database import Database
from app.main import create_app
from app.repositories.conversation_repository import ConversationRepository
from app.settings import LocalChatSettings, Settings

TOKEN = "0123456789abcdef0123456789abcdef"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class _FakeChatProvider:
    @property
    def model(self) -> ChatModel:
        return ChatModel(provider="ollama", model="fixture-chat", version="v1")

    async def stream(self, messages: tuple[ChatMessage, ...]) -> AsyncIterator[str]:
        assert messages
        yield "A matrix preserves an eigenvector direction [[source:1]]."

    async def aclose(self) -> None:
        return None


def _settings(root: Path, *, provider: bool = True) -> Settings:
    local_chat = (
        LocalChatSettings(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="fixture-chat",
            version="v1",
        )
        if provider
        else None
    )
    return Settings(
        session_token=TOKEN,
        database_path=root / "learning.sqlite3",
        document_data_path=root / "documents",
        seed_demo=True,
        local_chat=local_chat,
    )


def _create_payload(
    conversation_id: str, question: str = "What is an eigenvector?"
) -> dict:
    return {
        "id": conversation_id,
        "question": question,
        "sourceScope": {"kind": "course", "courseId": "course-calculus"},
    }


def _turn_payload(question: str = "What is an eigenvector?") -> dict:
    return {
        "question": question,
        "idempotencyKey": f"answer:{uuid.uuid4()}",
        "userMessageId": str(uuid.uuid4()),
        "assistantMessageId": str(uuid.uuid4()),
        "sourceScope": {"kind": "course", "courseId": "course-calculus"},
        "retrievalLimit": 8,
    }


def _events(response) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    event: str | None = None
    for line in response.iter_lines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            assert event is not None
            parsed.append((event, json.loads(line.removeprefix("data: "))))
            event = None
    return parsed


def _upload_and_wait(client: TestClient) -> None:
    response = client.post(
        "/v1/documents/import",
        headers=HEADERS,
        files={
            "file": (
                "eigenvectors.txt",
                b"An eigenvector keeps its direction under a linear transformation.",
                "text/plain",
            )
        },
        data={"course_id": "course-calculus"},
    )
    assert response.status_code == 202
    job_id = response.json()["job"]["id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/v1/index-jobs/{job_id}", headers=HEADERS).json()
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            assert job["status"] == "completed"
            return
        time.sleep(0.02)
    raise AssertionError("indexing did not complete")


def test_create_is_authenticated_strict_idempotent_and_readable(tmp_path) -> None:
    conversation_id = str(uuid.uuid4())
    with TestClient(create_app(_settings(tmp_path))) as client:
        unauthenticated = client.post("/v1/conversations", json={"unexpected": True})
        assert unauthenticated.status_code == 401

        created = client.post(
            "/v1/conversations",
            headers=HEADERS,
            json=_create_payload(conversation_id),
        )
        replayed = client.post(
            "/v1/conversations",
            headers=HEADERS,
            json=_create_payload(conversation_id),
        )
        conflict = client.post(
            "/v1/conversations",
            headers=HEADERS,
            json=_create_payload(conversation_id, "Changed payload"),
        )
        strict = client.post(
            "/v1/conversations",
            headers=HEADERS,
            json={**_create_payload(str(uuid.uuid4())), "extra": True},
        )
        restored = client.get(f"/v1/conversations/{conversation_id}", headers=HEADERS)
        missing = client.get(f"/v1/conversations/{uuid.uuid4()}", headers=HEADERS)
        oversized = client.post(
            "/v1/conversations",
            headers={**HEADERS, "Content-Type": "application/json"},
            content=json.dumps({"padding": "x" * (64 * 1024)}),
        )

    assert created.status_code == 201
    assert created.json()["replayed"] is False
    assert replayed.status_code == 200
    assert replayed.json()["replayed"] is True
    assert conflict.status_code == 409
    assert strict.status_code == 422
    assert restored.status_code == 200
    assert restored.json()["sourceScope"] == {
        "kind": "course",
        "courseId": "course-calculus",
    }
    assert missing.status_code == 404
    assert oversized.status_code == 413


def test_stream_commits_turn_and_citation_before_done_then_restores(tmp_path) -> None:
    settings = _settings(tmp_path)
    conversation_id = str(uuid.uuid4())
    app = create_app(
        settings, chat_provider_factory=lambda _settings: _FakeChatProvider()
    )
    with TestClient(app) as client:
        _upload_and_wait(client)
        assert (
            client.post(
                "/v1/conversations",
                headers=HEADERS,
                json=_create_payload(conversation_id),
            ).status_code
            == 201
        )
        turn = _turn_payload()
        streamed = client.post(
            f"/v1/conversations/{conversation_id}/answers/stream",
            headers=HEADERS,
            json=turn,
        )
        events = _events(streamed)
        restored = client.get(
            f"/v1/conversations/{conversation_id}/messages", headers=HEADERS
        )
        replayed_stream = client.post(
            f"/v1/conversations/{conversation_id}/answers/stream",
            headers=HEADERS,
            json=turn,
        )
        replayed_events = _events(replayed_stream)

    assert streamed.status_code == 200
    assert events[0][0] == "metadata"
    assert events[0][1]["runId"] == turn["assistantMessageId"]
    assert events[0][1]["assistantMessageId"] == turn["assistantMessageId"]
    assert events[-1][0] == "done"
    assert replayed_events[0][1]["replayed"] is True
    assert replayed_events[-1][0] == "done"
    messages = restored.json()["messages"]
    assert [message["sequence"] for message in messages] == [0, 1]
    assert messages[0]["id"] == turn["userMessageId"]
    assistant = messages[1]
    assert assistant["id"] == turn["assistantMessageId"]
    assert assistant["status"] == "completed"
    assert assistant["replyToMessageId"] == turn["userMessageId"]
    assert assistant["finishedAt"] is not None
    assert len(assistant["citations"]) == 1
    citation = assistant["citations"][0]
    assert citation["documentVersionId"]
    assert len(citation["chunkContentHash"]) == 64
    assert citation["documentName"] == "eigenvectors.txt"
    with Database(settings.database_path).connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0

    # A new app process over the same database restores the authoritative turn.
    with TestClient(create_app(settings)) as restarted:
        after_restart = restarted.get(
            f"/v1/conversations/{conversation_id}/messages/{turn['assistantMessageId']}",
            headers=HEADERS,
        )
    assert after_restart.status_code == 200
    assert after_restart.json()["status"] == "completed"
    assert after_restart.json()["citations"] == assistant["citations"]


def test_provider_failure_and_server_cancel_are_durable_authoritative_states(
    tmp_path,
) -> None:
    settings = _settings(tmp_path, provider=False)
    conversation_id = str(uuid.uuid4())
    with TestClient(create_app(settings)) as client:
        _upload_and_wait(client)
        client.post(
            "/v1/conversations",
            headers=HEADERS,
            json=_create_payload(conversation_id),
        )
        failed_turn = _turn_payload()
        failed = client.post(
            f"/v1/conversations/{conversation_id}/answers/stream",
            headers=HEADERS,
            json=failed_turn,
        )
        assert _events(failed)[-1][1]["code"] == "provider_missing"
        failed_message = client.get(
            f"/v1/conversations/{conversation_id}/messages/{failed_turn['assistantMessageId']}",
            headers=HEADERS,
        ).json()
        assert failed_message["status"] == "failed"
        assert failed_message["citations"] == []

        pending_turn = _turn_payload("Cancel this answer")
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_turn(
                conversation_id=conversation_id,
                user_message_id=pending_turn["userMessageId"],
                assistant_message_id=pending_turn["assistantMessageId"],
                question=pending_turn["question"],
                source_scope_kind="course",
                source_course_id="course-calculus",
                retrieval_limit=8,
                idempotency_key=pending_turn["idempotencyKey"],
                prompt_version="grounded-answer-v1",
            )
        in_progress = client.post(
            f"/v1/conversations/{conversation_id}/answers/stream",
            headers=HEADERS,
            json=pending_turn,
        )
        different_ids = client.post(
            f"/v1/conversations/{conversation_id}/answers/stream",
            headers=HEADERS,
            json={
                **pending_turn,
                "userMessageId": str(uuid.uuid4()),
                "assistantMessageId": str(uuid.uuid4()),
            },
        )
        cancel_key = f"cancel:{uuid.uuid4()}"
        cancelled = client.post(
            f"/v1/conversations/{conversation_id}/messages/{pending_turn['assistantMessageId']}/cancel",
            headers=HEADERS,
            json={"idempotencyKey": cancel_key},
        )
        replay = client.post(
            f"/v1/conversations/{conversation_id}/messages/{pending_turn['assistantMessageId']}/cancel",
            headers=HEADERS,
            json={"idempotencyKey": cancel_key},
        )

    assert cancelled.status_code == 200
    assert in_progress.status_code == 409
    assert in_progress.json()["detail"]["code"] == "answer_in_progress"
    assert different_ids.status_code == 409
    assert different_ids.json()["detail"]["code"] == "answer_idempotency_conflict"
    assert cancelled.json()["message"]["status"] == "cancelled"
    assert cancelled.json()["replayed"] is False
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True


def test_terminal_commit_failure_never_emits_done_and_reconciles_interrupted(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    conversation_id = str(uuid.uuid4())
    app = create_app(
        settings, chat_provider_factory=lambda _settings: _FakeChatProvider()
    )
    with TestClient(app) as setup_client:
        _upload_and_wait(setup_client)
        setup_client.post(
            "/v1/conversations",
            headers=HEADERS,
            json=_create_payload(conversation_id),
        )

    def fail_completion(*_args, **_kwargs):
        raise sqlite3.OperationalError("forced terminal commit failure")

    monkeypatch.setattr(ConversationRepository, "complete_message", fail_completion)
    turn = _turn_payload()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/v1/conversations/{conversation_id}/answers/stream",
            headers=HEADERS,
            json=turn,
        )
        events = _events(response)
        reconciled = client.get(
            f"/v1/conversations/{conversation_id}/messages/{turn['assistantMessageId']}",
            headers=HEADERS,
        )

    assert not any(name == "done" for name, _data in events)
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "interrupted"


def test_conversation_history_is_stable_bounded_scoped_and_redacted(tmp_path) -> None:
    settings = _settings(tmp_path, provider=False)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    with TestClient(create_app(settings)) as client:
        for conversation_id in ids[:2]:
            assert (
                client.post(
                    "/v1/conversations",
                    headers=HEADERS,
                    json=_create_payload(
                        conversation_id, f"Question {conversation_id}"
                    ),
                ).status_code
                == 201
            )
        assert (
            client.post(
                "/v1/conversations",
                headers=HEADERS,
                json={
                    "id": ids[2],
                    "question": "Question across all indexed sources",
                    "sourceScope": {"kind": "all_indexed"},
                },
            ).status_code
            == 201
        )

        with Database(settings.database_path).connection() as connection:
            repository = ConversationRepository(connection)
            turn = repository.create_turn(
                conversation_id=ids[0],
                user_message_id=str(uuid.uuid4()),
                assistant_message_id=str(uuid.uuid4()),
                question="A learner prompt that is safe to preview " + "x" * 300,
                source_scope_kind="course",
                source_course_id="course-calculus",
                retrieval_limit=8,
                idempotency_key=f"answer:{uuid.uuid4()}",
            )
            repository.transition_message(
                turn["assistant_message"]["id"],
                status="failed",
                expected_statuses=("pending",),
                error_code="provider_missing",
                error_detail="private provider configuration detail",
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id IN (?, ?)",
                ("2026-07-21T12:00:00+00:00", ids[0], ids[1]),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                ("2026-07-20T12:00:00+00:00", ids[2]),
            )
            connection.commit()

        unauthenticated_invalid = client.get("/v1/conversations?cursor=not-a-cursor")
        invalid_cursor = client.get(
            "/v1/conversations?cursor=not-a-cursor", headers=HEADERS
        )
        semantic_cursor = (
            urlsafe_b64encode(
                json.dumps(
                    {
                        "version": 1,
                        "updatedAt": "not-a-date",
                        "id": "not-a-uuid",
                        "courseId": None,
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            .decode("ascii")
            .rstrip("=")
        )
        invalid_semantic_cursor = client.get(
            "/v1/conversations", headers=HEADERS, params={"cursor": semantic_cursor}
        )
        unknown_query = client.get("/v1/conversations?unexpected=true", headers=HEADERS)
        first = client.get("/v1/conversations?limit=2", headers=HEADERS)
        first_body = first.json()
        filter_drift = client.get(
            "/v1/conversations",
            headers=HEADERS,
            params={
                "cursor": first_body["nextCursor"],
                "course_id": "course-calculus",
            },
        )
        second = client.get(
            "/v1/conversations",
            headers=HEADERS,
            params={"limit": 2, "cursor": first_body["nextCursor"]},
        )
        scoped = client.get(
            "/v1/conversations?limit=50&course_id=course-calculus", headers=HEADERS
        )

    assert unauthenticated_invalid.status_code == 401
    assert invalid_cursor.status_code == 422
    assert invalid_semantic_cursor.status_code == 422
    assert filter_drift.status_code == 422
    assert unknown_query.status_code == 422
    assert first.status_code == 200
    assert first_body["nextCursor"]
    first_ids = [item["id"] for item in first_body["conversations"]]
    assert first_ids == sorted(ids[:2], reverse=True)
    second_ids = [item["id"] for item in second.json()["conversations"]]
    assert second_ids == [ids[2]]
    assert not set(first_ids) & set(second_ids)
    failed = next(item for item in first_body["conversations"] if item["id"] == ids[0])
    assert failed["answerStatus"] == "failed"
    assert failed["messageCount"] == 2
    assert len(failed["lastMessagePreview"]) <= 160
    assert "content" not in failed
    assert "provider" not in json.dumps(failed).lower()
    assert "private provider configuration detail" not in json.dumps(first_body)
    scoped_body = scoped.json()
    assert {item["id"] for item in scoped_body["conversations"]} == set(ids[:2])
    assert all(
        item["sourceScope"]["kind"] == "course" for item in scoped_body["conversations"]
    )
