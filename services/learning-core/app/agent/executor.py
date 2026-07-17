from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping
from typing import AsyncContextManager

from pydantic import ValidationError

from .audit import (
    AuditSink,
    ToolAuditReservation,
    ToolAuditStart,
    ToolAuditSuccess,
    ToolAuditTerminal,
    summarize_for_audit,
    summarize_mutation,
)
from .registry import ToolRegistry
from .transaction import LocalWriteSession
from .types import (
    PermissionLevel,
    StateMutation,
    ToolArguments,
    ToolContext,
    ToolOutput,
    ToolResult,
    ToolReplayResult,
)

TransactionFactory = Callable[[], AsyncContextManager[LocalWriteSession]]


class ToolPermissionError(PermissionError):
    pass


class ConfirmationRequiredError(ToolPermissionError):
    pass


class ToolContractError(RuntimeError):
    pass


class ToolArgumentValidationError(ValueError):
    """Provider arguments did not satisfy a registered tool's input model."""


class RecoverableReadToolError(RuntimeError):
    """An explicitly classified, side-effect-free temporary read failure.

    Tools may raise this only after deciding that retrying or choosing another
    read tool is safe.  It intentionally carries no provider-facing detail.
    """


class ToolAuditUncertainError(RuntimeError):
    """A terminal audit write failed after a tool failure."""


