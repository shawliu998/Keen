from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.assessment import generate_source_cloze, generate_targeted_practice
from app.database import Database
from app.main import create_app
from app.repositories.task_repository import TaskRepository
from app.settings import Settings
from app.services.focused_study_request import (
    FocusedStudyRequestService,
    _concept_name,
    normalize_goal,
)
from conftest import TOKEN


AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC).isoformat()
COURSE_ID = "course-focused-study"
OTHER_COURSE_ID = "course-focused-other"


def _settings(database_path: Path) -> Settings:
    return Settings(
        session_token=TOKEN,
        database_path=database_path,
        seed_demo=False,
    )


def _course(client: TestClient, course_id: str) -> None:
    with client.app.state.database.connection() as connection:
        connection.execute(
            "INSERT INTO courses (id, title, description, created_at) VALUES (?, ?, '', ?)",
            (course_id, course_id, NOW),
        )
        connection.commit()


def _source(
    client: TestClient,
    *,
    course_id: str,
    suffix: str,
    chunks: list[str],
) -> list[str]:
    document_id = f"document-focused-{suffix}"
    version_id = f"version-focused-{suffix}"
    with client.app.state.database.connection() as connection:
        connection.execute(
            """
            INSERT INTO documents
                (id, course_id, name, mime_type, extension, status, page_count,
                 chunk_count, error, created_at, updated_at)
            VALUES (?, ?, ?, 'text/markdown', '.md', 'indexed', 1, ?, NULL, ?, ?)
            """,
            (document_id, course_id, f"{suffix}.md", len(chunks), NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO document_versions
                (id, document_id, version_number, content_hash, storage_path,
                 size_bytes, parser_version, page_count, created_at)
            VALUES (?, ?, 1, ?, ?, 100, 'fixture', 1, ?)
            """,
            (
                version_id,
                document_id,
                suffix[0].encode().hex().ljust(64, "0")[:64],
                f"/{suffix}",
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO course_documents (course_id, document_id, added_at) VALUES (?, ?, ?)",
            (course_id, document_id, NOW),
        )
        chunk_ids: list[str] = []
        for ordinal, content in enumerate(chunks):
            chunk_id = f"chunk-focused-{suffix}-{ordinal}"
            chunk_ids.append(chunk_id)
            connection.execute(
                """
                INSERT INTO document_chunks
                    (id, document_id, version_id, ordinal, page_number,
                     section_path, content, content_hash, text_location,
                     parser_version, embedding_version, created_at)
                VALUES (?, ?, ?, ?, 1, '[]', ?, ?, '{}', 'fixture', NULL, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    version_id,
                    ordinal,
                    content,
                    f"{ordinal + 1:064x}",
                    NOW,
                ),
            )
        connection.commit()
    return chunk_ids


def _payload(
    goal: str,
    *,
    client_request_id: str = "focused-client-request-0001",
    idempotency_key: str = "focused-idempotency-key-0001",
    course_id: str = COURSE_ID,
) -> dict[str, str]:
    return {
        "course_id": course_id,
        "goal": goal,
        "client_request_id": client_request_id,
        "idempotency_key": idempotency_key,
    }


def _post(client: TestClient, payload: dict[str, str]):
    return client.post(
        "/v1/focused-study-requests",
        headers=AUTH,
        json=payload,
    )


def _mutation_counts(client: TestClient) -> dict[str, int]:
    tables = (
        "concepts",
        "mastery",
        "study_tasks",
        "study_sessions",
        "study_plan_versions",
        "study_units",
        "study_session_events",
        "study_adaptive_actions",
    )
    with client.app.state.database.connection() as connection:
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in tables
        }


