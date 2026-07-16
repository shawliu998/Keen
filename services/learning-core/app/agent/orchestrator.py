from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from typing import Protocol

from .audit import summarize_for_audit
from .event_stream import AgentEventStore
from .provider import (
    AgentProvider,
    close_provider_safely,
    ContentDelta,
    ProviderAction,
    ProviderCheckpoint,
    ProviderDisconnectedError,
    ProviderFinished,
    ProviderOutputError,
    ProviderRequest,
    ProviderToolResult,
    ProviderWarning,
    ToolCall,
)
from .sqlite_audit import mutation_id_for_invocation
from .types import ToolContext, ToolReplayResult, ToolResult

_MAX_PROVIDER_ACTIONS = 1_000
_MAX_PROVIDER_BYTES = 4 * 1024 * 1024
_MAX_CONTENT_BYTES = 2 * 1024 * 1024
_MAX_TOOL_ROUNDS = 16
_MAX_TOOL_FEEDBACK_BYTES = 256 * 1024
_PROVIDER_FEEDBACK_CANCEL_TIMEOUT_SECONDS = 1.0


def _consume_task_result(task: asyncio.Task[None]) -> None:
    with contextlib.suppress(BaseException):
        task.exception()


async def _cancel_submission_safely(submission: asyncio.Task[None]) -> None:
    submission.cancel()
    done, _ = await asyncio.wait(
        {submission}, timeout=_PROVIDER_FEEDBACK_CANCEL_TIMEOUT_SECONDS
    )
    if submission not in done:
        submission.add_done_callback(_consume_task_result)
        return
    with contextlib.suppress(BaseException):
        submission.result()


class StepExecutor(Protocol):
    async def execute_step(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
        context: ToolContext,
        idempotency_key: str | None = None,
    ) -> ToolResult | ToolReplayResult: ...


