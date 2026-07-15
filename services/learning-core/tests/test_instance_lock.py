from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient

from app.instance_lock import InstanceAlreadyRunningError, hold_database_instance_lock
from app.main import create_app
from app.settings import Settings
from conftest import TOKEN


def test_database_instance_lock_is_exclusive_and_private(tmp_path) -> None:
    database_path = tmp_path / "learning-core.sqlite3"

    with hold_database_instance_lock(database_path) as lock_path:
        assert lock_path == tmp_path / "learning-core.sqlite3.lock"
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
        with pytest.raises(InstanceAlreadyRunningError):
            with hold_database_instance_lock(database_path):
                pass

    with hold_database_instance_lock(database_path):
        pass


def test_database_instance_lock_rejects_a_symlink(tmp_path) -> None:
    database_path = tmp_path / "learning-core.sqlite3"
    outside = tmp_path / "outside.lock"
    outside.write_text("not a lock", encoding="utf-8")
    os.symlink(outside, tmp_path / "learning-core.sqlite3.lock")

    with pytest.raises(OSError):
        with hold_database_instance_lock(database_path):
            pass


def test_database_instance_lock_uses_the_canonical_database_identity(tmp_path) -> None:
    database_path = tmp_path / "learning-core.sqlite3"
    database_path.touch()
    alias_path = tmp_path / "database-alias.sqlite3"
    alias_path.symlink_to(database_path)

    with hold_database_instance_lock(database_path) as lock_path:
        assert lock_path == tmp_path / "learning-core.sqlite3.lock"
        with pytest.raises(InstanceAlreadyRunningError):
            with hold_database_instance_lock(alias_path):
                pass


def test_second_app_cannot_recover_or_clean_an_active_database(tmp_path) -> None:
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "shared.sqlite3",
        document_data_path=tmp_path / "documents",
    )
    first = TestClient(create_app(settings))
    with first:
        incoming = settings.document_data_path / ".incoming"
        incoming.mkdir(mode=0o700, parents=True)
        active_upload = incoming / f"{'a' * 32}.upload"
        active_upload.write_bytes(b"active")

        with pytest.raises(InstanceAlreadyRunningError):
            with TestClient(create_app(settings)):
                pass

        assert active_upload.read_bytes() == b"active"
