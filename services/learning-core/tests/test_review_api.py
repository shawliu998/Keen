from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.review_repository import ReviewRepository
from app.repositories.task_repository import TaskRepository
from app.review.scheduler import SCHEDULER_VERSION
from app.settings import Settings

RESTART_TOKEN = "abcdef0123456789abcdef0123456789"


def _create_due_review(
    client,
    *,
    item_id: str = "review-api-chain-rule",
    prompt: str = "Explain the chain rule.",
    idempotency_key: str = "review-api-chain-rule-create",
):
    with client.app.state.database.connection() as connection:
        item, _created = ReviewRepository(connection).create_item(
            item_id=item_id,
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            item_type="free_recall",
            prompt=prompt,
            expected_answer={
                "accepted_answers": [
                    "Differentiate the outer function, then multiply by the derivative of the inner function."
                ]
            },
            source_type="manual",
            source_id=None,
            due_at="2026-07-16T08:00:00+00:00",
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key=idempotency_key,
            created_at="2026-07-16T07:00:00+00:00",
        )
        return item


def _create_review_task(
    client,
    *,
    task_id: str,
    item: dict,
    source_type: str = "review",
    source_id: str | None = None,
):
    with client.app.state.database.connection() as connection:
        task, _created = TaskRepository(connection).create_task(
            task_id=task_id,
            course_id=item["course_id"],
            concept_id=item["concept_id"],
            title=f"Review {item['prompt']}",
            reason="A real review is due.",
            due_at=item["due_at"],
            estimated_minutes=5,
            source_type=source_type,
            source_id=item["id"] if source_id is None else source_id,
            priority_score=100.0,
            priority_components={
                "recommendation_algorithm_version": "autonomous-recommendation/1.0.0",
                "candidate_id": f"review:{item['id']}",
                "action": "review_due",
                "target_type": "review_item",
                "target_id": item["id"],
            },
            recommended_reason="Review is due.",
            idempotency_key=f"{task_id}-create",
            created_at="2026-07-16T07:30:00+00:00",
        )
        return task


def test_due_review_requires_authentication(client):
    response = client.get("/v1/reviews/due")

    assert response.status_code == 401


def test_due_review_list_and_rating_are_real_and_idempotent(client, auth_headers):
    item = _create_due_review(client)

    queue = client.get("/v1/reviews/due", headers=auth_headers)

    assert queue.status_code == 200
    body = queue.json()
    assert [review["id"] for review in body["items"]] == [item["id"]]
    assert body["items"][0]["course_title"] == "Calculus I"
    assert body["items"][0]["concept_name"] == "Chain rule"
    assert body["items"][0]["expected_answer"]["accepted_answers"][0].startswith(
        "Differentiate"
    )

    request = {
        "rating": "good",
        "response": "Outer derivative times the derivative of the inner function.",
        "expectedRevision": 0,
        "idempotencyKey": "review-api-rating-0001",
    }
    applied = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json=request,
    )
    replayed = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json=request,
    )

    assert applied.status_code == 201
    assert applied.json()["outcome"] == "applied"
    assert applied.json()["schedule"]["revision"] == 1
    assert replayed.status_code == 200
    assert replayed.json()["outcome"] == "replayed"
    assert replayed.json()["schedule"] == applied.json()["schedule"]

    with client.app.state.database.connection() as connection:
        attempt_count = connection.execute(
            "SELECT COUNT(*) FROM review_attempts"
        ).fetchone()[0]
        mastery = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = 'concept-chain-rule'"
        ).fetchone()

    assert attempt_count == 1
    assert dict(mastery) == {"probability": 0.42, "attempts": 2}


