from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Sequence

from fastapi.testclient import TestClient
import pytest

import app.index_worker as worker_module
from app.__main__ import parse_args, resolve_local_embedding_settings
from app.document_repository import DocumentRepository
from app.local_providers import LocalProviderError
from app.main import create_app
from app.retrieval_interfaces import EmbeddingModel
from app.settings import LocalEmbeddingSettings, Settings
from conftest import TOKEN


MODEL = EmbeddingModel(
    provider="ollama", model="fixture-embed", version="v1", dimensions=3
)


def test_embedding_cli_is_all_or_none_and_loopback_only() -> None:
    base = ["--token", TOKEN, "--port", "0", "--database", "/tmp/keen.sqlite3"]
    assert resolve_local_embedding_settings(parse_args(base)) is None
    with pytest.raises(SystemExit, match="configured together"):
        resolve_local_embedding_settings(
            parse_args([*base, "--embedding-provider", "ollama"])
        )
    with pytest.raises(SystemExit, match="loopback"):
        resolve_local_embedding_settings(
            parse_args(
                [
                    *base,
                    "--embedding-provider",
                    "ollama",
                    "--embedding-base-url",
                    "http://192.0.2.10:11434",
                    "--embedding-model",
                    "fixture",
                    "--embedding-version",
                    "v1",
                    "--embedding-dimensions",
                    "3",
                ]
            )
        )


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0.0, -1.0])
def test_embedding_configuration_rejects_unsafe_timeouts(timeout: float) -> None:
    with pytest.raises(ValueError, match="finite and greater than zero"):
        LocalEmbeddingSettings(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="fixture",
            version="v1",
            dimensions=3,
            read_timeout_seconds=timeout,
        )


@pytest.mark.parametrize("value", ["x\nsecret", "x" * 257])
def test_embedding_configuration_bounds_model_identity(value: str) -> None:
    with pytest.raises(ValueError, match="model and version"):
        LocalEmbeddingSettings(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model=value,
            version="v1",
            dimensions=3,
        )


class _Provider:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.model = MODEL
        self.failure = failure
        self.calls: list[tuple[str, ...]] = []
        self.closed = False

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.calls.append(tuple(texts))
        if self.failure is not None:
            raise self.failure
        return tuple((1.0, float(index), 0.25) for index, _ in enumerate(texts))

    async def embed_query(self, text: str) -> Sequence[float]:
        del text
        return (1.0, 0.0, 0.25)

    async def aclose(self) -> None:
        self.closed = True


class _BlockingProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.cancelled = threading.Event()

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.calls.append(tuple(texts))
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("unreachable")


def _settings(tmp_path, *, embedding: bool = True) -> Settings:
    return Settings(
        session_token=TOKEN,
        database_path=tmp_path / "embedding-jobs.sqlite3",
        local_embedding=(
            LocalEmbeddingSettings(
                provider="ollama",
                base_url="http://127.0.0.1:11434",
                model=MODEL.model,
                version=MODEL.version,
                dimensions=MODEL.dimensions,
            )
            if embedding
            else None
        ),
    )


