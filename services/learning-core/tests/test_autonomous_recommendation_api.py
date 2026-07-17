from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from conftest import TOKEN
from app.schemas import LearningActionCandidateResponse
from app.repositories.task_repository import TaskRepository
from app.request_guard import SMALL_JSON_REQUEST_BYTES
from app.services.learning_snapshot import LearningSnapshotService


AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 7, 17, 9, 0, tzinfo=UTC).isoformat()


def _insert_course(client: TestClient, course_id: str) -> None:
    with client.app.state.database.connection() as connection:
        connection.execute(
            "INSERT INTO courses (id, title, description, created_at) VALUES (?, ?, '', ?)",
            (course_id, f"Course {course_id}", NOW),
        )
        connection.commit()


def _insert_weak_concept(client: TestClient, *, course_id: str) -> None:
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name, bkt_slip, bkt_guess, bkt_transit)
            VALUES ('concept-api', ?, 'API limits', 0.1, 0.2, 0.1)
            """,
            (course_id,),
        )
        connection.execute(
            """
            INSERT INTO mastery (concept_id, probability, attempts, updated_at)
            VALUES ('concept-api', 0.2, 0, ?)
            """,
            (NOW,),
        )
        connection.commit()


def test_recommendation_api_creates_replays_and_exposes_real_feed(
    client: TestClient,
) -> None:
    _insert_course(client, "course-api")
    _insert_weak_concept(client, course_id="course-api")
    payload = {"course_id": "course-api", "available_minutes": 10}

    created = client.post("/v1/autonomous-recommendations", headers=AUTH, json=payload)
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["outcome"] == "task_created"
    assert created_body["task"]["course_id"] == "course-api"
    assert created_body["task"]["source_type"] == "weak_concept"
    assert created_body["candidate"]["action"] == "study_very_weak_concept"
    assert created_body["candidate"]["priority_components"]
    assert created_body["snapshot"]["available_minutes"] == 10
    assert [task["id"] for task in created_body["snapshot"]["pending_tasks"]] == [
        created_body["task"]["id"]
    ]

    replay = client.post("/v1/autonomous-recommendations", headers=AUTH, json=payload)
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "replay"
    assert replay.json()["task"]["id"] == created_body["task"]["id"]
    assert [task["id"] for task in replay.json()["snapshot"]["pending_tasks"]] == [
        created_body["task"]["id"]
    ]

    feed = client.get(
        "/v1/learning-snapshot?course_id=course-api&available_minutes=10", headers=AUTH
    )
    assert feed.status_code == 200
    assert [task["id"] for task in feed.json()["pending_tasks"]] == [
        created_body["task"]["id"]
    ]
    assert feed.json()["as_of"].endswith(("+00:00", "Z"))


def test_recommendation_api_returns_empty_for_a_real_course_without_actions(
    client: TestClient,
) -> None:
    _insert_course(client, "course-api-empty")
    response = client.post(
        "/v1/autonomous-recommendations",
        headers=AUTH,
        json={"course_id": "course-api-empty", "available_minutes": 25},
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "empty"
    assert response.json()["task"] is None
    assert response.json()["candidate"] is None
    assert response.json()["snapshot"]["pending_tasks"] == []


def test_same_day_completed_recommendation_replays_without_becoming_pending(
    client: TestClient,
) -> None:
    _insert_course(client, "course-api-completed-replay")
    _insert_weak_concept(client, course_id="course-api-completed-replay")
    payload = {
        "course_id": "course-api-completed-replay",
        "available_minutes": 20,
    }
    created = client.post("/v1/autonomous-recommendations", headers=AUTH, json=payload)
    assert created.status_code == 201
    task_id = created.json()["task"]["id"]

    with client.app.state.database.connection() as connection:
        repository = TaskRepository(connection)
        task = repository.get(task_id)
        assert task is not None
        repository.complete(task_id, expected_revision=int(task["revision"]))
        connection.execute(
            """
            UPDATE study_tasks
            SET due_at = '2026-07-17',
                scheduled_for = '2026-07-17',
                created_at = '2026-07-17T08:00:00',
                updated_at = '2026-07-17T09:00:00'
            WHERE id = ?
            """,
            (task_id,),
        )
        connection.commit()

    replay = client.post("/v1/autonomous-recommendations", headers=AUTH, json=payload)
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "replay"
    assert replay.json()["task"]["id"] == task_id
    assert replay.json()["task"]["status"] == "completed"
    assert replay.json()["snapshot"]["pending_tasks"] == []
    for field in ("due_at", "scheduled_for", "created_at", "updated_at"):
        assert replay.json()["task"][field].endswith(("Z", "+00:00"))

    with client.app.state.database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM study_tasks WHERE course_id = ?",
                ("course-api-completed-replay",),
            ).fetchone()[0]
            == 1
        )


def test_recommendation_api_rejects_cross_course_document_without_internal_details(
    client: TestClient,
) -> None:
    _insert_course(client, "course-api-target")
    _insert_course(client, "course-api-source")
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            INSERT INTO documents
                (id, course_id, name, mime_type, extension, status, page_count,
                 chunk_count, error, created_at, updated_at)
            VALUES ('document-api-source', 'course-api-source', 'Source.md',
                    'text/markdown', '.md', 'indexed', 1, 0, NULL, ?, ?)
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO course_documents (course_id, document_id, added_at)
            VALUES ('course-api-source', 'document-api-source', ?)
            """,
            (NOW,),
        )
        connection.commit()

    response = client.post(
        "/v1/autonomous-recommendations",
        headers=AUTH,
        json={
            "course_id": "course-api-target",
            "document_id": "document-api-source",
            "available_minutes": 25,
        },
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "document_not_available_for_course"
    assert detail["automaticRecovery"] is False
    assert "sqlite" not in response.text.lower()
    assert "constraint" not in response.text.lower()
    assert "document-api-source" not in response.text


def test_recommendation_api_validates_boundaries_and_maps_missing_course(
    client: TestClient,
) -> None:
    for payload in (
        {"course_id": "course-api", "available_minutes": 0},
        {"course_id": "course-api", "available_minutes": 1_441},
        {"course_id": "course-api", "available_minutes": True},
        {"course_id": "course api", "available_minutes": 25},
        {"course_id": "course-api", "available_minutes": 25, "unexpected": True},
    ):
        assert (
            client.post(
                "/v1/autonomous-recommendations", headers=AUTH, json=payload
            ).status_code
            == 422
        )

    for missing in (
        client.get("/v1/learning-snapshot?course_id=course-missing", headers=AUTH),
        client.post(
            "/v1/autonomous-recommendations",
            headers=AUTH,
            json={"course_id": "course-missing", "available_minutes": 20},
        ),
    ):
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "course_not_found"
        assert "sqlite" not in missing.text.lower()


def test_learning_priority_response_rejects_non_finite_values_but_keeps_negative_unclamped_score() -> (
    None
):
    candidate = {
        "id": "concept:concept-api",
        "action": "study_very_weak_concept",
        "target_type": "concept",
        "target_id": "concept-api",
        "component": "mastery",
        "priority_tier": 3,
        "estimated_minutes": 15,
        "fits_available_minutes": True,
        "priority_score": 0.8,
        "priority_unclamped_score": -0.4,
        "priority_algorithm_version": "feed-priority/1.0.0",
        "priority_components": [
            {"name": "mastery", "raw_value": 0.2, "weight": 1.0, "contribution": 0.8}
        ],
        "priority_explanation": ["Weak mastery is prioritized."],
        "why": "Mastery is below the weak threshold.",
    }
    assert (
        LearningActionCandidateResponse.model_validate(
            candidate
        ).priority_unclamped_score
        == -0.4
    )

    for field, value in (
        ("priority_score", float("nan")),
        ("priority_unclamped_score", float("inf")),
        ("raw_value", float("nan")),
        ("weight", float("inf")),
        ("contribution", float("nan")),
    ):
        invalid = deepcopy(candidate)
        if field in {"raw_value", "weight", "contribution"}:
            invalid["priority_components"][0][field] = value
        else:
            invalid[field] = value
        with pytest.raises(ValidationError):
            LearningActionCandidateResponse.model_validate(invalid)


def test_manual_high_priority_task_is_read_and_covers_a_recommendation(
    client: TestClient,
) -> None:
    _insert_course(client, "course-api-high-priority")
    _insert_weak_concept(client, course_id="course-api-high-priority")
    with client.app.state.database.connection() as connection:
        task, created = TaskRepository(connection).create_task(
            task_id="task-api-high-priority",
            course_id="course-api-high-priority",
            concept_id="concept-api",
            title="Legacy high priority",
            reason="Imported from an earlier local plan.",
            due_at=NOW,
            estimated_minutes=15,
            source_type="manual",
            source_id=None,
            priority_score=9,
            priority_components={},
            recommended_reason="",
            idempotency_key="task-api-high-priority-key",
            created_at=NOW,
        )
        connection.execute(
            """
            UPDATE study_tasks
            SET due_at = '2026-07-17',
                scheduled_for = '2026-07-17',
                created_at = '2026-07-16T09:00:00',
                updated_at = '2026-07-17T09:00:00'
            WHERE id = ?
            """,
            (task["id"],),
        )
        connection.commit()
    assert created is True
    assert task["priority_score"] == 9

    feed = client.get(
        "/v1/learning-snapshot?course_id=course-api-high-priority&available_minutes=20",
        headers=AUTH,
    )
    assert feed.status_code == 200
    assert feed.json()["pending_tasks"][0]["priority_score"] == 9
    for field in ("due_at", "scheduled_for", "created_at", "updated_at"):
        assert feed.json()["pending_tasks"][0][field].endswith(("Z", "+00:00"))

    covered = client.post(
        "/v1/autonomous-recommendations",
        headers=AUTH,
        json={"course_id": "course-api-high-priority", "available_minutes": 20},
    )
    assert covered.status_code == 200
    assert covered.json()["outcome"] == "covered_by_active_task"
    assert covered.json()["task"]["priority_score"] == 9
    assert covered.json()["snapshot"]["pending_tasks"][0]["priority_score"] == 9
    for field in ("due_at", "scheduled_for", "created_at", "updated_at"):
        assert covered.json()["task"][field].endswith(("Z", "+00:00"))
        assert covered.json()["snapshot"]["pending_tasks"][0][field].endswith(
            ("Z", "+00:00")
        )


def test_task_repository_rejects_negative_and_non_finite_new_priority_scores(
    client: TestClient,
) -> None:
    for priority_score in (-1, float("nan"), float("inf")):
        with client.app.state.database.connection() as connection:
            with pytest.raises(
                ValueError, match="priority score must be finite and non-negative"
            ):
                TaskRepository(connection).create_task(
                    task_id="task-invalid-priority",
                    course_id="course-calculus",
                    title="Invalid priority",
                    reason="Must not persist.",
                    due_at=NOW,
                    estimated_minutes=15,
                    source_type="manual",
                    source_id=None,
                    priority_score=priority_score,
                    priority_components={},
                    recommended_reason="",
                    idempotency_key="task-invalid-priority-key",
                    created_at=NOW,
                )


def test_autonomous_recommendation_body_limit_and_auth_order(
    client: TestClient,
) -> None:
    oversized = b"x" * (SMALL_JSON_REQUEST_BYTES + 1)
    headers = {**AUTH, "Content-Type": "application/json"}
    declared = client.post(
        "/v1/autonomous-recommendations", headers=headers, content=oversized
    )
    assert declared.status_code == 413
    assert (
        declared.json()["detail"]["message"]
        == "JSON request exceeds the configured size limit"
    )

    unauthorized = client.post(
        "/v1/autonomous-recommendations",
        headers={"Content-Type": "application/json"},
        content=oversized,
    )
    assert unauthorized.status_code == 401


def test_snapshot_read_failure_does_not_claim_a_write_may_be_durable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_read(*_args, **_kwargs):
        raise sqlite3.OperationalError("synthetic private database detail")

    monkeypatch.setattr(LearningSnapshotService, "build", fail_read)
    response = client.get(
        "/v1/learning-snapshot?course_id=course-calculus&available_minutes=20",
        headers=AUTH,
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["message"] == "Keen could not safely read the local learning feed."
    assert detail["recoveryAction"] == "Refresh the learning feed and retry."
    assert "outcomeMayBeDurable" not in detail
    assert "database" not in response.text.lower()


def test_invalid_legacy_task_timestamp_fails_with_a_redacted_read_error(
    client: TestClient,
) -> None:
    _insert_course(client, "course-api-invalid-time")
    _insert_weak_concept(client, course_id="course-api-invalid-time")
    with client.app.state.database.connection() as connection:
        task, _ = TaskRepository(connection).create_task(
            task_id="task-api-invalid-time",
            course_id="course-api-invalid-time",
            concept_id="concept-api",
            title="Invalid legacy time",
            reason="Fixture for fail-closed serialization.",
            due_at=NOW,
            estimated_minutes=15,
            source_type="manual",
            source_id=None,
            priority_score=1,
            priority_components={},
            recommended_reason="",
            idempotency_key="task-api-invalid-time-key",
            created_at=NOW,
        )
        connection.execute(
            "UPDATE study_tasks SET due_at = 'not-an-iso-time' WHERE id = ?",
            (task["id"],),
        )
        connection.commit()

    response = client.get(
        "/v1/learning-snapshot?course_id=course-api-invalid-time&available_minutes=20",
        headers=AUTH,
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "learning_feed_temporarily_unavailable"
    assert "not-an-iso-time" not in response.text
    assert "timestamp" not in response.text.lower()
