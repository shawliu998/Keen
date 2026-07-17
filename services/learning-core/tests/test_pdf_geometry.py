from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from pypdf import PdfReader, PdfWriter

from app.chat_interfaces import ChatMessage, ChatModel
from app.database import Database
from app.main import create_app
from app.settings import LocalChatSettings, Settings
from conftest import TOKEN, _minimal_text_pdf

HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class _CitingProvider:
    def __init__(self, source_index: int = 1) -> None:
        self.source_index = source_index

    @property
    def model(self) -> ChatModel:
        return ChatModel(provider="ollama", model="fixture-chat", version="v1")

    async def stream(self, _messages: tuple[ChatMessage, ...]) -> AsyncIterator[str]:
        yield f"The source supports this answer [[source:{self.source_index}]]"

    async def aclose(self) -> None:
        return None


def _settings(root: Path, *, chat: bool = False) -> Settings:
    return Settings(
        session_token=TOKEN,
        database_path=root / "learning.sqlite3",
        document_data_path=root / "documents",
        seed_demo=True,
        local_chat=(
            LocalChatSettings(
                provider="ollama",
                base_url="http://127.0.0.1:11434",
                model="fixture-chat",
                version="v1",
            )
            if chat
            else None
        ),
    )


def _upload_and_wait(
    client: TestClient,
    *,
    filename: str,
    content: bytes,
    media_type: str,
    timeout: float = 15.0,
) -> str:
    response = client.post(
        "/v1/documents/import",
        headers=HEADERS,
        files={"file": (filename, content, media_type)},
        data={"course_id": "course-calculus"},
    )
    assert response.status_code == 202
    body = response.json()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/v1/index-jobs/{body['job']['id']}", headers=HEADERS).json()
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            assert job["status"] == "completed", job
            return str(body["document"]["id"])
        time.sleep(0.02)
    raise AssertionError("indexing did not complete")


def _sse_events(response) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event: str | None = None
    for line in response.iter_lines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            assert event is not None
            events.append((event, json.loads(line.removeprefix("data: "))))
            event = None
    return events


def test_pdf_geometry_persists_and_citation_maps_real_bbox(tmp_path) -> None:
    pdf = _minimal_text_pdf(
        ["Photosynthesis captures sunlight energy in chloroplasts."]
    )
    with TestClient(
        create_app(
            _settings(tmp_path, chat=True),
            chat_provider_factory=lambda _configuration: _CitingProvider(),
        )
    ) as client:
        document_id = _upload_and_wait(
            client,
            filename="biology.pdf",
            content=pdf,
            media_type="application/pdf",
        )
        with client.app.state.database.connection() as connection:
            geometry = connection.execute(
                """
                SELECT g.*, chunks.document_id
                FROM document_chunk_geometry g
                JOIN document_chunks chunks ON chunks.id = g.chunk_id
                WHERE chunks.document_id = ?
                ORDER BY g.id
                """,
                (document_id,),
            ).fetchall()
        response = client.post(
            "/v1/answer/stream",
            headers=HEADERS,
            json={
                "question": "How does photosynthesis capture sunlight?",
                "courseId": "course-calculus",
                "retrievalLimit": 8,
            },
        )
        events = _sse_events(response)

    assert geometry
    first = geometry[0]
    assert first["page_number"] == 1
    assert "Photosynthesis" in first["original_text"]
    assert "Photosynthesis" in first["normalized_text"]
    assert first["block_id"] == "p1-b0"
    assert first["span_id"].startswith("p1-b0-s")
    assert 0 <= first["bbox_x0"] < first["bbox_x1"] <= first["page_width"]
    assert 0 <= first["bbox_y0"] < first["bbox_y1"] <= first["page_height"]
    citation = next(data for name, data in events if name == "citation")
    assert citation["pageNumber"] == 1
    assert "Photosynthesis" in citation["excerpt"]
    assert citation["bbox"]["coordinateSystem"] == "pdf_bottom_left"
    assert citation["bbox"]["pageWidth"] == 612.0
    assert citation["bbox"]["pageHeight"] == 792.0


