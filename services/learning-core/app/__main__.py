from __future__ import annotations

import argparse
import os
import socket
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, TextIO

import uvicorn

from .logging import configure_logging
from .main import create_app
from .settings import LocalChatSettings, LocalEmbeddingSettings, Settings


SESSION_TOKEN_ENVIRONMENT_KEY = "KEEN_SESSION_TOKEN"
PORT_ANNOUNCEMENT_PREFIX = "KEEN_SIDECAR_PORT="
PHASE_ANNOUNCEMENT_PREFIX = "KEEN_SIDECAR_PHASE="
READY_ANNOUNCEMENT = "KEEN_SIDECAR_READY=1"
MAX_SESSION_TOKEN_CHARACTERS = 4_096
StartupPhase = Literal["migrating", "recovering", "starting_server"]
VALID_STARTUP_PHASES = frozenset({"migrating", "recovering", "starting_server"})


class SidecarLifecycleEvents:
    """Write the machine-readable sidecar lifecycle protocol to stdout."""

    def __init__(self, output_stream: TextIO | None = None) -> None:
        self._output_stream = sys.stdout if output_stream is None else output_stream

    def announce_port(self, port: int) -> None:
        if not 1 <= port <= 65_535:
            raise ValueError("announced sidecar port must be between 1 and 65535")
        self._write(f"{PORT_ANNOUNCEMENT_PREFIX}{port}")

    def announce_phase(self, phase: StartupPhase) -> None:
        if phase not in VALID_STARTUP_PHASES:
            raise ValueError("unknown sidecar startup phase")
        self._write(f"{PHASE_ANNOUNCEMENT_PREFIX}{phase}")

    def announce_ready(self) -> None:
        self._write(READY_ANNOUNCEMENT)

    def _write(self, event: str) -> None:
        if "\r" in event or "\n" in event:
            raise ValueError("sidecar lifecycle events must be single-line frames")
        print(event, file=self._output_stream, flush=True)


class ReadyAnnouncingServer(uvicorn.Server):
    """Announce readiness only after lifespan and socket startup both succeed."""

    def __init__(self, config: uvicorn.Config, events: SidecarLifecycleEvents) -> None:
        super().__init__(config)
        self._events = events

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started and not self.should_exit:
            self._events.announce_ready()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Keen learning core sidecar")
    token_source = parser.add_mutually_exclusive_group()
    token_source.add_argument(
        "--token",
        help=(
            "ephemeral session Bearer token; when omitted, read "
            f"{SESSION_TOKEN_ENVIRONMENT_KEY}"
        ),
    )
    token_source.add_argument(
        "--token-stdin",
        action="store_true",
        help="read one newline-terminated session token from stdin",
    )
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--documents-directory", type=Path)
    parser.add_argument("--max-document-bytes", type=int, default=25 * 1024 * 1024)
    parser.add_argument("--max-pdf-pages", type=int, default=2_000)
    parser.add_argument(
        "--max-extracted-characters", type=int, default=12 * 1024 * 1024
    )
    parser.add_argument("--max-document-chunks", type=int, default=12_000)
    parser.add_argument("--pdf-max-rss-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--pdf-no-progress-timeout", type=float, default=15.0)
    parser.add_argument("--pdf-total-timeout", type=float, default=180.0)
    parser.add_argument("--embedding-provider", choices=("ollama", "openai-compatible"))
    parser.add_argument("--embedding-base-url")
    parser.add_argument("--embedding-model")
    parser.add_argument("--embedding-version")
    parser.add_argument("--embedding-dimensions", type=int)
    parser.add_argument("--embedding-connect-timeout", type=float, default=5.0)
    parser.add_argument("--embedding-read-timeout", type=float, default=60.0)
    parser.add_argument("--embedding-write-timeout", type=float, default=15.0)
    parser.add_argument("--embedding-pool-timeout", type=float, default=5.0)
    parser.add_argument("--chat-provider", choices=("ollama", "openai-compatible"))
    parser.add_argument("--chat-base-url")
    parser.add_argument("--chat-model")
    parser.add_argument("--chat-version")
    parser.add_argument("--chat-connect-timeout", type=float, default=5.0)
    parser.add_argument("--chat-read-timeout", type=float, default=120.0)
    parser.add_argument("--chat-write-timeout", type=float, default=15.0)
    parser.add_argument("--chat-pool-timeout", type=float, default=5.0)
    parser.add_argument("--chat-total-timeout", type=float, default=180.0)
    parser.add_argument("--seed-demo", action="store_true")
    return parser.parse_args(argv)