def _upload(client: TestClient) -> dict:
    response = client.post(
        "/v1/documents/import",
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={
            "file": (
                "vectors.txt",
                b"Local embeddings remain optional while lexical search remains durable.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 202
    return response.json()


def _wait(client: TestClient, job_id: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    headers = {"Authorization": f"Bearer {TOKEN}"}
    while time.monotonic() < deadline:
        job = client.get(f"/v1/index-jobs/{job_id}", headers=headers).json()
        if job["status"] in {"cancelled", "completed", "failed", "interrupted"}:
            return job
        time.sleep(0.02)
    raise AssertionError("embedding job did not finish")


def test_provider_success_persists_ready_vectors_and_real_progress(
    tmp_path, monkeypatch
) -> None:
    provider = _Provider()
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda _: provider)
    with TestClient(create_app(_settings(tmp_path))) as client:
        imported = _upload(client)
        assert _wait(client, imported["job"]["id"])["status"] == "completed"
        with client.app.state.database.connection() as connection:
            state = connection.execute(
                "SELECT status, expected_chunk_count, embedded_chunk_count "
                "FROM document_embedding_state"
            ).fetchone()
            vectors = connection.execute(
                "SELECT dimensions, length(embedding) AS bytes FROM chunk_embeddings"
            ).fetchall()
        assert dict(state) == {
            "status": "ready",
            "expected_chunk_count": len(vectors),
            "embedded_chunk_count": len(vectors),
        }
        assert vectors and all(
            (row["dimensions"], row["bytes"]) == (3, 12) for row in vectors
        )
        assert provider.calls and provider.closed is True


def test_absent_provider_is_explicit_lexical_only_without_fake_state(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path, embedding=False))) as client:
        imported = _upload(client)
        assert _wait(client, imported["job"]["id"])["status"] == "completed"
        with client.app.state.database.connection() as connection:
            document = connection.execute(
                "SELECT status FROM documents WHERE id = ?",
                (imported["document"]["id"],),
            ).fetchone()
            state_count = connection.execute(
                "SELECT COUNT(*) FROM document_embedding_state"
            ).fetchone()[0]
        assert document["status"] == "indexed"
        assert state_count == 0


def test_provider_failure_retains_lexical_index_and_records_failed_state(
    tmp_path, monkeypatch
) -> None:
    provider = _Provider(failure=LocalProviderError("secret provider detail"))
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda _: provider)
    with TestClient(create_app(_settings(tmp_path))) as client:
        imported = _upload(client)
        assert _wait(client, imported["job"]["id"])["status"] == "completed"
        with client.app.state.database.connection() as connection:
            state = connection.execute(
                "SELECT status, error FROM document_embedding_state"
            ).fetchone()
            document = connection.execute(
                "SELECT status FROM documents WHERE id = ?",
                (imported["document"]["id"],),
            ).fetchone()
            vector_count = connection.execute(
                "SELECT COUNT(*) FROM chunk_embeddings"
            ).fetchone()[0]
        assert state["status"] == "failed"
        assert state["error"] == (
            "local embedding provider is unavailable; lexical indexing completed"
        )
        assert document["status"] == "indexed"
        assert vector_count == 0


def test_cancellation_interrupts_http_task_and_removes_invisible_staging(
    tmp_path, monkeypatch
) -> None:
    provider = _BlockingProvider()
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda _: provider)
    with TestClient(create_app(_settings(tmp_path))) as client:
        imported = _upload(client)
        assert provider.started.wait(3)
        document_id = imported["document"]["id"]
        job_id = imported["job"]["id"]
        headers = {"Authorization": f"Bearer {TOKEN}"}
        search = client.post(
            "/v1/search", headers=headers, json={"query": "lexical durable"}
        )
        assert search.json()["results"] == []
        assert (
            client.post(f"/v1/index-jobs/{job_id}/cancel", headers=headers).status_code
            == 200
        )
        assert _wait(client, job_id)["status"] == "cancelled"
        assert provider.cancelled.wait(1)
        with client.app.state.database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                    (document_id,),
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[
                    0
                ]
                == 0
            )


def test_model_change_is_detected_as_needing_reindex(tmp_path, monkeypatch) -> None:
    provider = _Provider()
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda _: provider)
    with TestClient(create_app(_settings(tmp_path))) as client:
        imported = _upload(client)
        assert _wait(client, imported["job"]["id"])["status"] == "completed"
        with client.app.state.database.connection() as connection:
            repository = DocumentRepository(connection)
            assert (
                repository.embedding_reindex_required(imported["document"]["id"], MODEL)
                is False
            )
            changed = EmbeddingModel(
                provider=MODEL.provider,
                model=MODEL.model,
                version="v2",
                dimensions=MODEL.dimensions,
            )
            assert (
                repository.embedding_reindex_required(
                    imported["document"]["id"], changed
                )
                is True
            )
