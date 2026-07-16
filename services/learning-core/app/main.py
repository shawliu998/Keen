from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware

from . import __version__
from .answer_service import (
    AnswerService,
    ChatProviderFactory,
    create_chat_provider,
)
from .auth import require_session
from .database import Database
from .document_repository import DocumentRepository, DuplicateDocumentHashError
from .documents import (
    DocumentParseError,
    DocumentTooLargeError,
    DocumentValidationError,
    canonical_media_type,
    clear_incoming_uploads,
    copy_and_hash,
    ensure_private_directory,
    incoming_destination,
    parser_version_for,
    resolve_stored_document_path,
    storage_destination,
    validate_file_content,
    validate_upload_metadata,
)
from .index_jobs import ActiveIndexJobError, IndexJobRepository
from .index_worker import DocumentIndexWorker
from .instance_lock import hold_database_instance_lock
from .knowledge_state import enrich_document_knowledge_state
from .repository import LearningRepository
from .request_guard import RequestGuardMiddleware
from .retrieval_service import (
    HybridRetrievalService,
    ProviderFactory,
    create_embedding_provider,
)
from .schemas import (
    AnswerRequest,
    Citation,
    Course,
    DemoState,
    DocumentImportResponse,
    DocumentEmbeddingReindexResponse,
    DocumentCourseLinkResponse,
    DocumentIndexJob,
    DocumentIndexJobListResponse,
    DocumentListResponse,
    DocumentRetryResponse,
    GroundedQueryResponse,
    HealthResponse,
    MasteryAttempt,
    MasteryState,
    MasteryUpdate,
    SearchRequest,
    SearchResponse,
    StudyTask,
    TaskCreate,
    TaskUpdate,
)
from .settings import Settings
from .retrieval_interfaces import EmbeddingModel
from .storage_reconciliation import (
    StoredFileDeleteError,
    quarantine_for_delete,
    reconcile_document_storage,
    remove_quarantined_files,
    restore_quarantined_files,
)

logger = logging.getLogger("keen.learning_core")

StartupPhase = Literal["migrating", "recovering", "starting_server"]
StartupPhaseReporter = Callable[[StartupPhase], None]


def _repository(request: Request) -> Iterator[LearningRepository]:
    with request.app.state.database.connection() as connection:
        yield LearningRepository(connection)


