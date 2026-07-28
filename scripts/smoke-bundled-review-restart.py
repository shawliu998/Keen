#!/usr/bin/env python3
"""Exercise Review persistence through real frozen-sidecar process restarts.

This is a packaged service smoke, not GUI automation. It uses one explicit SQLite
fixture because Keen intentionally has no public arbitrary-card creation route.
"""

from __future__ import annotations

import json
import os
import selectors
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


READY_TIMEOUT_SECONDS = 120
REVIEW_ID = "packaged-review-restart-smoke"
ATTEMPT_KEY = "packaged-review-restart-attempt-0001"


@dataclass
class SidecarInstance:
    process: subprocess.Popen[str]
    port: int
    token: str
    stdout: list[str]
    stderr_path: Path


def fail(message: str, *, stderr_path: Path | None = None) -> None:
    detail = ""
    if stderr_path is not None and stderr_path.is_file():
        detail = stderr_path.read_text(encoding="utf-8", errors="replace")[:12_000]
    raise AssertionError(f"{message}{chr(10) + detail if detail else ''}")


def start_sidecar(sidecar: Path, root: Path, generation: int) -> SidecarInstance:
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
            "--seed-demo",
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
    output: list[str] = []
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
                output.append(line)
                if line.startswith("KEEN_SIDECAR_PORT="):
                    port = int(line.partition("=")[2])
                elif line == "KEEN_SIDECAR_READY=1":
                    ready = True
    selector.close()
    if not ready or port is None:
        stop_sidecar(process)
        fail(f"generation {generation} did not become ready", stderr_path=stderr_path)
    phases = [
        "KEEN_SIDECAR_PHASE=migrating",
        "KEEN_SIDECAR_PHASE=recovering",
        "KEEN_SIDECAR_PHASE=starting_server",
        "KEEN_SIDECAR_READY=1",
    ]
    positions = [output.index(phase) for phase in phases]
    if positions != sorted(positions):
        stop_sidecar(process)
        fail(f"generation {generation} lifecycle order was invalid: {output[:20]}")
    return SidecarInstance(process, port, token, output, stderr_path)


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