def test_focused_start_uses_only_goal_matches_in_the_selected_course_and_persists_ids(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path / "focused.sqlite3"))) as client:
        _course(client, COURSE_ID)
        _course(client, OTHER_COURSE_ID)
        local_ids = _source(
            client,
            course_id=COURSE_ID,
            suffix="local",
            chunks=[
                "Eigenvectors preserve their direction under a linear transformation.",
                "Eigenvectors have eigenvalues that describe their scale factors.",
                "Cellular respiration releases chemical energy from glucose.",
            ],
        )
        foreign_ids = _source(
            client,
            course_id=OTHER_COURSE_ID,
            suffix="foreign",
            chunks=[
                "Eigenvectors foreign secret source one.",
                "Eigenvectors foreign secret source two.",
            ],
        )

        response = _post(
            client,
            _payload("  Explain   eigenvectors from my course notes  "),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "session_created"
        assert body["session"]["goal"] == "Explain eigenvectors from my course notes"
        assert body["session"]["originating_task_id"] == body["task"]["id"]
        assert body["plan"]["session_id"] == body["session"]["id"]
        selected = list(
            dict.fromkeys(
                chunk_id
                for unit in body["plan"]["units"]
                for chunk_id in unit["source_chunk_ids"]
            )
        )
        assert selected == local_ids[:2]
        assert not set(selected) & set(foreign_ids)
        assert all(
            "respiration" not in unit["content"] for unit in body["plan"]["units"]
        )

        with client.app.state.database.connection() as connection:
            session = connection.execute(
                "SELECT goal_scope_json FROM study_sessions WHERE id = ?",
                (body["session"]["id"],),
            ).fetchone()
            task = TaskRepository(connection).get(body["task"]["id"])
            concept = connection.execute(
                "SELECT name FROM concepts WHERE id = ?",
                (body["task"]["concept_id"],),
            ).fetchone()
        assert json.loads(session["goal_scope_json"])["source_chunk_ids"] == selected
        assert (
            task["priority_components"]["focused_study_request"]["source_chunk_ids"]
            == selected
        )
        assert concept["name"] == "Eigenvectors"


def test_no_match_and_lexically_invalid_cjk_fail_closed_without_writes(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path / "no-match.sqlite3"))) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="biology",
            chunks=[
                "Photosynthesis captures sunlight.",
                "Chloroplasts contain chlorophyll.",
            ],
        )
        before = _mutation_counts(client)

        missing = _post(client, _payload("Explain eigenvectors"))
        cjk = _post(
            client,
            _payload(
                "光合",
                client_request_id="focused-client-request-cjk01",
                idempotency_key="focused-idempotency-key-cjk01",
            ),
        )

        assert missing.status_code == cjk.status_code == 200
        assert missing.json()["blocked_reason"] == "no_matching_indexed_source"
        assert cjk.json()["blocked_reason"] == "no_matching_indexed_source"
        assert _mutation_counts(client) == before


def test_intent_pronoun_cannot_match_an_unrelated_first_person_source(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path / "pronoun.sqlite3"))) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="pronoun-biology",
            chunks=[
                "I use cellular respiration to describe how cells release energy.",
                "I explain how photosynthesis captures sunlight in chloroplasts.",
            ],
        )
        before = _mutation_counts(client)

        response = _post(
            client,
            _payload("I want to understand eigenvectors"),
        )

        assert response.status_code == 200
        assert response.json()["outcome"] == "blocked"
        assert response.json()["blocked_reason"] == "no_matching_indexed_source"
        assert _mutation_counts(client) == before


def test_alpha_only_matches_block_before_creating_learning_or_adaptive_state(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_app(_settings(tmp_path / "alpha-dead-end.sqlite3"))
    ) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="alpha-dead-end",
            chunks=["Alpha", "Alpha"],
        )
        before = _mutation_counts(client)

        response = _post(client, _payload("Explain Alpha"))

        assert response.status_code == 200
        assert response.json()["outcome"] == "blocked"
        assert response.json()["blocked_reason"] == "no_matching_indexed_source"
        assert _mutation_counts(client) == before
        with client.app.state.database.connection() as connection:
            identity = connection.execute(
                "SELECT outcome, task_id, session_id, plan_id "
                "FROM focused_study_request_identities"
            ).fetchone()
            pending_adaptive = connection.execute(
                "SELECT COUNT(*) FROM study_adaptive_actions WHERE status = 'pending'"
            ).fetchone()[0]
        assert tuple(identity) == ("blocked", None, None, None)
        assert pending_adaptive == 0


