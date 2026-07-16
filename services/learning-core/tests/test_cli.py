from __future__ import annotations

from io import StringIO
import asyncio
import logging
import socket

import pytest

from app.__main__ import (
    PHASE_ANNOUNCEMENT_PREFIX,
    PORT_ANNOUNCEMENT_PREFIX,
    READY_ANNOUNCEMENT,
    ReadyAnnouncingServer,
    SESSION_TOKEN_ENVIRONMENT_KEY,
    SidecarLifecycleEvents,
    bind_loopback_listener,
    parse_args,
    resolve_session_token,
    resolve_local_chat_settings,
)
from app.logging import configure_logging
from app.settings import Settings


TOKEN = "0123456789abcdef0123456789abcdef"


def test_cli_token_remains_supported_and_takes_precedence() -> None:
    arguments = parse_args(
        [
            "--token",
            TOKEN,
            "--port",
            "43125",
            "--database",
            "/tmp/keen.sqlite3",
        ]
    )

    assert (
        resolve_session_token(
            arguments.token,
            environment={
                SESSION_TOKEN_ENVIRONMENT_KEY: "environment-token-that-is-long-enough"
            },
        )
        == TOKEN
    )


def test_sidecar_can_receive_token_without_exposing_it_in_arguments() -> None:
    arguments = parse_args(
        [
            "--token-stdin",
            "--port",
            "43125",
            "--database",
            "/tmp/keen.sqlite3",
        ]
    )

    assert arguments.token is None
    assert arguments.token_stdin is True
    assert (
        resolve_session_token(
            arguments.token,
            read_from_stdin=arguments.token_stdin,
            environment={},
            input_stream=StringIO(f"{TOKEN}\n"),
        )
        == TOKEN
    )


def test_demo_seed_requires_the_explicit_command_line_flag() -> None:
    base_arguments = [
        "--token-stdin",
        "--port",
        "0",
        "--database",
        "/tmp/keen.sqlite3",
    ]

    assert parse_args(base_arguments).seed_demo is False
    assert parse_args([*base_arguments, "--seed-demo"]).seed_demo is True


def test_local_chat_configuration_is_all_or_none_and_loopback_only() -> None:
    base = [
        "--token-stdin",
        "--port",
        "0",
        "--database",
        "/tmp/keen.sqlite3",
    ]
    assert resolve_local_chat_settings(parse_args(base)) is None

    configured = resolve_local_chat_settings(
        parse_args(
            [
                *base,
                "--chat-provider",
                "ollama",
                "--chat-base-url",
                "http://127.0.0.1:11434",
                "--chat-model",
                "local-chat",
                "--chat-version",
                "sha-local",
            ]
        )
    )
    assert configured is not None
    assert configured.model == "local-chat"

    with pytest.raises(SystemExit, match="must be configured together"):
        resolve_local_chat_settings(parse_args([*base, "--chat-provider", "ollama"]))
    with pytest.raises(SystemExit, match="loopback"):
        resolve_local_chat_settings(
            parse_args(
                [
                    *base,
                    "--chat-provider",
                    "ollama",
                    "--chat-base-url",
                    "http://192.0.2.1:11434",
                    "--chat-model",
                    "local-chat",
                    "--chat-version",
                    "v1",
                ]
            )
        )


def test_document_worker_resource_limits_are_configurable_and_validated() -> None:
    arguments = parse_args(
        [
            "--token-stdin",
            "--port",
            "0",
            "--database",
            "/tmp/keen.sqlite3",
            "--max-pdf-pages",
            "37",
            "--max-extracted-characters",
            "10000",
            "--max-document-chunks",
            "43",
            "--pdf-max-rss-bytes",
            "50000000",
            "--pdf-no-progress-timeout",
            "2.5",
            "--pdf-total-timeout",
            "9.5",
        ]
    )

    assert arguments.max_pdf_pages == 37
    assert arguments.max_extracted_characters == 10_000
    assert arguments.max_document_chunks == 43
    assert arguments.pdf_max_rss_bytes == 50_000_000
    assert arguments.pdf_no_progress_timeout == 2.5
    assert arguments.pdf_total_timeout == 9.5
    with pytest.raises(ValueError, match="must not exceed total timeout"):
        Settings(
            session_token=TOKEN,
            database_path="/tmp/keen.sqlite3",
            pdf_no_progress_timeout_seconds=10,
            pdf_total_timeout_seconds=9,
        )


