from __future__ import annotations

import hashlib
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
from typing import BinaryIO

import pypdf
from pypdf import PdfReader

PDF_PARSER_PREFIX = f"pypdf/{pypdf.__version__}"
TEXT_PARSER_PREFIX = "keen-text/1"
CHUNKER_VERSION = "keen-chunker/1"
MAX_CHUNK_CHARACTERS = 1_200
CHUNK_OVERLAP_CHARACTERS = 160
READ_BLOCK_BYTES = 64 * 1024
MAX_PDF_PAGES = 2_000
MAX_EXTRACTED_CHARACTERS = 12 * 1024 * 1024
MAX_DOCUMENT_CHUNKS = 12_000
PDF_PARSE_WALL_TIMEOUT_SECONDS = 6.0
PDF_PARSE_CPU_SECONDS = 5
PDF_PARSE_MEMORY_BYTES = 384 * 1024 * 1024
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


@dataclass(frozen=True, slots=True)
class ParsedUnit:
    page_number: int
    section_path: tuple[str, ...]
    text: str


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


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    page_count: int
    parser_version: str
    chunks: tuple[ParsedChunk, ...]


def validate_upload_metadata(filename: str | None, content_type: str | None) -> tuple[str, str]:
    if not filename:
        raise DocumentValidationError("a filename with a supported extension is required")
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
    if media_type not in allowed_types:
        raise DocumentValidationError(
            f"declared media type {media_type or '<missing>'} does not match {extension}"
        )
    return display_name, extension


def copy_and_hash(source: BinaryIO, destination: Path, max_bytes: int) -> tuple[int, str]:
    ensure_private_directory(destination.parent)
    digest = hashlib.sha256()
    size = 0
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        while block := source.read(READ_BLOCK_BYTES):
            size += len(block)
            if size > max_bytes:
                raise DocumentTooLargeError(f"document exceeds the {max_bytes}-byte limit")
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
        raise DocumentValidationError("PDF content must use a .pdf extension and application/pdf")
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


def storage_destination(root: Path, content_hash: str, extension: str) -> tuple[Path, str]:
    resolved_root = ensure_private_directory(root)
    relative = Path(content_hash[:2]) / f"{content_hash}{extension}"
    destination = (resolved_root / relative).resolve()
    if resolved_root != destination and resolved_root not in destination.parents:
        raise RuntimeError("generated document path escaped the configured data directory")
    ensure_private_directory(destination.parent)
    return destination, relative.as_posix()


def incoming_destination(root: Path, upload_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", upload_id):
        raise RuntimeError("generated upload identifier is invalid")
    resolved_root = ensure_private_directory(root)
    incoming_directory = resolved_root / ".incoming"
    resolved_incoming = ensure_private_directory(incoming_directory)
    if resolved_root != resolved_incoming and resolved_root not in resolved_incoming.parents:
        raise RuntimeError("temporary document path escaped the configured data directory")
    return resolved_incoming / f"{upload_id}.upload"


def clear_incoming_uploads(root: Path) -> int:
    resolved_root = ensure_private_directory(root)
    incoming_directory = resolved_root / ".incoming"
    if not incoming_directory.exists():
        return 0
    resolved_incoming = incoming_directory.resolve()
    if resolved_root != resolved_incoming and resolved_root not in resolved_incoming.parents:
        raise RuntimeError("temporary document path escaped the configured data directory")
    removed = 0
    for candidate in resolved_incoming.iterdir():
        if candidate.is_file() and candidate.name.endswith(".upload"):
            candidate.unlink()
            removed += 1
    return removed


def parse_document(path: Path, extension: str) -> ParsedDocument:
    if extension == ".pdf":
        return _parse_pdf_isolated(path)
    elif extension == ".md":
        units = _parse_markdown(path.read_text(encoding="utf-8-sig"))
        page_count = 1
    else:
        text = _normalize_text(path.read_text(encoding="utf-8-sig"))
        units = [ParsedUnit(page_number=1, section_path=(), text=text)] if text else []
        page_count = 1
    parser_version = parser_version_for(extension)

    _validate_extracted_text_size(units)
    chunks = _chunk_units(units)
    if not chunks:
        raise DocumentParseError("document contains no extractable text")
    return ParsedDocument(
        page_count=page_count,
        parser_version=parser_version,
        chunks=tuple(chunks),
    )


def _parse_pdf_isolated(path: Path) -> ParsedDocument:
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=True)
    process = context.Process(
        target=_pdf_parse_worker,
        args=(str(path), child_connection),
        name="keen-pdf-parser",
        daemon=True,
    )
    process.start()
    child_connection.close()
    deadline = time.monotonic() + PDF_PARSE_WALL_TIMEOUT_SECONDS
    next_memory_poll = time.monotonic()
    payload: tuple[str, object] | None = None
    resource_budget_reason: str | None = None
    memory_monitor_failures = 0
    worker_tree: tuple[int, ...] = (process.pid,)
    worker_process_group: int | None = None
    try:
        while time.monotonic() < deadline:
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
                    continue
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
                    if resident_bytes > PDF_PARSE_MEMORY_BYTES:
                        resource_budget_reason = "worker resident-memory limit exceeded"
                        break
                next_memory_poll = now + PDF_MEMORY_POLL_SECONDS
    except EOFError:
        payload = None
    finally:
        parent_connection.close()
        _terminate_pdf_worker_tree(process, worker_tree, worker_process_group)

    if resource_budget_reason is not None:
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


