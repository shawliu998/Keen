from __future__ import annotations

from io import StringIO
import socket

import pytest

from app.__main__ import (
    SESSION_TOKEN_ENVIRONMENT_KEY,
    bind_loopback_listener,
    parse_args,
    resolve_session_token,
)


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

    assert resolve_session_token(
        arguments.token,
        environment={SESSION_TOKEN_ENVIRONMENT_KEY: "environment-token-that-is-long-enough"},
    ) == TOKEN


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
    assert resolve_session_token(
        arguments.token,
        read_from_stdin=arguments.token_stdin,
        environment={},
        input_stream=StringIO(f"{TOKEN}\n"),
    ) == TOKEN


def test_environment_token_remains_supported_for_manual_launches() -> None:
    assert resolve_session_token(
        None,
        environment={SESSION_TOKEN_ENVIRONMENT_KEY: TOKEN},
    ) == TOKEN


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
