from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.agent.provider import (
    AgentProvider,
    ProviderAction,
    ProviderFinished,
    ProviderRequest,
    ProviderToolError,
    ToolCall,
)
from app.database import Database
from app.main import create_app
from app.repositories.agent_repository import AgentRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.task_repository import TaskRepository
from app.settings import Settings

TOKEN = "0123456789abcdef0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class _ProposalProvider(AgentProvider):
    name = "approval-test"
    model = "approval-test"
    version = "v1"

    def __init__(self, task_id: str, *, expected_revision: int = 0) -> None:
        self._task_id = task_id
        self._expected_revision = expected_revision

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]:
        del request
        yield ToolCall(
            call_id="propose-complete",
            tool_name="complete_study_task",
            arguments={
                "task_id": self._task_id,
                "expected_revision": self._expected_revision,
            },
        )
        yield ProviderFinished()

    async def submit_tool_result(self, _result: object) -> None:
        return None

    async def aclose(self) -> None:
        return None


class _RecoveringProposalProvider(_ProposalProvider):
    def __init__(self, task_id: str) -> None:
        super().__init__(task_id)
        self.feedback: list[object] = []

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]:
        del request
        yield ToolCall(
            call_id="invalid-proposal",
            tool_name="complete_study_task",
            arguments={
                "task_id": self._task_id,
                "expected_revision": 10**100,
            },
        )
        yield ToolCall(
            call_id="valid-proposal",
            tool_name="complete_study_task",
            arguments={"task_id": self._task_id, "expected_revision": 0},
        )
        yield ProviderFinished()

    async def submit_tool_result(self, result: object) -> None:
        self.feedback.append(result)


def _wait(client: TestClient, run_id: str, status: str) -> dict:
    for _ in range(100):
        run = client.get(f"/v1/agent/runs/{run_id}", headers=AUTH).json()
        if run["status"] == status:
            return run
        time.sleep(0.01)
    raise AssertionError(f"run did not become {status}")


def _create_run(client: TestClient, task_id: str) -> str:
    response = client.post(
        "/v1/agent/runs",
        headers=AUTH,
        json={
            "kind": "conversation",
            "userIntent": "Complete a task",
            "mode": "study",
            "input": {},
            "idempotencyKey": f"approval-{task_id}",
            "conversationId": "approval-conversation",
        },
    )
    assert response.status_code == 202
    return response.json()["id"]


def _pending_approval_id(client: TestClient, run_id: str) -> str:
    pending = client.get(
        f"/v1/agent/runs/{run_id}/level2-actions/pending", headers=AUTH
    )
    assert pending.status_code == 200
    body = pending.json()
    assert body["run"]["id"] == run_id
    assert len(body["approvals"]) == 1
    return body["approvals"][0]["approvalId"]