def _pdf_parse_worker(path: str, connection: Connection) -> None:
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
        _arm_pdf_worker_wall_timer()
        wall_timer_armed = True
        _apply_pdf_worker_limits()
        units, page_count = _parse_pdf(Path(path))
        _validate_extracted_text_size(units)
        chunks = _chunk_units(units)
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


def _arm_pdf_worker_wall_timer() -> None:
    signal.signal(signal.SIGALRM, _pdf_worker_wall_timeout)
    signal.setitimer(signal.ITIMER_REAL, PDF_PARSE_WALL_TIMEOUT_SECONDS)


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
        and all(isinstance(value, int) and not isinstance(value, bool) for value in identity)
    ):
        return False
    process_id, process_group = identity
    if process_id <= 1 or process_id != process_group or process_group == os.getpgrp():
        return False
    try:
        return os.getpgid(process_id) == process_group
    except (ProcessLookupError, PermissionError):
        return False


def _apply_pdf_worker_limits() -> None:
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (PDF_PARSE_CPU_SECONDS, PDF_PARSE_CPU_SECONDS),
    )
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
                (PDF_PARSE_MEMORY_BYTES, PDF_PARSE_MEMORY_BYTES),
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
            pid, pgid, process_resident_kibibytes = (
                int(value) for value in parts[:3]
            )
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
        safe_process_group
    ):
        raise DocumentParseError("PDF worker process group did not terminate")


def _wait_for_process_group_exit(process_group: int) -> bool:
    deadline = time.monotonic() + PDF_WORKER_GROUP_EXIT_TIMEOUT_SECONDS
    while True:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            if sys.platform == "darwin":
                live_members = _darwin_process_group_has_live_members(process_group)
                if live_members is False:
                    return True
            return False
        if time.monotonic() >= deadline:
            if sys.platform == "darwin":
                live_members = _darwin_process_group_has_live_members(process_group)
                return live_members is False
            return False
        time.sleep(0.01)


def _parse_pdf(path: Path) -> tuple[list[ParsedUnit], int]:
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise DocumentParseError("password-protected PDFs are not supported")
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise DocumentParseError(f"PDF exceeds the {MAX_PDF_PAGES}-page parsing limit")
        units: list[ParsedUnit] = []
        current_section: tuple[str, ...] = ()
        for page_number, page in enumerate(reader.pages, start=1):
            text = _normalize_text(page.extract_text() or "")
            if not text:
                continue
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
        return units, page_count
    except DocumentParseError:
        raise
    except Exception as error:
        raise DocumentParseError("PDF parsing failed") from error


def _parse_markdown(text: str) -> list[ParsedUnit]:
    units: list[ParsedUnit] = []
    headings: list[str] = []
    buffer: list[str] = []
    active_path: tuple[str, ...] = ()

    def flush() -> None:
        content = _normalize_text("\n".join(buffer))
        if content:
            units.append(ParsedUnit(page_number=1, section_path=active_path, text=content))
        buffer.clear()

    for line in text.splitlines():
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


def _validate_extracted_text_size(units: list[ParsedUnit]) -> None:
    extracted_characters = sum(len(unit.text) for unit in units)
    if extracted_characters > MAX_EXTRACTED_CHARACTERS:
        raise DocumentParseError(
            f"document exceeds the {MAX_EXTRACTED_CHARACTERS}-character extraction limit"
        )


def _chunk_units(units: list[ParsedUnit]) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for unit_ordinal, unit in enumerate(units):
        text = unit.text.strip()
        start = 0
        while start < len(text):
            end = min(start + MAX_CHUNK_CHARACTERS, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", start + 1, end), text.rfind(" ", start + 1, end))
                if boundary > start + MAX_CHUNK_CHARACTERS // 2:
                    end = boundary
            raw_content = text[start:end]
            leading_characters = len(raw_content) - len(raw_content.lstrip())
            trailing_characters = len(raw_content) - len(raw_content.rstrip())
            content_start = start + leading_characters
            content_end = end - trailing_characters
            content = raw_content.strip()
            if content:
                if len(chunks) >= MAX_DOCUMENT_CHUNKS:
                    raise DocumentParseError(
                        f"document exceeds the {MAX_DOCUMENT_CHUNKS}-chunk indexing limit"
                    )
                chunks.append(
                    ParsedChunk(
                        ordinal=len(chunks),
                        page_number=unit.page_number,
                        section_path=unit.section_path,
                        content=content,
                        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        unit_ordinal=unit_ordinal,
                        start_character=content_start,
                        end_character=content_end,
                    )
                )
            if end >= len(text):
                break
            next_start = max(end - CHUNK_OVERLAP_CHARACTERS, start + 1)
            while next_start < end and not text[next_start].isspace():
                next_start += 1
            start = next_start
    return chunks
