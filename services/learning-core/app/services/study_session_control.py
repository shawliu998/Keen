"""Idempotent pause and resume commands for one persisted Study Session."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.learning import transition_study_state
from app.repositories import write_scope
from app.repositories.study_repository import StudyRepository

StudySessionCommand = Literal["pause", "resume"]
StudySessionCommandOutcome = Literal["applied", "replayed"]


class StudySessionControlNotFoundError(LookupError):
    pass


class StudySessionControlConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StudySessionControlResult:
    outcome: StudySessionCommandOutcome
    command: StudySessionCommand
    course_id: str
    session: dict[str, Any]


class StudySessionControlService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def apply(
        self,
        *,
        command: StudySessionCommand,
        course_id: str,
        session_id: str,
        expected_revision: int,
        idempotency_key: str,
        now: datetime,
    ) -> StudySessionControlResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        idempotency_key = _idempotency_key(idempotency_key)
        if command not in {"pause", "resume"}:
            raise ValueError("invalid study session command")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")
        timestamp = _utc(now).isoformat()
        with write_scope(self.connection, commit=True):
            repository = StudyRepository(self.connection)
            session = repository.get_session(session_id)
            if session is None or session["course_id"] != course_id:
                raise StudySessionControlNotFoundError("study session not found")
            replay = repository.get_status_command(
                session_id=session_id, idempotency_key=idempotency_key
            )
            if replay is not None:
                if (
                    replay.get("command") != command
                    or replay.get("expected_revision") != expected_revision
                ):
                    raise StudySessionControlConflictError(
                        "study session command idempotency key was reused"
                    )
                return StudySessionControlResult(
                    "replayed", command, course_id, session
                )
            if int(session["revision"]) != expected_revision:
                raise StudySessionControlConflictError(
                    "study session revision conflict"
                )
            status = str(session["status"])
            if command == "pause":
                if status == "paused":
                    raise StudySessionControlConflictError(
                        "study session is already paused"
                    )
                if status in {"completed", "cancelled", "failed"}:
                    raise StudySessionControlConflictError(
                        "terminal study session cannot be paused"
                    )
                transition_study_state(status, "paused")
                target = "paused"
            else:
                if status != "paused":
                    raise StudySessionControlConflictError(
                        "study session is not paused"
                    )
                target = session.get("resume_from_status")
                if not isinstance(target, str):
                    raise RuntimeError("paused study session has no resume state")
                transition_study_state("paused", target, resume_from_status=target)
            try:
                updated = repository.transition_session(
                    session_id,
                    status=target,
                    expected_revision=expected_revision,
                    command=command,
                    idempotency_key=idempotency_key,
                    updated_at=timestamp,
                    commit=False,
                )
            except (RuntimeError, ValueError) as error:
                raise StudySessionControlConflictError(str(error)) from error
            return StudySessionControlResult("applied", command, course_id, updated)


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty identifier")
    return value


def _idempotency_key(value: object) -> str:
    key = _identifier(value, "idempotency_key")
    if len(key) < 16 or any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
        for character in key
    ):
        raise ValueError("invalid idempotency_key")
    return key


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)
