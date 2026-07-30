from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.database import Database
from app.repositories.conversation_repository import (
    ConversationCreateConflictError,
    ConversationRepository,
    MessageCancellationConflictError,
    MessageTransitionConflictError,
    TurnIdempotencyConflictError,
)


@pytest.fixture
def repository(tmp_path):
    database = Database(tmp_path / "conversations.sqlite3")
    database.migrate()
    database.seed_demo()
    with database.connection() as connection:
        yield ConversationRepository(connection), connection


def test_conversation_messages_persist_metadata_and_validate_idempotency(repository):
    repo, connection = repository
    conversation = repo.create_conversation(
        conversation_id="conversation-1",
        course_id="course-calculus",
        title="Limits",
        mode="teach",
    )
    repo.append_message(
        message_id="question-1",
        conversation_id=conversation["id"],
        role="user",
        content="What is a limit?",
        status="completed",
    )
    message = repo.append_message(
        message_id="message-1",
        conversation_id=conversation["id"],
        role="assistant",
        content="A limit describes nearby behavior.",
        status="completed",
        idempotency_key="answer-1",
        model_provider="local",
        model_name="fixture",
        prompt_version="v1",
        reply_to_message_id="question-1",
        retrieval_limit=8,
    )
    replay = repo.append_message(
        message_id="ignored-on-replay",
        conversation_id=conversation["id"],
        role="assistant",
        content="A limit describes nearby behavior.",
        status="completed",
        idempotency_key="answer-1",
        model_provider="local",
        model_name="fixture",
        prompt_version="v1",
        reply_to_message_id="question-1",
        retrieval_limit=8,
    )
    assert conversation["mode"] == "teach"
    assert message["model_name"] == "fixture"
    assert replay["id"] == "message-1"
    with pytest.raises(ValueError, match="different message payload"):
        repo.append_message(
            message_id="message-2",
            conversation_id=conversation["id"],
            role="assistant",
            content="changed",
            status="completed",
            idempotency_key="answer-1",
            reply_to_message_id="question-1",
            retrieval_limit=8,
        )
    assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2


def test_recovery_marks_only_unfinished_messages_interrupted(repository):
    repo, _ = repository
    repo.create_conversation(conversation_id="c", title="Recovery")
    repo.append_message(
        message_id="done",
        conversation_id="c",
        role="user",
        content="question",
        status="completed",
    )
    repo.append_message(
        message_id="streaming",
        conversation_id="c",
        role="assistant",
        content="partial",
        status="streaming",
        reply_to_message_id="done",
        retrieval_limit=8,
    )
    assert repo.recover_interrupted_messages() == ["streaming"]
    assert repo.get_message("streaming")["status"] == "interrupted"
    assert repo.get_message("done")["status"] == "completed"


def test_conversation_write_can_join_and_roll_back_outer_transaction(repository):
    repo, connection = repository
    connection.execute("BEGIN IMMEDIATE")
    repo.create_conversation(conversation_id="rolled-back", title="Draft")
    connection.rollback()
    assert repo.get_conversation("rolled-back") is None
    with pytest.raises(RuntimeError, match="caller-owned transaction"):
        repo.create_conversation(
            conversation_id="no-owner", title="Draft", commit=False
        )


def test_009_upgrades_an_008_database_without_data_loss(tmp_path):
    database = Database(tmp_path / "upgrade-from-008.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for version in range(1, 9):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute(
            "INSERT INTO courses (id, title, description, created_at) VALUES ('legacy', 'Legacy', '', '2026-01-01T00:00:00+00:00')"
        )
        connection.commit()
    assert {9, 10, 11, 12}.issubset(database.migrate())
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT title FROM courses WHERE id = 'legacy'"
            ).fetchone()[0]
            == "Legacy"
        )
    database.verify_consistency()


