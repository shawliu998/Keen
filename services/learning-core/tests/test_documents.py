from __future__ import annotations

import io
import json
import multiprocessing
import os
import resource
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import app.documents as documents_module
from app.database import Database
from app.document_repository import DocumentRepository
from app.documents import incoming_destination
from app.index_jobs import IndexJobRepository
from app.main import create_app
from app.settings import Settings
from conftest import TOKEN


def _guarded_worker_probe(connection):
    identity = documents_module._isolate_pdf_worker_process_group()
    documents_module._start_pdf_worker_parent_watch()
    connection.send(identity)
    connection.close()
    time.sleep(30)


def _guarded_worker_owner(connection):
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    worker = context.Process(target=_guarded_worker_probe, args=(child_connection,))
    worker.start()
    child_connection.close()
    identity = parent_connection.recv()
    parent_connection.close()
    connection.send(identity)
    connection.close()
    os._exit(0)


def _upload(
    client,
    headers,
    name: str,
    content: bytes,
    media_type: str,
    *,
    course_id: str | None = None,
):
    arguments = {
        "headers": headers,
        "files": {"file": (name, content, media_type)},
    }
    if course_id is not None:
        arguments["data"] = {"course_id": course_id}
    return client.post("/v1/documents/import", **arguments)


def _wait_for_job(client, headers, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/index-jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"cancelled", "completed", "failed", "interrupted"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"index job {job_id} did not finish")


def _wait_for_import(
    client, headers, response, timeout: float = 10.0
) -> tuple[dict, dict]:
    assert response.status_code in {200, 202}
    body = response.json()
    job = _wait_for_job(client, headers, body["job"]["id"], timeout)
    listing = client.get("/v1/documents", headers=headers)
    assert listing.status_code == 200
    document = next(
        document
        for document in listing.json()["documents"]
        if document["id"] == body["document"]["id"]
    )
    return document, job


def test_database_and_document_root_permissions_are_private(client):
    settings = client.app.state.settings

    assert stat.S_IMODE(settings.database_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings.document_data_path.stat().st_mode) == 0o700


def test_macos_pdf_worker_uses_parent_rss_monitor_not_sparse_address_limits(
    monkeypatch,
):
    applied: list[int] = []
    monkeypatch.setattr(documents_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        documents_module.resource,
        "setrlimit",
        lambda limit, _value: applied.append(limit),
    )

    documents_module._apply_pdf_worker_limits()

    assert resource.RLIMIT_CPU not in applied
    assert resource.RLIMIT_DATA not in applied
    assert resource.RLIMIT_AS not in applied


def test_macos_pdf_worker_rss_snapshot_includes_only_the_isolated_group(monkeypatch):
    output = """100 100 10 S
101 100 20 S
102 100 30 Z
200 200 999 R
"""
    monkeypatch.setattr(documents_module.os, "getpgrp", lambda: 999)
    monkeypatch.setattr(
        documents_module.subprocess,
        "run",
        lambda *_args, **_kwargs: documents_module.subprocess.CompletedProcess(
            args=[], returncode=0, stdout=output
        ),
    )

    assert documents_module._darwin_process_group_snapshot(100) == (
        (100, 101, 102),
        60 * 1024,
    )


def test_pdf_worker_process_group_identity_is_strictly_validated(monkeypatch):
    monkeypatch.setattr(documents_module.os, "getpgrp", lambda: 5000)
    monkeypatch.setattr(documents_module.os, "getpgid", lambda pid: pid)

    assert documents_module._validate_pdf_worker_process_group((4000, 4000))
    assert not documents_module._validate_pdf_worker_process_group((1, 1))
    assert not documents_module._validate_pdf_worker_process_group((4000, 4001))
    assert not documents_module._validate_pdf_worker_process_group((5000, 5000))
    assert not documents_module._validate_pdf_worker_process_group((True, True))


