"""Vertical contracts for a source-grounded Study Plan proposal decision."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from app.agent.provider import ContentDelta, ProviderFinished, ProviderRequest
from app.learning_agent.plan_proposal import (
    project_plan_proposal_context,
    revalidate_plan_proposal_context,
)
from app.repositories.study_repository import StudyRepository
from app.services.agent_runtime import AgentRuntimeManager
from app.services.learning_intervention import LearningInterventionService
from app.services.study_plan_proposal import (
    StudyPlanProposalConflictError,
    StudyPlanProposalService,
)
from test_autonomous_study_session import _database
from test_learning_intervention import (
    _ArtifactProvider,
    _ready_recall,
    _start_args,
    _wait_terminal,
)


class _ProposalProvider:
    name = "fixture"
    model = "bounded-plan-proposal"
    version = "v1"

    def __init__(self, *, invalid_handle: bool = False) -> None:
        self.requests: list[ProviderRequest] = []
        self.invalid_handle = invalid_handle

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        self.requests.append(request)
        proposal = request.input["planProposal"]
        target = proposal["targetUnit"]
        sources = proposal["sources"]
        handle = (
            "source-unissued" if self.invalid_handle else sources[0]["sourceHandle"]
        )
        yield ContentDelta(
            text=json.dumps(
                {
                    "schemaVersion": 1,
                    "summary": "Add a short composition prerequisite.",
                    "reason": (
                        "The cited source introduces the inner and outer functions "
                        "that the selected unit assumes."
                    ),
                    "operation": {
                        "kind": "insert_prerequisite",
                        "beforeUnitId": target["id"],
                        "title": "Composition refresher",
                        "objective": (
                            "Connect inner and outer functions using the cited source."
                        ),
                        "estimatedMinutes": 10,
                        "selectedSourceHandles": [handle],
                    },
                }
            )
        )
        yield ProviderFinished()

    async def aclose(self) -> None:
        return None


def _proposal_args(
    database, graph: dict[str, object], *, key: str
) -> dict[str, object]:
    with database.connection() as connection:
        plan = StudyRepository(connection).get_current_or_latest_plan(
            str(graph["session_id"])
        )
    assert plan is not None
    target = plan["units"][1]
    assert target["status"] == "locked"
    return {
        "course_id": "course-calculus",
        "session_id": str(graph["session_id"]),
        "expected_session_revision": int(graph["revision"]),
        "expected_plan_version": int(plan["version"]),
        "target_unit_id": str(target["id"]),
        "idempotency_key": key,
    }


def _learning_state(database, session_id: str) -> dict[str, object]:
    with database.connection() as connection:
        session = connection.execute(
            """
            SELECT revision, status, current_unit_id
            FROM study_sessions WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        assert session is not None
        return {
            "session": tuple(session),
            "planVersions": connection.execute(
                "SELECT COUNT(*) FROM study_plan_versions WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0],
            "units": connection.execute(
                """
                SELECT COUNT(*) FROM study_units u
                JOIN study_plan_versions p ON p.id = u.plan_version_id
                WHERE p.session_id = ?
                """,
                (session_id,),
            ).fetchone()[0],
            "masteryEvents": connection.execute(
                "SELECT COUNT(*) FROM mastery_events"
            ).fetchone()[0],
            "masteryEvidence": connection.execute(
                "SELECT COUNT(*) FROM mastery_evidence"
            ).fetchone()[0],
            "reviewItems": connection.execute(
                "SELECT COUNT(*) FROM review_items"
            ).fetchone()[0],
            "tasks": connection.execute("SELECT COUNT(*) FROM study_tasks").fetchone()[
                0
            ],
            "misconceptions": connection.execute(
                "SELECT COUNT(*) FROM misconceptions"
            ).fetchone()[0],
        }


def _insert_closer_plan_unit(
    database,
    *,
    plan_id: str,
    existing_target_id: str,
    new_unit_id: str,
) -> None:
    with database.connection() as connection:
        connection.execute(
            "UPDATE study_units SET ordinal = 2 WHERE id = ? AND plan_version_id = ?",
            (existing_target_id, plan_id),
        )
        connection.execute(
            """
            INSERT INTO study_units (
                id, plan_version_id, ordinal, concept_id, concept_ids_json,
                source_chunk_ids_json, title, objective, content,
                estimated_minutes, status, created_at, updated_at
            )
            SELECT ?, plan_version_id, 1, concept_id, concept_ids_json,
                   source_chunk_ids_json, 'Closer prerequisite',
                   'This is now the immediate unstarted successor.', content,
                   estimated_minutes, 'locked', created_at, updated_at
            FROM study_units WHERE id = ?
            """,
            (new_unit_id, existing_target_id),
        )
        connection.commit()


async def _ready_proposal(database, graph, *, key: str):
    provider = _ProposalProvider()
    runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
    service = StudyPlanProposalService(database, runtime)
    arguments = _proposal_args(database, graph, key=key)
    started = await service.start(**arguments)
    terminal = await _wait_terminal(runtime, started["run"]["id"])
    assert terminal["status"] == "completed"
    ready = service.get_current(
        course_id="course-calculus",
        session_id=str(graph["session_id"]),
    )
    assert ready["status"] == "ready"
    assert ready["artifact"] is not None
    return service, runtime, arguments, ready


async def _publish_intervention_artifact(database, graph):
    provider = _ArtifactProvider()
    runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
    service = LearningInterventionService(database, runtime)
    started = await service.start(
        **_start_args(graph, key="adaptive-intervention-artifact-001")
    )
    terminal = await _wait_terminal(runtime, str(started["run"]["id"]))
    assert terminal["status"] == "completed"
    ready = service.get_current(
        course_id="course-calculus",
        session_id=str(graph["session_id"]),
    )
    assert ready["status"] == "ready"
    assert ready["artifact"]["kind"] == "learning_intervention_artifact"
    return runtime, ready


def test_plan_proposal_is_source_linked_idempotent_and_has_no_learning_side_effects(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        provider = _ProposalProvider()
        runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
        service = StudyPlanProposalService(database, runtime)
        arguments = _proposal_args(
            database,
            graph,
            key="plan-proposal-idempotency-001",
        )
        before = _learning_state(database, str(graph["session_id"]))

        first = await service.start(**arguments)
        active_replay = await service.start(**arguments)
        assert first["run"]["id"] == active_replay["run"]["id"]
        terminal = await _wait_terminal(runtime, first["run"]["id"])
        assert terminal["status"] == "completed"

        ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        completed_replay = await service.start(**arguments)
        assert ready["status"] == "ready"
        assert completed_replay["run"]["id"] == first["run"]["id"]
        assert ready["artifact"]["decision"] == {
            "status": "pending",
            "applyAvailable": True,
        }
        assert (
            ready["artifact"]["operation"]["beforeUnitId"]
            == arguments["target_unit_id"]
        )
        assert ready["artifact"]["operation"]["selectedSourceHandles"] == [
            ready["artifact"]["sources"][0]["sourceHandle"]
        ]
        assert ready["artifact"]["sources"][0]["chunkContentHash"]
        assert _learning_state(database, str(graph["session_id"])) == before

        assert len(provider.requests) == 1
        request = provider.requests[0]
        assert request.output_format == "json_object"
        assert [tool.name for tool in request.tools] == ["search_course_knowledge"]
        assert request.input["planProposal"]["authority"] == {
            "canApplyPlan": False,
            "canChangeSession": False,
            "canGrade": False,
        }
        example = request.input["artifactContract"]["outputExample"]
        assert example["operation"]["beforeUnitId"] == arguments["target_unit_id"]
        assert example["operation"]["selectedSourceHandles"]

        with pytest.raises(
            StudyPlanProposalConflictError,
            match="study session revision is stale",
        ):
            await service.start(
                **{
                    **arguments,
                    "expected_session_revision": int(graph["revision"]) - 1,
                    "idempotency_key": "plan-proposal-stale-revision-001",
                }
            )
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="unstarted plan unit",
        ):
            await service.start(
                **{
                    **arguments,
                    "target_unit_id": str(graph["unit_id"]),
                    "idempotency_key": "plan-proposal-active-target-001",
                }
            )
        assert _learning_state(database, str(graph["session_id"])) == before
        await runtime.shutdown()

    asyncio.run(scenario())


def test_plan_proposal_target_is_always_the_immediate_unstarted_successor(
    tmp_path,
) -> None:
    async def scenario() -> None:
        start_database = _database(tmp_path / "start")
        start_graph = _ready_recall(start_database, correct=False)
        start_arguments = _proposal_args(
            start_database,
            start_graph,
            key="plan-proposal-remote-target-001",
        )
        with start_database.connection() as connection:
            plan = StudyRepository(connection).get_current_or_latest_plan(
                str(start_graph["session_id"])
            )
            assert plan is not None
            frozen = project_plan_proposal_context(
                connection,
                course_id="course-calculus",
                session_id=str(start_graph["session_id"]),
                expected_session_revision=int(
                    start_arguments["expected_session_revision"]
                ),
                expected_plan_version=int(start_arguments["expected_plan_version"]),
                target_unit_id=str(start_arguments["target_unit_id"]),
            )
        _insert_closer_plan_unit(
            start_database,
            plan_id=str(plan["id"]),
            existing_target_id=str(start_arguments["target_unit_id"]),
            new_unit_id="unit-new-immediate-successor",
        )
        with (
            start_database.connection() as connection,
            pytest.raises(
                RuntimeError,
                match="next unstarted plan unit",
            ),
        ):
            revalidate_plan_proposal_context(connection, frozen)

        runtime = AgentRuntimeManager(
            start_database,
            provider_factory=lambda: _ProposalProvider(),
        )
        service = StudyPlanProposalService(start_database, runtime)
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="next unstarted plan unit",
        ):
            await service.start(**start_arguments)
        await runtime.shutdown()

        decision_database = _database(tmp_path / "decision")
        decision_graph = _ready_recall(decision_database, correct=False)
        decision_service, decision_runtime, _, ready = await _ready_proposal(
            decision_database,
            decision_graph,
            key="plan-proposal-adjacency-decision-001",
        )
        artifact = ready["artifact"]
        assert artifact is not None
        _insert_closer_plan_unit(
            decision_database,
            plan_id=str(artifact["basePlanId"]),
            existing_target_id=str(artifact["operation"]["beforeUnitId"]),
            new_unit_id="unit-closer-before-decision",
        )
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="next unstarted plan unit",
        ):
            decision_service.decide(
                course_id="course-calculus",
                session_id=str(decision_graph["session_id"]),
                artifact_id=str(artifact["artifactId"]),
                expected_session_revision=int(artifact["baseSessionRevision"]),
                expected_plan_version=int(artifact["basePlanVersion"]),
                decision="accept",
                idempotency_key="plan-proposal-adjacency-decision-002",
            )
        await decision_runtime.shutdown()

    asyncio.run(scenario())


