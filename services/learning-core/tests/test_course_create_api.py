from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from fastapi.testclient import TestClient

from app.database import Database
from app.main import _repository, create_app
from app.repository import (
    CourseIdempotencyConflictError,
    CourseTitleConflictError,
    LearningRepository,
)
from app.settings import Settings
from conftest import TOKEN

AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _payload(
    *,
    title: str = "Linear Algebra",
    description: str = "Vectors and matrices.",
    key: str = "course-create-key",
) -> dict[str, str]:
    return {"title": title, "description": description, "idempotencyKey": key}


def test_course_create_empty_database_replays_the_same_canonical_request(
    tmp_path: Path,
) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "empty-courses.sqlite3",
        seed_demo=False,
    )
    with TestClient(create_app(settings)) as client:
        first = client.post("/v1/courses", headers=AUTH, json=_payload())
        assert first.status_code == 201
        assert first.json()["replayed"] is False
        created = first.json()["course"]
        assert created["id"].startswith("course-")
        assert created["title"] == "Linear Algebra"
        assert created["description"] == "Vectors and matrices."
        assert created["created_at"].endswith(("+00:00", "Z"))

        replay = client.post(
            "/v1/courses",
            headers=AUTH,
            json=_payload(title="  linear\u3000algebra ", key="course-create-key"),
        )
        assert replay.status_code == 200
        assert replay.json() == {"course": created, "replayed": True}
        assert len(client.get("/v1/courses", headers=AUTH).json()) == 1


def test_course_create_rejects_current_normalized_title_and_key_conflicts_without_sqlite_details(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    created = client.post("/v1/courses", headers=auth_headers, json=_payload())
    assert created.status_code == 201

    duplicate = client.post(
        "/v1/courses",
        headers=auth_headers,
        json=_payload(title="LINEAR\tALGEBRA", key="course-other-key-123"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "course_title_conflict"
    assert "sqlite" not in duplicate.text.lower()
    assert "constraint" not in duplicate.text.lower()

    key_conflict = client.post(
        "/v1/courses",
        headers=auth_headers,
        json=_payload(title="Different course", key="course-create-key"),
    )
    assert key_conflict.status_code == 409
    assert key_conflict.json()["detail"]["code"] == "idempotency_key_conflict"
    assert "sqlite" not in key_conflict.text.lower()
    assert "constraint" not in key_conflict.text.lower()


def test_course_create_scans_legacy_titles_without_rewriting_duplicate_legacy_rows(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "legacy-courses.sqlite3")
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
        for version in range(1, 21):
            migration = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.executemany(
            "INSERT INTO courses (id, title, description, created_at) VALUES (?, ?, '', ?)",
            [
                ("legacy-one", "Ａlgebra\u3000I", "2026-07-01T00:00:00+00:00"),
                ("legacy-two", "Algebra I", "2026-07-02T00:00:00+00:00"),
            ],
        )
        connection.commit()

    assert database.migrate() == [21, 22, 23, 24, 25, 26]
    with database.connection() as connection:
        study_session_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(study_sessions)")
        }
        assert "originating_task_id" in study_session_columns
        legacy = connection.execute(
            "SELECT id, normalized_title FROM courses ORDER BY id"
        ).fetchall()
        assert [(row["id"], row["normalized_title"]) for row in legacy] == [
            ("legacy-one", None),
            ("legacy-two", None),
        ]
        repository = LearningRepository(connection)
        try:
            repository.create_course(
                course_id="course-new",
                title=" algebra i ",
                description="New data must not shadow legacy data.",
                idempotency_key="legacy-conflict-key",
                created_at="2026-07-03T00:00:00+00:00",
            )
        except CourseTitleConflictError:
            pass
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("legacy normalized title was not checked")
        rows = connection.execute("SELECT id FROM courses ORDER BY id").fetchall()
        assert [row["id"] for row in rows] == ["legacy-one", "legacy-two"]


def test_course_create_is_atomic_for_concurrent_same_key_and_title_conflicts(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "concurrent-courses.sqlite3")
    database.migrate()
    start = Barrier(2)

    def create(*, course_id: str, key: str, title: str) -> tuple[dict, bool]:
        start.wait()
        with database.connection() as connection:
            return LearningRepository(connection).create_course(
                course_id=course_id,
                title=title,
                description="Concurrent request.",
                idempotency_key=key,
                created_at="2026-07-03T00:00:00+00:00",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        same_key = list(
            executor.map(
                lambda args: create(
                    course_id=args[0], key="course-same-key-123", title=args[1]
                ),
                (("course-a", "Probability"), ("course-b", " probability ")),
            )
        )
    assert sorted(replayed for _, replayed in same_key) == [False, True]
    assert same_key[0][0] == same_key[1][0]

    start = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                create,
                course_id="course-c",
                key="course-different-key-a",
                title="Statistics",
            ),
            executor.submit(
                create,
                course_id="course-d",
                key="course-different-key-b",
                title=" statistics ",
            ),
        ]
        results = []
        errors = []
        for future in futures:
            try:
                results.append(future.result())
            except CourseTitleConflictError as error:
                errors.append(error)
    assert len(results) == 1
    assert len(errors) == 1

    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM course_create_idempotency"
            ).fetchone()[0]
            == 2
        )


