from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime

from .documents import ParsedDocument

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"parsing", "failed"}),
    "parsing": frozenset({"chunking", "failed"}),
    "chunking": frozenset({"indexed", "failed"}),
    "indexed": frozenset(),
    "failed": frozenset({"parsing"}),
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
            self.connection.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone()
            is not None
        )

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
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.get_document_by_hash(content_hash)
            if existing is not None and existing["status"] != "failed":
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

    def list_documents(self) -> list[dict]:
        rows = self.connection.execute(
            self._document_select() + " ORDER BY d.created_at DESC, d.id"
        ).fetchall()
        return [self._document_dict(row) for row in rows if row is not None]

    def recover_interrupted_imports(self) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT id, status FROM documents
            WHERE status IN ('queued', 'parsing', 'chunking')
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
            JOIN documents d ON d.id = v.document_id
            WHERE v.storage_path = ? AND d.status <> 'failed'
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
            raise ValueError(f"invalid document status transition: {from_status} -> {to_status}")
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

    def index_document(
        self,
        *,
        document_id: str,
        version_id: str,
        parsed: ParsedDocument,
    ) -> dict:
        status_row = self.connection.execute(
            "SELECT status FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if status_row is None:
            raise LookupError("document not found")
        if status_row["status"] != "chunking":
            raise ValueError("document must be in chunking state before indexing")
        now = datetime.now(UTC).isoformat()
        with self.connection:
            self.connection.execute("DELETE FROM document_chunks WHERE version_id = ?", (version_id,))
            self.connection.executemany(
                """
                INSERT INTO document_chunks
                    (id, document_id, version_id, ordinal, page_number, section_path,
                     content, content_hash, text_location, parser_version,
                     embedding_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
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
                    for chunk in parsed.chunks
                ],
            )
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

    def search(self, query: str, *, course_id: str | None, limit: int) -> list[dict]:
        fts_query = self._fts_query(query)
        course_clause = " AND d.course_id = ?" if course_id is not None else ""
        parameters: list[str | int] = [fts_query]
        if course_id is not None:
            parameters.append(course_id)
        parameters.append(limit)
        rows = self.connection.execute(
            """
            SELECT dc.id AS chunk_id, dc.document_id, d.name AS document_name,
                   dc.page_number, dc.section_path, dc.content AS text,
                   bm25(document_chunks_fts, 1.0, 0.35) AS rank
            FROM document_chunks_fts
            JOIN document_chunks dc ON dc.rowid = document_chunks_fts.rowid
            JOIN documents d ON d.id = dc.document_id
            WHERE document_chunks_fts MATCH ? AND d.status = 'indexed'
            """
            + course_clause
            + " ORDER BY rank, dc.document_id, dc.ordinal LIMIT ?",
            parameters,
        ).fetchall()
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "document_name": row["document_name"],
                "page_number": int(row["page_number"]),
                "section_path": json.loads(row["section_path"]),
                "text": row["text"],
                "score": round(max(0.0, -float(row["rank"])), 8),
            }
            for row in rows
        ]

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)[:12]
        if not tokens:
            raise ValueError("query must contain at least one letter or number")
        return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)

    @staticmethod
    def _document_select() -> str:
        return """
            SELECT d.id, d.course_id, d.name, d.mime_type, d.status,
                   d.page_count, d.chunk_count, d.error, d.created_at,
                   v.size_bytes, v.content_hash, v.parser_version AS parser
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
        }
