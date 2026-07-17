"""Authenticated API for starting real, source-grounded autonomous study work."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

from ..schemas import (
    ActiveRecallAnswerRequest,
    ActiveRecallCheckpointResponse,
    ActiveRecallGradeResponse,
    ActiveRecallPlanResponse,
    ActiveRecallPlanUnitResponse,
    ActiveRecallProgressionRequest,
    ActiveRecallProgressionResponse,
    ActiveRecallReadResponse,
    ActiveRecallRunResponse,
    ActiveRecallSessionResponse,
    AutonomousStudyPlanResponse,
    AutonomousStudySessionRequest,
    AutonomousStudySessionResponse,
    AutonomousStudySessionStartResponse,
    AutonomousStudySessionUnitResponse,
    AutonomousStudyTaskResponse,
    DiagnosticAnswerRequest,
    DiagnosticCheckpointResponse,
    DiagnosticReadResponse,
    DiagnosticProgressionRequest,
    DiagnosticProgressionResponse,
    StudySessionReadResponse,
)
from ..services.diagnostic_progression import (
    DiagnosticConflictError,
    DiagnosticNotFoundError,
    DiagnosticReadResult,
    DiagnosticProgressionResult,
    DiagnosticProgressionService,
)
from ..services.active_recall_progression import (
    ActiveRecallConflictError,
    ActiveRecallNotFoundError,
    ActiveRecallProgressionResult,
    ActiveRecallProgressionService,
    ActiveRecallReadResult,
)
from ..services.autonomous_study_session import (
    AutonomousStudySessionResult,
    AutonomousStudySessionService,
)
from ..services.study_session_read import (
    StudySessionReadResult,
    StudySessionReadService,
)


router = APIRouter(prefix="/v1", tags=["autonomous-study-sessions"])
_ANSWERED_DIAGNOSTIC_SESSION_STATES = frozenset(
    {
        "studying",
        "checkpoint",
        "active_recall",
        "practicing",
        "summarizing",
        "review_scheduling",
    }
)


def _write_service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "autonomous_study_session_temporarily_unavailable",
            "message": "Keen could not safely start or recover the local study session.",
            "retryable": True,
            "recoveryAction": "Refresh the learning feed and retry. The session may already be saved.",
            "automaticRecovery": False,
            "outcomeMayBeDurable": True,
        },
    )


def _read_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "study_session_not_found",
            "message": "No study session is available in the selected course.",
            "retryable": False,
            "recoveryAction": "Return to the learning feed and choose an available recommendation.",
            "automaticRecovery": False,
        },
    )


def _read_service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "study_session_temporarily_unavailable",
            "message": "Keen could not safely restore the local study session.",
            "retryable": True,
            "recoveryAction": "Retry. If the problem continues, return to the learning feed.",
            "automaticRecovery": False,
        },
    )


def _diagnostic_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "study_diagnostic_not_found",
            "message": "No diagnostic checkpoint is available in the selected course.",
            "retryable": False,
            "recoveryAction": "Refresh the study session and continue its current step.",
            "automaticRecovery": False,
        },
    )


def _diagnostic_conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "study_diagnostic_conflict",
            "message": "The study session changed before this diagnostic action could be applied.",
            "retryable": True,
            "recoveryAction": "Refresh the study session, then retry using its current revision.",
            "automaticRecovery": False,
        },
    )


def _diagnostic_service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "study_diagnostic_temporarily_unavailable",
            "message": "Keen could not safely determine whether the diagnostic action was saved.",
            "retryable": True,
            "recoveryAction": "Refresh the study session, then retry with the same idempotency key.",
            "automaticRecovery": False,
            "outcomeMayBeDurable": True,
        },
    )


def _diagnostic_read_service_error() -> HTTPException:
    """Reads are safe to retry and must not imply a durable mutation."""

    return HTTPException(
        status_code=503,
        detail={
            "code": "study_diagnostic_temporarily_unavailable",
            "message": "Keen could not safely restore the local diagnostic state.",
            "retryable": True,
            "recoveryAction": "Retry. If the problem continues, return to the learning feed.",
            "automaticRecovery": False,
        },
    )


def _active_recall_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "study_active_recall_not_found",
            "message": "No active-recall state is available in the selected course.",
            "retryable": False,
            "recoveryAction": "Refresh the study session and continue its current step.",
            "automaticRecovery": False,
        },
    )


def _active_recall_conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "study_active_recall_conflict",
            "message": "The study session changed before active recall could be applied.",
            "retryable": True,
            "recoveryAction": "Refresh the study session, then retry using its current revision.",
            "automaticRecovery": False,
        },
    )


def _active_recall_write_service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "study_active_recall_temporarily_unavailable",
            "message": "Keen could not safely determine whether active recall was saved.",
            "retryable": True,
            "recoveryAction": "Refresh the study session, then retry with the same idempotency key.",
            "automaticRecovery": False,
            "outcomeMayBeDurable": True,
        },
    )


def _active_recall_read_service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "study_active_recall_temporarily_unavailable",
            "message": "Keen could not safely restore the local active-recall state.",
            "retryable": True,
            "recoveryAction": "Retry. If the problem continues, return to the learning feed.",
            "automaticRecovery": False,
        },
    )


def _stored_utc_datetime(value: object, *, optional: bool = False) -> datetime | None:
    """Make Keen's legacy UTC SQLite convention explicit at the API boundary."""

    if value is None:
        if optional:
            return None
        raise ValueError("stored timestamp is missing")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("stored timestamp is invalid") from None
    else:
        raise ValueError("stored timestamp is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _task(task: dict[str, Any] | None) -> AutonomousStudyTaskResponse | None:
    if task is None:
        return None
    return AutonomousStudyTaskResponse.model_validate(
        {
            "id": task["id"],
            "course_id": task["course_id"],
            "concept_id": task["concept_id"],
            "title": task["title"],
            "reason": task["reason"],
            "estimated_minutes": task["estimated_minutes"],
            "status": task["status"],
            "source_type": task["source_type"],
            "source_id": task["source_id"],
        }
    )


def _session(session: dict[str, Any] | None) -> AutonomousStudySessionResponse | None:
    if session is None:
        return None
    return AutonomousStudySessionResponse.model_validate(
        {
            "id": session["id"],
            "course_id": session["course_id"],
            "originating_task_id": session["originating_task_id"],
            "title": session["title"],
            "mode": session["mode"],
            "goal": session["goal"],
            "estimated_minutes": session["estimated_minutes"],
            "status": session["status"],
            "progress": session["progress"],
            "revision": session["revision"],
            "created_at": _stored_utc_datetime(session["created_at"]),
            "updated_at": _stored_utc_datetime(session["updated_at"]),
            "started_at": _stored_utc_datetime(session["started_at"], optional=True),
        }
    )


def _plan(plan: dict[str, Any] | None) -> AutonomousStudyPlanResponse | None:
    if plan is None:
        return None
    units = [
        AutonomousStudySessionUnitResponse.model_validate(
            {
                "id": unit["id"],
                "ordinal": unit["ordinal"],
                "concept_id": unit["concept_id"],
                "concept_ids": unit["concept_ids"],
                "source_chunk_ids": unit["source_chunk_ids"],
                "title": unit["title"],
                "objective": unit["objective"],
                "content": unit["content"],
                "estimated_minutes": unit["estimated_minutes"],
                "status": unit["status"],
            }
        )
        for unit in plan["units"]
    ]
    return AutonomousStudyPlanResponse.model_validate(
        {
            "id": plan["id"],
            "session_id": plan["session_id"],
            "version": plan["version"],
            "rationale": plan["rationale"],
            "units": units,
        }
    )


def _blocked_recovery(reason: str) -> str:
    return {
        "task_not_found": "Refresh the learning feed and choose an available recommendation.",
        "task_outside_course": "Return to the selected course and choose one of its recommendations.",
        "task_not_actionable": "Refresh the learning feed and choose an upcoming or overdue recommendation.",
        "task_not_autonomous": "Use the task's supported workflow or choose an autonomous recommendation.",
        "task_missing_concept": "Refresh the course after local recovery completes, then retry.",
        "source_session_unavailable": "Refresh the learning feed and choose a resumable study session.",
        "originating_session_terminal": "Choose another recommendation; this study session is already terminal.",
        "no_indexed_source": "Wait for a linked document to finish indexing, then retry.",
    }[reason]


def _response(
    result: AutonomousStudySessionResult,
    *,
    expected_course_id: str,
    expected_task_id: str,
) -> AutonomousStudySessionStartResponse:
    _validate_result(
        result,
        expected_course_id=expected_course_id,
        expected_task_id=expected_task_id,
    )
    blocked_reason = result.blocked_reason
    return AutonomousStudySessionStartResponse(
        outcome=result.outcome,
        course_id=result.course_id,
        task=_task(result.task),
        session=_session(result.session),
        plan=_plan(result.plan),
        blocked_reason=blocked_reason,
        recovery_action=_blocked_recovery(blocked_reason)
        if blocked_reason is not None
        else None,
    )


def _validate_result(
    result: AutonomousStudySessionResult,
    *,
    expected_course_id: str,
    expected_task_id: str,
) -> None:
    """Fail closed before serializing any inconsistent persisted state."""

    if result.course_id != expected_course_id:
        raise ValueError("study session result course does not match request")
    task = result.task
    session = result.session
    plan = result.plan
    if task is not None and (
        task.get("course_id") != expected_course_id
        or task.get("id") != expected_task_id
    ):
        raise ValueError("study session result task is outside request scope")
    if session is not None and session.get("course_id") != expected_course_id:
        raise ValueError("study session result session is outside request scope")

    if result.outcome == "blocked":
        if result.blocked_reason is None or session is not None or plan is not None:
            raise ValueError("blocked study session result is inconsistent")
        # This also guarantees every exposed blocked reason has a recovery path.
        _blocked_recovery(result.blocked_reason)
        return

    if result.blocked_reason is not None:
        raise ValueError("non-blocked study session result has a blocked reason")
    if task is None or session is None:
        raise ValueError("successful study session result is incomplete")

    if result.outcome == "session_created":
        if (
            plan is None
            or session.get("originating_task_id") != task.get("id")
            or plan.get("session_id") != session.get("id")
        ):
            raise ValueError("created study session result is inconsistent")
        return

    if result.outcome == "resumed":
        if plan is not None:
            raise ValueError("resumed study session result unexpectedly has a plan")
        if task.get("source_type") == "study_session":
            if task.get("source_id") != session.get("id"):
                raise ValueError("resumed source session does not match task")
        elif session.get("originating_task_id") != task.get("id"):
            raise ValueError("resumed originating session does not match task")
        return

    raise ValueError("unknown study session result outcome")


def _read_response(result: StudySessionReadResult) -> StudySessionReadResponse:
    session = _session(result.session)
    if session is None or session.course_id != result.course_id:
        raise ValueError("study session read result is outside course scope")
    plan = _plan(result.plan)
    if result.outcome == "ready":
        if plan is None or plan.session_id != session.id:
            raise ValueError("study session read plan is inconsistent")
        unit_ids = {unit.id for unit in plan.units}
        if (
            result.current_unit_id is not None
            and result.current_unit_id not in unit_ids
        ):
            raise ValueError("study session current unit is outside the plan")
        recovery_action = None
    elif result.outcome == "plan_unavailable":
        if plan is not None or result.current_unit_id is not None:
            raise ValueError("plan-unavailable study session result is inconsistent")
        recovery_action = (
            "Return to the learning feed and start a source-grounded recommendation."
        )
    else:
        raise ValueError("unknown study session read outcome")
    return StudySessionReadResponse(
        outcome=result.outcome,
        course_id=result.course_id,
        session=session,
        plan=plan,
        current_unit_id=result.current_unit_id,
        recovery_action=recovery_action,
    )


def _diagnostic_response(
    result: DiagnosticProgressionResult,
    *,
    expected_course_id: str,
    expected_session_id: str,
    expected_checkpoint_id: str | None = None,
) -> DiagnosticProgressionResponse:
    if result.course_id != expected_course_id:
        raise ValueError("diagnostic result is outside requested course")
    session = _session(result.session)
    plan = _plan(result.plan)
    checkpoint = result.checkpoint
    if session is None or plan is None:
        raise ValueError("diagnostic result is incomplete")
    if (
        session.course_id != expected_course_id
        or session.id != expected_session_id
        or plan.session_id != session.id
        or checkpoint.get("session_id") != session.id
        or checkpoint.get("kind") != "diagnostic"
        or checkpoint.get("unit_id") is None
    ):
        raise ValueError("diagnostic result relationships are invalid")
    if (
        expected_checkpoint_id is not None
        and checkpoint.get("id") != expected_checkpoint_id
    ):
        raise ValueError("diagnostic result checkpoint does not match path")
    first_unit = _diagnostic_first_unit(plan, checkpoint)
    current_unit = _diagnostic_unit(result.current_unit)
    _diagnostic_current_unit(plan, current_unit)
    current_unit_id = result.session.get("current_unit_id")
    if current_unit_id != (current_unit.id if current_unit is not None else None):
        raise ValueError("diagnostic result current unit pointer is inconsistent")

    effective_status = _diagnostic_effective_status(result.session)

    # A newly applied action has an exact state.  Replays must remain readable
    # after legitimate later work (for example a paused or completed session),
    # but can never point at a malformed first diagnostic.
    if result.outcome == "applied":
        if checkpoint["status"] == "pending":
            if session.status != "diagnosing" or current_unit is not None:
                raise ValueError("applied diagnostic begin state is inconsistent")
        elif checkpoint["status"] == "answered":
            if (
                session.status != "studying"
                or current_unit is None
                or current_unit.id != first_unit.id
                or current_unit.status != "active"
            ):
                raise ValueError("applied diagnostic answer state is inconsistent")
        else:
            raise ValueError("diagnostic checkpoint has an invalid status")
    elif result.outcome == "replayed":
        if checkpoint["status"] == "pending":
            if effective_status != "diagnosing" or current_unit is not None:
                raise ValueError("replayed pending diagnostic state is inconsistent")
        elif checkpoint["status"] == "answered":
            if effective_status not in _ANSWERED_DIAGNOSTIC_SESSION_STATES:
                raise ValueError("replayed answered diagnostic state is inconsistent")
            if current_unit is not None and current_unit.status != "active":
                raise ValueError("replayed diagnostic current unit is not active")
        else:
            raise ValueError("diagnostic checkpoint has an invalid status")
    else:
        raise ValueError("unknown diagnostic progression outcome")
    return DiagnosticProgressionResponse(
        outcome=result.outcome,
        course_id=result.course_id,
        session=session,
        plan=plan,
        checkpoint=DiagnosticCheckpointResponse.model_validate(
            {
                "id": checkpoint["id"],
                "session_id": checkpoint["session_id"],
                "unit_id": checkpoint["unit_id"],
                "kind": checkpoint["kind"],
                "prompt": checkpoint["prompt"],
                "status": checkpoint["status"],
            }
        ),
        current_unit=current_unit,
        current_unit_id=current_unit_id,
    )


def _diagnostic_read_response(
    result: DiagnosticReadResult, *, expected_course_id: str, expected_session_id: str
) -> DiagnosticReadResponse:
    session = _session(result.session)
    plan = _plan(result.plan)
    if (
        result.course_id != expected_course_id
        or session is None
        or plan is None
        or session.id != expected_session_id
        or session.course_id != expected_course_id
        or plan.session_id != session.id
    ):
        raise ValueError("diagnostic read result is inconsistent")
    checkpoint = result.checkpoint
    effective_status = _diagnostic_effective_status(result.session)
    if result.outcome == "not_started":
        if (
            effective_status != "goal_confirmation"
            or checkpoint is not None
            or result.current_unit is not None
            or result.session.get("current_unit_id") is not None
        ):
            raise ValueError("not-started diagnostic result is inconsistent")
        serialized_checkpoint = None
        serialized_current = None
    else:
        if checkpoint is None or checkpoint.get("session_id") != session.id:
            raise ValueError("diagnostic checkpoint is inconsistent")
        first_unit = _diagnostic_first_unit(plan, checkpoint)
        serialized_checkpoint = DiagnosticCheckpointResponse.model_validate(
            {
                "id": checkpoint["id"],
                "session_id": checkpoint["session_id"],
                "unit_id": checkpoint["unit_id"],
                "kind": checkpoint["kind"],
                "prompt": checkpoint["prompt"],
                "status": checkpoint["status"],
            }
        )
        serialized_current = _diagnostic_unit(result.current_unit)
        _diagnostic_current_unit(plan, serialized_current)
        if result.session.get("current_unit_id") != (
            serialized_current.id if serialized_current is not None else None
        ):
            raise ValueError("diagnostic read current unit pointer is inconsistent")
        if result.outcome == "pending" and (
            effective_status != "diagnosing"
            or checkpoint.get("status") != "pending"
            or serialized_current is not None
        ):
            raise ValueError("pending diagnostic state is inconsistent")
        if result.outcome == "answered" and (
            effective_status not in _ANSWERED_DIAGNOSTIC_SESSION_STATES
            or checkpoint.get("status") != "answered"
            or serialized_current is None
            or serialized_current.id != first_unit.id
            or serialized_current.status != "active"
        ):
            raise ValueError("answered diagnostic has no active current unit")
    return DiagnosticReadResponse(
        outcome=result.outcome,
        course_id=result.course_id,
        session=session,
        plan=plan,
        checkpoint=serialized_checkpoint,
        current_unit=serialized_current,
        current_unit_id=result.session.get("current_unit_id"),
    )


def _diagnostic_first_unit(
    plan: AutonomousStudyPlanResponse, checkpoint: dict[str, Any]
) -> AutonomousStudySessionUnitResponse:
    if checkpoint.get("kind") != "diagnostic" or checkpoint.get("unit_id") is None:
        raise ValueError("diagnostic checkpoint is invalid")
    if not plan.units or plan.units[0].ordinal != 0:
        raise ValueError("diagnostic plan has no ordinal-zero unit")
    unit = next((unit for unit in plan.units if unit.id == checkpoint["unit_id"]), None)
    if unit is None or unit.id != plan.units[0].id or unit.ordinal != 0:
        raise ValueError("diagnostic checkpoint is not bound to plan ordinal zero")
    return unit


def _diagnostic_effective_status(session: dict[str, Any]) -> str:
    """Resolve paused diagnostic state without exposing internal resume metadata."""

    status = session.get("status")
    resume_from = session.get("resume_from_status")
    if status == "paused":
        if not isinstance(resume_from, str):
            raise ValueError("paused diagnostic session has no resume state")
        return resume_from
    if resume_from is not None or not isinstance(status, str):
        raise ValueError("diagnostic session state is invalid")
    return status


def _diagnostic_unit(
    unit: dict[str, Any] | None,
) -> AutonomousStudySessionUnitResponse | None:
    if unit is None:
        return None
    return AutonomousStudySessionUnitResponse.model_validate(
        {
            "id": unit["id"],
            "ordinal": unit["ordinal"],
            "concept_id": unit["concept_id"],
            "concept_ids": unit["concept_ids"],
            "source_chunk_ids": unit["source_chunk_ids"],
            "title": unit["title"],
            "objective": unit["objective"],
            "content": unit["content"],
            "estimated_minutes": unit["estimated_minutes"],
            "status": unit["status"],
        }
    )


def _diagnostic_current_unit(
    plan: AutonomousStudyPlanResponse,
    current_unit: AutonomousStudySessionUnitResponse | None,
) -> None:
    """Fail closed unless the separately returned current unit is in this plan.

    Comparing the complete bounded model also prevents a corrupt result from
    pairing a valid plan-unit identifier with content or source relationships
    taken from another unit.
    """

    if current_unit is None:
        return
    plan_unit = next((unit for unit in plan.units if unit.id == current_unit.id), None)
    if plan_unit is None or plan_unit != current_unit:
        raise ValueError("diagnostic current unit is outside the current plan")


def _active_recall_session(value: dict[str, Any]) -> ActiveRecallSessionResponse:
    return ActiveRecallSessionResponse.model_validate(
        {
            "id": value["id"],
            "course_id": value["course_id"],
            "status": value["status"],
            "revision": value["revision"],
            "progress": value["progress"],
            "estimated_minutes": value["estimated_minutes"],
            "current_unit_id": value.get("current_unit_id"),
            "created_at": _stored_utc_datetime(value["created_at"]),
            "updated_at": _stored_utc_datetime(value["updated_at"]),
            "started_at": _stored_utc_datetime(value.get("started_at"), optional=True),
            "finished_at": _stored_utc_datetime(
                value.get("finished_at"), optional=True
            ),
        }
    )


def _active_recall_unit(
    value: dict[str, Any] | None,
) -> ActiveRecallPlanUnitResponse | None:
    if value is None:
        return None
    return ActiveRecallPlanUnitResponse.model_validate(
        {
            "id": value["id"],
            "ordinal": value["ordinal"],
            "estimated_minutes": value["estimated_minutes"],
            "status": value["status"],
            "created_at": _stored_utc_datetime(value["created_at"]),
            "updated_at": _stored_utc_datetime(value["updated_at"]),
        }
    )


def _active_recall_plan(value: dict[str, Any]) -> ActiveRecallPlanResponse:
    units = [_active_recall_unit(unit) for unit in value["units"]]
    if any(unit is None for unit in units):  # pragma: no cover - local invariant
        raise ValueError("active recall plan has an invalid unit")
    return ActiveRecallPlanResponse.model_validate(
        {
            "id": value["id"],
            "session_id": value["session_id"],
            "version": value["version"],
            "units": units,
        }
    )


def _active_recall_checkpoint(
    value: dict[str, Any] | None,
) -> ActiveRecallCheckpointResponse | None:
    if value is None:
        return None
    checkpoint = ActiveRecallCheckpointResponse.model_validate(
        {
            "id": value["id"],
            "kind": value["kind"],
            "prompt": value["prompt"],
            "status": value["status"],
            "created_at": _stored_utc_datetime(value["created_at"]),
            "answered_at": _stored_utc_datetime(
                value.get("answered_at"), optional=True
            ),
        }
    )
    response = value.get("response")
    if response not in {None, "Objective response recorded."}:
        raise ValueError("active recall checkpoint has an unsafe response")
    if checkpoint.status == "answered" and checkpoint.answered_at is None:
        raise ValueError("answered active recall checkpoint has no timestamp")
    if (
        checkpoint.status in {"pending", "skipped"}
        and checkpoint.answered_at is not None
    ):
        raise ValueError("unanswered active recall checkpoint has an answer timestamp")
    return checkpoint


def _active_recall_run(value: dict[str, Any] | None) -> ActiveRecallRunResponse | None:
    if value is None:
        return None
    run = ActiveRecallRunResponse.model_validate(
        {
            "id": value["id"],
            "status": value["status"],
            "checkpoint_id": value["checkpoint_id"],
            "generator_version": value["generator_version"],
            "created_at": _stored_utc_datetime(value["created_at"]),
            "answered_at": _stored_utc_datetime(
                value.get("answered_at"), optional=True
            ),
            "cancelled_at": _stored_utc_datetime(
                value.get("cancelled_at"), optional=True
            ),
            "cancellation_reason": value.get("cancellation_reason"),
        }
    )
    if run.status == "pending" and any(
        value is not None
        for value in (run.answered_at, run.cancelled_at, run.cancellation_reason)
    ):
        raise ValueError("pending active recall run has terminal metadata")
    if run.status == "answered" and (
        run.answered_at is None
        or run.cancelled_at is not None
        or run.cancellation_reason is not None
    ):
        raise ValueError("answered active recall run has invalid terminal metadata")
    if run.status == "cancelled" and (
        run.answered_at is not None
        or run.cancelled_at is None
        or run.cancellation_reason is None
    ):
        raise ValueError("cancelled active recall run has invalid terminal metadata")
    return run


def _active_recall_grade(
    value: dict[str, Any] | None,
) -> ActiveRecallGradeResponse | None:
    if value is None:
        return None
    return ActiveRecallGradeResponse.model_validate(
        {
            "correct": value["correct"],
            "score": value["score"],
            "max_score": value["max_score"],
            "grader_version": value["grader_version"],
        }
    )


def _active_recall_read_response(
    result: ActiveRecallReadResult, *, expected_course_id: str, expected_session_id: str
) -> ActiveRecallReadResponse:
    if result.course_id != expected_course_id:
        raise ValueError("active recall result is outside requested course")
    session = _active_recall_session(result.session)
    plan = _active_recall_plan(result.plan)
    checkpoint = _active_recall_checkpoint(result.checkpoint)
    run = _active_recall_run(result.run)
    current_unit = _active_recall_unit(result.current_unit)
    grade = _active_recall_grade(result.grade)
    if (
        session.id != expected_session_id
        or session.course_id != expected_course_id
        or plan.session_id != session.id
        or (
            (current_unit.id if current_unit is not None else None)
            != session.current_unit_id
        )
        or (
            current_unit is not None
            and all(unit.id != current_unit.id for unit in plan.units)
        )
        or (current_unit is None) != (session.current_unit_id is None)
    ):
        raise ValueError("active recall read relationships are invalid")
    if result.outcome == "not_started":
        if checkpoint is not None or run is not None or grade is not None:
            raise ValueError("not-started active recall result is inconsistent")
    else:
        if checkpoint is None or run is None or run.checkpoint_id != checkpoint.id:
            raise ValueError("active recall run and checkpoint are inconsistent")
        if result.outcome == "pending" and (
            run.status != "pending"
            or checkpoint.status != "pending"
            or grade is not None
        ):
            raise ValueError("pending active recall result is inconsistent")
        if result.outcome == "answered" and (
            run.status != "answered" or checkpoint.status != "answered" or grade is None
        ):
            raise ValueError("answered active recall result is inconsistent")
        if result.outcome == "cancelled" and (
            run.status != "cancelled"
            or checkpoint.status != "skipped"
            or grade is not None
        ):
            raise ValueError("cancelled active recall result is inconsistent")
    return ActiveRecallReadResponse(
        outcome=result.outcome,
        course_id=result.course_id,
        session=session,
        plan=plan,
        checkpoint=checkpoint,
        current_unit=current_unit,
        run=run,
        grade=grade,
    )


def _active_recall_progression_response(
    result: ActiveRecallProgressionResult,
    *,
    expected_course_id: str,
    expected_session_id: str,
    expected_run_id: str | None = None,
) -> ActiveRecallProgressionResponse:
    run_status = result.run.get("status")
    read_outcome = {
        "pending": "pending",
        "answered": "answered",
        "cancelled": "cancelled",
    }.get(run_status)
    if read_outcome is None:
        raise ValueError("active recall progression has an invalid run status")
    read = _active_recall_read_response(
        ActiveRecallReadResult(
            outcome=read_outcome,
            course_id=result.course_id,
            session=result.session,
            plan=result.plan,
            checkpoint=result.checkpoint,
            current_unit=result.current_unit,
            run=result.run,
            grade=result.grade,
        ),
        expected_course_id=expected_course_id,
        expected_session_id=expected_session_id,
    )
    if (
        expected_run_id is not None
        and read.run is not None
        and read.run.id != expected_run_id
    ):
        raise ValueError("active recall result does not match path")
    if read.checkpoint is None or read.run is None:
        raise ValueError("active recall progression is incomplete")
    return ActiveRecallProgressionResponse(
        outcome=result.outcome,
        course_id=read.course_id,
        session=read.session,
        plan=read.plan,
        checkpoint=read.checkpoint,
        current_unit=read.current_unit,
        run=read.run,
        grade=read.grade,
    )


@router.get(
    "/study-sessions/{session_id}",
    response_model=StudySessionReadResponse,
)
def get_study_session(
    request: Request,
    session_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
    course_id: str = Query(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
) -> StudySessionReadResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = StudySessionReadService(connection).get(
                course_id=course_id, session_id=session_id
            )
        if result is None:
            raise _read_not_found()
        return _read_response(result)
    except HTTPException:
        raise
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _read_service_error() from None


@router.get(
    "/study-sessions/{session_id}/diagnostic",
    response_model=DiagnosticReadResponse,
)
def get_study_diagnostic(
    request: Request,
    session_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
    course_id: str = Query(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
) -> DiagnosticReadResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = DiagnosticProgressionService(connection).get(
                course_id=course_id, session_id=session_id
            )
        return _diagnostic_read_response(
            result,
            expected_course_id=course_id,
            expected_session_id=session_id,
        )
    except DiagnosticNotFoundError:
        raise _diagnostic_not_found() from None
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _diagnostic_read_service_error() from None


@router.post(
    "/study-sessions/{session_id}/diagnostic",
    response_model=DiagnosticProgressionResponse,
)
def begin_study_diagnostic(
    payload: DiagnosticProgressionRequest,
    request: Request,
    response: Response,
    session_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
) -> DiagnosticProgressionResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = DiagnosticProgressionService(connection).begin(
                course_id=payload.course_id,
                session_id=session_id,
                expected_revision=payload.expected_revision,
                idempotency_key=payload.idempotency_key,
                now=datetime.now(UTC),
            )
        body = _diagnostic_response(
            result,
            expected_course_id=payload.course_id,
            expected_session_id=session_id,
        )
    except DiagnosticNotFoundError:
        raise _diagnostic_not_found() from None
    except DiagnosticConflictError:
        raise _diagnostic_conflict() from None
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _diagnostic_service_error() from None
    if body.outcome == "applied":
        response.status_code = 201
    return body


@router.post(
    "/study-sessions/{session_id}/diagnostic/{checkpoint_id}/answer",
    response_model=DiagnosticProgressionResponse,
)
def answer_study_diagnostic(
    payload: DiagnosticAnswerRequest,
    request: Request,
    response: Response,
    session_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
    checkpoint_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
) -> DiagnosticProgressionResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = DiagnosticProgressionService(connection).answer(
                course_id=payload.course_id,
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                expected_revision=payload.expected_revision,
                idempotency_key=payload.idempotency_key,
                response=payload.response,
                self_assessment=payload.self_assessment,
                now=datetime.now(UTC),
            )
        body = _diagnostic_response(
            result,
            expected_course_id=payload.course_id,
            expected_session_id=session_id,
            expected_checkpoint_id=checkpoint_id,
        )
    except DiagnosticNotFoundError:
        raise _diagnostic_not_found() from None
    except DiagnosticConflictError:
        raise _diagnostic_conflict() from None
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _diagnostic_service_error() from None
    if body.outcome == "applied":
        response.status_code = 201
    return body


@router.get(
    "/study-sessions/{session_id}/active-recall",
    response_model=ActiveRecallReadResponse,
)
def get_study_active_recall(
    request: Request,
    session_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
    course_id: str = Query(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
) -> ActiveRecallReadResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = ActiveRecallProgressionService(connection).get(
                course_id=course_id, session_id=session_id
            )
        return _active_recall_read_response(
            result,
            expected_course_id=course_id,
            expected_session_id=session_id,
        )
    except ActiveRecallNotFoundError:
        raise _active_recall_not_found() from None
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _active_recall_read_service_error() from None


@router.post(
    "/study-sessions/{session_id}/active-recall",
    response_model=ActiveRecallProgressionResponse,
)
def begin_study_active_recall(
    payload: ActiveRecallProgressionRequest,
    request: Request,
    response: Response,
    session_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
) -> ActiveRecallProgressionResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = ActiveRecallProgressionService(connection).begin(
                course_id=payload.course_id,
                session_id=session_id,
                expected_revision=payload.expected_revision,
                idempotency_key=payload.idempotency_key,
                now=datetime.now(UTC),
            )
        body = _active_recall_progression_response(
            result,
            expected_course_id=payload.course_id,
            expected_session_id=session_id,
        )
    except ActiveRecallNotFoundError:
        raise _active_recall_not_found() from None
    except ActiveRecallConflictError:
        raise _active_recall_conflict() from None
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _active_recall_write_service_error() from None
    if body.outcome == "applied":
        response.status_code = 201
    return body


@router.post(
    "/study-sessions/{session_id}/active-recall/{run_id}/answer",
    response_model=ActiveRecallProgressionResponse,
)
def answer_study_active_recall(
    payload: ActiveRecallAnswerRequest,
    request: Request,
    session_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
    run_id: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
) -> ActiveRecallProgressionResponse:
    """Answer is an update to an existing run, so applied and replay are 200."""

    try:
        with request.app.state.database.connection() as connection:
            result = ActiveRecallProgressionService(connection).answer(
                course_id=payload.course_id,
                session_id=session_id,
                run_id=run_id,
                expected_revision=payload.expected_revision,
                idempotency_key=payload.idempotency_key,
                response=payload.response,
                now=datetime.now(UTC),
            )
        return _active_recall_progression_response(
            result,
            expected_course_id=payload.course_id,
            expected_session_id=session_id,
            expected_run_id=run_id,
        )
    except ActiveRecallNotFoundError:
        raise _active_recall_not_found() from None
    except ActiveRecallConflictError:
        raise _active_recall_conflict() from None
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _active_recall_write_service_error() from None


@router.post(
    "/autonomous-study-sessions",
    response_model=AutonomousStudySessionStartResponse,
)
def start_or_resume_autonomous_study_session(
    payload: AutonomousStudySessionRequest,
    response: Response,
    request: Request,
) -> AutonomousStudySessionStartResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = AutonomousStudySessionService(connection).start_or_resume(
                course_id=payload.course_id,
                task_id=payload.task_id,
                now=datetime.now(UTC),
            )
        body = _response(
            result,
            expected_course_id=payload.course_id,
            expected_task_id=payload.task_id,
        )
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _write_service_error() from None

    if body.outcome == "session_created":
        response.status_code = 201
    return body


__all__ = ["router"]
