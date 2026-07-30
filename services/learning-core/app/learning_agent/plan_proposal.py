"""Frozen context for one explicit, read-only Study Plan proposal."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from ..repositories import dump_json
from ..repositories.study_repository import StudyRepository
from .context import load_frozen_sources
from .types import FrozenInterventionSource


@dataclass(frozen=True, slots=True)
class PlanProposalUnit:
    id: str
    ordinal: int
    title: str
    objective: str
    estimated_minutes: int
    status: str


@dataclass(frozen=True, slots=True)
class PlanProposalContext:
    course_id: str
    session_id: str
    session_revision: int
    goal: str
    plan_id: str
    plan_version: int
    target_unit: PlanProposalUnit
    units: tuple[PlanProposalUnit, ...]
    sources: tuple[FrozenInterventionSource, ...]


def project_plan_proposal_context(
    connection: sqlite3.Connection,
    *,
    course_id: str,
    session_id: str,
    expected_session_revision: int,
    expected_plan_version: int,
    target_unit_id: str,
) -> PlanProposalContext:
    """Freeze one learner-requested insertion point without changing the plan."""

    session = StudyRepository(connection).get_session(session_id)
    if session is None or session["course_id"] != course_id:
        raise LookupError("study session not found")
    if (
        session["status"] in {"completed", "cancelled", "failed"}
        or int(session["revision"]) != expected_session_revision
    ):
        raise RuntimeError("study session revision is stale")
    plan = StudyRepository(connection).get_current_or_latest_plan(session_id)
    if plan is None or int(plan["version"]) != expected_plan_version:
        raise RuntimeError("study plan version is stale")
    units = tuple(
        PlanProposalUnit(
            id=str(unit["id"]),
            ordinal=int(unit["ordinal"]),
            title=str(unit["title"]),
            objective=str(unit["objective"]),
            estimated_minutes=int(unit["estimated_minutes"]),
            status=str(unit["status"]),
        )
        for unit in plan["units"]
    )
    if len(units) < 2 or len(units) > 7:
        raise RuntimeError("study plan is outside the supported proposal bounds")
    current_index = next(
        (
            index
            for index, unit in enumerate(units)
            if unit.id == session["current_unit_id"] and unit.status == "active"
        ),
        None,
    )
    if current_index is None:
        raise RuntimeError("proposal requires the current active plan unit")
    expected_target = next(
        (
            unit
            for unit in units[current_index + 1 :]
            if unit.status in {"ready", "locked"}
        ),
        None,
    )
    target = next((unit for unit in units if unit.id == target_unit_id), None)
    raw_target = next(
        (unit for unit in plan["units"] if unit["id"] == target_unit_id),
        None,
    )
    if (
        target is None
        or raw_target is None
        or expected_target is None
        or target.id != expected_target.id
    ):
        raise RuntimeError("proposal target must be the next unstarted plan unit")
    source_ids = raw_target["source_chunk_ids"]
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or len(source_ids) > 8
        or len(source_ids) != len(set(source_ids))
        or any(not isinstance(value, str) or not value for value in source_ids)
    ):
        raise RuntimeError("proposal source scope is unavailable")
    sources = load_frozen_sources(
        connection,
        course_id=course_id,
        session_id=session_id,
        unit_id=target.id,
        source_ids=source_ids,
    )
    if sources is None:
        raise RuntimeError("proposal source scope is unavailable")
    return PlanProposalContext(
        course_id=course_id,
        session_id=session_id,
        session_revision=int(session["revision"]),
        goal=str(session["goal"]),
        plan_id=str(plan["id"]),
        plan_version=int(plan["version"]),
        target_unit=target,
        units=units,
        sources=sources,
    )


def revalidate_plan_proposal_context(
    connection: sqlite3.Connection,
    context: PlanProposalContext,
) -> None:
    current = project_plan_proposal_context(
        connection,
        course_id=context.course_id,
        session_id=context.session_id,
        expected_session_revision=context.session_revision,
        expected_plan_version=context.plan_version,
        target_unit_id=context.target_unit.id,
    )
    if current != context:
        raise RuntimeError("study plan or source scope changed during proposal")


def plan_proposal_context_fingerprint(context: PlanProposalContext) -> str:
    payload = {
        "courseId": context.course_id,
        "sessionId": context.session_id,
        "sessionRevision": context.session_revision,
        "planId": context.plan_id,
        "planVersion": context.plan_version,
        "targetUnitId": context.target_unit.id,
        "units": [
            {
                "id": unit.id,
                "ordinal": unit.ordinal,
                "status": unit.status,
            }
            for unit in context.units
        ],
        "sources": [
            source.model_dump(mode="json", by_alias=True) for source in context.sources
        ],
    }
    return hashlib.sha256(dump_json(payload).encode("utf-8")).hexdigest()


__all__ = [
    "PlanProposalContext",
    "PlanProposalUnit",
    "plan_proposal_context_fingerprint",
    "project_plan_proposal_context",
    "revalidate_plan_proposal_context",
]
