"""Vertical contracts for the thin misconception-repair intervention."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import pytest
from app.agent.provider import (
    ContentDelta,
    ProviderFinished,
    ProviderRequest,
)
from app.learning_agent.context import (
    legacy_context_fingerprint,
    project_intervention_eligibility,
)
from app.learning_agent.playbooks import (
    LearningInterventionIntent,
    select_playbook,
)
from app.repositories import dump_json, load_json
from app.repositories.intervention_outcome_repository import (
    InterventionOutcomeRepository,
)
from app.repositories.review_repository import ReviewRepository
from app.services.active_recall_progression import ActiveRecallProgressionService
from app.services.adaptive_study_session import AdaptiveStudySessionService
from app.services.agent_runtime import AgentRuntimeManager
from app.services.autonomous_study_session import AutonomousStudySessionService
from app.services.diagnostic_progression import DiagnosticProgressionService
from app.services.learning_intervention import (
    LearningInterventionConflictError,
    LearningInterventionNotFoundError,
    LearningInterventionService,
)
from app.services.review_session import ReviewSessionService
from app.services.study_summary_review import StudySummaryReviewService
from app.services.targeted_practice_progression import (
    TargetedPracticeProgressionService,
)
from test_autonomous_study_session import (
    NOW,
    _database,
    _indexed_source,
    _recommendation_task,
)


class _ArtifactProvider:
    name = "fixture"
    model = "bounded-artifact"
    version = "v1"

    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        self.requests.append(request)
        intervention = request.input["intervention"]
        assert isinstance(intervention, dict)
        sources = intervention["sources"]
        assert isinstance(sources, list) and sources
        handle = sources[0]["sourceHandle"]
        yield ContentDelta(
            text=json.dumps(
                {
                    "schemaVersion": 1,
                    "summary": "A different source-grounded formulation.",
                    "explanationMarkdown": (
                        "Think of the outer change as waiting for the inner "
                        "change supplied by the cited source example."
                    ),
                    "selectedSourceHandles": [handle],
                }
            )
        )
        yield ProviderFinished()

    async def aclose(self) -> None:
        self.closed = True


class _FailingProvider(_ArtifactProvider):
    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        self.requests.append(request)
        raise RuntimeError("private provider failure")
        if False:  # pragma: no cover - keeps this an async generator
            yield ProviderFinished()


class _BlockingProvider(_ArtifactProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        self.requests.append(request)
        self.started.set()
        await asyncio.Event().wait()
        yield ProviderFinished()  # pragma: no cover


def _ready_recall(
    database,
    *,
    correct: bool,
    legacy_session: bool = False,
    self_assessment: str = "partial",
) -> dict[str, object]:
    with database.connection() as connection:
        _indexed_source(connection)
        _recommendation_task(connection)
        created = AutonomousStudySessionService(connection).start_or_resume(
            course_id="course-calculus",
            task_id="autonomous-task",
            now=NOW,
        )
        assert created.session is not None
        session_id = str(created.session["id"])
        diagnostic = DiagnosticProgressionService(connection)
        diagnostic_run = diagnostic.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(created.session["revision"]),
            idempotency_key="diagnostic-begin-intervention-001",
            now=NOW,
        )
        diagnostic_answer = diagnostic.answer(
            course_id="course-calculus",
            session_id=session_id,
            checkpoint_id=str(diagnostic_run.checkpoint["id"]),
            expected_revision=int(diagnostic_run.session["revision"]),
            idempotency_key="diagnostic-answer-intervention-001",
            response="Ready to attempt recall.",
            self_assessment=self_assessment,
            now=NOW,
        )
        recall_service = ActiveRecallProgressionService(connection)
        recall = recall_service.begin(
            course_id="course-calculus",
            session_id=session_id,
            expected_revision=int(diagnostic_answer.session["revision"]),
            idempotency_key="active-recall-begin-intervention-001",
            now=NOW,
        )
        item = connection.execute(
            "SELECT answer_key_json FROM assessment_items WHERE id = ?",
            (
                connection.execute(
                    "SELECT item_id FROM study_active_recall_runs WHERE id = ?",
                    (recall.run["id"],),
                ).fetchone()["item_id"],
            ),
        ).fetchone()
        assert item is not None
        expected_answer = load_json(str(item["answer_key_json"]))["accepted_answers"][0]
        if legacy_session:
            # Model a pre-migration-028 session: production migrations preserve
            # its NULL adaptive policy instead of fabricating an action ledger.
            connection.execute("DROP TRIGGER study_sessions_adaptive_policy_immutable")
            connection.execute(
                "UPDATE study_sessions SET adaptive_policy_version = NULL WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        answered = recall_service.answer(
            course_id="course-calculus",
            session_id=session_id,
            run_id=str(recall.run["id"]),
            expected_revision=int(recall.session["revision"]),
            idempotency_key="active-recall-answer-intervention-001",
            response=str(expected_answer) if correct else "not the expected term",
            now=NOW,
        )
        attempt_id = connection.execute(
            "SELECT attempt_id FROM study_active_recall_runs WHERE id = ?",
            (recall.run["id"],),
        ).fetchone()["attempt_id"]
        return {
            "session_id": session_id,
            "unit_id": recall.current_unit["id"],
            "attempt_id": attempt_id,
            "revision": answered.session["revision"],
            "recall_run_id": recall.run["id"],
            "recall_prompt": recall.checkpoint["prompt"],
        }


async def _wait_terminal(runtime: AgentRuntimeManager, run_id: str) -> dict:
    for _ in range(400):
        run = runtime.get_run(run_id)
        assert run is not None
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return run
        await asyncio.sleep(0.01)
    raise AssertionError("Agent run did not reach a terminal state")


def _start_args(
    graph: dict[str, object],
    *,
    key: str,
    intent=LearningInterventionIntent.EXPLAIN_DIFFERENTLY,
    predecessor_run_id: str | None = None,
    predecessor_artifact_id: str | None = None,
):
    arguments = {
        "course_id": "course-calculus",
        "session_id": str(graph["session_id"]),
        "unit_id": str(graph["unit_id"]),
        "expected_session_revision": int(graph["revision"]),
        "intent": intent,
        "idempotency_key": key,
    }
    if predecessor_run_id is not None:
        arguments["predecessor_run_id"] = predecessor_run_id
    if predecessor_artifact_id is not None:
        arguments["predecessor_artifact_id"] = predecessor_artifact_id
    return arguments


def test_incorrect_recall_is_eligible_but_correct_recall_is_not(tmp_path) -> None:
    incorrect_path = tmp_path / "incorrect"
    incorrect_path.mkdir()
    incorrect_database = _database(incorrect_path)
    incorrect = _ready_recall(incorrect_database, correct=False)
    incorrect_runtime = AgentRuntimeManager(incorrect_database)
    snapshot = LearningInterventionService(
        incorrect_database, incorrect_runtime
    ).get_current(
        course_id="course-calculus",
        session_id=str(incorrect["session_id"]),
    )

    assert snapshot["status"] == "eligible"
    assert snapshot["actions"] == [
        "Explain differently",
        "Show a source example",
        "Test me instead",
    ]
    assert snapshot["artifact"]["whyNow"].startswith("Your latest Recall")
    assert snapshot["artifact"]["sources"]
    assert snapshot["artifact"]["whatNext"]["action"] == "continue_practice"

    correct_path = tmp_path / "correct"
    correct_path.mkdir()
    correct_database = _database(correct_path)
    correct = _ready_recall(correct_database, correct=True)
    correct_snapshot = LearningInterventionService(
        correct_database, AgentRuntimeManager(correct_database)
    ).get_current(
        course_id="course-calculus",
        session_id=str(correct["session_id"]),
    )
    assert correct_snapshot["status"] == "ineligible"
    assert correct_snapshot["reason"] == "recall_correct"


def test_playbook_selector_falls_back_without_first_not_yet_signal() -> None:
    assert (
        select_playbook(
            LearningInterventionIntent.EXPLAIN_DIFFERENTLY,
            diagnostic_self_report_score=0.5,
            has_predecessor=False,
        ).slug
        == "source-grounded-rephrase"
    )
    assert (
        select_playbook(
            LearningInterventionIntent.EXPLAIN_DIFFERENTLY,
            diagnostic_self_report_score=None,
            has_predecessor=False,
        ).slug
        == "source-grounded-rephrase"
    )
    assert (
        select_playbook(
            LearningInterventionIntent.SHOW_SOURCE_EXAMPLE,
            diagnostic_self_report_score=0.0,
            has_predecessor=False,
        ).slug
        == "source-grounded-example"
    )
    with pytest.raises(ValueError, match="deterministic Practice"):
        select_playbook(
            LearningInterventionIntent.TEST_ME_INSTEAD,
            diagnostic_self_report_score=0.0,
            has_predecessor=False,
        )


def test_first_not_yet_intervention_selects_one_progressive_hint(tmp_path) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(
            database,
            correct=False,
            self_assessment="not_yet",
        )
        provider = _ArtifactProvider()
        runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
        service = LearningInterventionService(database, runtime)
        start_arguments = _start_args(
            graph,
            key="intervention-progressive-hint-001",
        )

        started = await service.start(**start_arguments)
        replay = await service.start(**start_arguments)
        assert replay["run"]["id"] == started["run"]["id"]
        await _wait_terminal(runtime, str(started["run"]["id"]))
        await asyncio.sleep(0)
        first_ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert first_ready["status"] == "ready"
        assert first_ready["artifact"]["playbookSlug"] == "progressive-hint"
        assert first_ready["artifact"]["playbookVersion"] == 1

        persisted = runtime.get_run(str(started["run"]["id"]))
        assert persisted is not None
        intervention = persisted["input"]["intervention"]
        assert intervention["playbookSlug"] == "progressive-hint"
        assert intervention["playbookVersion"] == 1
        assert (
            intervention["playbookDefinitionHash"]
            == first_ready["artifact"]["playbookDefinitionHash"]
        )
        assert intervention["diagnosticSelfReport"]["score"] == 0.0
        assert intervention["diagnosticSelfReport"]["evidenceId"]

        successor = await service.start(
            **_start_args(
                graph,
                key="intervention-progressive-hint-successor-002",
                predecessor_run_id=str(first_ready["run"]["id"]),
                predecessor_artifact_id=str(first_ready["artifact"]["artifactId"]),
            )
        )
        await _wait_terminal(runtime, str(successor["run"]["id"]))
        second_ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert second_ready["status"] == "ready"
        assert second_ready["artifact"]["playbookSlug"] == ("source-grounded-rephrase")
        assert second_ready["artifact"]["predecessor"] == {
            "runId": first_ready["run"]["id"],
            "artifactId": first_ready["artifact"]["artifactId"],
        }

        with database.connection() as connection:
            lineage = InterventionOutcomeRepository(
                connection
            ).list_published_for_session(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert [
                (
                    row["playbook_slug"],
                    row["playbook_version"],
                    row["practice_run_id"],
                )
                for row in lineage
            ] == [
                (
                    "progressive-hint",
                    1,
                    first_ready["practice"]["practiceRunId"],
                ),
                (
                    "source-grounded-rephrase",
                    1,
                    first_ready["practice"]["practiceRunId"],
                ),
            ]
        await runtime.shutdown()

    asyncio.run(scenario())


def test_pre_selection_run_restores_with_legacy_context_fingerprint(tmp_path) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        runtime = AgentRuntimeManager(
            database, provider_factory=lambda: _ArtifactProvider()
        )
        service = LearningInterventionService(database, runtime)
        started = await service.start(
            **_start_args(graph, key="intervention-legacy-fingerprint-001")
        )
        await _wait_terminal(runtime, str(started["run"]["id"]))
        await asyncio.sleep(0)

        with database.connection() as connection:
            eligibility = project_intervention_eligibility(
                connection,
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert eligibility.context is not None
            row = connection.execute(
                "SELECT input_json FROM agent_runs WHERE id = ?",
                (started["run"]["id"],),
            ).fetchone()
            assert row is not None
            run_input = load_json(str(row["input_json"]))
            intervention = run_input["intervention"]
            intervention.pop("diagnosticSelfReport")
            intervention["contextFingerprint"] = legacy_context_fingerprint(
                eligibility.context
            )
            connection.execute(
                "UPDATE agent_runs SET input_json = ? WHERE id = ?",
                (dump_json(run_input), started["run"]["id"]),
            )
            connection.commit()

        restored = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert restored["status"] == "ready"
        assert restored["run"]["id"] == started["run"]["id"]
        assert restored["artifact"]["playbookSlug"] == ("source-grounded-rephrase")
        await runtime.shutdown()

    asyncio.run(scenario())


def test_intervention_isolated_by_course_session_and_requires_current_sources(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    graph = _ready_recall(database, correct=False)
    service = LearningInterventionService(database, AgentRuntimeManager(database))

    foreign = service.get_current(
        course_id="course-linear-algebra",
        session_id=str(graph["session_id"]),
    )
    assert foreign["status"] == "ineligible"
    with pytest.raises(LearningInterventionNotFoundError):
        service.require_owned_run(
            course_id="course-calculus",
            session_id="foreign-session",
            run_id="missing-run",
        )

    with database.connection() as connection:
        connection.execute(
            "UPDATE documents SET status = 'failed' WHERE id = 'source-document'"
        )
        connection.commit()
    unavailable = service.get_current(
        course_id="course-calculus",
        session_id=str(graph["session_id"]),
    )
    assert unavailable["status"] == "source_review"
    assert unavailable["reason"] == "source_unavailable"
    assert unavailable["fallback"]["action"] == "source_review"


def test_validated_artifact_replays_and_hands_off_distinct_existing_practice(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        provider = _ArtifactProvider()
        runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
        service = LearningInterventionService(database, runtime)
        before: dict[str, int] = {}
        with database.connection() as connection:
            adaptive_before = AdaptiveStudySessionService(connection).get(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert adaptive_before.action is not None
            assert adaptive_before.action["kind"] == "remediate"
            for table in (
                "mastery_events",
                "mastery_evidence",
                "review_items",
                "study_tasks",
                "misconceptions",
            ):
                before[table] = int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )

        first = await service.start(
            **_start_args(graph, key="intervention-artifact-idempotency-001")
        )
        replay_while_active = await service.start(
            **_start_args(graph, key="intervention-artifact-idempotency-001")
        )
        assert first["run"]["id"] == replay_while_active["run"]["id"]
        run_id = first["run"]["id"]
        terminal = await _wait_terminal(runtime, run_id)
        assert terminal["status"] == "completed"

        ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        replay_after_completion = await service.start(
            **_start_args(graph, key="intervention-artifact-idempotency-001")
        )
        assert ready["status"] == "ready"
        assert replay_after_completion["run"]["id"] == run_id
        assert ready["artifact"]["sources"][0]["sourceHandle"].startswith("source-")
        assert ready["practice"]["practiceRunId"]
        assert ready["practice"]["practicePrompt"] != graph["recall_prompt"]
        assert provider.requests[0].tools
        assert provider.requests[0].output_format == "json_object"
        assert [tool.name for tool in provider.requests[0].tools] == [
            "search_course_knowledge"
        ]
        intervention_input = provider.requests[0].input["intervention"]
        assert isinstance(intervention_input, dict)
        sources = intervention_input["sources"]
        assert isinstance(sources, list) and sources
        issued_source_handle = sources[0]["sourceHandle"]
        assert provider.requests[0].input["artifactContract"] == {
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
                "selectedSourceHandles": [issued_source_handle],
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
        }

        durable = runtime.event_store.list_events(run_id)
        artifact_events = [
            event
            for event in durable
            if event.event_type == "checkpoint"
            and event.payload.get("label") == "completion_published"
            and isinstance(event.payload.get("data"), dict)
            and event.payload["data"].get("kind") == "learning_intervention_artifact"
        ]
        assert len(artifact_events) == 1
        assert durable[-1].event_type == "done"
        assert durable.index(artifact_events[0]) < len(durable) - 1
        with database.connection() as connection:
            persisted_checkpoint = load_json(
                str(
                    connection.execute(
                        "SELECT payload_json FROM agent_events "
                        "WHERE run_id = ? AND event_type = 'checkpoint'",
                        (run_id,),
                    ).fetchone()["payload_json"]
                )
            )
        assert persisted_checkpoint == artifact_events[0].payload
        serialized = json.dumps([event.payload for event in durable])
        assert "answer_key" not in serialized
        assert "hidden_reasoning" not in serialized

        # Pre-envelope completion checkpoints remain readable after restart. The
        # public event adapter normalizes this row without rewriting SQLite, and
        # the intervention snapshot still exposes the artifact itself.
        with database.connection() as connection:
            connection.execute(
                "UPDATE agent_events SET payload_json = ? "
                "WHERE run_id = ? AND event_type = 'checkpoint'",
                (json.dumps(ready["artifact"]), run_id),
            )
        legacy_ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert legacy_ready["status"] == "ready"
        assert legacy_ready["artifact"] == ready["artifact"]

        with database.connection() as connection:
            adaptive_rows = connection.execute(
                """SELECT kind, status, predecessor_active_recall_run_id
                   FROM study_adaptive_actions WHERE session_id = ?
                   ORDER BY kind""",
                (graph["session_id"],),
            ).fetchall()
            after = {
                table: int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in before
            }
            practice_answer = load_json(
                str(
                    connection.execute(
                        """SELECT item.answer_key_json
                           FROM study_practice_runs practice
                           JOIN assessment_items item ON item.id = practice.item_id
                           WHERE practice.id = ?""",
                        (ready["practice"]["practiceRunId"],),
                    ).fetchone()["answer_key_json"]
                )
            )["accepted_answers"][0]
            recall_answer = load_json(
                str(
                    connection.execute(
                        """SELECT item.answer_key_json
                           FROM study_active_recall_runs recall
                           JOIN assessment_items item ON item.id = recall.item_id
                           WHERE recall.id = ?""",
                        (graph["recall_run_id"],),
                    ).fetchone()["answer_key_json"]
                )
            )["accepted_answers"][0]
        assert after == before
        assert [tuple(row) for row in adaptive_rows] == [
            ("practice", "completed", graph["recall_run_id"]),
            ("remediate", "completed", graph["recall_run_id"]),
        ]
        assert str(practice_answer).casefold() != str(recall_answer).casefold()

        with database.connection() as connection:
            answered_practice = TargetedPracticeProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
                run_id=str(ready["practice"]["practiceRunId"]),
                expected_revision=int(ready["practice"]["sessionRevision"]),
                idempotency_key="practice-answer-after-intervention-001",
                response=str(practice_answer),
                now=NOW,
            )
            second_recall_service = ActiveRecallProgressionService(connection)
            second_recall = second_recall_service.begin(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
                expected_revision=int(answered_practice.session["revision"]),
                idempotency_key="active-recall-begin-second-unit-001",
                now=NOW,
            )
            second_answer = second_recall_service.answer(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
                run_id=str(second_recall.run["id"]),
                expected_revision=int(second_recall.session["revision"]),
                idempotency_key="active-recall-answer-second-unit-001",
                response="still not the expected term",
                now=NOW,
            )

        current_recall = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert second_answer.session["status"] == "practicing"
        assert current_recall["status"] == "eligible"
        assert "kind" not in current_recall["artifact"]
        assert (
            current_recall["artifact"]["sources"][0]["sourceHandle"]
            != ready["artifact"]["sources"][0]["sourceHandle"]
        )
        await runtime.shutdown()

    asyncio.run(scenario())


def test_existing_predecessor_practice_recovers_before_artifact_checkpoint(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        runtime = AgentRuntimeManager(
            database,
            provider_factory=lambda: _ArtifactProvider(),
        )
        service = LearningInterventionService(database, runtime)
        started = await service.start(
            **_start_args(graph, key="intervention-crash-before-checkpoint-001")
        )
        terminal = await _wait_terminal(runtime, str(started["run"]["id"]))
        assert terminal["status"] == "completed"
        ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert ready["status"] == "ready"
        practice_run_id = str(ready["practice"]["practiceRunId"])

        # Model a crash boundary after the deterministic Practice transaction
        # committed but before the validated artifact checkpoint was durable.
        with database.connection() as connection:
            checkpoint = connection.execute(
                """
                SELECT id FROM agent_events
                WHERE run_id = ? AND event_type = 'checkpoint'
                ORDER BY sequence DESC LIMIT 1
                """,
                (started["run"]["id"],),
            ).fetchone()
            assert checkpoint is not None
            connection.execute(
                """
                UPDATE agent_events
                SET event_type = 'warning', payload_json = '{}'
                WHERE id = ?
                """,
                (checkpoint["id"],),
            )
            connection.commit()
        await runtime.shutdown()

        recovered_runtime = AgentRuntimeManager(database)
        recovered_service = LearningInterventionService(
            database,
            recovered_runtime,
        )
        recovered = recovered_service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert recovered["status"] == "practice_ready"
        assert recovered["artifact"] is None
        assert recovered["practice"]["practiceRunId"] == practice_run_id

        replay = await recovered_service.start(
            **_start_args(
                graph,
                key="intervention-crash-practice-replay-002",
                intent=LearningInterventionIntent.TEST_ME_INSTEAD,
            )
        )
        assert replay["status"] == "practice_ready"
        assert replay["practice"]["practiceRunId"] == practice_run_id
        with database.connection() as connection:
            practices = connection.execute(
                """
                SELECT id, predecessor_active_recall_run_id
                FROM study_practice_runs
                WHERE session_id = ?
                """,
                (graph["session_id"],),
            ).fetchall()
            actions = connection.execute(
                """
                SELECT kind, predecessor_active_recall_run_id
                FROM study_adaptive_actions
                WHERE session_id = ?
                ORDER BY kind
                """,
                (graph["session_id"],),
            ).fetchall()
        assert [tuple(row) for row in practices] == [
            (practice_run_id, graph["recall_run_id"])
        ]
        assert [tuple(row) for row in actions] == [
            ("practice", graph["recall_run_id"]),
            ("remediate", graph["recall_run_id"]),
        ]
        await recovered_runtime.shutdown()

    asyncio.run(scenario())


def test_provider_failure_falls_back_to_source_review_without_artifact(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        runtime = AgentRuntimeManager(
            database, provider_factory=lambda: _FailingProvider()
        )
        service = LearningInterventionService(database, runtime)
        started = await service.start(
            **_start_args(graph, key="intervention-provider-failure-001")
        )
        terminal = await _wait_terminal(runtime, started["run"]["id"])
        assert terminal["status"] == "failed"
        snapshot = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert snapshot["status"] == "source_review"
        assert snapshot["artifact"] is None
        assert snapshot["fallback"]["action"] == "source_review"
        assert not any(
            event.payload.get("kind") == "learning_intervention_artifact"
            for event in runtime.event_store.list_events(started["run"]["id"])
        )
        await runtime.shutdown()

    asyncio.run(scenario())


def test_alternative_artifact_requires_current_lineage_and_reuses_practice(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        provider = _ArtifactProvider()
        runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
        service = LearningInterventionService(database, runtime)

        first = await service.start(
            **_start_args(graph, key="intervention-lineage-first-001")
        )
        await _wait_terminal(runtime, first["run"]["id"])
        await asyncio.sleep(0)
        first_ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert first_ready["status"] == "ready"
        assert first_ready["artifact"]["predecessor"] is None

        with database.connection() as connection:
            protected_before = {
                table: int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in (
                    "mastery_events",
                    "mastery_evidence",
                    "review_items",
                    "study_tasks",
                    "misconceptions",
                )
            }
            practice_count_before = int(
                connection.execute(
                    "SELECT COUNT(*) FROM study_practice_runs WHERE session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
            )

        with pytest.raises(
            LearningInterventionConflictError,
            match="predecessor is stale or unavailable",
        ):
            await service.start(
                **_start_args(graph, key="intervention-lineage-missing-002")
            )
        with pytest.raises(
            LearningInterventionConflictError,
            match="predecessor is stale or unavailable",
        ):
            await service.start(
                **_start_args(
                    graph,
                    key="intervention-lineage-stale-003",
                    predecessor_run_id=str(first_ready["run"]["id"]),
                    predecessor_artifact_id="artifact-stale",
                )
            )

        alternative_arguments = _start_args(
            graph,
            key="intervention-lineage-alternative-004",
            intent=LearningInterventionIntent.SHOW_SOURCE_EXAMPLE,
            predecessor_run_id=str(first_ready["run"]["id"]),
            predecessor_artifact_id=str(first_ready["artifact"]["artifactId"]),
        )
        alternative = await service.start(**alternative_arguments)
        replay = await service.start(**alternative_arguments)
        assert replay["run"]["id"] == alternative["run"]["id"]
        await _wait_terminal(runtime, alternative["run"]["id"])
        second_ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert second_ready["status"] == "ready"
        assert second_ready["run"]["id"] == alternative["run"]["id"]
        assert second_ready["artifact"]["predecessor"] == {
            "runId": first_ready["run"]["id"],
            "artifactId": first_ready["artifact"]["artifactId"],
        }

        persisted = runtime.get_run(str(alternative["run"]["id"]))
        assert persisted is not None
        assert persisted["input"]["intervention"]["predecessor"] == {
            "runId": first_ready["run"]["id"],
            "artifactId": first_ready["artifact"]["artifactId"],
        }
        with database.connection() as connection:
            outcome_lineage = InterventionOutcomeRepository(
                connection
            ).list_published_for_session(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert [
                (
                    row["intervention_run_id"],
                    row["intervention_artifact_id"],
                    row["playbook_slug"],
                    row["practice_status"],
                    row["practice_correctness"],
                    row["review_attempt_id"],
                )
                for row in outcome_lineage
            ] == [
                (
                    first_ready["run"]["id"],
                    first_ready["artifact"]["artifactId"],
                    "source-grounded-rephrase",
                    "pending",
                    None,
                    None,
                ),
                (
                    second_ready["run"]["id"],
                    second_ready["artifact"]["artifactId"],
                    "source-grounded-example",
                    "pending",
                    None,
                    None,
                ),
            ]
            protected_after = {
                table: int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in protected_before
            }
            assert protected_after == protected_before
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM study_practice_runs WHERE session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == practice_count_before
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE study_session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 2
            )

        practice_handoff = await service.start(
            **_start_args(
                graph,
                key="intervention-lineage-practice-005",
                intent=LearningInterventionIntent.TEST_ME_INSTEAD,
                predecessor_run_id=str(second_ready["run"]["id"]),
                predecessor_artifact_id=str(second_ready["artifact"]["artifactId"]),
            )
        )
        assert practice_handoff["status"] == "practice_ready"
        assert (
            practice_handoff["practice"]["practiceRunId"]
            == second_ready["practice"]["practiceRunId"]
        )

        with pytest.raises(
            LearningInterventionConflictError,
            match="predecessor is stale or unavailable",
        ):
            await service.start(
                **_start_args(
                    graph,
                    key="intervention-lineage-old-head-006",
                    predecessor_run_id=str(first_ready["run"]["id"]),
                    predecessor_artifact_id=str(first_ready["artifact"]["artifactId"]),
                )
            )
        with database.connection() as connection:
            TargetedPracticeProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
                run_id=str(practice_handoff["practice"]["practiceRunId"]),
                expected_revision=int(practice_handoff["practice"]["sessionRevision"]),
                idempotency_key="intervention-lineage-practice-answer-005",
                response="still not the expected term",
                now=NOW,
            )
            scored_lineage = InterventionOutcomeRepository(
                connection
            ).list_published_for_session(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert len(scored_lineage) == 2
            assert {
                (row["practice_status"], row["practice_correctness"])
                for row in scored_lineage
            } == {("answered", "incorrect")}
            assert all(row["review_attempt_id"] is None for row in scored_lineage)
            with pytest.raises(
                sqlite3.IntegrityError,
                match="intervention outcome lineage is immutable",
            ):
                connection.execute(
                    """
                    UPDATE learning_intervention_outcomes
                    SET playbook_slug = 'changed'
                    """
                )
        await runtime.shutdown()

    asyncio.run(scenario())


def test_unpublished_outcome_lineage_remains_hidden(tmp_path) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        runtime = AgentRuntimeManager(
            database, provider_factory=lambda: _ArtifactProvider()
        )
        service = LearningInterventionService(database, runtime)

        started = await service.start(
            **_start_args(graph, key="intervention-unpublished-lineage-001")
        )
        await _wait_terminal(runtime, str(started["run"]["id"]))
        await asyncio.sleep(0)
        ready = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert ready["status"] == "ready"

        with database.connection() as connection:
            repository = InterventionOutcomeRepository(connection)
            published = repository.list_published_for_session(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert len(published) == 1
            original = published[0]
            repository.record_exposure(
                course_id=str(original["course_id"]),
                session_id=str(original["session_id"]),
                unit_id=str(original["unit_id"]),
                trigger_active_recall_run_id=str(
                    original["trigger_active_recall_run_id"]
                ),
                intervention_run_id=str(original["intervention_run_id"]),
                intervention_artifact_id="artifact-not-durably-published",
                practice_run_id=str(original["practice_run_id"]),
                playbook_slug=str(original["playbook_slug"]),
                playbook_version=int(original["playbook_version"]),
                playbook_definition_hash=str(original["playbook_definition_hash"]),
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM learning_intervention_outcomes"
                ).fetchone()[0]
                == 2
            )
            visible = repository.list_published_for_session(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert [row["intervention_artifact_id"] for row in visible] == [
                ready["artifact"]["artifactId"]
            ]
        await runtime.shutdown()

    asyncio.run(scenario())


def test_intervention_outcome_reaches_later_practice_and_review(tmp_path) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        first_graph = _ready_recall(database, correct=False)
        runtime = AgentRuntimeManager(
            database, provider_factory=lambda: _ArtifactProvider()
        )
        service = LearningInterventionService(database, runtime)

        first_started = await service.start(
            **_start_args(first_graph, key="intervention-outcome-first-001")
        )
        await _wait_terminal(runtime, str(first_started["run"]["id"]))
        await asyncio.sleep(0)
        first_ready = service.get_current(
            course_id="course-calculus",
            session_id=str(first_graph["session_id"]),
        )
        assert first_ready["status"] == "ready"
        with database.connection() as connection:
            first_practice = TargetedPracticeProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
                run_id=str(first_ready["practice"]["practiceRunId"]),
                expected_revision=int(first_ready["practice"]["sessionRevision"]),
                idempotency_key="intervention-outcome-first-practice-answer",
                response="not the expected term",
                now=NOW,
            )
            assert first_practice.session["status"] == "studying"
            recall = ActiveRecallProgressionService(connection).begin(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
                expected_revision=int(first_practice.session["revision"]),
                idempotency_key="intervention-outcome-second-recall-begin",
                now=NOW,
            )
            recalled = ActiveRecallProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
                run_id=str(recall.run["id"]),
                expected_revision=int(recall.session["revision"]),
                idempotency_key="intervention-outcome-second-recall-answer",
                response="still not the expected term",
                now=NOW,
            )
        second_graph = {
            "session_id": first_graph["session_id"],
            "unit_id": recall.current_unit["id"],
            "revision": recalled.session["revision"],
        }
        second_started = await service.start(
            **_start_args(second_graph, key="intervention-outcome-second-001")
        )
        await _wait_terminal(runtime, str(second_started["run"]["id"]))
        second_ready = service.get_current(
            course_id="course-calculus",
            session_id=str(first_graph["session_id"]),
        )
        assert second_ready["status"] == "ready"
        with database.connection() as connection:
            second_practice = TargetedPracticeProgressionService(connection).answer(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
                run_id=str(second_ready["practice"]["practiceRunId"]),
                expected_revision=int(second_ready["practice"]["sessionRevision"]),
                idempotency_key="intervention-outcome-second-practice-answer",
                response="not the expected term",
                now=NOW,
            )
            assert second_practice.session["status"] == "summarizing"
            completed = StudySummaryReviewService(connection).complete(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
                expected_revision=int(second_practice.session["revision"]),
                idempotency_key="intervention-outcome-summary-complete",
                now=NOW,
            )
            assert completed.review is not None
            before_review = InterventionOutcomeRepository(
                connection
            ).list_published_for_session(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
            )
            assert len(before_review) == 2
            assert before_review[0]["review_item_id"] is None
            review_item_id = str(before_review[1]["review_item_id"])
            assert before_review[1]["review_attempt_id"] is None
            review_repository = ReviewRepository(connection)
            review_item = review_repository.get_item(review_item_id)
            assert review_item is not None
            assert review_item["due_at"] == completed.review["due_at"]
            reviewed_at = datetime.fromisoformat(str(review_item["due_at"]))
            ReviewSessionService(connection).record_attempt(
                item_id=review_item_id,
                rating="good",
                response="independent delayed response",
                expected_revision=int(review_item["revision"]),
                idempotency_key="intervention-outcome-review-attempt",
                reviewed_at=reviewed_at,
            )
            after_review = InterventionOutcomeRepository(
                connection
            ).list_published_for_session(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
            )
            assert after_review[1]["review_rating"] == "good"
            assert after_review[1]["reviewed_at"] == reviewed_at.isoformat()
            assert after_review[1]["review_revision_before"] == 0
            assert after_review[1]["review_revision_after"] == 1

            review_item = review_repository.get_item(review_item_id)
            assert review_item is not None
            second_reviewed_at = datetime.fromisoformat(str(review_item["due_at"]))
            second_review = ReviewSessionService(connection).record_attempt(
                item_id=review_item_id,
                rating="easy",
                response="second delayed response",
                expected_revision=int(review_item["revision"]),
                idempotency_key="intervention-outcome-second-review-attempt",
                reviewed_at=second_reviewed_at,
            )
            latest = InterventionOutcomeRepository(
                connection
            ).list_published_for_session(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
            )
            assert latest[1]["review_item_id"] == review_item_id
            assert latest[1]["review_attempt_id"] == second_review.attempt["id"]
            assert latest[1]["review_rating"] == "easy"
            assert latest[1]["review_revision_before"] == 1
            assert latest[1]["review_revision_after"] == 2

            unrelated_reviewed_at = second_reviewed_at + timedelta(seconds=1)
            unrelated, created = review_repository.create_item(
                item_id="review-unrelated-later-attempt",
                course_id="course-calculus",
                concept_id=str(review_item["concept_id"]),
                item_type="free_recall",
                prompt="Unrelated later review item.",
                expected_answer={"required_terms": ["unrelated"]},
                source_type="manual",
                source_id=None,
                due_at=unrelated_reviewed_at.isoformat(),
                scheduler_version=str(review_item["scheduler_version"]),
                idempotency_key="intervention-outcome-unrelated-review-item",
                created_at=unrelated_reviewed_at.isoformat(),
            )
            assert created is True
            unrelated_attempt = ReviewSessionService(connection).record_attempt(
                item_id=str(unrelated["id"]),
                rating="again",
                response="unrelated response",
                expected_revision=int(unrelated["revision"]),
                idempotency_key="intervention-outcome-unrelated-review-attempt",
                reviewed_at=unrelated_reviewed_at,
            )
            isolated = InterventionOutcomeRepository(
                connection
            ).list_published_for_session(
                course_id="course-calculus",
                session_id=str(first_graph["session_id"]),
            )
            assert isolated[1]["review_item_id"] == review_item_id
            assert isolated[1]["review_attempt_id"] == second_review.attempt["id"]
            assert isolated[1]["review_attempt_id"] != unrelated_attempt.attempt["id"]
        await runtime.shutdown()

    asyncio.run(scenario())


def test_practice_failure_keeps_matching_adaptive_action_retryable(
    tmp_path, monkeypatch
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        provider = _ArtifactProvider()
        runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
        service = LearningInterventionService(database, runtime)
        original_begin = TargetedPracticeProgressionService.begin

        def fail_practice(*_args, **_kwargs):
            raise RuntimeError("simulated Practice persistence failure")

        monkeypatch.setattr(TargetedPracticeProgressionService, "begin", fail_practice)
        started = await service.start(
            **_start_args(graph, key="intervention-practice-failure-001")
        )
        terminal = await _wait_terminal(runtime, started["run"]["id"])
        assert terminal["status"] == "failed"
        assert not any(
            event.payload.get("kind") == "learning_intervention_artifact"
            for event in runtime.event_store.list_events(started["run"]["id"])
        )
        with database.connection() as connection:
            retry_state = AdaptiveStudySessionService(connection).get(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert retry_state.action is not None
            assert retry_state.action["kind"] == "practice"
            assert retry_state.action["status"] == "pending"
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM study_practice_runs WHERE session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 0
            )
        assert (
            service.get_current(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )["status"]
            == "source_review"
        )

        monkeypatch.setattr(
            TargetedPracticeProgressionService,
            "begin",
            original_begin,
        )
        recovered = await service.start(
            **_start_args(
                graph,
                key="intervention-practice-recovery-001",
                intent=LearningInterventionIntent.TEST_ME_INSTEAD,
            )
        )
        assert recovered["status"] == "practice_ready"
        with database.connection() as connection:
            restored = AdaptiveStudySessionService(connection).get(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )
            assert restored.state == "canonical"
            assert restored.action is None
        await runtime.shutdown()

    asyncio.run(scenario())


def test_provider_missing_reuses_full_agent_run_idempotency_validation(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        runtime = AgentRuntimeManager(database)
        service = LearningInterventionService(database, runtime)
        key = "intervention-provider-missing-idempotency-001"
        first = await service.start(**_start_args(graph, key=key))
        assert first["status"] == "source_review"
        run = runtime.get_run(first["run"]["id"])
        assert run is not None
        changed_input = json.loads(json.dumps(run["input"]))
        changed_input["intervention"]["intent"] = "show_source_example"

        with pytest.raises(
            ValueError, match="idempotency key was reused with a different run payload"
        ):
            service._record_provider_missing(
                session_id=str(graph["session_id"]),
                input_data=changed_input,
                user_intent=str(run["user_intent"]),
                idempotency_key=key,
                error_code="provider_missing",
            )
        with database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE study_session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 1
            )

    asyncio.run(scenario())


def test_provider_configuration_reoffers_missing_intervention_without_auto_start(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        missing_runtime = AgentRuntimeManager(database)
        missing_service = LearningInterventionService(database, missing_runtime)
        old_key = "intervention-provider-missing-recovery-001"

        missing = await missing_service.start(**_start_args(graph, key=old_key))
        assert missing["status"] == "source_review"
        assert missing["reason"] == "provider_missing"
        missing_run_id = missing["run"]["id"]

        provider = _ArtifactProvider()
        recovered_runtime = AgentRuntimeManager(
            database,
            provider_factory=lambda: provider,
        )
        recovered_service = LearningInterventionService(database, recovered_runtime)
        eligible = recovered_service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )

        assert eligible["status"] == "eligible"
        assert eligible["run"] is None
        with database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE study_session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 1
            )

        with pytest.raises(
            LearningInterventionConflictError,
            match="idempotency key was reused with a different run payload",
        ):
            await recovered_service.start(
                **_start_args(
                    graph,
                    key=old_key,
                    intent=LearningInterventionIntent.SHOW_SOURCE_EXAMPLE,
                )
            )

        restarted = await recovered_service.start(
            **_start_args(
                graph,
                key="intervention-provider-recovered-002",
            )
        )
        assert restarted["run"]["id"] != missing_run_id
        assert (await _wait_terminal(recovered_runtime, restarted["run"]["id"]))[
            "status"
        ] == "completed"
        assert (
            recovered_service.get_current(
                course_id="course-calculus",
                session_id=str(graph["session_id"]),
            )["status"]
            == "ready"
        )
        with database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE study_session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 2
            )
        await recovered_runtime.shutdown()

    asyncio.run(scenario())


def test_provider_unavailable_failure_is_not_automatically_reoffered(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)

        def unavailable_provider():
            raise RuntimeError("provider initialization failed")

        unavailable_service = LearningInterventionService(
            database,
            AgentRuntimeManager(
                database,
                provider_factory=unavailable_provider,
            ),
        )
        unavailable = await unavailable_service.start(
            **_start_args(
                graph,
                key="intervention-provider-unavailable-001",
            )
        )
        assert unavailable["status"] == "source_review"
        assert unavailable["reason"] == "provider_unavailable"

        recovered_service = LearningInterventionService(
            database,
            AgentRuntimeManager(
                database,
                provider_factory=_ArtifactProvider,
            ),
        )
        current = recovered_service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert current["status"] == "source_review"
        assert current["reason"] == "provider_unavailable"

    asyncio.run(scenario())


def test_cancellation_and_last_event_replay_use_existing_agent_events(tmp_path) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        provider = _BlockingProvider()
        runtime = AgentRuntimeManager(database, provider_factory=lambda: provider)
        service = LearningInterventionService(database, runtime)
        started = await service.start(
            **_start_args(graph, key="intervention-cancel-replay-001")
        )
        run_id = started["run"]["id"]
        await asyncio.wait_for(provider.started.wait(), timeout=2)
        events_before_cancel = runtime.event_store.list_events(run_id)
        assert events_before_cancel
        cancelled = await service.cancel(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
            run_id=run_id,
        )
        await _wait_terminal(runtime, run_id)
        assert cancelled["status"] == "cancelled"

        all_events = runtime.event_store.list_events(run_id)
        cursor = events_before_cancel[-1].id
        cursor_sequence = runtime.event_store.sequence_after_last_event_id(
            run_id, cursor
        )
        replayed = runtime.event_store.list_events(
            run_id,
            after_sequence=cursor_sequence,
        )
        assert replayed == all_events[cursor_sequence + 1 :]
        assert replayed[-1].event_type == "error"
        snapshot = service.get_current(
            course_id="course-calculus",
            session_id=str(graph["session_id"]),
        )
        assert snapshot["status"] == "cancelled"
        await runtime.shutdown()

    asyncio.run(scenario())


def test_test_me_instead_bypasses_provider_and_replays_existing_practice(
    tmp_path,
) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(database, correct=False)
        runtime = AgentRuntimeManager(database)
        service = LearningInterventionService(database, runtime)
        arguments = _start_args(
            graph,
            key="intervention-test-instead-001",
            intent=LearningInterventionIntent.TEST_ME_INSTEAD,
        )
        first = await service.start(**arguments)
        second = await service.start(**arguments)
        assert first["status"] == "practice_ready"
        assert second["status"] == "practice_ready"
        assert first["practice"]["practiceRunId"] == second["practice"]["practiceRunId"]
        with database.connection() as connection:
            adaptive_rows = connection.execute(
                """SELECT kind, status, predecessor_active_recall_run_id
                   FROM study_adaptive_actions WHERE session_id = ?
                   ORDER BY kind""",
                (graph["session_id"],),
            ).fetchall()
            assert [tuple(row) for row in adaptive_rows] == [
                ("practice", "completed", graph["recall_run_id"]),
                ("remediate", "completed", graph["recall_run_id"]),
            ]
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM study_practice_runs WHERE session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE study_session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 0
            )

    asyncio.run(scenario())


def test_legacy_session_keeps_direct_existing_practice_handoff(tmp_path) -> None:
    async def scenario() -> None:
        database = _database(tmp_path)
        graph = _ready_recall(
            database,
            correct=False,
            legacy_session=True,
        )
        runtime = AgentRuntimeManager(database)
        service = LearningInterventionService(database, runtime)
        result = await service.start(
            **_start_args(
                graph,
                key="intervention-legacy-practice-001",
                intent=LearningInterventionIntent.TEST_ME_INSTEAD,
            )
        )
        assert result["status"] == "practice_ready"
        with database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM study_adaptive_actions WHERE session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM study_practice_runs WHERE session_id = ?",
                    (graph["session_id"],),
                ).fetchone()[0]
                == 1
            )

    asyncio.run(scenario())
