from __future__ import annotations

import pytest

from app.agent.event_stream import AgentEventStore
from app.database import Database
from app.repositories.agent_repository import AgentRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.study_repository import StudyRepository


@pytest.fixture
def repository(tmp_path):
    database = Database(tmp_path / "agent.sqlite3")
    database.migrate()
    database.seed_demo()
    with database.connection() as connection:
        yield AgentRepository(connection), connection


def _create_run(
    repo: AgentRepository, *, run_id: str = "run-1", key: str = "request-1"
):
    return repo.create_run(
        run_id=run_id,
        kind="conversation",
        user_intent="Explain limits",
        mode="teach",
        provider="local",
        model="fixture",
        prompt_version="v1",
        input_data={"question": "What is a limit?"},
        idempotency_key=key,
    )


def test_run_and_tool_audit_are_idempotent_and_atomic(repository):
    repo, connection = repository
    run = _create_run(repo)
    replay = _create_run(repo, run_id="ignored")
    assert replay["id"] == run["id"]
    with pytest.raises(ValueError, match="different run payload"):
        repo.create_run(
            run_id="different",
            kind="conversation",
            user_intent="Changed",
            mode="teach",
            provider="local",
            model="fixture",
            prompt_version="v1",
            input_data={},
            idempotency_key="request-1",
        )
    repo.transition_run(run["id"], status="running")
    invocation = repo.start_tool_invocation(
        invocation_id="tool-1",
        run_id=run["id"],
        tool_name="create_note",
        permission_level=2,
        arguments={"title": "Limit"},
        idempotency_key="step-1",
    )
    repo.complete_tool_invocation(
        invocation["id"],
        result_summary={"entity_id": "note-1"},
        mutations=[
            {
                "id": "mutation-1",
                "entity_type": "note",
                "entity_id": "note-1",
                "operation": "create",
                "after": {"title": "Limit"},
                "undo": {"operation": "delete"},
                "reversible": True,
            }
        ],
    )
    assert (
        connection.execute("SELECT reversible FROM state_mutations").fetchone()[0] == 1
    )
    assert repo.get_tool_invocation("tool-1")["result_summary"] == {
        "entity_id": "note-1"
    }


def test_tool_permission_boundaries_fail_closed(repository):
    repo, _ = repository
    _create_run(repo)
    read = repo.start_tool_invocation(
        invocation_id="read",
        run_id="run-1",
        tool_name="search",
        permission_level=1,
        arguments={},
        idempotency_key="read",
    )
    with pytest.raises(PermissionError, match="level 1"):
        repo.complete_tool_invocation(
            read["id"],
            result_summary={"count": 1},
            mutations=[
                {
                    "id": "m1",
                    "entity_type": "note",
                    "entity_id": "n",
                    "operation": "create",
                    "after": {},
                }
            ],
        )
    local_write = repo.start_tool_invocation(
        invocation_id="write",
        run_id="run-1",
        tool_name="note",
        permission_level=2,
        arguments={},
        idempotency_key="write",
    )
    with pytest.raises(PermissionError, match="reversible"):
        repo.complete_tool_invocation(
            local_write["id"],
            result_summary={"entity_id": "n"},
            mutations=[
                {
                    "id": "m2",
                    "entity_type": "note",
                    "entity_id": "n",
                    "operation": "create",
                    "after": {},
                }
            ],
        )


