from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from typing import Protocol

from .audit import summarize_for_audit
from .catalog import ProviderToolPolicy, ProviderToolSpec
from .event_stream import AgentEventStore
from .executor import (
    AgentStepExecutor,
    RecoverableReadToolError,
    ToolArgumentValidationError,
)
from .provider import (
    AgentProvider,
    close_provider_safely,
    ContentDelta,
    FixedAutomationProvider,
    ProviderAction,
    ProviderCheckpoint,
    ProviderDisconnectedError,
    ProviderFinished,
    ProviderOutputError,
    ProviderRequest,
    ProviderToolError,
    ProviderToolFeedback,
    ProviderToolResult,
    ProviderWarning,
    ToolCall,
)
from .profile import AgentRunProfile
from .registry import ToolRegistry
from .sqlite_audit import mutation_id_for_invocation
from .types import ToolContext, ToolReplayResult, ToolResult

_MAX_PROVIDER_ACTIONS = 1_000
_MAX_PROVIDER_BYTES = 4 * 1024 * 1024
_MAX_CONTENT_BYTES = 2 * 1024 * 1024
_MAX_TOOL_ROUNDS = 16
_MAX_TOOL_FEEDBACK_BYTES = 256 * 1024
_MAX_RECOVERABLE_TOOL_ERRORS = 4
_MAX_IDENTICAL_RECOVERABLE_TOOL_ERRORS = 1
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


class Level2Proposer(Protocol):
    async def propose(
        self,
        *,
        run_id: str,
        call_id: str,
        arguments: Mapping[str, object],
    ) -> str: ...


class _ApprovalRequested:
    pass


class ProviderToolRuntime:
    """One inseparable provider catalog, allowlist, and constrained executor."""

    __slots__ = ("_executor", "_frozen", "_policy", "_proposal_tool_names")

    def __init__(self) -> None:
        raise TypeError("ProviderToolRuntime must be derived from a validated registry")

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("provider tool runtime is immutable")
        object.__setattr__(self, name, value)

    @classmethod
    def from_readonly_registry(
        cls, registry: ToolRegistry, executor: AgentStepExecutor
    ) -> ProviderToolRuntime:
        if cls is not ProviderToolRuntime:
            raise TypeError("provider tool runtime subclasses are not supported")
        if type(executor) is not AgentStepExecutor or not executor.is_bound_to(
            registry, require_non_transactional=True
        ):
            raise ValueError(
                "provider tool runtime requires the same non-transactional registry executor"
            )
        runtime = object.__new__(cls)
        object.__setattr__(runtime, "_executor", executor)
        object.__setattr__(
            runtime, "_policy", ProviderToolPolicy.from_readonly_registry(registry)
        )
        object.__setattr__(runtime, "_proposal_tool_names", frozenset())
        object.__setattr__(runtime, "_frozen", True)
        return runtime

    @classmethod
    def from_registry_with_proposals(
        cls,
        registry: ToolRegistry,
        executor: AgentStepExecutor,
        *,
        proposal_tool_names: frozenset[str],
    ) -> ProviderToolRuntime:
        if cls is not ProviderToolRuntime:
            raise TypeError("provider tool runtime subclasses are not supported")
        if type(executor) is not AgentStepExecutor or not executor.is_bound_to(
            registry, require_non_transactional=True
        ):
            raise ValueError(
                "provider tool runtime requires the same non-transactional registry executor"
            )
        runtime = object.__new__(cls)
        object.__setattr__(runtime, "_executor", executor)
        object.__setattr__(
            runtime,
            "_policy",
            ProviderToolPolicy.from_registry_with_proposals(
                registry, proposal_tool_names=proposal_tool_names
            ),
        )
        object.__setattr__(runtime, "_proposal_tool_names", proposal_tool_names)
        object.__setattr__(runtime, "_frozen", True)
        return runtime

    @property
    def executor(self) -> AgentStepExecutor:
        return self._executor

    @property
    def catalog(self) -> tuple[ProviderToolSpec, ...]:
        return self._policy.catalog

    @property
    def allowed_tool_names(self) -> frozenset[str]:
        return self._policy.allowed_tool_names

    @property
    def proposal_tool_names(self) -> frozenset[str]:
        return self._proposal_tool_names


