from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator

from ..agent.event_stream import encode_sse
from ..agent.types import is_hidden_reasoning_key, validate_bounded_json_object
from ..repositories import JsonValue
from ..schemas import ApiModel
from ..services.agent_runtime import (
    AgentBusyError,
    AgentProviderMissingError,
    AgentProviderUnavailableError,
    AgentRuntimeManager,
)

_IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
AgentRunStatus = Literal[
    "queued",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
]


def _reject_hidden_reasoning(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if is_hidden_reasoning_key(key):
                raise ValueError("Agent input must not contain hidden reasoning")
            _reject_hidden_reasoning(child)
    elif isinstance(value, list):
        for child in value:
            _reject_hidden_reasoning(child)


class AgentRunCreateRequest(ApiModel):
    kind: Literal["conversation", "deep_learn", "assessment", "review"]
    user_intent: str = Field(alias="userIntent", min_length=1, max_length=5_000)
    mode: Literal["ask", "teach", "study", "review", "plan"]
    input: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    conversation_id: str | None = Field(
        default=None, alias="conversationId", pattern=_IDENTIFIER
    )
    study_session_id: str | None = Field(
        default=None, alias="studySessionId", pattern=_IDENTIFIER
    )

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        _reject_hidden_reasoning(value)
        return value


class AgentRunResponse(ApiModel):
    id: str
    kind: Literal["conversation", "deep_learn", "assessment", "review"]
    mode: Literal["ask", "teach", "study", "review", "plan"]
    status: AgentRunStatus
    provider: str
    model: str
    error_code: str | None = Field(alias="errorCode")
    error_detail: str | None = Field(alias="errorDetail")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    started_at: datetime | None = Field(alias="startedAt")
    finished_at: datetime | None = Field(alias="finishedAt")


class AgentCancelResponse(ApiModel):
    accepted: bool
    run: AgentRunResponse


def _manager(request: Request) -> AgentRuntimeManager:
    return request.app.state.agent_runtime


def _run_response(run: dict) -> AgentRunResponse:
    return AgentRunResponse.model_validate(
        {field_name: run[field_name] for field_name in AgentRunResponse.model_fields}
    )


router = APIRouter(prefix="/v1/agent/runs", tags=["agent"])


@router.post("", status_code=202, response_model=AgentRunResponse)
async def create_agent_run(
    request: Request, payload: AgentRunCreateRequest
) -> AgentRunResponse:
    manager = _manager(request)
    try:
        run = await manager.create_run(
            kind=payload.kind,
            user_intent=payload.user_intent,
            mode=payload.mode,
            input_data=cast(dict[str, JsonValue], payload.input),
            idempotency_key=payload.idempotency_key,
            conversation_id=payload.conversation_id,
            study_session_id=payload.study_session_id,
        )
    except AgentProviderMissingError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_missing",
                "message": str(error),
                "retryable": False,
                "recoveryAction": "Configure a real Agent provider and retry.",
            },
        ) from error
    except AgentProviderUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_unavailable",
                "message": str(error),
                "retryable": True,
                "recoveryAction": "Check the configured Agent provider and retry.",
            },
        ) from error
    except AgentBusyError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "agent_busy",
                "message": str(error),
                "retryable": True,
                "recoveryAction": "Wait for or cancel the active Agent run.",
            },
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _run_response(run)


@router.get("/{run_id}", response_model=AgentRunResponse)
def get_agent_run(request: Request, run_id: str) -> AgentRunResponse:
    try:
        run = _manager(request).get_run(run_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid Agent run ID") from error
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return _run_response(run)


@router.post("/{run_id}/cancel", response_model=AgentCancelResponse)
async def cancel_agent_run(request: Request, run_id: str) -> AgentCancelResponse:
    try:
        accepted, run = await _manager(request).cancel(run_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Agent run not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid Agent run ID") from error
    return AgentCancelResponse(accepted=accepted, run=_run_response(run))


@router.get("/{run_id}/events")
async def stream_agent_events(
    request: Request,
    run_id: str,
    cursor: str | None = Query(default=None, max_length=128),
    last_event_id: str | None = Header(
        default=None, alias="Last-Event-ID", max_length=128
    ),
) -> StreamingResponse:
    if cursor is not None and last_event_id is not None and cursor != last_event_id:
        raise HTTPException(
            status_code=400,
            detail="cursor and Last-Event-ID identify different events",
        )
    selected_cursor = last_event_id or cursor
    manager = _manager(request)
    try:
        # Validate before StreamingResponse sends a 200 response. Errors raised
        # inside the iterator would otherwise appear as a silent broken stream.
        manager.validate_event_cursor(run_id, selected_cursor)
    except LookupError as error:
        detail = (
            "Agent run not found"
            if manager.get_run(run_id) is None
            else "Agent event cursor not found"
        )
        raise HTTPException(status_code=404, detail=detail) from error
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="invalid Agent event cursor"
        ) from error

    async def events() -> AsyncIterator[str]:
        disconnected = asyncio.Event()

        async def watch_disconnect() -> None:
            while not disconnected.is_set():
                if await request.is_disconnected():
                    disconnected.set()
                    return
                await asyncio.sleep(0.05)

        watcher = asyncio.create_task(watch_disconnect())
        try:
            async for event in manager.stream_events(
                run_id,
                last_event_id=selected_cursor,
                disconnected=disconnected,
            ):
                yield encode_sse(event)
        finally:
            disconnected.set()
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = [
    "AgentCancelResponse",
    "AgentRunCreateRequest",
    "AgentRunResponse",
    "router",
]
