from __future__ import annotations

import asyncio
import sqlite3
from hashlib import sha256

import pytest

from app.database import Database, ExtensionLoadingSecurityError, VectorCapabilityError
from app.retrieval_interfaces import ChunkMetadata, EmbeddingModel, VectorRecord
from app.sqlite_vector_store import SQLiteVectorStore


MODEL = EmbeddingModel(
    provider="local-fixture", model="tiny", version="1", dimensions=3
)
NOW = "2026-07-16T00:00:00+00:00"


def _run(awaitable):
    return asyncio.run(awaitable)


def _chunk(
    chunk_id: str,
    document_id: str,
    ordinal: int,
    *,
    courses: tuple[str, ...],
) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=chunk_id,
        document_id=document_id,
        document_name=f"{document_id}.txt",
        page_number=ordinal + 1,
        ordinal=ordinal,
        section_path=("Fixture",),
        text=f"fixture {chunk_id}",
        course_ids=courses,
    )


@pytest.fixture
def vector_database(tmp_path) -> Database:
    database = Database(tmp_path / "vectors.sqlite3")
    database.migrate()
    with database.connection() as connection:
        connection.executemany(
            "INSERT INTO courses(id, title, description, created_at) VALUES (?, ?, '', ?)",
            [("course-a", "Course A", NOW), ("course-b", "Course B", NOW)],
        )
        for document_id in ("doc-a", "doc-b"):
            connection.execute(
                """
                INSERT INTO documents (
                    id, course_id, name, mime_type, extension, status,
                    page_count, chunk_count, error, created_at, updated_at
                ) VALUES (?, NULL, ?, 'text/plain', '.txt', 'indexed',
                          2, 2, NULL, ?, ?)
                """,
                (document_id, f"{document_id}.txt", NOW, NOW),
            )
            version_id = f"version-{document_id}"
            connection.execute(
                """
                INSERT INTO document_versions (
                    id, document_id, version_number, content_hash, storage_path,
                    size_bytes, parser_version, page_count, created_at
                ) VALUES (?, ?, 1, ?, ?, 10, 'fixture', 2, ?)
                """,
                (
                    version_id,
                    document_id,
                    sha256(document_id.encode()).hexdigest(),
                    f"{document_id}.txt",
                    NOW,
                ),
            )
            for ordinal in range(2):
                chunk_id = f"chunk-{document_id[-1]}-{ordinal}"
                content = f"fixture content {chunk_id}"
                connection.execute(
                    """
                    INSERT INTO document_chunks (
                        id, document_id, version_id, ordinal, page_number,
                        section_path, content, content_hash, text_location,
                        parser_version, embedding_version, created_at
                    ) VALUES (?, ?, ?, ?, ?, '["Fixture"]', ?, ?, '{}',
                              'fixture', NULL, ?)
                    """,
                    (
                        chunk_id,
                        document_id,
                        version_id,
                        ordinal,
                        ordinal + 1,
                        content,
                        sha256(content.encode()).hexdigest(),
                        NOW,
                    ),
                )
        connection.executemany(
            "INSERT INTO course_documents(course_id, document_id, added_at) VALUES (?, ?, ?)",
            [("course-a", "doc-a", NOW), ("course-b", "doc-b", NOW)],
        )
        connection.commit()
    return database


def test_exact_cosine_search_course_filter_state_and_reopen(vector_database):
    store = SQLiteVectorStore(vector_database)
    records = [
        VectorRecord(
            _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",)), (1, 0, 0), MODEL
        ),
        VectorRecord(
            _chunk("chunk-a-1", "doc-a", 1, courses=("course-a",)), (0.8, 0.2, 0), MODEL
        ),
        VectorRecord(
            _chunk("chunk-b-0", "doc-b", 0, courses=("course-b",)), (0, 1, 0), MODEL
        ),
        VectorRecord(
            _chunk("chunk-b-1", "doc-b", 1, courses=("course-b",)), (0, 0.8, 0.2), MODEL
        ),
    ]
    _run(store.upsert(records))

    all_results = _run(
        store.search((1, 0, 0), embedding_model=MODEL, limit=4, course_id=None)
    )
    course_b = _run(
        store.search((1, 0, 0), embedding_model=MODEL, limit=4, course_id="course-b")
    )

    assert [result.chunk.chunk_id for result in all_results[:2]] == [
        "chunk-a-0",
        "chunk-a-1",
    ]
    assert {result.chunk.document_id for result in course_b} == {"doc-b"}
    assert all(result.chunk.course_ids == ("course-b",) for result in course_b)
    with vector_database.connection() as connection:
        states = connection.execute(
            "SELECT status, expected_chunk_count, embedded_chunk_count FROM document_embedding_state"
        ).fetchall()
    assert [tuple(row) for row in states] == [("ready", 2, 2), ("ready", 2, 2)]

    reopened = SQLiteVectorStore(Database(vector_database.path))
    reopened_results = _run(
        reopened.search((1, 0, 0), embedding_model=MODEL, limit=4, course_id=None)
    )
    assert [item.chunk.chunk_id for item in reopened_results] == [
        item.chunk.chunk_id for item in all_results
    ]


