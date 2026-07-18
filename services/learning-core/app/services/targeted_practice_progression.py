"""Durable, deterministic practice after an answered active-recall checkpoint.

The hidden answer stays in the immutable assessment item.  Every result from
this service is deliberately learner-safe: it contains the prompt and outcome,
never source text, identifiers that locate source material, or answer keys.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.assessment import (
    TARGETED_PRACTICE_GENERATOR_VERSION,
    FillBlankNormalization,
    ObjectiveItemType,
    generate_targeted_practice,
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
from app.repositories import dump_json, load_json, write_scope
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.practice_repository import (
    PracticeRepository,
    practice_source_content_fingerprint,
)
from app.repositories.study_repository import StudyRepository
from app.services.study_session_read import StudySessionReadService


_NAMESPACE = uuid.UUID("6425943c-891d-49c3-bc91-11af9f2096d1")
_CHECKPOINT_RESPONSE = "Objective response recorded."
_FILL_BLANK_POLICY = FillBlankNormalization()

PracticeOutcome = Literal["applied", "replayed"]
PracticeReadOutcome = Literal["not_started", "pending", "answered", "cancelled"]


class TargetedPracticeNotFoundError(LookupError):
    """The trusted course/session/run does not exist."""


class TargetedPracticeConflictError(RuntimeError):
    """The session cannot accept the requested practice action."""


@dataclass(frozen=True, slots=True)
class TargetedPracticeProgressionResult:
    outcome: PracticeOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any]
    checkpoint: dict[str, Any]
    current_unit: dict[str, Any] | None
    run: dict[str, Any]
    grade: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TargetedPracticeReadResult:
    outcome: PracticeReadOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any]
    checkpoint: dict[str, Any] | None
    current_unit: dict[str, Any] | None
    run: dict[str, Any] | None
    grade: dict[str, Any] | None = None


class TargetedPracticeProgressionService:
    """Persist exactly one source-bounded, follow-up practice assessment.

    All mutations are composed in one immediate transaction.  This path records
    objective PRACTICE evidence for weighted BKT and intentionally never writes
    an FSRS/review table.
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
    ) -> TargetedPracticeProgressionResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        expected_revision = _revision(expected_revision)
        idempotency_key = _idempotency_key(idempotency_key)
        timestamp = _utc(now).isoformat()
        with write_scope(self.connection, commit=True):
            self._require_scoped_session(course_id=course_id, session_id=session_id)
            fingerprint = _fingerprint(
                "begin",
                course_id,
                session_id,
                TARGETED_PRACTICE_GENERATOR_VERSION,
                expected_revision,
            )
            ledger = PracticeRepository(self.connection)
            try:
                replay = ledger.replay_begin(
                    course_id=course_id,
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                    payload_fingerprint=fingerprint,
                )
            except ValueError as error:
                raise TargetedPracticeConflictError(str(error)) from error
            if replay is not None:
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=replay,
                    outcome="replayed",
                )
            state = self._read(course_id=course_id, session_id=session_id)
            unit = _current_active_unit(state)
            checkpoint_id = _checkpoint_id(session_id, idempotency_key)
            assessment_id = _assessment_id(session_id, idempotency_key)
            item_id = _item_id(session_id, idempotency_key)
            source, source_content_fingerprint = self._source_for_unit(
                course_id=course_id, unit=unit
            )
            predecessor_run_id, ar_answer = self._active_recall_answer(
                course_id=course_id, session_id=session_id, unit=unit
            )
            if state.session["status"] == "paused":
                raise TargetedPracticeConflictError(
                    "paused study session cannot begin practice"
                )
            if state.session["status"] != "practicing":
                raise TargetedPracticeConflictError(
                    "study session is not ready for practice"
                )
            if int(state.session["revision"]) != expected_revision:
                raise TargetedPracticeConflictError("study session revision conflict")
            if (
                ledger.get_run_for_predecessor(
                    course_id=course_id,
                    session_id=session_id,
                    predecessor_active_recall_run_id=predecessor_run_id,
                )
                is not None
            ):
                raise TargetedPracticeConflictError(
                    "practice already exists; restore the existing run"
                )
            concept_name = self._concept_name(course_id, str(unit["concept_id"]))
            practice = generate_targeted_practice(
                source, concept=concept_name, excluded_answers=(ar_answer,)
            )
            if practice is None:
                raise TargetedPracticeConflictError(
                    "current unit has no distinct safe practice cloze"
                )
            mastery_before = int(
                self._mastery_parameters(str(unit["concept_id"]))["attempts"]
            )

            study = StudyRepository(self.connection)
            transition_study_state("practicing", "summarizing")
            # Reserve the canonical successor only after the scoring run seals;
            # begin itself remains in practicing while the learner answers.
            checkpoint = study.create_checkpoint(
                checkpoint_id=checkpoint_id,
                session_id=session_id,
                unit_id=str(unit["id"]),
                kind="practice",
                prompt=practice.prompt,
                created_at=timestamp,
                commit=False,
            )
            assessment = AssessmentRepository(self.connection).create_assessment(
                assessment_id=assessment_id,
                course_id=course_id,
                session_id=session_id,
                title="Targeted practice",
                purpose="practice",
                items=[
                    {
                        "id": item_id,
                        "item_type": "fill_blank",
                        "difficulty": "easy",
                        "prompt": practice.prompt,
                        "answer_key": {"accepted_answers": [practice.accepted_answer]},
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
            run, created = ledger.create_run(
                run_id=_run_id(session_id, idempotency_key),
                course_id=course_id,
                session_id=session_id,
                unit_id=str(unit["id"]),
                checkpoint_id=checkpoint_id,
                assessment_id=assessment_id,
                item_id=item_id,
                concept_id=str(unit["concept_id"]),
                predecessor_active_recall_run_id=predecessor_run_id,
                source_chunk_ids=list(unit["source_chunk_ids"]),
                source_content_fingerprint=source_content_fingerprint,
                accepted_answers_fingerprint=_answer_key_fingerprint(
                    practice.accepted_answer
                ),
                mastery_attempts_before=mastery_before,
                generator_version=practice.generator_version,
                idempotency_key=idempotency_key,
                payload_fingerprint=fingerprint,
                created_at=timestamp,
                commit=False,
            )
            if not created:  # pragma: no cover - writer-lock replay preflight owns this
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=run,
                    outcome="replayed",
                )
            if checkpoint["status"] != "pending":
                raise RuntimeError("practice begin did not create a pending checkpoint")
            return self._result(
                course_id=course_id, session_id=session_id, run=run, outcome="applied"
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
    ) -> TargetedPracticeProgressionResult:
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
            ledger = PracticeRepository(self.connection)
            run = ledger.get_run_for_session(
                course_id=course_id, session_id=session_id, run_id=run_id
            )
            if run is None:
                raise TargetedPracticeNotFoundError("practice run not found")
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
                raise TargetedPracticeConflictError(str(error)) from error
            if replay is not None:
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=replay,
                    outcome="replayed",
                )
            if run["status"] != "pending":
                raise TargetedPracticeConflictError("practice run is not pending")
            state = self._read(course_id=course_id, session_id=session_id)
            if state.session["status"] == "paused":
                raise TargetedPracticeConflictError(
                    "paused study session cannot answer practice"
                )
            if state.session["status"] != "practicing":
                raise TargetedPracticeConflictError(
                    "study session is not awaiting practice"
                )
            if int(state.session["revision"]) != expected_revision:
                raise TargetedPracticeConflictError("study session revision conflict")
            unit = _current_active_unit(state)
            if unit["id"] != run["unit_id"] or unit["concept_id"] != run["concept_id"]:
                raise TargetedPracticeConflictError("practice run is not current")
            checkpoint = self._checkpoint_for_run(run)
            item = self._item_for_run(run)
            grade = grade_objective_answer(
                ObjectiveItemType.FILL_BLANK,
                response,
                _expected_answers(item["answer_key"]),
                max_score=float(item["max_score"]),
                fill_blank_policy=_FILL_BLANK_POLICY,
            )
            evidence_input = MasteryEvidence(
                correctness=grade.correctness,
                independence=1.0,
                hint_level=0,
                difficulty=1.0,
                confidence=1.0,
                response_type=ResponseType.PRACTICE,
            )
            weight = calculate_evidence_weight(evidence_input)
            if weight <= 0.0:
                raise RuntimeError("practice evidence must have positive weight")
            mastery = self._mastery_parameters(str(run["concept_id"]))
            update = update_mastery_from_evidence(
                float(mastery["probability"]),
                evidence_input,
                bkt_parameters=BktParameters(
                    slip=float(mastery["bkt_slip"]),
                    guess=float(mastery["bkt_guess"]),
                    transit=float(mastery["bkt_transit"]),
                ),
            )
            attempt_id = _attempt_id(run_id, idempotency_key)
            evaluation_id = _evaluation_id(run_id, idempotency_key)
            evidence_id = _evidence_id(run_id, idempotency_key)
            assessment = AssessmentRepository(self.connection)
            assessment.start_attempt(
                attempt_id=attempt_id,
                assessment_id=str(run["assessment_id"]),
                item_id=str(run["item_id"]),
                answer=response,
                idempotency_key=f"practice-attempt:{run_id}:{idempotency_key}",
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
                correctness="correct" if grade.correct else "incorrect",
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
                evidence_type=ResponseType.PRACTICE.value,
                correctness=grade.correctness,
                independence=1.0,
                hint_level=0,
                weight=weight,
                idempotency_key=f"practice-evidence:{run_id}:{idempotency_key}",
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
                idempotency_key=f"practice-event:{run_id}:{idempotency_key}",
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
            if not applied:  # pragma: no cover - preflight owns this path
                return self._result(
                    course_id=course_id,
                    session_id=session_id,
                    run=sealed,
                    outcome="replayed",
                )
            transition_study_state("practicing", "summarizing")
            summarizing = StudyRepository(self.connection).transition_session(
                session_id,
                status="summarizing",
                expected_revision=expected_revision,
                updated_at=timestamp,
                commit=False,
            )
            if summarizing["status"] != "summarizing":
                raise RuntimeError("practice answer did not enter summarizing")
            return self._result(
                course_id=course_id,
                session_id=session_id,
                run=sealed,
                outcome="applied",
                grade=_public_grade(grade),
            )

    def get(self, *, course_id: str, session_id: str) -> TargetedPracticeReadResult:
        course_id = _identifier(course_id, "course_id")
        session_id = _identifier(session_id, "session_id")
        self._require_scoped_session(course_id=course_id, session_id=session_id)
        state = self._read(course_id=course_id, session_id=session_id)
        effective = _effective_status(state.session)
        run = PracticeRepository(self.connection).get_only_run_for_session(
            course_id=course_id, session_id=session_id
        )
        if run is None and effective == "practicing":
            return TargetedPracticeReadResult(
                "not_started",
                course_id,
                _public_session(state.session),
                _public_plan(state.plan),
                None,
                _public_unit(_active_unit_or_none(state)),
                None,
            )
        if run is None and effective in {"cancelled", "failed"}:
            return TargetedPracticeReadResult(
                "cancelled",
                course_id,
                _public_session(state.session),
                _public_plan(state.plan),
                None,
                _public_unit(_active_unit_or_none(state)),
                None,
            )
        if run is None:
            raise RuntimeError("study session has no restorable practice run")
        checkpoint = self._checkpoint_for_run(run)
        public = _public_run(run)
        base = dict(
            course_id=course_id,
            session=_public_session(state.session),
            plan=_public_plan(state.plan),
            checkpoint=_public_checkpoint(checkpoint),
            current_unit=_public_unit(_active_unit_or_none(state)),
            run=public,
        )
        if run["status"] == "answered":
            if effective not in {
                "summarizing",
                "review_scheduling",
                "completed",
                "cancelled",
                "failed",
            }:
                raise RuntimeError("answered practice is outside its session phase")
            return TargetedPracticeReadResult(
                outcome="answered", grade=self._stored_grade(run), **base
            )
        if run["status"] == "cancelled":
            if effective not in {"cancelled", "failed"}:
                raise RuntimeError("cancelled practice is outside its terminal session")
            return TargetedPracticeReadResult(outcome="cancelled", **base)
        if run["status"] == "pending":
            if effective != "practicing":
                raise RuntimeError("pending practice is outside its session phase")
            return TargetedPracticeReadResult(outcome="pending", **base)
        raise RuntimeError("study session cannot restore practice in this state")

    def _read(self, *, course_id: str, session_id: str):
        result = StudySessionReadService(self.connection).get(
            course_id=course_id, session_id=session_id
        )
        if result is None:
            raise TargetedPracticeNotFoundError("study session not found")
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
            raise TargetedPracticeNotFoundError("study session not found")

    def _active_recall_answer(
        self, *, course_id: str, session_id: str, unit: dict[str, Any]
    ) -> tuple[str, str]:
        row = self.connection.execute(
            """
            SELECT r.id, i.answer_key_json
            FROM study_active_recall_runs r
            JOIN assessment_items i ON i.id = r.item_id AND i.assessment_id = r.assessment_id
            WHERE r.course_id = ? AND r.session_id = ? AND r.unit_id = ?
              AND r.concept_id = ? AND r.status = 'answered'
            """,
            (course_id, session_id, unit["id"], unit["concept_id"]),
        ).fetchone()
        if row is None:
            raise TargetedPracticeConflictError(
                "answered active recall is required before practice"
            )
        return str(row["id"]), _expected_answers(load_json(row["answer_key_json"]))[0]

    def _checkpoint_for_run(self, run: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM study_checkpoints WHERE id = ? AND session_id = ?",
            (run["checkpoint_id"], run["session_id"]),
        ).fetchone()
        if row is None:
            raise RuntimeError("practice checkpoint is unavailable")
        return dict(row)

    def _item_for_run(self, run: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM assessment_items WHERE id = ? AND assessment_id = ?",
            (run["item_id"], run["assessment_id"]),
        ).fetchone()
        if row is None:
            raise RuntimeError("practice assessment item is unavailable")
        item = dict(row)
        item["answer_key"] = load_json(item.pop("answer_key_json"))
        expected_fingerprint = hashlib.sha256(
            dump_json(item["answer_key"]).encode("utf-8")
        ).hexdigest()
        sealed = self.connection.execute(
            "SELECT accepted_answers_fingerprint FROM study_practice_runs WHERE id = ?",
            (run["id"],),
        ).fetchone()
        if (
            sealed is None
            or expected_fingerprint != sealed["accepted_answers_fingerprint"]
        ):
            raise RuntimeError(
                "practice accepted answers fingerprint does not match item"
            )
        return item

    def _concept_name(self, course_id: str, concept_id: str) -> str:
        row = self.connection.execute(
            "SELECT name FROM concepts WHERE id = ? AND course_id = ?",
            (concept_id, course_id),
        ).fetchone()
        if row is None or not isinstance(row["name"], str) or not row["name"].strip():
            raise RuntimeError("practice concept is unavailable")
        return str(row["name"])

    def _source_for_unit(
        self, *, course_id: str, unit: dict[str, Any]
    ) -> tuple[str, str]:
        source = _unit_source(unit)
        source_ids = unit.get("source_chunk_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise RuntimeError("practice source citations are unavailable")
        placeholders = ",".join("?" for _ in source_ids)
        rows = self.connection.execute(
            f"""SELECT DISTINCT ch.id, ch.content FROM document_chunks ch
            JOIN course_documents cd ON cd.document_id = ch.document_id
            WHERE cd.course_id = ? AND ch.id IN ({placeholders})""",
            (course_id, *source_ids),
        ).fetchall()
        if {str(row["id"]) for row in rows} != set(source_ids) or not any(
            isinstance(row["content"], str) and source in str(row["content"])
            for row in rows
        ):
            raise RuntimeError("practice unit text is not in its cited source")
        return source, practice_source_content_fingerprint(
            unit_content=source,
            chunks=[(str(row["id"]), str(row["content"])) for row in rows],
        )

    def _mastery_parameters(self, concept_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """SELECT m.probability, m.attempts, c.bkt_slip, c.bkt_guess, c.bkt_transit
            FROM mastery m JOIN concepts c ON c.id = m.concept_id WHERE m.concept_id = ?""",
            (concept_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("practice mastery state is unavailable")
        return dict(row)

    def _answer_checkpoint(self, *, checkpoint_id: str, answered_at: str) -> None:
        cursor = self.connection.execute(
            """UPDATE study_checkpoints SET response = ?, status = 'answered', answered_at = ?
            WHERE id = ? AND kind = 'practice' AND status = 'pending' AND response IS NULL""",
            (_CHECKPOINT_RESPONSE, answered_at, checkpoint_id),
        )
        if cursor.rowcount != 1:
            raise TargetedPracticeConflictError("practice checkpoint is not pending")

    def _stored_grade(self, run: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT correctness, final_score, grader_version FROM answer_evaluations WHERE id = ? AND attempt_id = ? AND item_id = ?",
            (run["evaluation_id"], run["attempt_id"], run["item_id"]),
        ).fetchone()
        item = self.connection.execute(
            "SELECT max_score FROM assessment_items WHERE id = ?", (run["item_id"],)
        ).fetchone()
        if row is None or item is None:
            raise RuntimeError("practice evaluation is unavailable")
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
        outcome: PracticeOutcome,
        grade: dict[str, Any] | None = None,
    ) -> TargetedPracticeProgressionResult:
        if run["course_id"] != course_id or run["session_id"] != session_id:
            raise RuntimeError("practice result is inconsistent")
        state = self._read(course_id=course_id, session_id=session_id)
        checkpoint = self._checkpoint_for_run(run)
        public_run = _public_run(run)
        public_grade = grade
        if public_grade is None and run["status"] == "answered":
            public_grade = self._stored_grade(run)
        return TargetedPracticeProgressionResult(
            outcome,
            course_id,
            _public_session(state.session),
            _public_plan(state.plan),
            _public_checkpoint(checkpoint),
            _public_unit(_active_unit_or_none(state)),
            public_run,
            public_grade,
        )


def _current_active_unit(state: Any) -> dict[str, Any]:
    unit = _active_unit_or_none(state)
    if (
        unit is None
        or unit.get("status") != "active"
        or state.current_unit_id != unit.get("id")
    ):
        raise TargetedPracticeConflictError("study session has no active current unit")
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
        raise TargetedPracticeConflictError("current unit has no source excerpt")
    return content


def _expected_answers(value: object) -> list[str]:
    if not isinstance(value, dict) or not isinstance(
        value.get("accepted_answers"), list
    ):
        raise RuntimeError("practice answer key is malformed")
    answers = value["accepted_answers"]
    if len(answers) != 1 or not isinstance(answers[0], str):
        raise RuntimeError("practice answer key is malformed")
    return answers


def _public_run(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "status",
        "checkpoint_id",
        "generator_version",
        "created_at",
        "answered_at",
        "cancelled_at",
        "cancellation_reason",
    )
    return {field: row[field] for field in fields}


def _public_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    if checkpoint["response"] not in {None, _CHECKPOINT_RESPONSE}:
        raise RuntimeError("practice checkpoint response is malformed")
    fields = ("id", "kind", "prompt", "status", "created_at", "answered_at")
    return {field: checkpoint[field] for field in fields}


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "course_id",
        "status",
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
    return {
        field: unit[field]
        for field in (
            "id",
            "ordinal",
            "estimated_minutes",
            "status",
            "created_at",
            "updated_at",
        )
    }


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
    if session.get("resume_from_status") is not None or not isinstance(status, str):
        raise RuntimeError("study session status is invalid")
    return status


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty identifier")
    return value


def _idempotency_key(value: object) -> str:
    key = _identifier(value, "idempotency_key")
    if len(key) < 16 or any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
        for c in key
    ):
        raise ValueError("idempotency_key is invalid")
    return key


def _revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_revision must be a non-negative integer")
    return value


def _response(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8_000:
        raise ValueError("practice response must be 1 to 8000 characters")
    return value


def _normalize_response(response: str) -> str:
    from app.assessment.objective_grading import normalize_fill_blank

    normalized = normalize_fill_blank(response, _FILL_BLANK_POLICY)
    if not normalized:
        raise ValueError("practice response must not normalize to empty")
    return normalized


def _fingerprint(*values: object) -> str:
    return hashlib.sha256(
        "\x1f".join(str(value) for value in values).encode()
    ).hexdigest()


def _answer_key_fingerprint(answer: str) -> str:
    """Match the ledger's verification of the immutable item answer key."""

    return hashlib.sha256(
        dump_json({"accepted_answers": [answer]}).encode("utf-8")
    ).hexdigest()


def _uuid(session_id: str, kind: str, key: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{session_id}:{kind}:{key}"))


def _checkpoint_id(session_id: str, key: str) -> str:
    return f"practice-checkpoint:{_uuid(session_id, 'checkpoint', key)}"


def _assessment_id(session_id: str, key: str) -> str:
    return f"practice-assessment:{_uuid(session_id, 'assessment', key)}"


def _item_id(session_id: str, key: str) -> str:
    return f"practice-item:{_uuid(session_id, 'item', key)}"


def _run_id(session_id: str, key: str) -> str:
    return f"practice-run:{_uuid(session_id, 'run', key)}"


def _attempt_id(run_id: str, key: str) -> str:
    return f"practice-attempt:{uuid.uuid5(_NAMESPACE, f'{run_id}:attempt:{key}')}"


def _evaluation_id(run_id: str, key: str) -> str:
    return f"practice-evaluation:{uuid.uuid5(_NAMESPACE, f'{run_id}:evaluation:{key}')}"


def _evidence_id(run_id: str, key: str) -> str:
    return f"practice-evidence:{uuid.uuid5(_NAMESPACE, f'{run_id}:evidence:{key}')}"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "TargetedPracticeConflictError",
    "TargetedPracticeNotFoundError",
    "TargetedPracticeProgressionResult",
    "TargetedPracticeProgressionService",
    "TargetedPracticeReadResult",
]