def test_pdf_citation_without_geometry_returns_explicit_null_fallback(tmp_path) -> None:
    with TestClient(
        create_app(
            _settings(tmp_path, chat=True),
            chat_provider_factory=lambda _configuration: _CitingProvider(),
        )
    ) as client:
        document_id = _upload_and_wait(
            client,
            filename="fallback.pdf",
            content=_minimal_text_pdf(["Matrices map vectors between spaces."]),
            media_type="application/pdf",
        )
        with client.app.state.database.connection() as connection:
            connection.execute(
                """
                DELETE FROM document_chunk_geometry
                WHERE chunk_id IN (
                    SELECT id FROM document_chunks WHERE document_id = ?
                )
                """,
                (document_id,),
            )
            connection.commit()
        response = client.post(
            "/v1/answer/stream",
            headers=HEADERS,
            json={"question": "What maps vectors?", "retrievalLimit": 8},
        )
        events = _sse_events(response)

    citation = next(data for name, data in events if name == "citation")
    assert citation["bbox"] is None
    assert citation["pageNumber"] == 1


def test_authenticated_pdf_content_supports_range_and_rejects_path_escape(
    tmp_path,
) -> None:
    pdf = _minimal_text_pdf(["Local PDF content endpoint."])
    with TestClient(create_app(_settings(tmp_path))) as client:
        document_id = _upload_and_wait(
            client,
            filename="viewer.pdf",
            content=pdf,
            media_type="application/pdf",
        )
        assert client.get(f"/v1/documents/{document_id}/content").status_code == 401
        full = client.get(f"/v1/documents/{document_id}/content", headers=HEADERS)
        partial = client.get(
            f"/v1/documents/{document_id}/content",
            headers={**HEADERS, "Range": "bytes=0-7"},
        )
        text_id = _upload_and_wait(
            client,
            filename="notes.txt",
            content=b"A local text note.",
            media_type="text/plain",
        )
        text_response = client.get(f"/v1/documents/{text_id}/content", headers=HEADERS)
        with client.app.state.database.connection() as connection:
            connection.execute(
                "UPDATE document_versions SET storage_path = '../outside.pdf' "
                "WHERE document_id = ?",
                (document_id,),
            )
            connection.commit()
        escaped = client.get(f"/v1/documents/{document_id}/content", headers=HEADERS)

    assert full.status_code == 200
    assert full.content == pdf
    assert full.headers["content-type"] == "application/pdf"
    assert full.headers["cache-control"] == "private, no-store"
    assert full.headers["x-content-type-options"] == "nosniff"
    assert partial.status_code == 206
    assert partial.content == pdf[:8]
    assert partial.headers["content-range"].startswith("bytes 0-7/")
    assert text_response.status_code == 415
    assert escaped.status_code == 409
    assert b"outside" not in escaped.content


def test_geometry_migration_is_forward_only_and_restart_idempotent(tmp_path) -> None:
    database = Database(tmp_path / "geometry-forward.sqlite3")
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 8):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
        connection.commit()

    assert database.migrate() == list(range(8, 21))
    assert Database(database.path).migrate() == []
    with database.connection() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(document_chunk_geometry)")
        }
        count = connection.execute(
            "SELECT COUNT(*) FROM document_chunk_geometry"
        ).fetchone()[0]
    assert {
        "chunk_id",
        "page_number",
        "original_text",
        "normalized_text",
        "block_id",
        "span_id",
        "bbox_x0",
        "bbox_y0",
        "bbox_x1",
        "bbox_y1",
        "page_width",
        "page_height",
    }.issubset(columns)
    assert count == 0


def test_one_hundred_page_pdf_indexes_with_page_geometry(tmp_path) -> None:
    pdf = _minimal_text_pdf(
        [f"Page {page} contains bounded geometry text." for page in range(1, 101)]
    )
    with TestClient(create_app(_settings(tmp_path))) as client:
        document_id = _upload_and_wait(
            client,
            filename="hundred-pages.pdf",
            content=pdf,
            media_type="application/pdf",
            timeout=30.0,
        )
        document = next(
            item
            for item in client.get("/v1/documents", headers=HEADERS).json()["documents"]
            if item["id"] == document_id
        )
        with client.app.state.database.connection() as connection:
            geometry_pages = connection.execute(
                """
                SELECT COUNT(DISTINCT g.page_number)
                FROM document_chunk_geometry g
                JOIN document_chunks chunks ON chunks.id = g.chunk_id
                WHERE chunks.document_id = ?
                """,
                (document_id,),
            ).fetchone()[0]

    assert document["status"] == "indexed"
    assert document["pageCount"] == 100
    assert geometry_pages == 100


