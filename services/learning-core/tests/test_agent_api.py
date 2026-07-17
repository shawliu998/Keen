from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from collections.abc import AsyncIterator, Sequence

import pytest
from fastapi.testclient import TestClient

from app.agent.provider import (
    AgentProvider,
    ContentDelta,
    FixedAutomationProvider,
    ProviderAction,
    ProviderFinished,
    ProviderRequest,
    ProviderToolResult,
    ToolCall,
)
from app.chat_interfaces import ChatMessage, ChatModel
from app.database import Database
from app.main import create_app
from app.repositories.agent_repository import AgentRepository
from app.settings import LocalChatSettings, Settings

TOKEN = "0123456789abcdef0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _settings(tmp_path, *, seed_demo: bool = False) -> Settings:
    return Settings(
        session_token=TOKEN,
        database_path=tmp_path / "agent-api.sqlite3",
        seed_demo=seed_demo,
    )


def _payload(*, key: str = "agent-api-1") -> dict:
    return {
        "kind": "conversation",
        "userIntent": "Explain limits",
        "mode": "teach",
        "input": {"question": "What is a limit?"},
        "idempotencyKey": key,
    }


def _wait_for_terminal(client: TestClient, run_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/v1/agent/runs/{run_id}", headers=AUTH)
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return run
        time.sleep(0.01)
    raise AssertionError("Agent run did not reach a terminal state")


def _sse_events(body: str) -> list[dict[str, str]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            name, value = line.split(": ", 1)
            fields[name] = value
        events.append(fields)
    return events


def test_agent_api_requires_authentication(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.post("/v1/agent/runs", json=_payload()).status_code == 401
        assert client.get("/v1/agent/runs/run-missing").status_code == 401
        assert client.post("/v1/agent/runs/run-missing/cancel").status_code == 401
        assert client.get("/v1/agent/runs/run-missing/events").status_code == 401


def test_default_runtime_reports_provider_missing_without_creating_run(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "code": "provider_missing",
            "message": "no real Agent provider is configured for this installation",
            "retryable": False,
            "recoveryAction": "Configure a real Agent provider and retry.",
        }
        assert client.get("/v1/agent/runs/run-missing", headers=AUTH).status_code == 404
    with Database(settings.database_path).connection() as connection:
        assert connection.execute("SELECT count(*) FROM agent_runs").fetchone()[0] == 0


class _ConfiguredChatProvider:
    model = ChatModel(provider="ollama", model="keen-local", version="model-v7")

    def __init__(self) -> None:
        self.messages: tuple[ChatMessage, ...] = ()
        self.closed = False

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.messages = tuple(messages)
        yield "A real local "
        yield "Agent answer."

    async def aclose(self) -> None:
        self.closed = True


def test_local_chat_configuration_automatically_drives_real_agent_run(tmp_path):
    local_chat = LocalChatSettings(
        provider="ollama",
        base_url="http://127.0.0.1:11434",
        model="keen-local",
        version="model-v7",
    )
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "agent-api.sqlite3",
        local_chat=local_chat,
    )
    chat = _ConfiguredChatProvider()
    factory_configurations: list[LocalChatSettings] = []

    def chat_provider_factory(
        configuration: LocalChatSettings,
    ) -> _ConfiguredChatProvider:
        factory_configurations.append(configuration)
        return chat

    with TestClient(
        create_app(settings, chat_provider_factory=chat_provider_factory)
    ) as client:
        created = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert created.status_code == 202
        run_id = created.json()["id"]
        terminal = _wait_for_terminal(client, run_id)
        assert terminal["status"] == "completed"
        assert terminal["provider"] == "ollama"
        assert terminal["model"] == "keen-local"

        stream = client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH)
        assert stream.status_code == 200
        events = _sse_events(stream.text)
        metadata = json.loads(events[0]["data"])
        assert metadata == {
            "runId": run_id,
            "provider": "ollama",
            "model": "keen-local",
            "providerVersion": "model-v7+keen-agent-text-v1",
        }
        assert (
            "".join(
                json.loads(event["data"])["delta"]
                for event in events
                if event["event"] == "content_delta"
            )
            == "A real local Agent answer."
        )
        assert events[-1]["event"] == "done"

    assert factory_configurations == [local_chat]
    assert chat.closed is True
    assert chat.messages[0].role == "system"
    with Database(settings.database_path).connection() as connection:
        row = connection.execute(
            "SELECT provider, model, prompt_version FROM agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    assert tuple(row) == (
        "ollama",
        "keen-local",
        "model-v7+keen-agent-text-v1",
    )


def test_explicit_agent_provider_factory_precedes_local_chat_configuration(tmp_path):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "agent-api.sqlite3",
        local_chat=LocalChatSettings(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="unused-local-model",
            version="unused-v1",
        ),
    )
    chat_factory_called = False

    def chat_provider_factory(
        configuration: LocalChatSettings,
    ) -> _ConfiguredChatProvider:
        nonlocal chat_factory_called
        del configuration
        chat_factory_called = True
        return _ConfiguredChatProvider()

    with TestClient(
        create_app(
            settings,
            chat_provider_factory=chat_provider_factory,
            agent_provider_factory=lambda: FixedAutomationProvider(
                [ContentDelta(text="Explicit provider answer."), ProviderFinished()]
            ),
        )
    ) as client:
        created = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert created.status_code == 202
        terminal = _wait_for_terminal(client, created.json()["id"])

    assert terminal["status"] == "completed"
    assert terminal["provider"] == "automation"
    assert terminal["model"] == "fixed-actions"
    assert chat_factory_called is False