def _document_repository(request: Request) -> Iterator[DocumentRepository]:
    with request.app.state.database.connection() as connection:
        yield DocumentRepository(connection)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(
    settings: Settings,
    *,
    startup_phase_reporter: StartupPhaseReporter | None = None,
    embedding_provider_factory: ProviderFactory | None = None,
    chat_provider_factory: ChatProviderFactory | None = None,
) -> FastAPI:
    report_startup_phase = startup_phase_reporter or (lambda _phase: None)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with hold_database_instance_lock(settings.database_path) as lock_path:
            app.state.instance_lock_path = lock_path
            report_startup_phase("migrating")
            applied = app.state.database.migrate()

            report_startup_phase("recovering")
            ensure_private_directory(settings.document_data_path)
            with app.state.database.connection() as connection:
                interrupted_jobs = IndexJobRepository(connection).interrupt_active_jobs(
                    "indexing was interrupted by a previous sidecar shutdown; retry the document"
                )
                recovered = DocumentRepository(connection).recover_interrupted_imports()
            incoming_removed = clear_incoming_uploads(settings.document_data_path)
            reconciliation = reconcile_document_storage(
                app.state.database, settings.document_data_path
            )
            if settings.seed_demo:
                app.state.database.seed_demo()
            app.state.database.verify_consistency()
            worker = DocumentIndexWorker(
                app.state.database,
                settings,
                app.state.document_processing_lock,
            )
            app.state.document_index_worker = worker
            worker.start()
            logger.info(
                "database_ready",
                extra={
                    "migrations_applied": applied,
                    "interrupted_imports_recovered": len(recovered),
                    "interrupted_jobs_recovered": len(interrupted_jobs),
                    "temporary_uploads_removed": incoming_removed,
                    "storage_reconciliation": reconciliation,
                },
            )
            report_startup_phase("starting_server")
            try:
                yield
            finally:
                worker_stopped = worker.stop()
                with app.state.database.connection() as connection:
                    interrupted_on_shutdown = IndexJobRepository(
                        connection
                    ).interrupt_active_jobs(
                        "indexing was interrupted by sidecar shutdown; retry the document"
                    )
                if not worker_stopped:
                    logger.error(
                        "document_index_worker_stop_timeout",
                        extra={"interrupted_jobs": len(interrupted_on_shutdown)},
                    )

    app = FastAPI(
        title="Keen Learning Core",
        version=__version__,
        lifespan=lifespan,
        dependencies=[Depends(require_session)],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.database = Database(settings.database_path)
    app.state.document_import_lock = threading.Lock()
    app.state.document_processing_lock = threading.Lock()
    app.state.embedding_provider_factory = (
        embedding_provider_factory or create_embedding_provider
    )
    app.state.chat_provider_factory = chat_provider_factory or create_chat_provider

    def enrich_document(repository: DocumentRepository, document: dict) -> dict:
        return enrich_document_knowledge_state(
            repository.connection,
            document,
            configuration=settings.local_embedding,
            vector_extension_error=app.state.database.vector_extension_error,
        )

    app.add_middleware(
        RequestGuardMiddleware,
        session_token=settings.session_token,
        max_document_bytes=settings.max_document_bytes,
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "http://127.0.0.1:1430",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Range", "X-Request-ID"],
        expose_headers=["Accept-Ranges", "Content-Range", "X-Request-ID"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", service="keen-learning-core", version=__version__
        )

    @app.get("/v1/courses", response_model=list[Course])
    def list_courses(repository: LearningRepository = Depends(_repository)):
        return repository.list_courses()

    @app.get("/v1/courses/{course_id}", response_model=Course)
    def get_course(
        course_id: str, repository: LearningRepository = Depends(_repository)
    ):
        course = repository.get_course(course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="course not found")
        mastery = repository.list_mastery(course_id=course_id)
        course["concept_count"] = len(mastery)
        course["average_mastery"] = (
            round(sum(item["probability"] for item in mastery) / len(mastery), 6)
            if mastery
            else None
        )
        return course

    @app.get("/v1/tasks", response_model=list[StudyTask])
    def list_tasks(
        course_id: str | None = None,
        status: str | None = Query(
            default=None, pattern="^(upcoming|overdue|completed)$"
        ),
        repository: LearningRepository = Depends(_repository),
    ):
        return repository.list_tasks(course_id=course_id, status=status)

    @app.post("/v1/tasks", response_model=StudyTask, status_code=201)
    def create_task(
        task: TaskCreate,
        repository: LearningRepository = Depends(_repository),
    ):
        try:
            created = repository.create_task(
                task_id=f"task-{uuid.uuid4().hex}",
                course_id=task.course_id,
                concept_id=task.concept_id,
                title=task.title,
                reason=task.reason,
                due_at=task.due_at.isoformat(),
                estimated_minutes=task.estimated_minutes,
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail="concept not found") from error
        if created is None:
            raise HTTPException(status_code=404, detail="course not found")
        created["course_title"] = None
        return created

    @app.patch("/v1/tasks/{task_id}", response_model=StudyTask)
    def update_task(
        task_id: str,
        update: TaskUpdate,
        repository: LearningRepository = Depends(_repository),
    ):
        due_at = update.due_at.isoformat() if update.due_at else None
        task = repository.update_task(task_id, status=update.status, due_at=due_at)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        task["course_title"] = None
        return task

    @app.get("/v1/mastery", response_model=list[MasteryState])
    def list_mastery(
        course_id: str | None = None,
        repository: LearningRepository = Depends(_repository),
    ):
        return repository.list_mastery(course_id=course_id)

    @app.post("/v1/mastery/attempts", response_model=MasteryUpdate)
    def record_attempt(
        attempt: MasteryAttempt,
        repository: LearningRepository = Depends(_repository),
    ):
        result = repository.record_attempt(attempt.concept_id, correct=attempt.correct)
        if result is None:
            raise HTTPException(status_code=404, detail="concept not found")
        return result

    @app.get("/v1/demo-state", response_model=DemoState)
    def demo_state(repository: LearningRepository = Depends(_repository)):
        return {
            "courses": repository.list_courses(),
            "tasks": repository.list_tasks(),
            "mastery": repository.list_mastery(),
        }

    @app.post(
        "/v1/documents/import",
        response_model=DocumentImportResponse,
        status_code=202,
    )
    def import_document(
        response: Response,
        request: Request,
        file: UploadFile = File(...),
        course_id: str | None = Form(default=None),
        repository: DocumentRepository = Depends(_document_repository),
    ):
        try:
            display_name, extension = validate_upload_metadata(
                file.filename, file.content_type
            )
        except DocumentValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if course_id == "":
            course_id = None
        if course_id is not None and not repository.course_exists(course_id):
            raise HTTPException(status_code=404, detail="course not found")

        data_root = settings.document_data_path
        if data_root is None:  # pragma: no cover - normalized by Settings
            raise RuntimeError("document data path is not configured")
        incoming_path = incoming_destination(data_root, uuid.uuid4().hex)
        stored_path: Path | None = None
        storage_relative: str | None = None
        import_lock_acquired = False
        try:
            size_bytes, content_hash = copy_and_hash(
                file.file,
                incoming_path,
                settings.max_document_bytes,
            )
            validate_file_content(incoming_path, extension)
            request.app.state.document_import_lock.acquire()
            import_lock_acquired = True
            existing = repository.get_document_by_hash(content_hash)
            if existing is not None:
                latest_job = IndexJobRepository(
                    repository.connection
                ).latest_job_for_document(existing["id"])
                if latest_job is None:
                    raise HTTPException(
                        status_code=409,
                        detail="identical content has no recoverable indexing record",
                    )
                work_item = IndexJobRepository(repository.connection).work_item(
                    existing["id"]
                )
                if work_item is None:
                    raise HTTPException(
                        status_code=409,
                        detail="identical content has no recoverable source metadata",
                    )
                try:
                    resolve_stored_document_path(
                        data_root, str(work_item["storage_path"])
                    )
                except DocumentParseError as error:
                    if str(error) != "stored document file is missing":
                        raise HTTPException(
                            status_code=409, detail=str(error)
                        ) from error
                    if extension != work_item["extension"]:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "identical missing content must be re-imported with "
                                "its original file type"
                            ),
                        ) from error
                    repaired_path, repaired_relative = storage_destination(
                        data_root, content_hash, extension
                    )
                    if repaired_relative != work_item["storage_path"]:
                        raise HTTPException(
                            status_code=409,
                            detail="stored source metadata is not canonical",
                        ) from error
                    os.replace(incoming_path, repaired_path)
                    stored_path = repaired_path
                    storage_relative = repaired_relative
                    if latest_job["status"] in {"cancelled", "failed", "interrupted"}:
                        try:
                            latest_job = IndexJobRepository(
                                repository.connection
                            ).create_retry_job(
                                job_id=f"job-{uuid.uuid4().hex}",
                                document_id=existing["id"],
                            )
                        except ActiveIndexJobError as retry_error:
                            raise HTTPException(
                                status_code=409, detail=str(retry_error)
                            ) from retry_error
                        existing = repository.get_document(existing["id"])
                        if existing is None:  # pragma: no cover
                            raise RuntimeError("repaired document disappeared")
                        linked = False
                        if course_id is not None:
                            existing, linked = repository.link_document_course(
                                existing["id"], course_id
                            )
                        response.status_code = 202
                        request.app.state.document_index_worker.notify()
                        return {
                            "document": enrich_document(repository, existing),
                            "job": latest_job,
                            "duplicate": True,
                            "linked": linked,
                        }
                linked = False
                if course_id is not None:
                    existing, linked = repository.link_document_course(
                        existing["id"], course_id
                    )
                response.status_code = 200
                return {
                    "document": enrich_document(repository, existing),
                    "job": latest_job,
                    "duplicate": True,
                    "linked": linked,
                }

            stored_path, storage_relative = storage_destination(
                data_root, content_hash, extension
            )
            os.replace(incoming_path, stored_path)
            document_id = f"doc-{uuid.uuid4().hex}"
            version_id = f"version-{uuid.uuid4().hex}"
            job_id = f"job-{uuid.uuid4().hex}"
            mime_type = canonical_media_type(extension)
            try:
                document = repository.create_document(
                    document_id=document_id,
                    version_id=version_id,
                    course_id=course_id,
                    name=display_name,
                    mime_type=mime_type,
                    extension=extension,
                    content_hash=content_hash,
                    storage_path=storage_relative,
                    size_bytes=size_bytes,
                    parser_version=parser_version_for(extension),
                    job_id=job_id,
                )
            except DuplicateDocumentHashError as error:
                existing = error.document
                latest_job = IndexJobRepository(
                    repository.connection
                ).latest_job_for_document(existing["id"])
                if latest_job is None:
                    raise HTTPException(
                        status_code=409,
                        detail="identical content has no recoverable indexing record",
                    ) from error
                linked = False
                if course_id is not None:
                    existing, linked = repository.link_document_course(
                        existing["id"], course_id
                    )
                response.status_code = 200
                return {
                    "document": enrich_document(repository, existing),
                    "job": latest_job,
                    "duplicate": True,
                    "linked": linked,
                }
            job = IndexJobRepository(repository.connection).get_job(job_id)
            if job is None:  # pragma: no cover - inserted in the same transaction
                raise RuntimeError("index job did not persist")
            logger.info(
                "document_index_job_queued",
                extra={
                    "document_id": document_id,
                    "job_id": job_id,
                    "mime_type": mime_type,
                    "size_bytes": size_bytes,
                    "hash_prefix": content_hash[:12],
                },
            )
            request.app.state.document_index_worker.notify()
            return {
                "document": enrich_document(repository, document),
                "job": job,
                "duplicate": False,
                "linked": course_id is not None,
            }
        except DocumentTooLargeError as error:
            raise HTTPException(
                status_code=413,
                detail={
                    "message": str(error),
                    "retryable": True,
                    "recovery": "Choose a smaller supported document and retry.",
                },
            ) from error
        except DocumentValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except HTTPException:
            raise
        finally:
            try:
                incoming_path.unlink(missing_ok=True)
                if (
                    stored_path is not None
                    and storage_relative is not None
                    and not repository.storage_path_is_referenced(storage_relative)
                ):
                    stored_path.unlink(missing_ok=True)
            finally:
                if import_lock_acquired:
                    request.app.state.document_import_lock.release()

    @app.get("/v1/documents", response_model=DocumentListResponse)
    def list_documents(
        course_id: str | None = Query(default=None, alias="courseId"),
        repository: DocumentRepository = Depends(_document_repository),
    ):
        if course_id is not None and not repository.course_exists(course_id):
            raise HTTPException(status_code=404, detail="course not found")
        documents = [
            enrich_document(repository, document)
            for document in repository.list_documents(course_id)
        ]
        return {"documents": documents}

    @app.get("/v1/documents/{document_id}/content")
    def document_content(
        document_id: str,
        repository: DocumentRepository = Depends(_document_repository),
    ):
        source = repository.document_content_source(document_id)
        if source is None:
            raise HTTPException(status_code=404, detail="document not found")
        if source["extension"] != ".pdf" or source["mime_type"] != "application/pdf":
            raise HTTPException(
                status_code=415,
                detail="document content viewing is available only for PDF sources",
            )
        try:
            path = resolve_stored_document_path(
                settings.document_data_path,
                str(source["storage_path"]),
            )
        except DocumentParseError as error:
            raise HTTPException(
                status_code=409,
                detail=(
                    "the stored PDF source is unavailable; retry the import or restart "
                    "Keen to run storage recovery"
                ),
            ) from error
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=str(source["name"]),
            content_disposition_type="inline",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post(
        "/v1/documents/{document_id}/courses/{course_id}",
        response_model=DocumentCourseLinkResponse,
    )
    def link_document_course(
        request: Request,
        document_id: str,
        course_id: str,
        repository: DocumentRepository = Depends(_document_repository),
    ):
        with request.app.state.document_import_lock:
            try:
                document, linked = repository.link_document_course(
                    document_id, course_id
                )
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        return {"document": enrich_document(repository, document), "linked": linked}

    @app.delete("/v1/documents/{document_id}/courses/{course_id}", status_code=204)
    def unlink_document_course(
        request: Request,
        document_id: str,
        course_id: str,
        repository: DocumentRepository = Depends(_document_repository),
    ) -> Response:
        with request.app.state.document_import_lock:
            try:
                repository.unlink_document_course(document_id, course_id)
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(status_code=204)

    @app.get("/v1/index-jobs/{job_id}", response_model=DocumentIndexJob)
    def get_index_job(request: Request, job_id: str):
        with request.app.state.database.connection() as connection:
            job = IndexJobRepository(connection).get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="index job not found")
        return job

    @app.get("/v1/index-jobs", response_model=DocumentIndexJobListResponse)
    def list_index_jobs(
        request: Request,
        document_id: str | None = Query(default=None, alias="documentId"),
    ):
        with request.app.state.database.connection() as connection:
            if (
                document_id is not None
                and DocumentRepository(connection).get_document(document_id) is None
            ):
                raise HTTPException(status_code=404, detail="document not found")
            jobs = IndexJobRepository(connection).list_jobs(document_id)
        return {"jobs": jobs}

    @app.post(
        "/v1/index-jobs/{job_id}/cancel",
        response_model=DocumentIndexJob,
    )
    def cancel_index_job(request: Request, job_id: str):
        with request.app.state.database.connection() as connection:
            job = IndexJobRepository(connection).request_cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="index job not found")
        request.app.state.document_index_worker.notify()
        return job

    @app.post(
        "/v1/documents/{document_id}/retry",
        response_model=DocumentRetryResponse,
        status_code=202,
    )
    def retry_document(request: Request, document_id: str):
        with request.app.state.document_import_lock:
            with request.app.state.database.connection() as connection:
                documents = DocumentRepository(connection)
                document = documents.get_document(document_id)
                if document is None:
                    raise HTTPException(status_code=404, detail="document not found")
                work_item = IndexJobRepository(connection).work_item(document_id)
                if work_item is None:
                    raise HTTPException(
                        status_code=409, detail="document source metadata is missing"
                    )
                try:
                    resolve_stored_document_path(
                        settings.document_data_path, str(work_item["storage_path"])
                    )
                except DocumentValidationError as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                except Exception as error:
                    raise HTTPException(
                        status_code=409,
                        detail="stored source is unavailable; re-import the document",
                    ) from error
                try:
                    job = IndexJobRepository(connection).create_retry_job(
                        job_id=f"job-{uuid.uuid4().hex}",
                        document_id=document_id,
                    )
                except ActiveIndexJobError as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                document = documents.get_document(document_id)
                if document is None:  # pragma: no cover
                    raise RuntimeError("retried document disappeared")
        request.app.state.document_index_worker.notify()
        with request.app.state.database.connection() as connection:
            enriched = enrich_document(DocumentRepository(connection), document)
        return {"document": enriched, "job": job}

    @app.post(
        "/v1/documents/{document_id}/embedding-reindex",
        response_model=DocumentEmbeddingReindexResponse,
        status_code=202,
    )
    def reindex_document_embeddings(request: Request, document_id: str):
        configuration = settings.local_embedding
        if configuration is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "a local embedding provider must be configured before embeddings can be reindexed",
                    "retryable": False,
                    "recovery": "Configure one supported loopback embedding provider, restart the learning core, then reindex this source.",
                    "documentId": document_id,
                },
            )
        model = EmbeddingModel(
            provider=configuration.provider,
            model=configuration.model,
            version=configuration.version,
            dimensions=configuration.dimensions,
        )
        with request.app.state.document_import_lock:
            with request.app.state.database.connection() as connection:
                documents = DocumentRepository(connection)
                document = documents.get_document(document_id)
                if document is None:
                    raise HTTPException(status_code=404, detail="document not found")
                try:
                    job = IndexJobRepository(connection).create_embedding_reindex_job(
                        job_id=f"job-{uuid.uuid4().hex}",
                        document_id=document_id,
                        model=model,
                    )
                except ActiveIndexJobError as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                document = documents.get_document(document_id)
                if document is None:  # pragma: no cover
                    raise RuntimeError("embedding reindex document disappeared")
                enriched = enrich_document(documents, document)
        request.app.state.document_index_worker.notify()
        return {"document": enriched, "job": job}

    @app.delete("/v1/documents/{document_id}", status_code=204)
    def delete_document(request: Request, document_id: str) -> Response:
        # Import/retry registration and document deletion share this outer lock. The
        # worker never takes it, so waiting for its processing lock cannot deadlock.
        with request.app.state.document_import_lock:
            with request.app.state.database.connection() as connection:
                jobs = IndexJobRepository(connection)
                document = DocumentRepository(connection).get_document(document_id)
                if document is None:
                    raise HTTPException(status_code=404, detail="document not found")
                latest_job = jobs.latest_job_for_document(document_id)
                if latest_job is not None and latest_job["status"] in {
                    "queued",
                    "running",
                    "cancel_requested",
                }:
                    jobs.request_cancel(str(latest_job["id"]))
            request.app.state.document_index_worker.notify()

            with request.app.state.document_processing_lock:
                with request.app.state.database.connection() as connection:
                    jobs = IndexJobRepository(connection)
                    storage_paths = jobs.removable_storage_paths(document_id)
                    if storage_paths is None:
                        raise HTTPException(
                            status_code=404, detail="document not found"
                        )
                try:
                    quarantined = quarantine_for_delete(
                        settings.document_data_path, storage_paths
                    )
                except StoredFileDeleteError as error:
                    raise HTTPException(status_code=500, detail=str(error)) from error
                try:
                    with request.app.state.database.connection() as connection:
                        if not IndexJobRepository(connection).delete_document_record(
                            document_id
                        ):
                            raise RuntimeError(
                                "document record disappeared during deletion"
                            )
                except Exception as error:
                    try:
                        restore_quarantined_files(quarantined)
                    except StoredFileDeleteError as restore_error:
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "database deletion failed and quarantined source "
                                "restoration also failed; restart Keen for storage "
                                "reconciliation"
                            ),
                        ) from restore_error
                    raise HTTPException(
                        status_code=500,
                        detail="database deletion failed; document source was restored",
                    ) from error
                try:
                    remove_quarantined_files(quarantined)
                except StoredFileDeleteError as error:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "document record was deleted, but quarantined source cleanup "
                            "failed; restart Keen to retry maintenance"
                        ),
                    ) from error
        return Response(status_code=204)

    @app.post("/v1/search", response_model=SearchResponse)
    async def search_documents(
        request: Request,
        payload: SearchRequest,
        repository: DocumentRepository = Depends(_document_repository),
    ):
        if payload.course_id is not None and not repository.course_exists(
            payload.course_id
        ):
            raise HTTPException(status_code=404, detail="course not found")
        try:
            retrieval = await HybridRetrievalService(
                request.app.state.database,
                settings,
                provider_factory=request.app.state.embedding_provider_factory,
            ).retrieve(
                payload.query,
                course_id=payload.course_id,
                limit=payload.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "query": payload.query,
            "mode": retrieval.mode,
            "warning": retrieval.warning,
            "results": [
                {
                    "chunkId": result.chunk_ids[0],
                    "chunkIds": list(result.chunk_ids),
                    "documentId": result.document_id,
                    "documentName": result.document_name,
                    "pageNumber": result.page_start,
                    "pageEnd": result.page_end,
                    "sectionPath": list(result.section_path),
                    "text": result.text,
                    "score": result.score,
                }
                for result in retrieval.results
            ],
        }

    @app.post("/v1/query", response_model=GroundedQueryResponse)
    def grounded_query(
        payload: SearchRequest,
        repository: DocumentRepository = Depends(_document_repository),
    ):
        if payload.course_id is not None and not repository.course_exists(
            payload.course_id
        ):
            raise HTTPException(status_code=404, detail="course not found")
        try:
            results = repository.search(
                payload.query,
                course_id=payload.course_id,
                limit=payload.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not results:
            return {
                "answer": "No indexed local source matched this query.",
                "grounded": False,
                "citations": [],
                "note": "No matching FTS5 chunks were found; no answer was inferred.",
            }
        citations = [
            Citation(
                chunk_id=result["chunk_id"],
                document_id=result["document_id"],
                document_name=result["document_name"],
                page_number=result["page_number"],
                section_path=result["section_path"],
                excerpt=_citation_excerpt(result["text"], payload.query),
            )
            for result in results
        ]
        passages = "\n\n".join(
            f"[{index}] {citation.excerpt}"
            for index, citation in enumerate(citations, start=1)
        )
        return {
            "answer": f"Matching passages from indexed local sources:\n\n{passages}",
            "grounded": True,
            "citations": citations,
            "note": "Deterministic FTS5 extractive result; no vector search or model was used.",
        }

    @app.post("/v1/answer/stream")
    async def answer_stream(
        request: Request,
        payload: AnswerRequest,
        repository: DocumentRepository = Depends(_document_repository),
    ):
        if payload.course_id is not None and not repository.course_exists(
            payload.course_id
        ):
            raise HTTPException(status_code=404, detail="course not found")

        async def events() -> AsyncIterator[str]:
            service = AnswerService(
                request.app.state.database,
                settings,
                HybridRetrievalService(
                    request.app.state.database,
                    settings,
                    provider_factory=request.app.state.embedding_provider_factory,
                ),
                provider_factory=request.app.state.chat_provider_factory,
            )
            async for event in service.stream(
                question=payload.question,
                course_id=payload.course_id,
                conversation_id=payload.conversation_id,
                retrieval_limit=payload.retrieval_limit,
                is_disconnected=request.is_disconnected,
            ):
                yield _sse(event.event, event.data)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _citation_excerpt(text: str, query: str, max_characters: int = 360) -> str:
    if len(text) <= max_characters:
        return text
    positions = [
        text.casefold().find(token.casefold())
        for token in query.split()
        if token and text.casefold().find(token.casefold()) >= 0
    ]
    center = min(positions) if positions else 0
    start = max(0, center - max_characters // 3)
    end = min(len(text), start + max_characters)
    start = max(0, end - max_characters)
    return text[start:end].strip()
