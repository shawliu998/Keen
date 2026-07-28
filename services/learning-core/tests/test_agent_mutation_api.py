from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from app.agent.event_stream import AgentEventStore
from app.agent.provider import FixedAutomationProvider, ProviderFinished, ToolCall
from app.database import Database
from app.main import create_app
from app.repositories.agent_repository import AgentRepository
from app.settings import Settings

TOKEN = "0123456789abcdef0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _settings(tmp_path) -> Settings:
    return Settings(
        session_token=TOKEN,
        database_path=tmp_path / "agent-mutation-api.sqlite3",
        seed_demo=True,
    )


def _provider() -> FixedAutomationProvider:
    return FixedAutomationProvider(
        [
            ToolCall(
                call_id="complete-task",
                tool_name="complete_study_task",
                arguments={
                    "task_id": "task-chain-rule",
                    "course_id": "course-calculus",
                    "expected_revision": 0,
                    "completed_at": "2026-07-16T10:00:00Z",
                },
            ),
            ProviderFinished(),
        ]
    )


def _two_task_provider() -> FixedAutomationProvider:
    return FixedAutomationProvider(
        [
            ToolCall(
                call_id="complete-chain-rule",
                tool_name="complete_study_task",
                arguments={
                    "task_id": "task-chain-rule",
                    "course_id": "course-calculus",
                    "expected_revision": 0,
                    "completed_at": "2026-07-16T10:00:00Z",
                },
            ),
            ToolCall(
                call_id="complete-newton",
                tool_name="complete_study_task",
                arguments={
                    "task_id": "task-newton",
                    "course_id": "course-physics",
                    "expected_revision": 0,
                    "completed_at": "2026-07-16T10:05:00Z",
                },
            ),
            ProviderFinished(),
        ]
    )