def test_search_excludes_vectors_without_complete_ready_document_state(vector_database):
    store = SQLiteVectorStore(vector_database)
    _run(
        store.upsert(
            [
                VectorRecord(
                    _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",)),
                    (1, 0, 0),
                    MODEL,
                ),
                VectorRecord(
                    _chunk("chunk-a-1", "doc-a", 1, courses=("course-a",)),
                    (0.8, 0.2, 0),
                    MODEL,
                ),
            ]
        )
    )
    assert _run(store.search((1, 0, 0), embedding_model=MODEL, limit=5, course_id=None))

    with vector_database.connection() as connection:
        connection.execute(
            "UPDATE document_embedding_state SET status = 'failed' WHERE document_id = 'doc-a'"
        )
        connection.commit()

    assert (
        _run(store.search((1, 0, 0), embedding_model=MODEL, limit=5, course_id=None))
        == ()
    )


def test_search_excludes_partial_vectors_even_when_state_counts_claim_ready(
    vector_database,
):
    store = SQLiteVectorStore(vector_database)
    records = [
        VectorRecord(
            _chunk(
                f"chunk-{suffix}-{ordinal}",
                f"doc-{suffix}",
                ordinal,
                courses=(course,),
            ),
            vector,
            MODEL,
        )
        for suffix, course, vectors in (
            ("a", "course-a", ((1, 0, 0), (0.8, 0.2, 0))),
            ("b", "course-b", ((0, 1, 0), (0, 0.8, 0.2))),
        )
        for ordinal, vector in enumerate(vectors)
    ]
    _run(store.upsert(records))
    with vector_database.connection() as connection:
        connection.execute("DELETE FROM chunk_embeddings WHERE chunk_id = 'chunk-a-1'")
        connection.execute(
            """
            UPDATE document_embedding_state
            SET status = 'ready', expected_chunk_count = 2, embedded_chunk_count = 2
            WHERE document_id = 'doc-a'
            """
        )
        connection.commit()

    results = _run(
        store.search((1, 0, 0), embedding_model=MODEL, limit=10, course_id=None)
    )
    assert results
    assert {result.chunk.document_id for result in results} == {"doc-b"}


def test_model_version_and_dimensions_never_mix(vector_database):
    store = SQLiteVectorStore(vector_database)
    _run(
        store.upsert(
            [
                VectorRecord(
                    _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",)),
                    (1, 0, 0),
                    MODEL,
                )
            ]
        )
    )

    with pytest.raises(ValueError, match="version"):
        _run(
            store.search(
                (1, 0, 0),
                embedding_model=EmbeddingModel(
                    provider=MODEL.provider,
                    model=MODEL.model,
                    version="2",
                    dimensions=3,
                ),
                limit=5,
                course_id=None,
            )
        )
    with pytest.raises(ValueError, match="dimension mismatch"):
        _run(store.search((1, 0), embedding_model=MODEL, limit=5, course_id=None))

    with vector_database.connection() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE embedding_models SET version = 'mutated' WHERE provider = ?",
                (MODEL.provider,),
            )


def test_delete_document_clears_all_model_vectors_and_state(vector_database):
    store = SQLiteVectorStore(vector_database)
    second_model = EmbeddingModel(
        provider="local-fixture", model="other", version="1", dimensions=3
    )
    chunk = _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",))
    _run(
        store.upsert(
            [
                VectorRecord(chunk, (1, 0, 0), MODEL),
                VectorRecord(chunk, (0, 1, 0), second_model),
            ]
        )
    )

    assert _run(store.delete_document("doc-a")) == 2
    with vector_database.connection() as connection:
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


