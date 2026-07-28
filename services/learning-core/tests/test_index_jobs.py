from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

import app.index_worker as index_worker_module
import app.main as main_module
import app.storage_reconciliation as storage_module
from app.database import Database
from app.document_repository import DocumentRepository
from app.documents import DocumentProcessingCancelled, storage_destination
from app.index_jobs import IndexJobRepository
from app.main import create_app
from app.settings import Settings
from app.storage_reconciliation import StoredFileDeleteError, quarantine_for_delete
from conftest import TOKEN


TERMINAL_JOB_STATUSES = {"cancelled", "completed", "failed", "interrupted"}


def _upload(client, headers, name: str, content: bytes, media_type: str):
    return client.post(
        "/v1/documents/import",
        headers=headers,
        files={"file": (name, content, media_type)},
    )


def _wait_for_job(client, headers, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/index-jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        job = response.json()
        if job["status"] in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.02)
    raise AssertionError(f"index job {job_id} did not finish")


def test_import_returns_202_and_persists_a_pollable_job(client, auth_headers):
    response = _upload(
        client,
        auth_headers,
        "notes.txt",
        b"A persistent worker indexes this local text.",
        "text/plain",
    )

    assert response.status_code == 202
    body = response.json()
    assert body["duplicate"] is False
    assert body["document"]["status"] == "queued"
    assert set(body["job"]) == {
        "id",
        "documentId",
        "status",
        "stage",
        "progress",
        "cancelRequested",
        "error",
        "createdAt",
        "updatedAt",
        "startedAt",
        "finishedAt",
        "operation",
    }
    assert body["job"]["documentId"] == body["document"]["id"]
    assert body["job"]["status"] == "queued"
    assert body["job"]["stage"] == "stored"
    assert body["job"]["progress"] == 10

    completed = _wait_for_job(client, auth_headers, body["job"]["id"])
    assert completed["status"] == "completed"
    assert completed["stage"] == "finalizing"
    assert completed["progress"] == 100
    assert completed["startedAt"] is not None
    assert completed["finishedAt"] is not None


def test_job_list_filter_and_generic_mime_fallback(client, auth_headers):
    imported = _upload(
        client,
        auth_headers,
        "fallback.md",
        b"# Safe fallback\n\nThe extension and UTF-8 content are validated.",
        "application/octet-stream",
    )
    assert imported.status_code == 202
    document_id = imported.json()["document"]["id"]
    job_id = imported.json()["job"]["id"]

    listing = client.get(
        "/v1/index-jobs", headers=auth_headers, params={"documentId": document_id}
    )
    assert listing.status_code == 200
    assert [job["id"] for job in listing.json()["jobs"]] == [job_id]
    assert imported.json()["document"]["mimeType"] == "text/markdown"


def test_cancel_queued_job_is_immediate_and_retry_reuses_document(
    client, auth_headers, monkeypatch
):
    worker = client.app.state.document_index_worker
    worker.pause_for_test()
    try:
        imported = _upload(
            client,
            auth_headers,
            "cancel.txt",
            b"This queued job will be cancelled before parsing.",
            "text/plain",
        )
        assert imported.status_code == 202
        document_id = imported.json()["document"]["id"]
        job_id = imported.json()["job"]["id"]

        cancelled = client.post(f"/v1/index-jobs/{job_id}/cancel", headers=auth_headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancelRequested"] is True

        retried = client.post(
            f"/v1/documents/{document_id}/retry", headers=auth_headers
        )
        assert retried.status_code == 202
        assert retried.json()["document"]["id"] == document_id
        assert retried.json()["job"]["id"] != job_id
    finally:
        worker.resume_for_test()

    assert (
        _wait_for_job(client, auth_headers, retried.json()["job"]["id"])["status"]
        == "completed"
    )


def test_delete_cancels_processing_and_removes_database_and_storage(
    client, auth_headers
):
    worker = client.app.state.document_index_worker
    worker.pause_for_test()
    try:
        imported = _upload(
            client,
            auth_headers,
            "delete.txt",
            b"Delete removes the job, document, chunks, and unreferenced source.",
            "text/plain",
        )
        document_id = imported.json()["document"]["id"]
        with client.app.state.database.connection() as connection:
            relative = connection.execute(
                "SELECT storage_path FROM document_versions WHERE document_id = ?",
                (document_id,),
            ).fetchone()["storage_path"]
        stored = client.app.state.settings.document_data_path / relative
        assert stored.is_file()

        deleted = client.delete(f"/v1/documents/{document_id}", headers=auth_headers)
        assert deleted.status_code == 204
        assert not stored.exists()
        with client.app.state.database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM documents WHERE id = ?", (document_id,)
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM document_index_jobs WHERE document_id = ?",
                    (document_id,),
                ).fetchone()[0]
                == 0
            )
    finally:
        worker.resume_for_test()


