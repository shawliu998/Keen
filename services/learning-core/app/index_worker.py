from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import uuid
from collections.abc import Awaitable, Sequence
from typing import Any

from .database import Database, VectorCapabilityError
from .document_repository import DocumentRepository
from .documents import (
    DocumentLimits,
    DocumentParseError,
    DocumentProcessingCancelled,
    parse_document,
    resolve_stored_document_path,
)
from .index_jobs import IndexJobRepository
from .local_providers import (
    LocalProviderError,
    LocalProviderTimeouts,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from .retrieval_interfaces import (
    ChunkMetadata,
    EmbeddingModel,
    EmbeddingProvider,
    VectorRecord,
    validate_model_compatibility,
)
from .settings import LocalEmbeddingSettings, Settings
from .sqlite_vector_store import SQLiteVectorStore

logger = logging.getLogger("keen.learning_core.index_worker")

_EMBEDDING_BATCH_SIZE = 32


def create_embedding_provider(
    configuration: LocalEmbeddingSettings,
) -> EmbeddingProvider:
    timeouts = LocalProviderTimeouts(
        connect=configuration.connect_timeout_seconds,
        read=configuration.read_timeout_seconds,
        write=configuration.write_timeout_seconds,
        pool=configuration.pool_timeout_seconds,
    )
    provider_type = (
        OllamaEmbeddingProvider
        if configuration.provider == "ollama"
        else OpenAICompatibleEmbeddingProvider
    )
    return provider_type(
        base_url=configuration.base_url,
        model=configuration.model,
        version=configuration.version,
        dimensions=configuration.dimensions,
        timeouts=timeouts,
    )


class DocumentIndexWorker:
    """One persistent-queue consumer for heavyweight local document indexing."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        processing_lock: threading.Lock,
    ) -> None:
        self.database = database
        self.settings = settings
        self.processing_lock = processing_lock
        self.generation = f"worker-{uuid.uuid4().hex}"
        self._stopping = threading.Event()
        self._wake = threading.Event()
        self._run_gate = threading.Event()
        self._run_gate.set()
        self._thread = threading.Thread(
            target=self._run,
            name="keen-document-index-worker",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 8.0) -> bool:
        self._stopping.set()
        self._run_gate.set()
        self._wake.set()
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def pause_for_test(self) -> None:
        self._run_gate.clear()

    def resume_for_test(self) -> None:
        self._run_gate.set()
        self.notify()

    def _run(self) -> None:
        while not self._stopping.is_set():
            if not self._run_gate.wait(timeout=0.1):
                continue
            if self._stopping.is_set():
                break
            with self.database.connection() as connection:
                job = IndexJobRepository(connection).claim_next_job(self.generation)
            if job is None:
                self._wake.wait(timeout=0.25)
                self._wake.clear()
                continue
            self._process(job)

    def _process(self, job: dict) -> None:
        job_id = str(job["id"])
        document_id = str(job["document_id"])
        if job["operation"] == "embedding_reindex":
            with self.processing_lock:
                self._process_embedding_reindex(job)
            return
        with self.processing_lock:
            try:
                self._raise_if_stopping_or_cancelled(job_id)
                with self.database.connection() as connection:
                    work_item = IndexJobRepository(connection).work_item(document_id)
                if work_item is None:
                    raise DocumentParseError("document source metadata is missing")
                stored_path = resolve_stored_document_path(
                    self.settings.document_data_path, str(work_item["storage_path"])
                )
                limits = DocumentLimits(
                    max_pdf_pages=self.settings.max_pdf_pages,
                    max_extracted_characters=self.settings.max_extracted_characters,
                    max_document_chunks=self.settings.max_document_chunks,
                    pdf_max_rss_bytes=self.settings.pdf_max_rss_bytes,
                    pdf_no_progress_timeout_seconds=(
                        self.settings.pdf_no_progress_timeout_seconds
                    ),
                    pdf_total_timeout_seconds=self.settings.pdf_total_timeout_seconds,
                )
                parsed = parse_document(
                    stored_path,
                    str(work_item["extension"]),
                    limits=limits,
                    progress_callback=lambda stage, completed, total: (
                        self._parse_progress(job_id, stage, completed, total)
                    ),
                    cancellation_check=lambda: self._is_stopping_or_cancelled(job_id),
                )
                self._raise_if_stopping_or_cancelled(job_id)
                with self.database.connection() as connection:
                    jobs = IndexJobRepository(connection)
                    if not jobs.update_progress(job_id, stage="chunking", progress=65):
                        raise DocumentProcessingCancelled("indexing was cancelled")
                    DocumentRepository(connection).transition_status(
                        document_id, "chunking"
                    )
                    if not jobs.update_progress(
                        job_id, stage="lexical_indexing", progress=75
                    ):
                        raise DocumentProcessingCancelled("indexing was cancelled")
                    chunks = DocumentRepository(connection).stage_document_chunks(
                        document_id=document_id,
                        version_id=str(work_item["version_id"]),
                        parsed=parsed,
                        cancellation_check=lambda: self._is_stopping_or_cancelled(
                            job_id
                        ),
                        progress_callback=lambda completed, total: self._index_progress(
                            job_id, completed, total
                        ),
                    )
                self._raise_if_stopping_or_cancelled(job_id)
                self._embed_if_configured(
                    job_id=job_id,
                    document_id=document_id,
                    chunks=chunks,
                )
                self._raise_if_stopping_or_cancelled(job_id)
                with self.database.connection() as connection:
                    DocumentRepository(connection).finalize_document_index(
                        job_id=job_id,
                        document_id=document_id,
                        version_id=str(work_item["version_id"]),
                        parsed=parsed,
                    )
                logger.info(
                    "document_index_job_completed",
                    extra={
                        "document_id": document_id,
                        "job_id": job_id,
                        "page_count": parsed.page_count,
                        "chunk_count": len(parsed.chunks),
                    },
                )
            except (DocumentProcessingCancelled, InterruptedError):
                detail = (
                    "indexing was interrupted by sidecar shutdown; retry the document"
                    if self._stopping.is_set()
                    else "indexing was cancelled by the user"
                )
                with self.database.connection() as connection:
                    if "work_item" in locals() and work_item is not None:
                        DocumentRepository(connection).cleanup_staged_index(
                            str(work_item["version_id"])
                        )
                    jobs = IndexJobRepository(connection)
                    if self._stopping.is_set():
                        jobs.mark_interrupted(job_id, detail)
                    else:
                        jobs.mark_cancelled(job_id, detail)
            except DocumentParseError as error:
                with self.database.connection() as connection:
                    if "work_item" in locals() and work_item is not None:
                        DocumentRepository(connection).cleanup_staged_index(
                            str(work_item["version_id"])
                        )
                    IndexJobRepository(connection).mark_failed(job_id, str(error))
                logger.info(
                    "document_index_job_failed",
                    extra={"document_id": document_id, "job_id": job_id},
                )
            except Exception:
                with self.database.connection() as connection:
                    if "work_item" in locals() and work_item is not None:
                        DocumentRepository(connection).cleanup_staged_index(
                            str(work_item["version_id"])
                        )
                    IndexJobRepository(connection).mark_failed(
                        job_id, "unexpected indexing failure"
                    )
                logger.exception(
                    "document_index_job_unexpected_failure",
                    extra={"document_id": document_id, "job_id": job_id},
                )

    def _process_embedding_reindex(self, job: dict) -> None:
        job_id = str(job["id"])
        document_id = str(job["document_id"])
        target_model: EmbeddingModel | None = None
        try:
            self._raise_if_stopping_or_cancelled(job_id)
            with self.database.connection() as connection:
                jobs = IndexJobRepository(connection)
                target_model = jobs.target_embedding_model(job_id)
                if target_model is None:
                    raise ValueError("embedding reindex target model is missing")
                if not jobs.update_progress(job_id, stage="embedding", progress=2):
                    raise DocumentProcessingCancelled("embedding reindex was cancelled")
                self.database.require_vector_extension(connection)
                chunks = DocumentRepository(connection).chunk_metadata(document_id)
            if not chunks:
                raise ValueError("embedding reindex document has no indexed chunks")
            configuration = self.settings.local_embedding
            if configuration is None:
                raise LocalProviderError("local embedding provider is not configured")
            configured_model = EmbeddingModel(
                provider=configuration.provider,
                model=configuration.model,
                version=configuration.version,
                dimensions=configuration.dimensions,
            )
            validate_model_compatibility(
                indexed=configured_model, requested=target_model
            )
            provider = create_embedding_provider(configuration)
            try:
                validate_model_compatibility(
                    indexed=provider.model, requested=target_model
                )
            except ValueError:
                close = getattr(provider, "aclose", None)
                if close is not None:
                    asyncio.run(close())
                raise
            asyncio.run(
                self._embed_chunks_for_reindex(
                    job_id=job_id,
                    chunks=chunks,
                    provider=provider,
                    target_model=target_model,
                )
            )
            self._raise_if_stopping_or_cancelled(job_id)
            with self.database.connection() as connection:
                DocumentRepository(connection).finalize_embedding_reindex(
                    job_id=job_id,
                    document_id=document_id,
                    model=target_model,
                )
            logger.info(
                "document_embedding_reindex_completed",
                extra={"document_id": document_id, "job_id": job_id},
            )
        except (DocumentProcessingCancelled, InterruptedError):
            detail = (
                "embedding reindex was interrupted by sidecar shutdown"
                if self._stopping.is_set()
                else "embedding reindex was cancelled by the user"
            )
            with self.database.connection() as connection:
                jobs = IndexJobRepository(connection)
                if self._stopping.is_set():
                    jobs.mark_interrupted(job_id, detail)
                else:
                    jobs.mark_cancelled(job_id, detail)
        except (LocalProviderError, VectorCapabilityError, ValueError) as error:
            detail = self._safe_embedding_reindex_failure(error)
            with self.database.connection() as connection:
                if target_model is not None:
                    DocumentRepository(connection).record_embedding_reindex_failure(
                        job_id=job_id,
                        document_id=document_id,
                        model=target_model,
                        detail=detail,
                    )
                IndexJobRepository(connection).mark_failed(job_id, detail)
            logger.info(
                "document_embedding_reindex_failed",
                extra={"document_id": document_id, "job_id": job_id},
            )
        except Exception:
            detail = (
                "unexpected embedding reindex failure; existing lexical index retained"
            )
            with self.database.connection() as connection:
                if target_model is not None:
                    DocumentRepository(connection).record_embedding_reindex_failure(
                        job_id=job_id,
                        document_id=document_id,
                        model=target_model,
                        detail=detail,
                    )
                IndexJobRepository(connection).mark_failed(job_id, detail)
            logger.exception(
                "document_embedding_reindex_unexpected_failure",
                extra={"document_id": document_id, "job_id": job_id},
            )

    def _parse_progress(
        self, job_id: str, stage: str, completed: int, total: int
    ) -> None:
        if stage == "parsing":
            progress = 15 + round(35 * completed / max(1, total))
        else:
            progress = 50 + round(15 * completed / max(1, total))
        with self.database.connection() as connection:
            updated = IndexJobRepository(connection).update_progress(
                job_id, stage=stage, progress=progress
            )
        if not updated:
            raise DocumentProcessingCancelled("indexing was cancelled")

    def _index_progress(self, job_id: str, completed: int, total: int) -> None:
        progress = 75 + round(10 * completed / max(1, total))
        with self.database.connection() as connection:
            updated = IndexJobRepository(connection).update_progress(
                job_id, stage="lexical_indexing", progress=progress
            )
        if not updated:
            raise InterruptedError("indexing was cancelled")

    def _embed_if_configured(
        self,
        *,
        job_id: str,
        document_id: str,
        chunks: Sequence[ChunkMetadata],
    ) -> None:
        configuration = self.settings.local_embedding
        if configuration is None:
            return
        provider: EmbeddingProvider | None = None
        try:
            provider = create_embedding_provider(configuration)
            asyncio.run(
                self._embed_chunks(
                    job_id=job_id,
                    chunks=chunks,
                    provider=provider,
                )
            )
        except (DocumentProcessingCancelled, InterruptedError):
            raise
        except (LocalProviderError, VectorCapabilityError, ValueError) as error:
            detail = self._safe_embedding_failure(error)
            model = (
                provider.model
                if provider is not None
                else EmbeddingModel(
                    provider=configuration.provider,
                    model=configuration.model,
                    version=configuration.version,
                    dimensions=configuration.dimensions,
                )
            )
            with self.database.connection() as connection:
                DocumentRepository(connection).record_embedding_failure(
                    document_id, model, detail
                )
            logger.info(
                "document_embedding_unavailable_lexical_index_retained",
                extra={"document_id": document_id, "job_id": job_id},
            )

    async def _embed_chunks(
        self,
        *,
        job_id: str,
        chunks: Sequence[ChunkMetadata],
        provider: EmbeddingProvider,
    ) -> None:
        store = SQLiteVectorStore(self.database)
        close = getattr(provider, "aclose", None)
        try:
            for batch_start in range(0, len(chunks), _EMBEDDING_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + _EMBEDDING_BATCH_SIZE]
                vectors = await self._await_embedding_or_cancel(
                    provider.embed_documents(tuple(chunk.text for chunk in batch)),
                    job_id,
                )
                if len(vectors) != len(batch):
                    raise ValueError(
                        "embedding provider returned an unexpected vector count"
                    )
                await store.upsert(
                    tuple(
                        VectorRecord(
                            chunk=chunk,
                            vector=tuple(vector),
                            embedding_model=provider.model,
                        )
                        for chunk, vector in zip(batch, vectors, strict=True)
                    )
                )
                completed = min(batch_start + len(batch), len(chunks))
                with self.database.connection() as connection:
                    updated = IndexJobRepository(connection).update_progress(
                        job_id,
                        stage="embedding",
                        progress=85 + round(13 * completed / max(1, len(chunks))),
                    )
                if not updated:
                    raise DocumentProcessingCancelled("indexing was cancelled")
        finally:
            if close is not None:
                await close()

    async def _embed_chunks_for_reindex(
        self,
        *,
        job_id: str,
        chunks: Sequence[ChunkMetadata],
        provider: EmbeddingProvider,
        target_model: EmbeddingModel,
    ) -> None:
        close = getattr(provider, "aclose", None)
        try:
            for batch_start in range(0, len(chunks), _EMBEDDING_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + _EMBEDDING_BATCH_SIZE]
                vectors = await self._await_embedding_or_cancel(
                    provider.embed_documents(tuple(chunk.text for chunk in batch)),
                    job_id,
                )
                if len(vectors) != len(batch):
                    raise ValueError(
                        "embedding provider returned an unexpected vector count"
                    )
                records = tuple(
                    VectorRecord(
                        chunk=chunk,
                        vector=tuple(vector),
                        embedding_model=target_model,
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                )
                with self.database.connection() as connection:
                    repository = DocumentRepository(connection)
                    repository.stage_embedding_reindex_batch(
                        job_id=job_id,
                        model=target_model,
                        records=records,
                    )
                    completed = min(batch_start + len(batch), len(chunks))
                    updated = IndexJobRepository(connection).update_progress(
                        job_id,
                        stage="embedding",
                        progress=2 + round(96 * completed / max(1, len(chunks))),
                    )
                if not updated:
                    raise DocumentProcessingCancelled("embedding reindex was cancelled")
        finally:
            if close is not None:
                await close()

    async def _await_embedding_or_cancel(
        self, operation: Awaitable[Any], job_id: str
    ) -> Any:
        task = asyncio.ensure_future(operation)
        while True:
            done, _ = await asyncio.wait((task,), timeout=0.05)
            if done:
                return task.result()
            if self._is_stopping_or_cancelled(job_id):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                raise DocumentProcessingCancelled("indexing was cancelled")

    @staticmethod
    def _safe_embedding_failure(error: Exception) -> str:
        if isinstance(error, VectorCapabilityError):
            return "local vector storage is unavailable; lexical indexing completed"
        if isinstance(error, LocalProviderError):
            return "local embedding provider is unavailable; lexical indexing completed"
        return "local embedding response is incompatible; lexical indexing completed"

    @staticmethod
    def _safe_embedding_reindex_failure(error: Exception) -> str:
        if isinstance(error, VectorCapabilityError):
            return (
                "local vector storage is unavailable; existing lexical index retained"
            )
        if isinstance(error, LocalProviderError):
            return "local embedding provider is unavailable; existing lexical index retained"
        return (
            "local embedding response is incompatible; existing lexical index retained"
        )

    def _is_stopping_or_cancelled(self, job_id: str) -> bool:
        if self._stopping.is_set():
            return True
        with self.database.connection() as connection:
            return IndexJobRepository(connection).cancellation_requested(job_id)

    def _raise_if_stopping_or_cancelled(self, job_id: str) -> None:
        if self._is_stopping_or_cancelled(job_id):
            raise DocumentProcessingCancelled("indexing was cancelled")
