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

    applied = database.migrate()
    assert {1, 2, 4}.issubset(applied)
    assert database.migrate() == []
    database.seed_demo()
    database.seed_demo()

    with database.connection() as connection:
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        course_count = connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        concept_count = connection.execute("SELECT COUNT(*) FROM concepts").fetchone()[
            0
        ]
        task_count = connection.execute("SELECT COUNT(*) FROM study_tasks").fetchone()[
            0
        ]

    assert migration_count == len(applied)
    assert course_count == 2
    assert concept_count == 3
    assert task_count == 2


def test_migrated_database_passes_consistency_check(tmp_path):
    database = Database(tmp_path / "consistent.sqlite3")
    database.migrate()

    database.verify_consistency()


def test_embedding_migration_is_forward_only_without_fabricating_legacy_vectors(
    tmp_path,
):
    database = Database(tmp_path / "embedding-forward.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 6):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute(
            """
            INSERT INTO documents (
                id, course_id, name, mime_type, extension, status,
                page_count, chunk_count, error, created_at, updated_at
            ) VALUES ('legacy-vector-doc', NULL, 'legacy.txt', 'text/plain',
                      '.txt', 'indexed', 0, 0, NULL,
                      '2026-07-16T00:00:00+00:00',
                      '2026-07-16T00:00:00+00:00')
            """
        )
        connection.commit()

    applied = database.migrate()
    assert applied[:3] == [6, 7, 8]
    assert applied[3:] == list(range(9, 19))
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM documents WHERE id = 'legacy-vector-doc'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM document_embedding_state"
            ).fetchone()[0]
            == 0
        )


def test_embedding_migration_rolls_back_partial_schema_on_failure(tmp_path):
    database = Database(tmp_path / "embedding-rollback.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 6):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute("CREATE TABLE chunk_embeddings (fixture TEXT)")
        connection.commit()

    with pytest.raises(Exception, match="already exists"):
        database.migrate()
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = 6"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'embedding_models'"
            ).fetchone()[0]
            == 0
        )


