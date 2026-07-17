from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .courses import normalize_course_title_display


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


class CourseCreate(ApiModel):
    """The bounded, idempotent local course-creation command."""

    title: str = Field(min_length=1, max_length=240, strict=True)
    description: str = Field(default="", max_length=8_000, strict=True)
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=16,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        strict=True,
    )

    @field_validator("title")
    @classmethod
    def title_must_contain_non_whitespace(cls, value: str) -> str:
        normalized = normalize_course_title_display(value)
        if not normalized:
            raise ValueError("title must contain non-whitespace characters")
        if len(normalized) > 240:
            raise ValueError("normalized title must contain at most 240 characters")
        return normalized


class CourseCreateResponse(ApiModel):
    course: Course
    replayed: bool


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


_LEARNING_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class LearningFeedRequest(ApiModel):
    """A bounded local observation command; time is supplied by the sidecar."""

    course_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=_LEARNING_IDENTIFIER_PATTERN,
        strict=True,
    )
    available_minutes: int = Field(ge=1, le=1_440, strict=True)
    document_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=_LEARNING_IDENTIFIER_PATTERN,
        strict=True,
    )


class LearningPriorityComponentResponse(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    raw_value: float = Field(allow_inf_nan=False)
    weight: float = Field(allow_inf_nan=False)
    contribution: float = Field(allow_inf_nan=False)


class LearningActionCandidateResponse(ApiModel):
    id: str = Field(min_length=1, max_length=256)
    action: Literal[
        "review_due",
        "resume_study_session",
        "study_very_weak_concept",
        "address_repeated_misconception",
        "study_weak_concept",
    ]
    target_type: Literal["review_item", "study_session", "concept", "misconception"]
    target_id: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=100)
    priority_tier: int = Field(ge=1, le=10)
    estimated_minutes: int = Field(ge=1, le=1_440)
    fits_available_minutes: bool
    priority_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    # This is preserved before score clamping, so a negative deterministic
    # contribution remains valid evidence rather than a response failure.
    priority_unclamped_score: float = Field(allow_inf_nan=False)
    priority_algorithm_version: str = Field(min_length=1, max_length=100)
    priority_components: list[LearningPriorityComponentResponse] = Field(max_length=20)
    priority_explanation: list[str] = Field(max_length=20)
    why: str = Field(min_length=1, max_length=1_000)


class LearningFeedTaskResponse(ApiModel):
    id: str = Field(min_length=1, max_length=128)
    course_id: str = Field(min_length=1, max_length=128)
    concept_id: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2_000)
    due_at: datetime
    estimated_minutes: int = Field(ge=1, le=1_440)
    # A same-day idempotent replay may truthfully return the completed task;
    # completed tasks are still excluded from snapshot.pending_tasks.
    status: Literal["upcoming", "overdue", "completed"]
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str | None = Field(default=None, max_length=128)
    # Historical/manual tasks may use a non-normalized score greater than 1.
    priority_score: float = Field(ge=0, allow_inf_nan=False)
    # Older manual tasks predate recommendation provenance and legitimately
    # have no generated rationale.
    recommended_reason: str = Field(max_length=2_000)
    scheduled_for: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConceptBootstrapResponse(ApiModel):
    course_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    concept_id: str = Field(min_length=1, max_length=128)
    concept_name: str = Field(min_length=1, max_length=160)
    mastery_probability: float = Field(ge=0, le=1)
    mastery_attempts: int = Field(ge=0)
    concept_created: bool
    mastery_initialized: bool
    mastery_initialization_algorithm: str | None = Field(default=None, max_length=100)
    mastery_initialization_algorithm_version: str | None = Field(
        default=None, max_length=100
    )


class LearningFeedSnapshotResponse(ApiModel):
    course_id: str = Field(min_length=1, max_length=128)
    as_of: datetime
    available_minutes: int = Field(ge=1, le=1_440)
    due_review_count: int = Field(ge=0, le=50)
    incomplete_session_count: int = Field(ge=0, le=50)
    mastery_gap_count: int = Field(ge=0)
    misconception_count: int = Field(ge=0, le=50)
    pending_tasks: list[LearningFeedTaskResponse] = Field(max_length=50)
    candidates: list[LearningActionCandidateResponse] = Field(max_length=50)


class LearningFeedRecommendationResponse(ApiModel):
    outcome: Literal["empty", "task_created", "replay", "covered_by_active_task"]
    course_id: str = Field(min_length=1, max_length=128)
    snapshot: LearningFeedSnapshotResponse
    task: LearningFeedTaskResponse | None = None
    candidate: LearningActionCandidateResponse | None = None
    bootstrap: ConceptBootstrapResponse | None = None