def test_job_routes_require_auth(client):
    assert client.get("/v1/index-jobs/missing").status_code == 401
    assert client.post("/v1/index-jobs/missing/cancel").status_code == 401
    assert client.post("/v1/documents/missing/retry").status_code == 401
    assert client.delete("/v1/documents/missing").status_code == 401


def test_cancel_running_job_exits_worker_without_partial_chunks(
    client, auth_headers, monkeypatch
):
    started = threading.Event()

    def block_until_cancelled(
        _path,
        _extension,
        *,
        limits,
        progress_callback,
        cancellation_check,
    ):
        del limits, progress_callback
        started.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cancellation_check():
                raise DocumentProcessingCancelled("indexing was cancelled")
            time.sleep(0.01)
        raise AssertionError("worker did not observe cancellation")

    monkeypatch.setattr(index_worker_module, "parse_document", block_until_cancelled)
    imported = _upload(
        client,
        auth_headers,
        "running-cancel.txt",
        b"This parse remains active until its persistent cancellation flag is observed.",
        "text/plain",
    )
    assert imported.status_code == 202
    assert started.wait(2)
    job_id = imported.json()["job"]["id"]
    document_id = imported.json()["document"]["id"]

    cancelled = client.post(f"/v1/index-jobs/{job_id}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancel_requested"
    terminal = _wait_for_job(client, auth_headers, job_id)
    assert terminal["status"] == "cancelled"

    with client.app.state.database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            == 0
        )
    search = client.post(
        "/v1/search", headers=auth_headers, json={"query": "persistent"}
    )
    assert search.status_code == 200
    assert search.json()["results"] == []


def test_shutdown_marks_running_job_interrupted_and_stops_worker(
    tmp_path, auth_headers, monkeypatch
):
    started = threading.Event()

    def block_until_stopping(
        _path,
        _extension,
        *,
        limits,
        progress_callback,
        cancellation_check,
    ):
        del limits, progress_callback
        started.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cancellation_check():
                raise DocumentProcessingCancelled("indexing was interrupted")
            time.sleep(0.01)
        raise AssertionError("worker did not observe shutdown")

    monkeypatch.setattr(index_worker_module, "parse_document", block_until_stopping)
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "shutdown.sqlite3",
        document_data_path=tmp_path / "documents",
    )
    with TestClient(create_app(settings)) as test_client:
        imported = _upload(
            test_client,
            auth_headers,
            "shutdown.txt",
            b"Shutdown should persist an interrupted terminal state.",
            "text/plain",
        )
        job_id = imported.json()["job"]["id"]
        assert started.wait(2)

    with Database(settings.database_path).connection() as connection:
        job = IndexJobRepository(connection).get_job(job_id)
        assert job is not None
        assert job["status"] == "interrupted"
        assert "shutdown" in job["error"]


def test_startup_resumes_a_valid_queued_job(tmp_path, auth_headers):
    content = b"A queued persistent job resumes after the sidecar starts."
    settings, document_id, job_id, _stored = _prepare_persistent_job(
        tmp_path, content, status="queued"
    )

    with TestClient(create_app(settings)) as recovered:
        job = _wait_for_job(recovered, auth_headers, job_id)
        assert job["status"] == "completed"
        document = recovered.get("/v1/documents", headers=auth_headers).json()[
            "documents"
        ][0]
        assert document["id"] == document_id
        assert document["status"] == "indexed"


def test_startup_interrupts_running_job_then_retry_reuses_source(
    tmp_path, auth_headers
):
    content = b"A claimed job becomes explicitly interrupted after restart."
    settings, document_id, job_id, _stored = _prepare_persistent_job(
        tmp_path, content, status="running"
    )

    with TestClient(create_app(settings)) as recovered:
        interrupted = recovered.get(f"/v1/index-jobs/{job_id}", headers=auth_headers)
        assert interrupted.status_code == 200
        assert interrupted.json()["status"] == "interrupted"
        retried = recovered.post(
            f"/v1/documents/{document_id}/retry", headers=auth_headers
        )
        assert retried.status_code == 202
        assert (
            _wait_for_job(recovered, auth_headers, retried.json()["job"]["id"])[
                "status"
            ]
            == "completed"
        )