def test_accept_is_idempotent_and_switches_only_at_the_safe_unit_boundary(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        service, runtime, arguments, ready = await _ready_proposal(
            database,
            graph,
            key="plan-proposal-accept-source-001",
        )
        session_id = str(graph["session_id"])
        artifact = ready["artifact"]
        assert artifact is not None
        before = _learning_state(database, session_id)

        accepted = service.decide(
            course_id="course-calculus",
            session_id=session_id,
            artifact_id=str(artifact["artifactId"]),
            expected_session_revision=int(artifact["baseSessionRevision"]),
            expected_plan_version=int(artifact["basePlanVersion"]),
            decision="accept",
            idempotency_key="plan-proposal-accept-decision-001",
        )
        assert accepted["status"] == "accepted"
        assert accepted["artifact"]["decision"] == {
            "status": "accepted",
            "applyAvailable": False,
        }
        assert accepted["receipt"]["effectiveAfterCurrentStep"] is True
        assert accepted["receipt"]["undoAvailable"] is True
        assert (
            accepted["receipt"]["planVersion"]
            == int(arguments["expected_plan_version"]) + 1
        )

        after = _learning_state(database, session_id)
        assert after["planVersions"] == int(before["planVersions"]) + 1
        assert int(after["units"]) == int(before["units"]) + 3
        for field in (
            "session",
            "masteryEvents",
            "masteryEvidence",
            "reviewItems",
            "tasks",
            "misconceptions",
        ):
            assert after[field] == before[field]

        with database.connection() as connection:
            successor = StudyRepository(connection).get_locked_successor(
                session_id=session_id,
                unit_id=str(graph["unit_id"]),
            )
        assert successor is not None
        assert successor["title"] == "Composition refresher"
        assert successor["status"] == "locked"

        replay = service.decide(
            course_id="course-calculus",
            session_id=session_id,
            artifact_id=str(artifact["artifactId"]),
            expected_session_revision=int(artifact["baseSessionRevision"]),
            expected_plan_version=int(artifact["basePlanVersion"]),
            decision="accept",
            idempotency_key="plan-proposal-accept-decision-001",
        )
        assert replay["receipt"] == accepted["receipt"]
        assert _learning_state(database, session_id) == after
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="already resolved differently",
        ):
            service.decide(
                course_id="course-calculus",
                session_id=session_id,
                artifact_id=str(artifact["artifactId"]),
                expected_session_revision=int(artifact["baseSessionRevision"]),
                expected_plan_version=int(artifact["basePlanVersion"]),
                decision="keep",
                idempotency_key="plan-proposal-keep-after-accept-001",
            )

        with database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            advanced, activated = StudyRepository(connection).advance_current_unit(
                session_id=session_id,
                unit_id=str(graph["unit_id"]),
                successor_id=str(successor["id"]),
                expected_revision=int(artifact["baseSessionRevision"]),
                commit=False,
            )
            connection.commit()
        assert advanced["current_unit_id"] == successor["id"]
        assert int(advanced["revision"]) == int(artifact["baseSessionRevision"]) + 1
        assert activated["title"] == "Composition refresher"
        assert activated["status"] == "active"
        await runtime.shutdown()

    asyncio.run(scenario())