def test_local_chat_agent_fingerprints_long_version_before_run_persistence(tmp_path):
    long_version = "revision-" + "x" * 247
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "agent-api.sqlite3",
        local_chat=LocalChatSettings(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="keen-local",
            version=long_version,
        ),
    )
    chat = _ConfiguredChatProvider()
    chat.model = ChatModel(
        provider="ollama",
        model="keen-local",
        version=long_version,
    )
    expected_version = (
        f"sha256:{hashlib.sha256(long_version.encode('utf-8')).hexdigest()}"
        "+keen-agent-text-v1"
    )

    with TestClient(
        create_app(settings, chat_provider_factory=lambda _configuration: chat)
    ) as client:
        created = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert created.status_code == 202
        run_id = created.json()["id"]
        assert _wait_for_terminal(client, run_id)["status"] == "completed"

    with Database(settings.database_path).connection() as connection:
        persisted = connection.execute(
            "SELECT prompt_version FROM agent_runs WHERE id = ?", (run_id,)
        ).fetchone()[0]
    assert persisted == expected_version
    assert len(persisted) <= 128


def test_local_chat_agent_rejects_empty_output_without_false_content_or_done(tmp_path):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "agent-api.sqlite3",
        local_chat=LocalChatSettings(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="keen-local",
            version="model-v7",
        ),
    )

    class WhitespaceChatProvider(_ConfiguredChatProvider):
        async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
            self.messages = tuple(messages)
            yield "  "
            yield "\n"

    chat = WhitespaceChatProvider()
    with TestClient(
        create_app(settings, chat_provider_factory=lambda _configuration: chat)
    ) as client:
        created = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert created.status_code == 202
        run_id = created.json()["id"]
        terminal = _wait_for_terminal(client, run_id)
        assert terminal["status"] == "failed"
        assert terminal["errorCode"] == "provider_output_invalid"
        assert terminal["errorDetail"] == (
            "The Agent provider returned unusable output; the run did not complete. "
            "Retry, or choose another configured model."
        )
        events = _sse_events(
            client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH).text
        )
        event_types = [event["event"] for event in events]
        assert "content_delta" not in event_types
        assert "done" not in event_types
        assert event_types[-1] == "error"

    assert chat.closed is True


