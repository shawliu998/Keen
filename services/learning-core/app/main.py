from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from . import __version__
from .auth import require_session
from .database import Database
from .repository import LearningRepository
from .schemas import (
    AnswerRequest,
    Course,
    DemoState,
    HealthResponse,
    MasteryAttempt,
    MasteryState,
    MasteryUpdate,
    StudyTask,
    TaskCreate,
    TaskUpdate,
)
from .settings import Settings

logger = logging.getLogger("keen.learning_core")


def _repository(request: Request) -> Iterator[LearningRepository]:
    with request.app.state.database.connection() as connection:
        yield LearningRepository(connection)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        applied = app.state.database.migrate()
        if settings.seed_demo:
            app.state.database.seed_demo()
        logger.info("database_ready", extra={"migrations_applied": applied})
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
