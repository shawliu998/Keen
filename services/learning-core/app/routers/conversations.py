from __future__ import annotations

import hashlib
import json
import sqlite3
from base64 import b64decode, urlsafe_b64encode
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from ..answer_service import AnswerService
from ..repositories.conversation_repository import ConversationRepository
from ..retrieval_service import HybridRetrievalService
from ..schemas import (
    ConversationAnswerRequest,
    ConversationCancelRequest,
    ConversationCancelResponse,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationListQuery,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationResponse,
)
from ..services.conversation_answers import (
    ConversationConflictError,
    DurableConversationAnswerService,
)

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


def _encode_cursor(updated_at: str, conversation_id: str, course_id: str | None) -> str:
    payload = json.dumps(
        {
            "version": 1,
            "updatedAt": updated_at,
            "id": conversation_id,
            "courseId": course_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str | None, *, expected_course_id: str | None
) -> tuple[str | None, str | None]:
    if cursor is None:
        return None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(
            b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
        )
        if set(payload) != {"version", "updatedAt", "id", "courseId"}:
            raise ValueError
        if payload["version"] != 1 or payload["courseId"] != expected_course_id:
            raise ValueError
        updated_at = payload["updatedAt"]
        conversation_id = payload["id"]
        if (
            not isinstance(updated_at, str)
            or not updated_at
            or not isinstance(conversation_id, str)
            or not conversation_id
        ):
            raise ValueError
        parsed_updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if parsed_updated_at.tzinfo is None:
            raise ValueError
        if str(UUID(conversation_id)) != conversation_id:
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=422, detail="invalid conversation cursor"
        ) from error
    return updated_at, conversation_id


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _title_from_question(question: str) -> str:
    normalized = " ".join(question.split())
    return normalized if len(normalized) <= 96 else normalized[:95].rstrip() + "…"


