"""Create one explicit, source-grounded focused-study task and session.

This coordinator is deliberately separate from autonomous recommendation.  A
learner's submitted goal is the retrieval query and durable idempotency
payload; no course-wide candidate or unrelated source fallback is consulted.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.assessment import generate_source_cloze, generate_targeted_practice
from app.document_repository import DocumentRepository
from app.mastery import BktParameters
from app.repositories import write_scope
from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.services.adaptive_study_session import ADAPTIVE_SESSION_POLICY_VERSION


_IDENTITY_NAMESPACE = uuid.UUID("414494af-3044-4da1-915e-1be45286b8f6")
_CONCEPT_NAMESPACE = uuid.UUID("0fd89aa7-e729-40f6-8b80-74de58d5b7c5")
_REQUEST_VERSION = "focused-study-request/1.0.0"
_MAX_EXCERPT_LENGTH = 1_200
_INITIAL_MASTERY = 0.2
_INTENT_TERMS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "course",
        "chapter",
        "compare",
        "define",
        "describe",
        "document",
        "explain",
        "focus",
        "for",
        "from",
        "help",
        "i",
        "in",
        "it",
        "its",
        "learn",
        "learning",
        "lesson",
        "lecture",
        "material",
        "materials",
        "my",
        "me",
        "mine",
        "notes",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "please",
        "review",
        "recall",
        "section",
        "short",
        "source",
        "study",
        "summarize",
        "teach",
        "test",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "they",
        "this",
        "then",
        "textbook",
        "to",
        "understand",
        "use",
        "using",
        "want",
        "we",
        "with",
        "you",
        "your",
        "yours",
    }
)

FocusedStudyOutcome = Literal["session_created", "replayed", "blocked"]
FocusedStudyBlockedReason = Literal["course_not_found", "no_matching_indexed_source"]
_StudyMaterial = tuple[dict[str, Any], str, str]


class FocusedStudyConflictError(ValueError):
    """A stable request identity was reused for a different payload."""


@dataclass(frozen=True, slots=True)
class FocusedStudyRequestResult:
    outcome: FocusedStudyOutcome
    course_id: str
    task: dict[str, Any] | None
    session: dict[str, Any] | None
    plan: dict[str, Any] | None
    blocked_reason: FocusedStudyBlockedReason | None = None


class FocusedStudyRequestService:
    """Atomically create or reconcile one explicit focused-study request."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def start(
        self,
        *,
        course_id: str,
        goal: str,
        client_request_id: str,
        idempotency_key: str,
        now: datetime,
    ) -> FocusedStudyRequestResult:
        scoped_course_id = _identifier(course_id, "course_id")
        scoped_goal = normalize_goal(goal)
        scoped_client_id = _identifier(client_request_id, "client_request_id")
        scoped_key = _identifier(idempotency_key, "idempotency_key")
        current_time = _utc(now)
        fingerprint = _payload_fingerprint(
            course_id=scoped_course_id,
            goal=scoped_goal,
            client_request_id=scoped_client_id,
        )
        task_id = _stable_id("focused-task", scoped_client_id)
        task_key = f"focused-study:{scoped_key}"

        # BEGIN IMMEDIATE serializes both identity lookups and the composed
        # task/session/plan write. A cancelled transport can therefore be
        # reconciled by retrying either stable identity after restart.
        with write_scope(self.connection, commit=True):
            identity = self._identity_record(
                client_request_id=scoped_client_id,
                idempotency_key=scoped_key,
            )
            if identity is not None:
                if any(
                    identity[key] != value
                    for key, value in (
                        ("course_id", scoped_course_id),
                        ("goal", scoped_goal),
                        ("payload_fingerprint", fingerprint),
                    )
                ):
                    raise FocusedStudyConflictError("focused-study identity was reused")
                if identity["outcome"] == "session_created":
                    replay = self._replay(
                        task=TaskRepository(self.connection).get(identity["task_id"]),
                        course_id=scoped_course_id,
                        goal=scoped_goal,
                        client_request_id=scoped_client_id,
                        fingerprint=fingerprint,
                    )
                    if (
                        replay.session is None
                        or replay.plan is None
                        or replay.session["id"] != identity["session_id"]
                        or replay.plan["id"] != identity["plan_id"]
                    ):
                        raise RuntimeError(
                            "focused study identity links are inconsistent"
                        )
                    return replay
            else:
                # Safely adopt focused work created by the immediately prior
                # implementation before migration 030 existed. No new domain
                # work is synthesized during this compatibility path.
                by_key = self._task_by_key(task_key)
                by_client = TaskRepository(self.connection).get(task_id)
                if by_key is not None or by_client is not None:
                    if (
                        by_key is None
                        or by_client is None
                        or by_key["id"] != by_client["id"]
                    ):
                        raise FocusedStudyConflictError(
                            "focused-study identities disagree"
                        )
                    replay = self._replay(
                        task=by_key or by_client,
                        course_id=scoped_course_id,
                        goal=scoped_goal,
                        client_request_id=scoped_client_id,
                        fingerprint=fingerprint,
                    )
                    if (
                        replay.task is None
                        or replay.session is None
                        or replay.plan is None
                    ):
                        raise RuntimeError("focused study legacy replay is incomplete")
                    self._insert_identity(
                        client_request_id=scoped_client_id,
                        idempotency_key=scoped_key,
                        fingerprint=fingerprint,
                        course_id=scoped_course_id,
                        goal=scoped_goal,
                        outcome="session_created",
                        now=current_time,
                        task_id=replay.task["id"],
                        session_id=replay.session["id"],
                        plan_id=replay.plan["id"],
                    )
                    return replay
                self._insert_identity(
                    client_request_id=scoped_client_id,
                    idempotency_key=scoped_key,
                    fingerprint=fingerprint,
                    course_id=scoped_course_id,
                    goal=scoped_goal,
                    outcome="blocked",
                    now=current_time,
                )

            if (
                self.connection.execute(
                    "SELECT 1 FROM courses WHERE id = ?", (scoped_course_id,)
                ).fetchone()
                is None
            ):
                return _blocked(scoped_course_id, "course_not_found")

            materials = self._matching_materials(
                course_id=scoped_course_id, goal=scoped_goal
            )
            if not materials:
                return _blocked(scoped_course_id, "no_matching_indexed_source")

            source_chunk_ids = list(
                dict.fromkeys(str(chunk["chunk_id"]) for chunk, _, _ in materials)
            )
            concept_id = self._ensure_goal_concept(
                course_id=scoped_course_id,
                goal=scoped_goal,
                now=current_time,
            )
            marker: dict[str, Any] = {
                "version": _REQUEST_VERSION,
                "client_request_id": scoped_client_id,
                "payload_fingerprint": fingerprint,
                "goal": scoped_goal,
                "source_chunk_ids": source_chunk_ids,
            }
            task, created = TaskRepository(self.connection).create_task(
                task_id=task_id,
                course_id=scoped_course_id,
                concept_id=concept_id,
                title=_bounded(f"Study: {scoped_goal}", 500),
                reason=scoped_goal,
                due_at=current_time.isoformat(),
                estimated_minutes=25,
                source_type="manual",
                source_id=None,
                priority_score=1.0,
                priority_components={"focused_study_request": marker},
                recommended_reason="Explicit focused study requested by the learner.",
                scheduled_for=current_time.isoformat(),
                idempotency_key=task_key,
                created_at=current_time.isoformat(),
                commit=False,
            )
            if not created:  # pragma: no cover - protected by locked lookups
                raise RuntimeError("focused study task identity appeared concurrently")

            session_id = _stable_id("focused-session", scoped_client_id)
            plan_id = _stable_id("focused-plan", scoped_client_id)
            repository = StudyRepository(self.connection)
            session = repository.create_session(
                session_id=session_id,
                course_id=scoped_course_id,
                originating_task_id=task_id,
                title=_bounded(f"Study: {scoped_goal}", 500),
                mode="study",
                goal=scoped_goal,
                estimated_minutes=25,
                goal_scope={
                    "kind": "focused_study",
                    "client_request_id": scoped_client_id,
                    "payload_fingerprint": fingerprint,
                    "source_chunk_ids": source_chunk_ids,
                },
                adaptive_policy_version=ADAPTIVE_SESSION_POLICY_VERSION,
                created_at=current_time.isoformat(),
                commit=False,
            )
            plan = repository.save_plan(
                plan_id=plan_id,
                session_id=session_id,
                version=1,
                rationale=(
                    "The units use lexical goal matches that support deterministic "
                    "Recall and distinct Practice prompts."
                ),
                units=_units(
                    session_id=session_id,
                    goal=scoped_goal,
                    concept_id=concept_id,
                    materials=materials,
                ),
                created_at=current_time.isoformat(),
                commit=False,
            )
            session = repository.transition_session(
                session_id,
                status="goal_confirmation",
                expected_revision=int(session["revision"]),
                updated_at=current_time.isoformat(),
                commit=False,
            )
            updated = self.connection.execute(
                """
                UPDATE focused_study_request_identities
                SET outcome = 'session_created', task_id = ?, session_id = ?,
                    plan_id = ?, updated_at = ?
                WHERE client_request_id = ? AND idempotency_key = ?
                  AND payload_fingerprint = ? AND outcome = 'blocked'
                  AND task_id IS NULL AND session_id IS NULL AND plan_id IS NULL
                """,
                (
                    task["id"],
                    session["id"],
                    plan["id"],
                    current_time.isoformat(),
                    scoped_client_id,
                    scoped_key,
                    fingerprint,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("focused study identity could not be finalized")
            return FocusedStudyRequestResult(
                outcome="session_created",
                course_id=scoped_course_id,
                task=task,
                session=session,
                plan=plan,
            )

    def _identity_record(
        self, *, client_request_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        by_client = self.connection.execute(
            "SELECT * FROM focused_study_request_identities WHERE client_request_id = ?",
            (client_request_id,),
        ).fetchone()
        by_key = self.connection.execute(
            "SELECT * FROM focused_study_request_identities WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if by_client is None and by_key is None:
            return None
        if (
            by_client is None
            or by_key is None
            or by_client["client_request_id"] != by_key["client_request_id"]
            or by_client["idempotency_key"] != by_key["idempotency_key"]
            or by_client["client_request_id"] != client_request_id
            or by_client["idempotency_key"] != idempotency_key
        ):
            raise FocusedStudyConflictError("focused-study identities disagree")
        return dict(by_client)

    def _insert_identity(
        self,
        *,
        client_request_id: str,
        idempotency_key: str,
        fingerprint: str,
        course_id: str,
        goal: str,
        outcome: Literal["blocked", "session_created"],
        now: datetime,
        task_id: str | None = None,
        session_id: str | None = None,
        plan_id: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO focused_study_request_identities
                (client_request_id, idempotency_key, payload_fingerprint,
                 course_id, goal, outcome, task_id, session_id, plan_id,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_request_id,
                idempotency_key,
                fingerprint,
                course_id,
                goal,
                outcome,
                task_id,
                session_id,
                plan_id,
                now.isoformat(),
                now.isoformat(),
            ),
        )

    def _task_by_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT id FROM study_tasks WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return TaskRepository(self.connection).get(str(row["id"])) if row else None

    def _replay(
        self,
        *,
        task: dict[str, Any] | None,
        course_id: str,
        goal: str,
        client_request_id: str,
        fingerprint: str,
    ) -> FocusedStudyRequestResult:
        if task is None:  # pragma: no cover - caller guarantees one identity
            raise RuntimeError("focused study replay task is missing")
        components = task.get("priority_components")
        marker = (
            components.get("focused_study_request")
            if isinstance(components, dict)
            else None
        )
        if (
            not isinstance(marker, dict)
            or any(
                marker.get(key) != value
                for key, value in (
                    ("version", _REQUEST_VERSION),
                    ("client_request_id", client_request_id),
                    ("payload_fingerprint", fingerprint),
                    ("goal", goal),
                )
            )
            or task.get("course_id") != course_id
        ):
            raise FocusedStudyConflictError("focused-study identity was reused")

        row = self.connection.execute(
            "SELECT id FROM study_sessions WHERE originating_task_id = ?",
            (task["id"],),
        ).fetchone()
        if row is None:
            raise RuntimeError("focused study replay session is unavailable")
        repository = StudyRepository(self.connection)
        session = repository.get_session(str(row["id"]))
        plan = repository.get_current_or_latest_plan(str(row["id"]))
        if session is None or plan is None:
            raise RuntimeError("focused study replay is incomplete")
        expected_chunks = marker.get("source_chunk_ids")
        goal_scope = session.get("goal_scope")
        plan_chunks = list(
            dict.fromkeys(
                str(chunk_id)
                for unit in plan["units"]
                for chunk_id in unit["source_chunk_ids"]
            )
        )
        if (
            session.get("course_id") != course_id
            or session.get("goal") != goal
            or session.get("originating_task_id") != task.get("id")
            or not isinstance(goal_scope, dict)
            or goal_scope.get("source_chunk_ids") != expected_chunks
            or plan_chunks != expected_chunks
        ):
            raise RuntimeError("focused study replay relationships are inconsistent")
        return FocusedStudyRequestResult(
            outcome="replayed",
            course_id=course_id,
            task=task,
            session=session,
            plan=plan,
        )

    def _matching_materials(self, *, course_id: str, goal: str) -> list[_StudyMaterial]:
        query = _retrieval_query(goal)
        if query is None:
            return []
        try:
            candidates = DocumentRepository(self.connection).search(
                query, course_id=course_id, limit=100
            )
        except ValueError:
            return []
        candidates_in_scope: list[dict[str, Any]] = []
        for candidate in candidates:
            if not self._is_current_course_chunk(
                course_id=course_id, chunk_id=str(candidate["chunk_id"])
            ):
                continue
            text = str(candidate["text"]).strip()
            if text:
                candidates_in_scope.append({**candidate, "text": text})

        concept_name = _concept_name(goal)
        selected: list[_StudyMaterial] = []
        for candidate in candidates_in_scope:
            excerpt = str(candidate["text"])[:_MAX_EXCERPT_LENGTH].strip()
            if _supports_recall_and_practice(excerpt, concept_name=concept_name):
                selected.append((candidate, excerpt, ""))
            if len(selected) == 2:
                return selected

        # Preserve the bounded one-chunk/two-unit behavior only when each exact
        # half can independently generate both Recall and a distinct Practice.
        for candidate in candidates_in_scope:
            excerpt = str(candidate["text"])[:_MAX_EXCERPT_LENGTH]
            halves = _supported_excerpt_halves(excerpt, concept_name=concept_name)
            if halves is not None:
                first, second = halves
                return [
                    (candidate, first, " (Part 1)"),
                    (candidate, second, " (Part 2)"),
                ]
        return []

    def _is_current_course_chunk(self, *, course_id: str, chunk_id: str) -> bool:
        return (
            self.connection.execute(
                """
            SELECT 1
            FROM document_chunks ch
            JOIN documents d ON d.id = ch.document_id
            JOIN document_versions v ON v.id = ch.version_id
            JOIN course_documents cd ON cd.document_id = d.id
            WHERE ch.id = ? AND cd.course_id = ? AND d.status = 'indexed'
              AND v.version_number = (
                  SELECT MAX(current.version_number)
                  FROM document_versions current
                  WHERE current.document_id = d.id
              )
            """,
                (chunk_id, course_id),
            ).fetchone()
            is not None
        )

    def _ensure_goal_concept(self, *, course_id: str, goal: str, now: datetime) -> str:
        concept_name = _concept_name(goal)
        row = self.connection.execute(
            "SELECT id FROM concepts WHERE course_id = ? AND name = ?",
            (course_id, concept_name),
        ).fetchone()
        if row is None:
            concept_id = "focused-concept-" + str(
                uuid.uuid5(_CONCEPT_NAMESPACE, f"{course_id}\x1f{goal}")
            )
            parameters = BktParameters()
            self.connection.execute(
                """INSERT INTO concepts
                       (id, course_id, name, bkt_slip, bkt_guess, bkt_transit)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    concept_id,
                    course_id,
                    concept_name,
                    parameters.slip,
                    parameters.guess,
                    parameters.transit,
                ),
            )
        else:
            concept_id = str(row["id"])
        mastery = self.connection.execute(
            "SELECT 1 FROM mastery WHERE concept_id = ?", (concept_id,)
        ).fetchone()
        if mastery is None:
            history = self.connection.execute(
                """SELECT 1 WHERE EXISTS (
                       SELECT 1 FROM mastery_events WHERE concept_id = ?
                   ) OR EXISTS (
                       SELECT 1 FROM mastery_evidence WHERE concept_id = ?
                   )""",
                (concept_id, concept_id),
            ).fetchone()
            if history is not None:
                raise RuntimeError("focused concept mastery state is incomplete")
            self.connection.execute(
                """INSERT INTO mastery (concept_id, probability, attempts, updated_at)
                   VALUES (?, ?, 0, ?)""",
                (concept_id, _INITIAL_MASTERY, now.isoformat()),
            )
        return concept_id


def normalize_goal(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("goal must be a string")
    normalized = unicodedata.normalize("NFKC", value)
    if any(unicodedata.category(char).startswith("C") for char in normalized):
        raise ValueError("goal contains unsupported control characters")
    compact = " ".join(normalized.split())
    if not compact or len(compact) > 1_000:
        raise ValueError("goal must contain 1 to 1000 normalized characters")
    return compact


def _retrieval_query(goal: str) -> str | None:
    spans: list[str] = []
    current: list[str] = []
    for character in goal:
        if character.isalnum() or _is_cjk(character):
            current.append(character)
        elif current:
            spans.append("".join(current))
            current = []
    if current:
        spans.append("".join(current))
    terms = [
        cleaned
        for term in spans
        if (cleaned := _clean_query_span(term))
        and cleaned.casefold() not in _INTENT_TERMS
    ]
    return " ".join(dict.fromkeys(terms)) or None


def _clean_query_span(value: str) -> str:
    if not any(_is_cjk(character) for character in value):
        return value
    cleaned = value
    for prefix in ("请帮我解释", "请解释", "解释", "学习", "理解", "复习"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    for suffix in ("课程资料", "课堂笔记", "教材", "笔记"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned


def _units(
    *,
    session_id: str,
    goal: str,
    concept_id: str,
    materials: list[_StudyMaterial],
) -> list[dict[str, Any]]:
    if len(materials) != 2 or any(not content for _, content, _ in materials):
        raise ValueError("matching source cannot form two non-empty study units")
    return [
        {
            "id": f"{session_id}:unit:{ordinal}",
            "title": _bounded(f"Source {ordinal}{part}: {chunk['document_name']}", 500),
            "objective": _bounded(
                f"Use this source excerpt to work toward: {goal}", 5_000
            ),
            "content": content,
            "estimated_minutes": 12 if ordinal == 1 else 13,
            "concept_id": concept_id,
            "concept_ids": [concept_id],
            "source_chunk_ids": [str(chunk["chunk_id"])],
            "status": "ready" if ordinal == 1 else "locked",
        }
        for ordinal, (chunk, content, part) in enumerate(materials, start=1)
    ]


def _supported_excerpt_halves(
    excerpt: str, *, concept_name: str
) -> tuple[str, str] | None:
    """Find the nearest viable whitespace split without cutting a source word."""

    midpoint = len(excerpt) // 2
    boundaries = sorted(
        {
            index
            for index, character in enumerate(excerpt)
            if 0 < index < len(excerpt) - 1 and character.isspace()
        },
        key=lambda index: (abs(index - midpoint), index),
    )
    for split in boundaries:
        first = excerpt[:split].strip()
        second = excerpt[split:].strip()
        if (
            first
            and second
            and all(
                _supports_recall_and_practice(content, concept_name=concept_name)
                for content in (first, second)
            )
        ):
            return first, second
    return None


def _supports_recall_and_practice(source: str, *, concept_name: str) -> bool:
    recall = generate_source_cloze(source, concept=concept_name)
    if recall is None:
        return False
    return (
        generate_targeted_practice(
            source,
            concept=concept_name,
            excluded_answers=recall.accepted_answers,
        )
        is not None
    )


def _blocked(
    course_id: str, reason: FocusedStudyBlockedReason
) -> FocusedStudyRequestResult:
    return FocusedStudyRequestResult(
        outcome="blocked",
        course_id=course_id,
        task=None,
        session=None,
        plan=None,
        blocked_reason=reason,
    )


def _payload_fingerprint(*, course_id: str, goal: str, client_request_id: str) -> str:
    payload = json.dumps(
        {
            "client_request_id": client_request_id,
            "course_id": course_id,
            "goal": goal,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, identity: str) -> str:
    return f"{prefix}-" + str(
        uuid.uuid5(_IDENTITY_NAMESPACE, f"{prefix}\x1f{identity}")
    )


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError(f"{label} must contain 1 to 128 characters")
    return value


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
        or value.utcoffset().total_seconds() != 0
    ):
        raise ValueError("now must be a timezone-aware UTC datetime")
    return value.astimezone(UTC)


def _concept_name(goal: str) -> str:
    topic = _retrieval_query(goal) or "Focused study"
    topic = topic[:1].upper() + topic[1:]
    if len(topic) <= 160:
        return topic
    digest = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:12]
    return f"{topic[:144].rstrip()} [{digest}]"


def _bounded(value: str, limit: int) -> str:
    return value[:limit].strip() or "Focused study"


def _is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return any(
        start <= codepoint <= end
        for start, end in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x20000, 0x2FA1F),
            (0x3040, 0x30FF),
            (0xAC00, 0xD7AF),
        )
    )


__all__ = [
    "FocusedStudyConflictError",
    "FocusedStudyRequestResult",
    "FocusedStudyRequestService",
    "normalize_goal",
]
