from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
import struct
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from app.database import Database
from app.retrieval_interfaces import (
    ChunkMetadata,
    EmbeddingModel,
    VectorMatch,
    VectorRecord,
    validate_embedding,
    validate_model_compatibility,
)


class SQLiteVectorStore:
    """Exact sqlite-vec cosine retrieval over statically migrated BLOB rows."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        if not records:
            return
        records_by_model: dict[EmbeddingModel, list[VectorRecord]] = defaultdict(list)
        for record in records:
            _validate_model_bounds(record.embedding_model)
            records_by_model[record.embedding_model].append(record)

        with self._database.connection() as connection:
            self._database.require_vector_extension(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                for model, model_records in records_by_model.items():
                    model_id = _model_id(model)
                    _register_model(connection, model_id=model_id, model=model)
                    affected_documents: set[str] = set()
                    for record in model_records:
                        _assert_chunk_identity(connection, record.chunk)
                        vector = validate_embedding(
                            record.vector, model=record.embedding_model
                        )
                        timestamp = _now()
                        connection.execute(
                            """
                            INSERT INTO chunk_embeddings (
                                chunk_id, model_id, dimensions, embedding,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(chunk_id, model_id) DO UPDATE SET
                                dimensions = excluded.dimensions,
                                embedding = excluded.embedding,
                                updated_at = excluded.updated_at
                            """,
                            (
                                record.chunk.chunk_id,
                                model_id,
                                model.dimensions,
                                _serialize(vector),
                                timestamp,
                                timestamp,
                            ),
                        )
                        affected_documents.add(record.chunk.document_id)
                    for document_id in affected_documents:
                        _refresh_document_state(
                            connection, document_id=document_id, model_id=model_id
                        )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    async def search(
        self,
        vector: Sequence[float],
        *,
        embedding_model: EmbeddingModel,
        limit: int,
        course_id: str | None,
    ) -> Sequence[VectorMatch]:
        return await asyncio.to_thread(
            self._search_sync,
            tuple(vector),
            embedding_model=embedding_model,
            limit=limit,
            course_id=course_id,
        )

    def _search_sync(
        self,
        vector: Sequence[float],
        *,
        embedding_model: EmbeddingModel,
        limit: int,
        course_id: str | None,
    ) -> Sequence[VectorMatch]:
        if limit < 1 or limit > 100:
            raise ValueError("vector search limit must be between 1 and 100")
        _validate_model_bounds(embedding_model)
        query_vector = validate_embedding(vector, model=embedding_model)
        model_id = _model_id(embedding_model)
        with self._database.connection() as connection:
            self._database.require_vector_extension(connection)
            indexed_model = _get_indexed_model(
                connection, model_id=model_id, requested=embedding_model
            )
            if indexed_model is None:
                return ()
            validate_model_compatibility(
                indexed=indexed_model, requested=embedding_model
            )
            course_clause = ""
            parameters: list[object] = [_serialize(query_vector), model_id]
            if course_id is not None:
                course_clause = """
                    AND EXISTS (
                        SELECT 1 FROM course_documents cd
                        WHERE cd.document_id = dc.document_id
                          AND cd.course_id = ?
                    )
                """
                parameters.append(course_id)
            parameters.append(limit)
            rows = connection.execute(
                f"""
                SELECT
                    dc.id AS chunk_id, dc.document_id, d.name AS document_name,
                    dc.page_number, dc.ordinal, dc.section_path, dc.content,
                    vec_distance_cosine(ce.embedding, ?) AS distance,
                    COALESCE((
                        SELECT json_group_array(course_id) FROM (
                            SELECT course_id FROM course_documents
                            WHERE document_id = dc.document_id ORDER BY course_id
                        )
                    ), '[]') AS course_ids
                FROM chunk_embeddings ce
                JOIN document_chunks dc ON dc.id = ce.chunk_id
                JOIN documents d ON d.id = dc.document_id
                JOIN document_embedding_state des
                  ON des.document_id = dc.document_id
                 AND des.model_id = ce.model_id
                WHERE ce.model_id = ? AND d.status = 'indexed'
                  AND des.status = 'ready'
                  AND des.expected_chunk_count > 0
                  AND des.embedded_chunk_count = des.expected_chunk_count
                  AND des.expected_chunk_count = (
                      SELECT COUNT(*) FROM document_chunks counted
                      WHERE counted.document_id = dc.document_id
                  )
                  AND des.expected_chunk_count = (
                      SELECT COUNT(*)
                      FROM chunk_embeddings counted_embeddings
                      JOIN document_chunks counted_chunks
                        ON counted_chunks.id = counted_embeddings.chunk_id
                      WHERE counted_chunks.document_id = dc.document_id
                        AND counted_embeddings.model_id = ce.model_id
                  )
                {course_clause}
                ORDER BY distance ASC, dc.document_id, dc.ordinal, dc.id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        matches: list[VectorMatch] = []
        for row in rows:
            try:
                distance = float(row["distance"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "vector search returned an invalid distance"
                ) from error
            score = 1.0 - distance
            if not math.isfinite(score):
                raise ValueError("vector search returned a non-finite score")
            matches.append(
                VectorMatch(
                    chunk=ChunkMetadata(
                        chunk_id=str(row["chunk_id"]),
                        document_id=str(row["document_id"]),
                        document_name=str(row["document_name"]),
                        page_number=int(row["page_number"]),
                        ordinal=int(row["ordinal"]),
                        section_path=tuple(json.loads(row["section_path"])),
                        text=str(row["content"]),
                        course_ids=tuple(json.loads(row["course_ids"])),
                    ),
                    score=score,
                )
            )
        return tuple(matches)

    async def delete_document(self, document_id: str) -> int:
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    DELETE FROM chunk_embeddings
                    WHERE chunk_id IN (
                        SELECT id FROM document_chunks WHERE document_id = ?
                    )
                    """,
                    (document_id,),
                )
                connection.execute(
                    "DELETE FROM document_embedding_state WHERE document_id = ?",
                    (document_id,),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return max(cursor.rowcount, 0)


def _validate_model_bounds(model: EmbeddingModel) -> None:
    if model.dimensions > 8192:
        raise ValueError("embedding dimensions must not exceed 8192")


def _model_id(model: EmbeddingModel) -> str:
    identity = "\0".join(
        (model.provider, model.model, model.version, str(model.dimensions))
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _register_model(
    connection: sqlite3.Connection, *, model_id: str, model: EmbeddingModel
) -> None:
    timestamp = _now()
    connection.execute(
        """
        INSERT INTO embedding_models (
            id, provider, model, version, dimensions, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (
            model_id,
            model.provider,
            model.model,
            model.version,
            model.dimensions,
            timestamp,
        ),
    )
    indexed = _row_to_model(
        connection.execute(
            "SELECT * FROM embedding_models WHERE id = ?", (model_id,)
        ).fetchone()
    )
    validate_model_compatibility(indexed=indexed, requested=model)


def _get_indexed_model(
    connection: sqlite3.Connection,
    *,
    model_id: str,
    requested: EmbeddingModel,
) -> EmbeddingModel | None:
    exact = connection.execute(
        "SELECT * FROM embedding_models WHERE id = ?", (model_id,)
    ).fetchone()
    if exact is not None:
        return _row_to_model(exact)
    related = connection.execute(
        """
        SELECT * FROM embedding_models
        WHERE provider = ? AND model = ?
        ORDER BY created_at, id LIMIT 1
        """,
        (requested.provider, requested.model),
    ).fetchone()
    if related is not None:
        validate_model_compatibility(
            indexed=_row_to_model(related), requested=requested
        )
    return None


def _row_to_model(row: sqlite3.Row) -> EmbeddingModel:
    return EmbeddingModel(
        provider=str(row["provider"]),
        model=str(row["model"]),
        version=str(row["version"]),
        dimensions=int(row["dimensions"]),
    )


def _assert_chunk_identity(
    connection: sqlite3.Connection, metadata: ChunkMetadata
) -> None:
    row = connection.execute(
        "SELECT document_id FROM document_chunks WHERE id = ?", (metadata.chunk_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"embedding chunk does not exist: {metadata.chunk_id}")
    if row["document_id"] != metadata.document_id:
        raise ValueError("embedding chunk document metadata does not match storage")


def _refresh_document_state(
    connection: sqlite3.Connection, *, document_id: str, model_id: str
) -> None:
    counts = connection.execute(
        """
        SELECT
            COUNT(dc.id) AS expected,
            COUNT(ce.chunk_id) AS embedded
        FROM document_chunks dc
        LEFT JOIN chunk_embeddings ce
          ON ce.chunk_id = dc.id AND ce.model_id = ?
        WHERE dc.document_id = ?
        """,
        (model_id, document_id),
    ).fetchone()
    expected, embedded = int(counts["expected"]), int(counts["embedded"])
    status = "ready" if expected > 0 and embedded == expected else "embedding"
    connection.execute(
        """
        INSERT INTO document_embedding_state (
            document_id, model_id, status, expected_chunk_count,
            embedded_chunk_count, error, updated_at
        ) VALUES (?, ?, ?, ?, ?, NULL, ?)
        ON CONFLICT(document_id, model_id) DO UPDATE SET
            status = excluded.status,
            expected_chunk_count = excluded.expected_chunk_count,
            embedded_chunk_count = excluded.embedded_chunk_count,
            error = NULL,
            updated_at = excluded.updated_at
        """,
        (document_id, model_id, status, expected, embedded, _now()),
    )


def _serialize(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _now() -> str:
    return datetime.now(UTC).isoformat()