def test_conversation_create_and_turn_are_idempotent_with_stable_sequences(repository):
    repo, connection = repository
    created = repo.create_conversation(
        conversation_id="durable-conversation",
        course_id="course-calculus",
        title="Limits",
        source_scope_kind="course",
        create_payload_fingerprint="a" * 64,
    )
    replay = repo.create_conversation(
        conversation_id="durable-conversation",
        course_id="course-calculus",
        title="Limits",
        source_scope_kind="course",
        create_payload_fingerprint="a" * 64,
    )
    assert created["replayed"] is False
    assert replay["replayed"] is True
    assert {key: value for key, value in created.items() if key != "replayed"} == {
        key: value for key, value in replay.items() if key != "replayed"
    }
    assert created["source_scope"] == {
        "kind": "course",
        "course_id": "course-calculus",
    }
    with pytest.raises(ConversationCreateConflictError):
        repo.create_conversation(
            conversation_id="durable-conversation",
            course_id="course-calculus",
            title="Changed title",
            source_scope_kind="course",
            create_payload_fingerprint="a" * 64,
        )

    turn = repo.create_turn(
        conversation_id="durable-conversation",
        user_message_id="turn-user-1",
        assistant_message_id="turn-assistant-1",
        question="What is a limit?",
        source_scope_kind="course",
        source_course_id="course-calculus",
        retrieval_limit=8,
        idempotency_key="durable-turn-1",
        model_provider="ollama",
        model_name="fixture",
        prompt_version="v1",
    )
    turn_replay = repo.create_turn(
        conversation_id="durable-conversation",
        user_message_id="turn-user-1",
        assistant_message_id="turn-assistant-1",
        question="What is a limit?",
        source_scope_kind="course",
        source_course_id="course-calculus",
        retrieval_limit=8,
        idempotency_key="durable-turn-1",
        model_provider="ollama",
        model_name="fixture",
        prompt_version="v1",
    )
    assert turn["replayed"] is False
    assert turn_replay["replayed"] is True
    assert turn_replay["user_message"]["id"] == "turn-user-1"
    assert turn_replay["assistant_message"]["id"] == "turn-assistant-1"
    with pytest.raises(ValueError, match="different payload"):
        repo.create_turn(
            conversation_id="durable-conversation",
            user_message_id="different-user-id",
            assistant_message_id="different-assistant-id",
            question="What is a limit?",
            source_scope_kind="course",
            source_course_id="course-calculus",
            retrieval_limit=8,
            idempotency_key="durable-turn-1",
            prompt_version="grounded-answer-v1",
        )
    assert [message["sequence"] for message in repo.list_messages(created["id"])] == [
        0,
        1,
    ]
    assert turn["assistant_message"]["reply_to_message_id"] == "turn-user-1"
    with pytest.raises(TurnIdempotencyConflictError):
        repo.create_turn(
            conversation_id="durable-conversation",
            user_message_id="turn-user-1",
            assistant_message_id="turn-assistant-1",
            question="A different question",
            source_scope_kind="course",
            source_course_id="course-calculus",
            retrieval_limit=8,
            idempotency_key="durable-turn-1",
            model_provider="ollama",
            model_name="fixture",
            prompt_version="v1",
        )
    assert connection.execute("SELECT count(*) FROM messages").fetchone()[0] == 2