def test_keep_is_durable_without_creating_a_plan_version(tmp_path) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        service, runtime, _, ready = await _ready_proposal(
            database,
            graph,
            key="plan-proposal-keep-source-001",
        )
        session_id = str(graph["session_id"])
        artifact = ready["artifact"]
        assert artifact is not None
        before = _learning_state(database, session_id)

        kept = service.decide(
            course_id="course-calculus",
            session_id=session_id,
            artifact_id=str(artifact["artifactId"]),
            expected_session_revision=int(artifact["baseSessionRevision"]),
            expected_plan_version=int(artifact["basePlanVersion"]),
            decision="keep",
            idempotency_key="plan-proposal-keep-decision-001",
        )
        assert kept["status"] == "rejected"
        assert kept["receipt"] == {
            "proposalId": kept["receipt"]["proposalId"],
            "status": "rejected",
            "planVersion": None,
            "effectiveAfterCurrentStep": False,
            "undoAvailable": False,
            "undoUntil": None,
            "message": "The current learning plan was kept unchanged.",
        }
        assert _learning_state(database, session_id) == before
        await runtime.shutdown()

    asyncio.run(scenario())


def test_undo_appends_a_restore_version_and_fails_closed_after_learning_advances(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        service, runtime, _, ready = await _ready_proposal(
            database,
            graph,
            key="plan-proposal-undo-source-001",
        )
        session_id = str(graph["session_id"])
        artifact = ready["artifact"]
        assert artifact is not None
        expected_target_title = next(
            unit["title"]
            for unit in artifact["currentPlan"]["units"]
            if unit["id"] == artifact["operation"]["beforeUnitId"]
        )
        accepted = service.decide(
            course_id="course-calculus",
            session_id=session_id,
            artifact_id=str(artifact["artifactId"]),
            expected_session_revision=int(artifact["baseSessionRevision"]),
            expected_plan_version=int(artifact["basePlanVersion"]),
            decision="accept",
            idempotency_key="plan-proposal-undo-accept-001",
        )
        proposal_id = str(accepted["receipt"]["proposalId"])
        before_undo = _learning_state(database, session_id)

        undone = service.undo(
            course_id="course-calculus",
            session_id=session_id,
            proposal_id=proposal_id,
            expected_session_revision=int(artifact["baseSessionRevision"]),
            idempotency_key="plan-proposal-undo-decision-001",
        )
        assert undone["status"] == "undone"
        assert undone["receipt"]["status"] == "undone"
        assert undone["receipt"]["effectiveAfterCurrentStep"] is True
        assert undone["receipt"]["undoAvailable"] is False
        after_undo = _learning_state(database, session_id)
        assert after_undo["planVersions"] == int(before_undo["planVersions"]) + 1
        assert after_undo["session"] == before_undo["session"]

        with database.connection() as connection:
            successor = StudyRepository(connection).get_locked_successor(
                session_id=session_id,
                unit_id=str(graph["unit_id"]),
            )
        assert successor is not None
        assert successor["title"] == expected_target_title

        replay = service.undo(
            course_id="course-calculus",
            session_id=session_id,
            proposal_id=proposal_id,
            expected_session_revision=int(artifact["baseSessionRevision"]),
            idempotency_key="plan-proposal-undo-decision-001",
        )
        assert replay["receipt"] == undone["receipt"]

        next_database = _database(tmp_path / "advanced")
        next_graph = _ready_recall(next_database, correct=False)
        next_service, next_runtime, _, next_ready = await _ready_proposal(
            next_database,
            next_graph,
            key="plan-proposal-advanced-source-001",
        )
        next_artifact = next_ready["artifact"]
        assert next_artifact is not None
        next_accepted = next_service.decide(
            course_id="course-calculus",
            session_id=str(next_graph["session_id"]),
            artifact_id=str(next_artifact["artifactId"]),
            expected_session_revision=int(next_artifact["baseSessionRevision"]),
            expected_plan_version=int(next_artifact["basePlanVersion"]),
            decision="accept",
            idempotency_key="plan-proposal-advanced-accept-001",
        )
        with next_database.connection() as connection:
            connection.execute(
                "UPDATE study_sessions SET revision = revision + 1 WHERE id = ?",
                (next_graph["session_id"],),
            )
            connection.commit()
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="learning advanced",
        ):
            next_service.undo(
                course_id="course-calculus",
                session_id=str(next_graph["session_id"]),
                proposal_id=str(next_accepted["receipt"]["proposalId"]),
                expected_session_revision=int(next_artifact["baseSessionRevision"]) + 1,
                idempotency_key="plan-proposal-advanced-undo-001",
            )
        await next_runtime.shutdown()
        await runtime.shutdown()

    asyncio.run(scenario())


