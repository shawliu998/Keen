"""Authenticated API for bounded Study Plan proposals and explicit decisions."""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from pydantic import Field

from ..schemas import ApiModel
from ..services.agent_runtime import AgentBusyError
from ..services.study_plan_proposal import (
    StudyPlanProposalConflictError,
    StudyPlanProposalService,
)

_IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class StudyPlanProposalCreateRequest(ApiModel):
    course_id: str = Field(alias="courseId", pattern=_IDENTIFIER)
    expected_session_revision: int = Field(alias="expectedSessionRevision", ge=0)
    expected_plan_version: int = Field(alias="expectedPlanVersion", ge=1)
    target_unit_id: str = Field(alias="targetUnitId", pattern=_IDENTIFIER)
    request: Literal["insert_source_grounded_prerequisite"]
    trigger_origin: Literal["learner_request", "adaptive_evidence"] = Field(
        default="learner_request",
        alias="triggerOrigin",
    )
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )


class StudyPlanProposalDecisionRequest(ApiModel):
    course_id: str = Field(alias="courseId", pattern=_IDENTIFIER)
    artifact_id: str = Field(alias="artifactId", pattern=_IDENTIFIER)
    expected_session_revision: int = Field(alias="expectedSessionRevision", ge=0)
    expected_plan_version: int = Field(alias="expectedPlanVersion", ge=1)
    decision: Literal["accept", "keep"]
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )


class StudyPlanProposalUndoRequest(ApiModel):
    course_id: str = Field(alias="courseId", pattern=_IDENTIFIER)
    expected_session_revision: int = Field(alias="expectedSessionRevision", ge=0)
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )


class PlanProposalRunResponse(ApiModel):
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


class PlanProposalUnitResponse(ApiModel):
    id: str = Field(pattern=_IDENTIFIER)
    ordinal: int = Field(ge=0)
    title: str
    objective: str
    estimated_minutes: int = Field(alias="estimatedMinutes", ge=1)
    status: str


class PlanProposalSourceResponse(ApiModel):
    source_handle: str = Field(alias="sourceHandle", pattern=_IDENTIFIER)
    chunk_id: str = Field(alias="chunkId")
    document_id: str = Field(alias="documentId")
    document_version_id: str = Field(alias="documentVersionId")
    chunk_content_hash: str = Field(alias="chunkContentHash", pattern=r"^[0-9a-f]{64}$")
    document_name: str = Field(alias="documentName")
    page_number: int = Field(alias="pageNumber", ge=1)
    section_path: list[str] = Field(alias="sectionPath")
    quote: str
    geometry: dict[str, object] | None
    metadata: dict[str, object]


class InsertPrerequisiteResponse(ApiModel):
    kind: Literal["insert_prerequisite"]
    before_unit_id: str = Field(alias="beforeUnitId", pattern=_IDENTIFIER)
    title: str
    objective: str
    estimated_minutes: int = Field(alias="estimatedMinutes", ge=5, le=30)
    selected_source_handles: list[str] = Field(alias="selectedSourceHandles")


class PlanProposalDecisionResponse(ApiModel):
    status: Literal["unapplied", "pending", "accepted", "rejected", "undone"]
    apply_available: bool = Field(alias="applyAvailable")


class PlanProposalCurrentPlanResponse(ApiModel):
    units: list[PlanProposalUnitResponse] = Field(min_length=2, max_length=8)


class StudyPlanProposalArtifactResponse(ApiModel):
    kind: Literal["study_plan_proposal_artifact"]
    schema_version: Literal[1] = Field(alias="schemaVersion")
    artifact_id: str = Field(alias="artifactId", pattern=_IDENTIFIER)
    profile_id: Literal["learning.plan-proposal.source-grounded.v1"] = Field(
        alias="profileId"
    )
    profile_definition_hash: str = Field(
        alias="profileDefinitionHash", pattern=r"^[0-9a-f]{64}$"
    )
    base_session_revision: int = Field(alias="baseSessionRevision", ge=0)
    base_plan_id: str = Field(alias="basePlanId", pattern=_IDENTIFIER)
    base_plan_version: int = Field(alias="basePlanVersion", ge=1)
    summary: str
    reason: str
    current_plan: PlanProposalCurrentPlanResponse = Field(alias="currentPlan")
    operation: InsertPrerequisiteResponse
    sources: list[PlanProposalSourceResponse] = Field(min_length=1, max_length=8)
    decision: PlanProposalDecisionResponse


class StudyPlanProposalReceiptResponse(ApiModel):
    proposal_id: str = Field(alias="proposalId", pattern=_IDENTIFIER)
    status: Literal["accepted", "rejected", "undone"]
    plan_version: int | None = Field(alias="planVersion", ge=1)
    effective_after_current_step: bool = Field(alias="effectiveAfterCurrentStep")
    undo_available: bool = Field(alias="undoAvailable")
    undo_until: str | None = Field(alias="undoUntil")
    message: str


