from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from ..agent.event_stream import AgentEventStore, DurableAgentEvent, DurableEventStream
from ..agent.executor import AgentStepExecutor
from ..agent.orchestrator import AgentOrchestrator
from ..agent.provider import AgentProvider, close_provider_safely
from ..agent.registry import ToolRegistry
from ..agent.sqlite_audit import SQLiteAuditSink
from ..agent.tools.product import register_initial_product_tools
from ..database import Database
from ..repositories import JsonValue
from ..repositories.agent_repository import AgentRepository


class AgentProviderFactory(Protocol):
    def __call__(self) -> AgentProvider: ...


class AgentProviderMissingError(RuntimeError):
    pass


class AgentProviderUnavailableError(RuntimeError):
    pass


class AgentBusyError(RuntimeError):
    pass


class AgentRuntimeManager:
    """App-scoped owner of the single active Agent run.

    Process restart continuation is intentionally not inferred. Startup recovery
    durably marks unfinished work ``interrupted`` and emits a terminal error event;
    a caller must start a new run with a new idempotency key.
    """

    def __init__(
        self,
        database: Database,
        *,
        provider_factory: AgentProviderFactory | None = None,
    ) -> None:
        self._database = database
        self._provider_factory = provider_factory
        self._event_store = AgentEventStore(database)
        self._lock = asyncio.Lock()
        self._active_run_id: str | None = None
        self._active_orchestrator: AgentOrchestrator | None = None
        self._active_provider: AgentProvider | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._active_request: tuple[object, ...] | None = None

    @property
    def event_store(self) -> AgentEventStore:
        return self._event_store

    def recover_interrupted_runs(self) -> list[str]:
        with self._database.connection() as connection:
            return AgentRepository(connection).recover_interrupted_runs()

    async def create_run(
        self,
        *,
        kind: str,
        user_intent: str,
        mode: str,
        input_data: dict[str, JsonValue],
        idempotency_key: str,
        conversation_id: str | None = None,
        study_session_id: str | None = None,
    ) -> dict:
        request_signature = (
            kind,
            user_intent,
            mode,
            input_data,
            idempotency_key,
            conversation_id,
            study_session_id,
        )
        async with self._lock:
            if self._active_task is not None and not self._active_task.done():
                if self._active_request == request_signature:
                    active = self.get_run(self._active_run_id or "")
                    if active is None:  # pragma: no cover - invariant guard
                        raise RuntimeError("active Agent run disappeared")
                    return active
                if (
                    self._active_request is not None
                    and self._active_request[4] == idempotency_key
                    and self._active_request[0] == kind
                ):
                    raise ValueError(
                        "idempotency key was reused with a different run payload"
                    )
                raise AgentBusyError("another Agent run is already active")
            with self._database.connection() as connection:
                existing = AgentRepository(connection).find_run_by_idempotency(
                    kind=kind, idempotency_key=idempotency_key
                )
            if existing is not None:
                expected = (
                    conversation_id,
                    study_session_id,
                    kind,
                    user_intent,
                    mode,
                    input_data,
                )
                actual = tuple(
                    existing[key]
                    for key in (
                        "conversation_id",
                        "study_session_id",
                        "kind",
                        "user_intent",
                        "mode",
                        "input",
                    )
                )
                if actual != expected:
                    raise ValueError(
                        "idempotency key was reused with a different run payload"
                    )
                return existing
            if self._provider_factory is None:
                raise AgentProviderMissingError(
                    "no real Agent provider is configured for this installation"
                )
            try:
                provider = self._provider_factory()
            except Exception as error:
                raise AgentProviderUnavailableError(
                    "the configured Agent provider could not be initialized"
                ) from error
            proposed_run_id = f"run-{uuid.uuid4().hex}"
            try:
                with self._database.connection() as connection:
                    run = AgentRepository(connection).create_run(
                        run_id=proposed_run_id,
                        kind=kind,
                        provider=provider.name,
                        model=provider.model,
                        user_intent=user_intent,
                        mode=mode,
                        prompt_version=provider.version,
                        input_data=input_data,
                        idempotency_key=idempotency_key,
                        conversation_id=conversation_id,
                        study_session_id=study_session_id,
                    )
            except BaseException:
                await close_provider_safely(provider)
                raise
            if run["id"] != proposed_run_id:
                await close_provider_safely(provider)
                return run

            # Claim the app-scoped slot before returning to the HTTP caller. The
            # background task opens and owns its audit connection itself.
            self._active_run_id = proposed_run_id
            self._active_provider = provider
            self._active_request = request_signature
            task = asyncio.create_task(
                self._execute(proposed_run_id, provider),
                name=f"keen-agent-{proposed_run_id}",
            )
            self._active_task = task
            task.add_done_callback(self._schedule_clear)
            return run

    def get_run(self, run_id: str) -> dict | None:
        return self._event_store.get_run(run_id)

    def validate_event_cursor(self, run_id: str, event_id: str | None) -> None:
        if self.get_run(run_id) is None:
            raise LookupError("agent run not found")
        self._event_store.sequence_after_last_event_id(run_id, event_id)

    def stream_events(
        self,
        run_id: str,
        *,
        last_event_id: str | None,
        disconnected: asyncio.Event,
    ) -> AsyncIterator[DurableAgentEvent]:
        return DurableEventStream(self._event_store).replay(
            run_id,
            last_event_id=last_event_id,
            disconnected=disconnected,
        )

    async def cancel(self, run_id: str) -> tuple[bool, dict]:
        prepublish_provider: AgentProvider | None = None
        async with self._lock:
            run = self.get_run(run_id)
            if run is None:
                raise LookupError("agent run not found")
            if self._active_run_id != run_id:
                return False, run
            orchestrator = self._active_orchestrator
            task = self._active_task
            provider = self._active_provider
            if orchestrator is None:
                if task is not None:
                    task.cancel()
                self._event_store.finish_run(
                    run_id,
                    status="cancelled",
                    error_code="cancelled",
                    error_detail="Agent run was cancelled before starting",
                )
                updated = self.get_run(run_id)
                if updated is None:  # pragma: no cover - protected by foreign key
                    raise RuntimeError("cancelled Agent run disappeared")
                prepublish_provider = provider
            else:
                updated = None
        if prepublish_provider is not None:
            await close_provider_safely(prepublish_provider)
            if updated is None:  # pragma: no cover - assigned above
                raise RuntimeError("cancelled Agent run disappeared")
            return True, updated
        if orchestrator is None:
            if updated is None:  # pragma: no cover - assigned above
                raise RuntimeError("cancelled Agent run disappeared")
            return True, updated
        accepted = await orchestrator.cancel(run_id)
        updated = self.get_run(run_id)
        if updated is None:  # pragma: no cover - protected by foreign key
            raise RuntimeError("cancelled Agent run disappeared")
        return accepted, updated

    async def shutdown(self) -> None:
        deadline = asyncio.get_running_loop().time() + 5.0
        async with self._lock:
            task = self._active_task
            orchestrator = self._active_orchestrator
            provider = self._active_provider
            run_id = self._active_run_id
        if task is None or task.done():
            return
        if orchestrator is not None and run_id is not None:
            with contextlib.suppress(LookupError):
                await orchestrator.cancel(run_id)
        else:
            if run_id is not None:
                self._finish_cancelled_if_active(
                    run_id, "Agent run was cancelled during sidecar shutdown"
                )
            task.cancel()
            if provider is not None:
                await close_provider_safely(
                    provider,
                    timeout=max(
                        0.01, min(1.0, deadline - asyncio.get_running_loop().time())
                    ),
                )
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        done, _ = await asyncio.wait({task}, timeout=remaining)
        if task not in done:
            if run_id is not None:
                self._finish_cancelled_if_active(
                    run_id, "Agent run exceeded the sidecar shutdown deadline"
                )
            task.cancel()
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            if remaining:
                await asyncio.wait({task}, timeout=remaining)

    async def _execute(self, run_id: str, provider: AgentProvider) -> None:
        orchestrator: AgentOrchestrator | None = None
        try:
            # This connection is background-task-owned. It never comes from a
            # FastAPI yield dependency and remains open for the complete tool run.
            with self._database.connection() as audit_connection:
                sink = SQLiteAuditSink(
                    audit_connection,
                    reconciliation_connection_factory=self._database.connection,
                )
                registry = ToolRegistry()
                register_initial_product_tools(
                    registry, connection_factory=self._database.connection
                )
                executor = AgentStepExecutor(
                    registry,
                    sink,
                    transaction_factory=sink.transaction,
                )
                orchestrator = AgentOrchestrator(
                    event_store=self._event_store,
                    provider=provider,
                    executor=executor,
                )
                async with self._lock:
                    if self._active_run_id == run_id:
                        self._active_orchestrator = orchestrator
                await orchestrator.run(run_id)
        except asyncio.CancelledError:
            run = self.get_run(run_id)
            if run is not None and run["status"] not in {
                "completed",
                "failed",
                "cancelled",
                "interrupted",
            }:
                self._event_store.finish_run(
                    run_id,
                    status="cancelled",
                    error_code="cancelled",
                    error_detail="Agent run was cancelled before completion",
                )
            raise
        except Exception:
            run = self.get_run(run_id)
            if run is not None and run["status"] not in {
                "completed",
                "failed",
                "cancelled",
                "interrupted",
            }:
                self._event_store.finish_run(
                    run_id,
                    status="failed",
                    error_code="agent_runtime_error",
                    error_detail="Agent runtime failed before provider execution",
                )
        finally:
            if orchestrator is None:
                await close_provider_safely(provider)

    def _finish_cancelled_if_active(self, run_id: str, detail: str) -> None:
        run = self.get_run(run_id)
        if run is not None and run["status"] not in {
            "completed",
            "failed",
            "cancelled",
            "interrupted",
        }:
            self._event_store.finish_run(
                run_id,
                status="cancelled",
                error_code="cancelled",
                error_detail=detail,
            )

    def _schedule_clear(self, task: asyncio.Task[None]) -> None:
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(self._clear_if_active(task))

    async def _clear_if_active(self, task: asyncio.Task[None]) -> None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            task.exception()
        async with self._lock:
            if self._active_task is task:
                self._active_task = None
                self._active_run_id = None
                self._active_orchestrator = None
                self._active_provider = None
                self._active_request = None


__all__ = [
    "AgentBusyError",
    "AgentProviderFactory",
    "AgentProviderMissingError",
    "AgentProviderUnavailableError",
    "AgentRuntimeManager",
]
