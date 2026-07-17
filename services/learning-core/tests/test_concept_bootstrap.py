from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.concept_bootstrap import (
    INITIAL_MASTERY_ALGORITHM_VERSION,
    INITIAL_MASTERY_PROBABILITY,
    ConceptBootstrapRepository,
    CourseDocumentUnavailableError,
    IncompleteConceptMasteryStateError,
    IndexedDocumentRequiredError,
)
from app.database import Database
from app.repository import LearningRepository


def _insert_document(
    connection: sqlite3.Connection,
    *,
    document_id: str,
    course_id: str,
    status: str = "indexed",
    name: str = "Limits notes.md",
    section_path: str = '["Limits"]',
) -> None:
    now = "2026-07-17T00:00:00+00:00"
    connection.execute(
        """
        INSERT INTO documents
            (id, course_id, name, mime_type, extension, status, page_count,
             chunk_count, error, created_at, updated_at)
        VALUES (?, ?, ?, 'text/markdown', '.md', ?, 1, 1, NULL, ?, ?)
        """,
        (document_id, course_id, name, status, now, now),
    )
    connection.execute(
        """
        INSERT INTO document_versions
            (id, document_id, version_number, content_hash, storage_path,
             size_bytes, parser_version, page_count, created_at)
        VALUES (?, ?, 1, ?, 'documents/source', 1, 'fixture', 1, ?)
        """,
        (f"version-{document_id}", document_id, "a" * 64, now),
    )
    connection.execute(
        """
        INSERT INTO course_documents (course_id, document_id, added_at)
        VALUES (?, ?, ?)
        """,
        (course_id, document_id, now),
    )
    if status == "indexed":
        connection.execute(
            """
            INSERT INTO document_chunks
                (id, document_id, version_id, ordinal, page_number, section_path,
                 content, content_hash, text_location, parser_version,
                 embedding_version, created_at)
            VALUES (?, ?, ?, 0, 1, ?, 'source text', ?, '{}', 'fixture', NULL, ?)
            """,
            (
                f"chunk-{document_id}",
                document_id,
                f"version-{document_id}",
                section_path,
                "b" * 64,
                now,
            ),
        )
    connection.commit()


@pytest.fixture
def database(tmp_path):
    database = Database(tmp_path / "concept-bootstrap.sqlite3")
    database.migrate()
    database.seed_demo()
    return database


def test_bootstrap_requires_indexed_document_linked_to_course(database):
    with database.connection() as connection:
        repository = ConceptBootstrapRepository(connection)
        with pytest.raises(CourseDocumentUnavailableError, match="not available"):
            repository.bootstrap(course_id="course-calculus", document_id="missing")

        _insert_document(
            connection,
            document_id="queued-doc",
            course_id="course-calculus",
            status="queued",
        )
        with pytest.raises(IndexedDocumentRequiredError, match="finish indexing"):
            repository.bootstrap(course_id="course-calculus", document_id="queued-doc")


def test_bootstrap_rejects_document_outside_course_without_leaking_source(database):
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id="physics-doc",
            course_id="course-physics",
            name="private-physics-path.md",
        )
        with pytest.raises(CourseDocumentUnavailableError) as raised:
            ConceptBootstrapRepository(connection).bootstrap(
                course_id="course-calculus", document_id="physics-doc"
            )

    assert "private-physics-path" not in str(raised.value)


def test_bootstrap_is_idempotent_and_never_creates_user_mastery_events(database):
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id="limits-doc",
            course_id="course-calculus",
            section_path='["Bootstrap limits"]',
        )
        repository = ConceptBootstrapRepository(connection)
        created = repository.bootstrap(
            course_id="course-calculus", document_id="limits-doc"
        )
        replay = repository.bootstrap(
            course_id="course-calculus", document_id="limits-doc"
        )

        assert created.concept_created is True
        assert created.mastery_initialized is True
        assert replay.concept_created is False
        assert replay.mastery_initialized is False
        assert created.concept_id == replay.concept_id
        assert created.concept_name == "Bootstrap limits"
        assert created.mastery_probability == INITIAL_MASTERY_PROBABILITY
        assert created.mastery_attempts == 0
        assert (
            created.mastery_initialization_algorithm_version
            == INITIAL_MASTERY_ALGORITHM_VERSION
        )
        assert replay.mastery_initialization_algorithm is None
        assert replay.mastery_initialization_algorithm_version is None
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM mastery_events WHERE concept_id = ?",
                (created.concept_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM mastery_evidence WHERE concept_id = ?",
                (created.concept_id,),
            ).fetchone()[0]
            == 0
        )


def test_bootstrap_falls_back_to_safe_document_display_name(database):
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id="display-name-doc",
            course_id="course-calculus",
            name="Thermodynamics.md",
            section_path='["../not-a-concept-title"]',
        )

        result = ConceptBootstrapRepository(connection).bootstrap(
            course_id="course-calculus", document_id="display-name-doc"
        )

    assert result.concept_created is True
    assert result.mastery_initialized is True
    assert result.concept_name == "Thermodynamics"


