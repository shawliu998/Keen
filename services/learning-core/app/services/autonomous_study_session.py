"""Turn one persisted autonomous task into source-grounded study work.

This is intentionally a local composition service.  It never invents source
text, learner evidence, mastery, answers, or completion.  A task either
resumes the session it already names, resumes the unique session it created,
or creates a small two-unit plan from indexed chunks in the same course.
"""

from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.repositories import write_scope
from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.services.adaptive_study_session import ADAPTIVE_SESSION_POLICY_VERSION


_SESSION_NAMESPACE = uuid.UUID("7e8742e0-99b1-4a4e-924f-e83a2946f897")
_AUTONOMOUS_RECOMMENDATION_VERSION = "autonomous-recommendation/1.0.0"
_TERMINAL_SESSION_STATUSES = frozenset({"completed", "cancelled", "failed"})
_MAX_SOURCE_EXCERPT_LENGTH = 1_200

AutonomousSessionOutcome = Literal["session_created", "resumed", "blocked"]
AutonomousSessionBlockedReason = Literal[
    "task_not_found",
    "task_outside_course",
    "task_not_actionable",
    "task_not_autonomous",
    "task_missing_concept",
    "source_session_unavailable",
    "originating_session_terminal",
    "no_indexed_source",
]


@dataclass(frozen=True, slots=True)
class AutonomousStudySessionResult:
    outcome: AutonomousSessionOutcome
    course_id: str
    task: dict[str, Any] | None
    session: dict[str, Any] | None
    plan: dict[str, Any] | None
    blocked_reason: AutonomousSessionBlockedReason | None = None

    @property
    def created(self) -> bool:
        return self.outcome == "session_created"

    @property
    def resumed(self) -> bool:
        return self.outcome == "resumed"


