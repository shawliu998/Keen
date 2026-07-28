from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import app.index_worker as worker_module
from app.local_providers import LocalProviderError
from app.main import create_app
from app.retrieval_interfaces import EmbeddingModel
from app.settings import LocalEmbeddingSettings, Settings

TOKEN = "0123456789abcdef0123456789abcdef"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class _Provider:
    def __init__(self, model: EmbeddingModel, *, fail: bool = False) -> None:
        self._model = model
        self._fail = fail

    @property
    def model(self) -> EmbeddingModel:
        return self._model

    async def embed_documents(self, texts):
        if self._fail:
            raise LocalProviderError("untrusted provider response detail")
        return tuple((1.0, 0.0, 0.0) for _ in texts)

    async def embed_query(self, _text):
        if self._fail:
            raise LocalProviderError("untrusted provider response detail")
        return (1.0, 0.0, 0.0)

    async def aclose(self) -> None:
        return None


def _configuration(version: str = "v1") -> LocalEmbeddingSettings:
    return LocalEmbeddingSettings(
        provider="ollama",
        base_url="http://127.0.0.1:11434",
        model="fixture-embed",
        version=version,
        dimensions=3,
    )


def _settings(root: Path, configuration: LocalEmbeddingSettings | None) -> Settings:
    return Settings(
        session_token=TOKEN,
        database_path=root / "learning.sqlite3",
        document_data_path=root / "documents",
        seed_demo=True,
        local_embedding=configuration,
    )


def _factory(configuration: LocalEmbeddingSettings, *, fail: bool = False):
    return _Provider(
        EmbeddingModel(
            provider=configuration.provider,
            model=configuration.model,
            version=configuration.version,
            dimensions=configuration.dimensions,
        ),
        fail=fail,
    )


def _upload_and_wait(client: TestClient) -> str:
    response = client.post(
        "/v1/documents/import",
        headers=HEADERS,
        files={
            "file": (
                "vectors.txt",
                b"An eigenvector preserves direction after a matrix transformation.",
                "text/plain",
            )
        },
        data={"course_id": "course-calculus"},
    )
    assert response.status_code == 202
    body = response.json()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/v1/index-jobs/{body['job']['id']}", headers=HEADERS).json()
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            assert job["status"] == "completed"
            return body["document"]["id"]
        time.sleep(0.02)
    raise AssertionError("indexing did not complete")


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/v1/index-jobs/{job_id}", headers=HEADERS).json()
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.02)
    raise AssertionError("indexing did not complete")


def test_provider_missing_is_explicit_in_document_and_search_state(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path, None))) as client:
        document_id = _upload_and_wait(client)
        document = client.get("/v1/documents", headers=HEADERS).json()["documents"][0]
        search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "eigenvector direction", "limit": 8},
        ).json()
        reindex = client.post(
            f"/v1/documents/{document_id}/embedding-reindex", headers=HEADERS
        )

    assert document["id"] == document_id
    assert document["indexState"] == "indexed-lexical"
    assert document["embeddingStatus"] == "provider-missing"
    assert document["providerConfigured"] is False
    assert "lexical search remains available" in document["retrievalWarning"]
    assert search["mode"] == "lexical_only"
    assert "not configured" in search["warning"]
    assert search["results"]
    assert search["results"][0]["chunkIds"] == [search["results"][0]["chunkId"]]
    assert reindex.status_code == 409
    assert reindex.json()["detail"]["retryable"] is False
    assert "must be configured" in reindex.json()["detail"]["message"]


def test_ready_embeddings_produce_hybrid_state_and_search(
    tmp_path, monkeypatch
) -> None:
    configuration = _configuration()
    monkeypatch.setattr(
        worker_module, "create_embedding_provider", lambda value: _factory(value)
    )
    with TestClient(
        create_app(
            _settings(tmp_path, configuration),
            embedding_provider_factory=lambda value: _factory(value),
        )
    ) as client:
        _upload_and_wait(client)
        document = client.get("/v1/documents", headers=HEADERS).json()["documents"][0]
        search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "eigenvector direction", "limit": 8},
        ).json()
        reindex = client.post(
            f"/v1/documents/{document['id']}/embedding-reindex", headers=HEADERS
        )
        assert reindex.status_code == 202
        assert reindex.json()["job"]["operation"] == "embedding_reindex"
        with client.app.state.database.connection() as connection:
            during = connection.execute(
                "SELECT status, chunk_count FROM documents WHERE id = ?",
                (document["id"],),
            ).fetchone()
        assert dict(during) == {"status": "indexed", "chunk_count": 1}
        assert _wait_for_job(client, reindex.json()["job"]["id"])["status"] == (
            "completed"
        )
        rebuilt_document = client.get("/v1/documents", headers=HEADERS).json()[
            "documents"
        ][0]
        rebuilt_search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "eigenvector direction", "limit": 8},
        ).json()

    assert document["indexState"] == "indexed-hybrid"
    assert document["embeddingStatus"] == "ready"
    assert document["retrievalWarning"] is None
    assert search["mode"] == "hybrid"
    assert search["warning"] is None
    assert search["results"]
    assert rebuilt_document["indexState"] == "indexed-hybrid"
    assert rebuilt_search["mode"] == "hybrid"