def test_startup_marks_missing_source_failed(tmp_path, auth_headers):
    settings, document_id, job_id, stored = _prepare_persistent_job(
        tmp_path, b"This source will be removed before startup.", status="queued"
    )
    stored.unlink()

    with TestClient(create_app(settings)) as recovered:
        job = recovered.get(f"/v1/index-jobs/{job_id}", headers=auth_headers).json()
        document = recovered.get("/v1/documents", headers=auth_headers).json()[
            "documents"
        ][0]
        assert job["status"] == "failed"
        assert "missing" in job["error"]
        assert document["id"] == document_id
        assert document["status"] == "failed"
        assert "missing" in document["error"]


def test_same_hash_reimport_repairs_missing_indexed_source_and_retries(
    tmp_path, auth_headers
):
    content = b"Re-import restores a missing indexed source without a duplicate record."
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "repair.sqlite3",
        document_data_path=tmp_path / "repair-documents",
    )
    with TestClient(create_app(settings)) as initial:
        imported = _upload(initial, auth_headers, "repair.txt", content, "text/plain")
        document_id = imported.json()["document"]["id"]
        assert (
            _wait_for_job(initial, auth_headers, imported.json()["job"]["id"])["status"]
            == "completed"
        )
        with initial.app.state.database.connection() as connection:
            relative = connection.execute(
                "SELECT storage_path FROM document_versions WHERE document_id = ?",
                (document_id,),
            ).fetchone()["storage_path"]
    stored = settings.document_data_path / relative
    stored.unlink()

    with TestClient(create_app(settings)) as recovered:
        failed_document = recovered.get("/v1/documents", headers=auth_headers).json()[
            "documents"
        ][0]
        assert failed_document["status"] == "failed"
        repaired = _upload(recovered, auth_headers, "repair.txt", content, "text/plain")
        assert repaired.status_code == 202
        assert repaired.json()["duplicate"] is True
        assert repaired.json()["document"]["id"] == document_id
        assert (
            _wait_for_job(recovered, auth_headers, repaired.json()["job"]["id"])[
                "status"
            ]
            == "completed"
        )
        assert stored.read_bytes() == content
        with recovered.app.state.database.connection() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
            )


def test_startup_quarantines_unreferenced_stored_file(tmp_path):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "orphan.sqlite3",
        document_data_path=tmp_path / "documents",
    )
    Database(settings.database_path).migrate()
    orphan = settings.document_data_path / "aa" / "orphan.txt"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"not referenced by the database")

    with TestClient(create_app(settings)):
        assert not orphan.exists()
        quarantined = list((settings.document_data_path / ".quarantine").iterdir())
        assert len(quarantined) == 1
        assert quarantined[0].read_bytes() == b"not referenced by the database"


def test_startup_restores_hash_matching_referenced_delete_quarantine(
    tmp_path, auth_headers
):
    settings, _document_id, job_id, stored = _prepare_persistent_job(
        tmp_path, b"Verified quarantine recovery content.", status="queued"
    )
    quarantine = settings.document_data_path / ".quarantine"
    quarantine.mkdir(mode=0o700)
    quarantined = quarantine / f"{'a' * 32}-{stored.name}"
    os.replace(stored, quarantined)

    with TestClient(create_app(settings)) as recovered:
        assert _wait_for_job(recovered, auth_headers, job_id)["status"] == "completed"
        assert stored.read_bytes() == b"Verified quarantine recovery content."
        assert not quarantined.exists()


def test_startup_retains_hash_mismatched_quarantine_and_marks_source_missing(
    tmp_path, auth_headers
):
    settings, _document_id, job_id, stored = _prepare_persistent_job(
        tmp_path, b"Expected source content.", status="queued"
    )
    quarantine = settings.document_data_path / ".quarantine"
    quarantine.mkdir(mode=0o700)
    quarantined = quarantine / f"{'b' * 32}-{stored.name}"
    stored.unlink()
    quarantined.write_bytes(b"tampered quarantine content")

    with TestClient(create_app(settings)) as recovered:
        job = recovered.get(f"/v1/index-jobs/{job_id}", headers=auth_headers).json()
        assert job["status"] == "failed"
        assert "missing" in job["error"]
        assert quarantined.read_bytes() == b"tampered quarantine content"
        assert not stored.exists()