def test_single_source_chunk_is_split_on_a_word_boundary(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_app(_settings(tmp_path / "word-boundary-units.sqlite3"))
    ) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="word-boundary-units",
            chunks=[
                (
                    "Eigenvectors preserve their direction under a linear "
                    "transformation.\n"
                    "Eigenvectors have eigenvalues that describe their scale factors.\n"
                    "For a matrix A, a nonzero vector v is an eigenvector when "
                    "Av equals "
                    "lambda v. The scalar lambda is the corresponding eigenvalue."
                )
            ],
        )

        response = _post(client, _payload("Explain Eigenvectors"))

        assert response.status_code == 201
        units = response.json()["plan"]["units"]
        assert units[0]["content"].endswith("scale factors.")
        assert units[1]["content"].startswith("For a matrix A")
        assert not units[1]["content"].startswith("s.")


def test_focused_start_selects_only_units_with_distinct_recall_and_practice(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_app(_settings(tmp_path / "completable-units.sqlite3"))
    ) as client:
        _course(client, COURSE_ID)
        chunk_ids = _source(
            client,
            course_id=COURSE_ID,
            suffix="completable-units",
            chunks=[
                "Alpha",
                "Alpha particles carry positive charge.",
                "Alpha decay emits helium nuclei.",
            ],
        )

        response = _post(client, _payload("Explain Alpha"))

        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "session_created"
        assert [unit["source_chunk_ids"] for unit in body["plan"]["units"]] == [
            [chunk_ids[1]],
            [chunk_ids[2]],
        ]
        for unit in body["plan"]["units"]:
            recall = generate_source_cloze(
                unit["content"], concept=body["session"]["goal"]
            )
            assert recall is not None
            practice = generate_targeted_practice(
                unit["content"],
                concept=body["session"]["goal"],
                excluded_answers=recall.accepted_answers,
            )
            assert practice is not None
            assert practice.accepted_answer.casefold() != (
                recall.accepted_answers[0].casefold()
            )

        diagnostic = client.post(
            f"/v1/study-sessions/{body['session']['id']}/diagnostic",
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": body["session"]["revision"],
                "idempotency_key": "focused-completable-diagnostic-begin",
            },
        )
        assert diagnostic.status_code == 201
        diagnostic_body = diagnostic.json()
        diagnosed = client.post(
            f"/v1/study-sessions/{body['session']['id']}/diagnostic/"
            f"{diagnostic_body['checkpoint']['id']}/answer",
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": diagnostic_body["session"]["revision"],
                "idempotency_key": "focused-completable-diagnostic-answer",
                "response": "Ready to study the selected source.",
                "self_assessment": "partial",
            },
        )
        assert diagnosed.status_code == 201
        recall_begin = client.post(
            f"/v1/study-sessions/{body['session']['id']}/active-recall",
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": diagnosed.json()["session"]["revision"],
                "idempotency_key": "focused-completable-recall-begin",
            },
        )
        assert recall_begin.status_code == 201
        recall_body = recall_begin.json()
        with client.app.state.database.connection() as connection:
            answer_key = connection.execute(
                """
                SELECT i.answer_key_json
                FROM study_active_recall_runs r
                JOIN assessment_items i
                  ON i.id = r.item_id AND i.assessment_id = r.assessment_id
                WHERE r.id = ?
                """,
                (recall_body["run"]["id"],),
            ).fetchone()
        recall_answer = json.loads(answer_key["answer_key_json"])["accepted_answers"][0]
        recalled = client.post(
            f"/v1/study-sessions/{body['session']['id']}/active-recall/"
            f"{recall_body['run']['id']}/answer",
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": recall_body["session"]["revision"],
                "idempotency_key": "focused-completable-recall-answer",
                "response": recall_answer,
            },
        )
        assert recalled.status_code == 200
        assert recalled.json()["grade"]["correct"] is True
        practice_begin = client.post(
            f"/v1/study-sessions/{body['session']['id']}/practice",
            headers=AUTH,
            json={
                "course_id": COURSE_ID,
                "expected_revision": recalled.json()["session"]["revision"],
                "idempotency_key": "focused-completable-practice-begin",
            },
        )
        assert practice_begin.status_code == 201
        assert practice_begin.json()["run"]["status"] == "pending"