def _create_completed_run(client: TestClient, database_path) -> tuple[str, str]:
    created = client.post(
        "/v1/agent/runs",
        headers=AUTH,
        json={
            "kind": "conversation",
            "userIntent": "Complete the chain rule task",
            "mode": "study",
            "input": {},
            "idempotencyKey": "mutation-api-run",
        },
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    for _ in range(100):
        run = client.get(f"/v1/agent/runs/{run_id}", headers=AUTH).json()
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            break
        time.sleep(0.01)
    assert run["status"] == "completed"
    with Database(database_path).connection() as connection:
        mutation_id = connection.execute(
            "SELECT id FROM state_mutations WHERE run_id = ? ORDER BY created_at LIMIT 1",
            (run_id,),
        ).fetchone()[0]
    return run_id, mutation_id


def _action_path(run_id: str, mutation_id: str, action: str = "undo") -> str:
    return f"/v1/agent/runs/{run_id}/mutations/{mutation_id}/{action}"


def _seed_interrupted_action(
    client: TestClient,
    *,
    run_id: str,
    mutation_id: str,
    idempotency_key: str,
    with_invocation: bool,
) -> tuple[str, str]:
    service = client.app.state.agent_undo
    invocation_id, step_id = service._stable_ids(
        run_id,
        idempotency_key,
        action="undo",
        target_mutation_id=mutation_id,
    )
    client.app.state.agent_runtime.event_store.start_tool_step(
        run_id=run_id,
        step_id=step_id,
        ordinal=None,
        invocation_id=invocation_id,
        tool_name="undo_state_mutation",
        input_data={
            "toolName": "undo_state_mutation",
            "action": "undo",
            "targetMutationId": mutation_id,
            "idempotencyHash": service._idempotency_hash(run_id, idempotency_key),
        },
    )
    if with_invocation:
        with Database(
            client.app.state.settings.database_path
        ).connection() as connection:
            AgentRepository(connection).start_tool_invocation(
                invocation_id=invocation_id,
                run_id=run_id,
                step_id=step_id,
                tool_name="undo_state_mutation",
                permission_level=2,
                arguments={"mutation_id": mutation_id},
                idempotency_key=idempotency_key,
            )
    return invocation_id, step_id


def test_mutation_actions_require_auth_and_strict_bounded_body(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        path = _action_path(run_id, mutation_id)
        assert client.post(path, json={"idempotencyKey": "undo-1"}).status_code == 401
        assert (
            client.post(
                path,
                headers=AUTH,
                json={"idempotencyKey": "undo-1", "restore": {"status": "upcoming"}},
            ).status_code
            == 422
        )
        assert (
            client.post(
                path,
                headers={**AUTH, "Content-Type": "application/json"},
                content=b"x" * (64 * 1024 + 1),
            ).status_code
            == 413
        )


def test_undo_is_atomic_audited_evented_and_idempotent(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        path = _action_path(run_id, mutation_id)
        first = client.post(path, headers=AUTH, json={"idempotencyKey": "undo-1"})
        assert first.status_code == 200
        body = first.json()
        assert body == {
            "action": "undo",
            "runId": run_id,
            "targetMutationId": mutation_id,
            "invocationId": body["invocationId"],
            "mutationId": body["mutationId"],
            "entityType": "study_task",
            "entityId": "task-chain-rule",
            "operation": "update",
            "replayed": False,
        }
        replay = client.post(path, headers=AUTH, json={"idempotencyKey": "undo-1"})
        assert replay.status_code == 200
        assert replay.json() == {**body, "replayed": True}

        events_response = client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH)
        assert events_response.status_code == 200
        event_blocks = events_response.text.strip().split("\n\n")
        event_types = [
            next(line[7:] for line in block.splitlines() if line.startswith("event: "))
            for block in event_blocks
        ]
        assert event_types[-2:] == ["tool_result", "state_mutation"]
        payload = json.loads(
            next(
                line[6:]
                for line in event_blocks[-1].splitlines()
                if line.startswith("data: ")
            )
        )
        assert payload["mutationId"] == body["mutationId"]
        assert payload["invocationId"] == body["invocationId"]

    with Database(settings.database_path).connection() as connection:
        task = connection.execute(
            "SELECT status, revision FROM study_tasks WHERE id = 'task-chain-rule'"
        ).fetchone()
        assert tuple(task) == ("upcoming", 2)
        invocation = connection.execute(
            "SELECT permission_level, status, error_detail FROM tool_invocations WHERE id = ?",
            (body["invocationId"],),
        ).fetchone()
        assert tuple(invocation) == (2, "succeeded", None)
        original = connection.execute(
            "SELECT undone_by_tool_invocation_id FROM state_mutations WHERE id = ?",
            (mutation_id,),
        ).fetchone()
        assert original[0] == body["invocationId"]
        assert (
            connection.execute(
                "SELECT count(*) FROM state_mutations WHERE tool_invocation_id = ?",
                (body["invocationId"],),
            ).fetchone()[0]
            == 1
        )


def test_redo_uses_recorded_inverse_and_is_idempotent(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        undo = client.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "undo-1"},
        ).json()
        redo_path = _action_path(run_id, mutation_id, "redo")
        redo = client.post(redo_path, headers=AUTH, json={"idempotencyKey": "redo-1"})
        assert redo.status_code == 200
        body = redo.json()
        assert body["action"] == "redo"
        assert body["targetMutationId"] == mutation_id
        assert body["mutationId"] not in {mutation_id, undo["mutationId"]}
        assert body["replayed"] is False
        replay = client.post(redo_path, headers=AUTH, json={"idempotencyKey": "redo-1"})
        assert replay.status_code == 200
        assert replay.json() == {**body, "replayed": True}

    with Database(settings.database_path).connection() as connection:
        task = connection.execute(
            "SELECT status, revision FROM study_tasks WHERE id = 'task-chain-rule'"
        ).fetchone()
        assert tuple(task) == ("completed", 3)
        inverse = connection.execute(
            "SELECT undone_by_tool_invocation_id FROM state_mutations WHERE id = ?",
            (undo["mutationId"],),
        ).fetchone()
        assert inverse[0] == body["invocationId"]


def test_idempotency_key_reuse_and_cross_run_mutation_fail_closed(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        assert (
            client.post(
                _action_path(run_id, mutation_id),
                headers=AUTH,
                json={"idempotencyKey": "action-key"},
            ).status_code
            == 200
        )
        reused = client.post(
            _action_path(run_id, mutation_id, "redo"),
            headers=AUTH,
            json={"idempotencyKey": "action-key"},
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "idempotency_key_reused"
        missing = client.post(
            _action_path("run-not-owner", mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "cross-run"},
        )
        assert missing.status_code == 404
        assert "task-chain-rule" not in missing.text


def test_idempotency_key_cannot_alias_direct_inverse_undo_and_redo(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        inverse_id = client.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "first-undo"},
        ).json()["mutationId"]

        direct_inverse = client.post(
            _action_path(run_id, inverse_id),
            headers=AUTH,
            json={"idempotencyKey": "semantic-alias"},
        )
        assert direct_inverse.status_code == 200
        assert direct_inverse.json()["action"] == "undo"

        aliased_redo = client.post(
            _action_path(run_id, mutation_id, "redo"),
            headers=AUTH,
            json={"idempotencyKey": "semantic-alias"},
        )
        assert aliased_redo.status_code == 409
        assert aliased_redo.json()["detail"]["code"] == "idempotency_key_reused"


def test_changed_task_returns_redacted_conflict_and_terminal_audit(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        with Database(settings.database_path).connection() as connection:
            connection.execute(
                "UPDATE study_tasks SET title = ?, revision = revision + 1 WHERE id = ?",
                ("private-title-must-not-escape", "task-chain-rule"),
            )
            connection.commit()
        response = client.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "conflicting-undo"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "undo_conflict"
        assert "private-title" not in response.text

    with Database(settings.database_path).connection() as connection:
        invocation = connection.execute(
            "SELECT status, error_code, error_detail FROM tool_invocations WHERE idempotency_key = ?",
            ("conflicting-undo",),
        ).fetchone()
        assert tuple(invocation) == ("failed", "ValueError", None)
        step = connection.execute(
            "SELECT status, error_code, error_detail FROM agent_steps WHERE id = (SELECT step_id FROM tool_invocations WHERE idempotency_key = ?)",
            ("conflicting-undo",),
        ).fetchone()
        assert tuple(step) == ("failed", "undo_conflict", None)
        assert (
            connection.execute(
                "SELECT count(*) FROM state_mutations WHERE tool_invocation_id = (SELECT id FROM tool_invocations WHERE idempotency_key = ?)",
                ("conflicting-undo",),
            ).fetchone()[0]
            == 0
        )


def test_retry_heals_event_publication_after_atomic_undo_commit(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    original_complete = AgentEventStore.complete_tool_step
    attempts = 0

    def fail_once(self, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("private-publication-failure")
        return original_complete(self, **kwargs)

    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        monkeypatch.setattr(AgentEventStore, "complete_tool_step", fail_once)
        path = _action_path(run_id, mutation_id)
        first = client.post(
            path, headers=AUTH, json={"idempotencyKey": "recover-events"}
        )
        assert first.status_code == 500
        assert "private-publication" not in first.text
        replay = client.post(
            path, headers=AUTH, json={"idempotencyKey": "recover-events"}
        )
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True

    with Database(settings.database_path).connection() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM state_mutations WHERE tool_invocation_id = ?",
                (replay.json()["invocationId"],),
            ).fetchone()[0]
            == 1
        )
        step = connection.execute(
            "SELECT status FROM agent_steps WHERE id = (SELECT step_id FROM tool_invocations WHERE id = ?)",
            (replay.json()["invocationId"],),
        ).fetchone()[0]
        assert step == "completed"


def test_restart_terminalizes_step_created_before_invocation(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        _, step_id = _seed_interrupted_action(
            client,
            run_id=run_id,
            mutation_id=mutation_id,
            idempotency_key="crash-before-invocation",
            with_invocation=False,
        )

    with TestClient(create_app(settings)) as restarted:
        stale_key = restarted.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "crash-before-invocation"},
        )
        assert stale_key.status_code == 409
        assert stale_key.json()["detail"]["code"] == "idempotency_key_terminal"
        retry = restarted.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "after-step-crash"},
        )
        assert retry.status_code == 200
        events = restarted.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH)
        assert events.status_code == 200
        assert "mutation_action_interrupted" in events.text

    with Database(settings.database_path).connection() as connection:
        step = connection.execute(
            "SELECT status, error_code FROM agent_steps WHERE id = ?", (step_id,)
        ).fetchone()
        assert tuple(step) == ("failed", "process_restarted")
        assert (
            connection.execute(
                "SELECT count(*) FROM agent_events "
                "WHERE run_id = ? AND event_type = 'warning' "
                "AND json_extract(payload_json, '$.code') = 'mutation_action_interrupted'",
                (run_id,),
            ).fetchone()[0]
            == 1
        )


