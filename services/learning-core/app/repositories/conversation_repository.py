from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from . import JsonValue, dump_json, load_json, write_scope


class CitationInput(TypedDict):
    id: str
    document_id: str
    quote: str
    chunk_id: NotRequired[str | None]
    page_number: NotRequired[int | None]
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


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
        commit: bool = True,
    ) -> dict:
        if mode not in {"ask", "teach", "study", "review", "plan"}:
            raise ValueError("invalid conversation mode")
        now = _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO conversations
                    (id, course_id, title, mode, status, created_at, updated_at, archived_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?, NULL)
                """,
                (conversation_id, course_id, title, mode, now, now),
            )
        conversation = self.get_conversation(conversation_id)
        if conversation is None:  # pragma: no cover - protected by INSERT
            raise RuntimeError("conversation insert did not persist")
        return conversation

    def get_conversation(self, conversation_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, course_id, title, mode, status, created_at, updated_at, archived_at
            FROM conversations WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_conversations(self, *, status: str = "active") -> list[dict]:
        if status not in {"active", "archived"}:
            raise ValueError("invalid conversation status")
        rows = self.connection.execute(
            """
            SELECT c.id, c.course_id, c.title, c.mode, c.status, c.created_at, c.updated_at,
                   c.archived_at, COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.status = ?
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.id
            """,
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]

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
            if idempotency_key is not None:
                existing = self.connection.execute(
                    "SELECT id, role, status, content, model_provider, model_name, prompt_version FROM messages WHERE conversation_id = ? AND idempotency_key = ?",
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
                        {
                            "id": citation["id"],
                            "document_id": citation["document_id"],
                            "chunk_id": citation.get("chunk_id"),
                            "page_number": citation.get("page_number"),
                            "quote": citation["quote"],
                            "metadata": load_json(
                                dump_json(citation.get("metadata", {}))
                            ),
                        }
                        for citation in citations
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
                     error_detail, idempotency_key, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
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
                ),
            )
            for ordinal, citation in enumerate(citations):
                metadata = citation.get("metadata", {})
                if not isinstance(metadata, dict):
                    raise ValueError("citation metadata must be an object")
                self.connection.execute(
                    """
                    INSERT INTO message_citations
                        (id, message_id, ordinal, document_id, chunk_id,
                         page_number, quote, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
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
                   updated_at, completed_at
            FROM messages WHERE id = ?
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            return None
        message = dict(row)
        citation_rows = self.connection.execute(
            """
            SELECT id, document_id, chunk_id, page_number, quote, metadata_json
            FROM message_citations WHERE message_id = ? ORDER BY ordinal
            """,
            (message_id,),
        ).fetchall()
        message["citations"] = [
            {
                **{
                    key: citation[key]
                    for key in citation.keys()
                    if key != "metadata_json"
                },
                "metadata": load_json(citation["metadata_json"]),
            }
            for citation in citation_rows
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
        content: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        commit: bool = True,
    ) -> dict:
        current = self.get_message(message_id)
        if current is None:
            raise LookupError("message not found")
        if status not in _MESSAGE_TRANSITIONS[current["status"]]:
            raise ValueError(
                f"invalid message transition: {current['status']} -> {status}"
            )
        now = _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                UPDATE messages
                SET status = ?, content = COALESCE(?, content), error_code = ?,
                    error_detail = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    content,
                    error_code,
                    error_detail,
                    now,
                    now if status == "completed" else None,
                    message_id,
                ),
            )
        result = self.get_message(message_id)
        if result is None:  # pragma: no cover
            raise RuntimeError("message disappeared")
        return result

    def recover_interrupted_messages(self, *, commit: bool = True) -> list[str]:
        now = _now()
        with write_scope(self.connection, commit=commit):
            rows = self.connection.execute(
                "SELECT id FROM messages WHERE status IN ('pending', 'streaming') ORDER BY id"
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            if ids:
                self.connection.execute(
                    """
                    UPDATE messages SET status = 'interrupted', updated_at = ?,
                                        error_code = 'process_restarted',
                                        error_detail = 'Message generation was interrupted by restart'
                    WHERE status IN ('pending', 'streaming')
                    """,
                    (now,),
                )
        return ids