def test_migration_007_forward_repairs_early_006_model_immutability(tmp_path):
    database = Database(tmp_path / "embedding-forward-repair.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 7):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute("DROP TRIGGER embedding_models_identity_immutable")
        connection.commit()

    applied = database.migrate()
    assert applied[:2] == [7, 8]
    assert applied[2:] == list(range(9, 19))
    with database.connection() as connection:
        trigger = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'trigger' AND name = 'embedding_models_identity_immutable'
            """
        ).fetchone()
    assert trigger["name"] == "embedding_models_identity_immutable"


def test_learning_loop_migrations_preserve_existing_008_learning_state(tmp_path):
    database = Database(tmp_path / "learning-loop-forward.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 9):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute(
            """
            INSERT INTO courses (id, title, description, created_at)
            VALUES ('kept-course', 'Kept course', '', '2026-07-01T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name)
            VALUES ('kept-concept', 'kept-course', 'Kept concept')
            """
        )
        connection.execute(
            """
            INSERT INTO mastery (concept_id, probability, attempts, updated_at)
            VALUES ('kept-concept', 0.4, 1, '2026-07-02T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO mastery_events (
                concept_id, correct, probability_before,
                probability_after, observed_at
            ) VALUES (
                'kept-concept', 1, 0.2, 0.4, '2026-07-02T00:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO study_tasks (
                id, course_id, concept_id, title, reason, due_at,
                estimated_minutes, status, created_at, updated_at
            ) VALUES (
                'kept-task', 'kept-course', 'kept-concept', 'Kept task',
                'Legacy reason', '2026-07-20T00:00:00+00:00', 20, 'upcoming',
                '2026-07-02T00:00:00+00:00', '2026-07-02T00:00:00+00:00'
            )
            """
        )
        connection.commit()

    assert database.migrate() == list(range(9, 19))
    database.verify_consistency()
    with database.connection() as connection:
        mastery = connection.execute(
            "SELECT * FROM mastery WHERE concept_id = 'kept-concept'"
        ).fetchone()
        event = connection.execute(
            "SELECT * FROM mastery_events WHERE concept_id = 'kept-concept'"
        ).fetchone()
        task = connection.execute(
            "SELECT * FROM study_tasks WHERE id = 'kept-task'"
        ).fetchone()

    assert dict(mastery) == {
        "concept_id": "kept-concept",
        "probability": 0.4,
        "attempts": 1,
        "updated_at": "2026-07-02T00:00:00+00:00",
    }
    assert event["algorithm"] == "legacy_bkt"
    assert event["algorithm_version"] == "1"
    assert event["evidence_ids_json"] == "[]"
    assert task["title"] == "Kept task"
    assert task["source_type"] == "manual"
    assert task["priority_components_json"] == "{}"
    assert task["completed_at"] is None


def test_document_index_job_migration_applies_004(tmp_path):
    database = Database(tmp_path / "jobs.sqlite3")
    assert 4 in database.migrate()

    with database.connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        versions = [
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]

    assert "document_index_jobs" in tables
    assert {1, 2, 4}.issubset(versions)


def test_course_document_migration_backfills_legacy_course_id(tmp_path):
    database = Database(tmp_path / "course-links-backfill.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.executescript(
            (migrations / "001_initial.sql").read_text(encoding="utf-8")
        )
        connection.executescript(
            (migrations / "002_documents.sql").read_text(encoding="utf-8")
        )
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executemany(
            "INSERT INTO schema_migrations(version) VALUES (?)", [(1,), (2,)]
        )
        connection.execute(
            """
            INSERT INTO courses (id, title, description, created_at)
            VALUES ('legacy-course', 'Legacy', '', '2026-07-14T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, course_id, name, mime_type, extension, status,
                page_count, chunk_count, error, created_at, updated_at
            ) VALUES (
                'legacy-linked-document', 'legacy-course', 'legacy.txt',
                'text/plain', '.txt', 'failed', 0, 0, 'legacy fixture',
                '2026-07-15T00:00:00+00:00', '2026-07-15T00:01:00+00:00'
            )
            """
        )
        connection.commit()

    assert 3 in database.migrate()
    with database.connection() as connection:
        link = connection.execute(
            """
            SELECT course_id, document_id, added_at FROM course_documents
            WHERE document_id = 'legacy-linked-document'
            """
        ).fetchone()
        legacy_course_id = connection.execute(
            "SELECT course_id FROM documents WHERE id = 'legacy-linked-document'"
        ).fetchone()["course_id"]

    assert dict(link) == {
        "course_id": "legacy-course",
        "document_id": "legacy-linked-document",
        "added_at": "2026-07-15T00:00:00+00:00",
    }
    assert legacy_course_id == "legacy-course"


def test_document_index_job_migration_backfills_indexed_document_as_completed(
    tmp_path,
):
    database = Database(tmp_path / "jobs-backfill.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.executescript(
            (migrations / "001_initial.sql").read_text(encoding="utf-8")
        )
        connection.executescript(
            (migrations / "002_documents.sql").read_text(encoding="utf-8")
        )
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executemany(
            "INSERT INTO schema_migrations(version) VALUES (?)", [(1,), (2,)]
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, course_id, name, mime_type, extension, status,
                page_count, chunk_count, error, created_at, updated_at
            ) VALUES (
                'indexed-before-jobs', NULL, 'kept.txt', 'text/plain', '.txt',
                'indexed', 1, 1, NULL, '2026-07-15T00:00:00+00:00',
                '2026-07-15T00:01:00+00:00'
            )
            """
        )
        connection.commit()

    assert 4 in database.migrate()
    with database.connection() as connection:
        job = connection.execute(
            "SELECT * FROM document_index_jobs WHERE document_id = ?",
            ("indexed-before-jobs",),
        ).fetchone()

    assert job["status"] == "completed"
    assert job["stage"] == "finalizing"
    assert job["progress"] == 100
    assert job["error"] is None
    assert job["finished_at"] == "2026-07-15T00:01:00+00:00"


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


def test_document_migration_upgrades_an_existing_001_database_without_data_loss(
    tmp_path,
):
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

    applied = database.migrate()
    assert {2, 4}.issubset(applied)
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
    assert {1, 2, 4}.issubset(migration_versions)
    assert document_table["name"] == "documents"


def test_018_forward_upgrade_preserves_existing_agent_audit_and_is_idempotent(
    tmp_path,
):
    database = Database(tmp_path / "agent-undo-018-forward.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 18):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute(
            """
            INSERT INTO agent_runs (
                id, conversation_id, study_session_id, kind, user_intent, mode,
                status, provider, model, prompt_version, input_json, error_code,
                error_detail, idempotency_key, created_at, updated_at,
                started_at, finished_at
            ) VALUES (
                'kept-run', NULL, NULL, 'conversation', 'Keep audit', 'study',
                'queued', 'local', 'fixture', 'v1', '{}', NULL, NULL,
                'kept-run-key', '2026-07-16T00:00:00+00:00',
                '2026-07-16T00:00:00+00:00', NULL, NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO tool_invocations (
                id, run_id, step_id, tool_name, permission_level, status,
                arguments_json, arguments_hash, result_summary_json, error_code,
                error_detail, idempotency_key, created_at, updated_at,
                started_at, finished_at
            ) VALUES (
                'kept-tool', 'kept-run', NULL, 'legacy_local_write', 2,
                'succeeded', '{}', ?, '{"status":"completed"}', NULL, NULL,
                'kept-tool-key', '2026-07-16T00:00:00+00:00',
                '2026-07-16T00:00:00+00:00',
                '2026-07-16T00:00:00+00:00',
                '2026-07-16T00:00:00+00:00'
            )
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO state_mutations (
                id, run_id, tool_invocation_id, ordinal, entity_type,
                entity_id, operation, before_json, after_json, undo_json,
                reversible, created_at
            ) VALUES (
                'kept-mutation', 'kept-run', 'kept-tool', 0, 'study_task',
                'kept-task', 'update', '{"status":"upcoming"}',
                '{"status":"completed"}',
                '{"operation":"update","entity_type":"study_task","entity_id":"kept-task","restore":{"status":"upcoming"}}',
                1, '2026-07-16T00:00:00+00:00'
            )
            """
        )
        connection.commit()

    assert database.migrate() == [18]
    assert database.migrate() == []
    database.verify_consistency()
    with database.connection() as connection:
        kept = connection.execute(
            """
            SELECT id, run_id, tool_invocation_id, entity_type, entity_id,
                   operation, before_json, after_json, undo_json, reversible,
                   undone_at, undone_by_tool_invocation_id
            FROM state_mutations WHERE id = 'kept-mutation'
            """
        ).fetchone()
        versions = [
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        trigger_count = connection.execute(
            """
            SELECT count(*) FROM sqlite_master
            WHERE type = 'trigger' AND name IN (
                'state_mutations_undo_tracking_insert',
                'state_mutations_undo_tracking_update',
                'state_mutations_tracked_inverse_insert',
                'state_mutations_tracked_audit_update',
                'state_mutations_tracked_audit_delete',
                'tool_invocations_tracked_undo_update',
                'tool_invocations_tracked_undo_delete'
            )
            """
        ).fetchone()[0]
    assert dict(kept) == {
        "id": "kept-mutation",
        "run_id": "kept-run",
        "tool_invocation_id": "kept-tool",
        "entity_type": "study_task",
        "entity_id": "kept-task",
        "operation": "update",
        "before_json": '{"status":"upcoming"}',
        "after_json": '{"status":"completed"}',
        "undo_json": '{"operation":"update","entity_type":"study_task","entity_id":"kept-task","restore":{"status":"upcoming"}}',
        "reversible": 1,
        "undone_at": None,
        "undone_by_tool_invocation_id": None,
    }
    assert versions == list(range(1, 19))
    assert trigger_count == 7