def test_provider_factory_failure_is_safe_503_without_persistence_or_secret_log(
    tmp_path, caplog
):
    settings = _settings(tmp_path)

    def failing_factory() -> AgentProvider:
        raise RuntimeError("factory-secret-must-not-escape")

    with TestClient(
        create_app(settings, agent_provider_factory=failing_factory)
    ) as client:
        response = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "provider_unavailable"
        assert "factory-secret" not in response.text
    assert "factory-secret" not in caplog.text
    with Database(settings.database_path).connection() as connection:
        assert connection.execute("SELECT count(*) FROM agent_runs").fetchone()[0] == 0


def test_fixed_provider_create_get_and_durable_sse_cursor(tmp_path):
    settings = _settings(tmp_path)

    def provider_factory() -> AgentProvider:
        return FixedAutomationProvider(
            [
                ContentDelta(text="A limit describes nearby behavior."),
                ContentDelta(text=" It is defined by convergence."),
                ProviderFinished(),
            ]
        )

    with TestClient(
        create_app(settings, agent_provider_factory=provider_factory)
    ) as client:
        created = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert created.status_code == 202
        run_id = created.json()["id"]
        terminal = _wait_for_terminal(client, run_id)
        assert terminal["status"] == "completed"
        assert terminal["provider"] == "automation"
        assert terminal["model"] == "fixed-actions"
        assert "input" not in terminal
        assert "userIntent" not in terminal

        stream = client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH)
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(stream.text)
        assert [event["event"] for event in events] == [
            "metadata",
            "status",
            "content_delta",
            "content_delta",
            "status",
            "done",
        ]

        cursor = events[2]["id"]
        replay = client.get(
            f"/v1/agent/runs/{run_id}/events",
            headers={**AUTH, "Last-Event-ID": cursor},
        )
        assert replay.status_code == 200
        replayed = _sse_events(replay.text)
        assert cursor not in {event["id"] for event in replayed}
        assert [event["id"] for event in replayed] == [
            event["id"] for event in events[3:]
        ]

        query_replay = client.get(
            f"/v1/agent/runs/{run_id}/events", headers=AUTH, params={"cursor": cursor}
        )
        assert [event["id"] for event in _sse_events(query_replay.text)] == [
            event["id"] for event in events[3:]
        ]
        assert (
            client.get(
                f"/v1/agent/runs/{run_id}/events",
                headers={**AUTH, "Last-Event-ID": "event-missing"},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/v1/agent/runs/{run_id}/events",
                headers={**AUTH, "Last-Event-ID": cursor},
                params={"cursor": events[3]["id"]},
            ).status_code
            == 400
        )

        second = client.post(
            "/v1/agent/runs", headers=AUTH, json=_payload(key="agent-api-2")
        )
        second_run_id = second.json()["id"]
        _wait_for_terminal(client, second_run_id)
        cross_run_cursor = client.get(
            f"/v1/agent/runs/{second_run_id}/events",
            headers={**AUTH, "Last-Event-ID": cursor},
        )
        assert cross_run_cursor.status_code == 422


class _BlockingProvider:
    name = "test-provider"
    model = "blocking-model"
    version = "v1"

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]:
        del request
        yield ContentDelta(text="Started")
        await self.release.wait()
        yield ProviderFinished()

    async def aclose(self) -> None:
        self.closed = True


class _CloseRaisingProvider(_BlockingProvider):
    async def aclose(self) -> None:
        self.closed = True
        raise RuntimeError("close-secret-must-not-escape")


class _HungCloseProvider(_BlockingProvider):
    async def aclose(self) -> None:
        self.closed = True
        await asyncio.Event().wait()


