"""Authenticated API for starting real, source-grounded autonomous study work."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from ..schemas import (
    AutonomousStudyPlanResponse,
    AutonomousStudySessionRequest,
    AutonomousStudySessionResponse,
    AutonomousStudySessionStartResponse,
    AutonomousStudySessionUnitResponse,
    AutonomousStudyTaskResponse,
)
from ..services.autonomous_study_session import (
    AutonomousStudySessionResult,
    AutonomousStudySessionService,
)


router = APIRouter(prefix="/v1", tags=["autonomous-study-sessions"])


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
