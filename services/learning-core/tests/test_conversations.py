from __future__ import annotations

from pathlib import Path

import pytest

from app.database import Database
from app.repositories.conversation_repository import ConversationRepository


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
        )
    assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


def test_recovery_marks_only_unfinished_messages_interrupted(repository):
    repo, _ = repository
    repo.create_conversation(conversation_id="c", title="Recovery")
    repo.append_message(
        message_id="streaming",
        conversation_id="c",
        role="assistant",
        content="partial",
        status="streaming",
    )
    repo.append_message(
        message_id="done",
        conversation_id="c",
        role="user",
        content="question",
        status="completed",
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
