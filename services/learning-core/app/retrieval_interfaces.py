from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EmbeddingModel:
    """Immutable identity for vectors that may share an index."""

    provider: str
    model: str
    version: str
    dimensions: int

    def __post_init__(self) -> None:
        for field_name in ("provider", "model", "version"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"embedding {field_name} must not be empty")
        if self.dimensions < 1:
            raise ValueError("embedding dimensions must be greater than zero")


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    ordinal: int
    section_path: tuple[str, ...]
    text: str
    course_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.document_id:
            raise ValueError("chunk and document identifiers must not be empty")
        if self.page_number < 1:
            raise ValueError("chunk page number must be greater than zero")
        if self.ordinal < 0:
            raise ValueError("chunk ordinal must not be negative")
        if not self.text.strip():
            raise ValueError("chunk text must not be empty")


@dataclass(frozen=True, slots=True)
class VectorRecord:
    chunk: ChunkMetadata
    vector: tuple[float, ...]
    embedding_model: EmbeddingModel

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "vector",
            validate_embedding(self.vector, model=self.embedding_model),
        )


@dataclass(frozen=True, slots=True)
class VectorMatch:
    chunk: ChunkMetadata
    score: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.score):
            raise ValueError("vector match score must be finite")


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def model(self) -> EmbeddingModel: ...

    async def embed_documents(
        self, texts: Sequence[str]
    ) -> Sequence[Sequence[float]]: ...

    async def embed_query(self, text: str) -> Sequence[float]: ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, records: Sequence[VectorRecord]) -> None: ...

    async def search(
        self,
        vector: Sequence[float],
        *,
        embedding_model: EmbeddingModel,
        limit: int,
        course_id: str | None,
    ) -> Sequence[VectorMatch]: ...

    async def delete_document(self, document_id: str) -> int: ...


def validate_embedding(
    vector: Sequence[float], *, model: EmbeddingModel
) -> tuple[float, ...]:
    """Reject corrupt or incompatible vectors before a provider/store boundary."""

    values = tuple(float(value) for value in vector)
    if len(values) != model.dimensions:
        raise ValueError(
            "embedding dimension mismatch: "
            f"expected {model.dimensions}, received {len(values)}"
        )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("embedding values must all be finite")
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm == 0.0:
        raise ValueError("embedding vector must have a finite non-zero norm")
    # sqlite-vec accumulates cosine math in float32. Rescale extreme but otherwise
    # valid vectors so squares neither underflow nor overflow in that runtime.
    if norm < 1e-12 or norm > 1e12:
        values = tuple(value / norm for value in values)
    try:
        packed = struct.pack(f"<{len(values)}f", *values)
        float32_values = struct.unpack(f"<{len(values)}f", packed)
    except (OverflowError, struct.error) as error:
        raise ValueError("embedding values must be representable as float32") from error
    if not all(math.isfinite(value) for value in float32_values):
        raise ValueError("embedding float32 values must all be finite")
    float32_norm = math.hypot(*float32_values)
    if not math.isfinite(float32_norm) or float32_norm < 1e-12:
        raise ValueError("embedding vector must have a usable non-zero float32 norm")
    return float32_values


def validate_model_compatibility(
    *, indexed: EmbeddingModel, requested: EmbeddingModel
) -> None:
    """Fail closed instead of mixing vectors from incompatible model revisions."""

    mismatches = [
        field_name
        for field_name in ("provider", "model", "version", "dimensions")
        if getattr(indexed, field_name) != getattr(requested, field_name)
    ]
    if mismatches:
        raise ValueError(
            "embedding model is incompatible with the index: " + ", ".join(mismatches)
        )
