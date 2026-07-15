from __future__ import annotations

from app.database import Database


def test_migrations_and_seed_are_idempotent(tmp_path):
    database = Database(tmp_path / "migration.sqlite3")

    assert database.migrate() == [1]
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

    assert migration_count == 1
    assert course_count == 2
    assert concept_count == 3
    assert task_count == 2