def _fingerprint(payload: ConversationCreateRequest) -> str:
    canonical = json.dumps(
        {
            "question": payload.question,
            "scope": {
                "kind": payload.source_scope.kind,
                "courseId": getattr(payload.source_scope, "course_id", None),
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scope_response(kind: str, course_id: str | None) -> dict[str, str]:
    return (
        {"kind": kind}
        if kind == "all_indexed"
        else {
            "kind": kind,
            "courseId": str(course_id),
        }
    )


def _conversation_response(row: dict) -> dict:
    scope_kind = row.get("source_scope_kind")
    if scope_kind not in {"all_indexed", "course"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "conversation_scope_unavailable",
                "message": "This legacy conversation has no explicit source scope.",
                "retryable": False,
            },
        )
    return {
        "id": row["id"],
        "courseId": row["course_id"],
        "title": row["title"],
        "mode": row["mode"],
        "status": row["status"],
        "sourceScope": _scope_response(scope_kind, row["course_id"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "archivedAt": row["archived_at"],
    }


def _conversation_summary_response(row: dict) -> dict:
    scope_kind = row.get("source_scope_kind")
    if scope_kind not in {"all_indexed", "course"}:
        raise HTTPException(status_code=409, detail="conversation scope unavailable")
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "sourceScope": _scope_response(scope_kind, row["course_id"]),
        "courseTitle": row["course_title"],
        "messageCount": row["message_count"],
        "lastMessagePreview": row["last_message_preview"],
        "answerStatus": row["answer_status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _message_response(row: dict) -> dict:
    stored_scope = row.get("source_scope")
    scope_kind = stored_scope.get("kind") if isinstance(stored_scope, dict) else None
    source_course_id = (
        stored_scope.get("course_id") if isinstance(stored_scope, dict) else None
    )
    if scope_kind not in {"all_indexed", "course"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "message_scope_unavailable",
                "message": "This legacy message has no explicit source scope.",
                "retryable": False,
            },
        )
    return {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "sequence": row["sequence"],
        "role": row["role"],
        "status": row["status"],
        "content": row["content"],
        "replyToMessageId": row.get("reply_to_message_id"),
        "sourceScope": _scope_response(scope_kind, source_course_id),
        "retrievalLimit": row.get("retrieval_limit"),
        "modelProvider": row.get("model_provider"),
        "modelName": row.get("model_name"),
        "promptVersion": row.get("prompt_version"),
        "errorCode": row.get("error_code"),
        "errorDetail": row.get("error_detail"),
        "startedAt": row.get("started_at"),
        "finishedAt": row.get("finished_at"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "citations": [
            {
                "citationId": citation["citation_id"],
                "sourceIndex": citation["source_index"],
                "chunkId": citation["chunk_id"],
                "documentId": citation["document_id"],
                "documentVersionId": citation["document_version_id"],
                "chunkContentHash": citation["chunk_content_hash"],
                "documentName": citation["document_name"],
                "pageNumber": citation["page_number"],
                "sectionPath": citation["section_path"],
                "excerpt": citation["excerpt"],
                "bbox": citation["bbox"],
            }
            for citation in row["citations"]
        ],
    }


def _require_conversation(
    repository: ConversationRepository, conversation_id: str
) -> dict:
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.post("", response_model=ConversationCreateResponse, status_code=201)
def create_conversation(
    request: Request, payload: ConversationCreateRequest, response: Response
) -> dict:
    conversation_id = str(payload.id)
    course_id = getattr(payload.source_scope, "course_id", None)
    with request.app.state.database.connection() as connection:
        if (
            course_id is not None
            and connection.execute(
                "SELECT 1 FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            is None
        ):
            raise HTTPException(status_code=404, detail="course not found")
        repository = ConversationRepository(connection)
        try:
            conversation = repository.create_conversation(
                conversation_id=conversation_id,
                title=_title_from_question(payload.question),
                course_id=course_id,
                mode="ask",
                source_scope_kind=payload.source_scope.kind,
                create_payload_fingerprint=_fingerprint(payload),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "conversation_idempotency_conflict",
                    "message": str(error),
                    "retryable": False,
                },
            ) from error
    replayed = bool(conversation.pop("replayed"))
    if replayed:
        response.status_code = 200
    return {"conversation": _conversation_response(conversation), "replayed": replayed}


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    request: Request,
    query: Annotated[ConversationListQuery, Query()],
) -> dict:
    cursor_updated_at, cursor_id = _decode_cursor(
        query.cursor, expected_course_id=query.course_id
    )
    with request.app.state.database.connection() as connection:
        rows = ConversationRepository(connection).list_conversations(
            limit=query.limit + 1,
            cursor_updated_at=cursor_updated_at,
            cursor_id=cursor_id,
            course_id=query.course_id,
        )
    has_more = len(rows) > query.limit
    page = rows[: query.limit]
    next_cursor = (
        _encode_cursor(page[-1]["updated_at"], page[-1]["id"], query.course_id)
        if has_more and page
        else None
    )
    return {
        "conversations": [_conversation_summary_response(row) for row in page],
        "nextCursor": next_cursor,
    }


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(request: Request, conversation_id: str) -> dict:
    with request.app.state.database.connection() as connection:
        return _conversation_response(
            _require_conversation(ConversationRepository(connection), conversation_id)
        )


@router.get(
    "/{conversation_id}/messages", response_model=ConversationMessageListResponse
)
def list_messages(request: Request, conversation_id: str) -> dict:
    with request.app.state.database.connection() as connection:
        repository = ConversationRepository(connection)
        _require_conversation(repository, conversation_id)
        return {
            "messages": [
                _message_response(message)
                for message in repository.list_messages(conversation_id)
            ]
        }


@router.get(
    "/{conversation_id}/messages/{message_id}",
    response_model=ConversationMessageResponse,
)
def get_message(request: Request, conversation_id: str, message_id: str) -> dict:
    with request.app.state.database.connection() as connection:
        message = ConversationRepository(connection).get_message(message_id)
        if message is None or message["conversation_id"] != conversation_id:
            raise HTTPException(status_code=404, detail="message not found")
        return _message_response(message)


@router.post("/{conversation_id}/answers/stream")
async def stream_answer(
    request: Request, conversation_id: str, payload: ConversationAnswerRequest
) -> StreamingResponse:
    course_id = getattr(payload.source_scope, "course_id", None)
    with request.app.state.database.connection() as connection:
        repository = ConversationRepository(connection)
        conversation = _require_conversation(repository, conversation_id)
        if (
            conversation.get("source_scope_kind") != payload.source_scope.kind
            or conversation.get("course_id") != course_id
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "conversation_scope_conflict",
                    "message": "The answer scope does not match this conversation.",
                    "retryable": False,
                },
            )
        if (
            course_id is not None
            and connection.execute(
                "SELECT 1 FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            is None
        ):
            raise HTTPException(status_code=404, detail="course not found")

    answer_service = AnswerService(
        request.app.state.database,
        request.app.state.settings,
        HybridRetrievalService(
            request.app.state.database,
            request.app.state.settings,
            provider_factory=request.app.state.embedding_provider_factory,
        ),
        provider_factory=request.app.state.chat_provider_factory,
    )
    durable = DurableConversationAnswerService(
        request.app.state.database,
        answer_service,
        request.app.state.conversation_answer_runtime,
    )
    try:
        assistant, persisted_user_message_id, replayed = durable.begin_answer(
            conversation_id=conversation_id,
            user_message_id=str(payload.user_message_id),
            assistant_message_id=str(payload.assistant_message_id),
            question=payload.question,
            source_scope_kind=payload.source_scope.kind,
            source_course_id=course_id,
            retrieval_limit=payload.retrieval_limit,
            idempotency_key=payload.idempotency_key,
        )
    except ConversationConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "answer_idempotency_conflict",
                "message": str(error),
                "retryable": False,
            },
        ) from error
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "answer_integrity_conflict",
                "message": "The answer turn conflicted with persisted conversation state.",
                "retryable": False,
            },
        ) from error

    if replayed and assistant["status"] in {"pending", "streaming"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "answer_in_progress",
                "message": "This answer is already in progress. Read its saved status before retrying.",
                "retryable": True,
                "outcomeMayBeDurable": True,
            },
        )

    async def events() -> AsyncIterator[str]:
        async for event in durable.stream(
            conversation_id=conversation_id,
            assistant_message=assistant,
            question=payload.question,
            source_course_id=course_id,
            retrieval_limit=payload.retrieval_limit,
            user_message_id=persisted_user_message_id,
            replayed=replayed,
            is_disconnected=request.is_disconnected,
        ):
            yield _sse(event.event, event.data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{conversation_id}/messages/{message_id}/cancel",
    response_model=ConversationCancelResponse,
)
async def cancel_message(
    request: Request,
    conversation_id: str,
    message_id: str,
    payload: ConversationCancelRequest,
) -> dict:
    with request.app.state.database.connection() as connection:
        repository = ConversationRepository(connection)
        try:
            message = repository.cancel_message(
                message_id,
                conversation_id,
                payload.idempotency_key,
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail="message not found") from error
        except ValueError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "answer_cancel_conflict",
                    "message": str(error),
                    "retryable": False,
                },
            ) from error
    replayed = bool(message.pop("cancel_replayed"))
    await request.app.state.conversation_answer_runtime.signal_cancel(message_id)
    return {"message": _message_response(message), "replayed": replayed}
