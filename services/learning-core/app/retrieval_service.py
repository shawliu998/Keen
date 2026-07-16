from __future__ import annotations

import asyncio
import logging
import contextlib
from collections.abc import Callable

from .database import Database, VectorCapabilityError
from .hybrid_retrieval import (
    HybridRetrievalResult,
    RankedChunk,
    RetrievalCapability,
    fuse_ranked_chunks,
)
from .lexical_retrieval import normalize_query, search_lexical
from .local_providers import (
    LocalProviderError,
    LocalProviderTimeouts,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from .retrieval_interfaces import ChunkMetadata, EmbeddingProvider
from .settings import LocalEmbeddingSettings, Settings
from .sqlite_vector_store import SQLiteVectorStore

logger = logging.getLogger("keen.learning_core.retrieval")

ProviderFactory = Callable[[LocalEmbeddingSettings], EmbeddingProvider]


def create_embedding_provider(
    configuration: LocalEmbeddingSettings,
) -> EmbeddingProvider:
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
        timeouts=LocalProviderTimeouts(
            connect=configuration.connect_timeout_seconds,
            read=configuration.read_timeout_seconds,
            write=configuration.write_timeout_seconds,
            pool=configuration.pool_timeout_seconds,
        ),
    )


class HybridRetrievalService:
    """Runs both bounded channels and degrades explicitly to lexical search."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        provider_factory: ProviderFactory = create_embedding_provider,
    ) -> None:
        self._database = database
        self._settings = settings
        self._provider_factory = provider_factory

    async def retrieve(
        self,
        query: str,
        *,
        course_id: str | None,
        limit: int,
    ) -> HybridRetrievalResult:
        if not 1 <= limit <= 10:
            raise ValueError("search result limit must be between 1 and 10")
        normalized_query = normalize_query(query)
        lexical_rows = await asyncio.to_thread(
            self._search_lexical,
            normalized_query,
            course_id=course_id,
        )
        lexical = tuple(_lexical_ranked(row) for row in lexical_rows)
        configuration = self._settings.local_embedding
        if configuration is None:
            return _lexical_only(
                lexical,
                reason="a local embedding provider is not configured",
                course_id=course_id,
                limit=limit,
            )
        readiness_failure = await asyncio.to_thread(
            self._embedding_readiness_failure,
            configuration,
            course_id=course_id,
        )
        if readiness_failure is not None:
            return _lexical_only(
                lexical,
                reason=readiness_failure,
                course_id=course_id,
                limit=limit,
            )

        provider: EmbeddingProvider | None = None
        try:
            provider = self._provider_factory(configuration)
            query_vector = await provider.embed_query(normalized_query)
            matches = await SQLiteVectorStore(self._database).search(
                query_vector,
                embedding_model=provider.model,
                limit=30,
                course_id=course_id,
            )
        except VectorCapabilityError:
            return _lexical_only(
                lexical,
                reason="the sqlite-vec extension is unavailable",
                course_id=course_id,
                limit=limit,
            )
        except LocalProviderError:
            return _lexical_only(
                lexical,
                reason="the configured local embedding provider is unavailable",
                course_id=course_id,
                limit=limit,
            )
        except ValueError:
            return _lexical_only(
                lexical,
                reason="the configured embedding model is incompatible with the stored index",
                course_id=course_id,
                limit=limit,
            )
        except Exception:
            logger.exception("hybrid_vector_channel_failed")
            return _lexical_only(
                lexical,
                reason="the local vector channel failed; retry or reindex the affected sources",
                course_id=course_id,
                limit=limit,
            )
        finally:
            if provider is not None:
                close = getattr(provider, "aclose", None)
                if close is not None:
                    with contextlib.suppress(Exception):
                        await close()

        fused = fuse_ranked_chunks(
            lexical,
            tuple(RankedChunk(match.chunk, match.score) for match in matches),
            capability=RetrievalCapability(vector_available=True),
            course_id=course_id,
            # The fusion stage keeps its reviewed 6–10 context window. A caller
            # may request fewer results, in which case the serialized response is
            # sliced below without widening either retrieval channel.
            limit=max(6, limit),
        )
        return HybridRetrievalResult(
            mode=fused.mode,
            warning=fused.warning,
            results=fused.results[:limit],
        )

    def _search_lexical(self, query: str, *, course_id: str | None) -> list[dict]:
        with self._database.connection() as connection:
            return search_lexical(
                connection,
                query,
                course_id=course_id,
                limit=30,
            )

    def _embedding_readiness_failure(
        self,
        configuration: LocalEmbeddingSettings,
        *,
        course_id: str | None,
    ) -> str | None:
        course_clause = ""
        parameters: list[object] = [
            configuration.provider,
            configuration.model,
            configuration.version,
            configuration.dimensions,
        ]
        if course_id is not None:
            course_clause = """
                AND EXISTS (
                    SELECT 1 FROM course_documents cd
                    WHERE cd.document_id = des.document_id AND cd.course_id = ?
                )
            """
            parameters.append(course_id)
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT des.status, des.expected_chunk_count,
                       des.embedded_chunk_count,
                       (SELECT COUNT(*) FROM document_chunks chunks
                        WHERE chunks.document_id = des.document_id)
                           AS actual_chunk_count,
                       (SELECT COUNT(*)
                        FROM chunk_embeddings ce
                        JOIN document_chunks chunks ON chunks.id = ce.chunk_id
                        WHERE chunks.document_id = des.document_id
                          AND ce.model_id = des.model_id)
                           AS actual_vector_count
                FROM document_embedding_state des
                JOIN embedding_models em ON em.id = des.model_id
                JOIN documents d ON d.id = des.document_id
                WHERE em.provider = ? AND em.model = ? AND em.version = ?
                  AND em.dimensions = ?
                  AND d.status = 'indexed'
                  {course_clause}
                """,
                parameters,
            ).fetchall()
        statuses = {str(row["status"]) for row in rows}
        if any(
            row["status"] == "ready"
            and int(row["expected_chunk_count"]) > 0
            and int(row["embedded_chunk_count"]) == int(row["expected_chunk_count"])
            and int(row["actual_chunk_count"]) == int(row["expected_chunk_count"])
            and int(row["actual_vector_count"]) == int(row["expected_chunk_count"])
            for row in rows
        ):
            return None
        if "failed" in statuses:
            return (
                "embedding failed for compatible documents; retry indexing after "
                "the local provider recovers"
            )
        return "no documents have compatible ready embeddings; reindex is required"


def _lexical_ranked(row: dict) -> RankedChunk:
    return RankedChunk(
        chunk=ChunkMetadata(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            document_name=str(row["document_name"]),
            page_number=int(row["page_number"]),
            ordinal=int(row["ordinal"]),
            section_path=tuple(row["section_path"]),
            text=str(row["text"]),
            course_ids=tuple(row["course_ids"]),
        ),
        score=float(row["score"]),
    )


def _lexical_only(
    lexical: tuple[RankedChunk, ...],
    *,
    reason: str,
    course_id: str | None,
    limit: int,
) -> HybridRetrievalResult:
    fused = fuse_ranked_chunks(
        lexical,
        (),
        capability=RetrievalCapability(
            vector_available=False,
            vector_unavailable_reason=reason,
        ),
        course_id=course_id,
        # Preserve the same internal context window for lexical fallback.
        limit=max(6, limit),
    )
    return HybridRetrievalResult(
        mode=fused.mode,
        warning=fused.warning,
        results=fused.results[:limit],
    )