def test_single_active_claim_idempotent_replay_cancel_and_no_orphan(tmp_path):
    provider = _BlockingProvider()
    factory_calls = 0

    def provider_factory() -> AgentProvider:
        nonlocal factory_calls
        factory_calls += 1
        return provider

    settings = _settings(tmp_path)
    with TestClient(
        create_app(settings, agent_provider_factory=provider_factory)
    ) as client:
        first = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert first.status_code == 202
        run_id = first.json()["id"]

        same = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert same.status_code == 202
        assert same.json()["id"] == run_id
        assert factory_calls == 1

        busy = client.post(
            "/v1/agent/runs", headers=AUTH, json=_payload(key="different-key")
        )
        assert busy.status_code == 409
        assert busy.json()["detail"]["code"] == "agent_busy"
        with Database(settings.database_path).connection() as connection:
            assert (
                connection.execute("SELECT count(*) FROM agent_runs").fetchone()[0] == 1
            )

        cancelled = client.post(f"/v1/agent/runs/{run_id}/cancel", headers=AUTH)
        assert cancelled.status_code == 200
        assert cancelled.json()["accepted"] is True
        terminal = _wait_for_terminal(client, run_id)
        assert terminal["status"] == "cancelled"
        assert provider.closed is True

        stream = client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH)
        event_types = [event["event"] for event in _sse_events(stream.text)]
        assert event_types[-1] == "error"
        assert "done" not in event_types


class _ReleasedActionsProvider(FixedAutomationProvider):
    def __init__(self, actions: list[ProviderAction]) -> None:
        super().__init__(actions)
        self.release = threading.Event()
        self.actions = actions

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]:
        del request
        await asyncio.to_thread(self.release.wait)
        for action in self.actions:
            yield action


class _UndeclaredToolProvider:
    name = "undeclared-tools"
    model = "unsafe-tool-attempt"
    version = "v1"

    def __init__(self) -> None:
        self.feedback: list[ProviderToolResult] = []
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]:
        del request
        yield ToolCall(
            call_id="unapproved-complete",
            tool_name="complete_study_task",
            arguments={
                "task_id": "task-chain-rule",
                "course_id": "course-calculus",
                "expected_revision": 0,
                "completed_at": "2026-07-16T10:00:00Z",
            },
        )
        yield ProviderFinished()

    async def submit_tool_result(self, result: ProviderToolResult) -> None:
        self.feedback.append(result)

    async def aclose(self) -> None:
        self.closed = True