def test_restart_preserves_step_only_idempotency_across_mutation_targets(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(
        create_app(settings, agent_provider_factory=_two_task_provider)
    ) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        with Database(settings.database_path).connection() as connection:
            mutation_by_entity = {
                row["entity_id"]: row["id"]
                for row in connection.execute(
                    "SELECT id, entity_id FROM state_mutations WHERE run_id = ?",
                    (run_id,),
                ).fetchall()
            }
        mutation_id = mutation_by_entity["task-chain-rule"]
        _seed_interrupted_action(
            client,
            run_id=run_id,
            mutation_id=mutation_id,
            idempotency_key="step-only-key",
            with_invocation=False,
        )

    with TestClient(create_app(settings)) as restarted:
        reused = restarted.post(
            _action_path(run_id, mutation_by_entity["task-newton"]),
            headers=AUTH,
            json={"idempotencyKey": "step-only-key"},
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "idempotency_key_reused"
        with Database(settings.database_path).connection() as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM state_mutations WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
                == 2
            )

    with TestClient(create_app(settings)) as restarted_again:
        assert (
            restarted_again.get(
                f"/v1/agent/runs/{run_id}/events", headers=AUTH
            ).status_code
            == 200
        )
    with Database(settings.database_path).connection() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM agent_events "
                "WHERE run_id = ? AND event_type = 'warning' "
                "AND json_extract(payload_json, '$.code') = 'mutation_action_interrupted'",
                (run_id,),
            ).fetchone()[0]
            == 1
        )