def test_tool_audit_recursively_redacts_sensitive_arguments_and_summary(repository):
    repo, _ = repository
    _create_run(repo)
    invocation = repo.start_tool_invocation(
        invocation_id="audit",
        run_id="run-1",
        tool_name="search",
        permission_level=1,
        arguments={
            "query_id": "q1",
            "document_id": "document-1",
            "chunk_ids": ["chunk-1"],
            "context": "retrieval",
            "nested": {
                "document_text": "private source",
                "source_content": "private source content",
                "token": "secret-token",
                "path": "/private/path",
            },
        },
        idempotency_key="audit",
    )
    assert invocation["arguments"]["document_id"] == "document-1"
    assert invocation["arguments"]["chunk_ids"] == ["chunk-1"]
    assert invocation["arguments"]["context"] == "[REDACTED:TEXT]"
    assert invocation["arguments"]["nested"]["document_text"] == "[REDACTED]"
    assert invocation["arguments"]["nested"]["source_content"] == "[REDACTED]"
    assert invocation["arguments"]["nested"]["token"] == "[REDACTED]"
    assert invocation["arguments"]["nested"]["path"] == "[REDACTED]"
    completed = repo.complete_tool_invocation(
        invocation["id"],
        result_summary={"count": 1, "nested": {"content": "private result"}},
        mutations=[],
    )
    assert completed["result_summary"]["nested"]["content"] == "[REDACTED]"
    with pytest.raises(ValueError, match="different tool arguments"):
        repo.start_tool_invocation(
            invocation_id="audit-replay",
            run_id="run-1",
            tool_name="search",
            permission_level=1,
            arguments={
                "query_id": "q1",
                "document_id": "document-1",
                "chunk_ids": ["chunk-1"],
                "context": "retrieval",
                "nested": {
                    "document_text": "different private source",
                    "source_content": "private source content",
                    "token": "secret-token",
                    "path": "/private/path",
                },
            },
            idempotency_key="audit",
        )


def test_repository_audit_rejects_identifier_and_reasoning_privacy_bypasses(
    repository,
):
    repo, _ = repository
    _create_run(repo)
    invocation = repo.start_tool_invocation(
        invocation_id="privacy",
        run_id="run-1",
        tool_name="search",
        permission_level=1,
        arguments={
            "document_id": "private lesson text with spaces",
            "concept_ids": ["concept-safe", "student medical details"],
            "chainOfThought": "private reasoning",
            "chainofthought": "more private reasoning",
            "reasoning-trace": "private trace",
            "unknown_field": "full private source body",
        },
        idempotency_key="privacy",
    )
    assert invocation["arguments"] == {
        "chainOfThought": "[REDACTED]",
        "chainofthought": "[REDACTED]",
        "concept_ids": ["concept-safe", "[REDACTED:INVALID_ID]"],
        "document_id": "[REDACTED:INVALID_ID]",
        "reasoning-trace": "[REDACTED]",
        "unknown_field": "[REDACTED:TEXT]",
    }


def test_agent_run_rejects_mismatched_conversation_and_session_context(repository):
    repo, connection = repository
    conversations = ConversationRepository(connection)
    studies = StudyRepository(connection)
    conversations.create_conversation(
        conversation_id="calculus-conversation",
        course_id="course-calculus",
        title="Calculus",
        mode="study",
    )
    conversations.create_conversation(
        conversation_id="physics-conversation",
        course_id="course-physics",
        title="Physics",
        mode="study",
    )
    studies.create_session(
        session_id="physics-session",
        course_id="course-physics",
        conversation_id="physics-conversation",
        title="Physics",
        mode="study",
        goal="Learn mechanics",
        estimated_minutes=30,
    )
    with pytest.raises(ValueError, match="do not match"):
        repo.create_run(
            run_id="bad-context",
            conversation_id="calculus-conversation",
            study_session_id="physics-session",
            kind="deep_learn",
            user_intent="Learn",
            mode="study",
            provider="local",
            model="fixture",
            prompt_version="v1",
            input_data={},
            idempotency_key="bad-context",
        )


