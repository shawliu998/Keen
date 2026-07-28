from __future__ import annotations

import hashlib
import math
import multiprocessing
import os
import re
import resource
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path, PurePosixPath
from collections.abc import Callable
from typing import BinaryIO

import pypdf
import pdfminer
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTTextContainer, LTTextLine
from pypdf import PageObject, PdfReader

PDF_PARSER_PREFIX = f"pypdf/{pypdf.__version__};pdfminer.six/{pdfminer.__version__}"
TEXT_PARSER_PREFIX = "keen-text/1"
CHUNKER_VERSION = "keen-chunker/1"
MAX_CHUNK_CHARACTERS = 1_200
CHUNK_OVERLAP_CHARACTERS = 160
READ_BLOCK_BYTES = 64 * 1024
MAX_PDF_PAGES = 2_000
MAX_EXTRACTED_CHARACTERS = 12 * 1024 * 1024
MAX_DOCUMENT_CHUNKS = 12_000
PDF_PARSE_WALL_TIMEOUT_SECONDS = 180.0
PDF_NO_PROGRESS_TIMEOUT_SECONDS = 15.0
PDF_PARSE_MEMORY_BYTES = 512 * 1024 * 1024
PDF_MEMORY_POLL_SECONDS = 0.2
PDF_WORKER_START_TIMEOUT_SECONDS = 2.0
PDF_WORKER_GROUP_EXIT_TIMEOUT_SECONDS = 3.0

ALLOWED_MEDIA_TYPES: dict[str, frozenset[str]] = {
    ".pdf": frozenset({"application/pdf"}),
    ".md": frozenset({"text/markdown", "text/plain"}),
    ".txt": frozenset({"text/plain"}),
}