def test_pdf_worker_announces_isolated_group_before_parsing(monkeypatch):
    messages: list[object] = []

    class Connection:
        def send(self, message):
            messages.append(message)

        def poll(self, _timeout):
            return True

        def recv(self):
            return "start"

        def close(self):
            return None

    monkeypatch.setattr(documents_module.os, "setpgid", lambda pid, pgid: None)
    monkeypatch.setattr(documents_module.os, "getpid", lambda: 4321)
    monkeypatch.setattr(documents_module.os, "getpgrp", lambda: 4321)
    monkeypatch.setattr(
        documents_module, "_start_pdf_worker_parent_watch", lambda: None
    )
    monkeypatch.setattr(
        documents_module, "_arm_pdf_worker_wall_timer", lambda *_args: None
    )
    monkeypatch.setattr(documents_module.signal, "setitimer", lambda *_args: None)
    monkeypatch.setattr(
        documents_module,
        "_apply_pdf_worker_limits",
        lambda *_args: (_ for _ in ()).throw(
            documents_module.DocumentParseError("stop")
        ),
    )

    documents_module._pdf_parse_worker("unused.pdf", Connection())

    assert messages == [("ready", (4321, 4321)), ("error", "stop")]


def test_pdf_worker_parent_watch_kills_its_isolated_group(monkeypatch):
    events: list[str] = []

    class Parent:
        @staticmethod
        def join():
            events.append("parent-exited")

    monkeypatch.setattr(
        documents_module,
        "_kill_current_pdf_worker_group",
        lambda: events.append("group-killed"),
    )

    documents_module._watch_pdf_worker_parent(Parent())

    assert events == ["parent-exited", "group-killed"]


