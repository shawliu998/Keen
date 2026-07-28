"""Deterministic persisted branch after one valid active-recall result."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.repositories import write_scope
from app.repositories.adaptive_action_repository import AdaptiveActionRepository
from app.services.study_session_read import StudySessionReadService


ADAPTIVE_SESSION_POLICY_VERSION = "adaptive-session-policy/1.0.0"
_NAMESPACE = uuid.UUID("5eb5926c-274c-4ef8-8bb0-ad7b515a50f6")
_TERMINAL = frozenset({"completed", "cancelled", "failed"})

AdaptiveState = Literal[
    "legacy_canonical", "canonical", "action_required", "paused", "terminal"
]
AdaptiveOutcome = Literal["applied", "replayed"]


class AdaptiveStudyNotFoundError(LookupError):
    """The course-scoped session or action does not exist."""


class AdaptiveStudyConflictError(RuntimeError):
    """The persisted adaptive state cannot accept the requested action."""


@dataclass(frozen=True, slots=True)
class AdaptiveStudyStateResult:
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any] | None
    current_unit: dict[str, Any] | None
    current_unit_id: str | None
    state: AdaptiveState
    action: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class AdaptiveActionCompletionResult:
    outcome: AdaptiveOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any]
    completed_action: dict[str, Any]
    current_action: dict[str, Any]


class AdaptiveStudySessionService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_after_recall(
        self,
        *,
        course_id: str,
        session_id: str,
        unit_id: str,
        active_recall_run_id: str,
        correct: bool,
        created_at: str,
    ) -> dict[str, Any] | None:
        """Create the one initial action, participating in the recall transaction."""

        session = self._session(course_id=course_id, session_id=session_id)
        if session["adaptive_policy_version"] is None:
            return None
        if session["adaptive_policy_version"] != ADAPTIVE_SESSION_POLICY_VERSION:
            raise RuntimeError("study session adaptive policy is unsupported")
        kind = "practice" if correct else "remediate"
        reason = "active_recall_correct" if correct else "active_recall_incorrect"
        action, _ = AdaptiveActionRepository(self.connection).create_action(
            action_id=_action_id(active_recall_run_id, kind),
            course_id=course_id,
            session_id=session_id,
            unit_id=unit_id,
            predecessor_active_recall_run_id=active_recall_run_id,
            predecessor_action_id=None,
            kind=kind,
            reason_code=reason,
            policy_version=ADAPTIVE_SESSION_POLICY_VERSION,
            created_at=created_at,
            commit=False,
        )
        return action

    def get(self, *, course_id: str, session_id: str) -> AdaptiveStudyStateResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        read = StudySessionReadService(self.connection).get(
            course_id=course_id, session_id=session_id
        )
        if read is None:
            raise AdaptiveStudyNotFoundError("study session not found")
        current_unit = _current_unit(read.plan, read.current_unit_id)
        policy = self._policy(course_id=course_id, session_id=session_id)
        pending = AdaptiveActionRepository(self.connection).get_pending_for_session(
            course_id=course_id, session_id=session_id
        )
        status = str(read.session["status"])
        if policy is None:
            if pending is not None:
                raise RuntimeError("legacy session has an adaptive action")
            state: AdaptiveState = "legacy_canonical"
            action = None
        elif policy != ADAPTIVE_SESSION_POLICY_VERSION:
            raise RuntimeError("study session adaptive policy is unsupported")
        elif status in _TERMINAL:
            if pending is not None:
                raise RuntimeError(
                    "terminal study session has a pending adaptive action"
                )
            state, action = "terminal", None
        elif status == "paused":
            state, action = "paused", pending
        elif pending is not None:
            if read.current_unit_id != pending["unit_id"]:
                raise RuntimeError("adaptive action is outside the current study unit")
            state, action = "action_required", pending
        else:
            state, action = "canonical", None
        return AdaptiveStudyStateResult(
            course_id=course_id,
            session=read.session,
            plan=read.plan,
            current_unit=current_unit,
            current_unit_id=read.current_unit_id,
            state=state,
            action=action,
        )

    def complete_remediation(
        self,
        *,
        course_id: str,
        session_id: str,
        action_id: str,
        expected_action_revision: int,
        idempotency_key: str,
        now: datetime,
    ) -> AdaptiveActionCompletionResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        action_id = _identifier(action_id, "action_id")
        expected_action_revision = _revision(expected_action_revision)
        idempotency_key = _idempotency_key(idempotency_key)
        timestamp = _utc(now).isoformat()
        fingerprint = _fingerprint(
            course_id,
            session_id,
            action_id,
            expected_action_revision,
            ADAPTIVE_SESSION_POLICY_VERSION,
        )
        with write_scope(self.connection, commit=True):
            session = self._session(course_id=course_id, session_id=session_id)
            if session["adaptive_policy_version"] != ADAPTIVE_SESSION_POLICY_VERSION:
                raise AdaptiveStudyConflictError(
                    "study session does not use the adaptive policy"
                )
            ledger = AdaptiveActionRepository(self.connection)
            action = ledger.get_for_session(
                course_id=course_id, session_id=session_id, action_id=action_id
            )
            if action is None:
                raise AdaptiveStudyNotFoundError("adaptive action not found")
            key_owner = ledger.get_by_completion_key(
                course_id=course_id, session_id=session_id, key=idempotency_key
            )
            if key_owner is not None and key_owner["id"] != action_id:
                raise AdaptiveStudyConflictError(
                    "adaptive action idempotency key was reused"
                )
            if action["status"] == "completed":
                if (
                    key_owner is None
                    or key_owner["id"] != action_id
                    or ledger.completion_fingerprint(action_id) != fingerprint
                ):
                    raise AdaptiveStudyConflictError(
                        "adaptive action completion does not match the replay"
                    )
                return self._completion_result(
                    course_id=course_id,
                    session_id=session_id,
                    completed_action=action,
                    outcome="replayed",
                )
            if action["status"] != "pending" or action["kind"] != "remediate":
                raise AdaptiveStudyConflictError(
                    "adaptive action is not pending remediation"
                )
            if int(action["revision"]) != expected_action_revision:
                raise AdaptiveStudyConflictError("adaptive action revision conflict")
            if session["status"] == "paused":
                raise AdaptiveStudyConflictError(
                    "paused study session cannot complete remediation"
                )
            if (
                session["status"] != "practicing"
                or session["current_unit_id"] != action["unit_id"]
            ):
                raise AdaptiveStudyConflictError(
                    "remediation is outside the current study unit"
                )
            completed = ledger.complete_remediation(
                action_id=action_id,
                expected_revision=expected_action_revision,
                idempotency_key=idempotency_key,
                payload_fingerprint=fingerprint,
                completed_at=timestamp,
                commit=False,
            )
            identity = ledger.branch_identity(action_id)
            if identity is None:
                raise RuntimeError("adaptive remediation identity disappeared")
            ledger.create_action(
                action_id=_action_id(
                    str(identity["predecessor_active_recall_run_id"]), "practice"
                ),
                course_id=course_id,
                session_id=session_id,
                unit_id=str(action["unit_id"]),
                predecessor_active_recall_run_id=str(
                    identity["predecessor_active_recall_run_id"]
                ),
                predecessor_action_id=action_id,
                kind="practice",
                reason_code="remediation_completed",
                policy_version=ADAPTIVE_SESSION_POLICY_VERSION,
                created_at=timestamp,
                commit=False,
            )
            return self._completion_result(
                course_id=course_id,
                session_id=session_id,
                completed_action=completed,
                outcome="applied",
            )

    def require_pending_practice(
        self, *, course_id: str, session_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Gate a new practice run; legacy sessions retain canonical behavior."""

        policy = self._policy(course_id=course_id, session_id=session_id)
        if policy is None:
            return None
        if policy != ADAPTIVE_SESSION_POLICY_VERSION:
            raise RuntimeError("study session adaptive policy is unsupported")
        action = AdaptiveActionRepository(self.connection).get_pending_for_session(
            course_id=course_id, session_id=session_id
        )
        if action is None or action["kind"] != "practice":
            raise AdaptiveStudyConflictError(
                "practice is blocked until the current adaptive action is complete"
            )
        if action["unit_id"] != unit_id:
            raise AdaptiveStudyConflictError(
                "adaptive practice action is outside the current study unit"
            )
        return action

    def complete_practice(
        self, *, action_id: str, practice_run_id: str, completed_at: str
    ) -> None:
        AdaptiveActionRepository(self.connection).complete_practice(
            action_id=action_id,
            practice_run_id=practice_run_id,
            completed_at=completed_at,
            commit=False,
        )

    def _completion_result(
        self,
        *,
        course_id: str,
        session_id: str,
        completed_action: dict[str, Any],
        outcome: AdaptiveOutcome,
    ) -> AdaptiveActionCompletionResult:
        read = StudySessionReadService(self.connection).get(
            course_id=course_id, session_id=session_id
        )
        if read is None or read.plan is None:
            raise RuntimeError("adaptive study session plan is unavailable")
        current = AdaptiveActionRepository(self.connection).get_pending_for_session(
            course_id=course_id, session_id=session_id
        )
        if current is None:
            identity = AdaptiveActionRepository(self.connection).branch_identity(
                str(completed_action["id"])
            )
            if identity is None:
                raise RuntimeError("adaptive remediation identity disappeared")
            current = AdaptiveActionRepository(self.connection).get_for_branch(
                course_id=course_id,
                session_id=session_id,
                predecessor_active_recall_run_id=str(
                    identity["predecessor_active_recall_run_id"]
                ),
                kind="practice",
            )
        if current is None or current["kind"] != "practice":
            raise RuntimeError("remediation did not create one practice action")
        return AdaptiveActionCompletionResult(
            outcome=outcome,
            course_id=course_id,
            session=read.session,
            plan=read.plan,
            completed_action=completed_action,
            current_action=current,
        )

    def _session(self, *, course_id: str, session_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """SELECT id, course_id, status, current_unit_id, adaptive_policy_version
               FROM study_sessions WHERE id = ? AND course_id = ?""",
            (session_id, course_id),
        ).fetchone()
        if row is None:
            raise AdaptiveStudyNotFoundError("study session not found")
        return dict(row)

    def _policy(self, *, course_id: str, session_id: str) -> str | None:
        return self._session(course_id=course_id, session_id=session_id)[
            "adaptive_policy_version"
        ]


def _current_unit(
    plan: dict[str, Any] | None, current_unit_id: str | None
) -> dict[str, Any] | None:
    if plan is None or current_unit_id is None:
        return None
    units = [unit for unit in plan["units"] if unit["id"] == current_unit_id]
    if len(units) != 1:
        raise RuntimeError("study session current unit is outside its plan")
    return units[0]


def _action_id(active_recall_run_id: str, kind: str) -> str:
    return "adaptive-action-" + str(
        uuid.uuid5(_NAMESPACE, f"{active_recall_run_id}:{kind}")
    )


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty identifier")
    return value


def _revision(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_action_revision must be a non-negative integer")
    return value


def _idempotency_key(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
    if (
        not isinstance(value, str)
        or not 16 <= len(value) <= 128
        or value[0] not in allowed[:62]
        or any(character not in allowed for character in value)
    ):
        raise ValueError("idempotency_key must be a valid 16 to 128 character key")
    return value


def _fingerprint(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode()).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "ADAPTIVE_SESSION_POLICY_VERSION",
    "AdaptiveActionCompletionResult",
    "AdaptiveStudyConflictError",
    "AdaptiveStudyNotFoundError",
    "AdaptiveStudySessionService",
    "AdaptiveStudyStateResult",
]