def test_blocked_request_binds_both_identities_and_rejects_every_drift(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_app(_settings(tmp_path / "blocked-ledger.sqlite3"))
    ) as client:
        _course(client, COURSE_ID)
        payload = _payload("Explain eigenvectors")
        before = _mutation_counts(client)

        blocked = _post(client, payload)
        exact_retry = _post(client, payload)
        changed_goal = _post(client, {**payload, "goal": "Explain eigenvalues"})
        changed_key = _post(
            client,
            {**payload, "idempotency_key": "focused-idempotency-key-drift"},
        )
        changed_client = _post(
            client,
            {**payload, "client_request_id": "focused-client-request-drift"},
        )

        assert blocked.status_code == exact_retry.status_code == 200
        assert blocked.json()["blocked_reason"] == "no_matching_indexed_source"
        assert exact_retry.json()["blocked_reason"] == "no_matching_indexed_source"
        assert (
            changed_goal.status_code
            == changed_key.status_code
            == changed_client.status_code
            == 409
        )
        assert _mutation_counts(client) == before
        with client.app.state.database.connection() as connection:
            identity = connection.execute(
                "SELECT * FROM focused_study_request_identities"
            ).fetchall()
        assert len(identity) == 1
        assert identity[0]["client_request_id"] == payload["client_request_id"]
        assert identity[0]["idempotency_key"] == payload["idempotency_key"]
        assert identity[0]["outcome"] == "blocked"
        assert identity[0]["task_id"] is None
        assert identity[0]["session_id"] is None
        assert identity[0]["plan_id"] is None


def test_exact_blocked_retry_can_atomically_upgrade_after_restart_when_source_arrives(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "blocked-upgrade.sqlite3"
    settings = _settings(database_path)
    payload = _payload("Explain eigenvectors")
    with TestClient(create_app(settings)) as client:
        _course(client, COURSE_ID)
        blocked = _post(client, payload)
        assert blocked.status_code == 200
        assert blocked.json()["outcome"] == "blocked"

    with TestClient(create_app(settings)) as restarted:
        drifted = _post(restarted, {**payload, "goal": "Explain eigenvalues"})
        assert drifted.status_code == 409
        _source(
            restarted,
            course_id=COURSE_ID,
            suffix="blocked-upgrade",
            chunks=[
                "Eigenvectors retain direction under a linear transformation.",
                "Eigenvectors have eigenvalues that describe their scale.",
            ],
        )
        created = _post(restarted, payload)
        replayed = _post(restarted, payload)

        assert created.status_code == 201
        assert created.json()["outcome"] == "session_created"
        assert replayed.status_code == 200
        assert replayed.json()["outcome"] == "replayed"
        for key in ("task", "session", "plan"):
            assert replayed.json()[key] == created.json()[key]
        with restarted.app.state.database.connection() as connection:
            identity = connection.execute(
                "SELECT * FROM focused_study_request_identities"
            ).fetchone()
        assert identity["outcome"] == "session_created"
        assert identity["task_id"] == created.json()["task"]["id"]
        assert identity["session_id"] == created.json()["session"]["id"]
        assert identity["plan_id"] == created.json()["plan"]["id"]


def test_successful_identity_with_a_damaged_plan_link_fails_closed_without_recreation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "damaged-ledger.sqlite3"
    settings = _settings(database_path)
    payload = _payload("Explain eigenvectors")
    with TestClient(create_app(settings)) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="damaged-ledger",
            chunks=[
                "Eigenvectors retain direction under a linear transformation.",
                "Eigenvectors have eigenvalues that describe their scale.",
            ],
        )
        created = _post(client, payload)
        assert created.status_code == 201
        before = _mutation_counts(client)
        with client.app.state.database.connection() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "UPDATE focused_study_request_identities SET plan_id = 'missing-plan'"
            )
            connection.commit()

        retry = _post(client, payload)
        assert retry.status_code == 503
        assert retry.json()["detail"]["outcomeMayBeDurable"] is True
        assert _mutation_counts(client) == before


