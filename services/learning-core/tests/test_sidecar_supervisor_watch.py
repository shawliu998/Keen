from __future__ import annotations

import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from app.instance_lock import (
    InstanceAlreadyRunningError,
    hold_database_instance_lock,
)


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="supervisor process lifecycle is Unix-only"
)

_REPOSITORY_ROOT = Path(__file__).parents[3]
_SERVICE_ROOT = Path(__file__).parents[1]
_ENTRYPOINT = _REPOSITORY_ROOT / "apps/desktop/src-tauri/sidecar/entrypoint.py"
_PROCESS_TIMEOUT_SECONDS = 20.0
_TOKEN = "watchdog-token-0123456789abcdef0123456789abcdef"


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
        "watchdog sidecar did not become ready; "
        f"exit={process.poll()} stdout={output!r} stderr={errors!r}"
    )


def _stop_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2.0)
    else:
        process.wait(timeout=2.0)


def test_sidecar_exits_and_releases_resources_when_supervisor_disappears(
    tmp_path: Path,
) -> None:
    supervisor = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    database = tmp_path / "learning-core.sqlite3"
    documents = tmp_path / "documents"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    environment = {
        "KEEN_SUPERVISOR_PID": str(supervisor.pid),
        "PYTHONNOUSERSITE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(_SERVICE_ROOT),
        "TMPDIR": str(runtime),
    }
    sidecar = subprocess.Popen(
        [
            sys.executable,
            str(_ENTRYPOINT),
            "--token-stdin",
            "--port",
            "0",
            "--database",
            str(database),
            "--documents-directory",
            str(documents),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        cwd=_SERVICE_ROOT,
        env=environment,
    )
    try:
        assert sidecar.stdin is not None
        sidecar.stdin.write(f"{_TOKEN}\n")
        sidecar.stdin.flush()
        sidecar.stdin.close()
        port = _read_ready(sidecar)

        response = httpx.get(
            f"http://127.0.0.1:{port}/health",
            headers={"Authorization": f"Bearer {_TOKEN}"},
            timeout=2.0,
            trust_env=False,
        )
        assert response.status_code == 200
        with pytest.raises(InstanceAlreadyRunningError):
            with hold_database_instance_lock(database):
                pass

        supervisor.terminate()
        supervisor.wait(timeout=2.0)
        assert sidecar.wait(timeout=5.0) == 1

        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=0.25)
        with hold_database_instance_lock(database):
            pass
    finally:
        _stop_process_group(sidecar)
        _stop_process_group(supervisor)
        if sidecar.stdout is not None:
            sidecar.stdout.close()
        if sidecar.stderr is not None:
            sidecar.stderr.close()
