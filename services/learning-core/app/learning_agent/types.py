"""Strict internal types for one source-grounded intervention artifact."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agent.types import is_hidden_reasoning_key


class FrozenInterventionSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_handle: str = Field(
        alias="sourceHandle",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    chunk_id: str = Field(alias="chunkId", min_length=1, max_length=256)
    document_id: str = Field(alias="documentId", min_length=1, max_length=256)
    document_version_id: str = Field(
        alias="documentVersionId", min_length=1, max_length=256
    )
    chunk_content_hash: str = Field(
        alias="chunkContentHash",
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    document_name: str = Field(alias="documentName", min_length=1, max_length=512)
    page_number: int = Field(alias="pageNumber", ge=1)
    section_path: list[str] = Field(alias="sectionPath", max_length=16)
    quote: str = Field(min_length=1, max_length=12_000)
    geometry: dict[str, object] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class LearningInterventionProviderArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = Field(alias="schemaVersion")
    summary: str = Field(min_length=1, max_length=1000)
    explanation_markdown: str = Field(
        alias="explanationMarkdown", min_length=1, max_length=20_000
    )
    selected_source_handles: list[str] = Field(
        alias="selectedSourceHandles", min_length=1, max_length=8
    )

    @field_validator("selected_source_handles")
    @classmethod
    def validate_handles(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("selected source handles must be unique")
        if any(
            not handle
            or len(handle) > 128
            or not handle[0].isalnum()
            or any(
                character
                not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
                for character in handle
            )
            for handle in value
        ):
            raise ValueError("selected source handle is invalid")
        return value

    @field_validator("summary", "explanation_markdown")
    @classmethod
    def reject_hidden_or_authoritative_claims(cls, value: str) -> str:
        folded = " ".join(value.casefold().split())
        prohibited = (
            "you have mastered",
            "you mastered",
            "mastery score",
            "bkt",
            "fsrs",
            "session completed",
            "task completed",
        )
        if any(claim in folded for claim in prohibited):
            raise ValueError("artifact contains a prohibited learning-state claim")
        if is_hidden_reasoning_key(value):
            raise ValueError("artifact must not expose hidden reasoning")
        return value


__all__ = [
    "FrozenInterventionSource",
    "LearningInterventionProviderArtifact",
]