class StudyPlanProposalTriggerResponse(ApiModel):
    origin: Literal["learner_request", "adaptive_evidence"]
    reason_code: Literal[
        "learner_requested_prerequisite",
        "low_confidence_incorrect_recall_after_intervention",
    ] = Field(alias="reasonCode")
    evidence_ids: list[str] = Field(alias="evidenceIds", max_length=3)
    why_now: str = Field(alias="whyNow", min_length=1, max_length=1_000)
    learner_approval_required: Literal[True] = Field(alias="learnerApprovalRequired")


class StudyPlanProposalResponse(ApiModel):
    status: Literal[
        "none",
        "queued",
        "running",
        "ready",
        "stale",
        "unavailable",
        "accepted",
        "rejected",
        "undone",
    ]
    course_id: str = Field(alias="courseId", pattern=_IDENTIFIER)
    session_id: str = Field(alias="sessionId", pattern=_IDENTIFIER)
    reason: str | None
    run: PlanProposalRunResponse | None
    artifact: StudyPlanProposalArtifactResponse | None
    receipt: StudyPlanProposalReceiptResponse | None
    trigger: StudyPlanProposalTriggerResponse | None


router = APIRouter(prefix="/v1/study-sessions", tags=["study-plan-proposals"])


def _service(request: Request) -> StudyPlanProposalService:
    return StudyPlanProposalService(
        request.app.state.database,
        request.app.state.agent_runtime,
    )


@router.get(
    "/{session_id}/plan-proposals/current",
    response_model=StudyPlanProposalResponse,
)
def get_current_plan_proposal(
    request: Request,
    session_id: str = Path(pattern=_IDENTIFIER),
    course_id: str = Query(alias="courseId", pattern=_IDENTIFIER),
) -> StudyPlanProposalResponse:
    try:
        return StudyPlanProposalResponse.model_validate(
            _service(request).get_current(
                course_id=course_id,
                session_id=session_id,
            )
        )
    except (sqlite3.Error, RuntimeError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="The saved plan proposal could not be restored.",
        ) from None


@router.post(
    "/{session_id}/plan-proposals",
    response_model=StudyPlanProposalResponse,
)
async def create_plan_proposal(
    payload: StudyPlanProposalCreateRequest,
    request: Request,
    response: Response,
    session_id: str = Path(pattern=_IDENTIFIER),
) -> StudyPlanProposalResponse:
    try:
        result = await _service(request).start(
            course_id=payload.course_id,
            session_id=session_id,
            expected_session_revision=payload.expected_session_revision,
            expected_plan_version=payload.expected_plan_version,
            target_unit_id=payload.target_unit_id,
            idempotency_key=payload.idempotency_key,
            trigger_origin=payload.trigger_origin,
        )
        body = StudyPlanProposalResponse.model_validate(result)
    except (StudyPlanProposalConflictError, AgentBusyError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except (sqlite3.Error, RuntimeError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="The plan proposal could not be created; the current plan was unchanged.",
        ) from None
    if body.status in {"queued", "running"}:
        response.status_code = 202
    return body


@router.post(
    "/{session_id}/plan-proposals/{artifact_id}/decision",
    response_model=StudyPlanProposalResponse,
)
def decide_plan_proposal(
    payload: StudyPlanProposalDecisionRequest,
    request: Request,
    session_id: str = Path(pattern=_IDENTIFIER),
    artifact_id: str = Path(pattern=_IDENTIFIER),
) -> StudyPlanProposalResponse:
    if payload.artifact_id != artifact_id:
        raise HTTPException(
            status_code=409,
            detail="Plan proposal artifact identity does not match the route.",
        )
    try:
        return StudyPlanProposalResponse.model_validate(
            _service(request).decide(
                course_id=payload.course_id,
                session_id=session_id,
                artifact_id=artifact_id,
                expected_session_revision=payload.expected_session_revision,
                expected_plan_version=payload.expected_plan_version,
                decision=payload.decision,
                idempotency_key=payload.idempotency_key,
            )
        )
    except StudyPlanProposalConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except (sqlite3.Error, RuntimeError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="The plan decision could not be confirmed; the current learning step was unchanged.",
        ) from None


@router.post(
    "/{session_id}/plan-proposals/{proposal_id}/undo",
    response_model=StudyPlanProposalResponse,
)
def undo_plan_proposal(
    payload: StudyPlanProposalUndoRequest,
    request: Request,
    session_id: str = Path(pattern=_IDENTIFIER),
    proposal_id: str = Path(pattern=_IDENTIFIER),
) -> StudyPlanProposalResponse:
    try:
        return StudyPlanProposalResponse.model_validate(
            _service(request).undo(
                course_id=payload.course_id,
                session_id=session_id,
                proposal_id=proposal_id,
                expected_session_revision=payload.expected_session_revision,
                idempotency_key=payload.idempotency_key,
            )
        )
    except StudyPlanProposalConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except (sqlite3.Error, RuntimeError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="Undo could not be confirmed; the current learning plan was retained.",
        ) from None


__all__ = ["router"]