def test_environment_token_remains_supported_for_manual_launches() -> None:
    assert (
        resolve_session_token(
            None,
            environment={SESSION_TOKEN_ENVIRONMENT_KEY: TOKEN},
        )
        == TOKEN
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (TOKEN, "end with a newline"),
        (f"{TOKEN}\r\n", "must not contain line breaks"),
        ("x" * 4_097 + "\n", "too long"),
        ("\n", "empty"),
    ],
)
def test_stdin_token_protocol_rejects_malformed_frames(
    payload: str, message: str
) -> None:
    with pytest.raises(SystemExit, match=message):
        resolve_session_token(
            None,
            read_from_stdin=True,
            environment={},
            input_stream=StringIO(payload),
        )


def test_missing_session_token_exits_with_a_clear_error() -> None:
    with pytest.raises(SystemExit, match=SESSION_TOKEN_ENVIRONMENT_KEY):
        resolve_session_token(None, environment={})


def test_sidecar_owns_its_random_loopback_port_before_announcing_it() -> None:
    with bind_loopback_listener(0) as listener:
        host, port = listener.getsockname()
        assert host == "127.0.0.1"
        assert 1 <= port <= 65_535
        competing = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError):
                competing.bind(("127.0.0.1", port))
        finally:
            competing.close()


def test_lifecycle_events_are_exact_single_line_protocol_frames() -> None:
    output = StringIO()
    events = SidecarLifecycleEvents(output)

    events.announce_port(43125)
    events.announce_phase("migrating")
    events.announce_phase("recovering")
    events.announce_phase("starting_server")
    events.announce_ready()

    assert output.getvalue().splitlines() == [
        f"{PORT_ANNOUNCEMENT_PREFIX}43125",
        f"{PHASE_ANNOUNCEMENT_PREFIX}migrating",
        f"{PHASE_ANNOUNCEMENT_PREFIX}recovering",
        f"{PHASE_ANNOUNCEMENT_PREFIX}starting_server",
        READY_ANNOUNCEMENT,
    ]


def test_ordinary_logs_cannot_write_lifecycle_events_to_stdout(capsys) -> None:
    configure_logging()

    logging.getLogger("keen.learning_core").warning(READY_ANNOUNCEMENT)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert READY_ANNOUNCEMENT in captured.err


class _StartupResultServer(ReadyAnnouncingServer):
    def __init__(
        self,
        *,
        started: bool,
        should_exit: bool,
        events: SidecarLifecycleEvents,
    ) -> None:
        self.started = started
        self.should_exit = should_exit
        self._events = events

    async def _run_base_startup(self, sockets=None) -> None:
        return None


def test_ready_is_emitted_only_after_successful_server_startup(monkeypatch) -> None:
    output = StringIO()
    events = SidecarLifecycleEvents(output)
    server = _StartupResultServer(started=True, should_exit=False, events=events)
    monkeypatch.setattr(
        "app.__main__.uvicorn.Server.startup",
        server._run_base_startup,
    )

    asyncio.run(server.startup())

    assert output.getvalue() == f"{READY_ANNOUNCEMENT}\n"


@pytest.mark.parametrize(
    ("started", "should_exit"),
    [(False, False), (False, True), (True, True)],
)
def test_ready_is_not_emitted_when_server_startup_did_not_succeed(
    monkeypatch, started: bool, should_exit: bool
) -> None:
    output = StringIO()
    events = SidecarLifecycleEvents(output)
    server = _StartupResultServer(
        started=started,
        should_exit=should_exit,
        events=events,
    )
    monkeypatch.setattr(
        "app.__main__.uvicorn.Server.startup",
        server._run_base_startup,
    )

    asyncio.run(server.startup())

    assert output.getvalue() == ""