class AutonomousStudySessionService:
    """Create or recover exactly one study session for an autonomous task."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def start_or_resume(
        self, *, course_id: str, task_id: str, goal: str | None = None, now: datetime
    ) -> AutonomousStudySessionResult:
        scoped_course_id = _course_id(course_id)
        current_time = _utc(now)
        scoped_task_id = _task_id(task_id)
        scoped_goal = _user_goal(goal)

        # The task check, link lookup, source lookup, and creation share one
        # write transaction.  The partial unique index on originating_task_id
        # is the durable idempotency boundary across sidecars and restarts.
        with write_scope(self.connection, commit=True):
            task = TaskRepository(self.connection).get(scoped_task_id)
            blocked = _task_block(
                task,
                course_id=scoped_course_id,
                user_initiated=scoped_goal is not None,
            )
            if blocked is not None:
                # A caller scoped to another course must not receive the
                # foreign task payload merely to explain the denial.
                visible_task = None if blocked == "task_outside_course" else task
                return _blocked(scoped_course_id, visible_task, blocked)
            if task is None:  # pragma: no cover - guarded by _task_block
                return _blocked(scoped_course_id, None, "task_not_found")

            study_repository = StudyRepository(self.connection)
            if task["source_type"] == "study_session":
                source = self._source_session(
                    course_id=scoped_course_id, task=task, repository=study_repository
                )
                if source is None:
                    return _blocked(
                        scoped_course_id, task, "source_session_unavailable"
                    )
                return AutonomousStudySessionResult(
                    outcome="resumed",
                    course_id=scoped_course_id,
                    task=task,
                    session=source,
                    plan=None,
                )

            existing = self._originating_session(
                course_id=scoped_course_id,
                task_id=scoped_task_id,
                repository=study_repository,
            )
            if existing is not None:
                if existing["status"] in _TERMINAL_SESSION_STATUSES:
                    return _blocked(
                        scoped_course_id, task, "originating_session_terminal"
                    )
                return AutonomousStudySessionResult(
                    outcome="resumed",
                    course_id=scoped_course_id,
                    task=task,
                    session=existing,
                    plan=None,
                )

            concept = self._task_concept(course_id=scoped_course_id, task=task)
            if concept is None:
                return _blocked(scoped_course_id, task, "task_missing_concept")
            chunks = self._source_chunks(
                course_id=scoped_course_id, concept_name=str(concept["name"])
            )
            if not chunks:
                return _blocked(scoped_course_id, task, "no_indexed_source")
            materials = _source_materials(chunks)
            if materials is None:
                return _blocked(scoped_course_id, task, "no_indexed_source")

            session_id = _session_id(scoped_task_id)
            plan_id = _plan_id(scoped_task_id)
            units = _units(
                task=task,
                concept_id=str(concept["id"]),
                concept_name=str(concept["name"]),
                materials=materials,
            )
            session = study_repository.create_session(
                session_id=session_id,
                course_id=scoped_course_id,
                originating_task_id=scoped_task_id,
                title=_session_title(task)
                if scoped_goal is None
                else _session_title_for_goal(scoped_goal),
                mode="study",
                goal=_goal(task) if scoped_goal is None else scoped_goal,
                estimated_minutes=_session_minutes(task),
                goal_scope={
                    "originating_task_id": scoped_task_id,
                    "concepts": [str(concept["id"])],
                    "task_source_type": str(task["source_type"]),
                },
                adaptive_policy_version=ADAPTIVE_SESSION_POLICY_VERSION,
                created_at=current_time.isoformat(),
                commit=False,
            )
            plan = study_repository.save_plan(
                plan_id=plan_id,
                session_id=session_id,
                version=1,
                rationale=(
                    "Two bounded units cite indexed course source chunks that "
                    "contain the persisted concept label."
                ),
                units=units,
                created_at=current_time.isoformat(),
                commit=False,
            )
            session = study_repository.transition_session(
                session_id,
                status="goal_confirmation",
                expected_revision=int(session["revision"]),
                updated_at=current_time.isoformat(),
                commit=False,
            )
            return AutonomousStudySessionResult(
                outcome="session_created",
                course_id=scoped_course_id,
                task=task,
                session=session,
                plan=plan,
            )

    def _originating_session(
        self, *, course_id: str, task_id: str, repository: StudyRepository
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT id FROM study_sessions WHERE originating_task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        session = repository.get_session(str(row["id"]))
        if session is None:
            raise RuntimeError("originating study session disappeared")
        # Migration 022 enforces this relationship in healthy databases.  Keep
        # the service boundary defensive so a damaged database can never turn
        # a same-id lookup into cross-course session disclosure.
        if session.get("course_id") != course_id:
            raise RuntimeError("originating study session is outside the course")
        return session

    def _source_session(
        self,
        *,
        course_id: str,
        task: dict[str, Any],
        repository: StudyRepository,
    ) -> dict[str, Any] | None:
        source_id = task.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            return None
        session = repository.get_session(source_id)
        if (
            session is None
            or session["course_id"] != course_id
            or session["status"] in _TERMINAL_SESSION_STATUSES
        ):
            return None
        return session

    def _task_concept(
        self, *, course_id: str, task: dict[str, Any]
    ) -> sqlite3.Row | None:
        concept_id = task.get("concept_id")
        if not isinstance(concept_id, str) or not concept_id:
            return None
        return self.connection.execute(
            "SELECT id, name FROM concepts WHERE id = ? AND course_id = ?",
            (concept_id, course_id),
        ).fetchone()

    def _source_chunks(self, *, course_id: str, concept_name: str) -> list[sqlite3.Row]:
        # A weak-concept task may update mastery only when its learning material
        # has a directly verifiable relationship to that persisted concept.
        # Never fall back to unrelated chunks merely because they share a course.
        return list(
            self.connection.execute(
                """
                SELECT ch.id, ch.content, d.name, ch.page_number, ch.ordinal
                FROM document_chunks ch
                JOIN documents d ON d.id = ch.document_id
                JOIN document_versions v
                  ON v.id = ch.version_id AND v.document_id = d.id
                JOIN course_documents cd ON cd.document_id = d.id
                WHERE cd.course_id = ?
                  AND d.status = 'indexed'
                  AND length(ch.content) > 0
                  AND instr(lower(ch.content), lower(?)) > 0
                  AND v.version_number = (
                      SELECT MAX(current.version_number)
                      FROM document_versions current
                      WHERE current.document_id = d.id
                  )
                ORDER BY d.id, ch.ordinal, ch.id
                LIMIT 2
                """,
                (course_id, concept_name),
            ).fetchall()
        )


def _task_block(
    task: dict[str, Any] | None, *, course_id: str, user_initiated: bool = False
) -> AutonomousSessionBlockedReason | None:
    if task is None:
        return "task_not_found"
    if task["course_id"] != course_id:
        return "task_outside_course"
    if task["status"] not in {"upcoming", "overdue"}:
        return "task_not_actionable"
    components = task.get("priority_components")
    if (
        not isinstance(components, dict)
        or components.get("recommendation_algorithm_version")
        != _AUTONOMOUS_RECOMMENDATION_VERSION
    ) and not user_initiated:
        return "task_not_autonomous"
    return None


def _blocked(
    course_id: str,
    task: dict[str, Any] | None,
    reason: AutonomousSessionBlockedReason,
) -> AutonomousStudySessionResult:
    return AutonomousStudySessionResult(
        outcome="blocked",
        course_id=course_id,
        task=task,
        session=None,
        plan=None,
        blocked_reason=reason,
    )


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
        or value.utcoffset().total_seconds() != 0
    ):
        raise ValueError("now must be a timezone-aware UTC datetime")
    return value.astimezone(UTC)


def _course_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("course_id must be a non-empty string")
    return value.strip()


def _task_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 128:
        raise ValueError("task_id must be a non-empty string up to 128 characters")
    return value.strip()


def _user_goal(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("goal must be a string when provided")
    normalized = value.strip()
    if not normalized or len(normalized) > 1_000:
        raise ValueError("goal must contain 1 to 1000 characters")
    return normalized


def _session_id(task_id: str) -> str:
    return "autonomous-session-" + str(uuid.uuid5(_SESSION_NAMESPACE, task_id))


def _plan_id(task_id: str) -> str:
    return "autonomous-plan-" + str(uuid.uuid5(_SESSION_NAMESPACE, task_id))


def _units(
    *,
    task: dict[str, Any],
    concept_id: str,
    concept_name: str,
    materials: list[tuple[sqlite3.Row, str, str]],
) -> list[dict[str, Any]]:
    total = _session_minutes(task)
    first_minutes = max(1, total // 2)
    second_minutes = max(1, total - first_minutes)
    units: list[dict[str, Any]] = []
    for ordinal, (chunk, content, part) in enumerate(materials, start=1):
        label = _label(str(chunk["name"]), fallback="indexed source")
        units.append(
            {
                "id": f"{_session_id(str(task['id']))}:unit:{ordinal}",
                "title": _bounded(f"Source {ordinal}{part}: {label}", limit=500),
                "objective": _bounded(
                    f"Read the cited source excerpt for {_label(concept_name, fallback='this concept')}.",
                    limit=5000,
                ),
                "content": content,
                "estimated_minutes": first_minutes if ordinal == 1 else second_minutes,
                "concept_id": concept_id,
                "concept_ids": [concept_id],
                "source_chunk_ids": [str(chunk["id"])],
                "status": "ready" if ordinal == 1 else "locked",
            }
        )
    return units


def _source_materials(
    chunks: list[sqlite3.Row],
) -> list[tuple[sqlite3.Row, str, str]] | None:
    """Return two non-empty excerpts without synthesizing any source text."""

    if len(chunks) >= 2:
        excerpts = [
            str(chunk["content"])[:_MAX_SOURCE_EXCERPT_LENGTH].strip()
            for chunk in chunks[:2]
        ]
        if not all(excerpts):
            return None
        return [(chunks[0], excerpts[0], ""), (chunks[1], excerpts[1], "")]

    chunk = chunks[0]
    excerpt = str(chunk["content"])[:_MAX_SOURCE_EXCERPT_LENGTH]
    if len(excerpt) < 2:
        return None
    split_at = len(excerpt) // 2
    first = excerpt[:split_at].strip()
    second = excerpt[split_at:].strip()
    if not first or not second:
        return None
    return [(chunk, first, " (Part 1)"), (chunk, second, " (Part 2)")]


def _session_minutes(task: dict[str, Any]) -> int:
    minutes = int(task["estimated_minutes"])
    return min(max(minutes, 1), 1440)


def _session_title(task: dict[str, Any]) -> str:
    return _bounded(_label(str(task["title"]), fallback="Recommended study"), limit=500)


def _session_title_for_goal(goal: str) -> str:
    return _bounded(f"Study: {_label(goal, fallback='guided study')}", limit=500)


def _goal(task: dict[str, Any]) -> str:
    return _bounded(
        _label(str(task["reason"]), fallback="Work through the cited course source."),
        limit=5000,
    )


def _label(value: str, *, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    compact = " ".join(normalized.split())
    if not compact or any(
        unicodedata.category(char).startswith("C") for char in compact
    ):
        return fallback
    return compact


def _bounded(value: str, *, limit: int) -> str:
    return value[:limit] or "source"