def test_find_latest_run_uses_persisted_conversation_or_study_session(
    repository,
):
    repo, connection = repository
    conversations = ConversationRepository(connection)
    studies = StudyRepository(connection)
    conversations.create_conversation(
        conversation_id="activity-conversation",
        course_id="course-calculus",
        title="Activity conversation",
        mode="teach",
    )
    studies.create_session(
        session_id="focused-study-session",
        course_id="course-calculus",
        conversation_id="activity-conversation",
        title="Focused limits",
        mode="study",
        goal="Understand limits",
        estimated_minutes=25,
    )
    for run_id, created_at, conversation_id, study_session_id in (
        (
            "run-conversation-old",
            "2026-07-24T10:00:00+00:00",
            "activity-conversation",
            None,
        ),
        (
            "run-conversation-new",
            "2026-07-24T11:00:00+00:00",
            "activity-conversation",
            None,
        ),
        ("run-focused", "2026-07-24T12:00:00+00:00", None, "focused-study-session"),
    ):
        repo.create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            study_session_id=study_session_id,
            kind="deep_learn" if study_session_id else "conversation",
            user_intent="Understand limits",
            mode="study" if study_session_id else "teach",
            provider="local",
            model="fixture",
            prompt_version="v1",
            input_data={},
            idempotency_key=f"key-{run_id}",
        )
        connection.execute(
            "UPDATE agent_runs SET created_at = ? WHERE id = ?",
            (created_at, run_id),
        )
    connection.commit()

    assert (
        repo.find_latest_run(conversation_id="activity-conversation")["id"]
        == "run-conversation-new"
    )
    assert (
        repo.find_latest_run(study_session_id="focused-study-session")["id"]
        == "run-focused"
    )
    assert repo.find_latest_run(conversation_id="missing-conversation") is None
    with pytest.raises(ValueError, match="exactly one"):
        repo.find_latest_run()


def test_latest_run_activity_uses_one_sqlite_read_snapshot(tmp_path, monkeypatch):
    database = Database(tmp_path / "agent-activity-snapshot.sqlite3")
    database.migrate()
    database.seed_demo()
    with database.connection() as connection:
        ConversationRepository(connection).create_conversation(
            conversation_id="snapshot-conversation",
            course_id="course-calculus",
            title="Snapshot consistency",
            mode="teach",
        )
        repository = AgentRepository(connection)
        repository.create_run(
            run_id="snapshot-run",
            conversation_id="snapshot-conversation",
            kind="conversation",
            user_intent="Explain limits",
            mode="teach",
            provider="local",
            model="fixture",
            prompt_version="v1",
            input_data={},
            idempotency_key="snapshot-run",
        )
        repository.transition_run("snapshot-run", status="running")
        repository.append_event(
            event_id="snapshot-running",
            run_id="snapshot-run",
            event_type="status",
            payload={"status": "running"},
        )

    original_list_events = AgentRepository.list_events
    concurrent_write_committed = False

    def list_events_after_concurrent_completion(
        repository: AgentRepository,
        run_id: str,
        *,
        after_sequence: int = -1,
    ) -> list[dict]:
        nonlocal concurrent_write_committed
        with database.connection() as writer_connection:
            writer_repository = AgentRepository(writer_connection)
            writer_connection.execute("BEGIN IMMEDIATE")
            try:
                writer_repository.transition_run(
                    run_id,
                    status="completed",
                    commit=False,
                )
                writer_repository.append_event(
                    event_id="snapshot-done",
                    run_id=run_id,
                    event_type="done",
                    payload={"status": "completed"},
                    commit=False,
                )
                writer_connection.commit()
            except Exception:
                writer_connection.rollback()
                raise
        concurrent_write_committed = True
        return original_list_events(
            repository,
            run_id,
            after_sequence=after_sequence,
        )

    monkeypatch.setattr(
        AgentRepository,
        "list_events",
        list_events_after_concurrent_completion,
    )

    run, events = AgentEventStore(database).get_latest_run_activity(
        conversation_id="snapshot-conversation"
    )

    assert concurrent_write_committed
    assert run is not None
    assert run["status"] == "running"
    assert [event.event_type for event in events] == ["status"]
    assert events[0].payload == {"status": "running"}

    with database.connection() as connection:
        repository = AgentRepository(connection)
        assert repository.get_run("snapshot-run")["status"] == "completed"
        assert [
            row["event_type"]
            for row in original_list_events(repository, "snapshot-run")
        ] == ["status", "done"]


