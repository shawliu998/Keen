from __future__ import annotations

import hashlib
import sqlite3

from .settings import LocalEmbeddingSettings


def enrich_document_knowledge_state(
    connection: sqlite3.Connection,
    document: dict,
    *,
    configuration: LocalEmbeddingSettings | None,
    vector_extension_error: str | None,
) -> dict:
    """Add truthful retrieval/index state without changing persistence status."""

    enriched = dict(document)
    if document["status"] != "indexed":
        enriched.update(
            indexState="pending",
            embeddingStatus="not-applicable",
            embeddingModel=None,
            embeddingError=None,
            retrievalWarning=None,
            providerConfigured=configuration is not None,
        )
        return enriched
    if configuration is None:
        enriched.update(
            indexState="indexed-lexical",
            embeddingStatus="provider-missing",
            embeddingModel=None,
            embeddingError=None,
            retrievalWarning=(
                "Local embeddings are not configured. Existing lexical search remains available."
            ),
            providerConfigured=False,
        )
        return enriched

    model_id = _model_id(configuration)
    row = connection.execute(
        """
        SELECT des.status, des.expected_chunk_count, des.embedded_chunk_count,
               des.error,
               (SELECT COUNT(*) FROM chunk_embeddings ce
                JOIN document_chunks dc ON dc.id = ce.chunk_id
                WHERE dc.document_id = des.document_id
                  AND ce.model_id = des.model_id) AS actual_vector_count
        FROM document_embedding_state des
        WHERE des.document_id = ? AND des.model_id = ?
        """,
        (document["id"], model_id),
    ).fetchone()
    model_label = (
        f"{configuration.provider}: {configuration.model}@{configuration.version} "
        f"({configuration.dimensions} dimensions)"
    )
    common = {"embeddingModel": model_label, "providerConfigured": True}
    if row is None:
        enriched.update(
            **common,
            indexState="needs-reindex",
            embeddingStatus="needs-reindex",
            embeddingError=None,
            retrievalWarning=(
                "This source has no embeddings for the configured model. "
                "Lexical search remains available until it is reindexed."
            ),
        )
        return enriched
    if row["status"] == "failed":
        enriched.update(
            **common,
            indexState="indexed-lexical",
            embeddingStatus="provider-failure",
            embeddingError=row["error"],
            retrievalWarning=(
                "Embedding failed for this source. Its lexical index remains available; retry indexing after the local provider recovers."
            ),
        )
        return enriched
    ready = (
        row["status"] == "ready"
        and int(row["expected_chunk_count"]) > 0
        and int(row["embedded_chunk_count"]) == int(row["expected_chunk_count"])
        and int(row["expected_chunk_count"]) == int(document["chunk_count"])
        and int(row["actual_vector_count"]) == int(document["chunk_count"])
    )
    if not ready:
        enriched.update(
            **common,
            indexState="needs-reindex",
            embeddingStatus="needs-reindex",
            embeddingError=row["error"],
            retrievalWarning=(
                "Stored embeddings are incomplete. Lexical search remains available while this source needs reindexing."
            ),
        )
        return enriched
    if vector_extension_error is not None:
        enriched.update(
            **common,
            indexState="indexed-lexical",
            embeddingStatus="ready",
            embeddingError=None,
            retrievalWarning=(
                "Embeddings are stored, but sqlite-vec is unavailable. Search is lexical-only until the local service is repaired."
            ),
        )
        return enriched
    enriched.update(
        **common,
        indexState="indexed-hybrid",
        embeddingStatus="ready",
        embeddingError=None,
        retrievalWarning=None,
    )
    return enriched


def _model_id(configuration: LocalEmbeddingSettings) -> str:
    identity = "\0".join(
        (
            configuration.provider,
            configuration.model,
            configuration.version,
            str(configuration.dimensions),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