def test_quarantine_rolls_back_first_move_when_second_move_fails(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    paths: list[str] = []
    sources = []
    for index, content in enumerate((b"first", b"second")):
        digest = sha256(content).hexdigest()
        source, relative = storage_destination(root, digest, ".txt")
        source.write_bytes(content)
        paths.append(relative)
        sources.append(source)
    real_replace = os.replace
    moves_to_quarantine = 0

    def fail_second_move(source, destination):
        nonlocal moves_to_quarantine
        if ".quarantine" in str(destination):
            moves_to_quarantine += 1
            if moves_to_quarantine == 2:
                raise OSError("injected second move failure")
        return real_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", fail_second_move)
    with pytest.raises(StoredFileDeleteError, match="deletion quarantine"):
        quarantine_for_delete(root, paths)

    assert [source.read_bytes() for source in sources] == [b"first", b"second"]


def test_delete_restores_source_when_database_transaction_fails(
    client, auth_headers, monkeypatch
):
    imported = _upload(
        client,
        auth_headers,
        "rollback.txt",
        b"The source must survive an injected database deletion failure.",
        "text/plain",
    )
    assert (
        _wait_for_job(client, auth_headers, imported.json()["job"]["id"])["status"]
        == "completed"
    )
    document_id = imported.json()["document"]["id"]
    with client.app.state.database.connection() as connection:
        relative = connection.execute(
            "SELECT storage_path FROM document_versions WHERE document_id = ?",
            (document_id,),
        ).fetchone()["storage_path"]
    stored = client.app.state.settings.document_data_path / relative

    monkeypatch.setattr(
        IndexJobRepository,
        "delete_document_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("injected database failure")
        ),
    )
    deleted = client.delete(f"/v1/documents/{document_id}", headers=auth_headers)
    assert deleted.status_code == 500
    assert "source was restored" in deleted.json()["detail"]
    assert stored.read_bytes().startswith(b"The source must survive")
    assert client.get("/v1/documents", headers=auth_headers).json()["documents"]


def test_delete_serializes_against_retry(
    client, auth_headers, blank_pdf_bytes, monkeypatch
):
    failed_import = _upload(
        client, auth_headers, "failed.pdf", blank_pdf_bytes, "application/pdf"
    )
    job_id = failed_import.json()["job"]["id"]
    assert _wait_for_job(client, auth_headers, job_id)["status"] == "failed"
    document_id = failed_import.json()["document"]["id"]
    entered_quarantine = threading.Event()
    release_quarantine = threading.Event()
    original = main_module.quarantine_for_delete

    def blocking_quarantine(root, storage_paths):
        entered_quarantine.set()
        assert release_quarantine.wait(3)
        return original(root, storage_paths)

    monkeypatch.setattr(main_module, "quarantine_for_delete", blocking_quarantine)
    with ThreadPoolExecutor(max_workers=2) as executor:
        deletion = executor.submit(
            client.delete, f"/v1/documents/{document_id}", headers=auth_headers
        )
        assert entered_quarantine.wait(2)
        retry = executor.submit(
            client.post, f"/v1/documents/{document_id}/retry", headers=auth_headers
        )
        time.sleep(0.05)
        assert not retry.done()
        release_quarantine.set()
        assert deletion.result(timeout=3).status_code == 204
        retry_response = retry.result(timeout=3)

    assert retry_response.status_code == 404


def _prepare_persistent_job(
    tmp_path, content: bytes, *, status: str
) -> tuple[Settings, str, str, object]:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / f"{status}.sqlite3",
        document_data_path=tmp_path / f"{status}-documents",
    )
    database = Database(settings.database_path)
    database.migrate()
    content_hash = sha256(content).hexdigest()
    stored, relative = storage_destination(
        settings.document_data_path, content_hash, ".txt"
    )
    stored.write_bytes(content)
    document_id = f"doc-{status}"
    job_id = f"job-{status}"
    with database.connection() as connection:
        DocumentRepository(connection).create_document(
            document_id=document_id,
            version_id=f"version-{status}",
            course_id=None,
            name=f"{status}.txt",
            mime_type="text/plain",
            extension=".txt",
            content_hash=content_hash,
            storage_path=relative,
            size_bytes=len(content),
            parser_version="keen-text/1;plain;keen-chunker/1",
            job_id=job_id,
        )
        if status == "running":
            claimed = IndexJobRepository(connection).claim_next_job("old-worker")
            assert claimed is not None
            assert claimed["id"] == job_id
    return settings, document_id, job_id, stored
