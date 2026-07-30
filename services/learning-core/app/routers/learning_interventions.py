"""Authenticated product API for the closed misconception-repair loop."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field, model_validator

from ..learning_agent.playbooks import LearningInterventionIntent
from ..schemas import ApiModel
from ..services.agent_runtime import AgentBusyError
from ..services.learning_intervention import (
    LearningInterventionConflictError,
    LearningInterventionNotFoundError,
    LearningInterventionService,
)

_IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
InterventionActionLabel = Literal[
    "Explain differently",
    "Show a source example",
    "Test me instead",
]


class LearningInterventionCreateRequest(ApiModel):
    course_id: str = Field(
        alias="courseId", min_length=1, max_length=128, pattern=_IDENTIFIER
    )
    unit_id: str = Field(
        alias="unitId", min_length=1, max_length=128, pattern=_IDENTIFIER
    )
    expected_session_revision: int = Field(alias="expectedSessionRevision", ge=0)
    intent: LearningInterventionIntent
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    predecessor_run_id: str | None = Field(
        default=None, alias="predecessorRunId", pattern=_IDENTIFIER
    )
    predecessor_artifact_id: str | None = Field(
        default=None, alias="predecessorArtifactId", pattern=_IDENTIFIER
    )

    @model_validator(mode="after")
    def validate_predecessor_identity(self) -> LearningInterventionCreateRequest:
        if (self.predecessor_run_id is None) != (self.predecessor_artifact_id is None):
            raise ValueError("intervention predecessor identity must be complete")
        return self


class LearningInterventionCancelRequest(ApiModel):
    course_id: str = Field(
        alias="courseId", min_length=1, max_length=128, pattern=_IDENTIFIER
    )


class InterventionRunResponse(ApiModel):
    id: str = Field(pattern=_IDENTIFIER)
    status: Literal[
        "queued",
        "running",
        "waiting_approval",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ]
    provider: str
    model: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    error_code: str | None = Field(alias="errorCode")


class InterventionSourcePreviewResponse(ApiModel):
    source_handle: str = Field(alias="sourceHandle")
    document_id: str = Field(alias="documentId")
    document_name: str = Field(alias="documentName")
    page_number: int = Field(alias="pageNumber", ge=1)
    section_path: list[str] = Field(alias="sectionPath")
    metadata: dict[str, object]


class InterventionSourceResponse(InterventionSourcePreviewResponse):
    chunk_id: str = Field(alias="chunkId")
    document_version_id: str = Field(alias="documentVersionId")
    chunk_content_hash: str = Field(alias="chunkContentHash", pattern=r"^[0-9a-f]{64}$")
    quote: str = Field(min_length=1, max_length=12_000)
    geometry: dict[str, object] | None


class InterventionNextResponse(ApiModel):
    label: str
    action: Literal["continue_practice"]
    practice_run_id: str | None = Field(default=None, alias="practiceRunId")
    practice_prompt: str | None = Field(default=None, alias="practicePrompt")
    session_revision: int | None = Field(default=None, alias="sessionRevision", ge=0)


class InterventionEligibleArtifactResponse(ApiModel):
    why_now: str = Field(alias="whyNow")
    sources: list[InterventionSourcePreviewResponse]
    what_next: InterventionNextResponse = Field(alias="whatNext")


class InterventionArtifactPredecessorResponse(ApiModel):
    run_id: str = Field(alias="runId", pattern=_IDENTIFIER)
    artifact_id: str = Field(alias="artifactId", pattern=_IDENTIFIER)


class InterventionReadyArtifactResponse(ApiModel):
    kind: Literal["learning_intervention_artifact"]
    schema_version: Literal[1] = Field(alias="schemaVersion")
    artifact_id: str = Field(alias="artifactId", pattern=_IDENTIFIER)
    predecessor: InterventionArtifactPredecessorResponse | None = None
    profile_id: str = Field(alias="profileId")
    profile_definition_hash: str = Field(alias="profileDefinitionHash")
    playbook_slug: str = Field(alias="playbookSlug")
    playbook_version: int = Field(alias="playbookVersion", ge=1)
    playbook_definition_hash: str = Field(alias="playbookDefinitionHash")
    why_now: str = Field(alias="whyNow")
    summary: str
    explanation_markdown: str = Field(alias="explanationMarkdown")
    sources: list[InterventionSourceResponse] = Field(min_length=1, max_length=8)
    what_next: InterventionNextResponse = Field(alias="whatNext")


class InterventionFallbackResponse(ApiModel):
    action: Literal["source_review"]
    label: str
    retryable: bool | None = None


class LearningInterventionResponse(ApiModel):
    status: Literal[
        "ineligible",
        "eligible",
        "queued",
        "running",
        "ready",
        "cancelled",
        "source_review",
        "practice_ready",
    ]
    course_id: str = Field(alias="courseId")
    session_id: str = Field(alias="sessionId")
    reason: str | None
    actions: list[InterventionActionLabel]
    run: InterventionRunResponse | None
    artifact: (
        InterventionEligibleArtifactResponse | InterventionReadyArtifactResponse | None
    )
    practice: InterventionNextResponse | None
    fallback: InterventionFallbackResponse | None


router = APIRouter(prefix="/v1/study-sessions", tags=["learning-interventions"])


def _service(request: Request) -> LearningInterventionService:
    return LearningInterventionService(
        request.app.state.database,
        request.app.state.agent_runtime,
    )


@router.get(
    "/{session_id}/interventions/current",
    response_model=LearningInterventionResponse,
)
def get_current_intervention(
    request: Request,
    session_id: str = Path(min_length=1, max_length=128, pattern=_IDENTIFIER),
    course_id: str = Query(
        alias="courseId", min_length=1, max_length=128, pattern=_IDENTIFIER
    ),
) -> LearningInterventionResponse:
    try:
        return LearningInterventionResponse.model_validate(
            _service(request).get_current(
                course_id=course_id,
                session_id=session_id,
            )
        )
    except (sqlite3.Error, RuntimeError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="Intervention state could not be restored; the existing source review remains available.",
        ) from None


@router.post(
    "/{session_id}/interventions",
    response_model=LearningInterventionResponse,
)
async def create_intervention(
    payload: LearningInterventionCreateRequest,
    request: Request,
    response: Response,
    session_id: str = Path(min_length=1, max_length=128, pattern=_IDENTIFIER),
) -> LearningInterventionResponse:
    try:
        result = await _service(request).start(
            course_id=payload.course_id,
            session_id=session_id,
            unit_id=payload.unit_id,
            expected_session_revision=payload.expected_session_revision,
            intent=payload.intent,
            idempotency_key=payload.idempotency_key,
            predecessor_run_id=payload.predecessor_run_id,
            predecessor_artifact_id=payload.predecessor_artifact_id,
        )
        body = LearningInterventionResponse.model_validate(result)
    except LearningInterventionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except AgentBusyError:
        raise HTTPException(
            status_code=409,
            detail="Another Agent run is active; retry this intervention after it finishes.",
        ) from None
    except (sqlite3.Error, RuntimeError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="The intervention could not start; return to the current source and retry.",
        ) from None
    if body.status in {"queued", "running"}:
        response.status_code = 202
    elif body.status == "practice_ready":
        response.status_code = 201
    return body


@router.post(
    "/{session_id}/interventions/{run_id}/cancel",
    response_model=LearningInterventionResponse,
)
async def cancel_intervention(
    payload: LearningInterventionCancelRequest,
    request: Request,
    session_id: str = Path(min_length=1, max_length=128, pattern=_IDENTIFIER),
    run_id: str = Path(min_length=1, max_length=128, pattern=_IDENTIFIER),
) -> LearningInterventionResponse:
    try:
        result = await _service(request).cancel(
            course_id=payload.course_id,
            session_id=session_id,
            run_id=run_id,
        )
        return LearningInterventionResponse.model_validate(result)
    except LearningInterventionNotFoundError:
        raise HTTPException(
            status_code=404, detail="Intervention run not found"
        ) from None
    except (sqlite3.Error, RuntimeError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="Cancellation could not be confirmed; the run was left unchanged.",
        ) from None


@router.get("/{session_id}/interventions/{run_id}/events")
async def stream_intervention_events(
    request: Request,
    session_id: str = Path(min_length=1, max_length=128, pattern=_IDENTIFIER),
    run_id: str = Path(min_length=1, max_length=128, pattern=_IDENTIFIER),
    course_id: str = Query(
        alias="courseId", min_length=1, max_length=128, pattern=_IDENTIFIER
    ),
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
    service = _service(request)
    try:
        service.require_owned_run(
            course_id=course_id,
            session_id=session_id,
            run_id=run_id,
        )
        request.app.state.agent_runtime.validate_event_cursor(run_id, selected_cursor)
    except LearningInterventionNotFoundError:
        raise HTTPException(
            status_code=404, detail="Intervention run not found"
        ) from None
    except LookupError:
        raise HTTPException(
            status_code=404, detail="Intervention event cursor not found"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Invalid intervention event cursor"
        ) from None

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
            async for event in request.app.state.agent_runtime.stream_events(
                run_id,
                last_event_id=selected_cursor,
                disconnected=disconnected,
            ):
                public = service.public_event(
                    event=event,
                    course_id=course_id,
                    session_id=session_id,
                    run_id=run_id,
                )
                if public is not None:
                    yield _encode_sse(public)
        finally:
            disconnected.set()
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _encode_sse(event: dict[str, object]) -> str:
    return (
        f"id: {event['id']}\n"
        f"event: {event['event']}\n"
        f"data: {json.dumps(event['data'], ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


__all__ = [
    "LearningInterventionCreateRequest",
    "LearningInterventionResponse",
    "router",
]
