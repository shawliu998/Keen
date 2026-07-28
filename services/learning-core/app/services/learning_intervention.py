"""Thin Recall → bounded Agent artifact → existing Practice composition."""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from ..agent.event_stream import DurableAgentEvent
from ..database import Database
from ..learning_agent.context import (
    WHAT_NEXT,
    WHY_NOW,
    InterventionContext,
    context_fingerprint,
    legacy_context_fingerprint,
    project_intervention_eligibility,
)
from ..learning_agent.playbooks import (
    LearningInterventionIntent,
    select_playbook,
)
from ..learning_agent.practice_handoff import (
    InterventionPracticeHandoff,
    ensure_intervention_practice,
)
from ..learning_agent.profiles import (
    PROFILE_DEFINITION_HASH,
    PROFILE_ID,
    LearningInterventionRunProfile,
)
from ..learning_agent.types import FrozenInterventionSource
from ..repositories.agent_repository import AgentRepository
from ..repositories.practice_repository import PracticeRepository
from .agent_runtime import (
    AgentProviderMissingError,
    AgentProviderUnavailableError,
    AgentRuntimeManager,
)

_ACTION_LABELS = {
    LearningInterventionIntent.EXPLAIN_DIFFERENTLY: "Explain differently",
    LearningInterventionIntent.SHOW_SOURCE_EXAMPLE: "Show a source example",
    LearningInterventionIntent.TEST_ME_INSTEAD: "Test me instead",
}
_TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


class LearningInterventionNotFoundError(LookupError):
    pass


class LearningInterventionConflictError(RuntimeError):
    pass


