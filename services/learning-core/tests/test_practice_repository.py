from __future__ import annotations

from pathlib import Path

import pytest

from app.database import Database
from app.repositories.practice_repository import PracticeRepository


def test_025_upgrades_a_real_024_database_without_reapplying_history(tmp_path):
    """025 is forward-only: a deployed 024 database gains only the practice ledger."""

    database = Database(tmp_path / "from-024.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for version in range(1, 25):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (version,),
            )
        connection.commit()

    assert database.migrate() == [25, 26, 27, 28, 29, 30, 31, 32]
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'study_practice_runs'"
            ).fetchone()
            is not None
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_create_requires_a_caller_owned_transaction_when_commit_is_false(tmp_path):
    database = Database(tmp_path / "practice-repository.sqlite3")
    database.migrate()
    connection = database.connect()
    try:
        repository = PracticeRepository(connection)
        with pytest.raises(RuntimeError, match="caller-owned transaction"):
            repository.create_run(
                run_id="practice-run",
                course_id="course",
                session_id="session",
                unit_id="unit",
                predecessor_active_recall_run_id="active-recall-run",
                checkpoint_id="checkpoint",
                assessment_id="assessment",
                item_id="item",
                concept_id="concept",
                mastery_attempts_before=0,
                source_chunk_ids=["chunk"],
                source_content_fingerprint="c" * 64,
                accepted_answers_fingerprint="a" * 64,
                generator_version="targeted-practice/1",
                idempotency_key="practice-begin-key-0001",
                payload_fingerprint="b" * 64,
                commit=False,
            )
    finally:
        connection.close()
