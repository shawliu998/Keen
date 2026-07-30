from __future__ import annotations

import asyncio
import json
import sqlite3
import struct
import threading
import time
from collections.abc import Sequence
from hashlib import sha256

import pytest

import app.index_worker as worker_module
from app.database import Database
from app.document_repository import DocumentRepository
from app.index_jobs import ActiveIndexJobError, IndexJobRepository
from app.index_worker import DocumentIndexWorker
from app.local_providers import LocalProviderError
from app.retrieval_interfaces import EmbeddingModel, VectorRecord
from app.settings import LocalEmbeddingSettings, Settings


OLD_MODEL = EmbeddingModel(
    provider="ollama", model="fixture", version="old", dimensions=3
)
TARGET_MODEL = EmbeddingModel(
    provider="ollama", model="fixture", version="current", dimensions=3
)


class _Provider:
    def __init__(
        self,
        *,
        model: EmbeddingModel = TARGET_MODEL,
        fail_on_call: int | None = None,
        block_on_call: int | None = None,
    ) -> None:
        self.model = model
        self.fail_on_call = fail_on_call
        self.block_on_call = block_on_call
        self.calls = 0
        self.blocked = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()
        self.closed = False

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise LocalProviderError("fixture provider secret")
        if self.block_on_call == self.calls:
            self.blocked.set()
            try:
                while not self.release.is_set():
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        return tuple((1.0, float(index + 1), 0.25) for index, _ in enumerate(texts))

    async def embed_query(self, text: str) -> Sequence[float]:
        del text
        return (1.0, 1.0, 0.25)

    async def aclose(self) -> None:
        self.closed = True


def _model_id(model: EmbeddingModel) -> str:
    identity = "\0".join(
        (model.provider, model.model, model.version, str(model.dimensions))
    )
    return sha256(identity.encode()).hexdigest()


def _settings(tmp_path, model: EmbeddingModel = TARGET_MODEL) -> Settings:
    return Settings(
        session_token="t" * 32,
        database_path=tmp_path / "reindex.sqlite3",
        local_embedding=LocalEmbeddingSettings(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model=model.model,
            version=model.version,
            dimensions=model.dimensions,
        ),
    )


def _seed_indexed_document(database: Database, *, chunk_count: int = 33) -> str:
    database.migrate()
    document_id = "document-indexed"
    version_id = "version-indexed"
    now = "2026-07-16T00:00:00+00:00"
    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (
                id, course_id, name, mime_type, extension, status,
                page_count, chunk_count, error, created_at, updated_at
            ) VALUES (?, NULL, 'indexed.txt', 'text/plain', '.txt', 'indexed',
                      1, ?, NULL, ?, ?)
            """,
            (document_id, chunk_count, now, now),
        )
        connection.execute(
            """
            INSERT INTO document_versions (
                id, document_id, version_number, content_hash, storage_path,
                size_bytes, parser_version, page_count, created_at
            ) VALUES (?, ?, 1, ?, 'sha256/fixture.txt', 1, 'fixture', 1, ?)
            """,
            (version_id, document_id, "a" * 64, now),
        )
        for ordinal in range(chunk_count):
            content = f"durable lexical token chunk {ordinal}"
            connection.execute(
                """
                INSERT INTO document_chunks (
                    id, document_id, version_id, ordinal, page_number,
                    section_path, content, content_hash, text_location,
                    parser_version, embedding_version, created_at
                ) VALUES (?, ?, ?, ?, 1, '[]', ?, ?, ?, 'fixture', NULL, ?)
                """,
                (
                    f"chunk-{ordinal}",
                    document_id,
                    version_id,
                    ordinal,
                    content,
                    sha256(content.encode()).hexdigest(),
                    json.dumps({"unit": 0, "start": ordinal, "end": ordinal + 1}),
                    now,
                ),
            )
        old_model_id = _model_id(OLD_MODEL)
        connection.execute(
            """
            INSERT INTO embedding_models
                (id, provider, model, version, dimensions, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                old_model_id,
                OLD_MODEL.provider,
                OLD_MODEL.model,
                OLD_MODEL.version,
                OLD_MODEL.dimensions,
                now,
            ),
        )
        for ordinal in range(chunk_count):
            connection.execute(
                """
                INSERT INTO chunk_embeddings (
                    chunk_id, model_id, dimensions, embedding,
                    created_at, updated_at
                ) VALUES (?, ?, 3, ?, ?, ?)
                """,
                (
                    f"chunk-{ordinal}",
                    old_model_id,
                    struct.pack("<3f", 0.5, 0.5, 0.5),
                    now,
                    now,
                ),
            )
        connection.execute(
            """
            INSERT INTO document_embedding_state (
                document_id, model_id, status, expected_chunk_count,
                embedded_chunk_count, error, updated_at
            ) VALUES (?, ?, 'ready', ?, ?, NULL, ?)
            """,
            (document_id, old_model_id, chunk_count, chunk_count, now),
        )
        connection.commit()
    return document_id