def test_provider_failure_keeps_lexical_results_and_safe_failure_state(
    tmp_path, monkeypatch
) -> None:
    configuration = _configuration()
    monkeypatch.setattr(
        worker_module,
        "create_embedding_provider",
        lambda value: _factory(value, fail=True),
    )
    with TestClient(
        create_app(
            _settings(tmp_path, configuration),
            embedding_provider_factory=lambda value: _factory(value, fail=True),
        )
    ) as client:
        _upload_and_wait(client)
        document = client.get("/v1/documents", headers=HEADERS).json()["documents"][0]
        search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "eigenvector direction", "limit": 8},
        ).json()

    assert document["indexState"] == "indexed-lexical"
    assert document["embeddingStatus"] == "provider-failure"
    assert document["embeddingError"] == (
        "local embedding provider is unavailable; lexical indexing completed"
    )
    assert "untrusted provider response detail" not in str(document)
    assert search["mode"] == "lexical_only"
    assert "local provider recovers" in search["warning"]
    assert search["results"]


def test_provider_runtime_failure_downgrades_a_ready_index(
    tmp_path, monkeypatch
) -> None:
    configuration = _configuration()
    monkeypatch.setattr(
        worker_module, "create_embedding_provider", lambda value: _factory(value)
    )
    with TestClient(create_app(_settings(tmp_path, configuration))) as client:
        _upload_and_wait(client)

    with TestClient(
        create_app(
            _settings(tmp_path, configuration),
            embedding_provider_factory=lambda value: _factory(value, fail=True),
        )
    ) as client:
        search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "eigenvector direction", "limit": 8},
        ).json()

    assert search["mode"] == "lexical_only"
    assert "configured local embedding provider is unavailable" in search["warning"]
    assert search["results"]


def test_model_change_marks_needs_reindex_and_does_not_mix_vectors(
    tmp_path, monkeypatch
) -> None:
    first = _configuration("v1")
    monkeypatch.setattr(
        worker_module, "create_embedding_provider", lambda value: _factory(value)
    )
    with TestClient(create_app(_settings(tmp_path, first))) as client:
        _upload_and_wait(client)

    changed = _configuration("v2")
    with TestClient(
        create_app(
            _settings(tmp_path, changed),
            embedding_provider_factory=lambda value: _factory(value),
        )
    ) as client:
        document = client.get("/v1/documents", headers=HEADERS).json()["documents"][0]
        search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "eigenvector direction", "limit": 8},
        ).json()

    assert document["indexState"] == "needs-reindex"
    assert document["embeddingStatus"] == "needs-reindex"
    assert "v2" in document["embeddingModel"]
    assert search["mode"] == "lexical_only"
    assert "reindex is required" in search["warning"]
    assert search["results"]


def test_vector_extension_failure_downgrades_without_hiding_lexical_results(
    tmp_path, monkeypatch
) -> None:
    configuration = _configuration()
    monkeypatch.setattr(
        worker_module, "create_embedding_provider", lambda value: _factory(value)
    )
    with TestClient(create_app(_settings(tmp_path, configuration))) as client:
        _upload_and_wait(client)

    def unavailable(_connection) -> None:
        raise OSError("native extension unavailable")

    app = create_app(
        _settings(tmp_path, configuration),
        embedding_provider_factory=lambda value: _factory(value),
    )
    with TestClient(app) as client:
        client.app.state.database._vector_extension_loader = unavailable
        document = client.get("/v1/documents", headers=HEADERS).json()["documents"][0]
        search = client.post(
            "/v1/search",
            headers=HEADERS,
            json={"query": "eigenvector direction", "limit": 8},
        ).json()

    assert document["indexState"] == "indexed-lexical"
    assert document["embeddingStatus"] == "ready"
    assert "sqlite-vec is unavailable" in document["retrievalWarning"]
    assert search["mode"] == "lexical_only"
    assert "sqlite-vec extension is unavailable" in search["warning"]
    assert search["results"]