def test_restart_terminalizes_running_invocation_and_requires_new_key(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        invocation_id, step_id = _seed_interrupted_action(
            client,
            run_id=run_id,
            mutation_id=mutation_id,
            idempotency_key="crash-after-invocation",
            with_invocation=True,
        )

    with TestClient(create_app(settings)) as restarted:
        stale_key = restarted.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "crash-after-invocation"},
        )
        assert stale_key.status_code == 409
        assert stale_key.json()["detail"]["code"] == "idempotency_key_terminal"
        retry = restarted.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "after-invocation-crash"},
        )
        assert retry.status_code == 200

    with Database(settings.database_path).connection() as connection:
        invocation = connection.execute(
            "SELECT status, error_code FROM tool_invocations WHERE id = ?",
            (invocation_id,),
        ).fetchone()
        step = connection.execute(
            "SELECT status, error_code FROM agent_steps WHERE id = ?", (step_id,)
        ).fetchone()
        assert tuple(invocation) == ("cancelled", "process_restarted")
        assert tuple(step) == ("failed", "process_restarted")


def test_restart_recovers_succeeded_invocation_and_missing_events(
    tmp_path, monkeypatch
):
    settings = _settings(tmp_path)
    original_complete = AgentEventStore.complete_tool_step

    def fail_publication(self, **kwargs):
        raise RuntimeError("private-publication-failure")

    with TestClient(create_app(settings, agent_provider_factory=_provider)) as client:
        run_id, mutation_id = _create_completed_run(client, settings.database_path)
        monkeypatch.setattr(AgentEventStore, "complete_tool_step", fail_publication)
        first = client.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "crash-after-commit"},
        )
        assert first.status_code == 500
    monkeypatch.setattr(AgentEventStore, "complete_tool_step", original_complete)

    with TestClient(create_app(settings)) as restarted:
        events = restarted.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH)
        assert events.status_code == 200
        assert "tool_result" in events.text
        assert "state_mutation" in events.text
        replay = restarted.post(
            _action_path(run_id, mutation_id),
            headers=AUTH,
            json={"idempotencyKey": "crash-after-commit"},
        )
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
