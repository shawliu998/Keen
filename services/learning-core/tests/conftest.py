from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

TOKEN = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "test.sqlite3",
        seed_demo=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}