def test_runtime_denies_tools_for_provider_without_reviewed_allowlist(tmp_path):
    settings = _settings(tmp_path, seed_demo=True)
    provider = _UndeclaredToolProvider()

    with TestClient(
        create_app(settings, agent_provider_factory=lambda: provider)
    ) as client:
        created = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert created.status_code == 202
        run_id = created.json()["id"]
        terminal = _wait_for_terminal(client, run_id)
        assert terminal["status"] == "failed"
        assert terminal["errorCode"] == "provider_protocol_error"
        events = _sse_events(
            client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH).text
        )
        assert not any(event["event"] == "tool_start" for event in events)

    with Database(settings.database_path).connection() as connection:
        task = connection.execute(
            "SELECT status, revision FROM study_tasks WHERE id = 'task-chain-rule'"
        ).fetchone()
        invocation_count = connection.execute(
            "SELECT count(*) FROM tool_invocations WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
    assert tuple(task) == ("upcoming", 0)
    assert invocation_count == 0
    assert provider.feedback == []
    assert provider.closed is True


def test_level_two_tool_starts_after_post_and_uses_background_owned_connection(
    tmp_path,
):
    settings = _settings(tmp_path, seed_demo=True)
    provider = _ReleasedActionsProvider(
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

    with TestClient(
        create_app(settings, agent_provider_factory=lambda: provider)
    ) as client:
        response = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        assert response.status_code == 202
        run_id = response.json()["id"]
        with Database(settings.database_path).connection() as connection:
            assert (
                connection.execute(
                    "SELECT status FROM study_tasks WHERE id = 'task-chain-rule'"
                ).fetchone()[0]
                == "upcoming"
            )
        provider.release.set()
        assert _wait_for_terminal(client, run_id)["status"] == "completed"
        events = _sse_events(
            client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH).text
        )
        mutation = next(event for event in events if event["event"] == "state_mutation")
        mutation_payload = json.loads(mutation["data"])
        assert mutation_payload["mutationId"].startswith("mutation-")
        assert mutation_payload["entityId"] == "task-chain-rule"
    with Database(settings.database_path).connection() as connection:
        task = connection.execute(
            "SELECT status, revision FROM study_tasks WHERE id = 'task-chain-rule'"
        ).fetchone()
        assert tuple(task) == ("completed", 1)
        persisted_mutation = connection.execute(
            "SELECT id FROM state_mutations"
        ).fetchone()[0]
        assert persisted_mutation == mutation_payload["mutationId"]
    assert provider.closed is True
    assert len(provider.tool_results) == 1
    assert provider.tool_results[0].fidelity == "full"
    assert provider.tool_results[0].output == {
        "task_id": "task-chain-rule",
        "status": "completed",
        "revision": 1,
    }


def test_startup_recovery_appends_one_terminal_error_and_second_start_is_idempotent(
    tmp_path,
):
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    database.migrate()
    with database.connection() as connection:
        repository = AgentRepository(connection)
        repository.create_run(
            run_id="run-stale",
            kind="conversation",
            provider="local-provider",
            model="model-v1",
            user_intent="Resume me",
            mode="teach",
            prompt_version="v1",
            input_data={},
            idempotency_key="stale-key",
        )
        repository.transition_run("run-stale", status="running")
        repository.add_step(
            step_id="step-stale",
            run_id="run-stale",
            ordinal=0,
            kind="tool",
            label="export_study_data",
            input_data={},
        )
        repository.start_tool_invocation(
            invocation_id="invocation-stale",
            run_id="run-stale",
            step_id="step-stale",
            tool_name="export_study_data",
            permission_level=3,
            arguments={"course_id": "course-calculus", "format": "json"},
            idempotency_key="invocation-stale",
        )
        repository.request_approval(
            approval_id="approval-stale",
            run_id="run-stale",
            invocation_id="invocation-stale",
            summary="Export course study data",
        )

    with TestClient(create_app(settings)) as client:
        run = client.get("/v1/agent/runs/run-stale", headers=AUTH).json()
        assert run["status"] == "interrupted"
        assert run["errorCode"] == "process_restarted"
        first_events = _sse_events(
            client.get("/v1/agent/runs/run-stale/events", headers=AUTH).text
        )
        assert [event["event"] for event in first_events] == ["status", "error"]
        assert "process_restarted" in first_events[-1]["data"]
        assert "done" not in {event["event"] for event in first_events}
        with Database(settings.database_path).connection() as connection:
            assert (
                connection.execute(
                    "SELECT status FROM agent_steps WHERE id = 'step-stale'"
                ).fetchone()[0]
                == "interrupted"
            )
            assert (
                connection.execute(
                    "SELECT status FROM tool_invocations WHERE id = 'invocation-stale'"
                ).fetchone()[0]
                == "cancelled"
            )
            assert (
                connection.execute(
                    "SELECT status FROM approval_requests WHERE id = 'approval-stale'"
                ).fetchone()[0]
                == "cancelled"
            )

    with TestClient(create_app(settings)) as client:
        second_events = _sse_events(
            client.get("/v1/agent/runs/run-stale/events", headers=AUTH).text
        )
        assert [event["id"] for event in second_events] == [
            event["id"] for event in first_events
        ]


def test_hidden_reasoning_and_extra_fields_are_rejected_before_persistence(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: FixedAutomationProvider(
                [ProviderFinished()]
            ),
        )
    ) as client:
        hidden = _payload()
        hidden["input"] = {"chainOfThought": "private reasoning"}
        assert (
            client.post("/v1/agent/runs", headers=AUTH, json=hidden).status_code == 422
        )
        extra = {**_payload(), "provider": "automation"}
        assert (
            client.post("/v1/agent/runs", headers=AUTH, json=extra).status_code == 422
        )
        unsafe_key = _payload()
        unsafe_key["idempotencyKey"] = "private text with spaces"
        assert (
            client.post("/v1/agent/runs", headers=AUTH, json=unsafe_key).status_code
            == 422
        )
    with Database(settings.database_path).connection() as connection:
        assert connection.execute("SELECT count(*) FROM agent_runs").fetchone()[0] == 0