def _create_job(
    database: Database, document_id: str, *, job_id: str = "reindex"
) -> dict:
    with database.connection() as connection:
        return IndexJobRepository(connection).create_embedding_reindex_job(
            job_id=job_id,
            document_id=document_id,
            model=TARGET_MODEL,
        )


def _wait_for_job(database: Database, job_id: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with database.connection() as connection:
            job = IndexJobRepository(connection).get_job(job_id)
        assert job is not None
        if job["status"] in {"cancelled", "completed", "failed", "interrupted"}:
            return job
        time.sleep(0.02)
    raise AssertionError("embedding reindex job did not finish")


def _start_worker(
    database: Database, settings: Settings, provider: _Provider, monkeypatch
) -> DocumentIndexWorker:
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda _: provider)
    worker = DocumentIndexWorker(database, settings, threading.Lock())
    worker.start()
    worker.notify()
    return worker


def test_reindex_stages_then_atomically_promotes_without_hiding_lexical_data(
    tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    document_id = _seed_indexed_document(database)
    _create_job(database, document_id)
    provider = _Provider(block_on_call=2)
    worker = _start_worker(database, settings, provider, monkeypatch)
    try:
        assert provider.blocked.wait(3)
        with database.connection() as connection:
            document = connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            target_live = connection.execute(
                "SELECT COUNT(*) FROM chunk_embeddings WHERE model_id = ?",
                (_model_id(TARGET_MODEL),),
            ).fetchone()[0]
            staged = connection.execute(
                "SELECT COUNT(*) FROM embedding_reindex_staging WHERE job_id = 'reindex'"
            ).fetchone()[0]
            lexical = DocumentRepository(connection).search(
                "durable lexical", course_id=None, limit=5
            )
        assert document["status"] == "indexed"
        assert target_live == 0
        assert staged == 32
        assert lexical
        provider.release.set()
        assert _wait_for_job(database, "reindex")["status"] == "completed"
    finally:
        provider.release.set()
        assert worker.stop()
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()["status"]
            == "indexed"
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            == 33
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM chunk_embeddings WHERE model_id = ?",
                (_model_id(TARGET_MODEL),),
            ).fetchone()[0]
            == 33
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM chunk_embeddings WHERE model_id = ?",
                (_model_id(OLD_MODEL),),
            ).fetchone()[0]
            == 33
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM embedding_reindex_staging"
            ).fetchone()[0]
            == 0
        )


def test_running_cancel_cleans_staging_without_failing_document(
    tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    document_id = _seed_indexed_document(database)
    _create_job(database, document_id)
    provider = _Provider(block_on_call=2)
    worker = _start_worker(database, settings, provider, monkeypatch)
    try:
        assert provider.blocked.wait(3)
        with database.connection() as connection:
            cancelled = IndexJobRepository(connection).request_cancel("reindex")
        assert cancelled is not None and cancelled["status"] == "cancel_requested"
        assert _wait_for_job(database, "reindex")["status"] == "cancelled"
        assert provider.cancelled.wait(1)
    finally:
        provider.release.set()
        assert worker.stop()
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()["status"]
            == "indexed"
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            == 33
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM embedding_reindex_staging"
            ).fetchone()[0]
            == 0
        )


