from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class InstanceAlreadyRunningError(RuntimeError):
    pass


@contextmanager
def hold_database_instance_lock(database_path: Path) -> Iterator[Path]:
    """Own one database exclusively for migration, recovery, and request handling."""

    database_path = database_path.expanduser()
    database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    canonical_parent = database_path.parent.resolve(strict=True)
    database_identity = canonical_parent / database_path.name
    if database_identity.exists() or database_identity.is_symlink():
        database_identity = database_identity.resolve(strict=True)
    lock_path = database_identity.with_name(f"{database_identity.name}.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("learning-core instance lock is not a regular file")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstanceAlreadyRunningError(
                "another learning-core process already owns this database"
            ) from error
        yield lock_path
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
