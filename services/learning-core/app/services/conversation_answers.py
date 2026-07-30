from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable

from ..answer_service import AnswerEvent, AnswerService
from ..database import Database
from ..repositories.conversation_repository import ConversationRepository

DisconnectProbe = Callable[[], Awaitable[bool]]


class ConversationConflictError(RuntimeError):
    """The durable command identity was reused for different state."""


class ConversationAnswerRuntime:
    """Process-local cancellation signals; SQLite remains the authority."""

    def __init__(self) -> None:
        self._signals: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def register(self, message_id: str) -> asyncio.Event:
        async with self._lock:
            signal = self._signals.get(message_id)
            if signal is None:
                signal = asyncio.Event()
                self._signals[message_id] = signal
            return signal

    async def signal_cancel(self, message_id: str) -> None:
        async with self._lock:
            signal = self._signals.get(message_id)
            if signal is not None:
                signal.set()

    async def unregister(self, message_id: str, signal: asyncio.Event) -> None:
        async with self._lock:
            if self._signals.get(message_id) is signal:
                self._signals.pop(message_id, None)


class DurableConversationAnswerService:
    """Persist one Conversation turn while delegating generation to AnswerService."""

    def __init__(
        self,
        database: Database,
        answer_service: AnswerService,
        runtime: ConversationAnswerRuntime,
    ) -> None:
        self._database = database
        self._answer_service = answer_service
        self._runtime = runtime

    def begin_answer(
        self,
        *,
        conversation_id: str,
        user_message_id: str,
        assistant_message_id: str,
        question: str,
        source_scope_kind: str,
        source_course_id: str | None,
        retrieval_limit: int,
        idempotency_key: str,
    ) -> tuple[dict, str, bool]:
        try:
            with self._database.connection() as connection:
                turn = ConversationRepository(connection).create_turn(
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                    question=question,
                    source_scope_kind=source_scope_kind,
                    source_course_id=source_course_id,
                    retrieval_limit=retrieval_limit,
                    idempotency_key=idempotency_key,
                    prompt_version="grounded-answer-v1",
                )
                user_message = turn["user_message"]
                assistant_message = turn["assistant_message"]
                if (
                    user_message is None or assistant_message is None
                ):  # pragma: no cover
                    raise RuntimeError("durable turn did not persist")
                return (
                    assistant_message,
                    str(user_message["id"]),
                    bool(turn["replayed"]),
                )
        except ValueError as error:
            raise ConversationConflictError(str(error)) from error

    async def stream(
        self,
        *,
        conversation_id: str,
        assistant_message: dict,
        question: str,
        source_course_id: str | None,
        retrieval_limit: int,
        user_message_id: str,
        replayed: bool,
        is_disconnected: DisconnectProbe,
    ) -> AsyncIterator[AnswerEvent]:
        assistant_id = str(assistant_message["id"])
        if replayed:
            async for event in self._replay(assistant_message, user_message_id):
                yield event
            return

        signal = await self._runtime.register(assistant_id)
        partial = ""
        citations: list[dict] = []
        provider: dict[str, object] | None = None
        terminal = False
        disconnected = False

        async def stopped() -> bool:
            nonlocal disconnected
            if signal.is_set():
                return True
            disconnected = await is_disconnected()
            return disconnected

        try:
            self._transition(assistant_id, conversation_id, "streaming")
            async for event in self._answer_service.stream(
                question=question,
                course_id=source_course_id,
                conversation_id=conversation_id,
                retrieval_limit=retrieval_limit,
                is_disconnected=stopped,
                include_durable_identity=True,
            ):
                if signal.is_set():
                    break
                data = dict(event.data)
                if event.event == "metadata":
                    provider_value = data.get("provider")
                    provider = (
                        provider_value if isinstance(provider_value, dict) else None
                    )
                    data.update(
                        {
                            "runId": assistant_id,
                            "conversationId": conversation_id,
                            "userMessageId": user_message_id,
                            "assistantMessageId": assistant_id,
                        }
                    )
                elif event.event == "delta":
                    partial += str(data["text"])
                elif event.event == "citation":
                    if any(
                        citation["sourceIndex"] == data["sourceIndex"]
                        for citation in citations
                    ):
                        continue
                    citation_id = f"{assistant_id}:c{len(citations) + 1}"
                    data["citationId"] = citation_id
                    citations.append(data)
                elif event.event == "done":
                    self._complete(
                        assistant_id,
                        conversation_id,
                        partial,
                        citations,
                        provider,
                    )
                    data["runId"] = assistant_id
                    data["citationCount"] = len(citations)
                    data["grounded"] = bool(citations)
                    terminal = True
                elif event.event == "error":
                    self._fail(
                        assistant_id,
                        conversation_id,
                        partial,
                        code=str(data["code"]),
                        detail=str(data["message"]),
                    )
                    data["runId"] = assistant_id
                    terminal = True
                yield AnswerEvent(event.event, data)
                if terminal:
                    return
        except asyncio.CancelledError:
            disconnected = True
            raise
        finally:
            await self._runtime.unregister(assistant_id, signal)
            if not terminal:
                current = self._get_message(assistant_id)
                if current is not None and current["status"] in {
                    "pending",
                    "streaming",
                }:
                    detail = (
                        "The answer stream disconnected before completion."
                        if disconnected
                        else "The answer was interrupted before completion."
                    )
                    with contextlib.suppress(ValueError, LookupError, sqlite3.Error):
                        self._transition(
                            assistant_id,
                            conversation_id,
                            "interrupted",
                            content=partial,
                            error_code="client_disconnected"
                            if disconnected
                            else "interrupted",
                            error_detail=detail,
                        )

    async def _replay(
        self, message: dict, user_message_id: str
    ) -> AsyncIterator[AnswerEvent]:
        message_id = str(message["id"])
        conversation_id = str(message["conversation_id"])
        yield AnswerEvent(
            "metadata",
            {
                "runId": message_id,
                "conversationId": conversation_id,
                "userMessageId": user_message_id,
                "assistantMessageId": message_id,
                "provider": _provider_from_message(message),
                "retrievalLimit": message["retrieval_limit"],
                "replayed": True,
            },
        )
        status = str(message["status"])
        if status == "completed":
            if message["content"]:
                yield AnswerEvent("delta", {"text": message["content"]})
            for citation in message["citations"]:
                yield AnswerEvent("citation", _citation_event(citation))
            yield AnswerEvent(
                "done",
                {
                    "runId": message_id,
                    "finishReason": "stop",
                    "grounded": bool(message["citations"]),
                    "citationCount": len(message["citations"]),
                    "citationValidation": "structural_only",
                },
            )
            return
        yield AnswerEvent(
            "error",
            {
                "runId": message_id,
                "code": message.get("error_code") or status,
                "message": message.get("error_detail")
                or "The saved answer did not complete.",
                "retryable": status in {"failed", "interrupted"},
            },
        )

    def _get_message(self, message_id: str) -> dict | None:
        with self._database.connection() as connection:
            return ConversationRepository(connection).get_message(message_id)

    def _transition(
        self,
        message_id: str,
        conversation_id: str,
        status: str,
        *,
        content: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> dict:
        with self._database.connection() as connection:
            return ConversationRepository(connection).transition_message(
                message_id,
                conversation_id=conversation_id,
                status=status,
                content=content,
                error_code=error_code,
                error_detail=error_detail,
            )

    def _fail(
        self,
        message_id: str,
        conversation_id: str,
        content: str,
        *,
        code: str,
        detail: str,
    ) -> None:
        self._transition(
            message_id,
            conversation_id,
            "failed",
            content=content,
            error_code=code,
            error_detail=detail,
        )

    def _complete(
        self,
        message_id: str,
        conversation_id: str,
        content: str,
        citations: list[dict],
        provider: dict[str, object] | None,
    ) -> None:
        with self._database.connection() as connection:
            ConversationRepository(connection).complete_message(
                message_id=message_id,
                conversation_id=conversation_id,
                content=content,
                citations=[_citation_input(citation) for citation in citations],
                model_provider=(str(provider["kind"]) if provider else None),
                model_name=(str(provider["model"]) if provider else None),
                prompt_version="grounded-answer-v1",
            )


def _provider_from_message(message: dict) -> dict[str, object] | None:
    # The durable schema stores provider/model, but not the provider protocol
    # version. Returning a fabricated version would make a replay less truthful.
    return None


def _citation_input(citation: dict) -> dict:
    return {
        "id": citation["citationId"],
        "source_index": citation["sourceIndex"],
        "document_id": citation["documentId"],
        "document_version_id": citation["documentVersionId"],
        "chunk_id": citation["chunkId"],
        "chunk_content_hash": citation["chunkContentHash"],
        "document_name": citation["documentName"],
        "page_number": citation["pageNumber"],
        "section_path": citation["sectionPath"],
        "quote": citation["excerpt"],
        "bbox": citation.get("bbox"),
    }


def _citation_event(citation: dict) -> dict[str, object]:
    return {
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
