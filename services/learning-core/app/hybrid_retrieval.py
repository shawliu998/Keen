from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.retrieval_interfaces import ChunkMetadata


MAX_CHANNEL_CANDIDATES = 30
MAX_MERGED_CHUNKS = 3
MAX_MERGED_CHARACTERS = 12_000
LEXICAL_ONLY_WARNING = (
    "Vector retrieval is unavailable; results use lexical search only."
)


@dataclass(frozen=True, slots=True)
class RankedChunk:
    chunk: ChunkMetadata
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class RetrievalCapability:
    vector_available: bool
    vector_unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.vector_available and self.vector_unavailable_reason is not None:
            raise ValueError("available vector retrieval cannot have a failure reason")
        if (
            not self.vector_available
            and not (self.vector_unavailable_reason or "").strip()
        ):
            raise ValueError("unavailable vector retrieval requires a reason")


@dataclass(frozen=True, slots=True)
class FusedChunk:
    chunk_ids: tuple[str, ...]
    document_id: str
    document_name: str
    page_start: int
    page_end: int
    ordinal_start: int
    ordinal_end: int
    section_path: tuple[str, ...]
    text: str
    course_ids: tuple[str, ...]
    score: float


@dataclass(frozen=True, slots=True)
class HybridRetrievalResult:
    mode: Literal["hybrid", "lexical_only"]
    warning: str | None
    results: tuple[FusedChunk, ...]


def fuse_ranked_chunks(
    lexical_results: Sequence[RankedChunk],
    vector_results: Sequence[RankedChunk],
    *,
    capability: RetrievalCapability,
    limit: int = 8,
    course_id: str | None = None,
    rrf_k: int = 60,
) -> HybridRetrievalResult:
    """Fuse at most top-30/channel, deduplicate, then merge adjacent chunks."""

    if not 6 <= limit <= 10:
        raise ValueError("hybrid result limit must be between 6 and 10")
    if rrf_k < 1:
        raise ValueError("RRF rank constant must be greater than zero")
    if not capability.vector_available and vector_results:
        raise ValueError(
            "vector results supplied while vector retrieval is unavailable"
        )

    fused: dict[str, _AccumulatedChunk] = {}
    _accumulate_channel(
        fused,
        lexical_results[:MAX_CHANNEL_CANDIDATES],
        channel="lexical",
        course_id=course_id,
        rrf_k=rrf_k,
    )
    if capability.vector_available:
        _accumulate_channel(
            fused,
            vector_results[:MAX_CHANNEL_CANDIDATES],
            channel="vector",
            course_id=course_id,
            rrf_k=rrf_k,
        )

    ranked = sorted(
        fused.values(),
        key=lambda item: (
            -item.score,
            item.best_rank,
            item.chunk.document_id,
            item.chunk.ordinal,
            item.chunk.chunk_id,
        ),
    )
    merged = _merge_adjacent(ranked)
    output = tuple(_to_fused_chunk(item) for item in merged[:limit])
    if capability.vector_available:
        return HybridRetrievalResult(mode="hybrid", warning=None, results=output)
    reason = capability.vector_unavailable_reason or "unknown reason"
    return HybridRetrievalResult(
        mode="lexical_only",
        warning=f"{LEXICAL_ONLY_WARNING} Reason: {reason}",
        results=output,
    )


@dataclass(slots=True)
class _AccumulatedChunk:
    chunk: ChunkMetadata
    score: float
    best_rank: int


@dataclass(slots=True)
class _MergedChunk:
    chunks: list[ChunkMetadata]
    score: float
    best_rank: int


def _accumulate_channel(
    fused: dict[str, _AccumulatedChunk],
    results: Sequence[RankedChunk],
    *,
    channel: Literal["lexical", "vector"],
    course_id: str | None,
    rrf_k: int,
) -> None:
    seen_in_channel: set[str] = set()
    for rank, result in enumerate(results, start=1):
        chunk = result.chunk
        if chunk.chunk_id in seen_in_channel:
            continue
        seen_in_channel.add(chunk.chunk_id)
        if course_id is not None and course_id not in chunk.course_ids:
            continue
        contribution = 1.0 / (rrf_k + rank)
        existing = fused.get(chunk.chunk_id)
        if existing is None:
            fused[chunk.chunk_id] = _AccumulatedChunk(
                chunk=chunk, score=contribution, best_rank=rank
            )
            continue
        if existing.chunk != chunk:
            raise ValueError(
                f"conflicting {channel} metadata for chunk {chunk.chunk_id}"
            )
        existing.score += contribution
        existing.best_rank = min(existing.best_rank, rank)


def _merge_adjacent(items: Sequence[_AccumulatedChunk]) -> list[_MergedChunk]:
    """Merge retrieved neighbors without changing the group's best-hit rank."""

    groups: list[_MergedChunk] = []
    ordered = sorted(
        items,
        key=lambda item: (
            item.chunk.document_id,
            item.chunk.ordinal,
            item.chunk.chunk_id,
        ),
    )
    for item in ordered:
        chunk = item.chunk
        group = groups[-1] if groups else None
        is_next = (
            group is not None
            and group.chunks[-1].document_id == chunk.document_id
            and group.chunks[-1].ordinal + 1 == chunk.ordinal
            and len(group.chunks) < MAX_MERGED_CHUNKS
            and sum(len(value.text) for value in group.chunks) + len(chunk.text)
            <= MAX_MERGED_CHARACTERS
        )
        if not is_next:
            groups.append(
                _MergedChunk(chunks=[chunk], score=item.score, best_rank=item.best_rank)
            )
            continue
        group.chunks.append(chunk)
        group.score = max(group.score, item.score)
        group.best_rank = min(group.best_rank, item.best_rank)

    return sorted(
        groups,
        key=lambda group: (
            -group.score,
            group.best_rank,
            group.chunks[0].document_id,
            group.chunks[0].ordinal,
        ),
    )


def _to_fused_chunk(group: _MergedChunk) -> FusedChunk:
    chunks = sorted(group.chunks, key=lambda value: (value.ordinal, value.chunk_id))
    first, last = chunks[0], chunks[-1]
    common_courses = set(first.course_ids)
    for chunk in chunks[1:]:
        common_courses.intersection_update(chunk.course_ids)
    return FusedChunk(
        chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
        document_id=first.document_id,
        document_name=first.document_name,
        page_start=min(chunk.page_number for chunk in chunks),
        page_end=max(chunk.page_number for chunk in chunks),
        ordinal_start=first.ordinal,
        ordinal_end=last.ordinal,
        section_path=first.section_path,
        text="\n\n".join(chunk.text for chunk in chunks),
        course_ids=tuple(sorted(common_courses)),
        score=round(group.score, 8),
    )
