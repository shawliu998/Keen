from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="process-group SIGKILL recovery is Unix-only"
)

_SERVER_HELPER = Path(__file__).parent / "helpers" / "agent_socket_server.py"
_SERVICE_ROOT = Path(__file__).parents[1]
_PROCESS_TIMEOUT_SECONDS = 20.0
_HTTP_TIMEOUT = httpx.Timeout(10.0)


@dataclass(frozen=True)
class _Sidecar:
    process: subprocess.Popen[str]
    port: int


def _read_ready(process: subprocess.Popen[str]) -> int:
    assert process.stdout is not None
    assert process.stderr is not None
    frames: queue.Queue[str | None] = queue.Queue()
    output: list[str] = []
    errors: list[str] = []

    def drain_stdout() -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            output.append(line)
            frames.put(line)
        frames.put(None)

    def drain_stderr() -> None:
        assert process.stderr is not None
        errors.extend(line.rstrip("\n") for line in process.stderr)

    threading.Thread(target=drain_stdout, daemon=True).start()
    threading.Thread(target=drain_stderr, daemon=True).start()
    deadline = time.monotonic() + _PROCESS_TIMEOUT_SECONDS
    port: int | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None and frames.empty():
            break
        try:
            line = frames.get(timeout=min(0.1, deadline - time.monotonic()))
        except queue.Empty:
            continue
        if line is None:
            break
        if line.startswith("KEEN_SIDECAR_PORT="):
            port = int(line.removeprefix("KEEN_SIDECAR_PORT="))
        if line == "KEEN_SIDECAR_READY=1":
            assert port is not None
            return port
    raise AssertionError(
        "socket test sidecar did not become ready; "
        f"exit={process.poll()} stdout={output!r} stderr={errors!r}"
    )


def _kill_process_group(
    process: subprocess.Popen[str], *, require_running: bool = False
) -> None:
    return_code = process.poll()
    if require_running and return_code is not None:
        raise AssertionError(f"sidecar exited before SIGKILL: {return_code}")
    if return_code is None:
        assert os.getpgid(process.pid) == process.pid
        assert os.getpgrp() != process.pid
        os.killpg(process.pid, signal.SIGKILL)
        return_code = process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)
        assert return_code == -signal.SIGKILL
        with pytest.raises(ProcessLookupError):
            os.killpg(process.pid, 0)
    else:
        process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)


