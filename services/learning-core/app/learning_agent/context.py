"""Project intervention eligibility from existing authoritative learning facts."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from ..repositories import dump_json, load_json
from .types import FrozenInterventionSource

EligibilityReason = Literal[
    "eligible",
    "recall_not_answered",
    "recall_correct",
    "session_not_practicing",
    "source_unavailable",
]

WHY_NOW = "Your latest Recall did not meet the expected answer."
WHAT_NEXT = "Continue with a new, independently scored Practice prompt."


@dataclass(frozen=True, slots=True)
class InterventionContext:
    course_id: str
    session_id: str
    session_revision: int
    unit_id: str
    unit_title: str
    unit_objective: str
    goal: str
    recall_run_id: str
    trigger_attempt_id: str
    trigger_evaluation_id: str
    recall_prompt: str
    learner_response: str
    diagnostic_self_report_evidence_id: str | None
    diagnostic_self_report_score: float | None
    sources: tuple[FrozenInterventionSource, ...]


@dataclass(frozen=True, slots=True)
class InterventionEligibility:
    reason: EligibilityReason
    context: InterventionContext | None


def project_intervention_eligibility(
    connection: sqlite3.Connection,
    *,
    course_id: str,
    session_id: str,
) -> InterventionEligibility:
    """Return a read-only projection; no Agent or learning state is created."""

    row = connection.execute(
        """
        SELECT session.course_id, session.id AS session_id,
               session.revision AS session_revision, session.status AS session_status,
               session.goal, session.current_unit_id,
               unit.id AS unit_id, unit.title AS unit_title,
               unit.objective AS unit_objective,
               recall.id AS recall_run_id, recall.status AS recall_status,
               recall.attempt_id, recall.evaluation_id,
               recall.source_chunk_ids_json,
               item.prompt AS recall_prompt,
               attempt.answer_json,
               evaluation.correctness, evaluation.evaluation_source,
               (
                   SELECT evidence.id
                   FROM study_checkpoints diagnostic
                   JOIN mastery_evidence evidence
                     ON evidence.id = diagnostic.mastery_evidence_id
                   WHERE diagnostic.session_id = session.id
                     AND diagnostic.unit_id = unit.id
                     AND diagnostic.kind = 'diagnostic'
                     AND diagnostic.status = 'answered'
                     AND evidence.session_id = session.id
                     AND evidence.concept_id = unit.concept_id
                     AND evidence.evidence_type = 'user_report'
                     AND evidence.weight = 0
                   ORDER BY diagnostic.answered_at DESC, diagnostic.id DESC
                   LIMIT 1
               ) AS diagnostic_self_report_evidence_id,
               (
                   SELECT evidence.correctness
                   FROM study_checkpoints diagnostic
                   JOIN mastery_evidence evidence
                     ON evidence.id = diagnostic.mastery_evidence_id
                   WHERE diagnostic.session_id = session.id
                     AND diagnostic.unit_id = unit.id
                     AND diagnostic.kind = 'diagnostic'
                     AND diagnostic.status = 'answered'
                     AND evidence.session_id = session.id
                     AND evidence.concept_id = unit.concept_id
                     AND evidence.evidence_type = 'user_report'
                     AND evidence.weight = 0
                   ORDER BY diagnostic.answered_at DESC, diagnostic.id DESC
                   LIMIT 1
               ) AS diagnostic_self_report_score
        FROM study_sessions session
        LEFT JOIN study_units unit ON unit.id = session.current_unit_id
        LEFT JOIN study_active_recall_runs recall
          ON recall.course_id = session.course_id
         AND recall.session_id = session.id
         AND recall.unit_id = session.current_unit_id
        LEFT JOIN assessment_items item ON item.id = recall.item_id
        LEFT JOIN assessment_attempts attempt ON attempt.id = recall.attempt_id
        LEFT JOIN answer_evaluations evaluation ON evaluation.id = recall.evaluation_id
        WHERE session.id = ? AND session.course_id = ?
        ORDER BY recall.created_at DESC, recall.id DESC
        LIMIT 1
        """,
        (session_id, course_id),
    ).fetchone()
    if (
        row is None
        or row["unit_id"] is None
        or row["recall_run_id"] is None
        or row["recall_status"] != "answered"
        or row["attempt_id"] is None
        or row["evaluation_id"] is None
    ):
        return InterventionEligibility(reason="recall_not_answered", context=None)
    if row["evaluation_source"] != "deterministic" or row["correctness"] == "correct":
        return InterventionEligibility(reason="recall_correct", context=None)
    if row["session_status"] != "practicing":
        return InterventionEligibility(reason="session_not_practicing", context=None)

    source_ids = load_json(str(row["source_chunk_ids_json"]))
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or len(source_ids) > 8
        or any(not isinstance(value, str) or not value for value in source_ids)
        or len(set(source_ids)) != len(source_ids)
    ):
        return InterventionEligibility(reason="source_unavailable", context=None)
    sources = load_frozen_sources(
        connection,
        course_id=course_id,
        session_id=session_id,
        unit_id=str(row["unit_id"]),
        source_ids=source_ids,
    )
    if sources is None:
        return InterventionEligibility(reason="source_unavailable", context=None)
    learner_response = _learner_response(row["answer_json"])
    return InterventionEligibility(
        reason="eligible",
        context=InterventionContext(
            course_id=course_id,
            session_id=session_id,
            session_revision=int(row["session_revision"]),
            unit_id=str(row["unit_id"]),
            unit_title=str(row["unit_title"]),
            unit_objective=str(row["unit_objective"]),
            goal=str(row["goal"]),
            recall_run_id=str(row["recall_run_id"]),
            trigger_attempt_id=str(row["attempt_id"]),
            trigger_evaluation_id=str(row["evaluation_id"]),
            recall_prompt=str(row["recall_prompt"]),
            learner_response=learner_response,
            diagnostic_self_report_evidence_id=(
                str(row["diagnostic_self_report_evidence_id"])
                if row["diagnostic_self_report_evidence_id"] is not None
                else None
            ),
            diagnostic_self_report_score=(
                float(row["diagnostic_self_report_score"])
                if row["diagnostic_self_report_score"] is not None
                else None
            ),
            sources=sources,
        ),
    )


def revalidate_intervention_context(
    connection: sqlite3.Connection,
    context: InterventionContext,
) -> tuple[FrozenInterventionSource, ...]:
    """Re-project and require the exact same trigger and frozen source identity."""

    current = project_intervention_eligibility(
        connection,
        course_id=context.course_id,
        session_id=context.session_id,
    )
    if current.reason != "eligible" or current.context is None:
        raise ValueError("intervention learning state is no longer eligible")
    candidate = current.context
    if (
        candidate.session_revision != context.session_revision
        or candidate.unit_id != context.unit_id
        or candidate.recall_run_id != context.recall_run_id
        or candidate.trigger_attempt_id != context.trigger_attempt_id
        or candidate.trigger_evaluation_id != context.trigger_evaluation_id
        or candidate.diagnostic_self_report_evidence_id
        != context.diagnostic_self_report_evidence_id
        or candidate.diagnostic_self_report_score
        != context.diagnostic_self_report_score
        or candidate.sources != context.sources
    ):
        raise ValueError("intervention learning state or source scope changed")
    return candidate.sources


def context_fingerprint(context: InterventionContext) -> str:
    return _context_fingerprint(context, include_diagnostic_self_report=True)


def legacy_context_fingerprint(context: InterventionContext) -> str:
    """Restore runs frozen before diagnostic selection joined the context."""

    return _context_fingerprint(context, include_diagnostic_self_report=False)


def _context_fingerprint(
    context: InterventionContext,
    *,
    include_diagnostic_self_report: bool,
) -> str:
    payload = {
        "courseId": context.course_id,
        "sessionId": context.session_id,
        "unitId": context.unit_id,
        "recallRunId": context.recall_run_id,
        "triggerAttemptId": context.trigger_attempt_id,
        "triggerEvaluationId": context.trigger_evaluation_id,
        "sources": [
            source.model_dump(mode="json", by_alias=True) for source in context.sources
        ],
    }
    if include_diagnostic_self_report:
        payload["diagnosticSelfReport"] = (
            {
                "evidenceId": context.diagnostic_self_report_evidence_id,
                "score": context.diagnostic_self_report_score,
            }
            if context.diagnostic_self_report_evidence_id is not None
            and context.diagnostic_self_report_score is not None
            else None
        )
    return hashlib.sha256(dump_json(payload).encode("utf-8")).hexdigest()


def load_frozen_sources(
    connection: sqlite3.Connection,
    *,
    course_id: str,
    session_id: str,
    unit_id: str,
    source_ids: list[str],
) -> tuple[FrozenInterventionSource, ...] | None:
    placeholders = ",".join("?" for _ in source_ids)
    rows = connection.execute(
        f"""
        SELECT chunk.id AS chunk_id, chunk.document_id, chunk.version_id,
               chunk.content_hash, chunk.page_number, chunk.section_path,
               chunk.content, chunk.text_location, document.name AS document_name
        FROM document_chunks chunk
        JOIN documents document ON document.id = chunk.document_id
        JOIN course_documents course_document
          ON course_document.document_id = document.id
        WHERE course_document.course_id = ?
          AND document.status = 'indexed'
          AND chunk.id IN ({placeholders})
        ORDER BY chunk.document_id, chunk.ordinal, chunk.id
        """,
        (course_id, *source_ids),
    ).fetchall()
    if {str(row["chunk_id"]) for row in rows} != set(source_ids):
        return None
    sources: list[FrozenInterventionSource] = []
    for row in rows:
        identity = "\0".join(
            (
                course_id,
                session_id,
                unit_id,
                str(row["chunk_id"]),
                str(row["version_id"]),
                str(row["content_hash"]),
            )
        )
        handle = f"source-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"
        content = str(row["content"])
        sources.append(
            FrozenInterventionSource(
                sourceHandle=handle,
                chunkId=str(row["chunk_id"]),
                documentId=str(row["document_id"]),
                documentVersionId=str(row["version_id"]),
                chunkContentHash=str(row["content_hash"]),
                documentName=str(row["document_name"]),
                pageNumber=int(row["page_number"]),
                sectionPath=_string_list(load_json(str(row["section_path"]))),
                quote=content[:2_000],
                geometry=_json_object_or_none(load_json(str(row["text_location"]))),
                metadata={
                    "quoteTruncated": len(content) > 2_000,
                    "contentTrust": "untrusted_course_data",
                },
            )
        )
    return tuple(sources)


def _learner_response(value: object) -> str:
    parsed = load_json(str(value))
    if isinstance(parsed, str):
        return parsed[:2_000]
    if isinstance(parsed, list):
        return ", ".join(str(item) for item in parsed)[:2_000]
    return str(parsed)[:2_000]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("source section path is invalid")
    return value[:16]


def _json_object_or_none(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"fragments": value}
    raise ValueError("source geometry is invalid")


__all__ = [
    "WHAT_NEXT",
    "WHY_NOW",
    "InterventionContext",
    "InterventionEligibility",
    "context_fingerprint",
    "legacy_context_fingerprint",
    "load_frozen_sources",
    "project_intervention_eligibility",
    "revalidate_intervention_context",
]
