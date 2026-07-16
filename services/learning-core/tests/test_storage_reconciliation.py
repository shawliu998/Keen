from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app
from app.settings import Settings
from app.storage_reconciliation import StoredFileDeleteError
from conftest import TOKEN


def _upload(client, headers, name: str, content: bytes, media_type: str):
    return client.post(
        "/v1/documents/import",
        headers=headers,
        files={"file": (name, content, media_type)},
    )


def test_delete_missing_physical_source_still_removes_database_records(
    client, auth_headers
):
    worker = client.app.state.document_index_worker
    worker.pause_for_test()
    try:
        imported = _upload(
            client,
            auth_headers,
            "missing-before-delete.txt",
            b"The database remains deletable after its physical source disappears.",
            "text/plain",
        )
        assert imported.status_code == 202
        document_id = imported.json()["document"]["id"]
        with client.app.state.database.connection() as connection:
            relative = connection.execute(
                "SELECT storage_path FROM document_versions WHERE document_id = ?",
                (document_id,),
            ).fetchone()["storage_path"]
        stored = client.app.state.settings.document_data_path / relative
        stored.unlink()

        deleted = client.delete(f"/v1/documents/{document_id}", headers=auth_headers)

        assert deleted.status_code == 204
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


def test_delete_cleanup_failure_is_retried_by_startup_maintenance(
    tmp_path, auth_headers, monkeypatch
):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "cleanup-recovery.sqlite3",
        document_data_path=tmp_path / "cleanup-recovery-documents",
    )
    with TestClient(create_app(settings)) as client:
        worker = client.app.state.document_index_worker
        worker.pause_for_test()
        imported = _upload(
            client,
            auth_headers,
            "cleanup-recovery.txt",
            b"Startup maintenance removes quarantine after durable DB deletion.",
            "text/plain",
        )
        assert imported.status_code == 202
        document_id = imported.json()["document"]["id"]

        def fail_quarantine_cleanup(_files) -> None:
            raise StoredFileDeleteError(
                "document record was deleted but quarantined source cleanup failed"
            )

        with monkeypatch.context() as scoped_patch:
            scoped_patch.setattr(
                main_module, "remove_quarantined_files", fail_quarantine_cleanup
            )
            deleted = client.delete(
                f"/v1/documents/{document_id}", headers=auth_headers
            )

        assert deleted.status_code == 500
        assert "restart Keen" in deleted.json()["detail"]
        with client.app.state.database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM documents WHERE id = ?", (document_id,)
                ).fetchone()[0]
                == 0
            )
        quarantine = settings.document_data_path / ".quarantine"
        leftovers = list(quarantine.iterdir())
        assert len(leftovers) == 1
        assert leftovers[0].is_file()
        worker.resume_for_test()

    with TestClient(create_app(settings)):
        pass

    assert list((settings.document_data_path / ".quarantine").iterdir()) == []
