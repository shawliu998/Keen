from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.documents as documents_module
import app.main as main_module
from app.database import Database
from app.document_repository import DocumentRepository
from app.documents import ParsedChunk, ParsedDocument, storage_destination
from app.index_jobs import IndexJobRepository
from app.main import create_app
from app.settings import Settings
from conftest import TOKEN


TERMINAL_JOB_STATUSES = {"cancelled", "completed", "failed", "interrupted"}


def _blocking_pdf_worker(path: str, connection, limits=None) -> None:
    """A spawn-safe isolated parser with a real descendant in its process group."""

    del limits
    try:
        os.setpgid(0, 0)
        worker_pid = os.getpid()
        process_group = os.getpgrp()
        connection.send(("ready", (worker_pid, process_group)))
        if not connection.poll(5) or connection.recv() != "start":
            return
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        Path(f"{path}.worker-state").write_text(
            f"{worker_pid},{process_group},{descendant.pid}", encoding="utf-8"
        )
        connection.send(("progress", ("parsing", 0, 1)))
        while True:
            time.sleep(1)
    finally:
        connection.close()


@pytest.mark.parametrize("_iteration", range(12))
def test_queued_cancel_losing_claim_cas_does_not_fail_claimed_document(
    tmp_path, _iteration
):
    settings, document_id, job_id, database = _seed_text_job(tmp_path, "claim-cas")
    cancel_started = threading.Event()

    def request_cancel() -> dict | None:
        cancel_started.set()
        with database.connection() as connection:
            return IndexJobRepository(connection).request_cancel(job_id)

    # Hold the claim's write transaction open while cancellation starts. The
    # cancellation must serialize behind it, observe running, and never apply the
    # stale queued->failed document transition.
    with database.connection() as claim_connection:
        claim_connection.execute("BEGIN IMMEDIATE")
        claim_connection.execute(
            """
            UPDATE document_index_jobs
            SET status = 'running', stage = 'parsing', progress = 15,
                worker_generation = 'race-worker'
            WHERE id = ? AND status = 'queued'
            """,
            (job_id,),
        )
        claim_connection.execute(
            "UPDATE documents SET status = 'parsing', error = NULL WHERE id = ?",
            (document_id,),
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            cancellation = executor.submit(request_cancel)
            assert cancel_started.wait(1)
            claim_connection.commit()
            observed = cancellation.result(timeout=3)

    assert observed is not None
    assert observed["status"] == "cancel_requested"
    assert observed["cancel_requested"] is True
    with database.connection() as connection:
        document = DocumentRepository(connection).get_document(document_id)
    assert document is not None
    assert document["status"] == "parsing"
    assert document["error"] is None
    assert settings.document_data_path is not None


def test_late_unsuccessful_finalize_does_not_downgrade_completed_indexed_document(
    tmp_path,
):
    _settings, document_id, job_id, database = _seed_text_job(tmp_path, "finalize-cas")

    with database.connection() as connection:
        jobs = IndexJobRepository(connection)
        documents = DocumentRepository(connection)
        assert jobs.claim_next_job("finalize-worker") is not None
        documents.transition_status(document_id, "chunking")
        chunk_content = "durably indexed before a stale failure handler runs"
        documents.index_document(
            job_id=job_id,
            document_id=document_id,
            version_id="version-finalize-cas",
            parsed=ParsedDocument(
                page_count=1,
                parser_version="keen-text/1;plain;keen-chunker/1",
                chunks=(
                    ParsedChunk(
                        ordinal=0,
                        page_number=1,
                        section_path=(),
                        content=chunk_content,
                        content_hash=sha256(chunk_content.encode()).hexdigest(),
                        unit_ordinal=0,
                        start_character=0,
                        end_character=len(chunk_content),
                    ),
                ),
            ),
        )

        # A cancellation/error handler that was already in flight must lose to the
        # completed terminal state without changing the paired document state.
        jobs.mark_failed(job_id, "late worker failure after durable finalization")

        job = jobs.get_job(job_id)
        document = documents.get_document(document_id)

    assert job is not None
    assert job["status"] == "completed"
    assert job["error"] is None
    assert document is not None
    assert document["status"] == "indexed"
    assert document["error"] is None


def test_http_cancel_running_pdf_kills_process_group_without_searchable_partial(
    tmp_path, auth_headers, pdf_bytes, monkeypatch
):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "pdf-cancel.sqlite3",
        document_data_path=tmp_path / "pdf-cancel-documents",
        pdf_no_progress_timeout_seconds=10,
        pdf_total_timeout_seconds=20,
    )
    monkeypatch.setattr(documents_module, "_pdf_parse_worker", _blocking_pdf_worker)
    process_group: int | None = None
    try:
        with TestClient(create_app(settings)) as client:
            imported = _upload(
                client,
                auth_headers,
                "cancel-process-group.pdf",
                pdf_bytes,
                "application/pdf",
            )
            assert imported.status_code == 202
            document_id = imported.json()["document"]["id"]
            job_id = imported.json()["job"]["id"]
            with client.app.state.database.connection() as connection:
                relative = connection.execute(
                    "SELECT storage_path FROM document_versions WHERE document_id = ?",
                    (document_id,),
                ).fetchone()["storage_path"]
            state_path = Path(f"{settings.document_data_path / relative}.worker-state")
            assert _wait_until(state_path.exists, timeout=5)
            _worker_pid, process_group, descendant_pid = (
                int(value)
                for value in state_path.read_text(encoding="utf-8").split(",")
            )
            assert _live_process_group_members(process_group)

            cancelled = client.post(
                f"/v1/index-jobs/{job_id}/cancel", headers=auth_headers
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancel_requested"
            terminal = _wait_for_job(client, auth_headers, job_id)
            assert terminal["status"] == "cancelled"
            assert _wait_until(
                lambda: not _live_process_group_members(process_group), timeout=3
            )
            assert descendant_pid not in _live_process_group_members(process_group)

            with client.app.state.database.connection() as connection:
                assert (
                    connection.execute(
                        "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                        (document_id,),
                    ).fetchone()[0]
                    == 0
                )
            search = client.post(
                "/v1/search",
                headers=auth_headers,
                json={"query": "photosynthesis"},
            )
            assert search.status_code == 200
            assert search.json()["results"] == []
    finally:
        if (
            process_group is not None
            and process_group > 1
            and process_group != os.getpgrp()
            and _live_process_group_members(process_group)
        ):
            os.killpg(process_group, signal.SIGKILL)


def test_delete_and_retry_are_serialized_by_the_document_mutation_lock(
    tmp_path, auth_headers, monkeypatch
):
    settings, document_id, job_id, database = _seed_text_job(tmp_path, "delete-retry")
    with database.connection() as connection:
        jobs = IndexJobRepository(connection)
        assert jobs.claim_next_job("failed-worker") is not None
        jobs.mark_failed(job_id, "deterministic retryable failure")

    retry_entered = threading.Event()
    release_retry = threading.Event()
    delete_entered = threading.Event()
    original_retry = IndexJobRepository.create_retry_job
    original_quarantine = main_module.quarantine_for_delete

    def blocking_retry(repository, *, job_id: str, document_id: str):
        retry_entered.set()
        assert release_retry.wait(3)
        return original_retry(repository, job_id=job_id, document_id=document_id)

    def observed_quarantine(root, storage_paths):
        delete_entered.set()
        return original_quarantine(root, storage_paths)

    monkeypatch.setattr(IndexJobRepository, "create_retry_job", blocking_retry)
    monkeypatch.setattr(main_module, "quarantine_for_delete", observed_quarantine)
    with TestClient(create_app(settings)) as client:
        worker = client.app.state.document_index_worker
        worker.pause_for_test()
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                retry = executor.submit(
                    client.post,
                    f"/v1/documents/{document_id}/retry",
                    headers=auth_headers,
                )
                assert retry_entered.wait(2)
                deletion = executor.submit(
                    client.delete,
                    f"/v1/documents/{document_id}",
                    headers=auth_headers,
                )
                assert not delete_entered.wait(0.2)
                release_retry.set()
                assert retry.result(timeout=3).status_code == 202
                assert deletion.result(timeout=3).status_code == 204
        finally:
            worker.resume_for_test()

        with client.app.state.database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM documents WHERE id = ?", (document_id,)
                ).fetchone()[0]
                == 0
            )


