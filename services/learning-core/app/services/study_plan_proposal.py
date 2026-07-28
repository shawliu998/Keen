"""Bounded Agent proposal → explicit deterministic plan decision."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ..database import Database
from ..learning_agent.context import (
    context_fingerprint as intervention_context_fingerprint,
)
from ..learning_agent.context import (
    project_intervention_eligibility,
)
from ..learning_agent.plan_proposal import (
    PlanProposalContext,
    plan_proposal_context_fingerprint,
    project_plan_proposal_context,
)
from ..learning_agent.plan_proposal_profile import (
    PLAN_PROPOSAL_PROFILE_HASH,
    PLAN_PROPOSAL_PROFILE_ID,
    StudyPlanProposalRunProfile,
)
from ..learning_agent.profiles import (
    PROFILE_DEFINITION_HASH as INTERVENTION_PROFILE_HASH,
)
from ..learning_agent.profiles import (
    PROFILE_ID as INTERVENTION_PROFILE_ID,
)
from ..repositories import dump_json, load_json
from ..repositories.agent_repository import AgentRepository
from ..repositories.study_repository import StudyRepository, StudyUnitInput
from .agent_runtime import (
    AgentProviderMissingError,
    AgentProviderUnavailableError,
    AgentRuntimeManager,
)

_USER_INTENT = (
    "Propose one source-grounded prerequisite unit before the trusted unstarted "
    "target. Return only the strict Plan Proposal JSON. Do not apply or claim to "
    "apply the plan, grade the learner, or change learning state."
)
_UNDO_WINDOW = timedelta(minutes=10)
_ADAPTIVE_TRIGGER_REASON = "low_confidence_incorrect_recall_after_intervention"
_MAX_LOW_CONFIDENCE_SCORE = 0.4


class StudyPlanProposalConflictError(RuntimeError):
    pass


class StudyPlanProposalService:
    def __init__(self, database: Database, runtime: AgentRuntimeManager) -> None:
        self._database = database
        self._runtime = runtime

    async def start(
        self,
        *,
        course_id: str,
        session_id: str,
        expected_session_revision: int,
        expected_plan_version: int,
        target_unit_id: str,
        idempotency_key: str,
        trigger_origin: str = "learner_request",
    ) -> dict[str, Any]:
        trigger = self._start_trigger(
            course_id=course_id,
            session_id=session_id,
            origin=trigger_origin,
        )
        try:
            with self._database.connection() as connection:
                context = project_plan_proposal_context(
                    connection,
                    course_id=course_id,
                    session_id=session_id,
                    expected_session_revision=expected_session_revision,
                    expected_plan_version=expected_plan_version,
                    target_unit_id=target_unit_id,
                )
        except (LookupError, RuntimeError, ValueError) as error:
            raise StudyPlanProposalConflictError(str(error)) from None

        profile = StudyPlanProposalRunProfile(
            database=self._database,
            context=context,
        )
        input_data = _run_input(context, profile=profile, trigger=trigger)
        if trigger["origin"] == "adaptive_evidence":
            idempotency_key = _adaptive_idempotency_key(
                context=context,
                trigger=trigger,
            )
        try:
            run = await self._runtime.create_run(
                kind="deep_learn",
                user_intent=_USER_INTENT,
                mode="plan",
                input_data=input_data,
                idempotency_key=idempotency_key,
                study_session_id=session_id,
                run_profile=profile,
            )
        except ValueError as error:
            if str(error) == "idempotency key was reused with a different run payload":
                raise StudyPlanProposalConflictError(str(error)) from None
            raise
        except (AgentProviderMissingError, AgentProviderUnavailableError) as error:
            code = (
                "provider_missing"
                if isinstance(error, AgentProviderMissingError)
                else "provider_unavailable"
            )
            run = self._record_unavailable(
                session_id=session_id,
                input_data=input_data,
                idempotency_key=idempotency_key,
                error_code=code,
            )
        return self._run_snapshot(run)

    def get_current(self, *, course_id: str, session_id: str) -> dict[str, Any]:
        with self._database.connection() as connection:
            run = connection.execute(
                """
                SELECT id FROM agent_runs
                WHERE kind = 'deep_learn'
                  AND study_session_id = ?
                  AND course_scope_id = ?
                  AND json_extract(input_json, '$.planProposal.profileId') = ?
                  AND json_extract(input_json, '$.planProposal.profileDefinitionHash') = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (
                    session_id,
                    course_id,
                    PLAN_PROPOSAL_PROFILE_ID,
                    PLAN_PROPOSAL_PROFILE_HASH,
                ),
            ).fetchone()
            value = (
                AgentRepository(connection).get_run(str(run["id"]))
                if run is not None
                else None
            )
        if value is None:
            return {
                "status": "none",
                "courseId": course_id,
                "sessionId": session_id,
                "reason": None,
                "run": None,
                "artifact": None,
                "receipt": None,
                "trigger": self._adaptive_trigger(
                    course_id=course_id,
                    session_id=session_id,
                ),
            }
        return self._run_snapshot(value)

    def decide(
        self,
        *,
        course_id: str,
        session_id: str,
        artifact_id: str,
        expected_session_revision: int,
        expected_plan_version: int,
        decision: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if decision not in {"accept", "keep"}:
            raise ValueError("unsupported plan proposal decision")
        snapshot = self.get_current(course_id=course_id, session_id=session_id)
        artifact = snapshot.get("artifact")
        run = snapshot.get("run")
        trigger = snapshot.get("trigger")
        if (
            snapshot["status"] not in {"ready", "accepted", "rejected", "undone"}
            or not isinstance(artifact, dict)
            or artifact.get("artifactId") != artifact_id
            or not isinstance(run, dict)
            or not isinstance(trigger, dict)
        ):
            raise StudyPlanProposalConflictError(
                "plan proposal is not current or decision-ready"
            )
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    """
                    SELECT * FROM study_plan_proposals
                    WHERE validated_artifact_id = ?
                    """,
                    (artifact_id,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["decision_idempotency_key"] != idempotency_key
                        or (
                            decision == "accept"
                            and existing["status"] not in {"accepted", "undone"}
                        )
                        or (decision == "keep" and existing["status"] != "rejected")
                    ):
                        raise StudyPlanProposalConflictError(
                            "plan proposal was already resolved differently"
                        )
                    connection.rollback()
                    return self.get_current(
                        course_id=course_id,
                        session_id=session_id,
                    )

                context, base_plan = self._decision_context(
                    connection,
                    course_id=course_id,
                    session_id=session_id,
                    artifact=artifact,
                    expected_session_revision=expected_session_revision,
                    expected_plan_version=expected_plan_version,
                )
                now = datetime.now(UTC)
                proposal_id = _proposal_id(artifact_id)
                accepted_version: int | None = None
                undo_until: str | None = None
                if decision == "accept":
                    accepted_version = self._next_plan_version(
                        connection,
                        session_id=session_id,
                    )
                    self._save_decision_plan(
                        connection,
                        proposal_id=proposal_id,
                        session_id=session_id,
                        version=accepted_version,
                        base_plan=base_plan,
                        artifact=artifact,
                        include_proposal=True,
                        created_at=now.isoformat(),
                    )
                    status = "accepted"
                    undo_until = (now + _UNDO_WINDOW).isoformat()
                else:
                    status = "rejected"

                connection.execute(
                    """
                    INSERT INTO study_plan_proposals
                        (id, run_id, validated_artifact_id, course_id,
                         study_session_id, base_plan_id, base_plan_version,
                         base_session_revision, trigger_event_ids_json,
                         proposal_json, reason_json, status,
                         accepted_plan_version, undo_plan_version, undo_until,
                         decision_idempotency_key, undo_idempotency_key,
                         created_at, resolved_at, undone_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, NULL)
                    """,
                    (
                        proposal_id,
                        run["id"],
                        artifact_id,
                        course_id,
                        session_id,
                        context.plan_id,
                        context.plan_version,
                        context.session_revision,
                        dump_json(trigger.get("evidenceIds", [])),
                        dump_json(artifact),
                        dump_json(
                            {
                                "reason": artifact["reason"],
                                "trigger": trigger,
                            }
                        ),
                        status,
                        accepted_version,
                        undo_until,
                        idempotency_key,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.get_current(course_id=course_id, session_id=session_id)

    def undo(
        self,
        *,
        course_id: str,
        session_id: str,
        proposal_id: str,
        expected_session_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT * FROM study_plan_proposals
                    WHERE id = ? AND course_id = ? AND study_session_id = ?
                    """,
                    (proposal_id, course_id, session_id),
                ).fetchone()
                if row is None:
                    raise StudyPlanProposalConflictError(
                        "accepted plan adjustment was not found"
                    )
                if row["status"] == "undone":
                    if row["undo_idempotency_key"] != idempotency_key:
                        raise StudyPlanProposalConflictError(
                            "plan adjustment Undo was already resolved differently"
                        )
                    connection.rollback()
                    return self.get_current(
                        course_id=course_id,
                        session_id=session_id,
                    )
                if row["status"] != "accepted":
                    raise StudyPlanProposalConflictError(
                        "only an accepted plan adjustment can be undone"
                    )
                now = datetime.now(UTC)
                if (
                    row["undo_until"] is None
                    or datetime.fromisoformat(str(row["undo_until"])) < now
                ):
                    raise StudyPlanProposalConflictError(
                        "the safe Undo window has expired; the adjusted plan was retained"
                    )
                session = StudyRepository(connection).get_session(session_id)
                if (
                    session is None
                    or int(session["revision"]) != expected_session_revision
                    or int(session["revision"]) != int(row["base_session_revision"])
                ):
                    raise StudyPlanProposalConflictError(
                        "learning advanced after the adjustment; the current plan was retained"
                    )
                current = connection.execute(
                    """
                    SELECT u.id, u.status, p.id AS plan_id
                    FROM study_units u
                    JOIN study_plan_versions p ON p.id = u.plan_version_id
                    WHERE u.id = ? AND p.session_id = ?
                    """,
                    (session["current_unit_id"], session_id),
                ).fetchone()
                if (
                    current is None
                    or current["status"] != "active"
                    or current["plan_id"] != row["base_plan_id"]
                ):
                    raise StudyPlanProposalConflictError(
                        "learning advanced into the adjusted plan; the current plan was retained"
                    )
                accepted_plan = connection.execute(
                    """
                    SELECT id FROM study_plan_versions
                    WHERE session_id = ? AND version = ?
                    """,
                    (session_id, row["accepted_plan_version"]),
                ).fetchone()
                if accepted_plan is None or self._plan_has_learning_evidence(
                    connection,
                    plan_id=str(accepted_plan["id"]),
                ):
                    raise StudyPlanProposalConflictError(
                        "learning evidence now depends on the adjusted plan; it was retained"
                    )
                base_plan = StudyRepository(connection).get_plan_by_id(
                    str(row["base_plan_id"])
                )
                if base_plan is None:
                    raise StudyPlanProposalConflictError(
                        "the previous plan is unavailable; the current plan was retained"
                    )
                artifact = load_json(str(row["proposal_json"]))
                if not isinstance(artifact, dict):
                    raise TypeError("stored plan proposal is invalid")
                undo_version = self._next_plan_version(
                    connection,
                    session_id=session_id,
                )
                self._save_decision_plan(
                    connection,
                    proposal_id=proposal_id,
                    session_id=session_id,
                    version=undo_version,
                    base_plan=base_plan,
                    artifact=artifact,
                    include_proposal=False,
                    created_at=now.isoformat(),
                )
                cursor = connection.execute(
                    """
                    UPDATE study_plan_proposals
                    SET status = 'undone', undo_plan_version = ?,
                        undo_idempotency_key = ?, undone_at = ?
                    WHERE id = ? AND status = 'accepted'
                    """,
                    (undo_version, idempotency_key, now.isoformat(), proposal_id),
                )
                if cursor.rowcount != 1:
                    raise StudyPlanProposalConflictError(
                        "plan adjustment changed before Undo"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.get_current(course_id=course_id, session_id=session_id)

    def _run_snapshot(self, run: dict[str, Any]) -> dict[str, Any]:
        artifact = next(
            (
                candidate
                for event in reversed(
                    self._runtime.event_store.list_events(str(run["id"]))
                )
                if event.event_type == "checkpoint"
                and (candidate := _artifact_from_checkpoint(event.payload)) is not None
            ),
            None,
        )
        if artifact is not None:
            resolved = self._resolved_decision(
                run=run,
                artifact=artifact,
            )
            if resolved is not None:
                return resolved
            status = "ready" if self._base_is_current(run, artifact) else "stale"
            public_artifact = dict(artifact)
            public_artifact["decision"] = {
                "status": "pending" if status == "ready" else "unapplied",
                "applyAvailable": status == "ready",
            }
            return {
                "status": status,
                "courseId": run["course_scope_id"],
                "sessionId": run["study_session_id"],
                "reason": None if status == "ready" else "base_plan_changed",
                "run": _public_run(run),
                "artifact": public_artifact,
                "receipt": None,
                "trigger": _trigger_from_run(run),
            }
        if run["status"] in {"queued", "running", "waiting_approval"}:
            return {
                "status": "queued" if run["status"] == "queued" else "running",
                "courseId": run["course_scope_id"],
                "sessionId": run["study_session_id"],
                "reason": None,
                "run": _public_run(run),
                "artifact": None,
                "receipt": None,
                "trigger": _trigger_from_run(run),
            }
        return {
            "status": "unavailable",
            "courseId": run["course_scope_id"],
            "sessionId": run["study_session_id"],
            "reason": run.get("error_code") or "invalid_output",
            "run": _public_run(run),
            "artifact": None,
            "receipt": None,
            "trigger": _trigger_from_run(run),
        }

    def _resolved_decision(
        self,
        *,
        run: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM study_plan_proposals
                WHERE run_id = ? AND validated_artifact_id = ?
                  AND course_id = ? AND study_session_id = ?
                """,
                (
                    run["id"],
                    artifact["artifactId"],
                    run["course_scope_id"],
                    run["study_session_id"],
                ),
            ).fetchone()
        if row is None:
            return None
        status = str(row["status"])
        public_artifact = dict(artifact)
        if status == "invalidated":
            public_artifact["decision"] = {
                "status": "unapplied",
                "applyAvailable": False,
            }
            return {
                "status": "stale",
                "courseId": run["course_scope_id"],
                "sessionId": run["study_session_id"],
                "reason": "base_plan_changed",
                "run": _public_run(run),
                "artifact": public_artifact,
                "receipt": None,
                "trigger": _trigger_from_run(run),
            }
        public_artifact["decision"] = {
            "status": status,
            "applyAvailable": False,
        }
        return {
            "status": status,
            "courseId": run["course_scope_id"],
            "sessionId": run["study_session_id"],
            "reason": None,
            "run": _public_run(run),
            "artifact": public_artifact,
            "receipt": _receipt(dict(row)),
            "trigger": _trigger_from_run(run),
        }

    def _start_trigger(
        self,
        *,
        course_id: str,
        session_id: str,
        origin: str,
    ) -> dict[str, Any]:
        if origin == "learner_request":
            return {
                "origin": "learner_request",
                "reasonCode": "learner_requested_prerequisite",
                "evidenceIds": [],
                "whyNow": "You asked Keen to suggest one source-grounded prerequisite.",
                "learnerApprovalRequired": True,
            }
        if origin != "adaptive_evidence":
            raise ValueError("unsupported plan proposal trigger origin")
        trigger = self._adaptive_trigger(
            course_id=course_id,
            session_id=session_id,
        )
        if trigger is None:
            raise StudyPlanProposalConflictError(
                "the saved learning evidence does not support an Agent plan suggestion"
            )
        return trigger

    def _adaptive_trigger(
        self,
        *,
        course_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Project one proactive trigger from authoritative persisted evidence."""

        with self._database.connection() as connection:
            eligibility = project_intervention_eligibility(
                connection,
                course_id=course_id,
                session_id=session_id,
            )
            context = eligibility.context
            if (
                eligibility.reason != "eligible"
                or context is None
                or context.diagnostic_self_report_evidence_id is None
                or context.diagnostic_self_report_score is None
                or context.diagnostic_self_report_score > _MAX_LOW_CONFIDENCE_SCORE
            ):
                return None
            row = connection.execute(
                """
                SELECT run.id AS run_id,
                       COALESCE(
                           json_extract(event.payload_json, '$.artifactId'),
                           json_extract(event.payload_json, '$.data.artifactId')
                       ) AS artifact_id
                FROM agent_runs run
                JOIN agent_events event ON event.run_id = run.id
                WHERE run.study_session_id = ?
                  AND run.course_scope_id = ?
                  AND run.kind = 'deep_learn'
                  AND run.mode = 'study'
                  AND run.status = 'completed'
                  AND json_extract(
                        run.input_json,
                        '$.intervention.profileId'
                      ) = ?
                  AND json_extract(
                        run.input_json,
                        '$.intervention.profileDefinitionHash'
                      ) = ?
                  AND json_extract(
                        run.input_json,
                        '$.intervention.contextFingerprint'
                      ) = ?
                  AND event.event_type = 'checkpoint'
                  AND COALESCE(
                        json_extract(event.payload_json, '$.kind'),
                        json_extract(event.payload_json, '$.data.kind')
                      ) = 'learning_intervention_artifact'
                  AND COALESCE(
                        json_extract(event.payload_json, '$.profileId'),
                        json_extract(event.payload_json, '$.data.profileId')
                      ) = ?
                  AND COALESCE(
                        json_extract(
                            event.payload_json,
                            '$.profileDefinitionHash'
                        ),
                        json_extract(
                            event.payload_json,
                            '$.data.profileDefinitionHash'
                        )
                      ) = ?
                ORDER BY run.created_at DESC, run.id DESC, event.sequence DESC
                LIMIT 1
                """,
                (
                    session_id,
                    course_id,
                    INTERVENTION_PROFILE_ID,
                    INTERVENTION_PROFILE_HASH,
                    intervention_context_fingerprint(context),
                    INTERVENTION_PROFILE_ID,
                    INTERVENTION_PROFILE_HASH,
                ),
            ).fetchone()
        if row is None or not isinstance(row["artifact_id"], str):
            return None
        return {
            "origin": "adaptive_evidence",
            "reasonCode": _ADAPTIVE_TRIGGER_REASON,
            "evidenceIds": [
                context.diagnostic_self_report_evidence_id,
                context.trigger_evaluation_id,
                str(row["artifact_id"]),
            ],
            "whyNow": (
                "Your opening confidence was low, the latest Recall was "
                "incorrect, and a source-grounded intervention is ready."
            ),
            "learnerApprovalRequired": True,
        }

    def _decision_context(
        self,
        connection,
        *,
        course_id: str,
        session_id: str,
        artifact: dict[str, Any],
        expected_session_revision: int,
        expected_plan_version: int,
    ) -> tuple[PlanProposalContext, dict[str, Any]]:
        if (
            artifact.get("baseSessionRevision") != expected_session_revision
            or artifact.get("basePlanVersion") != expected_plan_version
        ):
            raise StudyPlanProposalConflictError(
                "plan proposal decision uses a stale session or plan revision"
            )
        operation = artifact.get("operation")
        if not isinstance(operation, dict):
            raise TypeError("plan proposal operation is invalid")
        try:
            context = project_plan_proposal_context(
                connection,
                course_id=course_id,
                session_id=session_id,
                expected_session_revision=expected_session_revision,
                expected_plan_version=expected_plan_version,
                target_unit_id=str(operation["beforeUnitId"]),
            )
        except (LookupError, RuntimeError, ValueError) as error:
            raise StudyPlanProposalConflictError(str(error)) from None
        if context.plan_id != artifact.get("basePlanId") or [
            unit.id for unit in context.units
        ] != [
            unit.get("id")
            for unit in artifact.get("currentPlan", {}).get("units", [])
            if isinstance(unit, dict)
        ]:
            raise StudyPlanProposalConflictError(
                "plan proposal base no longer matches the saved plan"
            )
        source_handles = {source.source_handle for source in context.sources}
        selected_handles = operation.get("selectedSourceHandles")
        if (
            not isinstance(selected_handles, list)
            or not selected_handles
            or any(handle not in source_handles for handle in selected_handles)
        ):
            raise StudyPlanProposalConflictError(
                "plan proposal source scope is no longer valid"
            )
        base_plan = StudyRepository(connection).get_plan_by_id(context.plan_id)
        if base_plan is None:
            raise StudyPlanProposalConflictError("study plan is unavailable")
        return context, base_plan

    @staticmethod
    def _next_plan_version(connection, *, session_id: str) -> int:
        return int(
            connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM study_plan_versions WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()[0]
        )

    @staticmethod
    def _plan_has_learning_evidence(connection, *, plan_id: str) -> bool:
        non_quiet = connection.execute(
            """
            SELECT 1 FROM study_units
            WHERE plan_version_id = ?
              AND status NOT IN ('completed', 'locked')
            LIMIT 1
            """,
            (plan_id,),
        ).fetchone()
        checkpoint = connection.execute(
            """
            SELECT 1 FROM study_checkpoints c
            JOIN study_units u ON u.id = c.unit_id
            WHERE u.plan_version_id = ?
            LIMIT 1
            """,
            (plan_id,),
        ).fetchone()
        return non_quiet is not None or checkpoint is not None

    @staticmethod
    def _save_decision_plan(
        connection,
        *,
        proposal_id: str,
        session_id: str,
        version: int,
        base_plan: dict[str, Any],
        artifact: dict[str, Any],
        include_proposal: bool,
        created_at: str,
    ) -> None:
        session = StudyRepository(connection).get_session(session_id)
        if session is None or session["current_unit_id"] is None:
            raise StudyPlanProposalConflictError(
                "plan adjustment requires one active current unit"
            )
        raw_units = base_plan["units"]
        if not isinstance(raw_units, list):
            raise TypeError("stored study plan units are invalid")
        current_ids = [
            str(unit["id"])
            for unit in raw_units
            if unit["id"] == session["current_unit_id"] and unit["status"] == "active"
        ]
        if len(current_ids) != 1:
            raise StudyPlanProposalConflictError(
                "current learning step no longer matches the proposal base"
            )
        operation = artifact.get("operation")
        sources = artifact.get("sources")
        if not isinstance(operation, dict) or not isinstance(sources, list):
            raise TypeError("stored plan proposal is invalid")
        source_ids = {
            str(source["sourceHandle"]): str(source["chunkId"])
            for source in sources
            if isinstance(source, dict)
            and isinstance(source.get("sourceHandle"), str)
            and isinstance(source.get("chunkId"), str)
        }
        selected_handles = operation.get("selectedSourceHandles")
        if not isinstance(selected_handles, list):
            raise TypeError("stored plan proposal handles are invalid")
        selected_source_ids = [source_ids[str(handle)] for handle in selected_handles]
        target = next(
            (unit for unit in raw_units if unit["id"] == operation.get("beforeUnitId")),
            None,
        )
        if target is None:
            raise StudyPlanProposalConflictError(
                "plan proposal target no longer exists"
            )
        units: list[StudyUnitInput] = []
        for raw in raw_units:
            if include_proposal and raw["id"] == target["id"]:
                units.append(
                    {
                        "id": _unit_id(proposal_id, version, "proposal"),
                        "title": str(operation["title"]),
                        "objective": str(operation["objective"]),
                        "estimated_minutes": int(operation["estimatedMinutes"]),
                        "concept_id": target["concept_id"],
                        "concept_ids": list(target["concept_ids"]),
                        "source_chunk_ids": selected_source_ids,
                        "content": "",
                        "status": "locked",
                    }
                )
            copied_status = (
                "completed" if raw["status"] in {"completed", "active"} else "locked"
            )
            units.append(
                {
                    "id": _unit_id(proposal_id, version, str(raw["id"])),
                    "title": str(raw["title"]),
                    "objective": str(raw["objective"]),
                    "estimated_minutes": int(raw["estimated_minutes"]),
                    "concept_id": raw["concept_id"],
                    "concept_ids": list(raw["concept_ids"]),
                    "source_chunk_ids": list(raw["source_chunk_ids"]),
                    "content": str(raw["content"]),
                    "status": copied_status,
                }
            )
        if not 2 <= len(units) <= 8:
            raise StudyPlanProposalConflictError(
                "adjusted study plan exceeds the supported unit count"
            )
        StudyRepository(connection).save_plan(
            plan_id=_plan_id(proposal_id, version),
            session_id=session_id,
            version=version,
            rationale=(
                "Accepted source-grounded prerequisite"
                if include_proposal
                else "Undo restored the previous unstarted sequence"
            ),
            units=units,
            created_at=created_at,
            commit=False,
        )

    def _base_is_current(
        self,
        run: dict[str, Any],
        artifact: dict[str, Any],
    ) -> bool:
        with self._database.connection() as connection:
            session = StudyRepository(connection).get_session(
                str(run["study_session_id"])
            )
            plan = StudyRepository(connection).get_current_or_latest_plan(
                str(run["study_session_id"])
            )
        return (
            session is not None
            and plan is not None
            and int(session["revision"]) == artifact["baseSessionRevision"]
            and str(plan["id"]) == artifact["basePlanId"]
            and int(plan["version"]) == artifact["basePlanVersion"]
        )

    def _record_unavailable(
        self,
        *,
        session_id: str,
        input_data: dict[str, Any],
        idempotency_key: str,
        error_code: str,
    ) -> dict[str, Any]:
        proposed_id = f"run-{uuid.uuid4().hex}"
        with self._database.connection() as connection:
            run = AgentRepository(connection).create_run(
                run_id=proposed_id,
                kind="deep_learn",
                provider="unavailable",
                model="unavailable",
                user_intent=_USER_INTENT,
                mode="plan",
                prompt_version=PLAN_PROPOSAL_PROFILE_ID,
                input_data=input_data,
                idempotency_key=idempotency_key,
                study_session_id=session_id,
            )
        if run["id"] != proposed_id:
            return run
        self._runtime.event_store.start_run(
            str(run["id"]),
            metadata={
                "runId": run["id"],
                "provider": "unavailable",
                "model": "unavailable",
                "providerVersion": PLAN_PROPOSAL_PROFILE_ID,
            },
        )
        self._runtime.event_store.finish_run(
            str(run["id"]),
            status="failed",
            error_code=error_code,
            error_detail="The configured provider was unavailable for this proposal",
        )
        updated = self._runtime.get_run(str(run["id"]))
        if updated is None:  # pragma: no cover
            raise RuntimeError("plan proposal run disappeared")
        return updated


def _run_input(
    context: PlanProposalContext,
    *,
    profile: StudyPlanProposalRunProfile,
    trigger: dict[str, Any],
) -> dict[str, Any]:
    return {
        "planProposal": {
            "profileId": profile.id,
            "profileDefinitionHash": profile.definition_hash,
            "request": "insert_source_grounded_prerequisite",
            "explicitLearnerRequest": trigger["origin"] == "learner_request",
            "agentTriggered": trigger["origin"] == "adaptive_evidence",
            "learnerApprovalRequired": True,
            "trigger": trigger,
            "courseId": context.course_id,
            "sessionId": context.session_id,
            "sessionRevision": context.session_revision,
            "goal": context.goal,
            "planId": context.plan_id,
            "planVersion": context.plan_version,
            "targetUnit": {
                "id": context.target_unit.id,
                "title": context.target_unit.title,
                "objective": context.target_unit.objective,
                "estimatedMinutes": context.target_unit.estimated_minutes,
                "status": context.target_unit.status,
            },
            "currentUnits": [
                {
                    "id": unit.id,
                    "ordinal": unit.ordinal,
                    "title": unit.title,
                    "objective": unit.objective,
                    "estimatedMinutes": unit.estimated_minutes,
                    "status": unit.status,
                }
                for unit in context.units
            ],
            "sources": [
                source.model_dump(mode="json", by_alias=True)
                for source in context.sources
            ],
            "contextFingerprint": plan_proposal_context_fingerprint(context),
            "authority": {
                "canApplyPlan": False,
                "canChangeSession": False,
                "canGrade": False,
            },
        },
        "artifactContract": {
            "schemaVersion": 1,
            "requiredFields": ["schemaVersion", "summary", "reason", "operation"],
            "outputExample": {
                "schemaVersion": 1,
                "summary": "Add one short prerequisite before the selected unit.",
                "reason": "The cited source introduces a concept the selected unit assumes.",
                "operation": {
                    "kind": "insert_prerequisite",
                    "beforeUnitId": context.target_unit.id,
                    "title": "Prerequisite refresher",
                    "objective": "Connect the prerequisite idea to the selected unit.",
                    "estimatedMinutes": 10,
                    "selectedSourceHandles": [context.sources[0].source_handle],
                },
            },
            "operation": {
                "kind": "insert_prerequisite",
                "beforeUnitId": context.target_unit.id,
                "estimatedMinutes": {"minimum": 5, "maximum": 30},
                "selectedSourceHandles": [
                    source.source_handle for source in context.sources
                ],
            },
            "forbiddenAuthority": [
                "apply_plan",
                "plan_pointer",
                "grading",
                "mastery",
                "bkt",
                "fsrs",
                "task_completion",
                "session_completion",
            ],
        },
    }


def _trigger_from_run(run: dict[str, Any]) -> dict[str, Any] | None:
    value = run.get("input")
    if not isinstance(value, dict):
        return None
    proposal = value.get("planProposal")
    if not isinstance(proposal, dict):
        return None
    trigger = proposal.get("trigger")
    if not isinstance(trigger, dict):
        if (
            trigger is None
            and proposal.get("explicitLearnerRequest") is True
            and proposal.get("agentTriggered") is not True
        ):
            return {
                "origin": "learner_request",
                "reasonCode": "learner_requested_prerequisite",
                "evidenceIds": [],
                "whyNow": (
                    "You asked Keen to suggest one source-grounded prerequisite."
                ),
                "learnerApprovalRequired": True,
            }
        return None
    origin = trigger.get("origin")
    evidence_ids = trigger.get("evidenceIds")
    if (
        origin not in {"learner_request", "adaptive_evidence"}
        or not isinstance(trigger.get("reasonCode"), str)
        or not isinstance(trigger.get("whyNow"), str)
        or trigger.get("learnerApprovalRequired") is not True
        or not isinstance(evidence_ids, list)
        or any(not isinstance(value, str) or not value for value in evidence_ids)
    ):
        raise TypeError("stored plan proposal trigger is invalid")
    return {
        "origin": origin,
        "reasonCode": trigger["reasonCode"],
        "evidenceIds": list(evidence_ids),
        "whyNow": trigger["whyNow"],
        "learnerApprovalRequired": True,
    }


def _adaptive_idempotency_key(
    *,
    context: PlanProposalContext,
    trigger: dict[str, Any],
) -> str:
    digest = hashlib.sha256(
        dump_json(
            {
                "sessionId": context.session_id,
                "sessionRevision": context.session_revision,
                "planId": context.plan_id,
                "planVersion": context.plan_version,
                "targetUnitId": context.target_unit.id,
                "trigger": trigger,
            }
        ).encode("utf-8")
    ).hexdigest()
    return f"adaptive-plan-proposal-{digest}"


def _artifact_from_checkpoint(payload: object) -> dict[str, Any] | None:
    candidate = payload
    if (
        isinstance(payload, dict)
        and payload.get("label") == "completion_published"
        and isinstance(payload.get("data"), dict)
    ):
        candidate = payload["data"]
    return (
        candidate
        if isinstance(candidate, dict)
        and candidate.get("kind") == "study_plan_proposal_artifact"
        and candidate.get("profileId") == PLAN_PROPOSAL_PROFILE_ID
        and candidate.get("profileDefinitionHash") == PLAN_PROPOSAL_PROFILE_HASH
        else None
    )


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


def _proposal_id(artifact_id: str) -> str:
    return (
        "plan-proposal-" + hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()[:32]
    )


def _plan_id(proposal_id: str, version: int) -> str:
    digest = hashlib.sha256(f"{proposal_id}\0plan\0{version}".encode()).hexdigest()
    return f"plan-{digest[:32]}"


def _unit_id(proposal_id: str, version: int, source: str) -> str:
    digest = hashlib.sha256(
        f"{proposal_id}\0unit\0{version}\0{source}".encode()
    ).hexdigest()
    return f"unit-{digest[:32]}"


def _receipt(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row["status"])
    accepted_version = row.get("accepted_plan_version")
    undo_version = row.get("undo_plan_version")
    undo_until = row.get("undo_until")
    undo_available = False
    if status == "accepted" and isinstance(undo_until, str):
        try:
            undo_available = datetime.fromisoformat(undo_until) >= datetime.now(UTC)
        except ValueError:
            undo_available = False
    if status == "accepted":
        message = (
            "The adjusted plan is saved. It will take effect after the current "
            "learning step finishes."
        )
    elif status == "undone":
        message = (
            "The adjustment was undone. The previous unstarted sequence will "
            "continue after the current learning step."
        )
    else:
        message = "The current learning plan was kept unchanged."
    return {
        "proposalId": row["id"],
        "status": status,
        "planVersion": (
            int(undo_version)
            if undo_version is not None
            else int(accepted_version)
            if accepted_version is not None
            else None
        ),
        "effectiveAfterCurrentStep": status in {"accepted", "undone"},
        "undoAvailable": undo_available,
        "undoUntil": undo_until,
        "message": message,
    }


__all__ = [
    "StudyPlanProposalConflictError",
    "StudyPlanProposalService",
]
