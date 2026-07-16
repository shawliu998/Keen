from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .database import Database
from .documents import (
    DocumentParseError,
    ensure_private_directory,
    resolve_stored_document_path,
    storage_destination,
)
from .index_jobs import IndexJobRepository

logger = logging.getLogger("keen.learning_core.storage")


class StoredFileDeleteError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QuarantinedFile:
    source: Path
    quarantine: Path


def reconcile_document_storage(database: Database, root: Path) -> dict[str, int]:
    resolved_root = ensure_private_directory(root)
    with database.connection() as connection:
        jobs = IndexJobRepository(connection)
        references = jobs.referenced_storage_paths()
        duplicate_hashes = jobs.duplicate_hashes()

    quarantine_recovery = _recover_delete_quarantine(resolved_root, references)
    referenced_paths = {str(item["storage_path"]) for item in references}
    missing = 0
    for reference in references:
        try:
            resolve_stored_document_path(resolved_root, str(reference["storage_path"]))
        except DocumentParseError:
            missing += 1
            with database.connection() as connection:
                IndexJobRepository(connection).mark_missing_storage(
                    str(reference["document_id"]), str(reference["storage_path"])
                )
            logger.warning(
                "document_storage_reconciled",
                extra={
                    "document_id": reference["document_id"],
                    "hash_prefix": str(reference["content_hash"])[:12],
                    "action": "mark_missing",
                    "result": "failed_document",
                },
            )

    quarantined = 0
    for candidate in _stored_files(resolved_root):
        relative = candidate.relative_to(resolved_root).as_posix()
        if relative in referenced_paths:
            continue
        quarantine = _quarantine_destination(resolved_root, candidate.name)
        os.replace(candidate, quarantine)
        quarantined += 1
        logger.info(
            "document_storage_reconciled",
            extra={
                "hash_prefix": candidate.stem[:12],
                "action": "quarantine_orphan",
                "result": "moved",
            },
        )

    for duplicate in duplicate_hashes:
        logger.warning(
            "document_storage_reconciled",
            extra={
                "hash_prefix": str(duplicate["content_hash"])[:12],
                "action": "duplicate_hash_check",
                "result": f"{duplicate['document_count']}_documents",
            },
        )
    return {
        "missing": missing,
        "quarantined": quarantined,
        "duplicate_hashes": len(duplicate_hashes),
        "delete_quarantine_restored": quarantine_recovery["restored"],
        "delete_quarantine_removed": quarantine_recovery["removed"],
    }


def quarantine_for_delete(
    root: Path, storage_paths: list[str]
) -> list[QuarantinedFile]:
    moved: list[QuarantinedFile] = []
    try:
        for storage_path in storage_paths:
            try:
                source = resolve_stored_document_path(root, storage_path)
            except DocumentParseError as error:
                if str(error) == "stored document file is missing":
                    continue
                raise
            destination = _quarantine_destination(
                ensure_private_directory(root), source.name
            )
            os.replace(source, destination)
            moved.append(QuarantinedFile(source=source, quarantine=destination))
    except (DocumentParseError, OSError) as error:
        try:
            restore_quarantined_files(moved)
        except StoredFileDeleteError as restore_error:
            raise StoredFileDeleteError(
                "document deletion quarantine failed and already-moved files could not be restored"
            ) from restore_error
        raise StoredFileDeleteError(
            "document sources could not be moved to deletion quarantine"
        ) from error
    return moved


def restore_quarantined_files(files: list[QuarantinedFile]) -> None:
    failures: list[OSError] = []
    for item in reversed(files):
        try:
            ensure_private_directory(item.source.parent)
            os.replace(item.quarantine, item.source)
        except OSError as error:
            failures.append(error)
    if failures:
        raise StoredFileDeleteError(
            "quarantined document sources could not be restored"
        ) from failures[0]


def remove_quarantined_files(files: list[QuarantinedFile]) -> None:
    failures: list[OSError] = []
    for item in files:
        try:
            item.quarantine.unlink()
        except OSError as error:
            failures.append(error)
    if failures:
        raise StoredFileDeleteError(
            "document record was deleted but quarantined source cleanup failed"
        ) from failures[0]


def _quarantine_destination(root: Path, original_name: str) -> Path:
    quarantine = ensure_private_directory(root / ".quarantine")
    return quarantine / f"{uuid.uuid4().hex}-{original_name}"


def _recover_delete_quarantine(root: Path, references: list[dict]) -> dict[str, int]:
    """Resolve crash leftovers without deleting a still-referenced source."""

    quarantine = root / ".quarantine"
    if not quarantine.exists():
        return {"restored": 0, "removed": 0}
    if quarantine.is_symlink() or not quarantine.is_dir():
        raise RuntimeError("document deletion quarantine must be a private directory")
    references_by_name = {
        Path(str(reference["storage_path"])).name: reference for reference in references
    }
    restored = 0
    removed = 0
    for candidate in quarantine.iterdir():
        if candidate.is_symlink() or not candidate.is_file():
            continue
        match = re.fullmatch(r"[a-f0-9]{32}-(.+)", candidate.name)
        if match is None:
            continue
        original_name = match.group(1)
        reference = references_by_name.get(original_name)
        if reference is None:
            candidate.unlink()
            removed += 1
            logger.info(
                "document_delete_quarantine_maintained",
                extra={"action": "remove_unreferenced", "result": "removed"},
            )
            continue
        expected_hash = str(reference["content_hash"])
        if _file_sha256(candidate) != expected_hash:
            logger.warning(
                "document_delete_quarantine_maintained",
                extra={
                    "action": "verify_referenced_source",
                    "result": "hash_mismatch_retained",
                    "hash_prefix": expected_hash[:12],
                },
            )
            continue
        extension = Path(original_name).suffix
        destination, relative = storage_destination(
            root, str(reference["content_hash"]), extension
        )
        if relative != str(reference["storage_path"]):
            logger.warning(
                "document_delete_quarantine_maintained",
                extra={
                    "action": "verify_reference_path",
                    "result": "noncanonical_retained",
                    "hash_prefix": expected_hash[:12],
                },
            )
            continue
        if destination.exists():
            candidate.unlink()
            removed += 1
            result = "duplicate_removed"
        else:
            os.replace(candidate, destination)
            restored += 1
            result = "restored"
        logger.info(
            "document_delete_quarantine_maintained",
            extra={
                "action": "recover_referenced_source",
                "result": result,
                "hash_prefix": expected_hash[:12],
            },
        )
    return {"restored": restored, "removed": removed}


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _stored_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = [
            name
            for name in directory_names
            if not name.startswith(".") and not (Path(directory) / name).is_symlink()
        ]
        for file_name in file_names:
            candidate = Path(directory) / file_name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            files.append(candidate)
    return files
