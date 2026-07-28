from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol


class VectorExtensionLoader(Protocol):
    def __call__(self, connection: sqlite3.Connection) -> None: ...


class VectorCapabilityError(RuntimeError):
    """Raised only by vector operations when sqlite-vec is unavailable."""


class ExtensionLoadingSecurityError(RuntimeError):
    """The enabled connection was closed because loading could not be disabled."""


def _load_sqlite_vec(connection: sqlite3.Connection) -> None:
    import sqlite_vec

    sqlite_vec.load(connection)


class Database:
    def __init__(
        self,
        path: Path,
        *,
        vector_extension_loader: VectorExtensionLoader = _load_sqlite_vec,
    ) -> None:
        self.path = path
        self._vector_extension_loader = vector_extension_loader
        self._vector_extension_error: str | None = None

    def connect(self) -> sqlite3.Connection:
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() or self.path.is_symlink():
                metadata = self.path.lstat()
                if (
                    self.path.is_symlink()
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                ):
                    raise RuntimeError(
                        "learning-core database path must be a regular file"
                    )
                os.chmod(self.path, 0o600)
        # FastAPI may enter, consume, and close a synchronous yield dependency on
        # different worker threads. Each connection remains request-scoped and is
        # never used concurrently, so disabling SQLite's creator-thread assertion is safe.
        connection = sqlite3.connect(self.path, timeout=10.0, check_same_thread=False)
        if self.path != Path(":memory:"):
            os.chmod(self.path, 0o600)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            self._try_load_vector_extension(connection)
        except ExtensionLoadingSecurityError:
            # The unsafe connection was closed by _try_load_vector_extension.
            # Reopen a fresh connection that never enables extension loading so
            # lexical storage remains available without retaining that capability.
            connection = sqlite3.connect(
                self.path, timeout=10.0, check_same_thread=False
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @property
    def vector_extension_error(self) -> str | None:
        return self._vector_extension_error

    def require_vector_extension(self, connection: sqlite3.Connection) -> str:
        try:
            version = connection.execute("SELECT vec_version()").fetchone()[0]
        except sqlite3.Error as error:
            reason = self._vector_extension_error or error.__class__.__name__
            raise VectorCapabilityError(
                f"sqlite-vec capability is unavailable: {reason}"
            ) from error
        return str(version)

    def _try_load_vector_extension(self, connection: sqlite3.Connection) -> None:
        extension_loading_enabled = False
        try:
            connection.enable_load_extension(True)
            extension_loading_enabled = True
            self._vector_extension_loader(connection)
        except (
            AttributeError,
            ImportError,
            OSError,
            RuntimeError,
            sqlite3.Error,
        ) as error:
            self._vector_extension_error = error.__class__.__name__
        else:
            self._vector_extension_error = None
        finally:
            if extension_loading_enabled:
                try:
                    connection.enable_load_extension(False)
                except (AttributeError, OSError, RuntimeError, sqlite3.Error) as error:
                    self._vector_extension_error = error.__class__.__name__
                    connection.close()
                    raise ExtensionLoadingSecurityError(
                        "SQLite extension loading could not be disabled safely"
                    ) from error

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> list[int]:
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        applied: list[int] = []
        with self.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()
            existing = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for path in sorted(migrations_dir.glob("*.sql")):
                version_text = path.name.split("_", 1)[0]
                if not version_text.isdigit():
                    continue
                version = int(version_text)
                if version in existing:
                    continue
                sql = path.read_text(encoding="utf-8")
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + sql
                    + f"\nINSERT INTO schema_migrations(version) VALUES ({version});\n"
                    + "COMMIT;"
                )
                applied.append(version)
                existing.add(version)
        return applied

    def seed_demo(self) -> None:
        seed_path = Path(__file__).resolve().parent.parent / "seeds" / "demo.sql"
        with self.connection() as connection:
            connection.executescript(seed_path.read_text(encoding="utf-8"))
            connection.commit()

    def verify_consistency(self) -> None:
        """Fail startup when SQLite or its declared relationships are inconsistent."""

        with self.connection() as connection:
            integrity_errors = [
                row[0]
                for row in connection.execute("PRAGMA quick_check")
                if row[0] != "ok"
            ]
            foreign_key_errors = list(connection.execute("PRAGMA foreign_key_check"))
        if integrity_errors or foreign_key_errors:
            raise RuntimeError("learning-core database consistency check failed")
