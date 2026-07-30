from __future__ import annotations

import math

import pytest

from app.hybrid_retrieval import (
    LEXICAL_ONLY_WARNING,
    RankedChunk,
    RetrievalCapability,
    fuse_ranked_chunks,
)
from app.retrieval_interfaces import (
    ChunkMetadata,
    EmbeddingModel,
    VectorRecord,
    validate_embedding,
    validate_model_compatibility,
)


MODEL = EmbeddingModel(provider="local", model="fixture", version="1", dimensions=3)


def _ranked(
    chunk_id: str,
    *,
    document_id: str = "doc-a",
    ordinal: int = 0,
    course_ids: tuple[str, ...] = ("course-a",),
) -> RankedChunk:
    return RankedChunk(
        ChunkMetadata(
            chunk_id=chunk_id,
            document_id=document_id,
            document_name=f"{document_id}.txt",
            page_number=ordinal + 1,
            ordinal=ordinal,
            section_path=("Section",),
            text=f"Text for {chunk_id}",
            course_ids=course_ids,
        )
    )


def test_embedding_dimension_finiteness_and_model_revision_are_fail_closed():
    assert validate_embedding((0, 1, 2), model=MODEL) == (0.0, 1.0, 2.0)
    VectorRecord(_ranked("chunk").chunk, (0, 1, 2), MODEL)

    with pytest.raises(ValueError, match="dimension mismatch"):
        validate_embedding((0, 1), model=MODEL)
    with pytest.raises(ValueError, match="finite"):
        validate_embedding((0, math.nan, 2), model=MODEL)
    with pytest.raises(ValueError, match="version"):
        validate_model_compatibility(
            indexed=MODEL,
            requested=EmbeddingModel(
                provider="local", model="fixture", version="2", dimensions=3
            ),
        )
    with pytest.raises(ValueError, match="dimensions"):
        validate_model_compatibility(
            indexed=MODEL,
            requested=EmbeddingModel(
                provider="local", model="fixture", version="1", dimensions=4
            ),
        )


@pytest.mark.parametrize(
    "vector",
    [
        (0.0, 0.0, 0.0),
    ],
)
def test_embeddings_must_be_usable_nonzero_float32_vectors(vector):
    with pytest.raises(ValueError, match="non-zero"):
        VectorRecord(_ranked("bad-vector").chunk, vector, MODEL)


@pytest.mark.parametrize("magnitude", [1e-300, 1e-30, 1e30, 1e300])
def test_extreme_vectors_are_safely_rescaled_for_sqlite_cosine(magnitude):
    values = validate_embedding((magnitude, 0.0, 0.0), model=MODEL)
    assert values == (1.0, 0.0, 0.0)


def test_rrf_promotes_cross_channel_hit_and_deduplicates_each_channel():
    lexical = [_ranked("lexical"), _ranked("both"), _ranked("both")]
    vector = [_ranked("both"), _ranked("vector")]

    result = fuse_ranked_chunks(
        lexical,
        vector,
        capability=RetrievalCapability(vector_available=True),
        limit=8,
    )

    assert result.mode == "hybrid"
    assert result.warning is None
    assert result.results[0].chunk_ids == ("both",)
    assert sum("both" in item.chunk_ids for item in result.results) == 1


def test_top_thirty_per_channel_is_used_and_course_filter_metadata_is_preserved():
    lexical = [
        _ranked(
            f"chunk-{index}",
            document_id=f"doc-{index}",
            course_ids=("course-a",) if index != 30 else ("course-b",),
        )
        for index in range(31)
    ]

    result = fuse_ranked_chunks(
        lexical,
        (),
        capability=RetrievalCapability(
            vector_available=False, vector_unavailable_reason="model not installed"
        ),
        course_id="course-a",
        limit=10,
    )

    assert result.mode == "lexical_only"
    assert result.warning is not None and LEXICAL_ONLY_WARNING in result.warning
    assert len(result.results) == 10
    assert all(item.course_ids == ("course-a",) for item in result.results)
    assert all("chunk-30" not in item.chunk_ids for item in result.results)


def test_adjacent_chunks_merge_in_ordinal_order_with_stable_metadata():
    result = fuse_ranked_chunks(
        [_ranked("middle", ordinal=4), _ranked("before", ordinal=3)],
        [_ranked("after", ordinal=5)],
        capability=RetrievalCapability(vector_available=True),
        limit=6,
    )

    assert len(result.results) == 1
    merged = result.results[0]
    assert merged.chunk_ids == ("before", "middle", "after")
    assert (merged.ordinal_start, merged.ordinal_end) == (3, 5)
    assert merged.text == "Text for before\n\nText for middle\n\nText for after"


def test_adjacent_merge_has_a_bounded_chunk_count_without_length_score_bias():
    result = fuse_ranked_chunks(
        [_ranked(f"chunk-{ordinal}", ordinal=ordinal) for ordinal in range(6)],
        (),
        capability=RetrievalCapability(
            vector_available=False, vector_unavailable_reason="disabled"
        ),
        limit=6,
    )

    assert [item.chunk_ids for item in result.results] == [
        ("chunk-0", "chunk-1", "chunk-2"),
        ("chunk-3", "chunk-4", "chunk-5"),
    ]
    assert result.results[0].score >= result.results[1].score


def test_lexical_only_mode_cannot_hide_vector_results_or_omit_reason():
    with pytest.raises(ValueError, match="requires a reason"):
        RetrievalCapability(vector_available=False)
    with pytest.raises(ValueError, match="vector results supplied"):
        fuse_ranked_chunks(
            [_ranked("lexical")],
            [_ranked("vector")],
            capability=RetrievalCapability(
                vector_available=False, vector_unavailable_reason="disabled"
            ),
            limit=8,
        )


@pytest.mark.parametrize("limit", [0, 5, 11, 50])
def test_hybrid_output_limit_is_six_to_ten(limit):
    with pytest.raises(ValueError, match="between 6 and 10"):
        fuse_ranked_chunks(
            (),
            (),
            capability=RetrievalCapability(
                vector_available=False, vector_unavailable_reason="disabled"
            ),
            limit=limit,
        )
