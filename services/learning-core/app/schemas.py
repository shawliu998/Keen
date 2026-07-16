from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: Literal["keen-learning-core"]
    version: str


class Course(ApiModel):
    id: str
    title: str
    description: str
    created_at: datetime
    concept_count: int = 0
    average_mastery: float | None = None


class StudyTask(ApiModel):
    id: str
    course_id: str
    course_title: str | None = None
    title: str
    reason: str
    due_at: datetime
    estimated_minutes: int
    status: Literal["upcoming", "overdue", "completed"]
    concept_id: str | None
    created_at: datetime
    updated_at: datetime


class TaskCreate(ApiModel):
    course_id: str
    concept_id: str | None = None
    title: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1, max_length=2_000)
    due_at: datetime
    estimated_minutes: int = Field(gt=0, le=1_440)


class TaskUpdate(ApiModel):
    status: Literal["upcoming", "overdue", "completed"] | None = None
    due_at: datetime | None = None


class MasteryState(ApiModel):
    concept_id: str
    course_id: str
    concept_name: str
    probability: float = Field(ge=0, le=1)
    attempts: int = Field(ge=0)
    updated_at: datetime


class MasteryAttempt(ApiModel):
    concept_id: str
    correct: bool


class MasteryUpdate(ApiModel):
    concept_id: str
    correct: bool
    probability_before: float = Field(ge=0, le=1)
    probability_after: float = Field(ge=0, le=1)
    attempts: int
    updated_at: datetime


class AnswerRequest(ApiModel):
    question: str = Field(min_length=1, max_length=8_000)
    course_id: str | None = Field(default=None, alias="courseId")
    conversation_id: str | None = Field(
        default=None,
        alias="conversationId",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    retrieval_limit: int = Field(default=8, alias="retrievalLimit", ge=6, le=10)


class DemoState(ApiModel):
    courses: list[Course]
    tasks: list[StudyTask]
    mastery: list[MasteryState]


DocumentStatus = Literal["queued", "parsing", "chunking", "indexed", "failed"]


class DocumentRecord(ApiModel):
    id: str
    name: str
    mime_type: str = Field(alias="mimeType")
    size_bytes: int = Field(alias="sizeBytes", gt=0)
    content_hash: str = Field(alias="contentHash", min_length=64, max_length=64)
    status: DocumentStatus
    page_count: int = Field(alias="pageCount", ge=0)
    chunk_count: int = Field(alias="chunkCount", ge=0)
    parser: str
    created_at: datetime = Field(alias="createdAt")
    error: str | None
    course_ids: list[str] = Field(alias="courseIds")
    course_id: str | None = Field(default=None, exclude=True)
    index_state: (
        Literal["pending", "indexed-lexical", "indexed-hybrid", "needs-reindex"] | None
    ) = Field(default=None, alias="indexState")
    embedding_status: (
        Literal[
            "not-applicable",
            "provider-missing",
            "pending",
            "embedding",
            "ready",
            "provider-failure",
            "needs-reindex",
        ]
        | None
    ) = Field(default=None, alias="embeddingStatus")
    embedding_model: str | None = Field(default=None, alias="embeddingModel")
    embedding_error: str | None = Field(default=None, alias="embeddingError")
    retrieval_warning: str | None = Field(default=None, alias="retrievalWarning")
    provider_configured: bool | None = Field(default=None, alias="providerConfigured")


class DocumentListResponse(ApiModel):
    documents: list[DocumentRecord]


IndexJobStatus = Literal[
    "queued",
    "running",
    "cancel_requested",
    "cancelled",
    "completed",
    "failed",
    "interrupted",
]
IndexJobStage = Literal[
    "queued",
    "validating",
    "stored",
    "parsing",
    "chunking",
    "lexical_indexing",
    "embedding",
    "finalizing",
]


class DocumentIndexJob(ApiModel):
    id: str
    document_id: str = Field(alias="documentId")
    status: IndexJobStatus
    stage: IndexJobStage
    progress: int = Field(ge=0, le=100)
    cancel_requested: bool = Field(alias="cancelRequested")
    error: str | None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    started_at: datetime | None = Field(alias="startedAt")
    finished_at: datetime | None = Field(alias="finishedAt")
    operation: Literal["full_index", "embedding_reindex"]


class DocumentIndexJobListResponse(ApiModel):
    jobs: list[DocumentIndexJob]


class DocumentRetryResponse(ApiModel):
    document: DocumentRecord
    job: DocumentIndexJob


class DocumentEmbeddingReindexResponse(ApiModel):
    document: DocumentRecord
    job: DocumentIndexJob


class DocumentCourseLinkResponse(ApiModel):
    document: DocumentRecord
    linked: bool


class DocumentImportResponse(ApiModel):
    document: DocumentRecord
    job: DocumentIndexJob
    duplicate: bool
    linked: bool


class SearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=2_000)
    course_id: str | None = Field(default=None, alias="courseId")
    limit: int = Field(default=8, ge=1, le=10)


class SearchResult(ApiModel):
    chunk_id: str = Field(alias="chunkId")
    chunk_ids: list[str] = Field(alias="chunkIds")
    document_id: str = Field(alias="documentId")
    document_name: str = Field(alias="documentName")
    page_number: int = Field(alias="pageNumber", ge=1)
    page_end: int = Field(alias="pageEnd", ge=1)
    section_path: list[str] = Field(alias="sectionPath")
    text: str
    score: float = Field(ge=0)


class SearchResponse(ApiModel):
    query: str
    mode: Literal["hybrid", "lexical_only"]
    warning: str | None
    results: list[SearchResult]


class Citation(ApiModel):
    chunk_id: str = Field(alias="chunkId")
    document_id: str = Field(alias="documentId")
    document_name: str = Field(alias="documentName")
    page_number: int = Field(alias="pageNumber", ge=1)
    section_path: list[str] = Field(alias="sectionPath")
    excerpt: str


class GroundedQueryResponse(ApiModel):
    answer: str
    grounded: bool
    citations: list[Citation]
    note: str
