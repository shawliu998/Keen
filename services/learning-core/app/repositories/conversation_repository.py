from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from typing import Literal, NotRequired, TypedDict

from . import JsonValue, dump_json, load_json, write_scope


class CitationInput(TypedDict):
    id: str
    document_id: str
    quote: str
    source_index: NotRequired[int]
    chunk_id: NotRequired[str | None]
    document_version_id: NotRequired[str]
    chunk_content_hash: NotRequired[str]
    document_name: NotRequired[str]
    page_number: NotRequired[int | None]
    section_path: NotRequired[list[str]]
    bbox: NotRequired[dict[str, JsonValue] | None]
    metadata: NotRequired[dict[str, JsonValue]]


class AttachmentInput(TypedDict):
    id: str
    document_id: str
    display_name: str


_MESSAGE_TRANSITIONS = {
    "pending": frozenset(
        {"streaming", "completed", "failed", "cancelled", "interrupted"}
    ),
    "streaming": frozenset({"completed", "failed", "cancelled", "interrupted"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
}

SourceScopeKind = Literal["all_indexed", "course"]


class ConversationCreateConflictError(ValueError):
    """A conversation id was already created for a different payload."""


class TurnIdempotencyConflictError(ValueError):
    """A turn idempotency key was reused for a different turn payload."""


class MessageTransitionConflictError(ValueError):
    """A compare-and-swap message transition lost or targeted a terminal row."""


class MessageCancellationConflictError(ValueError):
    """A cancel key cannot be applied to the requested message state."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _conversation_fingerprint(
    *, title: str, course_id: str | None, mode: str, source_scope_kind: str
) -> str:
    payload = dump_json(
        {
            "course_id": course_id,
            "mode": mode,
            "source_scope_kind": source_scope_kind,
            "title": title,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_scope(kind: str, course_id: str | None) -> SourceScopeKind:
    if kind not in {"all_indexed", "course"}:
        raise ValueError("invalid source scope kind")
    if (kind == "all_indexed") != (course_id is None):
        raise ValueError("source scope does not match course")
    return kind  # type: ignore[return-value]


def _source_scope(kind: str | None, course_id: str | None) -> dict | None:
    if kind is None:
        return None
    return {"kind": kind, "course_id": course_id}


class ConversationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_conversation(
        self,
        *,
        conversation_id: str,
        title: str,
        course_id: str | None = None,
        mode: str = "ask",
        source_scope_kind: SourceScopeKind | None = None,
        create_payload_fingerprint: str | None = None,
        commit: bool = True,
    ) -> dict:
        if mode not in {"ask", "teach", "study", "review", "plan"}:
            raise ValueError("invalid conversation mode")
        scope_kind = _validate_scope(
            source_scope_kind or ("course" if course_id is not None else "all_indexed"),
            course_id,
        )
        canonical_fingerprint = _conversation_fingerprint(
            title=title,
            course_id=course_id,
            mode=mode,
            source_scope_kind=scope_kind,
        )
        fingerprint = create_payload_fingerprint or canonical_fingerprint
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("invalid conversation create fingerprint")
        now = _now()
        with write_scope(self.connection, commit=commit):
            existing = self._raw_conversation(conversation_id)
            if existing is not None:
                expected = (
                    course_id,
                    title,
                    mode,
                    scope_kind,
                    fingerprint,
                )
                actual = tuple(
                    existing[key]
                    for key in (
                        "course_id",
                        "title",
                        "mode",
                        "source_scope_kind",
                        "create_payload_fingerprint",
                    )
                )
                if actual != expected:
                    raise ConversationCreateConflictError(
                        "conversation id was reused with a different create payload"
                    )
                replay = self.get_conversation(conversation_id)
                if replay is None:  # pragma: no cover
                    raise RuntimeError("idempotent conversation disappeared")
                return {**replay, "replayed": True}
            self.connection.execute(
                """
                INSERT INTO conversations
                    (id, course_id, title, mode, status, created_at, updated_at,
                     archived_at, source_scope_kind, create_payload_fingerprint)
                VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?, ?)
                """,
                (
                    conversation_id,
                    course_id,
                    title,
                    mode,
                    now,
                    now,
                    scope_kind,
                    fingerprint,
                ),
            )
        conversation = self.get_conversation(conversation_id)
        if conversation is None:  # pragma: no cover - protected by INSERT
            raise RuntimeError("conversation insert did not persist")
        return {**conversation, "replayed": False}

    def _raw_conversation(self, conversation_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT id, course_id, title, mode, status, created_at, updated_at,
                   archived_at, source_scope_kind, create_payload_fingerprint
            FROM conversations WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()

    def get_conversation(self, conversation_id: str) -> dict | None:
        row = self._raw_conversation(conversation_id)
        if row is None:
            return None
        return {
            "id": row["id"],
            "course_id": row["course_id"],
            "source_scope_kind": row["source_scope_kind"],
            "title": row["title"],
            "mode": row["mode"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "archived_at": row["archived_at"],
            "source_scope": _source_scope(row["source_scope_kind"], row["course_id"]),
        }

    def list_conversations(
        self,
        *,
        status: str = "active",
        limit: int = 25,
        cursor_updated_at: str | None = None,
        cursor_id: str | None = None,
        course_id: str | None = None,
    ) -> list[dict]:
        if status not in {"active", "archived"}:
            raise ValueError("invalid conversation status")
        if not 1 <= limit <= 51:
            raise ValueError("conversation list limit must be between 1 and 51")
        if (cursor_updated_at is None) != (cursor_id is None):
            raise ValueError("conversation cursor is incomplete")
        filters = ["c.status = ?", "c.source_scope_kind IS NOT NULL"]
        parameters: list[object] = [status]
        if course_id is not None:
            filters.extend(["c.source_scope_kind = 'course'", "c.course_id = ?"])
            parameters.append(course_id)
        if cursor_updated_at is not None and cursor_id is not None:
            filters.append("(c.updated_at < ? OR (c.updated_at = ? AND c.id < ?))")
            parameters.extend([cursor_updated_at, cursor_updated_at, cursor_id])
        parameters.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT c.id, c.course_id, c.source_scope_kind, c.title, c.mode,
                   c.status, c.created_at, c.updated_at, c.archived_at,
                   course.title AS course_title,
                   (SELECT COUNT(*) FROM messages counted
                    WHERE counted.conversation_id = c.id) AS message_count,
                   (SELECT substr(latest.content, 1, 160) FROM messages latest
                    WHERE latest.conversation_id = c.id
                    ORDER BY latest.sequence DESC, latest.id DESC LIMIT 1) AS last_message_preview,
                   (SELECT assistant.status FROM messages assistant
                    WHERE assistant.conversation_id = c.id AND assistant.role = 'assistant'
                    ORDER BY assistant.sequence DESC, assistant.id DESC LIMIT 1) AS answer_status
            FROM conversations c
            LEFT JOIN courses course ON course.id = c.course_id
            WHERE {" AND ".join(filters)}
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            {
                "id": row["id"],
                "course_id": row["course_id"],
                "source_scope_kind": row["source_scope_kind"],
                "title": row["title"],
                "mode": row["mode"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "archived_at": row["archived_at"],
                "message_count": row["message_count"],
                "last_message_preview": row["last_message_preview"],
                "answer_status": row["answer_status"],
                "course_title": row["course_title"],
                "source_scope": _source_scope(
                    row["source_scope_kind"], row["course_id"]
                ),
            }
            for row in rows
        ]

    @staticmethod
    def _public_citation_input(citation: CitationInput) -> dict:
        return {
            "citation_id": citation["id"],
            "source_index": citation.get("source_index"),
            "chunk_id": citation.get("chunk_id"),
            "document_id": citation["document_id"],
            "document_version_id": citation.get("document_version_id"),
            "chunk_content_hash": citation.get("chunk_content_hash"),
            "document_name": citation.get("document_name"),
            "page_number": citation.get("page_number"),
            "section_path": citation.get("section_path"),
            "excerpt": citation["quote"],
            "bbox": citation.get("bbox"),
        }

    @staticmethod
    def _citation_dict(citation: sqlite3.Row) -> dict:
        metadata = load_json(citation["metadata_json"])
        legacy_metadata = metadata if isinstance(metadata, dict) else {}
        section_path = (
            load_json(citation["section_path_json"])
            if citation["section_path_json"] is not None
            else legacy_metadata.get("section_path")
        )
        bbox = (
            load_json(citation["geometry_json"])
            if citation["geometry_json"] is not None
            else legacy_metadata.get("bbox")
        )
        return {
            "citation_id": citation["id"],
            "source_index": citation["source_index"],
            "chunk_id": citation["chunk_id"],
            "document_id": citation["document_id"],
            "document_version_id": citation["document_version_id"],
            "chunk_content_hash": citation["chunk_content_hash"],
            "document_name": citation["document_name_snapshot"],
            "page_number": citation["page_number"],
            "section_path": section_path,
            "excerpt": citation["quote"],
            "bbox": bbox,
        }

    def _insert_citation(
        self, message_id: str, ordinal: int, citation: CitationInput
    ) -> None:
        metadata = citation.get("metadata", {})
        section_path = citation.get("section_path")
        bbox = citation.get("bbox")
        if not isinstance(metadata, dict):
            raise ValueError("citation metadata must be an object")
        if section_path is None or any(
            not isinstance(segment, str) for segment in section_path
        ):
            raise ValueError("citation section path must be a string array")
        if bbox is not None and not isinstance(bbox, dict):
            raise ValueError("citation geometry must be an object or null")
        required = (
            citation.get("source_index"),
            citation.get("chunk_id"),
            citation.get("document_version_id"),
            citation.get("chunk_content_hash"),
            citation.get("document_name"),
            citation.get("page_number"),
        )
        if any(value is None for value in required):
            raise ValueError("citation durable evidence is required")
        self.connection.execute(
            """
            INSERT INTO message_citations
                (id, message_id, ordinal, document_id, chunk_id,
                 page_number, quote, metadata_json, source_index,
                 document_version_id, chunk_content_hash,
                 document_name_snapshot, section_path_json, geometry_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                citation["id"],
                message_id,
                ordinal,
                citation["document_id"],
                citation.get("chunk_id"),
                citation.get("page_number"),
                citation["quote"],
                dump_json(metadata),
                citation.get("source_index"),
                citation.get("document_version_id"),
                citation.get("chunk_content_hash"),
                citation.get("document_name"),
                dump_json(section_path),
                dump_json(bbox) if bbox is not None else None,
            ),
        )

    def create_turn(
        self,
        *,
        conversation_id: str,
        user_message_id: str,
        assistant_message_id: str,
        question: str,
        source_scope_kind: SourceScopeKind,
        source_course_id: str | None,
        retrieval_limit: int,
        idempotency_key: str,
        model_provider: str | None = None,
        model_name: str | None = None,
        prompt_version: str | None = None,
        commit: bool = True,
    ) -> dict:
        if not 1 <= len(idempotency_key) <= 240:
            raise ValueError("turn idempotency key must contain 1 to 240 characters")
        if not 6 <= retrieval_limit <= 10:
            raise ValueError("retrieval limit must be between 6 and 10")
        _validate_scope(source_scope_kind, source_course_id)
        user_key = f"{idempotency_key}:user"
        assistant_key = f"{idempotency_key}:assistant"
        now = _now()
        with write_scope(self.connection, commit=commit):
            conversation = self._raw_conversation(conversation_id)
            if conversation is None:
                raise LookupError("conversation not found")
            if conversation["status"] != "active":
                raise ValueError("conversation is not active")
            if (
                conversation["source_scope_kind"] != source_scope_kind
                or conversation["course_id"] != source_course_id
            ):
                raise ValueError("turn source scope does not match conversation")
            existing = self.connection.execute(
                """
                SELECT id, role, status, content, reply_to_message_id,
                       source_scope_kind, source_course_id, retrieval_limit,
                       model_provider, model_name, prompt_version, idempotency_key
                FROM messages
                WHERE conversation_id = ?
                  AND idempotency_key IN (?, ?)
                ORDER BY sequence
                """,
                (conversation_id, user_key, assistant_key),
            ).fetchall()
            if existing:
                if len(existing) != 2:
                    raise TurnIdempotencyConflictError(
                        "turn idempotency replay is incomplete"
                    )
                by_key = {str(row["idempotency_key"]): row for row in existing}
                user = by_key.get(user_key)
                assistant = by_key.get(assistant_key)
                matches = (
                    user is not None
                    and assistant is not None
                    and user["id"] == user_message_id
                    and assistant["id"] == assistant_message_id
                    and user["role"] == "user"
                    and user["status"] == "completed"
                    and user["content"] == question
                    and assistant["role"] == "assistant"
                    and assistant["reply_to_message_id"] == user["id"]
                    and assistant["source_scope_kind"] == source_scope_kind
                    and assistant["source_course_id"] == source_course_id
                    and assistant["retrieval_limit"] == retrieval_limit
                    and assistant["prompt_version"] == prompt_version
                )
                if not matches:
                    raise TurnIdempotencyConflictError(
                        "turn idempotency key was reused with a different payload"
                    )
                return {
                    "user_message": self.get_message(str(user["id"])),
                    "assistant_message": self.get_message(str(assistant["id"])),
                    "replayed": True,
                }

            next_sequence = int(
                self.connection.execute(
                    "SELECT COALESCE(MAX(sequence), -1) + 1 FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0]
            )
            self.connection.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, sequence, role, status, content,
                     idempotency_key, created_at, updated_at, completed_at,
                     reply_to_message_id, source_scope_kind, source_course_id,
                     retrieval_limit, started_at, finished_at)
                VALUES (?, ?, ?, 'user', 'completed', ?, ?, ?, ?, ?, NULL,
                        ?, ?, NULL, ?, ?)
                """,
                (
                    user_message_id,
                    conversation_id,
                    next_sequence,
                    question,
                    user_key,
                    now,
                    now,
                    now,
                    source_scope_kind,
                    source_course_id,
                    now,
                    now,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, sequence, role, status, content,
                     model_provider, model_name, prompt_version, idempotency_key,
                     created_at, updated_at, reply_to_message_id,
                     source_scope_kind, source_course_id, retrieval_limit,
                     started_at, finished_at)
                VALUES (?, ?, ?, 'assistant', 'pending', '', ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, NULL, NULL)
                """,
                (
                    assistant_message_id,
                    conversation_id,
                    next_sequence + 1,
                    model_provider,
                    model_name,
                    prompt_version,
                    assistant_key,
                    now,
                    now,
                    user_message_id,
                    source_scope_kind,
                    source_course_id,
                    retrieval_limit,
                ),
            )
            self.connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return {
            "user_message": self.get_message(user_message_id),
            "assistant_message": self.get_message(assistant_message_id),
            "replayed": False,
        }

    def append_message(
        self,
        *,
        message_id: str,
        conversation_id: str,
        role: str,
        content: str,
        status: str,
        idempotency_key: str | None = None,
        citations: list[CitationInput] | None = None,
        attachments: list[AttachmentInput] | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        prompt_version: str | None = None,
        reply_to_message_id: str | None = None,
        source_scope_kind: SourceScopeKind | None = None,
        source_course_id: str | None = None,
        retrieval_limit: int | None = None,
        commit: bool = True,
    ) -> dict:
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("invalid message role")
        if status not in _MESSAGE_TRANSITIONS:
            raise ValueError("invalid message status")
        citations = citations or []
        attachments = attachments or []
        now = _now()
        with write_scope(self.connection, commit=commit):
            conversation = self._raw_conversation(conversation_id)
            if conversation is None:
                raise LookupError("conversation not found")
            effective_scope = _validate_scope(
                source_scope_kind or str(conversation["source_scope_kind"]),
                source_course_id
                if source_scope_kind is not None
                else conversation["course_id"],
            )
            effective_course_id = (
                source_course_id
                if source_scope_kind is not None
                else conversation["course_id"]
            )
            if (
                effective_scope != conversation["source_scope_kind"]
                or effective_course_id != conversation["course_id"]
            ):
                raise ValueError("message source scope does not match conversation")
            if idempotency_key is not None:
                existing = self.connection.execute(
                    """SELECT id, role, status, content, model_provider, model_name,
                              prompt_version, reply_to_message_id,
                              source_scope_kind, source_course_id, retrieval_limit
                       FROM messages
                       WHERE conversation_id = ? AND idempotency_key = ?""",
                    (conversation_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    expected = (
                        role,
                        status,
                        content,
                        model_provider,
                        model_name,
                        prompt_version,
                        reply_to_message_id,
                        effective_scope,
                        effective_course_id,
                        retrieval_limit,
                    )
                    actual = tuple(
                        existing[key]
                        for key in (
                            "role",
                            "status",
                            "content",
                            "model_provider",
                            "model_name",
                            "prompt_version",
                            "reply_to_message_id",
                            "source_scope_kind",
                            "source_course_id",
                            "retrieval_limit",
                        )
                    )
                    if actual != expected:
                        raise ValueError(
                            "idempotency key was reused with a different message payload"
                        )
                    replay = self.get_message(existing["id"])
                    if replay is None:  # pragma: no cover
                        raise RuntimeError("idempotent message disappeared")
                    expected_citations = [
                        self._public_citation_input(citation) for citation in citations
                    ]
                    expected_attachments = [
                        {
                            "id": attachment["id"],
                            "document_id": attachment["document_id"],
                            "display_name": attachment["display_name"],
                        }
                        for attachment in attachments
                    ]
                    if (
                        replay["citations"] != expected_citations
                        or replay["attachments"] != expected_attachments
                    ):
                        raise ValueError(
                            "idempotency key was reused with different message evidence"
                        )
                    return replay
            sequence = int(
                self.connection.execute(
                    "SELECT COALESCE(MAX(sequence), -1) + 1 FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0]
            )
            self.connection.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, sequence, role, status, content,
                     model_provider, model_name, prompt_version, error_code,
                     error_detail, idempotency_key, created_at, updated_at, completed_at,
                     reply_to_message_id, source_scope_kind, source_course_id,
                     retrieval_limit, started_at, finished_at, cancel_idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    message_id,
                    conversation_id,
                    sequence,
                    role,
                    status,
                    content,
                    model_provider,
                    model_name,
                    prompt_version,
                    idempotency_key,
                    now,
                    now,
                    now if status == "completed" else None,
                    reply_to_message_id,
                    effective_scope,
                    effective_course_id,
                    retrieval_limit,
                    now if status in {"streaming", "completed"} else None,
                    now
                    if status in {"completed", "failed", "cancelled", "interrupted"}
                    else None,
                ),
            )
            for ordinal, citation in enumerate(citations):
                self._insert_citation(message_id, ordinal, citation)
            for ordinal, attachment in enumerate(attachments):
                self.connection.execute(
                    """
                    INSERT INTO message_attachments
                        (id, message_id, ordinal, document_id, display_name)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        attachment["id"],
                        message_id,
                        ordinal,
                        attachment["document_id"],
                        attachment["display_name"],
                    ),
                )
            self.connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        message = self.get_message(message_id)
        if message is None:  # pragma: no cover - protected by INSERT
            raise RuntimeError("message insert did not persist")
        return message

    def get_message(self, message_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, conversation_id, sequence, role, status, content,
                   model_provider, model_name, prompt_version, error_code,
                   error_detail, idempotency_key, created_at,
                   updated_at, completed_at, reply_to_message_id,
                   source_scope_kind, source_course_id, retrieval_limit,
                   started_at, finished_at, cancel_idempotency_key
            FROM messages WHERE id = ?
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            return None
        message = {
            key: row[key]
            for key in row.keys()
            if key not in {"source_scope_kind", "source_course_id"}
        }
        message["source_scope"] = _source_scope(
            row["source_scope_kind"], row["source_course_id"]
        )
        citation_rows = self.connection.execute(
            """
            SELECT id, document_id, chunk_id, page_number, quote, metadata_json,
                   source_index, document_version_id, chunk_content_hash,
                   document_name_snapshot, section_path_json, geometry_json
            FROM message_citations WHERE message_id = ? ORDER BY ordinal
            """,
            (message_id,),
        ).fetchall()
        message["citations"] = [
            self._citation_dict(citation) for citation in citation_rows
        ]
        message["attachments"] = [
            dict(attachment)
            for attachment in self.connection.execute(
                """
                SELECT id, document_id, display_name FROM message_attachments
                WHERE message_id = ? ORDER BY ordinal
                """,
                (message_id,),
            )
        ]
        return message

    def list_messages(self, conversation_id: str) -> list[dict]:
        ids = self.connection.execute(
            "SELECT id FROM messages WHERE conversation_id = ? ORDER BY sequence",
            (conversation_id,),
        ).fetchall()
        return [message for row in ids if (message := self.get_message(row["id"]))]

    def transition_message(
        self,
        message_id: str,
        *,
        status: str,
        conversation_id: str | None = None,
        expected_statuses: tuple[str, ...] | None = None,
        content: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        commit: bool = True,
    ) -> dict:
        now = _now()
        with write_scope(self.connection, commit=commit):
            current = self.connection.execute(
                "SELECT conversation_id, status FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if current is None:
                raise LookupError("message not found")
            if (
                conversation_id is not None
                and current["conversation_id"] != conversation_id
            ):
                raise LookupError("message not found in conversation")
            allowed_current = expected_statuses or (str(current["status"]),)
            if current["status"] not in allowed_current:
                raise MessageTransitionConflictError(
                    "message status changed before transition"
                )
            if status not in _MESSAGE_TRANSITIONS[str(current["status"])]:
                raise MessageTransitionConflictError(
                    f"invalid message transition: {current['status']} -> {status}"
                )
            placeholders = ",".join("?" for _ in allowed_current)
            cursor = self.connection.execute(
                f"""
                UPDATE messages
                SET status = ?, content = COALESCE(?, content), error_code = ?,
                    error_detail = ?, updated_at = ?, completed_at = ?,
                    started_at = CASE
                        WHEN ? = 'streaming' THEN COALESCE(started_at, ?)
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN ? IN ('completed', 'failed', 'cancelled', 'interrupted')
                        THEN ? ELSE NULL
                    END
                WHERE id = ? AND conversation_id = ?
                  AND status IN ({placeholders})
                """,
                (
                    status,
                    content,
                    error_code,
                    error_detail,
                    now,
                    now if status == "completed" else None,
                    status,
                    now,
                    status,
                    now,
                    message_id,
                    current["conversation_id"],
                    *allowed_current,
                ),
            )
            if cursor.rowcount != 1:
                raise MessageTransitionConflictError(
                    "message status changed before transition"
                )
            self.connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, current["conversation_id"]),
            )
        result = self.get_message(message_id)
        if result is None:  # pragma: no cover
            raise RuntimeError("message disappeared")
        return result

    def complete_message(
        self,
        message_id: str,
        *,
        conversation_id: str,
        content: str,
        citations: list[CitationInput],
        model_provider: str | None = None,
        model_name: str | None = None,
        prompt_version: str | None = None,
        expected_statuses: tuple[str, ...] = ("pending", "streaming"),
        commit: bool = True,
    ) -> dict:
        now = _now()
        with write_scope(self.connection, commit=commit):
            placeholders = ",".join("?" for _ in expected_statuses)
            cursor = self.connection.execute(
                f"""
                UPDATE messages
                SET status = 'completed', content = ?, error_code = NULL,
                    error_detail = NULL, updated_at = ?, completed_at = ?,
                    started_at = COALESCE(started_at, ?), finished_at = ?,
                    model_provider = COALESCE(?, model_provider),
                    model_name = COALESCE(?, model_name),
                    prompt_version = COALESCE(?, prompt_version)
                WHERE id = ? AND conversation_id = ? AND role = 'assistant'
                  AND status IN ({placeholders})
                """,
                (
                    content,
                    now,
                    now,
                    now,
                    now,
                    model_provider,
                    model_name,
                    prompt_version,
                    message_id,
                    conversation_id,
                    *expected_statuses,
                ),
            )
            if cursor.rowcount != 1:
                raise MessageTransitionConflictError(
                    "assistant message was not completable"
                )
            for ordinal, citation in enumerate(citations):
                self._insert_citation(message_id, ordinal, citation)
            self.connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        result = self.get_message(message_id)
        if result is None:  # pragma: no cover
            raise RuntimeError("completed message disappeared")
        return result

    def cancel_message(
        self,
        message_id: str,
        conversation_id: str,
        cancel_key: str,
        *,
        commit: bool = True,
    ) -> dict:
        if not 1 <= len(cancel_key) <= 256:
            raise ValueError("cancel key must contain 1 to 256 characters")
        now = _now()
        with write_scope(self.connection, commit=commit):
            current = self.connection.execute(
                """
                SELECT status, cancel_idempotency_key
                FROM messages WHERE id = ? AND conversation_id = ?
                """,
                (message_id, conversation_id),
            ).fetchone()
            if current is None:
                raise LookupError("message not found in conversation")
            if current["status"] == "cancelled":
                if current["cancel_idempotency_key"] != cancel_key:
                    raise MessageCancellationConflictError(
                        "message was cancelled with a different key"
                    )
                replay = self.get_message(message_id)
                if replay is None:  # pragma: no cover
                    raise RuntimeError("cancelled message disappeared")
                return {**replay, "cancel_replayed": True}
            if current["status"] not in {"pending", "streaming"}:
                raise MessageCancellationConflictError(
                    "terminal message cannot be cancelled"
                )
            cursor = self.connection.execute(
                """
                UPDATE messages
                SET status = 'cancelled', cancel_idempotency_key = ?,
                    error_code = 'cancelled_by_client',
                    error_detail = 'Answer generation was cancelled by the client',
                    updated_at = ?, finished_at = ?, completed_at = NULL
                WHERE id = ? AND conversation_id = ?
                  AND status IN ('pending', 'streaming')
                """,
                (cancel_key, now, now, message_id, conversation_id),
            )
            if cursor.rowcount != 1:
                raise MessageCancellationConflictError(
                    "message status changed before cancellation"
                )
            self.connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        result = self.get_message(message_id)
        if result is None:  # pragma: no cover
            raise RuntimeError("cancelled message disappeared")
        return {**result, "cancel_replayed": False}

    def recover_interrupted_messages(self, *, commit: bool = True) -> list[str]:
        now = _now()
        with write_scope(self.connection, commit=commit):
            rows = self.connection.execute(
                """SELECT id, conversation_id FROM messages
                   WHERE status IN ('pending', 'streaming') ORDER BY id"""
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            if ids:
                self.connection.execute(
                    """
                    UPDATE messages SET status = 'interrupted', updated_at = ?,
                                        error_code = 'process_restarted',
                                        error_detail = 'Message generation was interrupted by restart',
                                        finished_at = ?, completed_at = NULL
                    WHERE status IN ('pending', 'streaming')
                    """,
                    (now, now),
                )
                conversation_ids = sorted({str(row["conversation_id"]) for row in rows})
                self.connection.executemany(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    [(now, conversation_id) for conversation_id in conversation_ids],
                )
        return ids