def test_exact_replay_is_stable_and_identity_reuse_with_new_payload_conflicts(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path / "replay.sqlite3"))) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="replay",
            chunks=[
                "Eigenvectors have a direction.",
                "Eigenvalues scale eigenvectors.",
            ],
        )
        payload = _payload("Explain eigenvectors")
        created = _post(client, payload)
        replayed = _post(client, payload)
        same_key_new_goal = _post(client, {**payload, "goal": "Explain eigenvalues"})
        same_client_new_key = _post(
            client,
            {
                **payload,
                "goal": "Explain eigenvalues",
                "idempotency_key": "focused-idempotency-key-0002",
            },
        )

        assert created.status_code == 201
        assert replayed.status_code == 200
        assert replayed.json()["outcome"] == "replayed"
        for key in ("task", "session", "plan"):
            assert replayed.json()[key] == created.json()[key]
        assert same_key_new_goal.status_code == 409
        assert same_client_new_key.status_code == 409


def test_distinct_goals_create_distinct_work_despite_an_active_autonomous_task(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path / "distinct.sqlite3"))) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="distinct",
            chunks=[
                "Eigenvectors keep direction and eigenvalues provide scale.",
                "Photosynthesis captures light energy in chloroplasts.",
            ],
        )
        with client.app.state.database.connection() as connection:
            connection.execute(
                """INSERT INTO concepts
                       (id, course_id, name, bkt_slip, bkt_guess, bkt_transit)
                   VALUES ('autonomous-concept', ?, 'Existing autonomous target', 0.1, 0.2, 0.1)""",
                (COURSE_ID,),
            )
            TaskRepository(connection).create_task(
                task_id="existing-autonomous-task",
                course_id=COURSE_ID,
                concept_id="autonomous-concept",
                title="Existing autonomous work",
                reason="Existing recommendation",
                due_at=NOW,
                estimated_minutes=20,
                source_type="weak_concept",
                source_id="autonomous-concept",
                priority_score=0.5,
                priority_components={
                    "recommendation_algorithm_version": "autonomous-recommendation/1.0.0"
                },
                recommended_reason="Existing recommendation",
                idempotency_key="existing-autonomous-task-key",
                created_at=NOW,
            )

        first = _post(client, _payload("Explain eigenvectors"))
        second = _post(
            client,
            _payload(
                "Explain photosynthesis",
                client_request_id="focused-client-request-0002",
                idempotency_key="focused-idempotency-key-0002",
            ),
        )

        assert first.status_code == second.status_code == 201
        for key in ("task", "session", "plan"):
            assert first.json()[key]["id"] != second.json()[key]["id"]
        assert first.json()["task"]["id"] != "existing-autonomous-task"
        assert second.json()["task"]["id"] != "existing-autonomous-task"


def test_restart_reconciles_the_same_committed_task_session_and_plan(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "restart.sqlite3"
    settings = _settings(database_path)
    payload = _payload("Explain eigenvectors")
    with TestClient(create_app(settings)) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="restart",
            chunks=["Eigenvectors have direction.", "Eigenvalues scale eigenvectors."],
        )
        created = _post(client, payload)
        assert created.status_code == 201
        created_body = created.json()

    with TestClient(create_app(settings)) as restarted:
        replayed = _post(restarted, payload)
        assert replayed.status_code == 200
        assert replayed.json()["outcome"] == "replayed"
        for key in ("task", "session", "plan"):
            assert replayed.json()[key] == created_body[key]


