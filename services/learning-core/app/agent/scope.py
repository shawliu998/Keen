from __future__ import annotations

import sqlite3


def resolve_course_scope(
    connection: sqlite3.Connection,
    *,
    conversation_id: str | None,
    study_session_id: str | None,
) -> str | None:
    """Resolve a run's immutable course scope from persisted learning context."""

    session = None
    if study_session_id is not None:
        session = connection.execute(
            "SELECT course_id, conversation_id FROM study_sessions WHERE id = ?",
            (study_session_id,),
        ).fetchone()
        if session is None:
            raise ValueError("agent run study session context does not exist")

    conversation = None
    if conversation_id is not None:
        conversation = connection.execute(
            "SELECT course_id FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if conversation is None:
            raise ValueError("agent run conversation context does not exist")

    if session is not None and conversation is not None:
        if session["conversation_id"] != conversation_id:
            raise ValueError("agent run conversation and study session do not match")
        if conversation["course_id"] not in {None, session["course_id"]}:
            raise ValueError("agent run conversation and study session do not match")

    if session is not None:
        return str(session["course_id"])
    if conversation is not None and conversation["course_id"] is not None:
        return str(conversation["course_id"])
    return None


__all__ = ["resolve_course_scope"]