def test_provider_disconnect_fails_without_false_done_or_private_error_detail(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(
        create_app(
            settings,
            agent_provider_factory=lambda: FixedAutomationProvider(
                [ContentDelta(text="partial private answer")]
            ),
        )
    ) as client:
        created = client.post("/v1/agent/runs", headers=AUTH, json=_payload())
        run_id = created.json()["id"]
        terminal = _wait_for_terminal(client, run_id)
        assert terminal["status"] == "failed"
        assert terminal["errorCode"] == "provider_disconnected"
        assert "partial private answer" not in (terminal["errorDetail"] or "")
        events = _sse_events(
            client.get(f"/v1/agent/runs/{run_id}/events", headers=AUTH).text
        )
        assert events[-1]["event"] == "error"
        assert "done" not in {event["event"] for event in events}


def test_stream_disconnect_does_not_cancel_run_and_shutdown_closes_provider(tmp_path):
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    database.migrate()
    provider = _BlockingProvider()

    async def scenario() -> None:
        from app.services.agent_runtime import AgentRuntimeManager

        manager = AgentRuntimeManager(database, provider_factory=lambda: provider)
        run = await manager.create_run(
            kind="conversation",
            user_intent="Keep working",
            mode="teach",
            input_data={},
            idempotency_key="disconnect-test",
        )
        for _ in range(100):
            if manager.event_store.list_events(run["id"]):
                break
            await asyncio.sleep(0.01)
        disconnected = asyncio.Event()
        disconnected.set()
        replayed = [
            event
            async for event in manager.stream_events(
                run["id"], last_event_id=None, disconnected=disconnected
            )
        ]
        assert replayed
        assert manager.get_run(run["id"])["status"] == "running"
        await manager.shutdown()
        assert manager.get_run(run["id"])["status"] == "cancelled"

    asyncio.run(scenario())
    assert provider.closed is True


def test_concurrent_same_key_claims_one_run_and_different_key_leaves_no_orphan(
    tmp_path,
):
    from app.services.agent_runtime import AgentBusyError, AgentRuntimeManager

    database = Database(tmp_path / "manager-concurrency.sqlite3")
    database.migrate()
    provider = _BlockingProvider()
    factory_calls = 0

    def factory() -> AgentProvider:
        nonlocal factory_calls
        factory_calls += 1
        return provider

    async def scenario() -> None:
        manager = AgentRuntimeManager(database, provider_factory=factory)
        arguments = {
            "kind": "conversation",
            "user_intent": "Concurrent request",
            "mode": "teach",
            "input_data": {},
            "idempotency_key": "same-key",
        }
        first, second = await asyncio.gather(
            manager.create_run(**arguments), manager.create_run(**arguments)
        )
        assert first["id"] == second["id"]
        assert factory_calls == 1
        with pytest.raises(AgentBusyError):
            await manager.create_run(**{**arguments, "idempotency_key": "other-key"})
        with database.connection() as connection:
            rows = connection.execute("SELECT id FROM agent_runs").fetchall()
            assert [row["id"] for row in rows] == [first["id"]]
        await manager.shutdown()

    asyncio.run(scenario())


def test_recovery_rolls_back_state_and_events_together_on_event_failure(
    tmp_path, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeManager

    database = Database(tmp_path / "recovery-atomic.sqlite3")
    database.migrate()
    with database.connection() as connection:
        repository = AgentRepository(connection)
        repository.create_run(
            run_id="run-atomic",
            kind="conversation",
            provider="provider",
            model="model",
            user_intent="Recover atomically",
            mode="teach",
            prompt_version="v1",
            input_data={},
            idempotency_key="atomic",
        )
        repository.transition_run("run-atomic", status="running")

    original_append = AgentRepository.append_event

    def fail_error_event(self, *, event_type, **kwargs):
        if event_type == "error":
            raise RuntimeError("injected recovery event failure")
        return original_append(self, event_type=event_type, **kwargs)

    monkeypatch.setattr(AgentRepository, "append_event", fail_error_event)
    manager = AgentRuntimeManager(database)
    with pytest.raises(RuntimeError, match="injected"):
        manager.recover_interrupted_runs()
    with database.connection() as connection:
        run = AgentRepository(connection).get_run("run-atomic")
        assert run["status"] == "running"
        assert (
            connection.execute("SELECT count(*) FROM agent_events").fetchone()[0] == 0
        )


def test_prepublish_cancel_survives_provider_close_error_and_is_terminal(tmp_path):
    from app.services.agent_runtime import AgentRuntimeManager

    database = Database(tmp_path / "cancel-close-error.sqlite3")
    database.migrate()
    provider = _CloseRaisingProvider()

    async def scenario() -> None:
        manager = AgentRuntimeManager(database, provider_factory=lambda: provider)
        run = await manager.create_run(
            kind="conversation",
            user_intent="Cancel immediately",
            mode="teach",
            input_data={},
            idempotency_key="cancel-close-error",
        )
        accepted, cancelled = await manager.cancel(run["id"])
        assert accepted is True
        assert cancelled["status"] == "cancelled"
        events = manager.event_store.list_events(run["id"])
        assert [event.event_type for event in events] == ["status", "error"]
        assert "close-secret" not in str(events[-1].payload)

    asyncio.run(scenario())
    assert provider.closed is True


def test_setup_failure_moves_queued_run_to_failed_without_false_done(
    tmp_path, monkeypatch
):
    import app.services.agent_runtime as runtime_module

    database = Database(tmp_path / "setup-failure.sqlite3")
    database.migrate()
    provider = _CloseRaisingProvider()

    def fail_setup(*args, **kwargs) -> None:
        del args, kwargs
        raise RuntimeError("setup-secret-must-not-escape")

    monkeypatch.setattr(runtime_module, "register_initial_product_tools", fail_setup)

    async def scenario() -> None:
        manager = runtime_module.AgentRuntimeManager(
            database, provider_factory=lambda: provider
        )
        run = await manager.create_run(
            kind="conversation",
            user_intent="Fail during setup",
            mode="teach",
            input_data={},
            idempotency_key="setup-failure",
        )
        current = manager.get_run(run["id"])
        for _ in range(100):
            if current["status"] == "failed":
                break
            await asyncio.sleep(0.01)
            current = manager.get_run(run["id"])
        assert current["status"] == "failed"
        assert current["error_code"] == "agent_runtime_error"
        assert "setup-secret" not in (current["error_detail"] or "")
        events = manager.event_store.list_events(run["id"])
        assert [event.event_type for event in events] == ["status", "error"]
        assert "done" not in {event.event_type for event in events}

    asyncio.run(scenario())
    assert provider.closed is True


def test_immediate_shutdown_terminalizes_queued_run_with_hung_close_in_budget(tmp_path):
    from app.services.agent_runtime import AgentRuntimeManager

    database = Database(tmp_path / "shutdown-hung-close.sqlite3")
    database.migrate()
    provider = _HungCloseProvider()

    async def scenario() -> None:
        manager = AgentRuntimeManager(database, provider_factory=lambda: provider)
        run = await manager.create_run(
            kind="conversation",
            user_intent="Shutdown immediately",
            mode="teach",
            input_data={},
            idempotency_key="shutdown-hung-close",
        )
        started = asyncio.get_running_loop().time()
        await manager.shutdown()
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 2.0
        current = manager.get_run(run["id"])
        assert current["status"] == "cancelled"
        events = manager.event_store.list_events(run["id"])
        assert events[-1].event_type == "error"
        assert "done" not in {event.event_type for event in events}

    asyncio.run(scenario())
    assert provider.closed is True


def test_durable_idempotent_replay_needs_no_provider_and_rejects_payload_conflict(
    tmp_path,
):
    from app.services.agent_runtime import AgentRuntimeManager

    database = Database(tmp_path / "durable-idempotency.sqlite3")
    database.migrate()
    with database.connection() as connection:
        repository = AgentRepository(connection)
        repository.create_run(
            run_id="run-existing",
            kind="conversation",
            provider="old-provider",
            model="old-model",
            user_intent="Replay safely",
            mode="teach",
            prompt_version="old-v1",
            input_data={"course_id": "course-calculus"},
            idempotency_key="durable-replay",
        )
        repository.transition_run("run-existing", status="running")
        repository.transition_run("run-existing", status="completed")
    factory_calls = 0

    def raising_factory() -> AgentProvider:
        nonlocal factory_calls
        factory_calls += 1
        raise RuntimeError("provider factory must not run")

    async def scenario() -> None:
        arguments = {
            "kind": "conversation",
            "user_intent": "Replay safely",
            "mode": "teach",
            "input_data": {"course_id": "course-calculus"},
            "idempotency_key": "durable-replay",
        }
        missing_manager = AgentRuntimeManager(database)
        missing_replay = await missing_manager.create_run(**arguments)
        assert missing_replay["id"] == "run-existing"
        manager = AgentRuntimeManager(database, provider_factory=raising_factory)
        replay = await manager.create_run(**arguments)
        assert replay["status"] == "completed"
        assert factory_calls == 0
        with pytest.raises(ValueError, match="different run payload"):
            await manager.create_run(
                **{**arguments, "user_intent": "Conflicting payload"}
            )
        assert factory_calls == 0

    asyncio.run(scenario())


def test_invalid_context_is_rejected_before_provider_initialization(tmp_path):
    from app.services.agent_runtime import AgentRuntimeManager

    database = Database(tmp_path / "repo-close-error.sqlite3")
    database.migrate()
    provider = _CloseRaisingProvider()

    async def scenario() -> None:
        manager = AgentRuntimeManager(database, provider_factory=lambda: provider)
        with pytest.raises(
            ValueError, match="agent run conversation context does not exist"
        ) as captured:
            await manager.create_run(
                kind="conversation",
                user_intent="Invalid conversation",
                mode="teach",
                input_data={},
                idempotency_key="repo-close-error",
                conversation_id="missing-conversation",
            )
        assert "close-secret" not in str(captured.value)

    asyncio.run(scenario())
    assert provider.closed is False
    with database.connection() as connection:
        assert connection.execute("SELECT count(*) FROM agent_runs").fetchone()[0] == 0


def test_agent_create_content_length_and_chunked_bodies_are_capped_before_factory(
    tmp_path,
):
    settings = _settings(tmp_path)
    factory_calls = 0

    def provider_factory() -> AgentProvider:
        nonlocal factory_calls
        factory_calls += 1
        return FixedAutomationProvider([ProviderFinished()])

    oversized = json.dumps(
        {**_payload(), "input": {"blob": "x" * (70 * 1024)}}
    ).encode()
    with TestClient(
        create_app(settings, agent_provider_factory=provider_factory)
    ) as client:
        declared = client.post(
            "/v1/agent/runs",
            headers={**AUTH, "Content-Type": "application/json"},
            content=oversized,
        )
        assert declared.status_code == 413

    async def exercise_chunked_guard() -> list[dict]:
        from app.request_guard import RequestGuardMiddleware

        midpoint = len(oversized) // 2
        chunks = [oversized[:midpoint], oversized[midpoint:]]
        sent: list[dict] = []

        async def receive() -> dict:
            body = chunks.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(chunks)}

        async def send(message: dict) -> None:
            sent.append(message)

        async def downstream(scope, receive, send) -> None:
            del scope, send
            while True:
                message = await receive()
                if not message.get("more_body"):
                    break
            provider_factory()
            raise AssertionError("oversized chunked Agent request reached FastAPI")

        middleware = RequestGuardMiddleware(
            downstream,
            session_token=TOKEN,
            max_document_bytes=1024,
        )
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/agent/runs",
            "headers": [
                (b"authorization", f"Bearer {TOKEN}".encode()),
                (b"content-type", b"application/json"),
            ],
        }
        await middleware(scope, receive, send)
        return sent

    sent = asyncio.run(exercise_chunked_guard())
    assert sent[0]["status"] == 413
    assert factory_calls == 0
    with Database(settings.database_path).connection() as connection:
        assert connection.execute("SELECT count(*) FROM agent_runs").fetchone()[0] == 0