def test_message_transitions_and_cancel_use_compare_and_swap(repository):
    repo, _ = repository
    repo.create_conversation(conversation_id="cas-conversation", title="CAS")
    repo.create_turn(
        conversation_id="cas-conversation",
        user_message_id="cas-user",
        assistant_message_id="cas-assistant",
        question="Run once",
        source_scope_kind="all_indexed",
        source_course_id=None,
        retrieval_limit=8,
        idempotency_key="cas-turn",
    )
    streaming = repo.transition_message(
        "cas-assistant",
        conversation_id="cas-conversation",
        expected_statuses=("pending",),
        status="streaming",
    )
    assert streaming["started_at"] is not None
    with pytest.raises(MessageTransitionConflictError):
        repo.transition_message(
            "cas-assistant",
            conversation_id="cas-conversation",
            expected_statuses=("pending",),
            status="streaming",
        )
    cancelled = repo.cancel_message(
        "cas-assistant",
        conversation_id="cas-conversation",
        cancel_key="cancel-cas-1",
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["finished_at"] is not None
    assert (
        repo.cancel_message(
            "cas-assistant",
            conversation_id="cas-conversation",
            cancel_key="cancel-cas-1",
        )["cancel_idempotency_key"]
        == "cancel-cas-1"
    )
    with pytest.raises(MessageCancellationConflictError):
        repo.cancel_message(
            "cas-assistant",
            conversation_id="cas-conversation",
            cancel_key="cancel-cas-2",
        )
    with pytest.raises(MessageTransitionConflictError):
        repo.complete_message(
            "cas-assistant",
            conversation_id="cas-conversation",
            content="Too late",
            citations=[],
        )


def test_two_connections_allow_only_one_terminal_transition(tmp_path):
    database = Database(tmp_path / "message-race.sqlite3")
    database.migrate()
    with database.connection() as connection:
        repo = ConversationRepository(connection)
        repo.create_conversation(conversation_id="race-conversation", title="Race")
        repo.create_turn(
            conversation_id="race-conversation",
            user_message_id="race-user",
            assistant_message_id="race-assistant",
            question="Which transition wins?",
            source_scope_kind="all_indexed",
            source_course_id=None,
            retrieval_limit=8,
            idempotency_key="race-turn",
        )

    barrier = threading.Barrier(2)

    def complete() -> str:
        with database.connection() as connection:
            barrier.wait()
            try:
                ConversationRepository(connection).complete_message(
                    "race-assistant",
                    conversation_id="race-conversation",
                    content="Completed",
                    citations=[],
                )
            except MessageTransitionConflictError:
                return "conflict"
            return "success"

    def cancel() -> str:
        with database.connection() as connection:
            barrier.wait()
            try:
                ConversationRepository(connection).cancel_message(
                    "race-assistant", "race-conversation", "race-cancel"
                )
            except MessageCancellationConflictError:
                return "conflict"
            return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [executor.submit(complete), executor.submit(cancel)]
        assert sorted(result.result(timeout=10) for result in results) == [
            "conflict",
            "success",
        ]
    with database.connection() as connection:
        terminal = ConversationRepository(connection).get_message("race-assistant")
    assert terminal["status"] in {"completed", "cancelled"}
    assert terminal["finished_at"] is not None


def _insert_citation_source(connection) -> None:
    now = "2026-07-21T00:00:00+00:00"
    connection.execute(
        """
        INSERT INTO documents
            (id, course_id, name, mime_type, extension, status, page_count,
             chunk_count, error, created_at, updated_at)
        VALUES ('citation-document', NULL, 'limits.txt', 'text/plain', '.txt',
                'indexed', 1, 1, NULL, ?, ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO document_versions
            (id, document_id, version_number, content_hash, storage_path,
             size_bytes, parser_version, page_count, created_at)
        VALUES ('citation-version', 'citation-document', 1, ?, 'aa/source.txt',
                10, 'fixture-v1', 1, ?)
        """,
        ("b" * 64, now),
    )
    connection.execute(
        """
        INSERT INTO document_chunks
            (id, document_id, version_id, ordinal, page_number, section_path,
             content, content_hash, text_location, parser_version, created_at)
        VALUES ('citation-chunk', 'citation-document', 'citation-version', 0, 1,
                '["Limits"]', 'A limit describes nearby behavior.', ?, '{}',
                'fixture-v1', ?)
        """,
        ("c" * 64, now),
    )
    connection.execute(
        """INSERT INTO course_documents(course_id, document_id, added_at)
           VALUES ('course-calculus', 'citation-document', ?)""",
        (now,),
    )
    connection.commit()


def _citation(*, content_hash: str = "c" * 64) -> dict:
    return {
        "id": "stored-citation-1",
        "source_index": 1,
        "document_id": "citation-document",
        "document_version_id": "citation-version",
        "chunk_id": "citation-chunk",
        "chunk_content_hash": content_hash,
        "document_name": "limits.txt",
        "page_number": 1,
        "section_path": ["Limits"],
        "quote": "A limit describes nearby behavior.",
        "bbox": None,
    }


def test_completion_persists_evidence_atomically_and_mismatch_rolls_back(repository):
    repo, connection = repository
    _insert_citation_source(connection)
    repo.create_conversation(
        conversation_id="evidence-conversation",
        course_id="course-calculus",
        title="Evidence",
    )
    repo.create_turn(
        conversation_id="evidence-conversation",
        user_message_id="evidence-user",
        assistant_message_id="evidence-assistant",
        question="Explain limits",
        source_scope_kind="course",
        source_course_id="course-calculus",
        retrieval_limit=8,
        idempotency_key="evidence-turn",
    )
    completed = repo.complete_message(
        "evidence-assistant",
        conversation_id="evidence-conversation",
        content="A limit describes nearby behavior.",
        citations=[_citation()],
    )
    assert completed["status"] == "completed"
    assert completed["citations"] == [
        {
            "citation_id": "stored-citation-1",
            "source_index": 1,
            "chunk_id": "citation-chunk",
            "document_id": "citation-document",
            "document_version_id": "citation-version",
            "chunk_content_hash": "c" * 64,
            "document_name": "limits.txt",
            "page_number": 1,
            "section_path": ["Limits"],
            "excerpt": "A limit describes nearby behavior.",
            "bbox": None,
        }
    ]

    repo.create_turn(
        conversation_id="evidence-conversation",
        user_message_id="bad-user",
        assistant_message_id="bad-assistant",
        question="Mismatch",
        source_scope_kind="course",
        source_course_id="course-calculus",
        retrieval_limit=8,
        idempotency_key="bad-evidence-turn",
    )
    bad_citation = _citation(content_hash="d" * 64)
    bad_citation["id"] = "stored-citation-bad"
    with pytest.raises(sqlite3.IntegrityError, match="citation evidence"):
        repo.complete_message(
            "bad-assistant",
            conversation_id="evidence-conversation",
            content="Must roll back",
            citations=[bad_citation],
        )
    assert repo.get_message("bad-assistant")["status"] == "pending"
    assert repo.get_message("bad-assistant")["content"] == ""


def test_recovery_terminalizes_durable_messages_and_updates_conversation(repository):
    repo, connection = repository
    repo.create_conversation(conversation_id="restart-conversation", title="Restart")
    repo.create_turn(
        conversation_id="restart-conversation",
        user_message_id="restart-user",
        assistant_message_id="restart-assistant",
        question="Resume?",
        source_scope_kind="all_indexed",
        source_course_id=None,
        retrieval_limit=8,
        idempotency_key="restart-turn",
    )
    connection.execute(
        "UPDATE conversations SET updated_at = '2000-01-01T00:00:00+00:00' WHERE id = 'restart-conversation'"
    )
    connection.commit()
    assert repo.recover_interrupted_messages() == ["restart-assistant"]
    recovered = repo.get_message("restart-assistant")
    assert recovered["status"] == "interrupted"
    assert recovered["error_code"] == "process_restarted"
    assert recovered["finished_at"] is not None
    assert (
        repo.get_conversation("restart-conversation")["updated_at"]
        != "2000-01-01T00:00:00+00:00"
    )
    assert repo.recover_interrupted_messages() == []


def test_027_preserves_nullable_legacy_conversation_rows(tmp_path):
    database = Database(tmp_path / "upgrade-from-026.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for version in range(1, 27):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute(
            """
            INSERT INTO conversations
                (id, title, mode, status, created_at, updated_at)
            VALUES ('legacy-conversation', 'Legacy', 'ask', 'active',
                    '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO messages
                (id, conversation_id, sequence, role, status, content,
                 created_at, updated_at)
            VALUES ('legacy-message', 'legacy-conversation', 0, 'assistant',
                    'streaming', 'partial',
                    '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:00+00:00')
            """
        )
        connection.commit()

    assert database.migrate() == [27, 28, 29, 30, 31, 32]
    with database.connection() as connection:
        repo = ConversationRepository(connection)
        assert repo.get_conversation("legacy-conversation")["source_scope"] is None
        assert repo.get_message("legacy-message")["source_scope"] is None
        assert repo.recover_interrupted_messages() == ["legacy-message"]
        with pytest.raises(sqlite3.IntegrityError, match="source scope is required"):
            connection.execute(
                """
                INSERT INTO conversations
                    (id, title, mode, status, created_at, updated_at)
                VALUES ('invalid-new', 'Invalid', 'ask', 'active', 'now', 'now')
                """
            )
        repo.create_conversation(conversation_id="durable-new", title="Durable")
        base_columns = """
            INSERT INTO messages
                (id, conversation_id, sequence, role, status, content,
                 created_at, updated_at, source_scope_kind, source_course_id,
                 reply_to_message_id, retrieval_limit)
            VALUES (?, 'durable-new', ?, ?, ?, '', 'now', 'now',
                    'all_indexed', NULL, ?, ?)
        """
        with pytest.raises(sqlite3.IntegrityError, match="assistant message requires"):
            connection.execute(
                base_columns,
                ("assistant-without-reply", 0, "assistant", "pending", None, 8),
            )
        with pytest.raises(sqlite3.IntegrityError, match="user message cannot"):
            connection.execute(
                base_columns,
                ("user-with-retrieval", 0, "user", "completed", None, 8),
            )
        with pytest.raises(sqlite3.IntegrityError, match="non-turn message cannot"):
            connection.execute(
                base_columns,
                ("tool-with-retrieval", 0, "tool", "completed", None, 8),
            )
        turn = repo.create_turn(
            conversation_id="durable-new",
            user_message_id="durable-user",
            assistant_message_id="durable-assistant",
            question="Why?",
            source_scope_kind="all_indexed",
            source_course_id=None,
            retrieval_limit=8,
            idempotency_key="durable-trigger-turn",
        )
        assert turn["replayed"] is False
        with pytest.raises(sqlite3.IntegrityError, match="assistant message requires"):
            connection.execute(
                "UPDATE messages SET retrieval_limit = NULL WHERE id = 'durable-assistant'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="user message cannot"):
            connection.execute(
                "UPDATE messages SET retrieval_limit = 8 WHERE id = 'durable-user'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="non-turn message cannot"):
            connection.execute(
                "UPDATE messages SET role = 'tool' WHERE id = 'durable-assistant'"
            )
    database.verify_consistency()
