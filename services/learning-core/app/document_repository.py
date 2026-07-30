from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from .documents import ParsedDocument
from .lexical_retrieval import search_lexical
from .retrieval_interfaces import (
    ChunkMetadata,
    EmbeddingModel,
    VectorRecord,
    validate_embedding,
    validate_model_compatibility,
)

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"parsing", "failed"}),
    "parsing": frozenset({"chunking", "failed"}),
    "chunking": frozenset({"indexed", "failed"}),
    "indexed": frozenset(),
    "failed": frozenset({"queued", "parsing"}),
}


class DuplicateDocumentHashError(RuntimeError):
    def __init__(self, document: dict) -> None:
        super().__init__("document content hash was claimed concurrently")
        self.document = document


class DocumentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def course_exists(self, course_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            is not None
        )

    def document_content_source(self, document_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT d.id, d.name, d.mime_type, d.extension, v.storage_path,
                   v.size_bytes
            FROM documents d
            JOIN document_versions v ON v.document_id = d.id
            WHERE d.id = ?
            ORDER BY v.version_number DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def create_document(
        self,
        *,
        document_id: str,
        version_id: str,
        course_id: str | None,
        name: str,
        mime_type: str,
        extension: str,
        content_hash: str,
        storage_path: str,
        size_bytes: int,
        parser_version: str,
        job_id: str | None = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.get_document_by_hash(content_hash)
            if existing is not None:
                self.connection.rollback()
                raise DuplicateDocumentHashError(existing)
            self.connection.execute(
                """
                INSERT INTO documents
                    (id, course_id, name, mime_type, extension, status,
                     page_count, chunk_count, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', 0, 0, NULL, ?, ?)
                """,
                (document_id, course_id, name, mime_type, extension, now, now),
            )
            self.connection.execute(
                """
                INSERT INTO document_versions
                    (id, document_id, version_number, content_hash, storage_path,
                     size_bytes, parser_version, page_count, created_at)
                VALUES (?, ?, 1, ?, ?, ?, ?, 0, ?)
                """,
                (
                    version_id,
                    document_id,
                    content_hash,
                    storage_path,
                    size_bytes,
                    parser_version,
                    now,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO document_status_events
                    (document_id, from_status, to_status, detail, occurred_at)
                VALUES (?, NULL, 'queued', NULL, ?)
                """,
                (document_id, now),
            )
            if course_id is not None:
                self.connection.execute(
                    """
                    INSERT INTO course_documents (course_id, document_id, added_at)
                    VALUES (?, ?, ?)
                    """,
                    (course_id, document_id, now),
                )
            if job_id is not None:
                self.connection.execute(
                    """
                    INSERT INTO document_index_jobs
                        (id, document_id, status, stage, progress,
                         cancel_requested, error, created_at, updated_at)
                    VALUES (?, ?, 'queued', 'stored', 10, 0, NULL, ?, ?)
                    """,
                    (job_id, document_id, now, now),
                )
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        document = self.get_document(document_id)
        if document is None:  # pragma: no cover - guarded by the inserts above
            raise RuntimeError("document insert did not persist")
        return document

    def get_document(self, document_id: str) -> dict | None:
        row = self.connection.execute(
            self._document_select() + " WHERE d.id = ?",
            (document_id,),
        ).fetchone()
        return self._document_dict(row)

    def get_document_by_hash(self, content_hash: str) -> dict | None:
        row = self.connection.execute(
            self._document_select()
            + """
              WHERE v.content_hash = ?
              ORDER BY CASE d.status WHEN 'indexed' THEN 0 ELSE 1 END,
                       d.created_at DESC, d.id
              LIMIT 1
            """,
            (content_hash,),
        ).fetchone()
        return self._document_dict(row)

    def list_documents(self, course_id: str | None = None) -> list[dict]:
        course_clause = """
            WHERE EXISTS (
                SELECT 1 FROM course_documents filtered_link
                WHERE filtered_link.document_id = d.id
                  AND filtered_link.course_id = ?
            )
        """
        query = self._document_select()
        parameters: tuple[str, ...] = ()
        if course_id is not None:
            query += course_clause
            parameters = (course_id,)
        rows = self.connection.execute(
            query + " ORDER BY d.created_at DESC, d.id", parameters
        ).fetchall()
        return [self._document_dict(row) for row in rows if row is not None]

    def link_document_course(
        self, document_id: str, course_id: str
    ) -> tuple[dict, bool]:
        now = datetime.now(UTC).isoformat()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            if (
                self.connection.execute(
                    "SELECT 1 FROM documents WHERE id = ?", (document_id,)
                ).fetchone()
                is None
            ):
                self.connection.rollback()
                raise LookupError("document not found")
            if not self.course_exists(course_id):
                self.connection.rollback()
                raise LookupError("course not found")
            linked = (
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO course_documents
                        (course_id, document_id, added_at)
                    VALUES (?, ?, ?)
                    """,
                    (course_id, document_id, now),
                ).rowcount
                == 1
            )
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        document = self.get_document(document_id)
        if document is None:  # pragma: no cover - protected by transaction above
            raise RuntimeError("linked document disappeared")
        return document, linked

    def unlink_document_course(self, document_id: str, course_id: str) -> bool:
        """Remove only membership; zero-link documents remain in the global library."""

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            if (
                self.connection.execute(
                    "SELECT 1 FROM documents WHERE id = ?", (document_id,)
                ).fetchone()
                is None
            ):
                self.connection.rollback()
                raise LookupError("document not found")
            if not self.course_exists(course_id):
                self.connection.rollback()
                raise LookupError("course not found")
            unlinked = (
                self.connection.execute(
                    """
                    DELETE FROM course_documents
                    WHERE document_id = ? AND course_id = ?
                    """,
                    (document_id, course_id),
                ).rowcount
                == 1
            )
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        return unlinked

    def recover_interrupted_imports(self) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT id, status FROM documents
            WHERE status IN ('queued', 'parsing', 'chunking')
              AND NOT EXISTS (
                  SELECT 1 FROM document_index_jobs j
                  WHERE j.document_id = documents.id
                    AND j.status IN ('queued', 'running', 'cancel_requested')
              )
            ORDER BY created_at, id
            """
        ).fetchall()
        if not rows:
            return []
        now = datetime.now(UTC).isoformat()
        detail = "indexing was interrupted by a previous shutdown; retry the import"
        with self.connection:
            for row in rows:
                self.connection.execute(
                    """
                    INSERT INTO document_index_jobs (
                        id, document_id, status, stage, progress,
                        cancel_requested, error, created_at, updated_at,
                        started_at, finished_at
                    )
                    SELECT ?, ?, 'interrupted', 'parsing', 0,
                           0, ?, ?, ?, NULL, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM document_index_jobs WHERE document_id = ?
                    )
                    """,
                    (
                        f"job-recovered-{row['id']}",
                        row["id"],
                        detail,
                        now,
                        now,
                        now,
                        row["id"],
                    ),
                )
                self.connection.execute(
                    """
                    UPDATE documents
                    SET status = 'failed', error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (detail, now, row["id"]),
                )
                self.connection.execute(
                    """
                    INSERT INTO document_status_events
                        (document_id, from_status, to_status, detail, occurred_at)
                    VALUES (?, ?, 'failed', ?, ?)
                    """,
                    (row["id"], row["status"], detail, now),
                )
        return [str(row["id"]) for row in rows]

    def storage_path_is_referenced(
        self, storage_path: str, *, excluding_document_id: str | None = None
    ) -> bool:
        query = """
            SELECT 1
            FROM document_versions v
            WHERE v.storage_path = ?
        """
        parameters: tuple[str, ...] = (storage_path,)
        if excluding_document_id is not None:
            query += " AND v.document_id <> ?"
            parameters = (storage_path, excluding_document_id)
        query += " LIMIT 1"
        return self.connection.execute(query, parameters).fetchone() is not None

    def transition_status(
        self,
        document_id: str,
        to_status: str,
        *,
        detail: str | None = None,
    ) -> dict:
        row = self.connection.execute(
            "SELECT status FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            raise LookupError("document not found")
        from_status = str(row["status"])
        if to_status not in _ALLOWED_TRANSITIONS[from_status]:
            raise ValueError(
                f"invalid document status transition: {from_status} -> {to_status}"
            )
        now = datetime.now(UTC).isoformat()
        error = detail if to_status == "failed" else None
        with self.connection:
            self.connection.execute(
                "UPDATE documents SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (to_status, error, now, document_id),
            )
            self.connection.execute(
                """
                INSERT INTO document_status_events
                    (document_id, from_status, to_status, detail, occurred_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (document_id, from_status, to_status, detail, now),
            )
        document = self.get_document(document_id)
        if document is None:  # pragma: no cover
            raise RuntimeError("document status update did not persist")
        return document

    def stage_document_chunks(
        self,
        *,
        document_id: str,
        version_id: str,
        parsed: ParsedDocument,
        cancellation_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[ChunkMetadata, ...]:
        status_row = self.connection.execute(
            "SELECT status FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if status_row is None:
            raise LookupError("document not found")
        if status_row["status"] != "chunking":
            raise ValueError("document must be in chunking state before indexing")
        now = datetime.now(UTC).isoformat()
        try:
            with self.connection:
                self.connection.execute(
                    "DELETE FROM document_chunks WHERE version_id = ?", (version_id,)
                )
            insert_sql = """
                INSERT INTO document_chunks
                    (id, document_id, version_id, ordinal, page_number, section_path,
                     content, content_hash, text_location, parser_version,
                     embedding_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """
            for batch_start in range(0, len(parsed.chunks), 64):
                batch = parsed.chunks[batch_start : batch_start + 64]
                if cancellation_check is not None and cancellation_check():
                    raise InterruptedError("indexing was cancelled")
                with self.connection:
                    self.connection.executemany(
                        insert_sql,
                        [
                            (
                                f"chunk-{version_id}-{chunk.ordinal}",
                                document_id,
                                version_id,
                                chunk.ordinal,
                                chunk.page_number,
                                json.dumps(chunk.section_path, ensure_ascii=False),
                                chunk.content,
                                chunk.content_hash,
                                json.dumps(
                                    {
                                        "unit": chunk.unit_ordinal,
                                        "start": chunk.start_character,
                                        "end": chunk.end_character,
                                    },
                                    separators=(",", ":"),
                                ),
                                parsed.parser_version,
                                now,
                            )
                            for chunk in batch
                        ],
                    )
                    geometry_rows = [
                        (
                            f"chunk-{version_id}-{chunk.ordinal}",
                            span.page_number,
                            span.original_text,
                            span.normalized_text,
                            span.block_id,
                            span.span_id,
                            span.bbox_x0,
                            span.bbox_y0,
                            span.bbox_x1,
                            span.bbox_y1,
                            span.page_width,
                            span.page_height,
                        )
                        for chunk in batch
                        for span in chunk.geometry
                    ]
                    if geometry_rows:
                        self.connection.executemany(
                            """
                            INSERT INTO document_chunk_geometry (
                                chunk_id, page_number, original_text,
                                normalized_text, block_id, span_id,
                                bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                                page_width, page_height
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            geometry_rows,
                        )
                if progress_callback is not None:
                    progress_callback(
                        min(batch_start + len(batch), len(parsed.chunks)),
                        len(parsed.chunks),
                    )
        except Exception:
            with self.connection:
                self.connection.execute(
                    "DELETE FROM document_chunks WHERE version_id = ?", (version_id,)
                )
            raise
        return self.chunk_metadata(document_id, version_id=version_id)

    def chunk_metadata(
        self, document_id: str, *, version_id: str | None = None
    ) -> tuple[ChunkMetadata, ...]:
        version_clause = " AND dc.version_id = ?" if version_id is not None else ""
        parameters: tuple[str, ...] = (
            (document_id, version_id) if version_id is not None else (document_id,)
        )
        rows = self.connection.execute(
            f"""
            SELECT dc.id, dc.document_id, d.name, dc.page_number, dc.ordinal,
                   dc.section_path, dc.content,
                   COALESCE((
                       SELECT json_group_array(course_id) FROM (
                           SELECT course_id FROM course_documents
                           WHERE document_id = dc.document_id ORDER BY course_id
                       )
                   ), '[]') AS course_ids
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE dc.document_id = ? {version_clause}
            ORDER BY dc.ordinal, dc.id
            """,
            parameters,
        ).fetchall()
        return tuple(
            ChunkMetadata(
                chunk_id=str(row["id"]),
                document_id=str(row["document_id"]),
                document_name=str(row["name"]),
                page_number=int(row["page_number"]),
                ordinal=int(row["ordinal"]),
                section_path=tuple(json.loads(row["section_path"])),
                text=str(row["content"]),
                course_ids=tuple(json.loads(row["course_ids"])),
            )
            for row in rows
        )

    def finalize_document_index(
        self,
        *,
        job_id: str,
        document_id: str,
        version_id: str,
        parsed: ParsedDocument,
    ) -> dict:
        """Atomically expose staged lexical/vector rows and complete the claimed job."""

        now = datetime.now(UTC).isoformat()
        with self.connection:
            completed = self.connection.execute(
                """
                UPDATE document_index_jobs
                SET status = 'completed', stage = 'finalizing', progress = 100,
                    cancel_requested = 0, error = NULL,
                    finished_at = ?, updated_at = ?
                WHERE id = ? AND document_id = ?
                  AND status = 'running' AND cancel_requested = 0
                """,
                (now, now, job_id, document_id),
            ).rowcount
            if completed != 1:
                raise InterruptedError("indexing was cancelled before finalization")
            self.connection.execute(
                """
                UPDATE document_versions
                SET parser_version = ?, page_count = ?
                WHERE id = ? AND document_id = ?
                """,
                (parsed.parser_version, parsed.page_count, version_id, document_id),
            )
            self.connection.execute(
                """
                UPDATE documents
                SET status = 'indexed', page_count = ?, chunk_count = ?,
                    error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (parsed.page_count, len(parsed.chunks), now, document_id),
            )
            self.connection.execute(
                """
                INSERT INTO document_status_events
                    (document_id, from_status, to_status, detail, occurred_at)
                VALUES (?, 'chunking', 'indexed', NULL, ?)
                """,
                (document_id, now),
            )
        document = self.get_document(document_id)
        if document is None:  # pragma: no cover
            raise RuntimeError("indexed document did not persist")
        return document

    def index_document(
        self,
        *,
        job_id: str,
        document_id: str,
        version_id: str,
        parsed: ParsedDocument,
        cancellation_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict:
        """Compatibility wrapper for lexical-only callers and race tests."""

        self.stage_document_chunks(
            document_id=document_id,
            version_id=version_id,
            parsed=parsed,
            cancellation_check=cancellation_check,
            progress_callback=progress_callback,
        )
        if cancellation_check is not None and cancellation_check():
            self.cleanup_staged_index(version_id)
            raise InterruptedError("indexing was cancelled")
        return self.finalize_document_index(
            job_id=job_id,
            document_id=document_id,
            version_id=version_id,
            parsed=parsed,
        )

    def cleanup_staged_index(self, version_id: str) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM document_chunks WHERE version_id = ?", (version_id,)
            )

    def record_embedding_failure(
        self, document_id: str, model: EmbeddingModel, detail: str
    ) -> None:
        model_id = self._embedding_model_id(model)
        now = datetime.now(UTC).isoformat()
        with self.connection:
            self._register_embedding_model(model_id, model, now)
            self.connection.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE model_id = ? AND chunk_id IN (
                    SELECT id FROM document_chunks WHERE document_id = ?
                )
                """,
                (model_id, document_id),
            )
            expected = int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                    (document_id,),
                ).fetchone()[0]
            )
            self.connection.execute(
                """
                INSERT INTO document_embedding_state (
                    document_id, model_id, status, expected_chunk_count,
                    embedded_chunk_count, error, updated_at
                ) VALUES (?, ?, 'failed', ?, 0, ?, ?)
                ON CONFLICT(document_id, model_id) DO UPDATE SET
                    status = 'failed', expected_chunk_count = excluded.expected_chunk_count,
                    embedded_chunk_count = 0, error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (document_id, model_id, expected, detail, now),
            )

    def stage_embedding_reindex_batch(
        self,
        *,
        job_id: str,
        model: EmbeddingModel,
        records: Sequence[VectorRecord],
    ) -> None:
        """Persist one reindex batch outside live vectors until atomic promotion."""

        if not records:
            return
        model_id = self._embedding_model_id(model)
        now = datetime.now(UTC).isoformat()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            job = self.connection.execute(
                """
                SELECT document_id, status, cancel_requested, embedding_model_id
                FROM document_index_jobs
                WHERE id = ? AND operation = 'embedding_reindex'
                """,
                (job_id,),
            ).fetchone()
            if (
                job is None
                or job["status"] != "running"
                or bool(job["cancel_requested"])
            ):
                self.connection.rollback()
                raise InterruptedError("embedding reindex was cancelled")
            if job["embedding_model_id"] != model_id:
                self.connection.rollback()
                raise ValueError("embedding reindex model does not match queued job")
            for record in records:
                validate_model_compatibility(
                    indexed=record.embedding_model, requested=model
                )
                if record.chunk.document_id != job["document_id"]:
                    raise ValueError(
                        "embedding reindex chunk does not belong to queued document"
                    )
                exists = self.connection.execute(
                    """
                    SELECT 1 FROM document_chunks
                    WHERE id = ? AND document_id = ?
                    """,
                    (record.chunk.chunk_id, job["document_id"]),
                ).fetchone()
                if exists is None:
                    raise ValueError("embedding reindex chunk no longer exists")
                vector = validate_embedding(record.vector, model=model)
                self.connection.execute(
                    """
                    INSERT INTO embedding_reindex_staging (
                        job_id, chunk_id, model_id, dimensions,
                        embedding, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, chunk_id) DO UPDATE SET
                        model_id = excluded.model_id,
                        dimensions = excluded.dimensions,
                        embedding = excluded.embedding,
                        created_at = excluded.created_at
                    """,
                    (
                        job_id,
                        record.chunk.chunk_id,
                        model_id,
                        model.dimensions,
                        struct.pack(f"<{len(vector)}f", *vector),
                        now,
                    ),
                )
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def finalize_embedding_reindex(
        self,
        *,
        job_id: str,
        document_id: str,
        model: EmbeddingModel,
    ) -> None:
        """Atomically replace only the target model after a complete staged rebuild."""

        model_id = self._embedding_model_id(model)
        now = datetime.now(UTC).isoformat()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            job = self.connection.execute(
                """
                SELECT status, cancel_requested, operation, embedding_model_id
                FROM document_index_jobs
                WHERE id = ? AND document_id = ?
                """,
                (job_id, document_id),
            ).fetchone()
            document = self.connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if (
                job is None
                or job["operation"] != "embedding_reindex"
                or job["status"] != "running"
                or bool(job["cancel_requested"])
            ):
                raise InterruptedError(
                    "embedding reindex was cancelled before finalization"
                )
            if document is None or document["status"] != "indexed":
                raise ValueError("embedding reindex document is no longer indexed")
            if job["embedding_model_id"] != model_id:
                raise ValueError("embedding reindex model does not match queued job")
            counts = self.connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM document_chunks
                     WHERE document_id = ?) AS expected,
                    (SELECT COUNT(*) FROM embedding_reindex_staging s
                     JOIN document_chunks dc ON dc.id = s.chunk_id
                     WHERE s.job_id = ? AND s.model_id = ?
                       AND dc.document_id = ?) AS staged,
                    (SELECT COUNT(*) FROM embedding_reindex_staging
                     WHERE job_id = ?) AS staged_total
                """,
                (document_id, job_id, model_id, document_id, job_id),
            ).fetchone()
            expected = int(counts["expected"])
            staged = int(counts["staged"])
            if (
                expected == 0
                or staged != expected
                or int(counts["staged_total"]) != expected
            ):
                raise ValueError("embedding reindex staging is incomplete")
            self.connection.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE model_id = ? AND chunk_id IN (
                    SELECT id FROM document_chunks WHERE document_id = ?
                )
                """,
                (model_id, document_id),
            )
            self.connection.execute(
                """
                INSERT INTO chunk_embeddings (
                    chunk_id, model_id, dimensions, embedding,
                    created_at, updated_at
                )
                SELECT chunk_id, model_id, dimensions, embedding, created_at, ?
                FROM embedding_reindex_staging
                WHERE job_id = ?
                """,
                (now, job_id),
            )
            self.connection.execute(
                """
                INSERT INTO document_embedding_state (
                    document_id, model_id, status, expected_chunk_count,
                    embedded_chunk_count, error, updated_at
                ) VALUES (?, ?, 'ready', ?, ?, NULL, ?)
                ON CONFLICT(document_id, model_id) DO UPDATE SET
                    status = 'ready',
                    expected_chunk_count = excluded.expected_chunk_count,
                    embedded_chunk_count = excluded.embedded_chunk_count,
                    error = NULL,
                    updated_at = excluded.updated_at
                """,
                (document_id, model_id, expected, expected, now),
            )
            completed = self.connection.execute(
                """
                UPDATE document_index_jobs
                SET status = 'completed', stage = 'finalizing', progress = 100,
                    cancel_requested = 0, error = NULL,
                    finished_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running' AND cancel_requested = 0
                """,
                (now, now, job_id),
            ).rowcount
            if completed != 1:
                raise InterruptedError(
                    "embedding reindex was cancelled before finalization"
                )
            self.connection.execute(
                "DELETE FROM embedding_reindex_staging WHERE job_id = ?",
                (job_id,),
            )
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def record_embedding_reindex_failure(
        self,
        *,
        job_id: str,
        document_id: str,
        model: EmbeddingModel,
        detail: str,
    ) -> None:
        """Record target failure while retaining live chunks and prior vectors."""

        model_id = self._embedding_model_id(model)
        now = datetime.now(UTC).isoformat()
        with self.connection:
            self._register_embedding_model(model_id, model, now)
            self.connection.execute(
                "DELETE FROM embedding_reindex_staging WHERE job_id = ?", (job_id,)
            )
            expected = int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                    (document_id,),
                ).fetchone()[0]
            )
            retained = int(
                self.connection.execute(
                    """
                    SELECT COUNT(*) FROM chunk_embeddings
                    WHERE model_id = ? AND chunk_id IN (
                        SELECT id FROM document_chunks WHERE document_id = ?
                    )
                    """,
                    (model_id, document_id),
                ).fetchone()[0]
            )
            self.connection.execute(
                """
                INSERT INTO document_embedding_state (
                    document_id, model_id, status, expected_chunk_count,
                    embedded_chunk_count, error, updated_at
                ) VALUES (?, ?, 'failed', ?, ?, ?, ?)
                ON CONFLICT(document_id, model_id) DO UPDATE SET
                    status = 'failed',
                    expected_chunk_count = excluded.expected_chunk_count,
                    embedded_chunk_count = excluded.embedded_chunk_count,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (document_id, model_id, expected, retained, detail, now),
            )

    def embedding_reindex_required(
        self, document_id: str, model: EmbeddingModel
    ) -> bool:
        row = self.connection.execute(
            """
            SELECT des.status, des.expected_chunk_count, des.embedded_chunk_count,
                   (SELECT COUNT(*) FROM document_chunks dc
                    WHERE dc.document_id = des.document_id) AS actual_chunk_count,
                   (SELECT COUNT(*) FROM chunk_embeddings ce
                    JOIN document_chunks dc ON dc.id = ce.chunk_id
                    WHERE dc.document_id = des.document_id
                      AND ce.model_id = des.model_id) AS actual_vector_count
            FROM document_embedding_state des
            WHERE des.document_id = ? AND des.model_id = ?
            """,
            (document_id, self._embedding_model_id(model)),
        ).fetchone()
        return row is None or not (
            row["status"] == "ready"
            and int(row["expected_chunk_count"]) == int(row["actual_chunk_count"])
            and int(row["embedded_chunk_count"]) == int(row["actual_chunk_count"])
            and int(row["actual_vector_count"]) == int(row["actual_chunk_count"])
        )

    def _register_embedding_model(
        self, model_id: str, model: EmbeddingModel, now: str
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO embedding_models
                (id, provider, model, version, dimensions, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                model_id,
                model.provider,
                model.model,
                model.version,
                model.dimensions,
                now,
            ),
        )

    @staticmethod
    def _embedding_model_id(model: EmbeddingModel) -> str:
        identity = "\0".join(
            (model.provider, model.model, model.version, str(model.dimensions))
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def search(self, query: str, *, course_id: str | None, limit: int) -> list[dict]:
        return search_lexical(
            self.connection,
            query,
            course_id=course_id,
            limit=limit,
        )

    @staticmethod
    def _document_select() -> str:
        return """
            SELECT d.id, d.course_id, d.name, d.mime_type, d.status,
                   d.page_count, d.chunk_count, d.error, d.created_at,
                   v.size_bytes, v.content_hash, v.parser_version AS parser,
                   COALESCE((
                       SELECT json_group_array(ordered_links.course_id)
                       FROM (
                           SELECT cd.course_id
                           FROM course_documents cd
                           WHERE cd.document_id = d.id
                           ORDER BY cd.course_id
                       ) AS ordered_links
                   ), '[]') AS course_ids
            FROM documents d
            JOIN document_versions v ON v.document_id = d.id
            AND v.version_number = (
                SELECT MAX(latest.version_number)
                FROM document_versions latest
                WHERE latest.document_id = d.id
            )
        """

    @staticmethod
    def _document_dict(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "mime_type": row["mime_type"],
            "size_bytes": int(row["size_bytes"]),
            "content_hash": row["content_hash"],
            "status": row["status"],
            "page_count": int(row["page_count"]),
            "chunk_count": int(row["chunk_count"]),
            "parser": row["parser"],
            "created_at": row["created_at"],
            "error": row["error"],
            "course_id": row["course_id"],
            "course_ids": json.loads(row["course_ids"]),
        }