def test_unissued_source_handle_fails_closed_without_artifact_or_plan_change(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        provider = _ProposalProvider(invalid_handle=True)
        runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
        service = StudyPlanProposalService(database, runtime)
        before = _learning_state(database, str(graph["session_id"]))
        started = await service.start(
            **_proposal_args(
                database,
                graph,
                key="plan-proposal-invalid-source-001",
            )
        )
        terminal = await _wait_terminal(runtime, started["run"]["id"])
        assert terminal["status"] == "failed"
        snapshot = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert snapshot["status"] == "unavailable"
        assert snapshot["artifact"] is None
        assert _learning_state(database, str(graph["session_id"])) == before
        await runtime.shutdown()

    asyncio.run(scenario())


def test_adaptive_trigger_requires_low_confidence_incorrect_recall_and_artifact(
    tmp_path,
) -> None:
    async def scenario() -> None:
        no_artifact_database = _database(tmp_path / "no-artifact")
        no_artifact_graph = _ready_recall(
            no_artifact_database,
            correct=False,
            self_assessment="not_yet",
        )
        no_artifact_runtime = AgentRuntimeManager(
            no_artifact_database,
            provider_factory=lambda: _ProposalProvider(),
        )
        no_artifact_service = StudyPlanProposalService(
            no_artifact_database,
            no_artifact_runtime,
        )
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="does not support an Agent plan suggestion",
        ):
            await no_artifact_service.start(
                **_proposal_args(
                    no_artifact_database,
                    no_artifact_graph,
                    key="adaptive-no-artifact-001",
                ),
                trigger_origin="adaptive_evidence",
            )
        assert (
            no_artifact_service.get_current(
                course_id="course-calculus",
                session_id=str(no_artifact_graph["session_id"]),
            )["trigger"]
            is None
        )
        await no_artifact_runtime.shutdown()

        high_confidence_database = _database(tmp_path / "high-confidence")
        high_confidence_graph = _ready_recall(
            high_confidence_database,
            correct=False,
            self_assessment="partial",
        )
        intervention_runtime, _ = await _publish_intervention_artifact(
            high_confidence_database,
            high_confidence_graph,
        )
        high_confidence_runtime = AgentRuntimeManager(
            high_confidence_database,
            provider_factory=lambda: _ProposalProvider(),
        )
        high_confidence_service = StudyPlanProposalService(
            high_confidence_database,
            high_confidence_runtime,
        )
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="does not support an Agent plan suggestion",
        ):
            await high_confidence_service.start(
                **_proposal_args(
                    high_confidence_database,
                    high_confidence_graph,
                    key="adaptive-high-confidence-001",
                ),
                trigger_origin="adaptive_evidence",
            )
        await high_confidence_runtime.shutdown()
        await intervention_runtime.shutdown()

        eligible_database = _database(tmp_path / "eligible")
        eligible_graph = _ready_recall(
            eligible_database,
            correct=False,
            self_assessment="not_yet",
        )
        (
            eligible_intervention_runtime,
            intervention,
        ) = await _publish_intervention_artifact(
            eligible_database,
            eligible_graph,
        )
        provider = _ProposalProvider()
        eligible_runtime = AgentRuntimeManager(
            eligible_database,
            provider_factory=lambda: provider,
        )
        eligible_service = StudyPlanProposalService(
            eligible_database,
            eligible_runtime,
        )
        arguments = _proposal_args(
            eligible_database,
            eligible_graph,
            key="caller-key-is-ignored-for-adaptive-001",
        )
        started = await eligible_service.start(
            **arguments,
            trigger_origin="adaptive_evidence",
        )
        replay = await eligible_service.start(
            **{
                **arguments,
                "idempotency_key": "different-caller-key-adaptive-002",
            },
            trigger_origin="adaptive_evidence",
        )
        assert replay["run"]["id"] == started["run"]["id"]
        assert started["trigger"] == {
            "origin": "adaptive_evidence",
            "reasonCode": "low_confidence_incorrect_recall_after_intervention",
            "evidenceIds": [
                started["trigger"]["evidenceIds"][0],
                started["trigger"]["evidenceIds"][1],
                intervention["artifact"]["artifactId"],
            ],
            "whyNow": (
                "Your opening confidence was low, the latest Recall was "
                "incorrect, and a source-grounded intervention is ready."
            ),
            "learnerApprovalRequired": True,
        }
        terminal = await _wait_terminal(
            eligible_runtime,
            str(started["run"]["id"]),
        )
        assert terminal["status"] == "completed"
        assert len(provider.requests) == 1

        stale_arguments = {
            **arguments,
            "expected_session_revision": int(arguments["expected_session_revision"])
            - 1,
            "idempotency_key": "adaptive-stale-revision-003",
        }
        with pytest.raises(
            StudyPlanProposalConflictError,
            match="study session revision is stale",
        ):
            await eligible_service.start(
                **stale_arguments,
                trigger_origin="adaptive_evidence",
            )
        await eligible_runtime.shutdown()
        await eligible_intervention_runtime.shutdown()

    asyncio.run(scenario())


