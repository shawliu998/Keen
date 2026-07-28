from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import Field

from ..schemas import ApiModel
from ..services.agent_undo import (
    AgentUndoConflictError,
    AgentUndoForbiddenError,
    AgentUndoNotFoundError,
    AgentUndoResult,
    AgentUndoService,
    UndoAction,
)

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
SafeIdentifier = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
]


class AgentMutationActionRequest(ApiModel):
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )


class AgentMutationActionResponse(ApiModel):
    action: Literal["undo", "redo"]
    run_id: str = Field(alias="runId")
    target_mutation_id: str = Field(alias="targetMutationId")
    invocation_id: str = Field(alias="invocationId")
    mutation_id: str = Field(alias="mutationId")
    entity_type: Literal["study_task"] = Field(alias="entityType")
    entity_id: str = Field(alias="entityId")
    operation: Literal["update"]
    replayed: bool


router = APIRouter(prefix="/v1/agent/runs", tags=["agent"])


def _service(request: Request) -> AgentUndoService:
    return request.app.state.agent_undo


def _response(result: AgentUndoResult) -> AgentMutationActionResponse:
    return AgentMutationActionResponse(
        action=result.action,
        run_id=result.run_id,
        target_mutation_id=result.target_mutation_id,
        invocation_id=result.invocation_id,
        mutation_id=result.mutation_id,
        entity_type=result.entity_type,  # type: ignore[arg-type]
        entity_id=result.entity_id,
        operation=result.operation,  # type: ignore[arg-type]
        replayed=result.replayed,
    )


async def _execute(
    *,
    request: Request,
    action: UndoAction,
    run_id: str,
    mutation_id: str,
    payload: AgentMutationActionRequest,
) -> AgentMutationActionResponse:
    try:
        result = await _service(request).execute(
            action=action,
            run_id=run_id,
            mutation_id=mutation_id,
            idempotency_key=payload.idempotency_key,
        )
    except AgentUndoNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "mutation_not_found",
                "message": "The mutation was not found for this Agent run.",
                "retryable": False,
                "recoveryAction": "Refresh the Agent activity and choose an available mutation.",
                "automaticRecovery": False,
            },
        ) from None
    except AgentUndoForbiddenError:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "mutation_action_forbidden",
                "message": "This mutation type is not enabled for local reversal.",
                "retryable": False,
                "recoveryAction": "Only use Undo or Redo on an allowlisted study-task mutation.",
                "automaticRecovery": False,
            },
        ) from None
    except AgentUndoConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.code
                in {"run_not_terminal", "undo_in_progress", "undo_conflict"},
                "recoveryAction": (
                    "Refresh the Agent activity before retrying. Use a new idempotency key only after a terminal failure."
                ),
                "automaticRecovery": False,
            },
        ) from None
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "mutation_action_failed",
                "message": "The local mutation action could not be completed safely.",
                "retryable": True,
                "recoveryAction": "Refresh the Agent activity, verify the task state, and retry with the same idempotency key.",
                "automaticRecovery": False,
                "outcomeMayBeDurable": True,
            },
        ) from None
    return _response(result)


@router.post(
    "/{run_id}/mutations/{mutation_id}/undo",
    response_model=AgentMutationActionResponse,
)
async def undo_agent_mutation(
    request: Request,
    run_id: SafeIdentifier,
    mutation_id: SafeIdentifier,
    payload: AgentMutationActionRequest,
) -> AgentMutationActionResponse:
    return await _execute(
        request=request,
        action="undo",
        run_id=run_id,
        mutation_id=mutation_id,
        payload=payload,
    )


@router.post(
    "/{run_id}/mutations/{mutation_id}/redo",
    response_model=AgentMutationActionResponse,
)
async def redo_agent_mutation(
    request: Request,
    run_id: SafeIdentifier,
    mutation_id: SafeIdentifier,
    payload: AgentMutationActionRequest,
) -> AgentMutationActionResponse:
    return await _execute(
        request=request,
        action="redo",
        run_id=run_id,
        mutation_id=mutation_id,
        payload=payload,
    )


__all__ = [
    "AgentMutationActionRequest",
    "AgentMutationActionResponse",
    "router",
]