def test_agent_run_persists_scope_from_trusted_context_only(repository):
    repo, connection = repository
    conversations = ConversationRepository(connection)
    studies = StudyRepository(connection)
    conversations.create_conversation(
        conversation_id="trusted-conversation",
        course_id="course-calculus",
        title="Calculus",
        mode="study",
    )
    studies.create_session(
        session_id="trusted-session",
        course_id="course-calculus",
        conversation_id="trusted-conversation",
        title="Calculus",
        mode="study",
        goal="Learn limits",
        estimated_minutes=30,
    )

    run = repo.create_run(
        run_id="trusted-scope",
        conversation_id="trusted-conversation",
        study_session_id="trusted-session",
        kind="deep_learn",
        user_intent="Learn",
        mode="study",
        provider="course-physics",
        model="fixture",
        prompt_version="v1",
        input_data={"course_scope_id": "course-physics", "courseId": "course-physics"},
        idempotency_key="trusted-scope",
    )

    assert run["course_scope_id"] == "course-calculus"
    assert repo.get_run(run["id"])["course_scope_id"] == "course-calculus"


@pytest.mark.parametrize(
    ("conversation_id", "study_session_id", "message"),
    [
        ("missing-conversation", None, "conversation context does not exist"),
        (None, "missing-session", "study session context does not exist"),
    ],
)
def test_agent_run_rejects_nonexistent_context_with_stable_value_error(
    repository, conversation_id, study_session_id, message
):
    repo, _ = repository
    with pytest.raises(ValueError, match=message):
        repo.create_run(
            run_id="missing-context",
            conversation_id=conversation_id,
            study_session_id=study_session_id,
            kind="conversation",
            user_intent="Learn",
            mode="study",
            provider="local",
            model="fixture",
            prompt_version="v1",
            input_data={},
            idempotency_key="missing-context",
        )


def test_agent_run_idempotency_includes_resolved_course_scope(repository):
    repo, connection = repository
    conversations = ConversationRepository(connection)
    conversations.create_conversation(
        conversation_id="scope-replay",
        course_id="course-calculus",
        title="Calculus",
        mode="study",
    )
    original = repo.create_run(
        run_id="scope-replay-run",
        conversation_id="scope-replay",
        kind="conversation",
        user_intent="Learn",
        mode="study",
        provider="local",
        model="fixture",
        prompt_version="v1",
        input_data={},
        idempotency_key="scope-replay-key",
    )
    connection.execute(
        "UPDATE conversations SET course_id = 'course-physics' WHERE id = ?",
        ("scope-replay",),
    )
    connection.commit()

    with pytest.raises(ValueError, match="different run payload"):
        repo.create_run(
            run_id="ignored",
            conversation_id="scope-replay",
            kind="conversation",
            user_intent="Learn",
            mode="study",
            provider="local",
            model="fixture",
            prompt_version="v1",
            input_data={},
            idempotency_key="scope-replay-key",
        )
    assert repo.get_run(original["id"])["course_scope_id"] == "course-calculus"


def test_agent_invalid_transition_and_unvalidated_json_are_rejected(repository):
    repo, _ = repository
    _create_run(repo)
    with pytest.raises(ValueError, match="invalid run transition"):
        repo.transition_run("run-1", status="completed")
    with pytest.raises(ValueError, match="unsupported JSON"):
        repo.append_event(
            event_id="event",
            run_id="run-1",
            event_type="metadata",
            payload={"bad": object()},
        )  # type: ignore[dict-item]


def test_recovery_closes_run_step_tool_and_approval(repository):
    repo, connection = repository
    _create_run(repo)
    repo.transition_run("run-1", status="running")
    repo.add_step(
        step_id="step",
        run_id="run-1",
        ordinal=0,
        kind="tool",
        label="Export",
        input_data={},
    )
    repo.start_tool_invocation(
        invocation_id="tool",
        run_id="run-1",
        step_id="step",
        tool_name="export",
        permission_level=3,
        arguments={},
        idempotency_key="export-1",
    )
    repo.request_approval(
        approval_id="approval",
        run_id="run-1",
        invocation_id="tool",
        summary="Export data",
    )
    assert repo.recover_interrupted_runs() == ["run-1"]
    assert repo.get_run("run-1")["status"] == "interrupted"
    assert (
        connection.execute(
            "SELECT status FROM agent_steps WHERE id = 'step'"
        ).fetchone()[0]
        == "interrupted"
    )
    assert repo.get_tool_invocation("tool")["status"] == "cancelled"
    assert (
        connection.execute("SELECT status FROM approval_requests").fetchone()[0]
        == "cancelled"
    )