def test_delete_document_does_not_require_vector_extension(vector_database):
    store = SQLiteVectorStore(vector_database)
    _run(
        store.upsert(
            [
                VectorRecord(
                    _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",)),
                    (1, 0, 0),
                    MODEL,
                )
            ]
        )
    )

    def fail_to_load(_connection):
        raise RuntimeError("fixture extension failure")

    lexical_only = Database(vector_database.path, vector_extension_loader=fail_to_load)
    assert _run(SQLiteVectorStore(lexical_only).delete_document("doc-a")) == 1
    with lexical_only.connection() as connection:
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


def test_embedding_foreign_keys_cascade_without_vector_extension(vector_database):
    store = SQLiteVectorStore(vector_database)
    _run(
        store.upsert(
            [
                VectorRecord(
                    _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",)),
                    (1, 0, 0),
                    MODEL,
                )
            ]
        )
    )
    with vector_database.connection() as connection:
        connection.execute("DELETE FROM documents WHERE id = 'doc-a'")
        connection.commit()
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


def test_extension_failure_keeps_lexical_database_available(tmp_path):
    def fail_to_load(_connection):
        raise RuntimeError("fixture extension failure")

    database = Database(
        tmp_path / "lexical-only.sqlite3", vector_extension_loader=fail_to_load
    )
    assert database.migrate() == list(range(1, 27))
    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0
    assert database.vector_extension_error == "RuntimeError"

    with pytest.raises(VectorCapabilityError, match="capability is unavailable"):
        _run(
            SQLiteVectorStore(database).search(
                (1, 0, 0), embedding_model=MODEL, limit=5, course_id=None
            )
        )


def test_missing_extension_enable_keeps_lexical_capability_failure_explicit(tmp_path):
    database = Database(
        tmp_path / "policy.sqlite3", vector_extension_loader=lambda _: None
    )

    class MissingEnableConnection:
        pass

    database._try_load_vector_extension(MissingEnableConnection())  # type: ignore[arg-type]
    assert database.vector_extension_error == "AttributeError"

    class DisableDeniedConnection:
        def __init__(self) -> None:
            self.calls: list[bool] = []
            self.closed = False

        def enable_load_extension(self, enabled: bool) -> None:
            self.calls.append(enabled)
            if not enabled:
                raise sqlite3.OperationalError("not authorized")

        def close(self) -> None:
            self.closed = True

    connection = DisableDeniedConnection()
    with pytest.raises(
        ExtensionLoadingSecurityError, match="could not be disabled safely"
    ):
        database._try_load_vector_extension(connection)  # type: ignore[arg-type]
    assert connection.calls == [True, False]
    assert connection.closed is True
    assert database.vector_extension_error == "OperationalError"


def test_non_finite_vector_distance_fails_closed(vector_database):
    store = SQLiteVectorStore(vector_database)
    _run(
        store.upsert(
            [
                VectorRecord(
                    _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",)),
                    (1, 0, 0),
                    MODEL,
                ),
                VectorRecord(
                    _chunk("chunk-a-1", "doc-a", 1, courses=("course-a",)),
                    (0.8, 0.2, 0),
                    MODEL,
                ),
            ]
        )
    )

    def load_with_invalid_distance(connection):
        import sqlite_vec

        sqlite_vec.load(connection)
        connection.create_function("vec_distance_cosine", 2, lambda _a, _b: None)

    corrupt = SQLiteVectorStore(
        Database(
            vector_database.path, vector_extension_loader=load_with_invalid_distance
        )
    )
    with pytest.raises(ValueError, match="invalid distance"):
        _run(corrupt.search((1, 0, 0), embedding_model=MODEL, limit=5, course_id=None))


def test_corrupt_vector_blob_is_rejected_by_sqlite_vec(vector_database):
    store = SQLiteVectorStore(vector_database)
    _run(
        store.upsert(
            [
                VectorRecord(
                    _chunk("chunk-a-0", "doc-a", 0, courses=("course-a",)),
                    (1, 0, 0),
                    MODEL,
                ),
                VectorRecord(
                    _chunk("chunk-a-1", "doc-a", 1, courses=("course-a",)),
                    (0.8, 0.2, 0),
                    MODEL,
                ),
            ]
        )
    )
    with vector_database.connection() as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE chunk_embeddings SET embedding = x'0001' WHERE chunk_id = 'chunk-a-0'"
        )
        connection.commit()

    with pytest.raises(sqlite3.Error):
        _run(store.search((1, 0, 0), embedding_model=MODEL, limit=5, course_id=None))
