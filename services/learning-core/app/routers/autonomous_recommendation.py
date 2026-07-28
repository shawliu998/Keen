"""Authenticated, local-only API for one deterministic learning recommendation."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..concept_bootstrap import (
    ConceptBootstrapResult,
    CourseDocumentUnavailableError,
    CourseNotFoundError,
    IncompleteConceptMasteryStateError,
    IndexedDocumentRequiredError,
)
from ..repository import LearningRepository
from ..schemas import (
    ConceptBootstrapResponse,
    LearningActionCandidateResponse,
    LearningFeedRecommendationResponse,
    LearningFeedRequest,
    LearningFeedSnapshotResponse,
    LearningFeedTaskResponse,
    LearningPriorityComponentResponse,
)
from ..services.autonomous_recommendation import AutonomousRecommendationCoordinator
from ..services.learning_snapshot import (
    LearningActionCandidate,
    LearningSnapshot,
    LearningSnapshotService,
)


router = APIRouter(prefix="/v1", tags=["learning-feed"])


def _not_found(*, code: str, message: str, recovery: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": code,
            "message": message,
            "retryable": False,
            "recoveryAction": recovery,
            "automaticRecovery": False,
        },
    )


def _conflict(*, code: str, message: str, recovery: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": code,
            "message": message,
            "retryable": True,
            "recoveryAction": recovery,
            "automaticRecovery": False,
        },
    )


def _read_service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "learning_feed_temporarily_unavailable",
            "message": "Keen could not safely read the local learning feed.",
            "retryable": True,
            "recoveryAction": "Refresh the learning feed and retry.",
            "automaticRecovery": False,
        },
    )


def _write_service_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "learning_feed_temporarily_unavailable",
            "message": "Keen could not safely read or update the local learning feed.",
            "retryable": True,
            "recoveryAction": "Refresh the learning feed and retry. The result may already be saved.",
            "automaticRecovery": False,
            "outcomeMayBeDurable": True,
        },
    )


def _require_course(repository: LearningRepository, course_id: str) -> None:
    if repository.get_course(course_id) is None:
        raise _course_not_found()


def _course_not_found() -> HTTPException:
    return _not_found(
        code="course_not_found",
        message="The requested course was not found.",
        recovery="Refresh the course list and choose an available course.",
    )


def _candidate(candidate: LearningActionCandidate) -> LearningActionCandidateResponse:
    return LearningActionCandidateResponse(
        id=candidate.id,
        action=candidate.action,
        target_type=candidate.target_type,
        target_id=candidate.target_id,
        concept_id=candidate.concept_id,
        component=candidate.component,
        priority_tier=candidate.priority_tier,
        estimated_minutes=candidate.estimated_minutes,
        fits_available_minutes=candidate.fits_available_minutes,
        priority_score=candidate.priority_score,
        priority_unclamped_score=candidate.priority_unclamped_score,
        priority_algorithm_version=candidate.priority_algorithm_version,
        priority_components=[
            LearningPriorityComponentResponse(
                name=item.name,
                raw_value=item.raw_value,
                weight=item.weight,
                contribution=item.contribution,
            )
            for item in candidate.priority_components
        ],
        priority_explanation=list(candidate.priority_explanation),
        why=candidate.why,
    )


def _task(task: dict[str, object]) -> LearningFeedTaskResponse:
    """Expose only the bounded task data needed to render the local feed."""

    return LearningFeedTaskResponse.model_validate(
        {
            "id": task["id"],
            "course_id": task["course_id"],
            "concept_id": task["concept_id"],
            "title": task["title"],
            "reason": task["reason"],
            "due_at": _stored_utc_datetime(task["due_at"]),
            "estimated_minutes": task["estimated_minutes"],
            "status": task["status"],
            "source_type": task["source_type"],
            "source_id": task["source_id"],
            "priority_score": task["priority_score"],
            "recommended_reason": task["recommended_reason"],
            "scheduled_for": _stored_utc_datetime(task["scheduled_for"], optional=True),
            "created_at": _stored_utc_datetime(task["created_at"]),
            "updated_at": _stored_utc_datetime(task["updated_at"]),
            "completed_at": _stored_utc_datetime(
                task.get("completed_at"), optional=True
            ),
        }
    )


def _stored_utc_datetime(value: object, *, optional: bool = False) -> datetime | None:
    """Normalize legacy SQLite timestamps under Keen's UTC storage contract.

    Early tasks may contain a date-only or naive ISO value.  Those values were
    stored under the same UTC convention, so the API makes that convention
    explicit instead of weakening the client boundary.  Malformed values fail
    closed and are mapped to a redacted service error by the caller.
    """

    if value is None:
        if optional:
            return None
        raise ValueError("stored task timestamp is missing")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("stored task timestamp is invalid") from None
    else:
        raise ValueError("stored task timestamp is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _snapshot(snapshot: LearningSnapshot) -> LearningFeedSnapshotResponse:
    return LearningFeedSnapshotResponse(
        course_id=snapshot.course_id,
        as_of=snapshot.as_of,
        available_minutes=snapshot.available_minutes,
        due_review_count=len(snapshot.due_reviews),
        incomplete_session_count=len(snapshot.incomplete_sessions),
        mastery_gap_count=snapshot.mastery_gap_count,
        misconception_count=len(snapshot.misconceptions),
        pending_tasks=[_task(task) for task in snapshot.pending_tasks],
        completed_tasks=[_task(task) for task in snapshot.completed_tasks],
        candidates=[_candidate(candidate) for candidate in snapshot.candidates],
    )


def _bootstrap(
    result: ConceptBootstrapResult | None,
) -> ConceptBootstrapResponse | None:
    if result is None:
        return None
    return ConceptBootstrapResponse.model_validate(
        {
            "course_id": result.course_id,
            "document_id": result.document_id,
            "concept_id": result.concept_id,
            "concept_name": result.concept_name,
            "mastery_probability": result.mastery_probability,
            "mastery_attempts": result.mastery_attempts,
            "concept_created": result.concept_created,
            "mastery_initialized": result.mastery_initialized,
            "mastery_initialization_algorithm": result.mastery_initialization_algorithm,
            "mastery_initialization_algorithm_version": result.mastery_initialization_algorithm_version,
        }
    )


@router.get("/learning-snapshot", response_model=LearningFeedSnapshotResponse)
def get_learning_feed(
    request: Request,
    course_id: str = Query(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
    ),
    available_minutes: int = Query(default=25, ge=1, le=1_440),
) -> LearningFeedSnapshotResponse:
    try:
        with request.app.state.database.connection() as connection:
            _require_course(LearningRepository(connection), course_id)
            snapshot = LearningSnapshotService(connection).build(
                course_id=course_id,
                now=datetime.now(UTC),
                available_minutes=available_minutes,
            )
        return _snapshot(snapshot)
    except sqlite3.Error:
        raise _read_service_error() from None
    except ValueError:
        # Pydantic has already checked request values; do not expose internal details.
        raise _read_service_error() from None


@router.post(
    "/autonomous-recommendations", response_model=LearningFeedRecommendationResponse
)
def recommend_learning_action(
    payload: LearningFeedRequest,
    response: Response,
    request: Request,
) -> LearningFeedRecommendationResponse:
    try:
        with request.app.state.database.connection() as connection:
            result = AutonomousRecommendationCoordinator(
                connection
            ).observe_and_recommend(
                course_id=payload.course_id,
                document_id=payload.document_id,
                now=datetime.now(UTC),
                available_minutes=payload.available_minutes,
                time_zone=payload.time_zone,
            )
    except CourseNotFoundError:
        raise _course_not_found() from None
    except CourseDocumentUnavailableError:
        raise _not_found(
            code="document_not_available_for_course",
            message="The selected document is not available in this course.",
            recovery="Choose a document linked to this course and retry.",
        ) from None
    except IndexedDocumentRequiredError:
        raise _conflict(
            code="document_not_indexed",
            message="The selected document must finish indexing before it can be used for learning.",
            recovery="Wait for indexing to finish, then retry this recommendation.",
        ) from None
    except IncompleteConceptMasteryStateError:
        raise _conflict(
            code="concept_mastery_state_incomplete",
            message="Keen found incomplete local mastery state and did not create a recommendation.",
            recovery="Refresh the course after local recovery completes, then retry.",
        ) from None
    except (sqlite3.Error, RuntimeError, ValueError):
        raise _write_service_error() from None

    # The snapshot is intentionally able to describe a missing course for
    # internal read composition.  This public mutation must not present that
    # absence as a real, empty local course.
    if not result.snapshot.course_exists:
        raise _course_not_found()
    if result.outcome == "task_created":
        response.status_code = 201
    try:
        return LearningFeedRecommendationResponse(
            outcome=result.outcome,
            course_id=result.course_id,
            snapshot=_snapshot(result.snapshot),
            task=_task(result.task) if result.task is not None else None,
            candidate=_candidate(result.candidate)
            if result.candidate is not None
            else None,
            bootstrap=_bootstrap(result.bootstrap),
        )
    except ValueError:
        # Stored state crossing this boundary failed the strict response model.
        raise _write_service_error() from None


__all__ = ["router"]