def test_cross_page_merged_result_expands_to_exact_single_chunk_sources(
    tmp_path,
) -> None:
    provider = _CitingProvider(source_index=2)
    with TestClient(
        create_app(
            _settings(tmp_path, chat=True),
            chat_provider_factory=lambda _configuration: provider,
        )
    ) as client:
        document_id = _upload_and_wait(
            client,
            filename="two-pages.pdf",
            content=_minimal_text_pdf(
                [
                    "Mitochondria have a folded inner membrane.",
                    "Mitochondria produce cellular energy on this page.",
                ]
            ),
            media_type="application/pdf",
        )
        search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "mitochondria", "limit": 8},
        )
        answer = client.post(
            "/v1/answer/stream",
            headers=HEADERS,
            json={"question": "mitochondria", "retrievalLimit": 8},
        )
        events = _sse_events(answer)
        with client.app.state.database.connection() as connection:
            page_two_chunk = connection.execute(
                """
                SELECT id FROM document_chunks
                WHERE document_id = ? AND page_number = 2
                """,
                (document_id,),
            ).fetchone()["id"]

    assert search.status_code == 200
    assert len(search.json()["results"][0]["chunkIds"]) == 2
    retrieval = next(data for name, data in events if name == "retrieval")
    assert len(retrieval["chunks"]) >= 2
    assert all(len(source["chunkIds"]) == 1 for source in retrieval["chunks"])
    assert retrieval["chunks"][1]["chunkId"] == page_two_chunk
    assert retrieval["chunks"][1]["pageNumber"] == 2
    citation = next(data for name, data in events if name == "citation")
    assert citation["sourceIndex"] == 2
    assert citation["chunkId"] == page_two_chunk
    assert citation["pageNumber"] == 2


def _pdf_with_page_transform(kind: str, text: str) -> bytes:
    reader = PdfReader(BytesIO(_minimal_text_pdf([text])))
    page = reader.pages[0]
    if kind == "rotation":
        page.rotate(90)
    elif kind == "cropbox":
        page.cropbox.lower_left = (36, 36)
        page.cropbox.upper_right = (576, 756)
    else:  # pragma: no cover - fixture construction is controlled by parametrization
        raise AssertionError("unknown PDF transform")
    writer = PdfWriter()
    writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize("kind", ["rotation", "cropbox"])
def test_transformed_pdf_keeps_page_citation_but_never_fabricates_bbox(
    tmp_path, kind: str
) -> None:
    text = f"Conservative {kind} page geometry fallback."
    pdf = _pdf_with_page_transform(kind, text)
    page = PdfReader(BytesIO(pdf)).pages[0]
    if kind == "rotation":
        assert page.rotation == 90
    else:
        assert tuple(page.cropbox) != tuple(page.mediabox)

    with TestClient(
        create_app(
            _settings(tmp_path, chat=True),
            chat_provider_factory=lambda _configuration: _CitingProvider(),
        )
    ) as client:
        document_id = _upload_and_wait(
            client,
            filename=f"{kind}.pdf",
            content=pdf,
            media_type="application/pdf",
        )
        with client.app.state.database.connection() as connection:
            geometry_count = connection.execute(
                """
                SELECT COUNT(*) FROM document_chunk_geometry geometry
                JOIN document_chunks chunks ON chunks.id = geometry.chunk_id
                WHERE chunks.document_id = ?
                """,
                (document_id,),
            ).fetchone()[0]
        content = client.get(f"/v1/documents/{document_id}/content", headers=HEADERS)
        answer = client.post(
            "/v1/answer/stream",
            headers=HEADERS,
            json={"question": f"conservative {kind}", "retrievalLimit": 8},
        )
        events = _sse_events(answer)

    assert geometry_count == 0
    assert content.status_code == 200
    assert content.content == pdf
    citation = next(data for name, data in events if name == "citation")
    assert citation["pageNumber"] == 1
    assert citation["bbox"] is None
