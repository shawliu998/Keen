"""Strict provider output for one bounded, unapplied plan proposal."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agent.types import is_hidden_reasoning_key


class InsertPrerequisiteOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["insert_prerequisite"]
    before_unit_id: str = Field(alias="beforeUnitId", min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=500)
    estimated_minutes: int = Field(alias="estimatedMinutes", ge=5, le=30)
    selected_source_handles: list[str] = Field(
        alias="selectedSourceHandles", min_length=1, max_length=8
    )

    @field_validator("selected_source_handles")
    @classmethod
    def validate_handles(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
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

    @field_validator("title", "objective")
    @classmethod
    def reject_state_claims(cls, value: str) -> str:
        folded = " ".join(value.casefold().split())
        if any(
            claim in folded
            for claim in (
                "mastered",
                "mastery score",
                "completed",
                "task done",
                "bkt",
                "fsrs",
            )
        ):
            raise ValueError("proposal operation contains a prohibited state claim")
        if is_hidden_reasoning_key(value):
            raise ValueError("proposal must not expose hidden reasoning")
        return value


class StudyPlanProposalProviderArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = Field(alias="schemaVersion")
    summary: str = Field(min_length=1, max_length=1_000)
    reason: str = Field(min_length=1, max_length=1_000)
    operation: InsertPrerequisiteOperation

    @field_validator("summary", "reason")
    @classmethod
    def reject_authoritative_claims(cls, value: str) -> str:
        folded = " ".join(value.casefold().split())
        prohibited = (
            "plan updated",
            "plan applied",
            "session completed",
            "task completed",
            "mastery score",
            "you have mastered",
            "bkt",
            "fsrs",
        )
        if any(claim in folded for claim in prohibited):
            raise ValueError("proposal contains a prohibited state claim")
        if is_hidden_reasoning_key(value):
            raise ValueError("proposal must not expose hidden reasoning")
        return value


__all__ = [
    "InsertPrerequisiteOperation",
    "StudyPlanProposalProviderArtifact",
]
