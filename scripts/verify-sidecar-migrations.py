#!/usr/bin/env python3
"""Fail closed when the sidecar's packaged migration tree is incomplete."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


MIGRATION_NAME = re.compile(r"(?P<version>[0-9]{3})_[A-Za-z0-9][A-Za-z0-9_.-]*\.sql$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a continuous, sidecar-packaged SQL migration sequence."
    )
    parser.add_argument("migrations_dir", type=Path)
    parser.add_argument("--minimum-version", type=int, required=True)
    return parser.parse_args()


def validate_migrations(migrations_dir: Path, *, minimum_version: int) -> int:
    """Return the highest version or raise ValueError for unsafe migration input."""

    if minimum_version < 1:
        raise ValueError("minimum migration version must be positive")
    if not migrations_dir.is_dir():
        raise ValueError(f"migration directory is missing: {migrations_dir}")

    migrations: dict[int, Path] = {}
    sql_files = sorted(
        path for path in migrations_dir.iterdir() if path.suffix == ".sql"
    )
    if not sql_files:
        raise ValueError("migration directory has no SQL migrations")
    for path in sql_files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(
                f"migration must be a regular non-symlink file: {path.name}"
            )
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise ValueError(f"migration filename is invalid: {path.name}")
        version = int(match.group("version"))
        if version < 1:
            raise ValueError(f"migration version must start at 001: {path.name}")
        if version in migrations:
            raise ValueError(
                f"duplicate migration version {version:03d}: "
                f"{migrations[version].name}, {path.name}"
            )
        migrations[version] = path

    highest_version = max(migrations)
    missing = [
        version
        for version in range(1, highest_version + 1)
        if version not in migrations
    ]
    if missing:
        formatted = ", ".join(f"{version:03d}" for version in missing)
        raise ValueError(
            f"migration sequence is not continuous from 001: missing {formatted}"
        )
    if highest_version < minimum_version:
        raise ValueError(
            f"latest migration {highest_version:03d} is below required "
            f"{minimum_version:03d}"
        )
    return highest_version


def main() -> int:
    args = parse_args()
    try:
        highest_version = validate_migrations(
            args.migrations_dir, minimum_version=args.minimum_version
        )
    except ValueError as error:
        print(f"sidecar migrations: error: {error}")
        return 1
    print(
        "sidecar migrations: verified "
        f"001-{highest_version:03d} in {args.migrations_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