def test_restart_resumes_persisted_queued_job(tmp_path, auth_headers):
    settings, document_id, job_id, _database = _seed_text_job(
        tmp_path, "restart-queued"
    )

    with TestClient(create_app(settings)) as client:
        job = _wait_for_job(client, auth_headers, job_id)
        assert job["status"] == "completed"
        documents = client.get("/v1/documents", headers=auth_headers).json()[
            "documents"
        ]
        assert [(item["id"], item["status"]) for item in documents] == [
            (document_id, "indexed")
        ]


def test_restart_interrupts_running_job_then_retry_completes(tmp_path, auth_headers):
    settings, document_id, job_id, database = _seed_text_job(
        tmp_path, "restart-running"
    )
    with database.connection() as connection:
        claimed = IndexJobRepository(connection).claim_next_job("dead-worker")
        assert claimed is not None
        assert claimed["status"] == "running"

    with TestClient(create_app(settings)) as client:
        interrupted = client.get(f"/v1/index-jobs/{job_id}", headers=auth_headers)
        assert interrupted.status_code == 200
        assert interrupted.json()["status"] == "interrupted"
        retried = client.post(
            f"/v1/documents/{document_id}/retry", headers=auth_headers
        )
        assert retried.status_code == 202
        terminal = _wait_for_job(client, auth_headers, retried.json()["job"]["id"])
        assert terminal["status"] == "completed"


