from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.routers import providers
from app.settings import LocalChatSettings, Settings
from conftest import TOKEN


AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_provider_test_requires_configuration_without_starting_a_probe(
    tmp_path,
) -> None:
    with TestClient(
        create_app(
            Settings(
                session_token=TOKEN,
                database_path=tmp_path / "provider-missing.sqlite3",
            )
        )
    ) as client:
        response = client.post("/v1/provider/test", headers=AUTH)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": (
            "No provider is configured. Save an Ollama or "
            "OpenAI-compatible provider first."
        ),
        "retryable": False,
        "recovery": "Open Settings and save a provider configuration.",
    }


def test_provider_test_uses_current_process_settings_without_exposing_key(
    tmp_path, monkeypatch
) -> None:
    secret = "test-only-provider-key"
    local_chat = LocalChatSettings(
        provider="openai-compatible",
        base_url="https://api.example.com/v1",
        model="replacement-model",
        version="replacement-model",
        api_key=secret,
    )
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "provider-current.sqlite3",
        local_chat=local_chat,
    )
    observed: list[LocalChatSettings] = []

    async def probe(configuration: LocalChatSettings) -> str:
        observed.append(configuration)
        return "Connected"

    monkeypatch.setattr(providers, "test_provider_connectivity", probe)
    with TestClient(create_app(settings)) as client:
        response = client.post("/v1/provider/test", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "status": "connected",
        "provider": "openai-compatible",
        "model": "replacement-model",
        "detail": "Connected",
    }
    assert observed == [local_chat]
    assert secret not in response.text
    assert secret not in repr(local_chat)
    assert secret not in repr(settings)
