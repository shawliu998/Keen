"""Move a source-grounded session through its non-scored opening diagnostic."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.learning import transition_study_state
from app.mastery_evidence import (
    MasteryEvidence,
    ResponseType,
    calculate_evidence_weight,
)
from app.repositories import write_scope
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.study_repository import StudyRepository
from app.services.study_session_read import StudySessionReadService


_NAMESPACE = uuid.UUID("e7651f4c-6dfc-4529-8e8a-77c469a0a444")
DiagnosticOutcome = Literal["applied", "replayed"]
DiagnosticReadOutcome = Literal["not_started", "pending", "answered"]
_ANSWERED_SESSION_STATES = frozenset(
    {
        "studying",
        "checkpoint",
        "active_recall",
        "practicing",
        "summarizing",
        "review_scheduling",
    }
)


class DiagnosticNotFoundError(LookupError):
    """The session/checkpoint is absent from the requested course scope."""


class DiagnosticConflictError(RuntimeError):
    """A healthy session no longer accepts the requested transition."""


@dataclass(frozen=True, slots=True)
class DiagnosticProgressionResult:
    outcome: DiagnosticOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any]
    checkpoint: dict[str, Any]
    current_unit: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class DiagnosticReadResult:
    outcome: DiagnosticReadOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any]
    checkpoint: dict[str, Any] | None
    current_unit: dict[str, Any] | None


class DiagnosticProgressionService:
    """Perform each diagnostic mutation in one local SQLite transaction.

    The stored learner response is untrusted display data.  It is deliberately
    represented only by zero-weight ``user_report`` evidence: no answer is
    graded and no mastery, FSRS, task, or misconception state is changed.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def begin(
        self,
        *,
        course_id: str,
        session_id: str,
        expected_revision: int,
        idempotency_key: str,
        now: datetime,
    ) -> DiagnosticProgressionResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        idempotency_key = _idempotency_key(idempotency_key)
        expected_revision = _revision(expected_revision)
        fingerprint = _fingerprint("begin", course_id, session_id, expected_revision)
        timestamp = _utc(now).isoformat()
        with write_scope(self.connection, commit=True):
            self._require_scoped_session(course_id=course_id, session_id=session_id)
            repo = StudyRepository(self.connection)
            replay = self.connection.execute(
                """
                SELECT * FROM study_checkpoints
                WHERE diagnostic_begin_idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
            if replay is not None:
                checkpoint = dict(replay)
                if (
                    checkpoint["diagnostic_begin_payload_fingerprint"] != fingerprint
                    or checkpoint["session_id"] != session_id
                ):
                    raise DiagnosticConflictError(
                        "diagnostic begin idempotency key was reused"
                    )
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    checkpoint=checkpoint,
                    outcome="replayed",
                )

            state = self._read(course_id=course_id, session_id=session_id)
            session = state.session
            plan = state.plan
            if plan is None or session["status"] != "goal_confirmation":
                raise DiagnosticConflictError(
                    "study session is not ready for diagnostics"
                )
            if int(session["revision"]) != expected_revision:
                raise DiagnosticConflictError("study session revision conflict")
            first = _first_ready_unit(state, require_current_none=True)
            existing = self.connection.execute(
                """
                SELECT 1 FROM study_checkpoints
                WHERE session_id = ? AND kind = 'diagnostic' AND status = 'pending'
                """,
                (session_id,),
            ).fetchone()
            if existing is not None:
                raise DiagnosticConflictError(
                    "study session already has a pending diagnostic"
                )
            transition_study_state("goal_confirmation", "diagnosing")
            checkpoint, created = repo.create_diagnostic_checkpoint(
                checkpoint_id=_checkpoint_id(session_id, idempotency_key),
                session_id=session_id,
                unit_id=str(first["id"]),
                prompt=_prompt(first),
                idempotency_key=idempotency_key,
                payload_fingerprint=fingerprint,
                created_at=timestamp,
                commit=False,
            )
            if not created:  # pragma: no cover - covered by upfront replay lookup
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    checkpoint=checkpoint,
                    outcome="replayed",
                )
            repo.transition_session(
                session_id,
                status="diagnosing",
                expected_revision=expected_revision,
                updated_at=timestamp,
                commit=False,
            )
            return self._result(
                course_id=course_id,
                session_id=session_id,
                checkpoint=checkpoint,
                outcome="applied",
            )

    def get(self, *, course_id: str, session_id: str) -> DiagnosticReadResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        self._require_scoped_session(course_id=course_id, session_id=session_id)
        state = self._read(course_id=course_id, session_id=session_id)
        plan = state.plan
        if plan is None:  # pragma: no cover - _read enforces this
            raise RuntimeError("study session plan is unavailable")
        rows = self.connection.execute(
            """
            SELECT * FROM study_checkpoints
            WHERE session_id = ? AND kind = 'diagnostic'
            ORDER BY created_at, id
            """,
            (session_id,),
        ).fetchall()
        checkpoints = [dict(row) for row in rows]
        session = state.session
        current = next(
            (unit for unit in plan["units"] if unit["id"] == state.current_unit_id),
            None,
        )
        effective_status = _effective_session_status(session)
        if effective_status == "goal_confirmation":
            if checkpoints:
                raise RuntimeError("goal confirmation has an unexpected diagnostic")
            return DiagnosticReadResult(
                outcome="not_started",
                course_id=course_id,
                session=session,
                plan=plan,
                checkpoint=None,
                current_unit=None,
            )
        if effective_status == "diagnosing":
            if len(checkpoints) != 1 or checkpoints[0]["status"] != "pending":
                raise RuntimeError("diagnosing session has no valid pending diagnostic")
            checkpoint = checkpoints[0]
            if checkpoint["unit_id"] != plan["units"][0]["id"] or current is not None:
                raise RuntimeError("pending diagnostic is outside the current plan")
            return DiagnosticReadResult(
                outcome="pending",
                course_id=course_id,
                session=session,
                plan=plan,
                checkpoint=checkpoint,
                current_unit=None,
            )
        if effective_status in _ANSWERED_SESSION_STATES:
            if len(checkpoints) != 1 or checkpoints[0]["status"] != "answered":
                raise RuntimeError("studying session has no answered diagnostic")
            checkpoint = checkpoints[0]
            if (
                checkpoint["unit_id"] != plan["units"][0]["id"]
                or current is None
                or current["id"] != plan["units"][0]["id"]
                or current["status"] != "active"
            ):
                raise RuntimeError("answered diagnostic is outside the current plan")
            self._validate_answered_evidence(checkpoint=checkpoint, unit=current)
            return DiagnosticReadResult(
                outcome="answered",
                course_id=course_id,
                session=session,
                plan=plan,
                checkpoint=checkpoint,
                current_unit=current,
            )
        raise RuntimeError("study session cannot restore a diagnostic in this state")

    def answer(
        self,
        *,
        course_id: str,
        session_id: str,
        checkpoint_id: str,
        expected_revision: int,
        idempotency_key: str,
        response: str,
        self_assessment: str,
        now: datetime,
    ) -> DiagnosticProgressionResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        checkpoint_id = _identifier(checkpoint_id, "checkpoint_id")
        idempotency_key = _idempotency_key(idempotency_key)
        expected_revision = _revision(expected_revision)
        response = _response(response)
        self_assessment = _self_assessment(self_assessment)
        fingerprint = _fingerprint(
            "answer",
            course_id,
            session_id,
            checkpoint_id,
            expected_revision,
            response,
            self_assessment,
        )
        timestamp = _utc(now).isoformat()
        with write_scope(self.connection, commit=True):
            self._require_scoped_session(course_id=course_id, session_id=session_id)
            repo = StudyRepository(self.connection)
            row = self.connection.execute(
                "SELECT * FROM study_checkpoints WHERE id = ? AND session_id = ?",
                (checkpoint_id, session_id),
            ).fetchone()
            checkpoint = dict(row) if row is not None else None
            if checkpoint is None:
                raise DiagnosticNotFoundError("study checkpoint not found")
            if checkpoint["diagnostic_answer_idempotency_key"] is not None:
                if (
                    checkpoint["diagnostic_answer_idempotency_key"] != idempotency_key
                    or checkpoint["diagnostic_answer_payload_fingerprint"]
                    != fingerprint
                ):
                    raise DiagnosticConflictError(
                        "diagnostic answer is already recorded"
                    )
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    checkpoint=checkpoint,
                    outcome="replayed",
                )

            state = self._read(course_id=course_id, session_id=session_id)
            session = state.session
            if session["status"] != "diagnosing":
                raise DiagnosticConflictError(
                    "study session is not awaiting a diagnostic answer"
                )
            if int(session["revision"]) != expected_revision:
                raise DiagnosticConflictError("study session revision conflict")
            first = _first_ready_unit(state, require_current_none=True)
            if (
                checkpoint["kind"] != "diagnostic"
                or checkpoint["status"] != "pending"
                or checkpoint["unit_id"] != first["id"]
            ):
                raise DiagnosticConflictError("diagnostic checkpoint is not current")
            concept_id = first.get("concept_id")
            if (
                not isinstance(concept_id, str)
                or concept_id not in first["concept_ids"]
            ):
                raise RuntimeError("first study unit has no validated primary concept")

            evidence_id = _evidence_id(checkpoint_id, idempotency_key)
            weight = calculate_evidence_weight(
                MasteryEvidence(
                    correctness=_assessment_correctness(self_assessment),
                    independence=0.0,
                    hint_level=0,
                    difficulty=1.0,
                    confidence=1.0,
                    response_type=ResponseType.USER_REPORT,
                )
            )
            if weight != 0.0:  # defensive invariant for future parameter changes
                raise RuntimeError(
                    "diagnostic user report evidence must have zero weight"
                )
            MasteryRepository(self.connection).record_evidence(
                evidence_id=evidence_id,
                concept_id=concept_id,
                evidence_type=ResponseType.USER_REPORT.value,
                correctness=_assessment_correctness(self_assessment),
                independence=0.0,
                hint_level=0,
                weight=weight,
                idempotency_key=f"diagnostic-answer:{checkpoint_id}:{idempotency_key}",
                session_id=session_id,
                created_at=timestamp,
                commit=False,
            )
            checkpoint, applied = repo.answer_diagnostic_checkpoint(
                checkpoint_id=checkpoint_id,
                response=response,
                idempotency_key=idempotency_key,
                payload_fingerprint=fingerprint,
                mastery_evidence_id=evidence_id,
                answered_at=timestamp,
                commit=False,
            )
            if not applied:  # pragma: no cover - protected by preflight above
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    checkpoint=checkpoint,
                    outcome="replayed",
                )
            transition_study_state("diagnosing", "planning")
            planning = repo.transition_session(
                session_id,
                status="planning",
                expected_revision=expected_revision,
                updated_at=timestamp,
                commit=False,
            )
            transition_study_state("planning", "studying")
            repo.activate_first_unit(
                unit_id=str(first["id"]),
                session_id=session_id,
                updated_at=timestamp,
                commit=False,
            )
            repo.transition_session(
                session_id,
                status="studying",
                expected_revision=int(planning["revision"]),
                progress=0.0,
                current_unit_id=str(first["id"]),
                updated_at=timestamp,
                commit=False,
            )
            return self._result(
                course_id=course_id,
                session_id=session_id,
                checkpoint=checkpoint,
                outcome="applied",
            )

    def _read(self, *, course_id: str, session_id: str):
        result = StudySessionReadService(self.connection).get(
            course_id=course_id, session_id=session_id
        )
        if result is None:
            raise DiagnosticNotFoundError("study session not found")
        if result.outcome != "ready" or result.plan is None:
            raise RuntimeError("study session plan is unavailable")
        return result

    def _require_scoped_session(self, *, course_id: str, session_id: str) -> None:
        row = self.connection.execute(
            "SELECT 1 FROM study_sessions WHERE id = ? AND course_id = ?",
            (session_id, course_id),
        ).fetchone()
        if row is None:
            raise DiagnosticNotFoundError("study session not found")

    def _result(
        self,
        *,
        course_id: str,
        session_id: str,
        checkpoint: dict[str, Any],
        outcome: DiagnosticOutcome,
    ) -> DiagnosticProgressionResult:
        state = self._read(course_id=course_id, session_id=session_id)
        plan = state.plan
        if plan is None:
            raise RuntimeError("diagnostic session plan is unavailable")
        current = next(
            (unit for unit in plan["units"] if unit["id"] == state.current_unit_id),
            None,
        )
        if checkpoint.get("status") == "answered":
            first = plan["units"][0] if plan["units"] else None
            if first is None or checkpoint.get("unit_id") != first.get("id"):
                raise RuntimeError("answered diagnostic is outside the current plan")
            self._validate_answered_evidence(checkpoint=checkpoint, unit=first)
        return DiagnosticProgressionResult(
            outcome=outcome,
            course_id=course_id,
            session=state.session,
            plan=plan,
            checkpoint=checkpoint,
            current_unit=current,
        )

    def _validate_answered_evidence(
        self, *, checkpoint: dict[str, Any], unit: dict[str, Any]
    ) -> None:
        evidence_id = checkpoint.get("mastery_evidence_id")
        concept_id = unit.get("concept_id")
        concept_ids = unit.get("concept_ids")
        if (
            not isinstance(evidence_id, str)
            or not evidence_id
            or not isinstance(concept_id, str)
            or not isinstance(concept_ids, list)
            or concept_id not in concept_ids
        ):
            raise RuntimeError("answered diagnostic evidence relationship is invalid")
        evidence = self.connection.execute(
            """
            SELECT session_id, concept_id, evidence_type, weight
            FROM mastery_evidence
            WHERE id = ?
            """,
            (evidence_id,),
        ).fetchone()
        if (
            evidence is None
            or evidence["session_id"] != checkpoint.get("session_id")
            or evidence["concept_id"] != concept_id
            or evidence["evidence_type"] != ResponseType.USER_REPORT.value
            or float(evidence["weight"]) != 0.0
        ):
            raise RuntimeError("answered diagnostic evidence relationship is invalid")


def _first_ready_unit(state: Any, *, require_current_none: bool) -> dict[str, Any]:
    if require_current_none and state.current_unit_id is not None:
        raise DiagnosticConflictError("study session already has a current unit")
    units = state.plan["units"]
    if not units or units[0]["ordinal"] != 0 or units[0]["status"] != "ready":
        raise DiagnosticConflictError("study session first unit is not ready")
    return units[0]


def _effective_session_status(session: dict[str, Any]) -> str:
    """Resolve a paused session to the exact stage it can resume."""

    status = session.get("status")
    resume_from = session.get("resume_from_status")
    if status == "paused":
        if not isinstance(resume_from, str):
            raise RuntimeError("paused study session has no resumable state")
        return resume_from
    if resume_from is not None:
        raise RuntimeError("active study session has an unexpected resume state")
    if not isinstance(status, str):
        raise RuntimeError("study session status is invalid")
    return status


def _prompt(unit: dict[str, Any]) -> str:
    title = _display_text(unit.get("title"), "unit title", maximum=500)
    objective = _display_text(unit.get("objective"), "unit objective", maximum=5_000)
    return (
        f"Before beginning {title}, briefly describe what you already know about this goal: "
        f"{objective} Also choose one self-assessment: not_yet, partial, or confident. "
        "This is a prior-knowledge reflection, not a scored question."
    )


def _display_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"stored {label} is invalid")
    return value.strip()


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty identifier")
    return value


def _idempotency_key(value: object) -> str:
    key = _identifier(value, "idempotency_key")
    if len(key) < 16 or any(
        character
        not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
        for character in key
    ):
        raise ValueError("idempotency_key is invalid")
    return key


def _revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_revision must be a non-negative integer")
    return value


def _response(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8_000:
        raise ValueError("diagnostic response must be 1 to 8000 characters")
    return value


def _self_assessment(value: object) -> str:
    if value not in {"not_yet", "partial", "confident"}:
        raise ValueError("self_assessment is invalid")
    return str(value)


def _assessment_correctness(value: str) -> float:
    return {"not_yet": 0.0, "partial": 0.5, "confident": 1.0}[value]


def _fingerprint(*values: object) -> str:
    encoded = "\x1f".join(str(value) for value in values).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _checkpoint_id(session_id: str, key: str) -> str:
    return f"diagnostic:{uuid.uuid5(_NAMESPACE, f'{session_id}:begin:{key}')}"


def _evidence_id(checkpoint_id: str, key: str) -> str:
    return (
        f"diagnostic-evidence:{uuid.uuid5(_NAMESPACE, f'{checkpoint_id}:answer:{key}')}"
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "DiagnosticConflictError",
    "DiagnosticNotFoundError",
    "DiagnosticReadResult",
    "DiagnosticProgressionResult",
    "DiagnosticProgressionService",
]
