"""Persist one source-grounded active-recall question and its evidence.

This is intentionally a local, deterministic composition service.  It keeps
the hidden fill-blank answer in the assessment tables, while every public
result contains only a prompt, status, and post-submission grade metadata.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.assessment import (
    SOURCE_CLOZE_GENERATOR_VERSION,
    FillBlankNormalization,
    ObjectiveItemType,
    generate_source_cloze,
    grade_objective_answer,
)
from app.learning import transition_study_state
from app.mastery import BktParameters
from app.mastery_evidence import (
    MasteryEvidence,
    ResponseType,
    calculate_evidence_weight,
    update_mastery_from_evidence,
)
from app.repositories import load_json, write_scope
from app.repositories.active_recall_repository import ActiveRecallRepository
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.study_repository import StudyRepository
from app.services.study_session_read import StudySessionReadService
from app.services.adaptive_study_session import AdaptiveStudySessionService


_NAMESPACE = uuid.UUID("9f749ee3-2d93-4aa8-8256-88b7cb763d82")
_CHECKPOINT_RESPONSE = "Objective response recorded."
_FILL_BLANK_POLICY = FillBlankNormalization()

ActiveRecallOutcome = Literal["applied", "replayed"]
ActiveRecallReadOutcome = Literal["not_started", "pending", "answered", "cancelled"]


class ActiveRecallNotFoundError(LookupError):
    """The scoped session or active-recall run does not exist."""


class ActiveRecallConflictError(RuntimeError):
    """A healthy session cannot accept the requested active-recall action."""


@dataclass(frozen=True, slots=True)
class ActiveRecallProgressionResult:
    outcome: ActiveRecallOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any]
    checkpoint: dict[str, Any]
    current_unit: dict[str, Any] | None
    run: dict[str, Any]
    grade: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ActiveRecallReadResult:
    outcome: ActiveRecallReadOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any]
    checkpoint: dict[str, Any] | None
    current_unit: dict[str, Any] | None
    run: dict[str, Any] | None
    grade: dict[str, Any] | None = None


class ActiveRecallProgressionService:
    """Create and score the first unit's deterministic active-recall item.

    Each write is one ``BEGIN IMMEDIATE`` transaction.  The flow intentionally
    does not touch FSRS tables; it records a separate weighted-BKT mastery
    event from an objective active-recall observation.
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
    ) -> ActiveRecallProgressionResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        expected_revision = _revision(expected_revision)
        idempotency_key = _idempotency_key(idempotency_key)
        timestamp = _utc(now).isoformat()
        with write_scope(self.connection, commit=True):
            self._require_scoped_session(course_id=course_id, session_id=session_id)
            state = self._read(course_id=course_id, session_id=session_id)
            ledger = ActiveRecallRepository(self.connection)
            prior = ledger.find_by_begin_idempotency_key(
                course_id=course_id, session_id=session_id, key=idempotency_key
            )
            if prior is None:
                unit = _current_active_unit(state)
            else:
                unit = next(
                    (
                        candidate
                        for candidate in state.plan["units"]
                        if candidate["id"] == prior["unit_id"]
                    ),
                    None,
                )
                if unit is None:
                    raise RuntimeError("active recall replay unit is outside the plan")
            checkpoint_id = _checkpoint_id(session_id, idempotency_key)
            assessment_id = _assessment_id(session_id, idempotency_key)
            item_id = _item_id(session_id, idempotency_key)
            fingerprint = _fingerprint(
                "begin",
                course_id,
                session_id,
                unit["id"],
                checkpoint_id,
                assessment_id,
                item_id,
                unit["concept_id"],
                ",".join(unit["source_chunk_ids"]),
                SOURCE_CLOZE_GENERATOR_VERSION,
                expected_revision,
            )
            try:
                replay = ledger.replay_begin(
                    course_id=course_id,
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                    payload_fingerprint=fingerprint,
                )
            except ValueError as error:
                raise ActiveRecallConflictError(str(error)) from error
            if replay is not None:
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=replay,
                    outcome="replayed",
                )
            unit = _current_active_unit(state)
            if state.session["status"] == "paused":
                raise ActiveRecallConflictError(
                    "paused study session cannot begin active recall"
                )
            if state.session["status"] != "studying":
                raise ActiveRecallConflictError(
                    "study session is not ready for active recall"
                )
            if int(state.session["revision"]) != expected_revision:
                raise ActiveRecallConflictError("study session revision conflict")

            source = self._source_for_unit(course_id=course_id, unit=unit)
            concept_name = self._concept_name(course_id, str(unit["concept_id"]))
            cloze = generate_source_cloze(source, concept=concept_name)
            if cloze is None:
                raise ActiveRecallConflictError("current unit has no safe source cloze")
            mastery_attempts_before = int(
                self._mastery_parameters(str(unit["concept_id"]))["attempts"]
            )

            study = StudyRepository(self.connection)
            transition_study_state("studying", "checkpoint")
            checkpoint_state = study.transition_session(
                session_id,
                status="checkpoint",
                expected_revision=expected_revision,
                updated_at=timestamp,
                commit=False,
            )
            transition_study_state("checkpoint", "active_recall")
            active_state = study.transition_session(
                session_id,
                status="active_recall",
                expected_revision=int(checkpoint_state["revision"]),
                updated_at=timestamp,
                commit=False,
            )
            checkpoint = study.create_checkpoint(
                checkpoint_id=checkpoint_id,
                session_id=session_id,
                unit_id=str(unit["id"]),
                kind="active_recall",
                prompt=cloze.prompt,
                created_at=timestamp,
                commit=False,
            )
            assessment = AssessmentRepository(self.connection).create_assessment(
                assessment_id=assessment_id,
                course_id=course_id,
                session_id=session_id,
                title="Active recall",
                purpose="checkpoint",
                items=[
                    {
                        "id": item_id,
                        "item_type": "fill_blank",
                        "difficulty": "easy",
                        "prompt": cloze.prompt,
                        "answer_key": {
                            "accepted_answers": list(cloze.accepted_answers)
                        },
                        "max_score": 1.0,
                        "source_chunk_ids": list(unit["source_chunk_ids"]),
                        "concept_id": str(unit["concept_id"]),
                    }
                ],
                created_at=timestamp,
                commit=False,
            )
            AssessmentRepository(self.connection).publish_assessment(
                assessment_id,
                expected_revision=int(assessment["revision"]),
                published_at=timestamp,
                commit=False,
            )
            run, created = ActiveRecallRepository(self.connection).create_run(
                run_id=_run_id(session_id, idempotency_key),
                course_id=course_id,
                session_id=session_id,
                unit_id=str(unit["id"]),
                checkpoint_id=checkpoint_id,
                assessment_id=assessment_id,
                item_id=item_id,
                concept_id=str(unit["concept_id"]),
                source_chunk_ids=list(unit["source_chunk_ids"]),
                mastery_attempts_before=mastery_attempts_before,
                generator_version=cloze.generator_version,
                idempotency_key=idempotency_key,
                payload_fingerprint=fingerprint,
                created_at=timestamp,
                commit=False,
            )
            if not created:  # pragma: no cover - preflight replay owns this path
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=run,
                    outcome="replayed",
                )
            if (
                active_state["status"] != "active_recall"
                or checkpoint["status"] != "pending"
            ):
                raise RuntimeError("active recall begin did not create a pending state")
            return self._result(
                course_id=course_id,
                session_id=session_id,
                run=run,
                outcome="applied",
            )

    def answer(
        self,
        *,
        course_id: str,
        session_id: str,
        run_id: str,
        expected_revision: int,
        idempotency_key: str,
        response: str,
        now: datetime,
    ) -> ActiveRecallProgressionResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        run_id = _identifier(run_id, "run_id")
        expected_revision = _revision(expected_revision)
        idempotency_key = _idempotency_key(idempotency_key)
        response = _response(response)
        normalized_response = _normalize_response(response)
        timestamp = _utc(now).isoformat()
        with write_scope(self.connection, commit=True):
            self._require_scoped_session(course_id=course_id, session_id=session_id)
            ledger = ActiveRecallRepository(self.connection)
            run = ledger.get_run_for_session(
                course_id=course_id, session_id=session_id, run_id=run_id
            )
            if run is None:
                raise ActiveRecallNotFoundError("active recall run not found")
            fingerprint = _fingerprint(
                "answer",
                course_id,
                session_id,
                run_id,
                run["unit_id"],
                run["checkpoint_id"],
                run["assessment_id"],
                run["item_id"],
                expected_revision,
                normalized_response,
                run["generator_version"],
                "objective-grader/1.0.0",
            )
            try:
                replay = ledger.replay_answer(
                    run_id=run_id,
                    course_id=course_id,
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                    payload_fingerprint=fingerprint,
                )
            except ValueError as error:
                raise ActiveRecallConflictError(str(error)) from error
            if replay is not None:
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=replay,
                    outcome="replayed",
                )
            if run["status"] != "pending":
                raise ActiveRecallConflictError("active recall run is not pending")

            state = self._read(course_id=course_id, session_id=session_id)
            if state.session["status"] == "paused":
                raise ActiveRecallConflictError(
                    "paused study session cannot answer active recall"
                )
            if state.session["status"] != "active_recall":
                raise ActiveRecallConflictError(
                    "study session is not awaiting active recall"
                )
            if int(state.session["revision"]) != expected_revision:
                raise ActiveRecallConflictError("study session revision conflict")
            unit = _current_active_unit(state)
            if unit["id"] != run["unit_id"] or unit["concept_id"] != run["concept_id"]:
                raise ActiveRecallConflictError("active recall run is not current")
            checkpoint = self._checkpoint_for_run(run)
            item = self._item_for_run(run)
            expected_answers = _expected_answers(item["answer_key"])
            grade = grade_objective_answer(
                ObjectiveItemType.FILL_BLANK,
                response,
                expected_answers,
                max_score=float(item["max_score"]),
                fill_blank_policy=_FILL_BLANK_POLICY,
            )
            correctness = "correct" if grade.correct else "incorrect"
            attempt_id = _attempt_id(run_id, idempotency_key)
            evaluation_id = _evaluation_id(run_id, idempotency_key)
            evidence_id = _evidence_id(run_id, idempotency_key)
            mastery = self._mastery_parameters(str(run["concept_id"]))
            evidence_input = MasteryEvidence(
                correctness=grade.correctness,
                independence=1.0,
                hint_level=0,
                difficulty=1.0,
                confidence=1.0,
                response_type=ResponseType.ACTIVE_RECALL,
            )
            weight = calculate_evidence_weight(evidence_input)
            if weight <= 0.0:
                raise RuntimeError("active recall evidence must have positive weight")
            update = update_mastery_from_evidence(
                float(mastery["probability"]),
                evidence_input,
                bkt_parameters=BktParameters(
                    slip=float(mastery["bkt_slip"]),
                    guess=float(mastery["bkt_guess"]),
                    transit=float(mastery["bkt_transit"]),
                ),
            )
            assessment = AssessmentRepository(self.connection)
            assessment.start_attempt(
                attempt_id=attempt_id,
                assessment_id=str(run["assessment_id"]),
                item_id=str(run["item_id"]),
                answer=response,
                idempotency_key=f"active-recall-attempt:{run_id}:{idempotency_key}",
                session_id=session_id,
                started_at=timestamp,
                commit=False,
            )
            assessment.grade_attempt(
                evaluation_id=evaluation_id,
                attempt_id=attempt_id,
                item_id=str(run["item_id"]),
                raw_score=grade.score,
                final_score=grade.score,
                correctness=correctness,
                independence=1.0,
                rubric_breakdown={},
                evaluation_source="deterministic",
                feedback="",
                grader_version=grade.grader_version,
                graded_at=timestamp,
                commit=False,
            )
            MasteryRepository(self.connection).record_evidence(
                evidence_id=evidence_id,
                concept_id=str(run["concept_id"]),
                evidence_type=ResponseType.ACTIVE_RECALL.value,
                correctness=grade.correctness,
                independence=1.0,
                hint_level=0,
                weight=weight,
                idempotency_key=f"active-recall-evidence:{run_id}:{idempotency_key}",
                attempt_id=attempt_id,
                session_id=session_id,
                created_at=timestamp,
                commit=False,
            )
            event, _ = MasteryRepository(self.connection).apply_event(
                concept_id=str(run["concept_id"]),
                correct=grade.correct,
                probability_before=update.before,
                probability_after=update.after,
                algorithm=update.algorithm,
                algorithm_version=update.algorithm_version,
                evidence_ids=[evidence_id],
                idempotency_key=f"active-recall-event:{run_id}:{idempotency_key}",
                observed_at=timestamp,
                commit=False,
            )
            self._answer_checkpoint(
                checkpoint_id=str(checkpoint["id"]), answered_at=timestamp
            )
            sealed, applied = ledger.mark_answered(
                run_id=run_id,
                idempotency_key=idempotency_key,
                payload_fingerprint=fingerprint,
                attempt_id=attempt_id,
                evaluation_id=evaluation_id,
                mastery_evidence_id=evidence_id,
                mastery_event_id=int(event["id"]),
                answered_at=timestamp,
                commit=False,
            )
            if not applied:  # pragma: no cover - checked before writes above
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=sealed,
                    outcome="replayed",
                )
            study = StudyRepository(self.connection)
            transition_study_state("active_recall", "practicing")
            practicing = study.transition_session(
                session_id,
                status="practicing",
                expected_revision=expected_revision,
                updated_at=timestamp,
                commit=False,
            )
            if practicing["status"] != "practicing":
                raise RuntimeError("active recall answer did not enter practicing")
            AdaptiveStudySessionService(self.connection).create_after_recall(
                course_id=course_id,
                session_id=session_id,
                unit_id=str(unit["id"]),
                active_recall_run_id=run_id,
                correct=grade.correct,
                created_at=timestamp,
            )
            return self._result(
                course_id=course_id,
                session_id=session_id,
                run=sealed,
                outcome="applied",
                grade=_public_grade(grade),
            )

    def get(self, *, course_id: str, session_id: str) -> ActiveRecallReadResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        self._require_scoped_session(course_id=course_id, session_id=session_id)
        state = self._read(course_id=course_id, session_id=session_id)
        effective = _effective_status(state.session)
        current_unit = _active_unit_or_none(state)
        repository = ActiveRecallRepository(self.connection)
        run = (
            repository.get_run_for_unit(
                course_id=course_id,
                session_id=session_id,
                unit_id=str(current_unit["id"]),
            )
            if current_unit is not None
            else repository.get_latest_run_for_session(
                course_id=course_id, session_id=session_id
            )
        )
        if run is None and effective == "studying":
            return ActiveRecallReadResult(
                outcome="not_started",
                course_id=course_id,
                session=_public_session(state.session),
                plan=_public_plan(state.plan),
                checkpoint=None,
                current_unit=_public_unit(_active_unit_or_none(state)),
                run=None,
            )
        if run is None:
            raise RuntimeError("study session has no restorable active recall run")
        if run["status"] == "answered":
            if effective not in {
                "studying",
                "checkpoint",
                "active_recall",
                "practicing",
                "summarizing",
                "review_scheduling",
                "completed",
                "cancelled",
                "failed",
            }:
                raise RuntimeError(
                    "answered active recall is outside its session phase"
                )
            checkpoint = self._checkpoint_for_run(run)
            return ActiveRecallReadResult(
                outcome="answered",
                course_id=course_id,
                session=_public_session(state.session),
                plan=_public_plan(state.plan),
                checkpoint=_public_checkpoint(checkpoint),
                current_unit=_public_unit(_active_unit_or_none(state)),
                run=_public_run(run),
                grade=self._stored_grade(run),
            )
        if run["status"] == "cancelled":
            if effective not in {"cancelled", "failed"}:
                raise RuntimeError(
                    "cancelled active recall is outside its terminal session"
                )
            checkpoint = self._checkpoint_for_run(run)
            return ActiveRecallReadResult(
                outcome="cancelled",
                course_id=course_id,
                session=_public_session(state.session),
                plan=_public_plan(state.plan),
                checkpoint=_public_checkpoint(checkpoint),
                current_unit=_public_unit(_active_unit_or_none(state)),
                run=_public_run(run),
            )
        if run["status"] == "pending":
            if effective != "active_recall":
                raise RuntimeError("pending active recall is outside its session phase")
            checkpoint = self._checkpoint_for_run(run)
            return ActiveRecallReadResult(
                outcome="pending",
                course_id=course_id,
                session=_public_session(state.session),
                plan=_public_plan(state.plan),
                checkpoint=_public_checkpoint(checkpoint),
                current_unit=_public_unit(_active_unit_or_none(state)),
                run=_public_run(run),
            )
        raise RuntimeError("study session cannot restore active recall in this state")

    def _read(self, *, course_id: str, session_id: str):
        result = StudySessionReadService(self.connection).get(
            course_id=course_id, session_id=session_id
        )
        if result is None:
            raise ActiveRecallNotFoundError("study session not found")
        if result.outcome != "ready" or result.plan is None:
            raise RuntimeError("study session plan is unavailable")
        return result

    def _require_scoped_session(self, *, course_id: str, session_id: str) -> None:
        if (
            self.connection.execute(
                "SELECT 1 FROM study_sessions WHERE id = ? AND course_id = ?",
                (session_id, course_id),
            ).fetchone()
            is None
        ):
            raise ActiveRecallNotFoundError("study session not found")

    def _checkpoint_for_run(self, run: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM study_checkpoints WHERE id = ? AND session_id = ?",
            (run["checkpoint_id"], run["session_id"]),
        ).fetchone()
        if row is None:
            raise RuntimeError("active recall checkpoint is unavailable")
        return dict(row)

    def _item_for_run(self, run: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM assessment_items WHERE id = ? AND assessment_id = ?",
            (run["item_id"], run["assessment_id"]),
        ).fetchone()
        if row is None:
            raise RuntimeError("active recall assessment item is unavailable")
        item = dict(row)
        item["answer_key"] = load_json(item.pop("answer_key_json"))
        return item

    def _concept_name(self, course_id: str, concept_id: str) -> str:
        row = self.connection.execute(
            "SELECT name FROM concepts WHERE id = ? AND course_id = ?",
            (concept_id, course_id),
        ).fetchone()
        if row is None or not isinstance(row["name"], str) or not row["name"].strip():
            raise RuntimeError("active recall concept is unavailable")
        return str(row["name"])

    def _source_for_unit(self, *, course_id: str, unit: dict[str, Any]) -> str:
        """Return only unit text that is still present in its cited course chunk."""

        source = _unit_source(unit)
        source_ids = unit.get("source_chunk_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise RuntimeError("active recall source citations are unavailable")
        placeholders = ",".join("?" for _ in source_ids)
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT ch.id, ch.content
            FROM document_chunks ch
            JOIN course_documents cd ON cd.document_id = ch.document_id
            WHERE cd.course_id = ? AND ch.id IN ({placeholders})
            """,
            (course_id, *source_ids),
        ).fetchall()
        if {str(row["id"]) for row in rows} != set(source_ids):
            raise RuntimeError("active recall source citations are unavailable")
        if not any(
            isinstance(row["content"], str) and source in str(row["content"])
            for row in rows
        ):
            raise RuntimeError("active recall unit text is not in its cited source")
        return source

    def _mastery_parameters(self, concept_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT m.probability, m.attempts, c.bkt_slip, c.bkt_guess, c.bkt_transit
            FROM mastery m JOIN concepts c ON c.id = m.concept_id
            WHERE m.concept_id = ?
            """,
            (concept_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("active recall mastery state is unavailable")
        return dict(row)

    def _answer_checkpoint(self, *, checkpoint_id: str, answered_at: str) -> None:
        cursor = self.connection.execute(
            """
            UPDATE study_checkpoints
            SET response = ?, status = 'answered', answered_at = ?
            WHERE id = ? AND kind = 'active_recall' AND status = 'pending'
              AND response IS NULL
            """,
            (_CHECKPOINT_RESPONSE, answered_at, checkpoint_id),
        )
        if cursor.rowcount != 1:
            raise ActiveRecallConflictError("active recall checkpoint is not pending")

    def _stored_grade(self, run: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT correctness, final_score, grader_version
            FROM answer_evaluations WHERE id = ? AND attempt_id = ? AND item_id = ?
            """,
            (run["evaluation_id"], run["attempt_id"], run["item_id"]),
        ).fetchone()
        item = self.connection.execute(
            "SELECT max_score FROM assessment_items WHERE id = ?", (run["item_id"],)
        ).fetchone()
        if row is None or item is None:
            raise RuntimeError("active recall evaluation is unavailable")
        return {
            "correct": row["correctness"] == "correct",
            "score": float(row["final_score"]),
            "max_score": float(item["max_score"]),
            "grader_version": row["grader_version"],
        }

    def _result(
        self,
        *,
        course_id: str,
        session_id: str,
        run: dict[str, Any],
        outcome: ActiveRecallOutcome,
        grade: dict[str, Any] | None = None,
    ) -> ActiveRecallProgressionResult:
        if run["course_id"] != course_id or run["session_id"] != session_id:
            raise RuntimeError("active recall result is inconsistent")
        state = self._read(course_id=course_id, session_id=session_id)
        checkpoint = self._checkpoint_for_run(run)
        stored_grade = self._stored_grade(run) if run["status"] == "answered" else None
        return ActiveRecallProgressionResult(
            outcome=outcome,
            course_id=course_id,
            session=_public_session(state.session),
            plan=_public_plan(state.plan),
            checkpoint=_public_checkpoint(checkpoint),
            current_unit=_public_unit(_active_unit_or_none(state)),
            run=_public_run(run),
            grade=grade if grade is not None else stored_grade,
        )


def _current_active_unit(state: Any) -> dict[str, Any]:
    unit = _active_unit_or_none(state)
    if (
        unit is None
        or unit.get("status") != "active"
        or state.current_unit_id != unit.get("id")
    ):
        raise ActiveRecallConflictError("study session has no active current unit")
    if not isinstance(unit.get("concept_id"), str) or unit[
        "concept_id"
    ] not in unit.get("concept_ids", []):
        raise RuntimeError("active study unit has no validated primary concept")
    return unit


def _active_unit_or_none(state: Any) -> dict[str, Any] | None:
    return next(
        (unit for unit in state.plan["units"] if unit["id"] == state.current_unit_id),
        None,
    )


def _unit_source(unit: dict[str, Any]) -> str:
    content = unit.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ActiveRecallConflictError("current unit has no source excerpt")
    return content


def _expected_answers(value: object) -> list[str]:
    if not isinstance(value, dict):
        raise RuntimeError("active recall answer key is malformed")
    answers = value.get("accepted_answers")
    if (
        not isinstance(answers, list)
        or len(answers) != 1
        or not isinstance(answers[0], str)
    ):
        raise RuntimeError("active recall answer key is malformed")
    return answers


def _public_run(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "status",
        "checkpoint_id",
        "assessment_id",
        "item_id",
        "generator_version",
        "attempt_id",
        "evaluation_id",
        "mastery_evidence_id",
        "mastery_event_id",
        "created_at",
        "answered_at",
        "cancelled_at",
        "cancellation_reason",
    )
    return {field: row[field] for field in fields}


def _public_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "kind",
        "prompt",
        "response",
        "status",
        "created_at",
        "answered_at",
    )
    result = {field: checkpoint[field] for field in fields}
    # The only answer ever persisted here is an intentionally generic marker.
    if result.get("response") not in {None, _CHECKPOINT_RESPONSE}:
        raise RuntimeError("active recall checkpoint response is malformed")
    return result


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "course_id",
        "status",
        "resume_from_status",
        "revision",
        "progress",
        "estimated_minutes",
        "current_unit_id",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    )
    return {field: session.get(field) for field in fields}


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": plan["id"],
        "session_id": plan["session_id"],
        "version": plan["version"],
        "units": [_public_unit(unit) for unit in plan["units"]],
    }


def _public_unit(unit: dict[str, Any] | None) -> dict[str, Any] | None:
    if unit is None:
        return None
    fields = (
        "id",
        "plan_version_id",
        "ordinal",
        "estimated_minutes",
        "status",
        "created_at",
        "updated_at",
    )
    return {field: unit[field] for field in fields}


def _public_grade(grade: Any) -> dict[str, Any]:
    return {
        "correct": bool(grade.correct),
        "score": float(grade.score),
        "max_score": float(grade.max_score),
        "grader_version": grade.grader_version,
    }


def _effective_status(session: dict[str, Any]) -> str:
    status = session.get("status")
    if status == "paused":
        resume = session.get("resume_from_status")
        if not isinstance(resume, str):
            raise RuntimeError("paused study session has no resumable state")
        return resume
    if session.get("resume_from_status") is not None:
        raise RuntimeError("active study session has an unexpected resume state")
    if not isinstance(status, str):
        raise RuntimeError("study session status is invalid")
    return status


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


def _revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_revision must be a non-negative integer")
    return value


def _response(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8_000:
        raise ValueError("active recall response must be 1 to 8000 characters")
    return value


def _normalize_response(response: str) -> str:
    # Use exactly the objective grader's policy in the idempotency fingerprint.
    from app.assessment.objective_grading import normalize_fill_blank

    normalized = normalize_fill_blank(response, _FILL_BLANK_POLICY)
    if not normalized:
        raise ValueError("active recall response must not normalize to empty")
    return normalized


def _fingerprint(*values: object) -> str:
    return hashlib.sha256(
        "\x1f".join(str(value) for value in values).encode()
    ).hexdigest()


def _uuid(session_id: str, kind: str, key: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{session_id}:{kind}:{key}"))


def _checkpoint_id(session_id: str, key: str) -> str:
    return f"active-recall-checkpoint:{_uuid(session_id, 'checkpoint', key)}"


def _assessment_id(session_id: str, key: str) -> str:
    return f"active-recall-assessment:{_uuid(session_id, 'assessment', key)}"


def _item_id(session_id: str, key: str) -> str:
    return f"active-recall-item:{_uuid(session_id, 'item', key)}"


def _run_id(session_id: str, key: str) -> str:
    return f"active-recall-run:{_uuid(session_id, 'run', key)}"


def _attempt_id(run_id: str, key: str) -> str:
    return f"active-recall-attempt:{uuid.uuid5(_NAMESPACE, f'{run_id}:attempt:{key}')}"


def _evaluation_id(run_id: str, key: str) -> str:
    return f"active-recall-evaluation:{uuid.uuid5(_NAMESPACE, f'{run_id}:evaluation:{key}')}"


def _evidence_id(run_id: str, key: str) -> str:
    return (
        f"active-recall-evidence:{uuid.uuid5(_NAMESPACE, f'{run_id}:evidence:{key}')}"
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "ActiveRecallConflictError",
    "ActiveRecallNotFoundError",
    "ActiveRecallProgressionResult",
    "ActiveRecallProgressionService",
    "ActiveRecallReadResult",
]