def test_rating_completes_only_the_exact_active_review_task_and_replays_once(
    client, auth_headers
):
    item = _create_due_review(client)
    matching = _create_review_task(client, task_id="review-task-matching", item=item)
    duplicate_matching = _create_review_task(
        client,
        task_id="review-task-duplicate-matching",
        item=item,
    )
    already_completed = _create_review_task(
        client,
        task_id="review-task-already-completed",
        item=item,
    )
    non_review = _create_review_task(
        client,
        task_id="review-task-non-review",
        item=item,
        source_type="manual",
    )
    with client.app.state.database.connection() as connection:
        other_item, _created = ReviewRepository(connection).create_item(
            item_id="review-api-other-item",
            course_id="course-calculus",
            concept_id="concept-chain-rule",
            item_type="free_recall",
            prompt="Explain another calculus rule.",
            expected_answer={"accepted_answers": ["Another answer"]},
            source_type="manual",
            source_id=None,
            due_at="2026-07-16T08:00:00+00:00",
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key="review-api-other-item-create",
            created_at="2026-07-16T07:00:00+00:00",
        )
    other_item_task = _create_review_task(
        client,
        task_id="review-task-other-item",
        item=other_item,
    )
    with client.app.state.database.connection() as connection:
        other_course_item, _created = ReviewRepository(connection).create_item(
            item_id="review-api-other-course",
            course_id="course-physics",
            concept_id="concept-newton-2",
            item_type="free_recall",
            prompt="Explain Newton's second law.",
            expected_answer={
                "accepted_answers": ["Force equals mass times acceleration."]
            },
            source_type="manual",
            source_id=None,
            due_at="2026-07-16T08:00:00+00:00",
            scheduler_version=SCHEDULER_VERSION,
            idempotency_key="review-api-other-course-create",
            created_at="2026-07-16T07:00:00+00:00",
        )
    other_course_task = _create_review_task(
        client,
        task_id="review-task-other-course",
        item=other_course_item,
    )
    with client.app.state.database.connection() as connection:
        TaskRepository(connection).complete(
            already_completed["id"],
            expected_revision=0,
            completed_at="2026-07-16T07:45:00+00:00",
        )

    request = {
        "rating": "good",
        "response": "Outer derivative times the derivative of the inner function.",
        "expectedRevision": 0,
        "taskContext": {
            "taskId": matching["id"],
            "courseId": item["course_id"],
        },
        "idempotencyKey": "review-api-task-rating-0001",
    }
    applied = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json=request,
    )
    replayed_after_unknown_outcome = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json=request,
    )

    assert applied.status_code == 201
    assert replayed_after_unknown_outcome.status_code == 200
    assert replayed_after_unknown_outcome.json()["outcome"] == "replayed"
    with client.app.state.database.connection() as connection:
        tasks = {
            row["id"]: dict(row)
            for row in connection.execute(
                """
                SELECT id, status, completed_at, revision
                FROM study_tasks
                WHERE id IN (?, ?, ?, ?, ?, ?)
                """,
                (
                    matching["id"],
                    duplicate_matching["id"],
                    already_completed["id"],
                    non_review["id"],
                    other_item_task["id"],
                    other_course_task["id"],
                ),
            ).fetchall()
        }
        attempt_count = connection.execute(
            "SELECT COUNT(*) FROM review_attempts WHERE review_item_id = ?",
            (item["id"],),
        ).fetchone()[0]

    assert tasks[matching["id"]]["status"] == "completed"
    assert tasks[matching["id"]]["revision"] == 1
    assert datetime.fromisoformat(
        tasks[matching["id"]]["completed_at"]
    ) == datetime.fromisoformat(applied.json()["reviewed_at"])
    assert tasks[already_completed["id"]]["status"] == "completed"
    assert tasks[already_completed["id"]]["revision"] == 1
    for untouched in (
        duplicate_matching,
        non_review,
        other_item_task,
        other_course_task,
    ):
        assert tasks[untouched["id"]]["status"] == "upcoming"
        assert tasks[untouched["id"]]["revision"] == 0
    assert attempt_count == 1

    forged_replay = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json={
            **request,
            "taskContext": {
                "taskId": duplicate_matching["id"],
                "courseId": item["course_id"],
            },
        },
    )
    assert forged_replay.status_code == 409
    assert forged_replay.json()["detail"] == {
        "code": "review_attempt_idempotency_conflict",
        "message": "This rating does not match the saved review submission.",
        "retryable": False,
        "recoveryAction": "Return to the Learning Feed and open the current task.",
        "automaticRecovery": False,
    }


