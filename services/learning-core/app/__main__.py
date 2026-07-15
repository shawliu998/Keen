from __future__ import annotations

import argparse
import os
import socket
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

import uvicorn

from .logging import configure_logging
from .main import create_app
from .settings import Settings


SESSION_TOKEN_ENVIRONMENT_KEY = "KEEN_SESSION_TOKEN"
PORT_ANNOUNCEMENT_PREFIX = "KEEN_SIDECAR_PORT="
MAX_SESSION_TOKEN_CHARACTERS = 4_096


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


def main() -> None:
    args = parse_args()
    if not 0 <= args.port <= 65535:
        raise SystemExit("--port must be between 0 and 65535")
    configure_logging()
    settings = Settings(
        session_token=resolve_session_token(
            args.token,
            read_from_stdin=args.token_stdin,
        ),
        database_path=args.database,
        seed_demo=args.seed_demo,
        document_data_path=args.documents_directory,
        max_document_bytes=args.max_document_bytes,
    )
    with bind_loopback_listener(args.port) as listener:
        bound_port = int(listener.getsockname()[1])
        print(f"{PORT_ANNOUNCEMENT_PREFIX}{bound_port}", flush=True)
        config = uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=bound_port,
            log_config=None,
        )
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
