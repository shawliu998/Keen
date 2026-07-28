"""Compose an intervention with Keen's existing adaptive Practice branch."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..repositories.adaptive_action_repository import AdaptiveActionRepository
from ..repositories.practice_repository import PracticeRepository
from ..services.adaptive_study_session import AdaptiveStudySessionService
from ..services.targeted_practice_progression import (
    TargetedPracticeProgressionService,
)
from .context import InterventionContext, revalidate_intervention_context


@dataclass(frozen=True, slots=True)
class InterventionPracticeHandoff:
    run_id: str
    prompt: str
    session_revision: int


def ensure_intervention_practice(
    connection: sqlite3.Connection,
    *,
    context: InterventionContext,
    idempotency_seed: str,
    now: datetime,
) -> InterventionPracticeHandoff:
    """Complete matching remediation, then restore or create canonical Practice.

    Remediation and Practice deliberately remain two existing durable
    transactions. If Practice creation fails, the completed remediation leaves
    its matching pending Practice action available for a later retry.
    """

    revalidate_intervention_context(connection, context)
    practice_repository = PracticeRepository(connection)
    existing = practice_repository.get_run_for_predecessor(
        course_id=context.course_id,
        session_id=context.session_id,
        predecessor_active_recall_run_id=context.recall_run_id,
    )
    if existing is not None:
        return _handoff(connection, existing)

    adaptive = AdaptiveStudySessionService(connection)
    state = adaptive.get(
        course_id=context.course_id,
        session_id=context.session_id,
    )
    if state.state == "action_required":
        action = state.action
        if action is None:  # pragma: no cover - guarded by adaptive service
            raise RuntimeError("adaptive intervention action disappeared")
        _validate_action(
            connection,
            context=context,
            action=action,
            allowed_kinds={"remediate", "practice"},
        )
        if action["kind"] == "remediate":
            completed = adaptive.complete_remediation(
                course_id=context.course_id,
                session_id=context.session_id,
                action_id=str(action["id"]),
                expected_action_revision=int(action["revision"]),
                idempotency_key=_idempotency_key(idempotency_seed, "remediation"),
                now=now,
            )
            action = completed.current_action
            _validate_action(
                connection,
                context=context,
                action=action,
                allowed_kinds={"practice"},
            )
    elif state.state != "legacy_canonical":
        raise RuntimeError(
            "intervention Practice is unavailable in the current adaptive state"
        )

    result = TargetedPracticeProgressionService(connection).begin(
        course_id=context.course_id,
        session_id=context.session_id,
        expected_revision=context.session_revision,
        idempotency_key=_idempotency_key(idempotency_seed, "practice"),
        now=now,
    )
    stored = practice_repository.get_run(str(result.run["id"]))
    if stored is None:  # pragma: no cover - protected by progression transaction
        raise RuntimeError("intervention Practice disappeared")
    return _handoff(connection, stored)


def _validate_action(
    connection: sqlite3.Connection,
    *,
    context: InterventionContext,
    action: dict,
    allowed_kinds: set[str],
) -> None:
    if (
        action.get("course_id") != context.course_id
        or action.get("session_id") != context.session_id
        or action.get("unit_id") != context.unit_id
        or action.get("kind") not in allowed_kinds
    ):
        raise RuntimeError("adaptive action does not match the intervention context")
    identity = AdaptiveActionRepository(connection).branch_identity(str(action["id"]))
    if (
        identity is None
        or identity.get("predecessor_active_recall_run_id") != context.recall_run_id
    ):
        raise RuntimeError("adaptive action belongs to a different Recall")


def _handoff(
    connection: sqlite3.Connection,
    practice: dict,
) -> InterventionPracticeHandoff:
    checkpoint = connection.execute(
        "SELECT prompt FROM study_checkpoints WHERE id = ?",
        (practice["checkpoint_id"],),
    ).fetchone()
    session = connection.execute(
        "SELECT revision FROM study_sessions WHERE id = ? AND course_id = ?",
        (practice["session_id"], practice["course_id"]),
    ).fetchone()
    if checkpoint is None or session is None:
        raise RuntimeError("Practice handoff is unavailable")
    return InterventionPracticeHandoff(
        run_id=str(practice["id"]),
        prompt=str(checkpoint["prompt"]),
        session_revision=int(session["revision"]),
    )


def _idempotency_key(seed: str, purpose: str) -> str:
    digest = hashlib.sha256(f"{seed}\0{purpose}".encode("utf-8")).hexdigest()
    return f"intervention-{purpose}-{digest}"


__all__ = ["InterventionPracticeHandoff", "ensure_intervention_practice"]
