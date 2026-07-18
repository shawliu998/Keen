"""Deterministic learning recap and one durable FSRS handoff."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.learning import transition_study_state
from app.repositories import load_json, write_scope
from app.repositories.review_repository import ReviewRepository
from app.repositories.study_repository import StudyRepository
from app.repositories.summary_review_repository import SummaryReviewRepository
from app.repositories.task_repository import TaskRepository
from app.review.scheduler import SCHEDULER_VERSION

_NAMESPACE = uuid.UUID("e89605a1-e0db-47b3-8f22-6a03bbf0c778")
SummaryOutcome = Literal["ready", "completed", "cancelled"]
WriteOutcome = Literal["applied", "replayed"]


class StudySummaryNotFoundError(LookupError):
    pass


class StudySummaryConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StudySummaryReadResult:
    outcome: SummaryOutcome
    course_id: str
    session: dict[str, Any]
    summary: dict[str, Any] | None
    review: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class StudySummaryResult:
    outcome: WriteOutcome
    course_id: str
    session: dict[str, Any]
    summary: dict[str, Any]
    review: dict[str, Any]


class StudySummaryReviewService:
    """Creates one review item without changing BKT/mastery state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, *, course_id: str, session_id: str) -> StudySummaryReadResult:
        course_id, session_id = (
            _identifier(course_id, "course_id"),
            _identifier(session_id, "session_id"),
        )
        session = self._session(course_id, session_id)
        effective = _effective_status(session)
        handoff = SummaryReviewRepository(self.connection).get_for_session(
            course_id=course_id, session_id=session_id
        )
        if handoff is not None:
            return self._read_handoff(handoff, session)
        if effective in {"cancelled", "failed"}:
            return StudySummaryReadResult(
                "cancelled", course_id, _public_session(session), None, None
            )
        if effective != "summarizing":
            raise StudySummaryConflictError("study session is not ready for summary")
        lineage = self._lineage(
            course_id=course_id, session_id=session_id, require_current=True
        )
        return StudySummaryReadResult(
            "ready", course_id, _public_session(session), _summary(lineage), None
        )

    def complete(
        self,
        *,
        course_id: str,
        session_id: str,
        expected_revision: int,
        idempotency_key: str,
        now: datetime,
    ) -> StudySummaryResult:
        course_id, session_id = (
            _identifier(course_id, "course_id"),
            _identifier(session_id, "session_id"),
        )
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")
        idempotency_key = _idempotency_key(idempotency_key)
        timestamp = _utc(now).isoformat()
        with write_scope(self.connection, commit=True):
            session = self._session(course_id, session_id)
            lineage = self._lineage(
                course_id=course_id, session_id=session_id, require_current=False
            )
            fingerprint = _fingerprint(
                course_id,
                session_id,
                lineage["practice_run_id"],
                expected_revision,
                SCHEDULER_VERSION,
            )
            ledger = SummaryReviewRepository(self.connection)
            try:
                replay = ledger.replay(
                    course_id=course_id,
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                    payload_fingerprint=fingerprint,
                )
            except ValueError as error:
                raise StudySummaryConflictError(str(error)) from error
            if replay is not None:
                return self._write_result(
                    replay, self._session(course_id, session_id), "replayed"
                )
            if _effective_status(session) == "paused":
                raise StudySummaryConflictError(
                    "paused study session cannot complete summary"
                )
            if session["status"] != "summarizing":
                existing = ledger.get_for_session(
                    course_id=course_id, session_id=session_id
                )
                if existing is not None:
                    raise StudySummaryConflictError(
                        "study summary is already completed; restore it before continuing"
                    )
                raise StudySummaryConflictError(
                    "study session is not ready for summary"
                )
            if int(session["revision"]) != expected_revision:
                raise StudySummaryConflictError("study session revision conflict")
            lineage = self._lineage(
                course_id=course_id, session_id=session_id, require_current=True
            )
            transition_study_state("summarizing", "review_scheduling")
            scheduling = StudyRepository(self.connection).transition_session(
                session_id,
                status="review_scheduling",
                expected_revision=expected_revision,
                updated_at=timestamp,
                commit=False,
            )
            review_item_id = _id(session_id, "review", idempotency_key)
            review, created = ReviewRepository(self.connection).create_item(
                item_id=review_item_id,
                course_id=course_id,
                concept_id=lineage["concept_id"],
                item_type="practice_problem",
                prompt=lineage["prompt"],
                expected_answer=lineage["answer_key"],
                source_type="assessment",
                source_id=lineage["assessment_id"],
                due_at=timestamp,
                scheduler_version=SCHEDULER_VERSION,
                idempotency_key=_review_idempotency_key(session_id, idempotency_key),
                created_at=timestamp,
                commit=False,
            )
            if not created:  # deterministic IDs only make this a repair/replay path
                raise RuntimeError(
                    "summary review item already exists without a handoff"
                )
            values = {
                "id": _id(session_id, "handoff", idempotency_key),
                "course_id": course_id,
                "session_id": session_id,
                "unit_id": lineage["unit_id"],
                "practice_run_id": lineage["practice_run_id"],
                "assessment_id": lineage["assessment_id"],
                "item_id": lineage["item_id"],
                "concept_id": lineage["concept_id"],
                "review_item_id": review_item_id,
                "active_recall_correct": int(lineage["active_recall_correct"]),
                "practice_correct": int(lineage["practice_correct"]),
                "practice_score": lineage["practice_score"],
                "practice_max_score": lineage["practice_max_score"],
                "remaining_units": lineage["remaining_units"],
                "scheduler_version": SCHEDULER_VERSION,
                "idempotency_key": idempotency_key,
                "review_due_at": review["due_at"],
                "review_scheduler": review["scheduler"],
                "review_state": review["state"],
                **self._complete_originating_task(session, timestamp),
                "payload_fingerprint": fingerprint,
                "created_at": timestamp,
            }
            handoff, applied = ledger.create(values=values, commit=False)
            if not applied:  # pragma: no cover - immediate writer lock owns preflight
                return self._write_result(
                    handoff, self._session(course_id, session_id), "replayed"
                )
            transition_study_state("review_scheduling", "completed")
            study = StudyRepository(self.connection)
            study.complete_current_unit(
                session_id=session_id,
                unit_id=lineage["unit_id"],
                expected_revision=int(scheduling["revision"]),
                updated_at=timestamp,
                commit=False,
            )
            completed = study.transition_session(
                session_id,
                status="completed",
                expected_revision=int(scheduling["revision"]),
                progress=1.0,
                updated_at=timestamp,
                commit=False,
            )
            return self._write_result(handoff, completed, "applied")

    def _session(self, course_id: str, session_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM study_sessions WHERE id = ? AND course_id = ?",
            (session_id, course_id),
        ).fetchone()
        if row is None:
            raise StudySummaryNotFoundError("study session not found")
        return dict(row)

    def _lineage(
        self, *, course_id: str, session_id: str, require_current: bool
    ) -> dict[str, Any]:
        current_clause = (
            "AND s.current_unit_id = r.unit_id AND u.status = 'active'"
            if require_current
            else ""
        )
        row = self.connection.execute(
            f"""SELECT r.id AS practice_run_id, r.unit_id, r.assessment_id, r.item_id, r.concept_id,
                      i.prompt, i.answer_key_json, i.max_score, ev.final_score, ev.is_correct,
                      ar.id AS active_recall_run_id, arev.is_correct AS active_recall_correct
               , (SELECT COUNT(*) FROM study_units u2 JOIN study_plan_versions p2 ON p2.id = u2.plan_version_id
                  WHERE p2.session_id = r.session_id AND u2.status = 'locked') AS remaining_units
               FROM study_practice_runs r
               JOIN study_sessions s ON s.id = r.session_id
               JOIN study_units u ON u.id = r.unit_id
               JOIN assessment_items i ON i.id = r.item_id AND i.assessment_id = r.assessment_id
               JOIN answer_evaluations ev ON ev.id = r.evaluation_id AND ev.item_id = r.item_id
               JOIN study_active_recall_runs ar ON ar.id = r.predecessor_active_recall_run_id
               JOIN answer_evaluations arev ON arev.id = ar.evaluation_id
               WHERE r.course_id = ? AND r.session_id = ? AND r.status = 'answered'
                 AND s.course_id = ? AND u.concept_id = r.concept_id {current_clause}""",
            (course_id, session_id, course_id),
        ).fetchone()
        if row is None:
            raise StudySummaryConflictError(
                "answered targeted practice is required before summary"
            )
        value = dict(row)
        answer_key = load_json(value.pop("answer_key_json"))
        if not isinstance(answer_key, dict) or not answer_key.get("accepted_answers"):
            raise RuntimeError("practice answer key is unavailable")
        value["answer_key"] = answer_key
        value["practice_correct"] = bool(value.pop("is_correct"))
        value["active_recall_correct"] = bool(value["active_recall_correct"])
        value["practice_score"] = float(value["final_score"])
        value["practice_max_score"] = float(value["max_score"])
        return value

    def _complete_originating_task(
        self, session: dict[str, Any], timestamp: str
    ) -> dict[str, Any]:
        task_id = session.get("originating_task_id")
        if task_id is None:
            return {"originating_task_id": None, "task_completed": 0}
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("study session originating task is invalid")
        task = TaskRepository(self.connection).get(task_id)
        if task is None or task["course_id"] != session["course_id"]:
            raise StudySummaryConflictError("originating study task is unavailable")
        if task["status"] == "completed":
            return {"originating_task_id": task_id, "task_completed": 1}
        if task["status"] not in {"upcoming", "overdue"}:
            raise StudySummaryConflictError(
                "originating study task cannot be completed"
            )
        TaskRepository(self.connection).complete(
            task_id,
            expected_revision=int(task["revision"]),
            completed_at=timestamp,
            commit=False,
        )
        return {"originating_task_id": task_id, "task_completed": 1}

    def _read_handoff(
        self, handoff: dict[str, Any], session: dict[str, Any]
    ) -> StudySummaryReadResult:
        review = self._review(handoff)
        return StudySummaryReadResult(
            "completed",
            handoff["course_id"],
            _public_session(session),
            _summary(handoff),
            review,
        )

    def _write_result(
        self, handoff: dict[str, Any], session: dict[str, Any], outcome: WriteOutcome
    ) -> StudySummaryResult:
        return StudySummaryResult(
            outcome,
            handoff["course_id"],
            _public_session(session),
            _summary(handoff),
            self._review(handoff),
        )

    def _review(self, handoff: dict[str, Any]) -> dict[str, Any]:
        return {
            "due_at": handoff["review_due_at"],
            "scheduler": handoff["review_scheduler"],
            "scheduler_version": handoff["scheduler_version"],
            "state": handoff["review_state"],
        }


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "active_recall_correct": bool(value["active_recall_correct"]),
        "practice_correct": bool(value["practice_correct"]),
        "practice_score": float(value["practice_score"]),
        "practice_max_score": float(value["practice_max_score"]),
        "task_completed": bool(value.get("task_completed", 0)),
        "remaining_units": int(value.get("remaining_units", 0)),
    }


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        key: session.get(key)
        for key in (
            "id",
            "course_id",
            "status",
            "revision",
            "progress",
            "estimated_minutes",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
        )
    }


def _effective_status(session: dict[str, Any]) -> str:
    status = session.get("status")
    if status == "paused":
        resume = session.get("resume_from_status")
        if not isinstance(resume, str):
            raise RuntimeError("paused study session has no resumable state")
        return resume
    return str(status)


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty identifier")
    return value


def _idempotency_key(value: object) -> str:
    key = _identifier(value, "idempotency_key")
    if len(key) < 16 or any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
        for char in key
    ):
        raise ValueError("idempotency_key is invalid")
    return key


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _fingerprint(*values: object) -> str:
    return hashlib.sha256("\x1f".join(map(str, values)).encode()).hexdigest()


def _id(session_id: str, kind: str, key: str) -> str:
    return (
        f"study-summary-{kind}:{uuid.uuid5(_NAMESPACE, f'{session_id}:{kind}:{key}')}"
    )


def _review_idempotency_key(session_id: str, key: str) -> str:
    return (
        "summary-review:"
        + hashlib.sha256(f"{session_id}\x1f{key}".encode()).hexdigest()
    )


__all__ = [
    "StudySummaryConflictError",
    "StudySummaryNotFoundError",
    "StudySummaryReadResult",
    "StudySummaryResult",
    "StudySummaryReviewService",
]