def request_json(
    instance: SidecarInstance,
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token or instance.token}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    call = urllib.request.Request(
        f"http://127.0.0.1:{instance.port}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(call, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def seed_due_review(database_path: Path) -> None:
    due_at = "2026-07-01T00:00:00+00:00"
    created_at = "2026-07-01T00:00:00+00:00"
    answer = {
        "accepted_answers": [
            "Differentiate the outer function, then multiply by the inner derivative."
        ]
    }
    creation = {
        "fixture": "packaged review restart smoke",
        "review_id": REVIEW_ID,
    }
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        sequence = connection.execute(
            "SELECT next_card_id FROM review_fsrs_identity_sequence WHERE singleton = 1"
        ).fetchone()
        if sequence is None:
            fail("packaged database has no FSRS identity sequence")
        card_id = int(sequence[0])
        connection.execute(
            "UPDATE review_fsrs_identity_sequence SET next_card_id = ? WHERE singleton = 1",
            (card_id + 1,),
        )
        connection.execute(
            """INSERT INTO review_items (
                   id, course_id, concept_id, item_type, prompt,
                   expected_answer_json, source_type, source_id, status,
                   idempotency_key, creation_payload_json, created_at, updated_at
               ) VALUES (?, 'course-calculus', 'concept-chain-rule', 'free_recall', ?,
                         ?, 'manual', NULL, 'active', ?, ?, ?, ?)""",
            (
                REVIEW_ID,
                "Explain the chain rule.",
                json.dumps(answer, separators=(",", ":")),
                "packaged-review-restart-create-0001",
                json.dumps(creation, separators=(",", ":")),
                created_at,
                created_at,
            ),
        )
        connection.execute(
            """INSERT INTO review_schedules (
                   review_item_id, difficulty, stability, due_at,
                   last_reviewed_at, repetitions, lapses, state, scheduler,
                   scheduler_version, scheduler_state_json, revision, updated_at,
                   fsrs_card_id
               ) VALUES (?, 5.0, 0.0, ?, NULL, 0, 0, 'new', 'fsrs',
                         'fsrs-6.3.1-keen-v1', ?, 0, ?, ?)""",
            (
                REVIEW_ID,
                due_at,
                json.dumps({"card_id": card_id, "step": 0}, separators=(",", ":")),
                created_at,
                card_id,
            ),
        )


def main() -> int:
    repository = Path(__file__).resolve().parent.parent
    app_bundle = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else (
            repository / "apps/desktop/src-tauri/target/release/bundle/macos/Keen.app"
        )
    )
    sidecar = app_bundle / "Contents/MacOS/keen-learning-core"
    if not sidecar.is_file() or not os.access(sidecar, os.X_OK):
        fail(f"bundled sidecar is missing or not executable: {sidecar}")

    with tempfile.TemporaryDirectory(prefix="keen-review-restart-") as temporary:
        root = Path(temporary)
        instances: list[SidecarInstance] = []
        try:
            migrated = start_sidecar(sidecar, root, 1)
            instances.append(migrated)
            status, health = request_json(migrated, "/health")
            assert status == 200 and health["status"] == "ok", (status, health)
            stop_sidecar(migrated.process)
            seed_due_review(root / "learning-core.sqlite3")

            rated = start_sidecar(sidecar, root, 2)
            instances.append(rated)
            status, old_auth = request_json(rated, "/health", token=migrated.token)
            assert status == 401, (status, old_auth)
            status, queue = request_json(rated, "/v1/reviews/due")
            assert status == 200, (status, queue)
            item = next(
                review for review in queue["items"] if review["id"] == REVIEW_ID
            )
            assert item["revision"] == 0 and item["scheduler"] == "fsrs", item
            attempt_payload = {
                "rating": "good",
                "response": "Outer derivative times the inner derivative.",
                "expectedRevision": 0,
                "idempotencyKey": ATTEMPT_KEY,
            }
            status, applied = request_json(
                rated,
                f"/v1/reviews/{REVIEW_ID}/attempts",
                method="POST",
                payload=attempt_payload,
            )
            assert status == 201 and applied["outcome"] == "applied", (status, applied)
            assert applied["schedule"]["revision"] == 1, applied
            stop_sidecar(rated.process)

            recovered = start_sidecar(sidecar, root, 3)
            instances.append(recovered)
            status, old_auth = request_json(recovered, "/health", token=rated.token)
            assert status == 401, (status, old_auth)
            status, queue = request_json(recovered, "/v1/reviews/due")
            assert status == 200, (status, queue)
            assert REVIEW_ID not in {review["id"] for review in queue["items"]}, queue
            status, replayed = request_json(
                recovered,
                f"/v1/reviews/{REVIEW_ID}/attempts",
                method="POST",
                payload=attempt_payload,
            )
            assert status == 200 and replayed["outcome"] == "replayed", (
                status,
                replayed,
            )
            assert replayed["schedule"] == applied["schedule"], (applied, replayed)
            with sqlite3.connect(root / "learning-core.sqlite3") as connection:
                revision = connection.execute(
                    "SELECT revision FROM review_schedules WHERE review_item_id = ?",
                    (REVIEW_ID,),
                ).fetchone()[0]
                attempts = connection.execute(
                    "SELECT COUNT(*) FROM review_attempts WHERE review_item_id = ?",
                    (REVIEW_ID,),
                ).fetchone()[0]
            assert revision == 1 and attempts == 1, (revision, attempts)
        finally:
            for instance in reversed(instances):
                stop_sidecar(instance.process)

    print(
        "smoke-bundled-review-restart: token rotation, due read, FSRS rating, "
        "restart recovery, idempotent replay, and single-attempt persistence passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
