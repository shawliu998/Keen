#!/usr/bin/env python3
"""Verify a frozen Keen sidecar against a local OpenAI-compatible provider.

This smoke uses a loopback mock, never a vendor account. It verifies the
packaged transport, explicit API-base path, provider failure/recovery, source
grounding, focused-study persistence, token rotation, and idempotent replay.
"""

from __future__ import annotations

import json
import os
import secrets
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

READY_TIMEOUT_SECONDS = 120
MOCK_MODEL = "keen-package-mock"
WRONG_MODEL = "keen-package-missing-model"
CLIENT_REQUEST_ID = "00000000-0000-4000-8000-000000000101"
FOCUSED_IDEMPOTENCY_KEY = "packaged-focused-study-request-0001"


class MockProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: ClassVar[list[tuple[str, str, dict[str, Any] | None]]] = []

    def do_GET(self) -> None:
        self.requests.append(("GET", self.path, None))
        if self.path != "/api/v1/models":
            self._json(404, {"error": "not found"})
            return
        self._json(200, {"data": [{"id": MOCK_MODEL}]})

    def do_POST(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"error": "invalid JSON"})
            return
        self.requests.append(("POST", self.path, payload))
        if self.path != "/api/v1/chat/completions":
            self._json(404, {"error": "not found"})
            return
        if payload.get("model") != MOCK_MODEL or payload.get("stream") is not True:
            self._json(400, {"error": "unexpected request"})
            return
        chunks = [
            {
                "model": MOCK_MODEL,
                "choices": [{"delta": {"content": "Eigenvectors preserve direction "}}],
            },
            {
                "model": MOCK_MODEL,
                "choices": [{"delta": {"content": "[[source:1]]"}}],
            },
            {
                "model": MOCK_MODEL,
                "choices": [{"delta": {}, "finish_reason": "stop"}],
            },
        ]
        body = (
            "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
            + "data: [DONE]\n\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@dataclass
class SidecarInstance:
    process: subprocess.Popen[str]
    port: int
    token: str
    stderr_path: Path


def fail(message: str, *, stderr_path: Path | None = None) -> None:
    detail = ""
    if stderr_path is not None and stderr_path.is_file():
        detail = stderr_path.read_text(encoding="utf-8", errors="replace")[:12_000]
    raise AssertionError(f"{message}{chr(10) + detail if detail else ''}")


def start_sidecar(
    sidecar: Path,
    root: Path,
    generation: int,
    *,
    provider_base: str,
    model: str,
) -> SidecarInstance:
    runtime = root / f"runtime-{generation}"
    documents = root / "documents"
    runtime.mkdir(mode=0o700)
    documents.mkdir(mode=0o700, exist_ok=True)
    stderr_path = root / f"generation-{generation}.stderr.log"
    stderr_file = stderr_path.open("w", encoding="utf-8")
    token = secrets.token_hex(32)
    process = subprocess.Popen(
        [
            str(sidecar),
            "--token-stdin",
            "--port",
            "0",
            "--database",
            str(root / "learning-core.sqlite3"),
            "--documents-directory",
            str(documents),
            "--chat-provider",
            "openai-compatible",
            "--chat-base-url",
            provider_base,
            "--chat-model",
            model,
            "--chat-version",
            model,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        text=True,
        bufsize=1,
        env={
            "KEEN_SUPERVISOR_PID": str(os.getpid()),
            "TMPDIR": str(runtime),
        },
        start_new_session=True,
    )
    stderr_file.close()
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(token + "\n")
    process.stdin.close()

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    port: int | None = None
    ready = False
    buffered_output = b""
    while time.monotonic() < deadline and not ready:
        if process.poll() is not None:
            fail(
                f"generation {generation} exited before READY with {process.returncode}",
                stderr_path=stderr_path,
            )
        for _key, _mask in selector.select(timeout=0.1):
            chunk = os.read(process.stdout.fileno(), 65_536)
            if not chunk:
                continue
            buffered_output += chunk
            while b"\n" in buffered_output:
                raw_line, buffered_output = buffered_output.split(b"\n", 1)
                line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
                if line.startswith("KEEN_SIDECAR_PORT="):
                    port = int(line.partition("=")[2])
                elif line == "KEEN_SIDECAR_READY=1":
                    ready = True
    selector.close()
    if not ready or port is None:
        stop_sidecar(process)
        fail(f"generation {generation} did not become ready", stderr_path=stderr_path)
    return SidecarInstance(process, port, token, stderr_path)


def stop_sidecar(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=12)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def request(
    instance: SidecarInstance,
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, bytes]:
    headers = {"Authorization": f"Bearer {token or instance.token}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    call = urllib.request.Request(
        f"http://127.0.0.1:{instance.port}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(call, timeout=15) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def request_json(
    instance: SidecarInstance,
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    status, body = request(
        instance,
        path,
        token=token,
        method=method,
        payload=payload,
    )
    return status, json.loads(body)


def import_text(
    instance: SidecarInstance, course_id: str, content: str
) -> dict[str, Any]:
    boundary = "----keen-provider-journey"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                b'Content-Disposition: form-data; name="file"; '
                b'filename="eigenvectors.txt"\r\n'
                b"Content-Type: text/plain\r\n\r\n"
            ),
            content.encode(),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="course_id"\r\n\r\n',
            course_id.encode(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    call = urllib.request.Request(
        f"http://127.0.0.1:{instance.port}/v1/documents/import",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {instance.token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(call, timeout=15) as response:
        assert response.status == 202
        imported = json.load(response)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        status, job = request_json(instance, f"/v1/index-jobs/{imported['job']['id']}")
        assert status == 200, (status, job)
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            assert job["status"] == "completed", job
            return imported
        time.sleep(0.03)
    raise AssertionError("provider-journey source indexing timed out")


def parse_sse(body: bytes) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    for line in body.decode().splitlines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            assert event_name is not None
            events.append((event_name, json.loads(line.removeprefix("data: "))))
            event_name = None
    return events


def main() -> int:
    repository = Path(__file__).resolve().parent.parent
    app_bundle = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else repository / "apps/desktop/src-tauri/target/release/bundle/macos/Keen.app"
    )
    sidecar = app_bundle / "Contents/MacOS/keen-learning-core"
    if not sidecar.is_file() or not os.access(sidecar, os.X_OK):
        fail(f"bundled sidecar is missing or not executable: {sidecar}")

    MockProviderHandler.requests = []
    provider_server = ThreadingHTTPServer(("127.0.0.1", 0), MockProviderHandler)
    provider_thread = threading.Thread(
        target=provider_server.serve_forever, daemon=True
    )
    provider_thread.start()
    provider_base = f"http://127.0.0.1:{provider_server.server_port}/api/v1"

    with tempfile.TemporaryDirectory(prefix="keen-provider-journey-") as temporary:
        root = Path(temporary)
        instances: list[SidecarInstance] = []
        try:
            first = start_sidecar(
                sidecar,
                root,
                1,
                provider_base=provider_base,
                model=MOCK_MODEL,
            )
            instances.append(first)
            status, connected = request_json(first, "/v1/provider/test", method="POST")
            assert status == 200 and connected == {
                "status": "connected",
                "provider": "openai-compatible",
                "model": MOCK_MODEL,
                "detail": "Connected",
            }, (status, connected)

            status, course_result = request_json(
                first,
                "/v1/courses",
                method="POST",
                payload={
                    "title": "Packaged provider journey",
                    "description": "Fresh-profile provider and recovery smoke",
                    "idempotencyKey": "packaged-provider-course-0001",
                },
            )
            assert status == 201, (status, course_result)
            course_id = course_result["course"]["id"]
            imported = import_text(
                first,
                course_id,
                (
                    "Eigenvectors preserve their direction under a linear "
                    "transformation. Their eigenvalues describe how strongly "
                    "that direction is scaled. Distinct eigenvectors can form "
                    "a basis that makes repeated transformations easier to "
                    "understand."
                ),
            )

            status, answer_body = request(
                first,
                "/v1/answer/stream",
                method="POST",
                payload={
                    "question": "What do eigenvectors preserve?",
                    "courseId": course_id,
                    "conversationId": "packaged-provider-conversation",
                    "retrievalLimit": 8,
                },
            )
            assert status == 200
            events = parse_sse(answer_body)
            assert any(name == "citation" for name, _data in events), events
            assert events[-1][0] == "done" and events[-1][1]["grounded"] is True

            focused_payload = {
                "course_id": course_id,
                "goal": "Understand eigenvectors and eigenvalues",
                "client_request_id": CLIENT_REQUEST_ID,
                "idempotency_key": FOCUSED_IDEMPOTENCY_KEY,
            }
            status, focused = request_json(
                first,
                "/v1/focused-study-requests",
                method="POST",
                payload=focused_payload,
            )
            assert status == 201 and focused["outcome"] == "session_created", (
                status,
                focused,
            )
            session_id = focused["session"]["id"]
            assert imported["document"]["id"] in {
                result["documentId"]
                for name, data in events
                if name == "retrieval"
                for result in data["chunks"]
            }
            stop_sidecar(first.process)

            broken = start_sidecar(
                sidecar,
                root,
                2,
                provider_base=provider_base,
                model=WRONG_MODEL,
            )
            instances.append(broken)
            status, _old_auth = request_json(broken, "/health", token=first.token)
            assert status == 401
            status, failed_test = request_json(
                broken, "/v1/provider/test", method="POST"
            )
            assert status == 503 and failed_test["detail"]["retryable"] is True
            status, persisted = request_json(
                broken,
                f"/v1/study-sessions/{session_id}?"
                + urllib.parse.urlencode({"course_id": course_id}),
            )
            assert status == 200 and persisted["session"]["id"] == session_id
            stop_sidecar(broken.process)

            recovered = start_sidecar(
                sidecar,
                root,
                3,
                provider_base=provider_base,
                model=MOCK_MODEL,
            )
            instances.append(recovered)
            status, _old_auth = request_json(recovered, "/health", token=broken.token)
            assert status == 401
            status, reconnected = request_json(
                recovered, "/v1/provider/test", method="POST"
            )
            assert status == 200 and reconnected["model"] == MOCK_MODEL
            status, restored = request_json(
                recovered,
                f"/v1/study-sessions/{session_id}?"
                + urllib.parse.urlencode({"course_id": course_id}),
            )
            assert status == 200 and restored["session"] == persisted["session"]
            status, replayed = request_json(
                recovered,
                "/v1/focused-study-requests",
                method="POST",
                payload=focused_payload,
            )
            assert status == 200 and replayed["outcome"] == "replayed"
            assert replayed["session"]["id"] == session_id

            with sqlite3.connect(root / "learning-core.sqlite3") as connection:
                assert (
                    connection.execute(
                        "SELECT COUNT(*) FROM focused_study_request_identities"
                    ).fetchone()[0]
                    == 1
                )
                assert (
                    connection.execute(
                        "SELECT COUNT(*) FROM study_sessions"
                    ).fetchone()[0]
                    == 1
                )

            get_paths = [
                path
                for method, path, _payload in MockProviderHandler.requests
                if method == "GET"
            ]
            post_requests = [
                (path, payload)
                for method, path, payload in MockProviderHandler.requests
                if method == "POST"
            ]
            assert get_paths.count("/api/v1/models") == 3, get_paths
            assert [path for path, _payload in post_requests] == [
                "/api/v1/chat/completions"
            ], post_requests
            chat_payload = post_requests[0][1]
            assert chat_payload is not None
            assert chat_payload["model"] == MOCK_MODEL
            assert chat_payload["stream"] is True
        finally:
            for instance in reversed(instances):
                stop_sidecar(instance.process)
            provider_server.shutdown()
            provider_server.server_close()
            provider_thread.join(timeout=5)

    print(
        "smoke-bundled-provider-journey: explicit API base, provider test, "
        "grounded answer, failure/recovery, focused-study persistence, token "
        "rotation, and idempotent replay passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