def test_adaptive_decision_persists_trigger_reason_and_recovers_after_restart(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(
            database,
            correct=False,
            self_assessment="not_yet",
        )
        intervention_runtime, intervention = await _publish_intervention_artifact(
            database,
            graph,
        )
        provider = _ProposalProvider()
        first_runtime = AgentRuntimeManager(
            database,
            provider_factory=lambda: provider,
        )
        first_service = StudyPlanProposalService(database, first_runtime)
        arguments = _proposal_args(
            database,
            graph,
            key="adaptive-cold-start-source-001",
        )
        started = await first_service.start(
            **arguments,
            trigger_origin="adaptive_evidence",
        )
        terminal = await _wait_terminal(first_runtime, str(started["run"]["id"]))
        assert terminal["status"] == "completed"
        before_restart = first_service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert before_restart["status"] == "ready"
        await first_runtime.shutdown()

        recovered_runtime = AgentRuntimeManager(
            database,
            provider_factory=lambda: _ProposalProvider(),
        )
        recovered_service = StudyPlanProposalService(database, recovered_runtime)
        recovered = recovered_service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert recovered == before_restart

        artifact = recovered["artifact"]
        assert artifact is not None
        accepted = recovered_service.decide(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
            artifact_id=str(artifact["artifactId"]),
            expected_session_revision=int(artifact["baseSessionRevision"]),
            expected_plan_version=int(artifact["basePlanVersion"]),
            decision="accept",
            idempotency_key="adaptive-cold-start-decision-001",
        )
        assert accepted["status"] == "accepted"
        with database.connection() as connection:
            row = connection.execute(
                """
                SELECT trigger_event_ids_json, reason_json
                FROM study_plan_proposals
                WHERE validated_artifact_id = ?
                """,
                (artifact["artifactId"],),
            ).fetchone()
        assert row is not None
        trigger_event_ids = json.loads(str(row["trigger_event_ids_json"]))
        reason = json.loads(str(row["reason_json"]))
        assert trigger_event_ids == accepted["trigger"]["evidenceIds"]
        assert trigger_event_ids[-1] == intervention["artifact"]["artifactId"]
        assert reason == {
            "reason": artifact["reason"],
            "trigger": accepted["trigger"],
        }

        await recovered_runtime.shutdown()
        final_runtime = AgentRuntimeManager(database)
        final = StudyPlanProposalService(database, final_runtime).get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert final["status"] == "accepted"
        assert final["receipt"] == accepted["receipt"]
        assert final["trigger"] == accepted["trigger"]
        await final_runtime.shutdown()
        await intervention_runtime.shutdown()

    asyncio.run(scenario())


def test_legacy_manual_proposal_without_trigger_recovers_and_can_be_decided(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        _, runtime, _, ready = await _ready_proposal(
            database,
            graph,
            key="legacy-manual-plan-proposal-001",
        )
        artifact = ready["artifact"]
        assert artifact is not None
        run_id = str(ready["run"]["id"])
        with database.connection() as connection:
            row = connection.execute(
                "SELECT input_json FROM agent_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            assert row is not None
            input_data = json.loads(str(row["input_json"]))
            assert input_data["planProposal"]["explicitLearnerRequest"] is True
            input_data["planProposal"].pop("trigger")
            connection.execute(
                "UPDATE agent_runs SET input_json = ? WHERE id = ?",
                (json.dumps(input_data), run_id),
            )
            connection.commit()
        await runtime.shutdown()

        recovered_runtime = AgentRuntimeManager(database)
        recovered_service = StudyPlanProposalService(database, recovered_runtime)
        recovered = recovered_service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        expected_trigger = {
            "origin": "learner_request",
            "reasonCode": "learner_requested_prerequisite",
            "evidenceIds": [],
            "whyNow": ("You asked Keen to suggest one source-grounded prerequisite."),
            "learnerApprovalRequired": True,
        }
        assert recovered["status"] == "ready"
        assert recovered["trigger"] == expected_trigger

        accepted = recovered_service.decide(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
            artifact_id=str(artifact["artifactId"]),
            expected_session_revision=int(artifact["baseSessionRevision"]),
            expected_plan_version=int(artifact["basePlanVersion"]),
            decision="accept",
            idempotency_key="legacy-manual-plan-decision-001",
        )
        assert accepted["status"] == "accepted"
        assert accepted["trigger"] == expected_trigger
        with database.connection() as connection:
            decision = connection.execute(
                """
                SELECT trigger_event_ids_json, reason_json
                FROM study_plan_proposals
                WHERE validated_artifact_id = ?
                """,
                (artifact["artifactId"],),
            ).fetchone()
        assert decision is not None
        assert json.loads(str(decision["trigger_event_ids_json"])) == []
        assert json.loads(str(decision["reason_json"])) == {
            "reason": artifact["reason"],
            "trigger": expected_trigger,
        }
        await recovered_runtime.shutdown()

    asyncio.run(scenario())


def test_plan_proposal_api_is_authenticated_and_returns_truthful_unavailable_state(
    client,
    auth_headers,
) -> None:
    graph = _ready_recall(client.app.state.database, correct=False)
    arguments = _proposal_args(
        client.app.state.database,
        graph,
        key="plan-proposal-api-missing-provider-001",
    )
    before = _learning_state(client.app.state.database, str(graph["session_id"]))
    path = f"/v1/study-sessions/{graph['session_id']}/plan-proposals"
    payload = {
        "courseId": arguments["course_id"],
        "expectedSessionRevision": arguments["expected_session_revision"],
        "expectedPlanVersion": arguments["expected_plan_version"],
        "targetUnitId": arguments["target_unit_id"],
        "request": "insert_source_grounded_prerequisite",
        "idempotencyKey": arguments["idempotency_key"],
    }

    assert client.post(path, json=payload).status_code == 401
    response = client.post(path, headers=auth_headers, json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == "provider_missing"
    assert response.json()["artifact"] is None

    current = client.get(
        f"{path}/current",
        headers=auth_headers,
        params={"courseId": "course-calculus"},
    )
    assert current.status_code == 200
    assert current.json() == response.json()
    decision_path = f"{path}/plan-proposal-artifact-missing/decision"
    decision_payload = {
        "courseId": "course-calculus",
        "artifactId": "plan-proposal-artifact-missing",
        "expectedSessionRevision": arguments["expected_session_revision"],
        "expectedPlanVersion": arguments["expected_plan_version"],
        "decision": "accept",
        "idempotencyKey": "plan-proposal-api-decision-001",
    }
    assert client.post(decision_path, json=decision_payload).status_code == 401
    assert (
        client.post(
            decision_path,
            headers=auth_headers,
            json=decision_payload,
        ).status_code
        == 409
    )

    undo_path = f"{path}/plan-proposal-missing/undo"
    undo_payload = {
        "courseId": "course-calculus",
        "expectedSessionRevision": arguments["expected_session_revision"],
        "idempotencyKey": "plan-proposal-api-undo-001",
    }
    assert client.post(undo_path, json=undo_payload).status_code == 401
    assert (
        client.post(
            undo_path,
            headers=auth_headers,
            json=undo_payload,
        ).status_code
        == 409
    )
    assert (
        _learning_state(client.app.state.database, str(graph["session_id"])) == before
    )

    stale = client.post(
        path,
        headers=auth_headers,
        json={
            **payload,
            "expectedSessionRevision": int(graph["revision"]) - 1,
            "idempotencyKey": "plan-proposal-api-stale-revision-001",
        },
    )
    assert stale.status_code == 409
    assert "revision is stale" in stale.json()["detail"]