def _sse_events(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def _state_counts(connection, run_id: str) -> tuple[int, int]:
    return (
        int(
            connection.execute(
                "SELECT COUNT(*) FROM tool_invocations WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
        ),
        int(
            connection.execute(
                "SELECT COUNT(*) FROM state_mutations WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        ),
    )


def test_level2_proposal_confirm_is_atomic_and_records_reversible_mutation(
    tmp_path,
) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval.sqlite3",
        seed_demo=True,
    )
    provider = _ProposalProvider("task-chain-rule")
    with TestClient(
        create_app(settings, agent_provider_factory=lambda: provider)
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        pending = client.get(
            f"/v1/agent/runs/{run_id}/level2-actions/pending", headers=AUTH
        )
        assert pending.status_code == 200
        approval_id = pending.json()["approvals"][0]["approvalId"]
        with Database(settings.database_path).connection() as connection:
            stored = json.loads(
                connection.execute(
                    "SELECT canonical_arguments_json FROM level2_approval_actions WHERE approval_id = ?",
                    (approval_id,),
                ).fetchone()[0]
            )
        assert set(stored) == {"task_id", "course_id", "expected_revision"}
        confirmation_started = datetime.now(UTC)
        confirmed = client.post(
            f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/confirm",
            headers=AUTH,
            json={"idempotencyKey": "confirm-1"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["resolution"] == "confirmed"
        assert confirmed.json()["replayed"] is False
        assert _wait(client, run_id, "completed")["status"] == "completed"
        with Database(settings.database_path).connection() as connection:
            completed_task = TaskRepository(connection).get("task-chain-rule")
            assert completed_task["status"] == "completed"
            assert datetime.fromisoformat(completed_task["completed_at"]) >= (
                confirmation_started
            )
            invocation = connection.execute(
                "SELECT execution_invocation_id FROM level2_approval_actions WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()[0]
            mutations = AgentRepository(connection).list_state_mutations(invocation)
            assert len(mutations) == 1
            mutation_id = mutations[0]["id"]
            invocations = connection.execute(
                "SELECT id, status FROM tool_invocations WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
            assert len(invocations) == 2
            assert {row["status"] for row in invocations} == {"denied", "succeeded"}
            assert invocation != next(
                str(row["id"]) for row in invocations if row["status"] == "denied"
            )
        undone = client.post(
            f"/v1/agent/runs/{run_id}/mutations/{mutation_id}/undo",
            headers=AUTH,
            json={"idempotencyKey": "undo-1"},
        )
        assert undone.status_code == 200
        with Database(settings.database_path).connection() as connection:
            assert (
                TaskRepository(connection).get("task-chain-rule")["status"]
                == "upcoming"
            )


def test_level2_reject_has_no_domain_mutation_or_execution_invocation(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-reject.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        approval_id = _pending_approval_id(client, run_id)
        rejected = client.post(
            f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/reject",
            headers=AUTH,
            json={"idempotencyKey": "reject-1"},
        )
        assert rejected.status_code == 200
        assert rejected.json() == {
            "run": rejected.json()["run"],
            "approvalId": approval_id,
            "resolution": "rejected",
            "replayed": False,
        }
        assert _wait(client, run_id, "cancelled")["errorCode"] == "approval_denied"
        with Database(settings.database_path).connection() as connection:
            assert (
                TaskRepository(connection).get("task-chain-rule")["status"]
                == "upcoming"
            )
            assert _state_counts(connection, run_id) == (1, 0)
            action = connection.execute(
                "SELECT execution_invocation_id, resolution_kind FROM level2_approval_actions WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            assert tuple(action) == (None, "reject")
            assert (
                connection.execute(
                    "SELECT status FROM approval_requests WHERE id = ?", (approval_id,)
                ).fetchone()[0]
                == "denied"
            )


def test_level2_confirm_replays_same_key_and_conflicts_for_a_new_key(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-replay.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        approval_id = _pending_approval_id(client, run_id)
        url = f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/confirm"
        first = client.post(url, headers=AUTH, json={"idempotencyKey": "confirm-1"})
        assert first.status_code == 200
        replay = client.post(url, headers=AUTH, json={"idempotencyKey": "confirm-1"})
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["run"]["status"] == "completed"
        conflict = client.post(url, headers=AUTH, json={"idempotencyKey": "confirm-2"})
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "approval_conflict"
        with Database(settings.database_path).connection() as connection:
            assert _state_counts(connection, run_id) == (2, 1)
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM state_mutations WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
                == 1
            )


def test_level2_confirm_and_reject_race_has_one_atomic_winner(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-race.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        approval_id = _pending_approval_id(client, run_id)

        def resolve(action: str, key: str):
            return client.post(
                f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/{action}",
                headers=AUTH,
                json={"idempotencyKey": key},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            confirm = pool.submit(resolve, "confirm", "race-confirm")
            reject = pool.submit(resolve, "reject", "race-reject")
            responses = [confirm.result(), reject.result()]
        assert sorted(response.status_code for response in responses) == [200, 409]

        with Database(settings.database_path).connection() as connection:
            resolution = connection.execute(
                "SELECT resolution_kind FROM level2_approval_actions WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()[0]
            task = TaskRepository(connection).get("task-chain-rule")
            _, mutation_count = _state_counts(connection, run_id)
        run = client.get(f"/v1/agent/runs/{run_id}", headers=AUTH).json()
        if resolution == "confirm":
            assert (run["status"], task["status"], mutation_count) == (
                "completed",
                "completed",
                1,
            )
        else:
            assert (run["status"], task["status"], mutation_count) == (
                "cancelled",
                "upcoming",
                0,
            )


def test_level2_stale_revision_expires_without_a_domain_mutation(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-stale.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        approval_id = _pending_approval_id(client, run_id)
        with Database(settings.database_path).connection() as connection:
            connection.execute(
                "UPDATE study_tasks SET revision = revision + 1 WHERE id = ?",
                ("task-chain-rule",),
            )
            connection.commit()
        expired = client.post(
            f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/confirm",
            headers=AUTH,
            json={"idempotencyKey": "stale-1"},
        )
        assert expired.status_code == 200
        assert expired.json()["resolution"] == "expired"
        assert expired.json()["replayed"] is False
        assert _wait(client, run_id, "failed")["errorCode"] == "approval_action_expired"
        with Database(settings.database_path).connection() as connection:
            assert (
                TaskRepository(connection).get("task-chain-rule")["status"]
                == "upcoming"
            )
            assert _state_counts(connection, run_id) == (1, 0)
            assert (
                connection.execute(
                    "SELECT status FROM approval_requests WHERE id = ?", (approval_id,)
                ).fetchone()[0]
                == "expired"
            )


def test_level2_cancel_pending_has_no_domain_mutation(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-cancel.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        approval_id = _pending_approval_id(client, run_id)
        cancelled = client.post(f"/v1/agent/runs/{run_id}/cancel", headers=AUTH)
        assert cancelled.status_code == 200
        assert cancelled.json()["accepted"] is True
        assert cancelled.json()["run"]["status"] == "cancelled"
        with Database(settings.database_path).connection() as connection:
            assert (
                TaskRepository(connection).get("task-chain-rule")["status"]
                == "upcoming"
            )
            assert _state_counts(connection, run_id) == (1, 0)
            assert (
                connection.execute(
                    "SELECT status FROM approval_requests WHERE id = ?", (approval_id,)
                ).fetchone()[0]
                == "cancelled"
            )
        conflict = client.post(
            f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/confirm",
            headers=AUTH,
            json={"idempotencyKey": "cancelled-confirm"},
        )
        assert conflict.status_code == 409


def test_level2_restart_fails_closed_and_cancels_the_pending_approval(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-restart.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as initial:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(initial, "task-chain-rule")
        _wait(initial, run_id, "waiting_approval")
        approval_id = _pending_approval_id(initial, run_id)

    with TestClient(create_app(settings)) as restarted:
        interrupted = restarted.get(f"/v1/agent/runs/{run_id}", headers=AUTH)
        assert interrupted.status_code == 200
        assert interrupted.json()["status"] == "interrupted"
        assert interrupted.json()["errorCode"] == "process_restarted"
        pending = restarted.get(
            f"/v1/agent/runs/{run_id}/level2-actions/pending", headers=AUTH
        )
        assert pending.json()["approvals"] == []
        conflict = restarted.post(
            f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/confirm",
            headers=AUTH,
            json={"idempotencyKey": "after-restart"},
        )
        assert conflict.status_code == 409
        with Database(settings.database_path).connection() as connection:
            assert (
                TaskRepository(connection).get("task-chain-rule")["status"]
                == "upcoming"
            )
            assert (
                connection.execute(
                    "SELECT status FROM approval_requests WHERE id = ?", (approval_id,)
                ).fetchone()[0]
                == "cancelled"
            )


def test_level2_public_api_and_sse_expose_only_safe_approval_fields(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-public.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        pending = client.get(
            f"/v1/agent/runs/{run_id}/level2-actions/pending", headers=AUTH
        )
        assert pending.status_code == 200
        approval = pending.json()["approvals"][0]
        assert set(approval) == {"approvalId", "toolName", "summary"}
        assert set(approval["summary"]) == {
            "title",
            "taskTitle",
            "courseTitle",
            "effect",
        }
        approval_id = approval["approvalId"]
        confirmed = client.post(
            f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/confirm",
            headers=AUTH,
            json={"idempotencyKey": "public-1"},
        )
        assert confirmed.status_code == 200
        events = _sse_events(
            client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH).text
        )
        requested = next(
            data
            for event, data in events
            if event == "checkpoint" and data.get("label") == "approval_requested"
        )
        assert requested == {"label": "approval_requested", "data": approval}
        resolved = next(
            data
            for event, data in events
            if event == "checkpoint" and data.get("label") == "approval_resolved"
        )
        assert resolved["label"] == "approval_resolved"
        assert set(resolved["data"]) == {
            "approvalId",
            "status",
            "executionInvocationId",
        }
        assert resolved["data"]["approvalId"] == approval_id
        assert resolved["data"]["status"] == "approved"
        assert isinstance(resolved["data"]["executionInvocationId"], str)
        mutation = next(data for event, data in events if event == "state_mutation")
        assert set(mutation) == {
            "callId",
            "invocationId",
            "mutationId",
            "entityType",
            "entityId",
            "operation",
            "reversible",
        }
        # The existing public mutation contract intentionally identifies the
        # changed entity so the activity panel can offer Undo. Exact tool
        # arguments, host scope, and reversible payloads remain audit data.
        public_text = "\n".join(
            [pending.text, confirmed.text]
            + [
                json.dumps(data, sort_keys=True)
                for event, data in events
                if event != "state_mutation"
            ]
        )
        for forbidden in (
            "course-calculus",
            "expected_revision",
            "expectedRevision",
            "completed_at",
            "completedAt",
            "canonical_arguments",
            "undo_json",
            "source_path",
            "reasoning",
        ):
            assert forbidden not in public_text


def test_level2_invalid_proposal_is_durably_redacted_then_provider_recovers(
    tmp_path,
) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-recovery.sqlite3",
        seed_demo=True,
    )
    provider = _RecoveringProposalProvider("task-chain-rule")
    with TestClient(
        create_app(settings, agent_provider_factory=lambda: provider)
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        assert len(provider.feedback) == 1
        assert isinstance(provider.feedback[0], ProviderToolError)
        assert provider.feedback[0].code == "invalid_arguments"
        with Database(settings.database_path).connection() as connection:
            recorded = AgentRepository(connection).list_events(run_id)
        events = [(str(event["event_type"]), event["payload"]) for event in recorded]
        failed = next(
            data
            for event, data in events
            if event == "tool_result" and data.get("failed") is True
        )
        assert failed == {
            "callId": "invalid-proposal",
            "invocationId": failed["invocationId"],
            "toolName": "complete_study_task",
            "failed": True,
            "code": "invalid_arguments",
            "retryable": True,
            "replayed": False,
        }
        assert str(10**100) not in json.dumps(events)
        with Database(settings.database_path).connection() as connection:
            failed_step = connection.execute(
                "SELECT status, error_code FROM agent_steps WHERE run_id = ? AND status = 'failed'",
                (run_id,),
            ).fetchone()
            assert tuple(failed_step) == ("failed", "invalid_arguments")
            assert _state_counts(connection, run_id) == (1, 0)


def test_level2_stored_action_arguments_are_immutable(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "approval-immutable.sqlite3",
        seed_demo=True,
    )
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: _ProposalProvider("task-chain-rule"),
        )
    ) as client:
        with Database(settings.database_path).connection() as connection:
            ConversationRepository(connection).create_conversation(
                conversation_id="approval-conversation",
                title="Approval test",
                course_id="course-calculus",
            )
        run_id = _create_run(client, "task-chain-rule")
        _wait(client, run_id, "waiting_approval")
        approval_id = _pending_approval_id(client, run_id)
        with Database(settings.database_path).connection() as connection:
            with pytest.raises(sqlite3.IntegrityError, match="action is immutable"):
                connection.execute(
                    "UPDATE level2_approval_actions SET canonical_arguments_json = ? WHERE approval_id = ?",
                    ("{}", approval_id),
                )
        confirmed = client.post(
            f"/v1/agent/runs/{run_id}/level2-actions/{approval_id}/confirm",
            headers=AUTH,
            json={"idempotencyKey": "immutable-confirm"},
        )
        assert confirmed.status_code == 200
        with Database(settings.database_path).connection() as connection:
            with pytest.raises(sqlite3.IntegrityError, match="resolution is immutable"):
                connection.execute(
                    "UPDATE level2_approval_actions SET resolution_idempotency_key = ? WHERE approval_id = ?",
                    ("rewritten-key", approval_id),
                )
            with pytest.raises(sqlite3.IntegrityError, match="action is immutable"):
                connection.execute(
                    "UPDATE level2_approval_actions SET execution_invocation_id = NULL WHERE approval_id = ?",
                    (approval_id,),
                )