def test_task_completion_failure_rolls_back_the_review_attempt_and_schedule(
    client, auth_headers
):
    item = _create_due_review(client)
    task = _create_review_task(client, task_id="review-task-rollback", item=item)
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            CREATE TRIGGER force_review_task_completion_failure
            BEFORE UPDATE OF status ON study_tasks
            WHEN old.id = 'review-task-rollback' AND new.status = 'completed'
            BEGIN
                SELECT RAISE(ABORT, 'forced review task completion failure');
            END
            """
        )
        connection.commit()

    response = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json={
            "rating": "good",
            "response": "Outer derivative times the derivative of the inner function.",
            "expectedRevision": 0,
            "taskContext": {
                "taskId": task["id"],
                "courseId": item["course_id"],
            },
            "idempotencyKey": "review-api-task-rollback-0001",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["outcomeMayBeDurable"] is True
    with client.app.state.database.connection() as connection:
        persisted_task = connection.execute(
            "SELECT status, completed_at, revision FROM study_tasks WHERE id = ?",
            (task["id"],),
        ).fetchone()
        schedule_revision = connection.execute(
            "SELECT revision FROM review_schedules WHERE review_item_id = ?",
            (item["id"],),
        ).fetchone()[0]
        attempt_count = connection.execute(
            "SELECT COUNT(*) FROM review_attempts WHERE review_item_id = ?",
            (item["id"],),
        ).fetchone()[0]

    assert dict(persisted_task) == {
        "status": "upcoming",
        "completed_at": None,
        "revision": 0,
    }
    assert schedule_revision == 0
    assert attempt_count == 0


def test_review_task_context_is_exact_and_rejects_wrong_or_inactive_tasks(
    client, auth_headers
):
    item = _create_due_review(client)
    matching = _create_review_task(client, task_id="review-task-exact", item=item)
    duplicate = _create_review_task(
        client, task_id="review-task-exact-duplicate", item=item
    )
    other_item = _create_due_review(
        client,
        item_id="review-api-context-other-item",
        prompt="Explain a different calculus rule.",
        idempotency_key="review-api-context-other-item-create",
    )
    other_item_task = _create_review_task(
        client,
        task_id="review-task-other-source",
        item=other_item,
    )
    non_review = _create_review_task(
        client,
        task_id="review-task-wrong-source-type",
        item=item,
        source_type="manual",
    )
    with client.app.state.database.connection() as connection:
        TaskRepository(connection).complete(
            matching["id"],
            expected_revision=0,
            completed_at="2026-07-16T07:45:00+00:00",
        )

    contexts = [
        ({"taskId": "missing-review-task", "courseId": item["course_id"]}, 404),
        ({"taskId": matching["id"], "courseId": item["course_id"]}, 409),
        ({"taskId": other_item_task["id"], "courseId": item["course_id"]}, 409),
        ({"taskId": non_review["id"], "courseId": item["course_id"]}, 409),
        ({"taskId": duplicate["id"], "courseId": "course-physics"}, 409),
    ]
    for index, (task_context, expected_status) in enumerate(contexts):
        response = client.post(
            f"/v1/reviews/{item['id']}/attempts",
            headers=auth_headers,
            json={
                "rating": "good",
                "response": "Outer derivative times the derivative of the inner function.",
                "expectedRevision": 0,
                "taskContext": task_context,
                "idempotencyKey": f"review-api-task-context-{index:04d}",
            },
        )
        assert response.status_code == expected_status
        assert response.json()["detail"]["code"] == (
            "review_task_not_found"
            if expected_status == 404
            else "review_task_context_conflict"
        )

    with client.app.state.database.connection() as connection:
        schedule_revision = connection.execute(
            "SELECT revision FROM review_schedules WHERE review_item_id = ?",
            (item["id"],),
        ).fetchone()[0]
        attempts = connection.execute(
            "SELECT COUNT(*) FROM review_attempts WHERE review_item_id = ?",
            (item["id"],),
        ).fetchone()[0]
        tasks = {
            row["id"]: dict(row)
            for row in connection.execute(
                "SELECT id, status, revision FROM study_tasks WHERE id IN (?, ?, ?, ?)",
                (
                    matching["id"],
                    duplicate["id"],
                    other_item_task["id"],
                    non_review["id"],
                ),
            ).fetchall()
        }
    assert schedule_revision == 0
    assert attempts == 0
    assert tasks[matching["id"]] == {
        "id": matching["id"],
        "status": "completed",
        "revision": 1,
    }
    for task in (duplicate, other_item_task, non_review):
        assert tasks[task["id"]] == {
            "id": task["id"],
            "status": "upcoming",
            "revision": 0,
        }


def test_bare_review_rating_does_not_complete_a_matching_feed_task(
    client, auth_headers
):
    item = _create_due_review(client)
    task = _create_review_task(client, task_id="review-task-direct-rating", item=item)

    response = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json={
            "rating": "good",
            "response": "Outer derivative times the derivative of the inner function.",
            "expectedRevision": 0,
            "idempotencyKey": "review-api-direct-rating-0001",
        },
    )

    assert response.status_code == 201
    with client.app.state.database.connection() as connection:
        persisted_task = connection.execute(
            "SELECT status, revision FROM study_tasks WHERE id = ?", (task["id"],)
        ).fetchone()
        attempt = connection.execute(
            "SELECT originating_task_id FROM review_attempts WHERE review_item_id = ?",
            (item["id"],),
        ).fetchone()
    assert dict(persisted_task) == {"status": "upcoming", "revision": 0}
    assert attempt["originating_task_id"] is None


def test_review_rating_rejects_a_stale_revision(client, auth_headers):
    item = _create_due_review(client)

    response = client.post(
        f"/v1/reviews/{item['id']}/attempts",
        headers=auth_headers,
        json={
            "rating": "hard",
            "response": "",
            "expectedRevision": 1,
            "idempotencyKey": "review-api-stale-0001",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "review_attempt_conflict"


def test_review_schedule_survives_learning_core_restart(tmp_path):
    database_path = tmp_path / "restart.sqlite3"
    settings = Settings(
        session_token=RESTART_TOKEN,
        database_path=database_path,
        seed_demo=True,
    )

    restart_headers = {"Authorization": f"Bearer {RESTART_TOKEN}"}
    with TestClient(create_app(settings)) as first_client:
        item = _create_due_review(first_client)
        applied = first_client.post(
            f"/v1/reviews/{item['id']}/attempts",
            headers=restart_headers,
            json={
                "rating": "good",
                "response": "Outer derivative times the derivative of the inner function.",
                "expectedRevision": 0,
                "idempotencyKey": "review-api-restart-0001",
            },
        )
        assert applied.status_code == 201
        scheduled_due_at = applied.json()["schedule"]["due_at"]

    with TestClient(create_app(settings)) as restarted_client:
        queue = restarted_client.get("/v1/reviews/due", headers=restart_headers)
        assert queue.status_code == 200
        assert item["id"] not in {review["id"] for review in queue.json()["items"]}
        with restarted_client.app.state.database.connection() as connection:
            persisted = connection.execute(
                "SELECT due_at, revision FROM review_schedules WHERE review_item_id = ?",
                (item["id"],),
            ).fetchone()
            attempt_count = connection.execute(
                "SELECT COUNT(*) FROM review_attempts WHERE review_item_id = ?",
                (item["id"],),
            ).fetchone()[0]

    assert persisted["revision"] == 1
    assert datetime.fromisoformat(persisted["due_at"]) == datetime.fromisoformat(
        scheduled_due_at
    )
    assert attempt_count == 1