class AgentStepExecutor:
    """Execute one provider-neutral tool step without retaining model reasoning.

    A failed ``record_started`` aborts before tool execution and does not make
    a second call to the sink that failed to establish the invocation. A failed
    Level 2 ``record_succeeded`` first leaves (and rolls back) the caller-owned
    transaction, then records a terminal failure outside that transaction.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        audit_sink: AuditSink,
        *,
        transaction_factory: TransactionFactory | None = None,
    ) -> None:
        self._registry = registry
        self._audit_sink = audit_sink
        self._transaction_factory = transaction_factory

    def is_bound_to(
        self, registry: ToolRegistry, *, require_non_transactional: bool = False
    ) -> bool:
        """Return whether this exact executor is bound to the trusted registry."""

        return self._registry is registry and (
            not require_non_transactional or self._transaction_factory is None
        )

    async def execute_step(
        self,
        *,
        invocation_id: str,
        idempotency_key: str | None = None,
        tool_name: str,
        arguments: Mapping[str, object],
        context: ToolContext,
    ) -> ToolResult | ToolReplayResult:
        tool = self._registry.get(tool_name)
        try:
            validated = self._registry.validate_arguments(tool_name, arguments)
        except ValidationError as error:
            raise ToolArgumentValidationError("tool arguments are invalid") from error
        context.raise_if_cancelled()
        reservation = await self._audit_sink.record_started(
            ToolAuditStart(
                invocation_id=invocation_id,
                run_id=context.run_id,
                step_id=context.step_id,
                tool_name=tool_name,
                permission_level=tool.permission_level,
                arguments=summarize_for_audit(validated.model_dump(mode="json")),
                idempotency_key=idempotency_key or invocation_id,
            )
        )
        if isinstance(reservation, ToolAuditReservation):
            if reservation.disposition == "replay":
                return ToolReplayResult(
                    invocation_id=reservation.invocation_id,
                    result_summary=reservation.result_summary or {},
                    mutation_ids=reservation.mutation_ids,
                )
            if reservation.invocation_id != invocation_id:
                raise RuntimeError("audit reservation returned a mismatched invocation")
        terminal = ToolAuditTerminal(
            invocation_id=invocation_id,
            error_code="permission_denied",
        )
        if tool.permission_level is PermissionLevel.CONFIRM_FIRST:
            await self._audit_sink.record_rejected(terminal)
            raise ConfirmationRequiredError(
                "Level 3 tools require confirmation and are unavailable in this milestone"
            )
        if (
            tool.permission_level is PermissionLevel.LOCAL_REVERSIBLE
            and self._transaction_factory is None
        ):
            await self._audit_sink.record_rejected(terminal)
            raise ToolPermissionError(
                "Level 2 tools require a caller-provided transaction context"
            )

        try:
            if tool.permission_level is PermissionLevel.LOCAL_REVERSIBLE:
                return await self._execute_level_two(
                    invocation_id=invocation_id,
                    tool=tool,
                    arguments=validated,
                    context=context,
                )
            context.raise_if_cancelled()
            result = await self._run_cancellable(
                tool.execute(validated, context), context
            )
            result = self._validate_result(
                PermissionLevel.AUTOMATIC, tool.result_model, result
            )
            await self._audit_sink.record_succeeded(
                self._success_record(invocation_id, result),
                mutations=result.mutations,
                transaction=None,
            )
            return result
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await self._audit_sink.record_cancelled(
                    ToolAuditTerminal(
                        invocation_id=invocation_id,
                        error_code="cancelled",
                    )
                )
            raise
        except Exception as error:
            try:
                await self._audit_sink.record_failed(
                    ToolAuditTerminal(
                        invocation_id=invocation_id,
                        error_code=type(error).__name__,
                    )
                )
            except Exception:
                error.add_note("The terminal tool audit could not be recorded")
                if isinstance(error, RecoverableReadToolError):
                    raise ToolAuditUncertainError(
                        "terminal tool audit state is uncertain"
                    ) from None
            raise

    async def _execute_level_two(
        self,
        *,
        invocation_id: str,
        tool,
        arguments: ToolArguments,
        context: ToolContext,
    ) -> ToolResult:
        if self._transaction_factory is None:  # pragma: no cover - checked by caller
            raise ToolPermissionError("missing transaction factory")
        async with self._transaction_factory() as transaction:
            transactional_context = context.with_transaction(transaction)
            transactional_context.raise_if_cancelled()
            result = await self._run_cancellable(
                tool.execute(arguments, transactional_context), transactional_context
            )
            result = self._validate_result(
                PermissionLevel.LOCAL_REVERSIBLE, tool.result_model, result
            )
            transactional_context.raise_if_cancelled()
            await self._audit_sink.record_succeeded(
                self._success_record(invocation_id, result),
                mutations=result.mutations,
                transaction=transaction,
            )
            return result

    @staticmethod
    def _validate_result(
        permission: PermissionLevel,
        result_model: type[ToolOutput],
        result: ToolResult,
    ) -> ToolResult:
        if not isinstance(result, ToolResult):
            raise ToolContractError("registered tools must return ToolResult")
        try:
            validated = ToolResult.model_validate(result.model_dump(mode="python"))
        except ValidationError as error:
            if permission is PermissionLevel.LOCAL_REVERSIBLE:
                raise ToolPermissionError(
                    "Level 2 tools must return valid, bounded before/after/undo mutation data"
                ) from error
            raise ToolContractError("tool returned an invalid result") from error
        if permission is PermissionLevel.AUTOMATIC and validated.mutations:
            raise ToolPermissionError("Level 1 tools cannot mutate state")
        if permission is PermissionLevel.LOCAL_REVERSIBLE:
            if not validated.mutations:
                raise ToolPermissionError(
                    "Level 2 tools must return before/after/undo mutation data"
                )
            for mutation in validated.mutations:
                required = {"before", "after", "undo"}
                if not isinstance(mutation, StateMutation) or not required.issubset(
                    mutation.model_fields_set
                ):
                    raise ToolPermissionError(
                        "Level 2 tools must return before/after/undo mutation data"
                    )
        try:
            output = result_model.model_validate(
                validated.output, strict=True
            ).model_dump(mode="json")
            return ToolResult(output=output, mutations=validated.mutations)
        except ValidationError as error:
            raise ToolContractError(
                "tool output does not match its registered result model"
            ) from error

    @staticmethod
    def _success_record(invocation_id: str, result: ToolResult) -> ToolAuditSuccess:
        return ToolAuditSuccess(
            invocation_id=invocation_id,
            result=summarize_for_audit(result.output),
            mutations=tuple(summarize_mutation(item) for item in result.mutations),
        )

    @staticmethod
    async def _run_cancellable(awaitable, context: ToolContext) -> ToolResult:
        execution = asyncio.ensure_future(awaitable)
        cancellation = asyncio.create_task(context.cancellation_event.wait())
        try:
            done, _ = await asyncio.wait(
                {execution, cancellation}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancellation in done and context.cancellation_event.is_set():
                execution.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await execution
                raise asyncio.CancelledError
            cancellation.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancellation
            result = await execution
            context.raise_if_cancelled()
            return result
        except asyncio.CancelledError:
            execution.cancel()
            cancellation.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await execution
            raise
        finally:
            cancellation.cancel()