def test_course_create_validation_authentication_and_64_kib_guard(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    unauthorized = client.post("/v1/courses", json=_payload())
    assert unauthorized.status_code == 401

    for invalid in (
        {**_payload(), "title": " \u3000\t "},
        {**_payload(), "title": 3},
        {**_payload(), "title": "ﬃ" * 240},
        {**_payload(), "idempotencyKey": "short"},
        {**_payload(), "idempotencyKey": "contains spaces 123"},
        {**_payload(), "unexpected": True},
    ):
        assert (
            client.post("/v1/courses", headers=auth_headers, json=invalid).status_code
            == 422
        )

    oversized = client.post(
        "/v1/courses",
        content=b"x" * (64 * 1024 + 1),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert (
        oversized.json()["detail"]["message"]
        == "JSON request exceeds the configured size limit"
    )


def test_course_create_repository_rejects_different_replay_payload(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "repository-conflict.sqlite3")
    database.migrate()
    with database.connection() as connection:
        repository = LearningRepository(connection)
        repository.create_course(
            course_id="course-first",
            title="Geometry",
            description="First payload.",
            idempotency_key="course-repository-key",
            created_at="2026-07-03T00:00:00+00:00",
        )
        try:
            repository.create_course(
                course_id="course-second",
                title="Geometry",
                description="Changed description.",
                idempotency_key="course-repository-key",
                created_at="2026-07-03T00:00:01+00:00",
            )
        except CourseIdempotencyConflictError:
            pass
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("idempotency mismatch was accepted")
        assert connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM course_create_idempotency"
            ).fetchone()[0]
            == 1
        )


def test_course_create_defaults_an_omitted_description(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/v1/courses",
        headers=auth_headers,
        json={
            "title": "Course without description",
            "idempotencyKey": "course-no-description-key",
        },
    )

    assert response.status_code == 201
    assert response.json()["course"]["description"] == ""


def test_course_create_sanitizes_a_real_sqlite_failure_and_keeps_request_id(
    client: TestClient,
    auth_headers: dict[str, str],
    caplog,
) -> None:
    private_detail = "private SQL detail at /Users/example/learning.sqlite3"
    with client.app.state.database.connection() as connection:
        connection.execute(
            f"""
            CREATE TRIGGER fail_course_create
            BEFORE INSERT ON courses
            BEGIN
                SELECT RAISE(ABORT, '{private_detail}');
            END
            """
        )

    response = client.post(
        "/v1/courses",
        headers={**auth_headers, "X-Request-ID": "course-sqlite-failure"},
        json=_payload(),
    )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "course-sqlite-failure"
    assert response.json() == {
        "detail": {
            "code": "course_create_failed",
            "message": "Keen could not safely determine whether the course creation was saved.",
            "retryable": False,
            "recovery": (
                "Refresh the course list. Confirm the local learning service and "
                "storage have recovered before retrying with the same creation key."
            ),
            "automaticRecovery": False,
            "outcomeMayBeDurable": True,
        }
    }
    assert private_detail not in response.text
    assert private_detail not in caplog.text


def test_course_create_reports_a_real_sqlite_write_lock_as_retryable(
    tmp_path: Path,
) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "locked-courses.sqlite3",
        seed_demo=False,
    )
    app = create_app(settings)

    def short_timeout_repository():
        with app.state.database.connection() as connection:
            connection.execute("PRAGMA busy_timeout = 50")
            yield LearningRepository(connection)

    app.dependency_overrides[_repository] = short_timeout_repository
    with TestClient(app) as client:
        lock = sqlite3.connect(settings.database_path)
        try:
            lock.execute("BEGIN IMMEDIATE")
            response = client.post("/v1/courses", headers=AUTH, json=_payload())
        finally:
            lock.rollback()
            lock.close()

        assert response.status_code == 503
        assert response.headers["X-Request-ID"]
        assert response.json() == {
            "detail": {
                "code": "course_create_temporarily_unavailable",
                "message": (
                    "Keen could not access the local learning database to create the course. "
                    "The result may have been saved."
                ),
                "retryable": True,
                "recovery": "Refresh the course list, then retry with the same creation key.",
                "automaticRecovery": False,
                "outcomeMayBeDurable": True,
            }
        }
        assert client.get("/v1/courses", headers=AUTH).json() == []
