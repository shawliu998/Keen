"""Authenticated local review queue API."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..schemas import DueReviewListResponse, ReviewAttemptRequest, ReviewAttemptResponse
from ..services.review_session import (
    ReviewConflictError,
    ReviewIdempotencyConflictError,
    ReviewNotFoundError,
    ReviewSessionService,
    ReviewTaskConflictError,
    ReviewTaskNotFoundError,
    public_attempt,
)

router = APIRouter(prefix="/v1/reviews", tags=["reviews"])


@router.get("/due", response_model=DueReviewListResponse)
def list_due_reviews(
    request: Request,
    course_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
    limit: int = Query(default=50, ge=1, le=50),
) -> dict:
    now = datetime.now(UTC)
    try:
        with request.app.state.database.connection() as connection:
            items = ReviewSessionService(connection).list_due(
                as_of=now,
                course_id=course_id,
                limit=limit,
            )
    except sqlite3.Error as error:
        raise _read_error() from error
    return {"as_of": now, "items": items}


@router.post("/{item_id}/attempts", response_model=ReviewAttemptResponse)
def record_review_attempt(
    item_id: str,
    body: ReviewAttemptRequest,
    response: Response,
    request: Request,
) -> dict:
    try:
        with request.app.state.database.connection() as connection:
            result = ReviewSessionService(connection).record_attempt(
                item_id=item_id,
                rating=body.rating,
                response=body.response,
                expected_revision=body.expected_revision,
                idempotency_key=body.idempotency_key,
                reviewed_at=datetime.now(UTC),
                task_id=body.task_context.task_id if body.task_context else None,
                task_course_id=(
                    body.task_context.course_id if body.task_context else None
                ),
            )
    except ReviewTaskNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "review_task_not_found",
                "message": "This saved review task is no longer available.",
                "retryable": False,
                "recoveryAction": "Return to the Learning Feed and open a current task.",
                "automaticRecovery": False,
            },
        ) from error
    except ReviewTaskConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "review_task_context_conflict",
                "message": "This saved review task no longer matches the due item.",
                "retryable": False,
                "recoveryAction": "Return to the Learning Feed and open a current task.",
                "automaticRecovery": False,
            },
        ) from error
    except ReviewIdempotencyConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "review_attempt_idempotency_conflict",
                "message": "This rating does not match the saved review submission.",
                "retryable": False,
                "recoveryAction": "Return to the Learning Feed and open the current task.",
                "automaticRecovery": False,
            },
        ) from error
    except ReviewNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "review_item_not_found",
                "message": "This local review is no longer available.",
                "retryable": False,
                "recoveryAction": "Refresh the review queue and continue with an available item.",
                "automaticRecovery": False,
            },
        ) from error
    except ReviewConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "review_attempt_conflict",
                "message": "The local review schedule changed before this rating could be applied.",
                "retryable": True,
                "recoveryAction": "Refresh the review queue, then rate the current item again.",
                "automaticRecovery": False,
            },
        ) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "review_attempt_temporarily_unavailable",
                "message": "Keen could not safely determine whether this local review rating was saved.",
                "retryable": True,
                "recoveryAction": "Refresh the review queue, then retry with the same rating if the item remains due.",
                "automaticRecovery": False,
                "outcomeMayBeDurable": True,
            },
        ) from error
    if result.outcome == "applied":
        response.status_code = 201
    return public_attempt(result)


def _read_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "review_queue_temporarily_unavailable",
            "message": "Keen could not read the local review queue.",
            "retryable": True,
            "recoveryAction": "Retry. Existing review schedules were not changed.",
            "automaticRecovery": False,
        },
    )