def test_provider_failure_is_persistent_and_not_connected_to_full_retry(
    tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    document_id = _seed_indexed_document(database)
    _create_job(database, document_id)
    provider = _Provider(fail_on_call=2)
    worker = _start_worker(database, settings, provider, monkeypatch)
    try:
        job = _wait_for_job(database, "reindex")
    finally:
        assert worker.stop()
    assert job["status"] == "failed"
    assert "provider is unavailable" in job["error"]
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()["status"]
            == "indexed"
        )
        state = connection.execute(
            """
            SELECT status, embedded_chunk_count, error
            FROM document_embedding_state WHERE model_id = ?
            """,
            (_model_id(TARGET_MODEL),),
        ).fetchone()
        assert state["status"] == "failed"
        assert state["embedded_chunk_count"] == 0
        assert "secret" not in state["error"]
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM embedding_reindex_staging"
            ).fetchone()[0]
            == 0
        )
        with pytest.raises(ActiveIndexJobError, match="retryable indexing job"):
            IndexJobRepository(connection).create_retry_job(
                job_id="wrong-full-retry", document_id=document_id
            )


def test_queued_cancel_and_restart_interruption_preserve_indexed_document(
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    document_id = _seed_indexed_document(database, chunk_count=2)
    _create_job(database, document_id, job_id="queued")
    with database.connection() as connection:
        cancelled = IndexJobRepository(connection).request_cancel("queued")
        assert cancelled is not None and cancelled["status"] == "cancelled"
        assert (
            connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()["status"]
            == "indexed"
        )

        jobs = IndexJobRepository(connection)
        jobs.create_embedding_reindex_job(
            job_id="claimed", document_id=document_id, model=TARGET_MODEL
        )
        claimed = jobs.claim_next_job("dead-worker")
        assert claimed is not None and claimed["operation"] == "embedding_reindex"
        with pytest.raises(
            sqlite3.IntegrityError, match="model does not match reindex job"
        ):
            connection.execute(
                """
                INSERT INTO embedding_reindex_staging (
                    job_id, chunk_id, model_id, dimensions,
                    embedding, created_at
                ) VALUES ('claimed', 'chunk-0', ?, 3, ?,
                          '2026-07-16T00:00:00+00:00')
                """,
                (_model_id(OLD_MODEL), struct.pack("<3f", 1.0, 1.0, 1.0)),
            )
        connection.rollback()
        chunk = DocumentRepository(connection).chunk_metadata(document_id)[0]
        DocumentRepository(connection).stage_embedding_reindex_batch(
            job_id="claimed",
            model=TARGET_MODEL,
            records=(
                VectorRecord(
                    chunk=chunk,
                    vector=(1.0, 1.0, 0.25),
                    embedding_model=TARGET_MODEL,
                ),
            ),
        )
        assert jobs.interrupt_active_jobs("sidecar restart") == ["claimed"]
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM embedding_reindex_staging"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()["status"]
            == "indexed"
        )


def test_pinned_model_fails_closed_when_restart_configuration_changes(
    tmp_path, monkeypatch
) -> None:
    settings = _settings(
        tmp_path,
        EmbeddingModel(
            provider="ollama", model="fixture", version="changed", dimensions=3
        ),
    )
    database = Database(settings.database_path)
    document_id = _seed_indexed_document(database, chunk_count=2)
    _create_job(database, document_id)
    provider = _Provider(model=EmbeddingModel("ollama", "fixture", "changed", 3))
    worker = _start_worker(database, settings, provider, monkeypatch)
    try:
        job = _wait_for_job(database, "reindex")
    finally:
        assert worker.stop()
    assert job["status"] == "failed"
    assert "incompatible" in job["error"]
    assert provider.calls == 0
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()["status"]
            == "indexed"
        )
