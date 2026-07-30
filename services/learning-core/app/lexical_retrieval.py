from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal


QueryScript = Literal["latin", "cjk", "mixed"]


@dataclass(frozen=True, slots=True)
class _SearchChannel:
    table: Literal["document_chunks_fts", "document_chunks_cjk_fts"]
    expression: str


def normalize_query(query: str) -> str:
    """Return the single canonical query shared by every retrieval channel."""

    normalized = unicodedata.normalize("NFKC", query).strip()
    if not normalized:
        raise ValueError("query must not be empty")
    return normalized


def detect_query_script(query: str) -> QueryScript:
    """Classify normalized query text for deterministic lexical routing."""

    normalized = unicodedata.normalize("NFKC", query)
    has_cjk = any(_is_cjk(character) for character in normalized)
    has_latin = any(_is_latin_or_digit(character) for character in normalized)
    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "cjk"
    if has_latin:
        return "latin"
    raise ValueError("query must contain at least one letter or number")


def search_lexical(
    connection: sqlite3.Connection,
    query: str,
    *,
    course_id: str | None,
    limit: int,
    rrf_k: int = 60,
) -> list[dict]:
    """Search Latin/CJK FTS channels and fuse mixed results with RRF."""

    if limit < 1:
        raise ValueError("search result limit must be greater than zero")
    if rrf_k < 1:
        raise ValueError("RRF rank constant must be greater than zero")
    normalized = normalize_query(query)
    script = detect_query_script(normalized)
    channels = _search_channels(normalized, script)
    candidate_limit = min(100, max(20, limit * 4))
    fused: dict[str, dict] = {}
    for channel in channels:
        rows = _search_channel(
            connection,
            channel,
            course_id=course_id,
            candidate_limit=candidate_limit,
        )
        for rank, row in enumerate(rows, start=1):
            chunk_id = str(row["chunk_id"])
            existing = fused.get(chunk_id)
            reciprocal_rank = 1.0 / (rrf_k + rank)
            if existing is None:
                existing = {
                    "chunk_id": chunk_id,
                    "document_id": row["document_id"],
                    "document_name": row["document_name"],
                    "page_number": int(row["page_number"]),
                    "ordinal": int(row["ordinal"]),
                    "section_path": json.loads(row["section_path"]),
                    "text": row["text"],
                    "course_ids": json.loads(row["course_ids"]),
                    "score": 0.0,
                    "_best_channel_rank": rank,
                }
                fused[chunk_id] = existing
            existing["score"] += reciprocal_rank
            existing["_best_channel_rank"] = min(
                int(existing["_best_channel_rank"]), rank
            )

    ranked = sorted(
        fused.values(),
        key=lambda item: (
            -float(item["score"]),
            int(item["_best_channel_rank"]),
            str(item["document_id"]),
            str(item["chunk_id"]),
        ),
    )[:limit]
    for item in ranked:
        item["score"] = round(float(item["score"]), 8)
        del item["_best_channel_rank"]
    return ranked


def _search_channels(query: str, script: QueryScript) -> tuple[_SearchChannel, ...]:
    channels: list[_SearchChannel] = []
    if script in {"latin", "mixed"}:
        latin_expression = _latin_match_expression(query)
        if latin_expression:
            channels.append(_SearchChannel("document_chunks_fts", latin_expression))
    if script in {"cjk", "mixed"}:
        cjk_expression = _cjk_match_expression(query)
        if cjk_expression:
            channels.append(_SearchChannel("document_chunks_cjk_fts", cjk_expression))
    if not channels:
        raise ValueError(
            "CJK query must contain at least one searchable three-character span"
        )
    return tuple(channels)


def _search_channel(
    connection: sqlite3.Connection,
    channel: _SearchChannel,
    *,
    course_id: str | None,
    candidate_limit: int,
) -> list[sqlite3.Row]:
    course_clause = ""
    parameters: list[str | int] = [channel.expression]
    if course_id is not None:
        course_clause = """
            AND EXISTS (
                SELECT 1 FROM course_documents cd
                WHERE cd.document_id = d.id AND cd.course_id = ?
            )
        """
        parameters.append(course_id)
    parameters.append(candidate_limit)
    # FTS table identifiers are selected only from the closed _SearchChannel type;
    # all user-controlled values remain bound parameters.
    sql = f"""
        SELECT dc.id AS chunk_id, dc.document_id,
               d.name AS document_name, dc.page_number, dc.ordinal,
               dc.section_path, dc.content AS text,
               COALESCE((
                   SELECT json_group_array(course_id) FROM (
                       SELECT course_id FROM course_documents
                       WHERE document_id = dc.document_id ORDER BY course_id
                   )
               ), '[]') AS course_ids,
               bm25({channel.table}, 1.0, 0.35) AS lexical_rank
        FROM {channel.table}
        JOIN document_chunks dc ON dc.rowid = {channel.table}.rowid
        JOIN documents d ON d.id = dc.document_id
        WHERE {channel.table} MATCH ? AND d.status = 'indexed'
        {course_clause}
        ORDER BY lexical_rank, dc.document_id, dc.ordinal
        LIMIT ?
    """
    return list(connection.execute(sql, parameters).fetchall())


def _latin_match_expression(query: str) -> str:
    terms = _script_spans(query, script="latin")[:12]
    return " OR ".join(_quote_fts_term(term) for term in terms)


def _cjk_match_expression(query: str) -> str:
    shingles: list[str] = []
    for span in _script_spans(query, script="cjk"):
        shingles.extend(
            span[offset : offset + 3] for offset in range(max(0, len(span) - 2))
        )
    terms = _dedupe_preserving_order(shingles)[:32]
    return " OR ".join(_quote_fts_term(term) for term in terms)


def _script_spans(query: str, *, script: Literal["latin", "cjk"]) -> list[str]:
    matches = _is_latin_or_digit if script == "latin" else _is_cjk
    spans: list[str] = []
    current: list[str] = []
    for character in query:
        if matches(character):
            current.append(character)
        elif current:
            spans.append("".join(current))
            current = []
    if current:
        spans.append("".join(current))
    return _dedupe_preserving_order(spans)


def _quote_fts_term(term: str) -> str:
    return f'"{term.replace(chr(34), chr(34) * 2)}"'


def _dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _is_latin_or_digit(character: str) -> bool:
    if character.isdecimal():
        return True
    return "LATIN" in unicodedata.name(character, "")


def _is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return any(
        start <= codepoint <= end
        for start, end in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x20000, 0x2FA1F),
            (0x3040, 0x30FF),
            (0xAC00, 0xD7AF),
        )
    )