def test_unknown_committed_outcome_reconciles_with_the_same_request_identities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with TestClient(create_app(_settings(tmp_path / "unknown.sqlite3"))) as client:
        _course(client, COURSE_ID)
        _source(
            client,
            course_id=COURSE_ID,
            suffix="unknown",
            chunks=[
                "Eigenvectors have a direction.",
                "Eigenvalues scale eigenvectors.",
            ],
        )
        original = FocusedStudyRequestService.start

        def commit_then_disconnect(self, **kwargs):
            original(self, **kwargs)
            raise sqlite3.OperationalError("simulated response loss after commit")

        monkeypatch.setattr(FocusedStudyRequestService, "start", commit_then_disconnect)
        unknown = _post(client, _payload("Explain eigenvectors"))
        monkeypatch.setattr(FocusedStudyRequestService, "start", original)
        reconciled = _post(client, _payload("Explain eigenvectors"))

        assert unknown.status_code == 503
        assert unknown.json()["detail"]["outcomeMayBeDurable"] is True
        assert reconciled.status_code == 200
        assert reconciled.json()["outcome"] == "replayed"
        with client.app.state.database.connection() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM study_tasks").fetchone()[0]
                == 1
            )
            assert (
                connection.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM study_plan_versions"
                ).fetchone()[0]
                == 1
            )


def test_focused_start_authenticates_before_parsing_and_rejects_extra_fields(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path / "strict.sqlite3"))) as client:
        payload = _payload("Explain eigenvectors")
        unauthenticated = client.post(
            "/v1/focused-study-requests", json={**payload, "unexpected": True}
        )
        strict = client.post(
            "/v1/focused-study-requests",
            headers=AUTH,
            json={**payload, "unexpected": True},
        )
        assert unauthenticated.status_code == 401
        assert strict.status_code == 422


@pytest.mark.parametrize("control", ["\u001c", "\u0085"])
def test_focused_goal_rejects_hidden_category_c_controls_before_any_write(
    tmp_path: Path,
    control: str,
) -> None:
    with TestClient(
        create_app(_settings(tmp_path / f"control-{ord(control)}.sqlite3"))
    ) as client:
        before = _mutation_counts(client)
        response = _post(client, _payload(f"Explain{control}eigenvectors"))

        assert response.status_code == 422
        assert _mutation_counts(client) == before
        with client.app.state.database.connection() as connection:
            ledger_count = connection.execute(
                "SELECT COUNT(*) FROM focused_study_request_identities"
            ).fetchone()[0]
        assert ledger_count == 0

    with pytest.raises(ValueError, match="control"):
        normalize_goal(f"Explain{control}eigenvectors")


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        (
            "Use a short lesson to help me understand the chain rule, then test my recall.",
            "Chain rule",
        ),
        ("Explain eigenvectors from my course notes", "Eigenvectors"),
        ("请帮我解释光合作用课程资料", "光合作用"),
    ],
)
def test_focused_goal_derives_a_bounded_concept_label(goal: str, expected: str) -> None:
    assert _concept_name(goal) == expected


def test_030_focused_identity_migration_is_forward_only_and_idempotent(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "focused-migration.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """CREATE TABLE schema_migrations (
                   version INTEGER PRIMARY KEY,
                   applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        for version in range(1, 30):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.execute(
            """INSERT INTO courses (id, title, description, created_at)
               VALUES ('preserved-course', 'Preserved', '', ?)""",
            (NOW,),
        )
        connection.commit()

    assert database.migrate() == [30, 31, 32]
    assert database.migrate() == []
    with database.connection() as connection:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(focused_study_request_identities)"
            )
        }
        preserved = connection.execute(
            "SELECT title FROM courses WHERE id = 'preserved-course'"
        ).fetchone()
        migration = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = 30"
        ).fetchone()
    assert {
        "client_request_id",
        "idempotency_key",
        "payload_fingerprint",
        "course_id",
        "goal",
        "outcome",
        "task_id",
        "session_id",
        "plan_id",
        "created_at",
        "updated_at",
    } == columns
    assert preserved["title"] == "Preserved"
    assert migration["version"] == 30