def test_bootstrap_preserves_existing_concept_and_mastery_state(database):
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id="known-limits",
            course_id="course-calculus",
            section_path='["Known bootstrap topic"]',
        )
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name)
            VALUES ('manual-limits', 'course-calculus', 'Known bootstrap topic')
            """
        )
        connection.execute(
            """
            INSERT INTO mastery (concept_id, probability, attempts, updated_at)
            VALUES ('manual-limits', 0.85, 7, '2026-07-17T00:00:00+00:00')
            """
        )
        connection.commit()

        result = ConceptBootstrapRepository(connection).bootstrap(
            course_id="course-calculus", document_id="known-limits"
        )

        assert result.concept_created is False
        assert result.mastery_initialized is False
        assert result.concept_id == "manual-limits"
        assert result.mastery_probability == 0.85
        assert result.mastery_attempts == 7
        assert result.mastery_initialization_algorithm is None
        assert result.mastery_initialization_algorithm_version is None


def test_bootstrap_initializes_missing_mastery_without_learning_history(database):
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id="missing-mastery-doc",
            course_id="course-calculus",
            section_path='["Missing mastery topic"]',
        )
        connection.execute(
            """
            INSERT INTO concepts (id, course_id, name)
            VALUES ('missing-mastery', 'course-calculus', 'Missing mastery topic')
            """
        )
        connection.commit()

        result = ConceptBootstrapRepository(connection).bootstrap(
            course_id="course-calculus", document_id="missing-mastery-doc"
        )

        assert result.concept_created is False
        assert result.mastery_initialized is True
        assert result.mastery_probability == INITIAL_MASTERY_PROBABILITY
        assert result.mastery_attempts == 0
        assert result.mastery_initialization_algorithm == "bkt"
        assert (
            result.mastery_initialization_algorithm_version
            == INITIAL_MASTERY_ALGORITHM_VERSION
        )


@pytest.mark.parametrize("history_kind", ["event", "evidence"])
def test_bootstrap_rejects_missing_mastery_with_learning_history(
    database, history_kind
):
    concept_name = f"Incomplete {history_kind} topic"
    document_id = f"incomplete-{history_kind}-doc"
    concept_id = f"incomplete-{history_kind}"
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id=document_id,
            course_id="course-calculus",
            section_path=f'["{concept_name}"]',
        )
        connection.execute(
            "INSERT INTO concepts (id, course_id, name) VALUES (?, ?, ?)",
            (concept_id, "course-calculus", concept_name),
        )
        if history_kind == "event":
            connection.execute(
                """
                INSERT INTO mastery_events
                    (concept_id, correct, probability_before, probability_after,
                     observed_at, algorithm, algorithm_version, evidence_ids_json,
                     idempotency_key)
                VALUES (?, 1, 0.2, 0.3, '2026-07-17T00:00:00+00:00',
                        'bkt', 'fixture-v1', '[]', ?)
                """,
                (concept_id, f"incomplete-{history_kind}-event"),
            )
        else:
            connection.execute(
                """
                INSERT INTO mastery_evidence
                    (id, concept_id, attempt_id, session_id, evidence_type,
                     correctness, independence, hint_level, confidence_calibration,
                     weight, idempotency_key, created_at)
                VALUES (?, ?, NULL, NULL, 'manual', 1, 1, 0, NULL, 1, ?,
                        '2026-07-17T00:00:00+00:00')
                """,
                (
                    f"incomplete-{history_kind}-evidence",
                    concept_id,
                    f"incomplete-{history_kind}-evidence-key",
                ),
            )
        connection.commit()

        with pytest.raises(IncompleteConceptMasteryStateError, match="repair"):
            ConceptBootstrapRepository(connection).bootstrap(
                course_id="course-calculus", document_id=document_id
            )

        assert (
            connection.execute(
                "SELECT 1 FROM mastery WHERE concept_id = ?", (concept_id,)
            ).fetchone()
            is None
        )


def test_bootstrap_replay_after_a_mastery_event_does_not_claim_initialization(database):
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id="event-replay-doc",
            course_id="course-calculus",
            section_path='["Event replay topic"]',
        )
        repository = ConceptBootstrapRepository(connection)
        initialized = repository.bootstrap(
            course_id="course-calculus", document_id="event-replay-doc"
        )
        event = LearningRepository(connection).record_attempt(
            initialized.concept_id, correct=True
        )
        assert event is not None

        replay = repository.bootstrap(
            course_id="course-calculus", document_id="event-replay-doc"
        )

        assert replay.concept_created is False
        assert replay.mastery_initialized is False
        assert replay.mastery_probability == event["probability_after"]
        assert replay.mastery_attempts == event["attempts"]
        assert replay.mastery_initialization_algorithm is None
        assert replay.mastery_initialization_algorithm_version is None


def test_bootstrap_concurrent_calls_create_one_zero_evidence_concept(database):
    with database.connection() as connection:
        _insert_document(
            connection,
            document_id="concurrent-doc",
            course_id="course-calculus",
            section_path='["Concurrent bootstrap topic"]',
        )

    barrier = Barrier(2)

    def bootstrap() -> tuple[str, bool]:
        connection = sqlite3.connect(database.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            barrier.wait(timeout=5)
            result = ConceptBootstrapRepository(connection).bootstrap(
                course_id="course-calculus", document_id="concurrent-doc"
            )
            return result.concept_id, result.concept_created
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _value: bootstrap(), range(2)))

    assert len({result[0] for result in results}) == 1
    assert results[0][0].startswith("concept-bootstrap-")
    assert sorted(result[1] for result in results) == [False, True]
    with database.connection() as connection:
        concept_id = results[0][0]
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM concepts WHERE id = ?", (concept_id,)
            ).fetchone()[0]
            == 1
        )
        mastery = connection.execute(
            "SELECT probability, attempts FROM mastery WHERE concept_id = ?",
            (concept_id,),
        ).fetchone()
        assert mastery is not None
        assert tuple(mastery) == (INITIAL_MASTERY_PROBABILITY, 0)
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM mastery_events WHERE concept_id = ?",
                (concept_id,),
            ).fetchone()[0]
            == 0
        )