class AgentOrchestrator:
    """One cancellable provider loop over a closed tool executor."""

    def __init__(
        self,
        *,
        event_store: AgentEventStore,
        provider: AgentProvider,
        executor: StepExecutor,
    ) -> None:
        self._event_store = event_store
        self._provider = provider
        self._executor = executor
        self._active: dict[str, asyncio.Event] = {}
        self._active_lock = asyncio.Lock()

    async def run(self, run_id: str) -> None:
        cancellation = asyncio.Event()
        started = False
        async with self._active_lock:
            if self._active:
                raise RuntimeError(
                    "single-Agent orchestrator already has an active run"
                )
            self._active[run_id] = cancellation
        try:
            run = self._event_store.get_run(run_id)
            if run is None:
                raise LookupError("agent run not found")
            self._event_store.start_run(
                run_id,
                metadata={
                    "runId": run_id,
                    "provider": self._provider.name,
                    "model": self._provider.model,
                    "providerVersion": self._provider.version,
                },
            )
            started = True
            request = ProviderRequest(
                run_id=run_id,
                user_intent=run["user_intent"],
                mode=run["mode"],
                input=run["input"],
            )
            finished = False
            ordinal = 0
            provider_bytes = 0
            content_bytes = 0
            tool_rounds = 0
            tool_feedback_bytes = 0
            iterator = self._provider.stream(request).__aiter__()
            while not finished:
                action = await self._next_action(iterator, cancellation)
                ordinal += 1
                if ordinal > _MAX_PROVIDER_ACTIONS:
                    raise ProviderLimitError("provider action limit exceeded")
                provider_bytes += len(
                    json.dumps(
                        action.model_dump(mode="json"),
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                )
                if provider_bytes > _MAX_PROVIDER_BYTES:
                    raise ProviderLimitError("provider byte limit exceeded")
                if isinstance(action, ContentDelta):
                    content_bytes += len(action.text.encode("utf-8"))
                    if content_bytes > _MAX_CONTENT_BYTES:
                        raise ProviderLimitError("provider content limit exceeded")
                if isinstance(action, ProviderFinished):
                    finished = True
                    continue
                if isinstance(action, ToolCall):
                    tool_rounds += 1
                    if tool_rounds > _MAX_TOOL_ROUNDS:
                        raise ProviderLimitError("provider tool round limit exceeded")
                feedback = await self._handle_action(
                    run_id=run_id,
                    ordinal=ordinal - 1,
                    action=action,
                    cancellation=cancellation,
                )
                if feedback is not None:
                    feedback_bytes = len(
                        json.dumps(
                            feedback.model_dump(mode="json"),
                            ensure_ascii=False,
                            allow_nan=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ).encode("utf-8")
                    )
                    tool_feedback_bytes += feedback_bytes
                    if tool_feedback_bytes > _MAX_TOOL_FEEDBACK_BYTES:
                        raise ProviderLimitError(
                            "provider tool feedback byte limit exceeded"
                        )
                    cancellation_check(cancellation)
                    await self._submit_tool_result(feedback, cancellation)
            cancellation_check(cancellation)
            self._event_store.finish_run(run_id, status="completed")
        except asyncio.CancelledError:
            cancellation.set()
            if started:
                self._event_store.finish_run(
                    run_id,
                    status="cancelled",
                    error_code="cancelled",
                    error_detail="Agent run was cancelled before completion",
                )
            raise
        except Exception as error:
            if not started:
                raise
            with contextlib.suppress(Exception):
                self._event_store.recover_completed_tool_steps(run_id=run_id)
            self._event_store.finish_run(
                run_id,
                status="failed",
                error_code=_error_code(error),
                error_detail=_safe_error_detail(error),
            )
        finally:
            await close_provider_safely(self._provider)
            async with self._active_lock:
                self._active.pop(run_id, None)

    async def cancel(self, run_id: str) -> bool:
        async with self._active_lock:
            cancellation = self._active.get(run_id)
            if cancellation is None:
                run = self._event_store.get_run(run_id)
                if run is None:
                    raise LookupError("agent run not found")
                if run["status"] != "queued":
                    return False
                self._event_store.finish_run(
                    run_id,
                    status="cancelled",
                    error_code="cancelled",
                    error_detail="Agent run was cancelled before starting",
                )
                return True
            cancellation.set()
            return True

    async def _handle_action(
        self,
        *,
        run_id: str,
        ordinal: int,
        action: ProviderAction,
        cancellation: asyncio.Event,
    ) -> ProviderToolResult | None:
        cancellation_check(cancellation)
        if isinstance(action, ContentDelta):
            self._event_store.append(run_id, "content_delta", {"delta": action.text})
            return None
        if isinstance(action, ProviderCheckpoint):
            self._event_store.append(
                run_id,
                "checkpoint",
                {"label": action.label, "data": action.data},
            )
            return None
        if isinstance(action, ProviderWarning):
            self._event_store.append(
                run_id,
                "warning",
                {"code": action.code, "message": action.message},
            )
            return None
        if isinstance(action, ToolCall):
            submit_tool_result = getattr(self._provider, "submit_tool_result", None)
            if not callable(submit_tool_result):
                raise ProviderProtocolError(
                    "provider emitted a tool call but cannot accept its result"
                )
            stable_digest = hashlib.sha256(
                f"{run_id}\0{action.call_id}".encode("utf-8")
            ).hexdigest()
            invocation_id = f"inv-{stable_digest}"
            step_id = f"step-{stable_digest}"
            idempotency_key = f"tool-{stable_digest}"
            self._event_store.start_tool_step(
                run_id=run_id,
                step_id=step_id,
                ordinal=ordinal,
                invocation_id=invocation_id,
                tool_name=action.tool_name,
                input_data={
                    "toolName": action.tool_name,
                    "callId": action.call_id,
                },
            )
            try:
                result = await self._executor.execute_step(
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    tool_name=action.tool_name,
                    arguments=action.arguments,
                    context=ToolContext(
                        run_id=run_id,
                        step_id=step_id,
                        cancellation_event=cancellation,
                    ),
                )
            except BaseException as error:
                with contextlib.suppress(Exception):
                    self._event_store.finish_tool_step_error(
                        run_id=run_id,
                        step_id=step_id,
                        status=(
                            "cancelled"
                            if isinstance(error, asyncio.CancelledError)
                            else "failed"
                        ),
                        error_code=(
                            "cancelled"
                            if isinstance(error, asyncio.CancelledError)
                            else _error_code(error)
                        ),
                    )
                raise
            if isinstance(result, ToolReplayResult):
                result_payload = {
                    "callId": action.call_id,
                    "invocationId": result.invocation_id,
                    "toolName": action.tool_name,
                    "result": result.result_summary,
                    "replayed": True,
                }
                mutation_payloads = [
                    {
                        "callId": action.call_id,
                        "invocationId": result.invocation_id,
                        "mutationId": mutation_id,
                        "replayed": True,
                    }
                    for mutation_id in result.mutation_ids
                ]
                feedback = ProviderToolResult(
                    call_id=action.call_id,
                    tool_name=action.tool_name,
                    invocation_id=result.invocation_id,
                    fidelity="audit_summary",
                    replayed=True,
                    output=result.result_summary,
                    mutation_ids=result.mutation_ids,
                )
            else:
                result_summary = summarize_for_audit(result.output)
                result_payload = {
                    "callId": action.call_id,
                    "invocationId": invocation_id,
                    "toolName": action.tool_name,
                    "result": result_summary.summary,
                    "truncated": result_summary.truncated,
                    "replayed": False,
                }
                mutation_payloads = [
                    {
                        "callId": action.call_id,
                        "invocationId": invocation_id,
                        "mutationId": mutation_id_for_invocation(
                            invocation_id, ordinal
                        ),
                        "entityType": mutation.entity_type,
                        "entityId": mutation.entity_id,
                        "operation": mutation.operation,
                        "reversible": True,
                    }
                    for ordinal, mutation in enumerate(result.mutations)
                ]
                feedback = ProviderToolResult(
                    call_id=action.call_id,
                    tool_name=action.tool_name,
                    invocation_id=invocation_id,
                    fidelity="full",
                    replayed=False,
                    output=result.output,
                    mutation_ids=tuple(
                        mutation_id_for_invocation(invocation_id, index)
                        for index, _mutation in enumerate(result.mutations)
                    ),
                )
            self._event_store.complete_tool_step(
                run_id=run_id,
                step_id=step_id,
                result_payload=result_payload,
                mutation_payloads=mutation_payloads,
            )
            return feedback
        raise TypeError(f"unsupported provider action: {type(action).__name__}")

    async def _submit_tool_result(
        self,
        feedback: ProviderToolResult,
        cancellation: asyncio.Event,
    ) -> None:
        submit_tool_result = getattr(self._provider, "submit_tool_result", None)
        if not callable(
            submit_tool_result
        ):  # pragma: no cover - checked before tool run
            raise ProviderProtocolError(
                "provider emitted a tool call but cannot accept its result"
            )
        submission = asyncio.create_task(submit_tool_result(feedback))
        cancelled = asyncio.create_task(cancellation.wait())
        try:
            done, _ = await asyncio.wait(
                {submission, cancelled}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancelled in done and cancellation.is_set():
                await _cancel_submission_safely(submission)
                raise asyncio.CancelledError
            cancelled.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancelled
            await submission
        except asyncio.CancelledError:
            await _cancel_submission_safely(submission)
            cancelled.cancel()
            raise
        finally:
            cancelled.cancel()

    @staticmethod
    async def _next_action(
        iterator: AsyncIterator[ProviderAction], cancellation: asyncio.Event
    ) -> ProviderAction:
        next_action = asyncio.create_task(iterator.__anext__())
        cancelled = asyncio.create_task(cancellation.wait())
        try:
            done, _ = await asyncio.wait(
                {next_action, cancelled}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancelled in done and cancellation.is_set():
                next_action.cancel()
                with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                    await next_action
                raise asyncio.CancelledError
            cancelled.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancelled
            try:
                return await next_action
            except StopAsyncIteration as error:
                raise ProviderDisconnectedError(
                    "provider disconnected before an explicit finished action"
                ) from error
        except asyncio.CancelledError:
            next_action.cancel()
            cancelled.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await next_action
            raise
        finally:
            cancelled.cancel()


def cancellation_check(cancellation: asyncio.Event) -> None:
    if cancellation.is_set():
        raise asyncio.CancelledError


def _error_code(error: Exception) -> str:
    if isinstance(error, ProviderDisconnectedError):
        return "provider_disconnected"
    if isinstance(error, ProviderOutputError):
        return "provider_output_invalid"
    name = type(error).__name__
    code = "".join(
        ("_" + character.lower()) if character.isupper() else character
        for character in name
    ).lstrip("_")
    return code[:80] or "agent_error"


class ProviderLimitError(RuntimeError):
    pass


class ProviderProtocolError(RuntimeError):
    pass


def _safe_error_detail(error: Exception) -> str:
    if isinstance(error, ProviderDisconnectedError):
        return str(error)
    if isinstance(error, ProviderOutputError):
        return (
            "The Agent provider returned unusable output; the run did not complete. "
            "Retry, or choose another configured model."
        )
    return f"Agent run failed: {type(error).__name__}"


__all__ = ["AgentOrchestrator", "StepExecutor"]