class _RecoverableToolErrorBudget:
    """Bound private recovery feedback without retaining error details."""

    def __init__(self) -> None:
        self.count = 0
        self._fingerprints: dict[str, int] = {}

    def reserve(self, *, action: ToolCall, code: str) -> None:
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "toolName": action.tool_name,
                    "arguments": action.arguments,
                    "code": code,
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if self.count >= _MAX_RECOVERABLE_TOOL_ERRORS:
            raise ProviderLimitError("recoverable tool error limit exceeded")
        repeated = self._fingerprints.get(fingerprint, 0)
        if repeated >= _MAX_IDENTICAL_RECOVERABLE_TOOL_ERRORS:
            raise ProviderProtocolError(
                "provider repeated an unchanged recoverable tool failure"
            )
        self.count += 1
        self._fingerprints[fingerprint] = repeated + 1


class AgentOrchestrator:
    """One cancellable provider loop over a closed tool executor."""

    def __init__(
        self,
        *,
        event_store: AgentEventStore,
        provider: AgentProvider,
        executor: StepExecutor | None = None,
        tool_runtime: ProviderToolRuntime | None = None,
        level2_proposer: Level2Proposer | None = None,
        run_profile: AgentRunProfile | None = None,
    ) -> None:
        if executor is None and tool_runtime is None:
            raise ValueError("an Agent tool executor is required")
        if executor is not None and tool_runtime is not None:
            raise ValueError("executor and provider tool runtime cannot be combined")
        if tool_runtime is not None and type(tool_runtime) is not ProviderToolRuntime:
            raise ValueError("provider tool runtime must use the exact trusted type")
        self._event_store = event_store
        self._provider = provider
        self._run_profile = run_profile
        self._level2_proposer = level2_proposer
        self._proposal_tool_names: frozenset[str] = frozenset()
        if tool_runtime is not None:
            self._executor = tool_runtime.executor
            self._tool_catalog = tool_runtime.catalog
            self._allowed_tool_names = tool_runtime.allowed_tool_names
            self._proposal_tool_names = tool_runtime.proposal_tool_names
            if self._proposal_tool_names and level2_proposer is None:
                raise ValueError(
                    "proposal-only Level 2 catalog requires a host proposer"
                )
        elif type(provider) is FixedAutomationProvider:
            # Exact in-process fixtures may exercise their closed executor
            # registry in unit tests without exposing a provider catalog.
            if executor is None:  # pragma: no cover - checked above
                raise ValueError("an Agent tool executor is required")
            self._executor = executor
            self._tool_catalog = ()
            self._allowed_tool_names = None
        else:
            if executor is None:  # pragma: no cover - checked above
                raise ValueError("an Agent tool executor is required")
            self._executor = executor
            self._tool_catalog = ()
            self._allowed_tool_names = frozenset()
        if level2_proposer is not None and not self._proposal_tool_names:
            raise ValueError("host proposer requires an explicit proposal-only catalog")
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
                output_format=(
                    self._run_profile.output_format
                    if self._run_profile is not None
                    else "text"
                ),
                input=run["input"],
                tools=self._tool_catalog,
            )
            finished = False
            waiting_for_approval = False
            ordinal = 0
            provider_bytes = 0
            content_bytes = 0
            tool_rounds = 0
            content_parts: list[str] = []
            tool_feedback_bytes = 0
            recoverable_error_budget = _RecoverableToolErrorBudget()
            iterator = self._provider.stream(request).__aiter__()
            while not finished:
                action = await self._next_action(iterator, cancellation)
                ordinal += 1
                action_limit = (
                    self._run_profile.limits.maximum_provider_actions
                    if self._run_profile is not None
                    else _MAX_PROVIDER_ACTIONS
                )
                if ordinal > action_limit:
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
                    content_parts.append(action.text)
                    content_bytes += len(action.text.encode("utf-8"))
                    content_limit = (
                        self._run_profile.limits.maximum_content_bytes
                        if self._run_profile is not None
                        else _MAX_CONTENT_BYTES
                    )
                    if content_bytes > content_limit:
                        raise ProviderLimitError("provider content limit exceeded")
                if isinstance(action, ProviderFinished):
                    finished = True
                    continue
                if isinstance(action, ToolCall):
                    tool_rounds += 1
                    tool_limit = (
                        self._run_profile.limits.maximum_tool_calls
                        if self._run_profile is not None
                        else _MAX_TOOL_ROUNDS
                    )
                    if tool_rounds > tool_limit:
                        raise ProviderLimitError("provider tool round limit exceeded")
                feedback = await self._handle_action(
                    run_id=run_id,
                    ordinal=ordinal - 1,
                    action=action,
                    cancellation=cancellation,
                    recoverable_error_budget=recoverable_error_budget,
                )
                if isinstance(feedback, _ApprovalRequested):
                    waiting_for_approval = True
                    break
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
            if not waiting_for_approval:
                if self._run_profile is not None:
                    publication = await self._run_profile.publish_completion(
                        run_id=run_id,
                        content="".join(content_parts),
                    )
                    self._event_store.append(
                        run_id,
                        "checkpoint",
                        {
                            "label": "completion_published",
                            "data": publication,
                        },
                    )
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
        recoverable_error_budget: _RecoverableToolErrorBudget,
    ) -> ProviderToolFeedback | _ApprovalRequested | None:
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
            if (
                self._allowed_tool_names is not None
                and action.tool_name not in self._allowed_tool_names
            ):
                raise ProviderProtocolError(
                    "provider requested a tool outside its runtime allowlist"
                )
            submit_tool_result = getattr(self._provider, "submit_tool_result", None)
            if not callable(submit_tool_result):
                raise ProviderProtocolError(
                    "provider emitted a tool call but cannot accept its result"
                )
            if action.tool_name in self._proposal_tool_names:
                if (
                    self._level2_proposer is None
                ):  # pragma: no cover - constructor invariant
                    raise ProviderProtocolError(
                        "proposal tool has no trusted host proposer"
                    )
                try:
                    await self._level2_proposer.propose(
                        run_id=run_id,
                        call_id=action.call_id,
                        arguments=action.arguments,
                    )
                except ToolArgumentValidationError:
                    proposal_digest = hashlib.sha256(
                        (run_id + "\0" + action.call_id).encode()
                    ).hexdigest()
                    invocation_id = f"inv-{proposal_digest}"
                    step_id = f"step-{proposal_digest}"
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
                    feedback = ProviderToolError(
                        call_id=action.call_id,
                        tool_name=action.tool_name,
                        invocation_id=invocation_id,
                        code="invalid_arguments",
                        category="validation",
                        retryable=True,
                        recovery_action="correct_arguments",
                    )
                    self._event_store.fail_tool_step_with_result(
                        run_id=run_id,
                        step_id=step_id,
                        error_code=feedback.code,
                        result_payload={
                            "callId": action.call_id,
                            "invocationId": invocation_id,
                            "toolName": action.tool_name,
                            "failed": True,
                            "code": feedback.code,
                            "retryable": feedback.retryable,
                            "replayed": False,
                        },
                    )
                    recoverable_error_budget.reserve(action=action, code=feedback.code)
                    return feedback
                return _ApprovalRequested()
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
                try:
                    cancellation_check(cancellation)
                except asyncio.CancelledError:
                    with contextlib.suppress(Exception):
                        self._event_store.finish_tool_step_error(
                            run_id=run_id,
                            step_id=step_id,
                            status="cancelled",
                            error_code="cancelled",
                        )
                    raise
                recoverable = _recoverable_tool_error(
                    error,
                    call_id=action.call_id,
                    tool_name=action.tool_name,
                    invocation_id=invocation_id,
                    allowed_read_tool=(
                        self._allowed_tool_names is not None
                        and action.tool_name in self._allowed_tool_names
                    ),
                )
                if recoverable is None:
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
                # The failed step and its redacted public result become durable
                # together before any private feedback budget decision.
                self._event_store.fail_tool_step_with_result(
                    run_id=run_id,
                    step_id=step_id,
                    error_code=recoverable.code,
                    result_payload={
                        "callId": action.call_id,
                        "invocationId": invocation_id,
                        "toolName": action.tool_name,
                        "failed": True,
                        "code": recoverable.code,
                        "retryable": recoverable.retryable,
                        "replayed": False,
                    },
                )
                recoverable_error_budget.reserve(action=action, code=recoverable.code)
                return recoverable
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
        feedback: ProviderToolFeedback,
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


def _recoverable_tool_error(
    error: BaseException,
    *,
    call_id: str,
    tool_name: str,
    invocation_id: str,
    allowed_read_tool: bool,
) -> ProviderToolError | None:
    """Classify only safe post-call Level 1 failures for private recovery."""

    if not allowed_read_tool or isinstance(error, asyncio.CancelledError):
        return None
    # Permission failures are never eligible, even if a caller accidentally
    # supplies a Level 2/3 executor.
    if isinstance(error, PermissionError):
        return None
    if isinstance(error, ToolArgumentValidationError):
        code = "invalid_arguments"
    elif isinstance(error, RecoverableReadToolError):
        code = "temporary_read_failure"
    else:
        return None
    fields = {
        "invalid_arguments": ("validation", True, "correct_arguments"),
        "temporary_read_failure": (
            "temporary",
            True,
            "retry_or_use_another_tool",
        ),
    }[code]
    return ProviderToolError(
        call_id=call_id,
        tool_name=tool_name,
        invocation_id=invocation_id,
        code=code,
        category=fields[0],
        retryable=fields[1],
        recovery_action=fields[2],
    )


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