class LearningInterventionService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeManager,
    ) -> None:
        self._database = database
        self._runtime = runtime

    def get_current(self, *, course_id: str, session_id: str) -> dict[str, Any]:
        with self._database.connection() as connection:
            eligibility = project_intervention_eligibility(
                connection,
                course_id=course_id,
                session_id=session_id,
            )
            if eligibility.context is not None:
                latest = self._latest_matching_run(
                    connection,
                    context=eligibility.context,
                )
                practice = PracticeRepository(connection).get_run_for_predecessor(
                    course_id=course_id,
                    session_id=session_id,
                    predecessor_active_recall_run_id=eligibility.context.recall_run_id,
                )
                if latest is not None:
                    snapshot = self._run_snapshot(latest)
                    if snapshot["artifact"] is not None:
                        return snapshot
                    if practice is not None and latest["status"] in _TERMINAL:
                        return self._practice_snapshot(connection, practice)
                    if self._can_reoffer_after_provider_configuration(latest):
                        return self._eligible_snapshot(eligibility.context)
                    return snapshot
                if practice is not None:
                    return self._practice_snapshot(connection, practice)
        if eligibility.reason == "eligible" and eligibility.context is not None:
            return self._eligible_snapshot(eligibility.context)
        if eligibility.reason == "source_unavailable":
            return self._source_review_snapshot(
                course_id=course_id,
                session_id=session_id,
                reason="source_unavailable",
                run=None,
            )
        return {
            "status": "ineligible",
            "courseId": course_id,
            "sessionId": session_id,
            "reason": eligibility.reason,
            "actions": [],
            "run": None,
            "artifact": None,
            "practice": None,
            "fallback": None,
        }

    async def start(
        self,
        *,
        course_id: str,
        session_id: str,
        unit_id: str,
        expected_session_revision: int,
        intent: LearningInterventionIntent,
        idempotency_key: str,
        predecessor_run_id: str | None = None,
        predecessor_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        with self._database.connection() as connection:
            eligibility = project_intervention_eligibility(
                connection,
                course_id=course_id,
                session_id=session_id,
            )
            replay = AgentRepository(connection).find_run_by_idempotency(
                kind="deep_learn",
                idempotency_key=idempotency_key,
            )
        context = eligibility.context
        if eligibility.reason != "eligible" or context is None:
            if eligibility.reason == "source_unavailable":
                return self._source_review_snapshot(
                    course_id=course_id,
                    session_id=session_id,
                    reason="source_unavailable",
                    run=None,
                )
            raise LearningInterventionConflictError(
                f"intervention is not eligible: {eligibility.reason}"
            )
        if (
            context.unit_id != unit_id
            or context.session_revision != expected_session_revision
        ):
            raise LearningInterventionConflictError(
                "intervention trigger or session revision is stale"
            )
        predecessor = self._validated_predecessor(
            context=context,
            predecessor_run_id=predecessor_run_id,
            predecessor_artifact_id=predecessor_artifact_id,
            allow_existing_replay=replay is not None,
        )

        if intent is LearningInterventionIntent.TEST_ME_INSTEAD:
            with self._database.connection() as connection:
                practice = ensure_intervention_practice(
                    connection,
                    context=context,
                    idempotency_seed=idempotency_key,
                    now=datetime.now(UTC),
                )
                return self._practice_handoff_snapshot(context, practice)

        playbook = select_playbook(
            intent,
            diagnostic_self_report_score=context.diagnostic_self_report_score,
            has_predecessor=predecessor is not None,
        )
        profile = LearningInterventionRunProfile(
            database=self._database,
            context=context,
            playbook=playbook,
            predecessor_run_id=predecessor["runId"] if predecessor else None,
            predecessor_artifact_id=(
                predecessor["artifactId"] if predecessor else None
            ),
        )
        input_data = _run_input(
            context,
            intent=intent,
            profile=profile,
            predecessor=predecessor,
        )
        try:
            run = await self._runtime.create_run(
                kind="deep_learn",
                user_intent=playbook.instruction,
                mode="study",
                input_data=input_data,
                idempotency_key=idempotency_key,
                study_session_id=session_id,
                run_profile=profile,
            )
        except ValueError as error:
            if str(error) == "idempotency key was reused with a different run payload":
                raise LearningInterventionConflictError(str(error)) from None
            raise
        except (AgentProviderMissingError, AgentProviderUnavailableError) as error:
            error_code = (
                "provider_missing"
                if isinstance(error, AgentProviderMissingError)
                else "provider_unavailable"
            )
            run = self._record_provider_missing(
                session_id=session_id,
                input_data=input_data,
                user_intent=playbook.instruction,
                idempotency_key=idempotency_key,
                error_code=error_code,
            )
        return self._run_snapshot(run)

    async def cancel(
        self,
        *,
        course_id: str,
        session_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        run = self.require_owned_run(
            course_id=course_id,
            session_id=session_id,
            run_id=run_id,
        )
        if run["status"] in _TERMINAL:
            return self._run_snapshot(run)
        accepted, updated = await self._runtime.cancel(run_id)
        if accepted and updated["status"] not in _TERMINAL:
            for _ in range(100):
                await asyncio.sleep(0.01)
                refreshed = self._runtime.get_run(run_id)
                if refreshed is None:  # pragma: no cover - ownership was verified
                    raise RuntimeError("cancelled intervention run disappeared")
                updated = refreshed
                if updated["status"] in _TERMINAL:
                    break
        return self._run_snapshot(updated)

    def require_owned_run(
        self,
        *,
        course_id: str,
        session_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        run = self._runtime.get_run(run_id)
        if (
            run is None
            or run.get("course_scope_id") != course_id
            or run.get("study_session_id") != session_id
            or not _is_intervention_input(run.get("input"))
        ):
            raise LearningInterventionNotFoundError("intervention run not found")
        return run

    def public_event(
        self,
        *,
        event: DurableAgentEvent,
        course_id: str,
        session_id: str,
        run_id: str,
    ) -> dict[str, object] | None:
        if event.event_type == "metadata":
            return {
                "id": event.id,
                "event": "started",
                "data": {"runId": run_id},
            }
        if event.event_type == "status":
            return {
                "id": event.id,
                "event": "running",
                "data": {"status": "running"},
            }
        if event.event_type == "tool_start":
            return {
                "id": event.id,
                "event": "searching_sources",
                "data": {"status": "searching_sources"},
            }
        if event.event_type == "tool_result":
            return {
                "id": event.id,
                "event": "source_context_ready",
                "data": {"status": "source_context_ready"},
            }
        artifact = _artifact_from_checkpoint(event.payload)
        if event.event_type == "checkpoint" and artifact is not None:
            return {
                "id": event.id,
                "event": "artifact_ready",
                "data": artifact,
            }
        if event.event_type == "done":
            snapshot = self.get_current(course_id=course_id, session_id=session_id)
            if snapshot["status"] == "ready":
                return {
                    "id": event.id,
                    "event": "done",
                    "data": {
                        "status": "ready",
                        "artifactId": snapshot["artifact"]["artifactId"],
                    },
                }
            return None
        if event.event_type == "error":
            run = self.require_owned_run(
                course_id=course_id,
                session_id=session_id,
                run_id=run_id,
            )
            event_name = (
                "cancelled" if run["status"] == "cancelled" else "source_review"
            )
            return {
                "id": event.id,
                "event": event_name,
                "data": {
                    "status": event_name,
                    "reason": run.get("error_code") or "provider_failed",
                },
            }
        return None

    @staticmethod
    def _latest_matching_run(
        connection: sqlite3.Connection,
        *,
        context: InterventionContext,
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT id FROM agent_runs
            WHERE study_session_id = ? AND course_scope_id = ?
              AND kind = 'deep_learn' AND mode = 'study'
              AND json_extract(input_json, '$.intervention.profileId') = ?
              AND json_extract(input_json, '$.intervention.unitId') = ?
              AND json_extract(input_json, '$.intervention.triggerAttemptId') = ?
              AND (
                    json_extract(
                        input_json,
                        '$.intervention.contextFingerprint'
                    ) = ?
                    OR (
                        json_type(
                            input_json,
                            '$.intervention.diagnosticSelfReport'
                        ) IS NULL
                        AND json_extract(
                            input_json,
                            '$.intervention.contextFingerprint'
                        ) = ?
                    )
              )
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (
                context.session_id,
                context.course_id,
                PROFILE_ID,
                context.unit_id,
                context.trigger_attempt_id,
                context_fingerprint(context),
                legacy_context_fingerprint(context),
            ),
        ).fetchone()
        return (
            AgentRepository(connection).get_run(str(row["id"]))
            if row is not None
            else None
        )

    def _can_reoffer_after_provider_configuration(
        self,
        run: dict[str, Any],
    ) -> bool:
        return (
            run["status"] == "failed"
            and run.get("error_code") == "provider_missing"
            and self._runtime.provider_configured
        )

    def _validated_predecessor(
        self,
        *,
        context: InterventionContext,
        predecessor_run_id: str | None,
        predecessor_artifact_id: str | None,
        allow_existing_replay: bool,
    ) -> dict[str, str] | None:
        if (predecessor_run_id is None) != (predecessor_artifact_id is None):
            raise LearningInterventionConflictError(
                "intervention predecessor identity is incomplete"
            )
        if allow_existing_replay:
            return (
                {
                    "runId": predecessor_run_id,
                    "artifactId": predecessor_artifact_id,
                }
                if predecessor_run_id is not None
                and predecessor_artifact_id is not None
                else None
            )
        with self._database.connection() as connection:
            latest = self._latest_matching_run(connection, context=context)
        latest_artifact = None
        if latest is not None:
            latest_artifact = next(
                (
                    artifact
                    for event in reversed(
                        self._runtime.event_store.list_events(str(latest["id"]))
                    )
                    if event.event_type == "checkpoint"
                    and (artifact := _artifact_from_checkpoint(event.payload))
                    is not None
                ),
                None,
            )
        if latest_artifact is None:
            if predecessor_run_id is not None:
                raise LearningInterventionConflictError(
                    "intervention predecessor is stale or unavailable"
                )
            return None
        if (
            predecessor_run_id != latest["id"]
            or predecessor_artifact_id != latest_artifact["artifactId"]
        ):
            raise LearningInterventionConflictError(
                "intervention predecessor is stale or unavailable"
            )
        return {
            "runId": str(latest["id"]),
            "artifactId": str(latest_artifact["artifactId"]),
        }

    def _run_snapshot(self, run: dict[str, Any]) -> dict[str, Any]:
        intervention = _intervention_input(run)
        events = self._runtime.event_store.list_events(str(run["id"]))
        artifact_event = next(
            (
                event
                for event in reversed(events)
                if event.event_type == "checkpoint"
                and _artifact_from_checkpoint(event.payload) is not None
            ),
            None,
        )
        if artifact_event is not None:
            artifact = _artifact_from_checkpoint(artifact_event.payload)
            if artifact is None:  # pragma: no cover - selected above
                raise RuntimeError("intervention artifact checkpoint was unavailable")
            return {
                "status": "ready",
                "courseId": run["course_scope_id"],
                "sessionId": run["study_session_id"],
                "reason": None,
                "actions": list(_ACTION_LABELS.values()),
                "run": _public_run(run),
                "artifact": artifact,
                "practice": artifact["whatNext"],
                "fallback": None,
            }
        if run["status"] in {"queued", "running", "waiting_approval"}:
            return {
                "status": "running" if run["status"] != "queued" else "queued",
                "courseId": run["course_scope_id"],
                "sessionId": run["study_session_id"],
                "reason": None,
                "actions": [],
                "run": _public_run(run),
                "artifact": None,
                "practice": None,
                "fallback": None,
            }
        if run["status"] == "cancelled":
            return {
                "status": "cancelled",
                "courseId": run["course_scope_id"],
                "sessionId": run["study_session_id"],
                "reason": "cancelled",
                "actions": list(_ACTION_LABELS.values()),
                "run": _public_run(run),
                "artifact": None,
                "practice": None,
                "fallback": {"action": "source_review", "label": "Return to source"},
            }
        reason = run.get("error_code") or (
            "invalid_output" if run["status"] == "completed" else "provider_failed"
        )
        return self._source_review_snapshot(
            course_id=str(run["course_scope_id"]),
            session_id=str(run["study_session_id"]),
            reason=str(reason),
            run=run,
            actions=intervention["allowedActions"],
        )

    def _eligible_snapshot(self, context: InterventionContext) -> dict[str, Any]:
        return {
            "status": "eligible",
            "courseId": context.course_id,
            "sessionId": context.session_id,
            "reason": None,
            "actions": list(_ACTION_LABELS.values()),
            "run": None,
            "artifact": {
                "whyNow": WHY_NOW,
                "sources": [_source_preview(source) for source in context.sources],
                "whatNext": {"label": WHAT_NEXT, "action": "continue_practice"},
            },
            "practice": None,
            "fallback": {"action": "source_review", "label": "Return to source"},
        }

    def _practice_snapshot(
        self,
        connection: sqlite3.Connection,
        practice: dict[str, Any],
    ) -> dict[str, Any]:
        checkpoint = connection.execute(
            "SELECT prompt FROM study_checkpoints WHERE id = ?",
            (practice["checkpoint_id"],),
        ).fetchone()
        session = connection.execute(
            "SELECT revision FROM study_sessions WHERE id = ?",
            (practice["session_id"],),
        ).fetchone()
        if checkpoint is None or session is None:
            raise RuntimeError("Practice handoff is unavailable")
        return {
            "status": "practice_ready",
            "courseId": practice["course_id"],
            "sessionId": practice["session_id"],
            "reason": None,
            "actions": [],
            "run": None,
            "artifact": None,
            "practice": {
                "label": WHAT_NEXT,
                "action": "continue_practice",
                "practiceRunId": practice["id"],
                "practicePrompt": checkpoint["prompt"],
                "sessionRevision": session["revision"],
            },
            "fallback": None,
        }

    @staticmethod
    def _practice_handoff_snapshot(
        context: InterventionContext,
        practice: InterventionPracticeHandoff,
    ) -> dict[str, Any]:
        return {
            "status": "practice_ready",
            "courseId": context.course_id,
            "sessionId": context.session_id,
            "reason": None,
            "actions": [],
            "run": None,
            "artifact": None,
            "practice": {
                "label": WHAT_NEXT,
                "action": "continue_practice",
                "practiceRunId": practice.run_id,
                "practicePrompt": practice.prompt,
                "sessionRevision": practice.session_revision,
            },
            "fallback": None,
        }

    @staticmethod
    def _source_review_snapshot(
        *,
        course_id: str,
        session_id: str,
        reason: str,
        run: dict[str, Any] | None,
        actions: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "source_review",
            "courseId": course_id,
            "sessionId": session_id,
            "reason": reason,
            "actions": actions or list(_ACTION_LABELS.values()),
            "run": _public_run(run) if run is not None else None,
            "artifact": None,
            "practice": None,
            "fallback": {
                "action": "source_review",
                "label": "Return to source",
                "retryable": reason not in {"source_unavailable"},
            },
        }

    def _record_provider_missing(
        self,
        *,
        session_id: str,
        input_data: dict[str, Any],
        user_intent: str,
        idempotency_key: str,
        error_code: str,
    ) -> dict:
        proposed_run_id = f"run-{uuid.uuid4().hex}"
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            run = repository.create_run(
                run_id=proposed_run_id,
                kind="deep_learn",
                provider="unavailable",
                model="unavailable",
                user_intent=user_intent,
                mode="study",
                prompt_version=PROFILE_ID,
                input_data=input_data,
                idempotency_key=idempotency_key,
                study_session_id=session_id,
            )
        if run["id"] != proposed_run_id:
            return run
        self._runtime.event_store.start_run(
            str(run["id"]),
            metadata={
                "runId": run["id"],
                "provider": "unavailable",
                "model": "unavailable",
                "providerVersion": PROFILE_ID,
            },
        )
        self._runtime.event_store.finish_run(
            str(run["id"]),
            status="failed",
            error_code=error_code,
            error_detail="The configured provider was unavailable for this intervention",
        )
        updated = self._runtime.get_run(str(run["id"]))
        if updated is None:  # pragma: no cover
            raise RuntimeError("provider-missing intervention run disappeared")
        return updated


def _run_input(
    context: InterventionContext,
    *,
    intent: LearningInterventionIntent,
    profile: LearningInterventionRunProfile,
    predecessor: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "intervention": {
            "profileId": profile.id,
            "profileDefinitionHash": profile.definition_hash,
            "playbookSlug": profile.playbook.slug,
            "playbookVersion": profile.playbook.version,
            "playbookDefinitionHash": profile.playbook.definition_hash,
            "intent": intent.value,
            "predecessor": predecessor,
            "courseId": context.course_id,
            "sessionId": context.session_id,
            "sessionRevision": context.session_revision,
            "unitId": context.unit_id,
            "unitTitle": context.unit_title,
            "unitObjective": context.unit_objective,
            "goal": context.goal,
            "triggerRecallRunId": context.recall_run_id,
            "triggerAttemptId": context.trigger_attempt_id,
            "triggerEvaluationId": context.trigger_evaluation_id,
            "diagnosticSelfReport": (
                {
                    "evidenceId": context.diagnostic_self_report_evidence_id,
                    "score": context.diagnostic_self_report_score,
                }
                if context.diagnostic_self_report_evidence_id is not None
                and context.diagnostic_self_report_score is not None
                else None
            ),
            "recallPrompt": context.recall_prompt,
            "learnerResponse": context.learner_response,
            "whyNow": WHY_NOW,
            "whatNext": WHAT_NEXT,
            "allowedActions": list(_ACTION_LABELS.values()),
            "sources": [
                source.model_dump(mode="json", by_alias=True)
                for source in context.sources
            ],
            "contextFingerprint": context_fingerprint(context),
        },
        "artifactContract": {
            "schemaVersion": 1,
            "requiredFields": [
                "schemaVersion",
                "summary",
                "explanationMarkdown",
                "selectedSourceHandles",
            ],
            "outputExample": {
                "schemaVersion": 1,
                "summary": "Brief source-grounded clarification.",
                "explanationMarkdown": "Explain the idea with cited source support.",
                "selectedSourceHandles": [context.sources[0].source_handle],
            },
            "selectedSourceHandleCount": {"minimum": 1, "maximum": 8},
            "forbiddenAuthority": [
                "grading",
                "mastery",
                "bkt",
                "fsrs",
                "feed",
                "task_completion",
                "session_completion",
            ],
        },
    }


def _intervention_input(run: dict[str, Any]) -> dict[str, Any]:
    value = run.get("input")
    if not isinstance(value, dict):
        raise TypeError("intervention run input is unavailable")
    intervention = value.get("intervention")
    if (
        not isinstance(intervention, dict)
        or intervention.get("profileId") != PROFILE_ID
    ):
        raise RuntimeError("intervention run profile is unavailable")
    return intervention


def _is_intervention_input(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("intervention"), dict)
        and value["intervention"].get("profileId") == PROFILE_ID
        and value["intervention"].get("profileDefinitionHash")
        == PROFILE_DEFINITION_HASH
    )


def _is_artifact_payload(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("kind") == "learning_intervention_artifact"
        and payload.get("profileId") == PROFILE_ID
        and payload.get("profileDefinitionHash") == PROFILE_DEFINITION_HASH
    )


def _artifact_from_checkpoint(payload: object) -> dict[str, Any] | None:
    """Extract a profile artifact from either historical or enveloped events."""

    candidate = payload
    if (
        isinstance(payload, dict)
        and payload.get("label") == "completion_published"
        and isinstance(payload.get("data"), dict)
    ):
        candidate = payload["data"]
    return candidate if _is_artifact_payload(candidate) else None


def _source_preview(source: FrozenInterventionSource) -> dict[str, object]:
    return {
        "sourceHandle": source.source_handle,
        "documentId": source.document_id,
        "documentName": source.document_name,
        "pageNumber": source.page_number,
        "sectionPath": source.section_path,
        "metadata": source.metadata,
    }


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "status": run["status"],
        "provider": run["provider"],
        "model": run["model"],
        "createdAt": run["created_at"],
        "updatedAt": run["updated_at"],
        "errorCode": run.get("error_code"),
    }


__all__ = [
    "LearningInterventionConflictError",
    "LearningInterventionNotFoundError",
    "LearningInterventionService",
]