def _upload(client, headers, name: str, content: bytes, media_type: str):
    return client.post(
        "/v1/documents/import",
        headers=headers,
        files={"file": (name, content, media_type)},
    )


def _wait_for_job(client, headers, job_id: str, timeout: float = 5) -> dict:
    terminal: dict | None = None

    def finished() -> bool:
        nonlocal terminal
        response = client.get(f"/v1/index-jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        terminal = response.json()
        return terminal["status"] in TERMINAL_JOB_STATUSES

    assert _wait_until(finished, timeout=timeout)
    assert terminal is not None
    return terminal


def _wait_until(predicate, *, timeout: float, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _live_process_group_members(process_group: int) -> set[int]:
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,pgid=,stat="],
        check=True,
        capture_output=True,
        text=True,
        timeout=1,
    )
    live: set[int] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        pid, pgid, state = parts
        if int(pgid) == process_group and not state.upper().startswith("Z"):
            live.add(int(pid))
    return live


def _seed_text_job(tmp_path: Path, name: str) -> tuple[Settings, str, str, Database]:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / f"{name}.sqlite3",
        document_data_path=tmp_path / f"{name}-documents",
    )
    database = Database(settings.database_path)
    database.migrate()
    content = f"deterministic adversarial fixture for {name}".encode()
    content_hash = sha256(content).hexdigest()
    stored, relative = storage_destination(
        settings.document_data_path, content_hash, ".txt"
    )
    stored.write_bytes(content)
    document_id = f"doc-{name}"
    job_id = f"job-{name}"
    with database.connection() as connection:
        DocumentRepository(connection).create_document(
            document_id=document_id,
            version_id=f"version-{name}",
            course_id=None,
            name=f"{name}.txt",
            mime_type="text/plain",
            extension=".txt",
            content_hash=content_hash,
            storage_path=relative,
            size_bytes=len(content),
            parser_version="keen-text/1;plain;keen-chunker/1",
            job_id=job_id,
        )
    return settings, document_id, job_id, database
