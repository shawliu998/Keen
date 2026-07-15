from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware

from . import __version__
from .auth import require_session
from .database import Database
from .document_repository import DocumentRepository, DuplicateDocumentHashError
from .documents import (
    DocumentParseError,
    DocumentTooLargeError,
    DocumentValidationError,
    clear_incoming_uploads,
    copy_and_hash,
    ensure_private_directory,
    incoming_destination,
    parse_document,
    parser_version_for,
    storage_destination,
    validate_file_content,
    validate_upload_metadata,
)
from .instance_lock import hold_database_instance_lock
from .repository import LearningRepository
from .request_guard import RequestGuardMiddleware
from .schemas import (
    AnswerRequest,
    Citation,
    Course,
    DemoState,
    DocumentImportResponse,
    DocumentListResponse,
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

logger = logging.getLogger("keen.learning_core")


def _repository(request: Request) -> Iterator[LearningRepository]:
    with request.app.state.database.connection() as connection:
        yield LearningRepository(connection)


def _document_repository(request: Request) -> Iterator[DocumentRepository]:
    with request.app.state.database.connection() as connection:
        yield DocumentRepository(connection)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with hold_database_instance_lock(settings.database_path) as lock_path:
            app.state.instance_lock_path = lock_path
            ensure_private_directory(settings.document_data_path)
            applied = app.state.database.migrate()
            with app.state.database.connection() as connection:
                recovered = DocumentRepository(connection).recover_interrupted_imports()
            incoming_removed = clear_incoming_uploads(settings.document_data_path)
            if settings.seed_demo:
                app.state.database.seed_demo()
            logger.info(
                "database_ready",
                extra={
                    "migrations_applied": applied,
                    "interrupted_imports_recovered": len(recovered),
                    "temporary_uploads_removed": incoming_removed,
                },
            )
            yield

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
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
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
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="keen-learning-core", version=__version__)

    @app.get("/v1/courses", response_model=list[Course])
    def list_courses(repository: LearningRepository = Depends(_repository)):
        return repository.list_courses()

    @app.get("/v1/courses/{course_id}", response_model=Course)
    def get_course(course_id: str, repository: LearningRepository = Depends(_repository)):
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
        status: str | None = Query(default=None, pattern="^(upcoming|overdue|completed)$"),
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
        status_code=201,
    )
    def import_document(
        response: Response,
        request: Request,
        file: UploadFile = File(...),
        course_id: str | None = Form(default=None),
        repository: DocumentRepository = Depends(_document_repository),
    ):
        try:
            display_name, extension = validate_upload_metadata(file.filename, file.content_type)
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
        document_id: str | None = None
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
            if existing is not None and existing["status"] == "indexed":
                if course_id is not None and existing["course_id"] != course_id:
                    raise HTTPException(
                        status_code=409,
                        detail="identical content is already indexed for a different course",
                    )
                response.status_code = 200
                return {"document": existing, "duplicate": True}
            if existing is not None and existing["status"] in {"queued", "parsing", "chunking"}:
                raise HTTPException(status_code=409, detail="identical content is already processing")

            stored_path, storage_relative = storage_destination(
                data_root, content_hash, extension
            )
            os.replace(incoming_path, stored_path)
            document_id = f"doc-{uuid.uuid4().hex}"
            version_id = f"version-{uuid.uuid4().hex}"
            mime_type = (file.content_type or "").split(";", 1)[0].strip().lower()
            try:
                repository.create_document(
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
                )
            except DuplicateDocumentHashError as error:
                existing = error.document
                if existing["status"] == "indexed":
                    if course_id is not None and existing["course_id"] != course_id:
                        raise HTTPException(
                            status_code=409,
                            detail="identical content is already indexed for a different course",
                        ) from error
                    response.status_code = 200
                    return {"document": existing, "duplicate": True}
                raise HTTPException(
                    status_code=409,
                    detail="identical content is already processing",
                ) from error
            repository.transition_status(document_id, "parsing")
            parsed = parse_document(stored_path, extension)
            repository.transition_status(document_id, "chunking")
            document = repository.index_document(
                document_id=document_id,
                version_id=version_id,
                parsed=parsed,
            )
            logger.info(
                "document_indexed",
                extra={
                    "document_id": document_id,
                    "mime_type": mime_type,
                    "size_bytes": size_bytes,
                    "page_count": parsed.page_count,
                    "chunk_count": len(parsed.chunks),
                },
            )
            return {"document": document, "duplicate": False}
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
        except DocumentParseError as error:
            if document_id is not None:
                repository.transition_status(document_id, "failed", detail=str(error))
            raise HTTPException(
                status_code=422,
                detail={
                    "message": str(error),
                    "documentId": document_id,
                    "status": "failed",
                    "retryable": True,
                    "recovery": (
                        "Retry with an unencrypted, text-extractable file. "
                        "OCR is not implemented."
                    ),
                },
            ) from error
        except HTTPException:
            raise
        except Exception:
            if document_id is not None:
                current = repository.get_document(document_id)
                if current is not None and current["status"] in {"queued", "parsing", "chunking"}:
                    repository.transition_status(
                        document_id,
                        "failed",
                        detail="unexpected indexing failure",
                    )
            raise
        finally:
            try:
                incoming_path.unlink(missing_ok=True)
                if document_id is not None:
                    current = repository.get_document(document_id)
                    should_remove_stored = False
                    if stored_path is not None and storage_relative is not None:
                        if current is None:
                            should_remove_stored = not repository.storage_path_is_referenced(
                                storage_relative
                            )
                        elif current["status"] == "failed":
                            should_remove_stored = not repository.storage_path_is_referenced(
                                storage_relative,
                                excluding_document_id=document_id,
                            )
                    if should_remove_stored and stored_path is not None:
                        stored_path.unlink(missing_ok=True)
            finally:
                if import_lock_acquired:
                    request.app.state.document_import_lock.release()

    @app.get("/v1/documents", response_model=DocumentListResponse)
    def list_documents(repository: DocumentRepository = Depends(_document_repository)):
        return {"documents": repository.list_documents()}

    @app.post("/v1/search", response_model=SearchResponse)
    def search_documents(
        payload: SearchRequest,
        repository: DocumentRepository = Depends(_document_repository),
    ):
        if payload.course_id is not None and not repository.course_exists(payload.course_id):
            raise HTTPException(status_code=404, detail="course not found")
        try:
            results = repository.search(
                payload.query,
                course_id=payload.course_id,
                limit=payload.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"query": payload.query, "results": results}

    @app.post("/v1/query", response_model=GroundedQueryResponse)
    def grounded_query(
        payload: SearchRequest,
        repository: DocumentRepository = Depends(_document_repository),
    ):
        if payload.course_id is not None and not repository.course_exists(payload.course_id):
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
            f"[{index}] {citation.excerpt}" for index, citation in enumerate(citations, start=1)
        )
        return {
            "answer": f"Matching passages from indexed local sources:\n\n{passages}",
            "grounded": True,
            "citations": citations,
            "note": "Deterministic FTS5 extractive result; no vector search or model was used.",
        }

    @app.post("/v1/answer/stream")
    def answer_stream(payload: AnswerRequest):
        async def events() -> AsyncIterator[str]:
            run_id = uuid.uuid4().hex
            yield _sse(
                "metadata",
                {"run_id": run_id, "mode": "offline-demo", "citations": []},
            )
            answer = (
                "Keen received your question locally. The learning-core demo does not "
                "have a model or retrieval pipeline configured yet, so it cannot provide "
                "a source-grounded answer."
            )
            for word in answer.split(" "):
                yield _sse("delta", {"text": word + " "})
            yield _sse("done", {"run_id": run_id, "finish_reason": "stop"})

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