@contextmanager
def _running_sidecar(database: Path, token: str) -> Iterator[_Sidecar]:
    environment = os.environ.copy()
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(_SERVICE_ROOT), existing_python_path) if value
    )
    process = subprocess.Popen(
        [sys.executable, str(_SERVER_HELPER), "--database", str(database)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        cwd=_SERVICE_ROOT,
        env=environment,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(f"{token}\n")
        process.stdin.flush()
        process.stdin.close()
        port = _read_ready(process)
        assert os.getpgid(process.pid) == process.pid
        yield _Sidecar(process=process, port=port)
    finally:
        _kill_process_group(process)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _parse_sse_lines(lines: Iterator[str], *, stop_event: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    fields: dict[str, str] = {}
    for line in lines:
        if line:
            name, value = line.split(": ", 1)
            fields[name] = value
            continue
        if fields:
            events.append(fields)
            if fields.get("event") == stop_event:
                return events
            fields = {}
    raise AssertionError(f"SSE stream ended before {stop_event!r}: {events!r}")


def _parse_complete_sse(body: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    fields: dict[str, str] = {}
    for line in body.splitlines():
        if line:
            name, value = line.split(": ", 1)
            fields[name] = value
            continue
        if fields:
            events.append(fields)
            fields = {}
    if fields:
        events.append(fields)
    return events


def _read_partial_event(client: httpx.Client, run_id: str) -> tuple[list[dict], str]:
    with client.stream("GET", f"/v1/agent/runs/{run_id}/events") as response:
        assert response.status_code == 200
        frames = _parse_sse_lines(
            iter(response.iter_lines()), stop_event="content_delta"
        )
    decoded = [{**frame, "data": json.loads(frame["data"])} for frame in frames]
    content = decoded[-1]
    assert content["event"] == "content_delta"
    assert content["data"] == {"delta": "partial-before-process-crash"}
    return decoded, content["id"]


def _read_recovery_events(client: httpx.Client, run_id: str, cursor: str) -> list[dict]:
    response = client.get(
        f"/v1/agent/runs/{run_id}/events",
        headers={"Last-Event-ID": cursor},
    )
    assert response.status_code == 200
    frames = _parse_complete_sse(response.text)
    return [{**frame, "data": json.loads(frame["data"])} for frame in frames]


def test_real_socket_restart_recovers_partial_agent_run_idempotently(tmp_path):
    database = tmp_path / "agent-socket-restart.sqlite3"
    first_token = "first-token-0123456789abcdef0123456789abcdef"
    second_token = "second-token-0123456789abcdef0123456789abcdef"
    third_token = "third-token-0123456789abcdef0123456789abcdef"
    payload = {
        "kind": "conversation",
        "userIntent": "Remain partial until the process is killed",
        "mode": "teach",
        "input": {"question": "What survives a restart?"},
        "idempotencyKey": "socket-restart-run-1",
    }

    with _running_sidecar(database, first_token) as first:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{first.port}",
            headers=_headers(first_token),
            timeout=_HTTP_TIMEOUT,
            trust_env=False,
        ) as client:
            created = client.post("/v1/agent/runs", json=payload)
            assert created.status_code == 202
            run_id = created.json()["id"]
            partial_events, cursor = _read_partial_event(client, run_id)
            assert [event["event"] for event in partial_events] == [
                "metadata",
                "status",
                "content_delta",
            ]
            in_flight = client.get(f"/v1/agent/runs/{run_id}")
            assert in_flight.status_code == 200
            assert in_flight.json()["status"] == "running"
        _kill_process_group(first.process, require_running=True)

    with _running_sidecar(database, second_token) as second:
        base_url = f"http://127.0.0.1:{second.port}"
        with httpx.Client(
            base_url=base_url, timeout=_HTTP_TIMEOUT, trust_env=False
        ) as anonymous:
            old_token = anonymous.get(
                f"/v1/agent/runs/{run_id}", headers=_headers(first_token)
            )
            assert old_token.status_code == 401

        with httpx.Client(
            base_url=base_url,
            headers=_headers(second_token),
            timeout=_HTTP_TIMEOUT,
            trust_env=False,
        ) as client:
            recovered = client.get(f"/v1/agent/runs/{run_id}")
            assert recovered.status_code == 200
            assert recovered.json()["status"] == "interrupted"
            assert recovered.json()["errorCode"] == "process_restarted"

            recovery_events = _read_recovery_events(client, run_id, cursor)
            assert [event["event"] for event in recovery_events] == [
                "status",
                "error",
            ]
            assert [event["data"] for event in recovery_events] == [
                {"status": "interrupted"},
                {
                    "code": "process_restarted",
                    "message": (
                        "Agent run was interrupted by restart; start a new run "
                        "to continue"
                    ),
                    "retryable": True,
                    "status": "interrupted",
                },
            ]
            recovery_ids = [event["id"] for event in recovery_events]
            assert cursor not in recovery_ids
            assert len(recovery_ids) == len(set(recovery_ids))
        _kill_process_group(second.process, require_running=True)

    with _running_sidecar(database, third_token) as third:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{third.port}",
            headers=_headers(third_token),
            timeout=_HTTP_TIMEOUT,
            trust_env=False,
        ) as client:
            second_replay = _read_recovery_events(client, run_id, cursor)
            assert second_replay == recovery_events
            terminal = client.get(f"/v1/agent/runs/{run_id}").json()
            assert terminal["status"] == "interrupted"
            assert terminal["errorCode"] == "process_restarted"