def resolve_session_token(
    command_line_token: str | None,
    *,
    read_from_stdin: bool = False,
    environment: Mapping[str, str] | None = None,
    input_stream: TextIO | None = None,
) -> str:
    if read_from_stdin:
        stream = sys.stdin if input_stream is None else input_stream
        line = stream.readline(MAX_SESSION_TOKEN_CHARACTERS + 2)
        if not line.endswith("\n"):
            raise SystemExit("stdin session token must end with a newline")
        token = line[:-1]
        if len(token) > MAX_SESSION_TOKEN_CHARACTERS:
            raise SystemExit("stdin session token is too long")
        if "\r" in token or "\n" in token:
            raise SystemExit("stdin session token must not contain line breaks")
        if not token:
            raise SystemExit("stdin session token is empty")
        return token

    source = os.environ if environment is None else environment
    token = command_line_token or source.get(SESSION_TOKEN_ENVIRONMENT_KEY)
    if not token:
        raise SystemExit(
            "a session token is required via --token or "
            f"{SESSION_TOKEN_ENVIRONMENT_KEY}"
        )
    return token


def bind_loopback_listener(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", port))
        listener.listen(2_048)
    except Exception:
        listener.close()
        raise
    return listener


def resolve_local_embedding_settings(
    args: argparse.Namespace,
) -> LocalEmbeddingSettings | None:
    embedding_values = (
        args.embedding_provider,
        args.embedding_base_url,
        args.embedding_model,
        args.embedding_version,
        args.embedding_dimensions,
    )
    if not any(value is not None for value in embedding_values):
        return None
    if not all(value is not None for value in embedding_values):
        raise SystemExit(
            "embedding provider, base URL, model, version, and dimensions "
            "must be configured together"
        )
    try:
        return LocalEmbeddingSettings(
            provider=args.embedding_provider,
            base_url=args.embedding_base_url,
            model=args.embedding_model,
            version=args.embedding_version,
            dimensions=args.embedding_dimensions,
            connect_timeout_seconds=args.embedding_connect_timeout,
            read_timeout_seconds=args.embedding_read_timeout,
            write_timeout_seconds=args.embedding_write_timeout,
            pool_timeout_seconds=args.embedding_pool_timeout,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error


def resolve_local_chat_settings(args: argparse.Namespace) -> LocalChatSettings | None:
    chat_values = (
        args.chat_provider,
        args.chat_base_url,
        args.chat_model,
        args.chat_version,
    )
    if not any(value is not None for value in chat_values):
        return None
    if not all(value is not None for value in chat_values):
        raise SystemExit(
            "chat provider, base URL, model, and version must be configured together"
        )
    try:
        return LocalChatSettings(
            provider=args.chat_provider,
            base_url=args.chat_base_url,
            model=args.chat_model,
            version=args.chat_version,
            connect_timeout_seconds=args.chat_connect_timeout,
            read_timeout_seconds=args.chat_read_timeout,
            write_timeout_seconds=args.chat_write_timeout,
            pool_timeout_seconds=args.chat_pool_timeout,
            total_timeout_seconds=args.chat_total_timeout,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error


def main() -> None:
    args = parse_args()
    if not 0 <= args.port <= 65535:
        raise SystemExit("--port must be between 0 and 65535")
    configure_logging()
    local_embedding = resolve_local_embedding_settings(args)
    local_chat = resolve_local_chat_settings(args)
    settings = Settings(
        session_token=resolve_session_token(
            args.token,
            read_from_stdin=args.token_stdin,
        ),
        database_path=args.database,
        seed_demo=args.seed_demo,
        document_data_path=args.documents_directory,
        max_document_bytes=args.max_document_bytes,
        max_pdf_pages=args.max_pdf_pages,
        max_extracted_characters=args.max_extracted_characters,
        max_document_chunks=args.max_document_chunks,
        pdf_max_rss_bytes=args.pdf_max_rss_bytes,
        pdf_no_progress_timeout_seconds=args.pdf_no_progress_timeout,
        pdf_total_timeout_seconds=args.pdf_total_timeout,
        local_embedding=local_embedding,
        local_chat=local_chat,
    )
    events = SidecarLifecycleEvents()
    with bind_loopback_listener(args.port) as listener:
        bound_port = int(listener.getsockname()[1])
        events.announce_port(bound_port)
        config = uvicorn.Config(
            create_app(settings, startup_phase_reporter=events.announce_phase),
            host="127.0.0.1",
            port=bound_port,
            log_config=None,
        )
        ReadyAnnouncingServer(config, events).run(sockets=[listener])


if __name__ == "__main__":
    main()
