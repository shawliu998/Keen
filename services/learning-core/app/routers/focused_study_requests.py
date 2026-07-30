"""Authenticated API for explicit goal-owned focused study."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response

from ..schemas import FocusedStudyRequest, FocusedStudyRequestResponse
from ..services.focused_study_request import (
    FocusedStudyConflictError,
    FocusedStudyRequestResult,
    FocusedStudyRequestService,
)
from .autonomous_study_sessions import _plan, _session, _task


router = APIRouter(prefix="/v1", tags=["focused-study"])


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "focused_study_identity_conflict",
            "message": "This focused-study request identity was already used for different inputs.",
            "retryable": False,
            "recoveryAction": "Start a new request with a new client request ID and idempotency key.",
            "automaticRecovery": False,
            "outcomeMayBeDurable": False,
        },
    )


def _service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "focused_study_temporarily_unavailable",
            "message": "Keen could not safely determine whether the focused study was saved.",
            "retryable": True,
            "recoveryAction": "Retry with the same client request ID and idempotency key to reconcile the result.",
            "automaticRecovery": False,
            "outcomeMayBeDurable": True,
        },
    )


def _recovery(reason: str) -> str:
    return {
        "course_not_found": "Refresh the course list and choose an available source scope.",
        "no_matching_indexed_source": (
            "Choose an indexed source that covers this goal, or revise the goal and use new request identities."
        ),
    }[reason]


def _response(result: FocusedStudyRequestResult) -> FocusedStudyRequestResponse:
    if result.outcome == "blocked":
        if (
            result.blocked_reason is None
            or result.task is not None
            or result.session is not None
            or result.plan is not None
        ):
            raise ValueError("blocked focused-study result is inconsistent")
        return FocusedStudyRequestResponse(
            outcome="blocked",
            course_id=result.course_id,
            task=None,
            session=None,
            plan=None,
            blocked_reason=result.blocked_reason,
            recovery_action=_recovery(result.blocked_reason),
        )
    if (
        result.blocked_reason is not None
        or result.task is None
        or result.session is None
        or result.plan is None
        or result.task.get("course_id") != result.course_id
        or result.session.get("course_id") != result.course_id
        or result.session.get("originating_task_id") != result.task.get("id")
        or result.plan.get("session_id") != result.session.get("id")
    ):
        raise ValueError("successful focused-study result is inconsistent")
    return FocusedStudyRequestResponse(
        outcome=result.outcome,
        course_id=result.course_id,
        task=_task(result.task),
        session=_session(result.session),
        plan=_plan(result.plan),
        blocked_reason=None,
        recovery_action=None,
    )


@router.post(
    "/focused-study-requests",
    response_model=FocusedStudyRequestResponse,
)
def start_focused_study(
    payload: FocusedStudyRequest,
    response: Response,
    request: Request,
) -> FocusedStudyRequestResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = FocusedStudyRequestService(connection).start(
                course_id=payload.course_id,
                goal=payload.goal,
                client_request_id=payload.client_request_id,
                idempotency_key=payload.idempotency_key,
                now=datetime.now(UTC),
            )
        body = _response(result)
    except FocusedStudyConflictError:
        raise _conflict() from None
    except (sqlite3.Error, RuntimeError, ValueError, LookupError, KeyError, TypeError):
        raise _service_error() from None
    if body.outcome == "session_created":
        response.status_code = 201
    return body


__all__ = ["router"]
