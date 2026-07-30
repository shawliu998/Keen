from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import UTC, datetime

from .retrieval_interfaces import EmbeddingModel


ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "cancel_requested"})
RETRYABLE_JOB_STATUSES = frozenset({"cancelled", "failed", "interrupted"})
TERMINAL_JOB_STATUSES = frozenset({"cancelled", "completed", "failed", "interrupted"})


class ActiveIndexJobError(RuntimeError):
    pass


class IndexJobRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_job(
        self,
        *,
        job_id: str,
        document_id: str,
        stage: str = "stored",
        progress: int = 10,
    ) -> dict:
        now = _now()
        try:
            self.connection.execute(
                """
                INSERT INTO document_index_jobs
                    (id, document_id, status, stage, progress,
                     cancel_requested, error, created_at, updated_at)
                VALUES (?, ?, 'queued', ?, ?, 0, NULL, ?, ?)
                """,
                (job_id, document_id, stage, progress, now, now),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise ActiveIndexJobError(
                "document already has an active indexing job"
            ) from error
        job = self.get_job(job_id)
        if job is None:  # pragma: no cover - guarded by insert
            raise RuntimeError("index job insert did not persist")
        return job

    def create_retry_job(self, *, job_id: str, document_id: str) -> dict:
        latest = self.latest_job_for_document(document_id)
        if (
            latest is None
            or latest["operation"] != "full_index"
            or latest["status"] not in RETRYABLE_JOB_STATUSES
        ):
            raise ActiveIndexJobError("document does not have a retryable indexing job")
        now = _now()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            document = self.connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if document is None:
                self.connection.rollback()
                raise LookupError("document not found")
            if document["status"] != "failed":
                self.connection.rollback()
                raise ActiveIndexJobError("document is not in a retryable state")
            self.connection.execute(
                """
                INSERT INTO document_index_jobs
                    (id, document_id, status, stage, progress,
                     cancel_requested, error, created_at, updated_at)
                VALUES (?, ?, 'queued', 'stored', 10, 0, NULL, ?, ?)
                """,
                (job_id, document_id, now, now),
            )
            self.connection.execute(
                """
                UPDATE documents
                SET status = 'queued', error = NULL, page_count = 0,
                    chunk_count = 0, updated_at = ?
                WHERE id = ?
                """,
                (now, document_id),
            )
            self.connection.execute(
                """
                INSERT INTO document_status_events
                    (document_id, from_status, to_status, detail, occurred_at)
                VALUES (?, 'failed', 'queued', 'indexing retry requested', ?)
                """,
                (document_id, now),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise ActiveIndexJobError(
                "document already has an active indexing job"
            ) from error
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        job = self.get_job(job_id)
        if job is None:  # pragma: no cover
            raise RuntimeError("retry job insert did not persist")
        return job

    def create_embedding_reindex_job(
        self,
        *,
        job_id: str,
        document_id: str,
        model: EmbeddingModel,
    ) -> dict:
        """Queue a model-pinned vector rebuild without changing document state."""

        now = _now()
        model_id = _embedding_model_id(model)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            document = self.connection.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if document is None:
                self.connection.rollback()
                raise LookupError("document not found")
            if document["status"] != "indexed":
                self.connection.rollback()
                raise ActiveIndexJobError(
                    "embedding reindex requires an indexed document"
                )
            chunk_count = int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                    (document_id,),
                ).fetchone()[0]
            )
            if chunk_count == 0:
                self.connection.rollback()
                raise ActiveIndexJobError(
                    "embedding reindex requires indexed document chunks"
                )
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
            registered = self.connection.execute(
                "SELECT * FROM embedding_models WHERE id = ?", (model_id,)
            ).fetchone()
            if registered is None or any(
                registered[field] != getattr(model, field)
                for field in ("provider", "model", "version", "dimensions")
            ):
                raise ValueError("embedding model registry identity conflict")
            self.connection.execute(
                """
                INSERT INTO document_index_jobs (
                    id, document_id, status, stage, progress,
                    cancel_requested, error, created_at, updated_at,
                    operation, embedding_model_id
                ) VALUES (?, ?, 'queued', 'embedding', 0,
                          0, NULL, ?, ?, 'embedding_reindex', ?)
                """,
                (job_id, document_id, now, now, model_id),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise ActiveIndexJobError(
                "document already has an active indexing job"
            ) from error
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        job = self.get_job(job_id)
        if job is None:  # pragma: no cover
            raise RuntimeError("embedding reindex job insert did not persist")
        return job

    def get_job(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM document_index_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return self._job_dict(row)

    def latest_job_for_document(self, document_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT * FROM document_index_jobs
            WHERE document_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        return self._job_dict(row)

    def list_jobs(self, document_id: str | None = None) -> list[dict]:
        if document_id is None:
            rows = self.connection.execute(
                """
                SELECT * FROM document_index_jobs
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT * FROM document_index_jobs
                WHERE document_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (document_id,),
            ).fetchall()
        return [self._job_dict(row) for row in rows if row is not None]

    def claim_next_job(self, worker_generation: str) -> dict | None:
        now = _now()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                """
                SELECT id, document_id, operation FROM document_index_jobs
                WHERE status = 'queued'
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                self.connection.rollback()
                return None
            updated = self.connection.execute(
                """
                UPDATE document_index_jobs
                SET status = 'running',
                    stage = CASE operation
                        WHEN 'embedding_reindex' THEN 'embedding'
                        ELSE 'parsing' END,
                    progress = CASE operation
                        WHEN 'embedding_reindex' THEN 1
                        ELSE 15 END,
                    worker_generation = ?, started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (worker_generation, now, now, row["id"]),
            ).rowcount
            if updated != 1:
                self.connection.rollback()
                return None
            document = self.connection.execute(
                "SELECT status FROM documents WHERE id = ?", (row["document_id"],)
            ).fetchone()
            if document is None:
                self.connection.execute(
                    """
                    UPDATE document_index_jobs
                    SET status = 'failed', error = 'document no longer exists',
                        finished_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, row["id"]),
                )
                self.connection.commit()
                return None
            operation = str(row["operation"])
            from_status = str(document["status"])
            if operation == "embedding_reindex" and from_status != "indexed":
                self.connection.execute(
                    """
                    UPDATE document_index_jobs
                    SET status = 'failed',
                        error = 'embedding reindex requires an indexed document',
                        finished_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, row["id"]),
                )
                self.connection.commit()
                return None
            if operation == "full_index" and from_status != "parsing":
                self.connection.execute(
                    """
                    UPDATE documents
                    SET status = 'parsing', error = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, row["document_id"]),
                )
                self.connection.execute(
                    """
                    INSERT INTO document_status_events
                        (document_id, from_status, to_status, detail, occurred_at)
                    VALUES (?, ?, 'parsing', NULL, ?)
                    """,
                    (row["document_id"], from_status, now),
                )
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        return self.get_job(str(row["id"]))

    def update_progress(self, job_id: str, *, stage: str, progress: int) -> bool:
        now = _now()
        updated = self.connection.execute(
            """
            UPDATE document_index_jobs
            SET stage = ?, progress = MAX(progress, ?), updated_at = ?
            WHERE id = ? AND status = 'running' AND cancel_requested = 0
            """,
            (stage, progress, now, job_id),
        ).rowcount
        self.connection.commit()
        return updated == 1

    def cancellation_requested(self, job_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT status, cancel_requested FROM document_index_jobs WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
        return (
            row is None
            or bool(row["cancel_requested"])
            or row["status"]
            in {
                "cancelled",
                "interrupted",
            }
        )

    def request_cancel(self, job_id: str) -> dict | None:
        now = _now()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                """
                SELECT status, document_id, operation
                FROM document_index_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                self.connection.rollback()
                return None
            status = str(row["status"])
            if status in TERMINAL_JOB_STATUSES:
                self.connection.rollback()
                return self.get_job(job_id)
            if status == "queued":
                detail = (
                    "embedding reindex was cancelled before it started"
                    if row["operation"] == "embedding_reindex"
                    else "indexing was cancelled before it started"
                )
                transitioned = self.connection.execute(
                    """
                    UPDATE document_index_jobs
                    SET status = 'cancelled', cancel_requested = 1,
                        error = ?, finished_at = ?, updated_at = ?
                    WHERE id = ? AND status = 'queued'
                    """,
                    (detail, now, now, job_id),
                ).rowcount
                if transitioned == 1 and row["operation"] == "full_index":
                    self._fail_document(str(row["document_id"]), detail, now)
            else:
                self.connection.execute(
                    """
                    UPDATE document_index_jobs
                    SET status = 'cancel_requested', cancel_requested = 1,
                        updated_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
                    (now, job_id),
                )
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        return self.get_job(job_id)

    def mark_cancelled(self, job_id: str, detail: str) -> None:
        self._finish_unsuccessful(job_id, "cancelled", detail)

    def mark_interrupted(self, job_id: str, detail: str) -> None:
        self._finish_unsuccessful(job_id, "interrupted", detail)

    def mark_failed(self, job_id: str, detail: str) -> None:
        self._finish_unsuccessful(job_id, "failed", detail)

    def interrupt_active_jobs(self, detail: str) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT id FROM document_index_jobs
            WHERE status IN ('running', 'cancel_requested')
            ORDER BY created_at, id
            """
        ).fetchall()
        for row in rows:
            self.mark_interrupted(str(row["id"]), detail)
        return [str(row["id"]) for row in rows]

    def work_item(self, document_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT d.id AS document_id, d.extension, v.id AS version_id,
                   v.storage_path, v.content_hash
            FROM documents d
            JOIN document_versions v ON v.document_id = d.id
            WHERE d.id = ?
            ORDER BY v.version_number DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def target_embedding_model(self, job_id: str) -> EmbeddingModel | None:
        row = self.connection.execute(
            """
            SELECT em.provider, em.model, em.version, em.dimensions
            FROM document_index_jobs j
            JOIN embedding_models em ON em.id = j.embedding_model_id
            WHERE j.id = ? AND j.operation = 'embedding_reindex'
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return EmbeddingModel(
            provider=str(row["provider"]),
            model=str(row["model"]),
            version=str(row["version"]),
            dimensions=int(row["dimensions"]),
        )

    def referenced_storage_paths(self) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT v.document_id, v.storage_path, v.content_hash, d.status
            FROM document_versions v
            JOIN documents d ON d.id = v.document_id
            ORDER BY v.document_id, v.version_number
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def duplicate_hashes(self) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT content_hash, COUNT(DISTINCT document_id) AS document_count
            FROM document_versions
            GROUP BY content_hash
            HAVING COUNT(DISTINCT document_id) > 1
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_missing_storage(self, document_id: str, storage_path: str) -> None:
        detail = f"stored source is missing: {storage_path}"
        now = _now()
        jobs = self.connection.execute(
            """
            SELECT id FROM document_index_jobs
            WHERE document_id = ? AND operation = 'full_index'
              AND status IN ('queued', 'running', 'cancel_requested')
            """,
            (document_id,),
        ).fetchall()
        active_embedding_job = self.connection.execute(
            """
            SELECT 1 FROM document_index_jobs
            WHERE document_id = ? AND operation = 'embedding_reindex'
              AND status IN ('queued', 'running', 'cancel_requested')
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        if not jobs and active_embedding_job is not None:
            return
        if not jobs:
            self.connection.execute(
                """
                INSERT INTO document_index_jobs (
                    id, document_id, status, stage, progress,
                    cancel_requested, error, created_at, updated_at,
                    started_at, finished_at
                ) VALUES (?, ?, 'failed', 'stored', 0, 0, ?, ?, ?, NULL, ?)
                """,
                (
                    f"job-storage-missing-{uuid.uuid4().hex}",
                    document_id,
                    detail,
                    now,
                    now,
                    now,
                ),
            )
        for row in jobs:
            self.connection.execute(
                """
                UPDATE document_index_jobs
                SET status = 'failed', error = ?, finished_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (detail, now, now, row["id"]),
            )
        self._fail_document(document_id, detail, now)
        self.connection.commit()

    def removable_storage_paths(self, document_id: str) -> list[str] | None:
        exists = self.connection.execute(
            "SELECT 1 FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if exists is None:
            return None
        rows = self.connection.execute(
            "SELECT storage_path FROM document_versions WHERE document_id = ?",
            (document_id,),
        ).fetchall()
        removable: list[str] = []
        for row in rows:
            storage_path = str(row["storage_path"])
            referenced_elsewhere = self.connection.execute(
                """
                SELECT 1 FROM document_versions
                WHERE storage_path = ? AND document_id <> ? LIMIT 1
                """,
                (storage_path, document_id),
            ).fetchone()
            if referenced_elsewhere is None:
                removable.append(storage_path)
        return removable

    def delete_document_record(self, document_id: str) -> bool:
        with self.connection:
            deleted = self.connection.execute(
                "DELETE FROM documents WHERE id = ?", (document_id,)
            ).rowcount
        return deleted == 1

    def _finish_unsuccessful(self, job_id: str, status: str, detail: str) -> None:
        now = _now()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                """
                SELECT document_id, status, operation
                FROM document_index_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None or row["status"] not in ACTIVE_JOB_STATUSES:
                self.connection.rollback()
                return
            effective_status = status
            effective_detail = detail
            if row["operation"] == "embedding_reindex" and status == "interrupted":
                effective_detail = (
                    "embedding reindex was interrupted by sidecar shutdown; "
                    "existing lexical index retained"
                )
            if row["status"] == "cancel_requested" and status == "failed":
                effective_status = "cancelled"
                effective_detail = (
                    "embedding reindex was cancelled by the user"
                    if row["operation"] == "embedding_reindex"
                    else "indexing was cancelled by the user"
                )
            transitioned = self.connection.execute(
                """
                UPDATE document_index_jobs
                SET status = ?,
                    cancel_requested = CASE
                        WHEN ? = 'cancelled' THEN 1 ELSE cancel_requested END,
                    error = ?, finished_at = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    effective_status,
                    effective_status,
                    effective_detail,
                    now,
                    now,
                    job_id,
                    row["status"],
                ),
            ).rowcount
            if transitioned == 1:
                if row["operation"] == "embedding_reindex":
                    self.connection.execute(
                        "DELETE FROM embedding_reindex_staging WHERE job_id = ?",
                        (job_id,),
                    )
                else:
                    self._fail_document(str(row["document_id"]), effective_detail, now)
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def _fail_document(self, document_id: str, detail: str, now: str) -> None:
        row = self.connection.execute(
            "SELECT status FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            return
        from_status = str(row["status"])
        if from_status == "failed":
            self.connection.execute(
                "UPDATE documents SET error = ?, updated_at = ? WHERE id = ?",
                (detail, now, document_id),
            )
            return
        self.connection.execute(
            """
            UPDATE documents SET status = 'failed', error = ?, updated_at = ?
            WHERE id = ?
            """,
            (detail, now, document_id),
        )
        self.connection.execute(
            """
            INSERT INTO document_status_events
                (document_id, from_status, to_status, detail, occurred_at)
            VALUES (?, ?, 'failed', ?, ?)
            """,
            (document_id, from_status, detail, now),
        )

    @staticmethod
    def _job_dict(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "document_id": row["document_id"],
            "status": row["status"],
            "stage": row["stage"],
            "progress": int(row["progress"]),
            "cancel_requested": bool(row["cancel_requested"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "operation": row["operation"],
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _embedding_model_id(model: EmbeddingModel) -> str:
    identity = "\0".join(
        (model.provider, model.model, model.version, str(model.dimensions))
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
