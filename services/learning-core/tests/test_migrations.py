from __future__ import annotations

import stat
from pathlib import Path

import pytest

from app.database import Database


def test_database_file_is_private_and_symlinks_are_rejected(tmp_path):
    database_path = tmp_path / "private.sqlite3"
    database_path.touch(mode=0o644)
    database = Database(database_path)

    with database.connection():
        pass

    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600

    outside = tmp_path / "outside.sqlite3"
    outside.touch()
    linked = tmp_path / "linked.sqlite3"
    linked.symlink_to(outside)
    with pytest.raises(RuntimeError, match="regular file"):
        Database(linked).connect()

    hard_linked = tmp_path / "hard-linked.sqlite3"
    hard_linked.hardlink_to(database_path)
    with pytest.raises(RuntimeError, match="regular file"):
        Database(hard_linked).connect()


def test_migrations_and_seed_are_idempotent(tmp_path):
    database = Database(tmp_path / "migration.sqlite3")

    assert database.migrate() == [1, 2]
    assert database.migrate() == []
    database.seed_demo()
    database.seed_demo()

    with database.connection() as connection:
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        course_count = connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        concept_count = connection.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
        task_count = connection.execute("SELECT COUNT(*) FROM study_tasks").fetchone()[0]

    assert migration_count == 2
    assert course_count == 2
    assert concept_count == 3
    assert task_count == 2


def test_document_migration_creates_fts_and_status_schema(tmp_path):
    database = Database(tmp_path / "documents-migration.sqlite3")
    database.migrate()

    with database.connection() as connection:
        objects = {
            (row["type"], row["name"])
            for row in connection.execute(
                """
                SELECT type, name FROM sqlite_master
                WHERE name IN (
                    'documents', 'document_versions', 'document_chunks',
                    'document_status_events', 'document_chunks_fts',
                    'document_chunks_fts_insert', 'document_chunks_fts_delete',
                    'document_chunks_fts_update'
                )
                """
            )
        }

    assert ("table", "documents") in objects
    assert ("table", "document_versions") in objects
    assert ("table", "document_chunks") in objects
    assert ("table", "document_status_events") in objects
    assert ("table", "document_chunks_fts") in objects
    assert ("trigger", "document_chunks_fts_insert") in objects
    assert ("trigger", "document_chunks_fts_delete") in objects
    assert ("trigger", "document_chunks_fts_update") in objects


def test_document_migration_upgrades_an_existing_001_database_without_data_loss(tmp_path):
    database = Database(tmp_path / "upgrade.sqlite3")
    initial_sql = (
        Path(__file__).resolve().parent.parent / "migrations" / "001_initial.sql"
    ).read_text(encoding="utf-8")
    with database.connection() as connection:
        connection.executescript(initial_sql)
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("INSERT INTO schema_migrations(version) VALUES (1)")
        connection.execute(
            """
            INSERT INTO courses(id, title, description, created_at)
            VALUES ('kept-course', 'Keep me', '', '2026-07-15T00:00:00+00:00')
            """
        )
        connection.commit()

    assert database.migrate() == [2]
    with database.connection() as connection:
        course = connection.execute(
            "SELECT title FROM courses WHERE id = 'kept-course'"
        ).fetchone()
        migration_versions = [
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        document_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
        ).fetchone()

    assert course["title"] == "Keep me"
    assert migration_versions == [1, 2]
    assert document_table["name"] == "documents"