def test_pdf_worker_group_exits_when_its_owner_is_killed():
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    owner = context.Process(target=_guarded_worker_owner, args=(child_connection,))
    owner.start()
    child_connection.close()
    assert parent_connection.poll(5)
    worker_pid, worker_process_group = parent_connection.recv()
    parent_connection.close()
    assert worker_pid == worker_process_group

    owner.join(timeout=3)
    assert not owner.is_alive()
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            live_members = documents_module._darwin_process_group_has_live_members(
                worker_process_group
            )
            if live_members is False:
                break
            time.sleep(0.05)
        assert (
            documents_module._darwin_process_group_has_live_members(
                worker_process_group
            )
            is False
        )
    finally:
        try:
            os.killpg(worker_process_group, documents_module.signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def test_pdf_worker_wall_timer_kills_the_group(monkeypatch):
    installed: list[object] = []
    timers: list[tuple[object, float]] = []
    killed: list[bool] = []
    monkeypatch.setattr(
        documents_module.signal,
        "signal",
        lambda signal_number, handler: installed.extend((signal_number, handler)),
    )
    monkeypatch.setattr(
        documents_module.signal,
        "setitimer",
        lambda timer, timeout: timers.append((timer, timeout)),
    )
    monkeypatch.setattr(
        documents_module,
        "_kill_current_pdf_worker_group",
        lambda: killed.append(True),
    )

    documents_module._arm_pdf_worker_wall_timer()
    handler = installed[1]
    handler(documents_module.signal.SIGALRM, None)

    assert installed[0] == documents_module.signal.SIGALRM
    assert timers == [
        (
            documents_module.signal.ITIMER_REAL,
            documents_module.PDF_PARSE_WALL_TIMEOUT_SECONDS,
        )
    ]
    assert killed == [True]


def test_pdf_worker_group_cleanup_kills_descendant_after_leader_exits():
    leader = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os, subprocess; os.setpgid(0, 0); "
                "child=subprocess.Popen(['/bin/sleep','30'], "
                "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                "print(child.pid, flush=True)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert leader.stdout is not None
    descendant_pid = int(leader.stdout.readline().strip())
    leader.wait(timeout=2)

    class ExitedProcess:
        pid = leader.pid

        @staticmethod
        def is_alive():
            return False

        @staticmethod
        def kill():
            raise AssertionError(
                "an exited leader must not be killed as a live process"
            )

        @staticmethod
        def join(timeout):
            assert timeout == 1

    try:
        documents_module._terminate_pdf_worker_tree(
            ExitedProcess(),
            (leader.pid, descendant_pid),
            leader.pid,
        )
        assert (
            documents_module._darwin_process_group_has_live_members(leader.pid) is False
        )
    finally:
        try:
            os.killpg(leader.pid, documents_module.signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _highly_compressed_operator_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT\n/F1 12 Tf\n(A) Tj\nET\n" * 700_000)
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_import_persists_pages_chunks_locations_and_status_history(
    client, auth_headers, pdf_bytes
):
    response = _upload(
        client, auth_headers, "biology.pdf", pdf_bytes, "application/pdf"
    )

    assert response.status_code == 202
    assert response.json()["duplicate"] is False
    document, job = _wait_for_import(client, auth_headers, response)
    assert job["status"] == "completed"
    assert set(document) == {
        "id",
        "name",
        "mimeType",
        "sizeBytes",
        "contentHash",
        "status",
        "pageCount",
        "chunkCount",
        "parser",
        "createdAt",
        "error",
        "courseIds",
        "indexState",
        "embeddingStatus",
        "embeddingModel",
        "embeddingError",
        "retrievalWarning",
        "providerConfigured",
    }
    assert document["name"] == "biology.pdf"
    assert document["mimeType"] == "application/pdf"
    assert document["sizeBytes"] == len(pdf_bytes)
    assert len(document["contentHash"]) == 64
    assert document["status"] == "indexed"
    assert document["pageCount"] == 2
    assert document["chunkCount"] == 2
    assert document["parser"] == (
        f"{documents_module.PDF_PARSER_PREFIX};{documents_module.CHUNKER_VERSION}"
    )
    assert document["error"] is None
    assert document["courseIds"] == []

    database = client.app.state.database
    with database.connection() as connection:
        events = connection.execute(
            """
            SELECT from_status, to_status FROM document_status_events
            WHERE document_id = ? ORDER BY id
            """,
            (document["id"],),
        ).fetchall()
        version = connection.execute(
            """
            SELECT storage_path FROM document_versions WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()
        chunks = connection.execute(
            """
            SELECT text_location, embedding_version FROM document_chunks
            WHERE document_id = ? ORDER BY ordinal
            """,
            (document["id"],),
        ).fetchall()

    assert [(row["from_status"], row["to_status"]) for row in events] == [
        (None, "queued"),
        ("queued", "parsing"),
        ("parsing", "chunking"),
        ("chunking", "indexed"),
    ]
    assert not version["storage_path"].startswith("/")
    stored = client.app.state.settings.document_data_path / version["storage_path"]
    assert stored.is_file()
    assert stored.read_bytes() == pdf_bytes
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert all(row["embedding_version"] is None for row in chunks)
    for row in chunks:
        location = json.loads(row["text_location"])
        assert set(location) == {"unit", "start", "end"}
        assert 0 <= location["start"] < location["end"]

    listing = client.get("/v1/documents", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json() == {"documents": [document]}


def test_duplicate_content_hash_reuses_the_indexed_document(
    client, auth_headers, pdf_bytes
):
    first = _upload(client, auth_headers, "first.pdf", pdf_bytes, "application/pdf")
    _wait_for_import(client, auth_headers, first)
    second = _upload(client, auth_headers, "renamed.pdf", pdf_bytes, "application/pdf")

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["document"]["id"] == first.json()["document"]["id"]
    assert second.json()["document"]["name"] == "first.pdf"

    with client.app.state.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0]
            == 1
        )


def test_same_hash_links_two_courses_without_reindex_and_last_unlink_keeps_document(
    client, auth_headers
):
    content = b"Course links share one durable source and searchable lexical index."
    first = _upload(
        client,
        auth_headers,
        "shared.txt",
        content,
        "text/plain",
        course_id="course-calculus",
    )
    assert first.status_code == 202
    assert first.json()["duplicate"] is False
    assert first.json()["linked"] is True
    first_document, first_job = _wait_for_import(client, auth_headers, first)
    assert first_job["status"] == "completed"
    assert first_document["courseIds"] == ["course-calculus"]

    second = _upload(
        client,
        auth_headers,
        "renamed.txt",
        content,
        "text/plain",
        course_id="course-physics",
    )
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["linked"] is True
    assert second.json()["document"]["id"] == first_document["id"]
    assert second.json()["document"]["courseIds"] == [
        "course-calculus",
        "course-physics",
    ]
    assert second.json()["job"]["id"] == first_job["id"]

    repeated = _upload(
        client,
        auth_headers,
        "again.txt",
        content,
        "text/plain",
        course_id="course-physics",
    )
    assert repeated.status_code == 200
    assert repeated.json()["duplicate"] is True
    assert repeated.json()["linked"] is False

    with client.app.state.database.connection() as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "documents",
                "document_versions",
                "document_index_jobs",
                "course_documents",
            )
        }
    assert counts == {
        "documents": 1,
        "document_versions": 1,
        "document_index_jobs": 1,
        "course_documents": 2,
    }

    for course_id in ("course-calculus", "course-physics"):
        listing = client.get(
            "/v1/documents", headers=auth_headers, params={"courseId": course_id}
        )
        assert [item["id"] for item in listing.json()["documents"]] == [
            first_document["id"]
        ]
        search = client.post(
            "/v1/search",
            headers=auth_headers,
            json={"query": "lexical", "courseId": course_id},
        )
        assert [item["documentId"] for item in search.json()["results"]] == [
            first_document["id"]
        ]

    unlinked = client.delete(
        f"/v1/documents/{first_document['id']}/courses/course-calculus",
        headers=auth_headers,
    )
    assert unlinked.status_code == 204
    remaining = client.get("/v1/documents", headers=auth_headers).json()["documents"]
    assert remaining[0]["courseIds"] == ["course-physics"]
    calculus_search = client.post(
        "/v1/search",
        headers=auth_headers,
        json={"query": "lexical", "courseId": "course-calculus"},
    )
    assert calculus_search.json()["results"] == []

    last_unlink = client.delete(
        f"/v1/documents/{first_document['id']}/courses/course-physics",
        headers=auth_headers,
    )
    assert last_unlink.status_code == 204
    unscoped = client.get("/v1/documents", headers=auth_headers).json()["documents"]
    assert len(unscoped) == 1
    assert unscoped[0]["courseIds"] == []
    global_search = client.post(
        "/v1/search", headers=auth_headers, json={"query": "lexical"}
    )
    assert len(global_search.json()["results"]) == 1
    assert (
        client.delete(
            f"/v1/documents/{first_document['id']}/courses/course-physics",
            headers=auth_headers,
        ).status_code
        == 204
    )

    relinked = client.post(
        f"/v1/documents/{first_document['id']}/courses/course-calculus",
        headers=auth_headers,
    )
    assert relinked.status_code == 200
    assert relinked.json()["linked"] is True
    assert relinked.json()["document"]["courseIds"] == ["course-calculus"]
    assert (
        client.post(
            f"/v1/documents/{first_document['id']}/courses/course-calculus",
            headers=auth_headers,
        ).json()["linked"]
        is False
    )


def test_missing_source_duplicate_202_reports_new_course_link(client, auth_headers):
    content = b"Repair and course linking share the same duplicate import transaction."
    first = _upload(
        client,
        auth_headers,
        "repair-link.txt",
        content,
        "text/plain",
        course_id="course-calculus",
    )
    document, job = _wait_for_import(client, auth_headers, first)
    assert job["status"] == "completed"
    with client.app.state.database.connection() as connection:
        relative = connection.execute(
            "SELECT storage_path FROM document_versions WHERE document_id = ?",
            (document["id"],),
        ).fetchone()["storage_path"]
    stored = client.app.state.settings.document_data_path / relative
    stored.unlink()
    with client.app.state.database.connection() as connection:
        IndexJobRepository(connection).mark_missing_storage(document["id"], relative)

    repaired = _upload(
        client,
        auth_headers,
        "repair-link.txt",
        content,
        "text/plain",
        course_id="course-physics",
    )
    assert repaired.status_code == 202
    assert repaired.json()["duplicate"] is True
    assert repaired.json()["linked"] is True
    assert repaired.json()["document"]["courseIds"] == [
        "course-calculus",
        "course-physics",
    ]
    assert (
        _wait_for_job(client, auth_headers, repaired.json()["job"]["id"])["status"]
        == "completed"
    )


def test_concurrent_duplicate_imports_create_one_document(
    client, auth_headers, pdf_bytes
):
    def upload(index: int):
        return _upload(
            client,
            auth_headers,
            f"concurrent-{index}.pdf",
            pdf_bytes,
            "application/pdf",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(upload, range(8)))

    assert sorted(response.status_code for response in responses) == [200] * 7 + [202]
    document_ids = {response.json()["document"]["id"] for response in responses}
    assert len(document_ids) == 1
    with client.app.state.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        storage_path = connection.execute(
            "SELECT storage_path FROM document_versions"
        ).fetchone()["storage_path"]
    assert (client.app.state.settings.document_data_path / storage_path).is_file()


def test_upload_rejects_extension_mime_and_content_mismatches(
    client, auth_headers, pdf_bytes
):
    wrong_mime = _upload(client, auth_headers, "notes.pdf", pdf_bytes, "text/plain")
    unsupported = _upload(
        client, auth_headers, "notes.exe", b"plain text", "text/plain"
    )
    disguised_pdf = _upload(
        client,
        auth_headers,
        "notes.txt",
        pdf_bytes,
        "text/plain",
    )

    assert wrong_mime.status_code == 422
    assert "does not match .pdf" in wrong_mime.json()["detail"]
    assert unsupported.status_code == 422
    assert "only .pdf, .md, and .txt" in unsupported.json()["detail"]
    assert disguised_pdf.status_code == 422
    assert "PDF content must use" in disguised_pdf.json()["detail"]
    with client.app.state.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    incoming = client.app.state.settings.document_data_path / ".incoming"
    assert not incoming.exists() or list(incoming.iterdir()) == []


def test_upload_enforces_streaming_size_limit_and_cleans_temporary_file(
    tmp_path, auth_headers
):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "small.sqlite3",
        document_data_path=tmp_path / "controlled-documents",
        max_document_bytes=8,
    )
    with TestClient(create_app(settings)) as limited_client:
        response = _upload(
            limited_client,
            auth_headers,
            "oversize.txt",
            b"nine-byte",
            "text/plain",
        )
        assert response.status_code == 413
        assert response.json()["detail"]["retryable"] is True
        with limited_client.app.state.database.connection() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
            )
    incoming = settings.document_data_path / ".incoming"
    assert not incoming.exists() or list(incoming.iterdir()) == []


def test_fts_search_and_grounded_query_return_verifiable_page_citations(
    client, auth_headers, pdf_bytes
):
    imported = _upload(
        client, auth_headers, "biology.pdf", pdf_bytes, "application/pdf"
    )
    document, job = _wait_for_import(client, auth_headers, imported)
    assert job["status"] == "completed"
    document_id = document["id"]

    search = client.post(
        "/v1/search",
        headers=auth_headers,
        json={"query": "mitochondria", "limit": 5},
    )
    assert search.status_code == 200
    assert search.json()["query"] == "mitochondria"
    assert len(search.json()["results"]) == 1
    result = search.json()["results"][0]
    assert result["documentId"] == document_id
    assert result["documentName"] == "biology.pdf"
    assert result["pageNumber"] == 2
    assert "Mitochondria" in result["text"]
    assert result["score"] >= 0

    syntax_input = client.post(
        "/v1/search",
        headers=auth_headers,
        json={"query": 'mitochondria" OR *'},
    )
    assert syntax_input.status_code == 200
    assert syntax_input.json()["results"][0]["pageNumber"] == 2

    query = client.post(
        "/v1/query",
        headers=auth_headers,
        json={"query": "mitochondria", "limit": 5},
    )
    assert query.status_code == 200
    body = query.json()
    assert body["grounded"] is True
    assert body["citations"][0]["documentId"] == document_id
    assert body["citations"][0]["pageNumber"] == 2
    assert body["citations"][0]["excerpt"] in result["text"]
    assert "no vector search or model" in body["note"]

    missing = client.post(
        "/v1/query",
        headers=auth_headers,
        json={"query": "term-that-does-not-exist"},
    )
    assert missing.status_code == 200
    assert missing.json() == {
        "answer": "No indexed local source matched this query.",
        "grounded": False,
        "citations": [],
        "note": "No matching FTS5 chunks were found; no answer was inferred.",
    }


def test_markdown_sections_and_client_filename_never_control_storage_path(
    client, auth_headers
):
    markdown = b"# Cell Biology\n\n## Mitochondria\n\nCristae contain the electron transport chain."
    response = _upload(
        client, auth_headers, "../../notes.md", markdown, "text/markdown"
    )

    assert response.status_code == 202
    document, job = _wait_for_import(client, auth_headers, response)
    assert job["status"] == "completed"
    assert document["name"] == "notes.md"
    search = client.post(
        "/v1/search",
        headers=auth_headers,
        json={"query": "Cristae"},
    )
    assert search.status_code == 200
    assert search.json()["results"][0]["sectionPath"] == [
        "Cell Biology",
        "Mitochondria",
    ]
    with client.app.state.database.connection() as connection:
        storage_path = connection.execute(
            "SELECT storage_path FROM document_versions"
        ).fetchone()["storage_path"]
    assert ".." not in storage_path
    assert (client.app.state.settings.document_data_path / storage_path).is_file()


def test_textless_pdf_persists_failed_state_and_retains_source_for_retry(
    client, auth_headers, blank_pdf_bytes
):
    response = _upload(
        client,
        auth_headers,
        "scan.pdf",
        blank_pdf_bytes,
        "application/pdf",
    )

    assert response.status_code == 202
    document, job = _wait_for_import(client, auth_headers, response)
    assert job["status"] == "failed"
    assert "no extractable text" in job["error"]
    listing = client.get("/v1/documents", headers=auth_headers).json()["documents"]
    assert len(listing) == 1
    assert listing[0]["status"] == "failed"
    assert listing[0]["error"] == "document contains no extractable text"
    with client.app.state.database.connection() as connection:
        version = connection.execute(
            "SELECT storage_path FROM document_versions WHERE document_id = ?",
            (document["id"],),
        ).fetchone()
        events = connection.execute(
            """
            SELECT to_status FROM document_status_events
            WHERE document_id = ? ORDER BY id
            """,
            (document["id"],),
        ).fetchall()
    assert [row["to_status"] for row in events] == ["queued", "parsing", "failed"]
    assert (
        client.app.state.settings.document_data_path / version["storage_path"]
    ).is_file()


def test_pdf_parser_isolated_worker_bounds_compressed_operator_expansion(
    client, auth_headers
):
    payload = _highly_compressed_operator_pdf()
    assert len(payload) < 50_000

    started = time.monotonic()
    response = _upload(
        client,
        auth_headers,
        "compressed-operators.pdf",
        payload,
        "application/pdf",
    )
    enqueue_elapsed = time.monotonic() - started

    assert response.status_code == 202
    assert enqueue_elapsed < 2
    _document, job = _wait_for_import(client, auth_headers, response, timeout=15)
    assert job["status"] == "failed"
    detail_message = job["error"]
    assert any(
        message in detail_message
        for message in ("bounded resource budget", "character extraction limit")
    ), detail_message
    assert client.get("/health", headers=auth_headers).status_code == 200


def test_document_routes_require_auth_and_cors_is_narrow(client, auth_headers):
    assert client.get("/v1/documents").status_code == 401
    assert client.post("/v1/search", json={"query": "biology"}).status_code == 401
    assert (
        client.post("/v1/documents/missing/courses/course-calculus").status_code == 401
    )
    assert (
        client.delete("/v1/documents/missing/courses/course-calculus").status_code
        == 401
    )

    allowed = client.options(
        "/v1/search",
        headers={
            "Origin": "tauri://localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "tauri://localhost"
    assert "POST" in allowed.headers["access-control-allow-methods"]

    actual = client.get(
        "/v1/documents",
        headers={**auth_headers, "Origin": "tauri://localhost"},
    )
    assert actual.status_code == 200
    assert actual.headers["access-control-allow-origin"] == "tauri://localhost"
    assert {
        value.strip()
        for value in actual.headers["access-control-expose-headers"].split(",")
    } == {"Accept-Ranges", "Content-Range", "X-Request-ID"}
    assert actual.headers["X-Request-ID"]

    disallowed = client.options(
        "/v1/search",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert disallowed.status_code == 400
    assert "access-control-allow-origin" not in disallowed.headers


def test_fts_query_with_only_operators_is_a_clear_validation_error(
    client, auth_headers
):
    response = client.post(
        "/v1/search",
        headers=auth_headers,
        json={"query": '"***"'},
    )

    assert response.status_code == 422
    assert "at least one letter or number" in response.json()["detail"]


def test_temporary_upload_path_rejects_a_symlink_outside_document_storage(tmp_path):
    document_root = tmp_path / "documents"
    outside = tmp_path / "outside"
    document_root.mkdir()
    outside.mkdir()
    os.symlink(outside, document_root / ".incoming")

    try:
        incoming_destination(document_root, "a" * 32)
    except RuntimeError as error:
        assert "escaped" in str(error)
    else:  # pragma: no cover - the security assertion above must fail closed
        raise AssertionError("an out-of-bound temporary upload path was accepted")


def test_request_scoped_sqlite_connections_are_safe_under_concurrency(
    client, auth_headers
):
    def list_documents(_: int) -> int:
        return client.get("/v1/documents", headers=auth_headers).status_code

    with ThreadPoolExecutor(max_workers=16) as executor:
        statuses = list(executor.map(list_documents, range(96)))

    assert statuses == [200] * 96


def test_startup_marks_interrupted_import_failed_and_allows_retry(
    tmp_path, auth_headers
):
    content = b"Interrupted import content remains safe to retry."
    content_hash = sha256(content).hexdigest()
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "recovery.sqlite3",
        document_data_path=tmp_path / "documents",
    )
    database = Database(settings.database_path)
    database.migrate()
    with database.connection() as connection:
        repository = DocumentRepository(connection)
        repository.create_document(
            document_id="doc-interrupted",
            version_id="version-interrupted",
            course_id=None,
            name="interrupted.txt",
            mime_type="text/plain",
            extension=".txt",
            content_hash=content_hash,
            storage_path=f"{content_hash[:2]}/{content_hash}.txt",
            size_bytes=len(content),
            parser_version="keen-text/1;plain;keen-chunker/1",
        )
        repository.transition_status("doc-interrupted", "parsing")
    stored = settings.document_data_path / content_hash[:2] / f"{content_hash}.txt"
    stored.parent.mkdir(parents=True, mode=0o700)
    stored.write_bytes(content)
    incoming = incoming_destination(settings.document_data_path, "b" * 32)
    incoming.write_bytes(b"partial")

    with TestClient(create_app(settings)) as recovered_client:
        listing = recovered_client.get("/v1/documents", headers=auth_headers)
        assert listing.status_code == 200
        interrupted = listing.json()["documents"][0]
        assert interrupted["status"] == "failed"
        assert "interrupted" in interrupted["error"]
        assert not incoming.exists()

        retried = recovered_client.post(
            "/v1/documents/doc-interrupted/retry", headers=auth_headers
        )
        assert retried.status_code == 202
        retried_document, retry_job = _wait_for_import(
            recovered_client, auth_headers, retried
        )
        assert retry_job["status"] == "completed"
        assert retried_document["status"] == "indexed"