def ensure_private_directory(path: Path) -> Path:
    """Create a directory without following a final symlink and enforce owner-only access."""

    path = path.expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError(
            "learning-core data path escaped its configured directory or is not a directory"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError("learning-core data path must be a directory")
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
    return path.resolve()


class DocumentValidationError(ValueError):
    pass


class DocumentTooLargeError(DocumentValidationError):
    pass


class DocumentParseError(ValueError):
    pass


class DocumentProcessingCancelled(DocumentParseError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentLimits:
    max_pdf_pages: int = MAX_PDF_PAGES
    max_extracted_characters: int = MAX_EXTRACTED_CHARACTERS
    max_document_chunks: int = MAX_DOCUMENT_CHUNKS
    pdf_max_rss_bytes: int = PDF_PARSE_MEMORY_BYTES
    pdf_no_progress_timeout_seconds: float = PDF_NO_PROGRESS_TIMEOUT_SECONDS
    pdf_total_timeout_seconds: float = PDF_PARSE_WALL_TIMEOUT_SECONDS


ProgressCallback = Callable[[str, int, int], None]
CancellationCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ParsedUnit:
    page_number: int
    section_path: tuple[str, ...]
    text: str
    geometry: tuple[ParsedTextSpan, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedTextSpan:
    page_number: int
    original_text: str
    normalized_text: str
    block_id: str
    span_id: str
    bbox_x0: float
    bbox_y0: float
    bbox_x1: float
    bbox_y1: float
    page_width: float
    page_height: float
    start_character: int
    end_character: int


@dataclass(frozen=True, slots=True)
class ParsedChunk:
    ordinal: int
    page_number: int
    section_path: tuple[str, ...]
    content: str
    content_hash: str
    unit_ordinal: int
    start_character: int
    end_character: int
    geometry: tuple[ParsedTextSpan, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    page_count: int
    parser_version: str
    chunks: tuple[ParsedChunk, ...]


def validate_upload_metadata(
    filename: str | None, content_type: str | None
) -> tuple[str, str]:
    if not filename:
        raise DocumentValidationError(
            "a filename with a supported extension is required"
        )
    normalized = filename.replace("\\", "/")
    display_name = PurePosixPath(normalized).name.strip()
    if not display_name or display_name in {".", ".."}:
        raise DocumentValidationError("a valid filename is required")
    if len(display_name) > 240:
        raise DocumentValidationError("filename exceeds 240 characters")
    extension = Path(display_name).suffix.lower()
    allowed_types = ALLOWED_MEDIA_TYPES.get(extension)
    if allowed_types is None:
        raise DocumentValidationError("only .pdf, .md, and .txt files are supported")
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in allowed_types and media_type not in {
        "",
        "application/octet-stream",
    }:
        raise DocumentValidationError(
            f"declared media type {media_type or '<missing>'} does not match {extension}"
        )
    return display_name, extension


def canonical_media_type(extension: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }[extension]


def copy_and_hash(
    source: BinaryIO, destination: Path, max_bytes: int
) -> tuple[int, str]:
    ensure_private_directory(destination.parent)
    digest = hashlib.sha256()
    size = 0
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        while block := source.read(READ_BLOCK_BYTES):
            size += len(block)
            if size > max_bytes:
                raise DocumentTooLargeError(
                    f"document exceeds the {max_bytes}-byte limit"
                )
            digest.update(block)
            output.write(block)
    if size == 0:
        raise DocumentValidationError("empty documents are not supported")
    return size, digest.hexdigest()


def validate_file_content(path: Path, extension: str) -> None:
    with path.open("rb") as source:
        prefix = source.read(8)
    if extension == ".pdf":
        if not prefix.startswith(b"%PDF-"):
            raise DocumentValidationError("file content is not a PDF")
        return
    if prefix.startswith(b"%PDF-"):
        raise DocumentValidationError(
            "PDF content must use a .pdf extension and application/pdf"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentValidationError("text documents must be valid UTF-8") from error
    if "\x00" in text:
        raise DocumentValidationError("text documents must not contain NUL bytes")


def parser_version_for(extension: str) -> str:
    if extension == ".pdf":
        return f"{PDF_PARSER_PREFIX};{CHUNKER_VERSION}"
    flavor = "markdown" if extension == ".md" else "plain"
    return f"{TEXT_PARSER_PREFIX};{flavor};{CHUNKER_VERSION}"


def storage_destination(
    root: Path, content_hash: str, extension: str
) -> tuple[Path, str]:
    resolved_root = ensure_private_directory(root)
    relative = Path(content_hash[:2]) / f"{content_hash}{extension}"
    destination = (resolved_root / relative).resolve()
    if resolved_root != destination and resolved_root not in destination.parents:
        raise RuntimeError(
            "generated document path escaped the configured data directory"
        )
    ensure_private_directory(destination.parent)
    return destination, relative.as_posix()


def resolve_stored_document_path(root: Path, storage_path: str) -> Path:
    relative = PurePosixPath(storage_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise DocumentParseError("stored document path is invalid")
    resolved_root = ensure_private_directory(root)
    candidate = resolved_root.joinpath(*relative.parts)
    if candidate.is_symlink():
        raise DocumentParseError("stored document path is not a regular file")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise DocumentParseError("stored document file is missing") from error
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise DocumentParseError(
            "stored document path escaped its configured directory"
        )
    metadata = resolved.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise DocumentParseError("stored document path is not a regular file")
    os.chmod(resolved, 0o600)
    return resolved


def incoming_destination(root: Path, upload_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", upload_id):
        raise RuntimeError("generated upload identifier is invalid")
    resolved_root = ensure_private_directory(root)
    incoming_directory = resolved_root / ".incoming"
    resolved_incoming = ensure_private_directory(incoming_directory)
    if (
        resolved_root != resolved_incoming
        and resolved_root not in resolved_incoming.parents
    ):
        raise RuntimeError(
            "temporary document path escaped the configured data directory"
        )
    return resolved_incoming / f"{upload_id}.upload"


def clear_incoming_uploads(root: Path) -> int:
    resolved_root = ensure_private_directory(root)
    incoming_directory = resolved_root / ".incoming"
    if not incoming_directory.exists():
        return 0
    resolved_incoming = incoming_directory.resolve()
    if (
        resolved_root != resolved_incoming
        and resolved_root not in resolved_incoming.parents
    ):
        raise RuntimeError(
            "temporary document path escaped the configured data directory"
        )
    removed = 0
    for candidate in resolved_incoming.iterdir():
        if candidate.is_file() and candidate.name.endswith(".upload"):
            candidate.unlink()
            removed += 1
    return removed


def parse_document(
    path: Path,
    extension: str,
    *,
    limits: DocumentLimits | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_check: CancellationCheck | None = None,
) -> ParsedDocument:
    limits = limits or DocumentLimits()
    _raise_if_cancelled(cancellation_check)
    if extension == ".pdf":
        return _parse_pdf_isolated(
            path,
            limits=limits,
            progress_callback=progress_callback,
            cancellation_check=cancellation_check,
        )
    elif extension == ".md":
        units = _parse_markdown(
            path.read_text(encoding="utf-8-sig"),
            cancellation_check=cancellation_check,
        )
        page_count = 1
    else:
        text = _normalize_text(path.read_text(encoding="utf-8-sig"))
        units = [ParsedUnit(page_number=1, section_path=(), text=text)] if text else []
        page_count = 1
    parser_version = parser_version_for(extension)

    _notify_progress(progress_callback, "parsing", 1, 1)
    _validate_extracted_text_size(units, limits.max_extracted_characters)
    chunks = _chunk_units(
        units,
        max_chunks=limits.max_document_chunks,
        progress_callback=progress_callback,
        cancellation_check=cancellation_check,
    )
    if not chunks:
        raise DocumentParseError("document contains no extractable text")
    return ParsedDocument(
        page_count=page_count,
        parser_version=parser_version,
        chunks=tuple(chunks),
    )


def _parse_pdf_isolated(
    path: Path,
    *,
    limits: DocumentLimits,
    progress_callback: ProgressCallback | None,
    cancellation_check: CancellationCheck | None,
) -> ParsedDocument:
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=True)
    process = context.Process(
        target=_pdf_parse_worker,
        args=(str(path), child_connection, limits),
        name="keen-pdf-parser",
        daemon=True,
    )
    process.start()
    child_connection.close()
    started_at = time.monotonic()
    deadline = started_at + limits.pdf_total_timeout_seconds
    last_progress_at = started_at
    next_memory_poll = started_at
    payload: tuple[str, object] | None = None
    resource_budget_reason: str | None = None
    memory_monitor_failures = 0
    worker_tree: tuple[int, ...] = (process.pid,)
    worker_process_group: int | None = None
    try:
        while time.monotonic() < deadline:
            _raise_if_cancelled(cancellation_check)
            if parent_connection.poll(0.05):
                message = parent_connection.recv()
                if (
                    isinstance(message, tuple)
                    and len(message) == 2
                    and message[0] == "ready"
                ):
                    identity = message[1]
                    if not _validate_pdf_worker_process_group(identity):
                        resource_budget_reason = "worker process-group isolation failed"
                        break
                    worker_pid, worker_process_group = identity
                    worker_tree = (process.pid, worker_pid)
                    parent_connection.send("start")
                    last_progress_at = time.monotonic()
                    continue
                if (
                    isinstance(message, tuple)
                    and len(message) == 2
                    and message[0] == "progress"
                ):
                    progress = message[1]
                    if (
                        isinstance(progress, tuple)
                        and len(progress) == 3
                        and isinstance(progress[0], str)
                        and isinstance(progress[1], int)
                        and isinstance(progress[2], int)
                    ):
                        _notify_progress(
                            progress_callback,
                            progress[0],
                            progress[1],
                            progress[2],
                        )
                        last_progress_at = time.monotonic()
                        continue
                    resource_budget_reason = "worker emitted invalid progress"
                    break
                payload = message
                break
            if not process.is_alive():
                break
            now = time.monotonic()
            if (
                sys.platform == "darwin"
                and worker_process_group is not None
                and now >= next_memory_poll
            ):
                snapshot = _darwin_process_group_snapshot(worker_process_group)
                if snapshot is None:
                    memory_monitor_failures += 1
                    if memory_monitor_failures >= 5:
                        resource_budget_reason = "worker memory monitor unavailable"
                        break
                else:
                    memory_monitor_failures = 0
                    worker_tree, resident_bytes = snapshot
                    if resident_bytes > limits.pdf_max_rss_bytes:
                        resource_budget_reason = "worker resident-memory limit exceeded"
                        break
                next_memory_poll = now + PDF_MEMORY_POLL_SECONDS
            if now - last_progress_at >= limits.pdf_no_progress_timeout_seconds:
                resource_budget_reason = (
                    "worker made no progress before the configured timeout"
                )
                break
    except DocumentProcessingCancelled:
        resource_budget_reason = "indexing was cancelled"
    except EOFError:
        payload = None
    finally:
        parent_connection.close()
        _terminate_pdf_worker_tree(process, worker_tree, worker_process_group)

    if resource_budget_reason is not None:
        if resource_budget_reason == "indexing was cancelled":
            raise DocumentProcessingCancelled(resource_budget_reason)
        raise DocumentParseError(
            f"PDF parsing exceeded the bounded resource budget: {resource_budget_reason}"
        )
    if payload is None:
        raise DocumentParseError("PDF parsing exceeded the bounded resource budget")
    kind, value = payload
    if kind == "ok" and isinstance(value, ParsedDocument):
        return value
    if kind == "error" and isinstance(value, str):
        raise DocumentParseError(value)
    raise DocumentParseError("PDF parsing failed in the isolated worker")


def _pdf_parse_worker(
    path: str, connection: Connection, limits: DocumentLimits | None = None
) -> None:
    limits = limits or DocumentLimits()
    wall_timer_armed = False
    try:
        worker_identity = _isolate_pdf_worker_process_group()
        _start_pdf_worker_parent_watch()
        connection.send(("ready", worker_identity))
        if (
            not connection.poll(PDF_WORKER_START_TIMEOUT_SECONDS)
            or connection.recv() != "start"
        ):
            return
        _arm_pdf_worker_wall_timer(limits.pdf_total_timeout_seconds)
        wall_timer_armed = True
        _apply_pdf_worker_limits(limits.pdf_max_rss_bytes)
        units, page_count = _parse_pdf(Path(path), limits, connection)
        _validate_extracted_text_size(units, limits.max_extracted_characters)
        chunks = _chunk_units(
            units,
            max_chunks=limits.max_document_chunks,
            progress_callback=lambda stage, completed, total: connection.send(
                ("progress", (stage, completed, total))
            ),
        )
        if not chunks:
            raise DocumentParseError("document contains no extractable text")
        connection.send(
            (
                "ok",
                ParsedDocument(
                    page_count=page_count,
                    parser_version=parser_version_for(".pdf"),
                    chunks=tuple(chunks),
                ),
            )
        )
    except DocumentParseError as error:
        connection.send(("error", str(error)))
    except (MemoryError, OSError):
        connection.send(("error", "PDF parsing exceeded the bounded resource budget"))
    except Exception:
        connection.send(("error", "PDF parsing failed"))
    finally:
        if wall_timer_armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
        connection.close()


def _isolate_pdf_worker_process_group() -> tuple[int, int]:
    try:
        os.setpgid(0, 0)
    except OSError as error:
        raise DocumentParseError("PDF worker process-group isolation failed") from error
    process_id = os.getpid()
    process_group = os.getpgrp()
    if process_id <= 1 or process_id != process_group:
        raise DocumentParseError("PDF worker process-group isolation failed")
    return process_id, process_group


def _start_pdf_worker_parent_watch() -> None:
    parent = multiprocessing.parent_process()
    if parent is None:
        raise DocumentParseError("PDF worker parent monitor is unavailable")
    threading.Thread(
        target=_watch_pdf_worker_parent,
        args=(parent,),
        name="keen-pdf-parent-watch",
        daemon=True,
    ).start()


def _watch_pdf_worker_parent(parent: multiprocessing.process.BaseProcess) -> None:
    parent.join()
    _kill_current_pdf_worker_group()


def _arm_pdf_worker_wall_timer(
    timeout_seconds: float = PDF_PARSE_WALL_TIMEOUT_SECONDS,
) -> None:
    signal.signal(signal.SIGALRM, _pdf_worker_wall_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)


def _pdf_worker_wall_timeout(_signum: int, _frame: object) -> None:
    _kill_current_pdf_worker_group()


def _kill_current_pdf_worker_group() -> None:
    process_group = os.getpgrp()
    if process_group > 1 and process_group == os.getpid():
        try:
            os.killpg(process_group, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    os._exit(1)


def _validate_pdf_worker_process_group(identity: object) -> bool:
    if not (
        isinstance(identity, tuple)
        and len(identity) == 2
        and all(
            isinstance(value, int) and not isinstance(value, bool) for value in identity
        )
    ):
        return False
    process_id, process_group = identity
    if process_id <= 1 or process_id != process_group or process_group == os.getpgrp():
        return False
    try:
        return os.getpgid(process_id) == process_group
    except (ProcessLookupError, PermissionError):
        return False


def _apply_pdf_worker_limits(max_rss_bytes: int = PDF_PARSE_MEMORY_BYTES) -> None:
    # A frozen macOS process reserves nearly a GiB of sparse malloc regions and maps the shared
    # cache into a huge virtual address range even while its RSS is small. Address/data rlimits
    # therefore reject harmless allocations. The parent enforces the same budget against the
    # worker tree's live RSS on macOS; other Unix platforms use kernel address/data ceilings.
    memory_limits = () if sys.platform == "darwin" else ("RLIMIT_AS", "RLIMIT_DATA")
    for limit_name in memory_limits:
        limit = getattr(resource, limit_name, None)
        if limit is None:
            continue
        try:
            resource.setrlimit(
                limit,
                (max_rss_bytes, max_rss_bytes),
            )
        except (OSError, ValueError):
            continue


def _darwin_process_group_snapshot(
    process_group: int,
) -> tuple[tuple[int, ...], int] | None:
    records = _darwin_process_group_records(process_group)
    if not records:
        return None
    process_ids = tuple(record[0] for record in records)
    resident_bytes = sum(record[1] for record in records) * 1024
    return process_ids, resident_bytes


def _darwin_process_group_records(
    process_group: int,
) -> tuple[tuple[int, int, str], ...] | None:
    if process_group <= 1 or process_group == os.getpgrp():
        return None
    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,pgid=,rss=,stat="],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=PDF_MEMORY_POLL_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    records: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            pid, pgid, process_resident_kibibytes = (int(value) for value in parts[:3])
        except ValueError:
            continue
        if pgid == process_group:
            records.append((pid, process_resident_kibibytes, parts[3]))
    return tuple(records)


def _darwin_process_group_has_live_members(process_group: int) -> bool | None:
    records = _darwin_process_group_records(process_group)
    if records is None:
        return None
    return any(not state.upper().startswith("Z") for _pid, _rss, state in records)


def _terminate_pdf_worker_tree(
    process: multiprocessing.Process,
    known_process_ids: tuple[int, ...],
    worker_process_group: int | None,
) -> None:
    process_ids = known_process_ids
    safe_process_group = (
        worker_process_group
        if worker_process_group is not None
        and worker_process_group > 1
        and worker_process_group != os.getpgrp()
        else None
    )
    if sys.platform == "darwin" and safe_process_group is not None:
        snapshot = _darwin_process_group_snapshot(safe_process_group)
        if snapshot is not None:
            process_ids = snapshot[0]
    if safe_process_group is not None:
        try:
            os.killpg(safe_process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            # Darwin can report EPERM when the only remaining member is an
            # already-dead child awaiting reap. Reap the tracked process below,
            # then use the bounded existence check as the final authority.
            pass
    for pid in reversed(process_ids):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            continue
    if process.is_alive():
        process.kill()
    process.join(timeout=1)
    if process.is_alive():
        raise DocumentParseError("PDF worker root process did not terminate")
    if safe_process_group is not None and not _wait_for_process_group_exit(
        safe_process_group, process_ids
    ):
        raise DocumentParseError("PDF worker process group did not terminate")


def _wait_for_process_group_exit(
    process_group: int, known_process_ids: tuple[int, ...] = ()
) -> bool:
    deadline = time.monotonic() + PDF_WORKER_GROUP_EXIT_TIMEOUT_SECONDS
    while True:
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except PermissionError:
            if sys.platform == "darwin":
                live_members = _darwin_process_group_has_live_members(process_group)
                if live_members is False:
                    return True
        for pid in reversed(known_process_ids):
            try:
                if os.getpgid(pid) == process_group:
                    os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                continue
        if sys.platform == "darwin":
            live_members = _darwin_process_group_has_live_members(process_group)
            if live_members is False:
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


def _parse_pdf(
    path: Path, limits: DocumentLimits, connection: Connection | None = None
) -> tuple[list[ParsedUnit], int]:
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise DocumentParseError("password-protected PDFs are not supported")
        page_count = len(reader.pages)
        if page_count > limits.max_pdf_pages:
            raise DocumentParseError(
                f"PDF exceeds the {limits.max_pdf_pages}-page parsing limit"
            )
        units: list[ParsedUnit] = []
        geometry_eligible_pages: set[int] = set()
        extracted_characters = 0
        current_section: tuple[str, ...] = ()
        for page_number, page in enumerate(reader.pages, start=1):
            text = _normalize_text(page.extract_text() or "")
            extracted_characters += len(text)
            if extracted_characters > limits.max_extracted_characters:
                raise DocumentParseError(
                    "document exceeds the "
                    f"{limits.max_extracted_characters}-character extraction limit"
                )
            if connection is not None:
                connection.send(("progress", ("parsing", page_number, page_count * 2)))
            if not text:
                continue
            if _pdf_page_geometry_supported(page):
                geometry_eligible_pages.add(page_number)
            first_line = text.split("\n", 1)[0].strip()
            if 0 < len(first_line) <= 120 and not first_line.endswith((".", "?", "!")):
                current_section = (first_line,)
            units.append(
                ParsedUnit(
                    page_number=page_number,
                    section_path=current_section,
                    text=text,
                )
            )
        geometry_by_page: dict[int, tuple[_RawPdfSpan, ...]] = {}
        if units and geometry_eligible_pages:
            try:
                geometry_by_page = _extract_pdf_geometry(
                    path,
                    page_count=page_count,
                    eligible_pages=geometry_eligible_pages,
                    connection=connection,
                )
            except (MemoryError, OSError):
                raise
            except Exception:
                # Geometry is an enhancement over the existing bounded pypdf text
                # extraction. Unsupported layout content must not fabricate boxes or
                # destroy an otherwise indexable lexical document.
                geometry_by_page = {}
        units = [
            ParsedUnit(
                page_number=unit.page_number,
                section_path=unit.section_path,
                text=unit.text,
                geometry=_map_pdf_geometry(
                    unit.text,
                    geometry_by_page.get(unit.page_number, ()),
                ),
            )
            for unit in units
        ]
        return units, page_count
    except DocumentParseError:
        raise
    except Exception as error:
        raise DocumentParseError("PDF parsing failed") from error


@dataclass(frozen=True, slots=True)
class _RawPdfSpan:
    page_number: int
    original_text: str
    normalized_text: str
    block_id: str
    span_id: str
    bbox_x0: float
    bbox_y0: float
    bbox_x1: float
    bbox_y1: float
    page_width: float
    page_height: float


def _extract_pdf_geometry(
    path: Path,
    *,
    page_count: int,
    eligible_pages: set[int],
    connection: Connection | None,
) -> dict[int, tuple[_RawPdfSpan, ...]]:
    pages: dict[int, tuple[_RawPdfSpan, ...]] = {}
    for page_number, layout in enumerate(extract_pages(str(path)), start=1):
        if page_number > page_count:
            break
        if page_number not in eligible_pages:
            pages[page_number] = ()
            if connection is not None:
                connection.send(
                    (
                        "progress",
                        ("parsing", page_count + page_number, page_count * 2),
                    )
                )
            continue
        page_width = float(layout.width)
        page_height = float(layout.height)
        if not _valid_page_dimensions(page_width, page_height):
            pages[page_number] = ()
            if connection is not None:
                connection.send(
                    (
                        "progress",
                        ("parsing", page_count + page_number, page_count * 2),
                    )
                )
            continue
        spans: list[_RawPdfSpan] = []
        for block_index, element in enumerate(layout):
            if not isinstance(element, LTTextContainer):
                continue
            lines = (
                (element,)
                if isinstance(element, LTTextLine)
                else tuple(child for child in element if isinstance(child, LTTextLine))
            )
            for line_index, line in enumerate(lines):
                original_text = line.get_text().rstrip("\r\n")
                normalized_text = _normalize_text(original_text)
                if not normalized_text:
                    continue
                bbox = _pdf_line_bbox(line, page_width, page_height)
                if bbox is None:
                    continue
                block_id = f"p{page_number}-b{block_index}"
                spans.append(
                    _RawPdfSpan(
                        page_number=page_number,
                        original_text=original_text,
                        normalized_text=normalized_text,
                        block_id=block_id,
                        span_id=f"{block_id}-s{line_index}",
                        bbox_x0=bbox[0],
                        bbox_y0=bbox[1],
                        bbox_x1=bbox[2],
                        bbox_y1=bbox[3],
                        page_width=page_width,
                        page_height=page_height,
                    )
                )
        pages[page_number] = tuple(spans)
        if connection is not None:
            connection.send(
                ("progress", ("parsing", page_count + page_number, page_count * 2))
            )
    return pages


def _pdf_page_geometry_supported(page: PageObject) -> bool:
    """Permit boxes only when pdfminer/PDF.js coordinate assumptions are stable.

    Rotated pages and CropBoxes that differ from the MediaBox require an explicit
    transform that the first geometry schema does not store. Returning no box is
    safer than drawing a plausible but incorrect highlight.
    """

    try:
        rotation = int(page.rotation or 0) % 360
        media_box = tuple(
            float(value)
            for value in (
                page.mediabox.left,
                page.mediabox.bottom,
                page.mediabox.right,
                page.mediabox.top,
            )
        )
        crop_box = tuple(
            float(value)
            for value in (
                page.cropbox.left,
                page.cropbox.bottom,
                page.cropbox.right,
                page.cropbox.top,
            )
        )
        user_unit = float(page.get("/UserUnit", 1))
    except (AttributeError, TypeError, ValueError):
        return False
    if rotation != 0 or not math.isclose(user_unit, 1.0):
        return False
    if not all(math.isfinite(value) for value in (*media_box, *crop_box)):
        return False
    if any(
        not math.isclose(media, crop, rel_tol=0.0, abs_tol=1e-6)
        for media, crop in zip(media_box, crop_box, strict=True)
    ):
        return False
    # The current stored bbox is relative to a zero-based page. Preserve page-only
    # fallback for unusual boxes with a translated origin.
    return math.isclose(media_box[0], 0.0, abs_tol=1e-6) and math.isclose(
        media_box[1], 0.0, abs_tol=1e-6
    )


def _pdf_line_bbox(
    line: LTTextLine, page_width: float, page_height: float
) -> tuple[float, float, float, float] | None:
    characters = [item for item in line if isinstance(item, LTChar)]
    boxes = [
        tuple(float(value) for value in character.bbox) for character in characters
    ]
    if not boxes:
        boxes = [tuple(float(value) for value in line.bbox)]
    x0 = max(0.0, min(box[0] for box in boxes))
    y0 = max(0.0, min(box[1] for box in boxes))
    x1 = min(page_width, max(box[2] for box in boxes))
    y1 = min(page_height, max(box[3] for box in boxes))
    values = (x0, y0, x1, y1)
    if not all(math.isfinite(value) for value in values):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return values


def _valid_page_dimensions(width: float, height: float) -> bool:
    return (
        math.isfinite(width)
        and math.isfinite(height)
        and 0 < width <= 1_000_000
        and 0 < height <= 1_000_000
    )


def _map_pdf_geometry(
    normalized_page_text: str,
    spans: tuple[_RawPdfSpan, ...],
) -> tuple[ParsedTextSpan, ...]:
    mapped: list[ParsedTextSpan] = []
    cursor = 0
    for span in spans:
        start = normalized_page_text.find(span.normalized_text, cursor)
        if start < 0:
            start = normalized_page_text.find(span.normalized_text)
        if start < 0:
            continue
        end = start + len(span.normalized_text)
        mapped.append(
            ParsedTextSpan(
                page_number=span.page_number,
                original_text=span.original_text,
                normalized_text=span.normalized_text,
                block_id=span.block_id,
                span_id=span.span_id,
                bbox_x0=span.bbox_x0,
                bbox_y0=span.bbox_y0,
                bbox_x1=span.bbox_x1,
                bbox_y1=span.bbox_y1,
                page_width=span.page_width,
                page_height=span.page_height,
                start_character=start,
                end_character=end,
            )
        )
        cursor = end
    return tuple(mapped)


def _parse_markdown(
    text: str, *, cancellation_check: CancellationCheck | None = None
) -> list[ParsedUnit]:
    units: list[ParsedUnit] = []
    headings: list[str] = []
    buffer: list[str] = []
    active_path: tuple[str, ...] = ()

    def flush() -> None:
        content = _normalize_text("\n".join(buffer))
        if content:
            units.append(
                ParsedUnit(page_number=1, section_path=active_path, text=content)
            )
        buffer.clear()

    for line in text.splitlines():
        _raise_if_cancelled(cancellation_check)
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            headings[level - 1 :] = [title]
            active_path = tuple(headings)
            buffer.append(title)
        else:
            buffer.append(line)
    flush()
    return units


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"[\t \f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _validate_extracted_text_size(
    units: list[ParsedUnit], max_extracted_characters: int = MAX_EXTRACTED_CHARACTERS
) -> None:
    extracted_characters = sum(len(unit.text) for unit in units)
    if extracted_characters > max_extracted_characters:
        raise DocumentParseError(
            f"document exceeds the {max_extracted_characters}-character extraction limit"
        )


def _chunk_units(
    units: list[ParsedUnit],
    *,
    max_chunks: int = MAX_DOCUMENT_CHUNKS,
    progress_callback: ProgressCallback | None = None,
    cancellation_check: CancellationCheck | None = None,
) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for unit_ordinal, unit in enumerate(units):
        _raise_if_cancelled(cancellation_check)
        text = unit.text.strip()
        start = 0
        while start < len(text):
            _raise_if_cancelled(cancellation_check)
            end = min(start + MAX_CHUNK_CHARACTERS, len(text))
            if end < len(text):
                boundary = max(
                    text.rfind("\n", start + 1, end), text.rfind(" ", start + 1, end)
                )
                if boundary > start + MAX_CHUNK_CHARACTERS // 2:
                    end = boundary
            raw_content = text[start:end]
            leading_characters = len(raw_content) - len(raw_content.lstrip())
            trailing_characters = len(raw_content) - len(raw_content.rstrip())
            content_start = start + leading_characters
            content_end = end - trailing_characters
            content = raw_content.strip()
            if content:
                if len(chunks) >= max_chunks:
                    raise DocumentParseError(
                        f"document exceeds the {max_chunks}-chunk indexing limit"
                    )
                chunks.append(
                    ParsedChunk(
                        ordinal=len(chunks),
                        page_number=unit.page_number,
                        section_path=unit.section_path,
                        content=content,
                        content_hash=hashlib.sha256(
                            content.encode("utf-8")
                        ).hexdigest(),
                        unit_ordinal=unit_ordinal,
                        start_character=content_start,
                        end_character=content_end,
                        geometry=tuple(
                            span
                            for span in unit.geometry
                            if span.end_character > content_start
                            and span.start_character < content_end
                        ),
                    )
                )
                _notify_progress(
                    progress_callback,
                    "chunking",
                    unit_ordinal + 1,
                    max(1, len(units)),
                )
            if end >= len(text):
                break
            next_start = max(end - CHUNK_OVERLAP_CHARACTERS, start + 1)
            while next_start < end and not text[next_start].isspace():
                next_start += 1
            start = next_start
    return chunks


def _raise_if_cancelled(cancellation_check: CancellationCheck | None) -> None:
    if cancellation_check is not None and cancellation_check():
        raise DocumentProcessingCancelled("indexing was cancelled")


def _notify_progress(
    callback: ProgressCallback | None, stage: str, completed: int, total: int
) -> None:
    if callback is not None:
        callback(stage, completed, max(1, total))
