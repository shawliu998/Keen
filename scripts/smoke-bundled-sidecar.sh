#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly APP_BUNDLE="${1:-${REPOSITORY_ROOT}/apps/desktop/src-tauri/target/release/bundle/macos/Keen.app}"
readonly SIDECAR="${APP_BUNDLE}/Contents/MacOS/keen-learning-core"
readonly PYTHON_BIN="${PYTHON_BIN:-${REPOSITORY_ROOT}/.venv/bin/python}"

fail() {
  printf 'smoke-bundled-sidecar: error: %s\n' "$*" >&2
  if [[ -f "${stderr_log:-}" ]]; then
    sed -n '1,200p' "${stderr_log}" >&2
  fi
  exit 1
}

[[ -x "${SIDECAR}" ]] || fail "bundled executable is missing: ${SIDECAR}"
[[ -x "${PYTHON_BIN}" ]] || fail "repository Python is missing: ${PYTHON_BIN}"

umask 077
smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/keen-bundled-sidecar.XXXXXX")"
stdout_log="${smoke_root}/stdout.log"
stderr_log="${smoke_root}/stderr.log"
database_path="${smoke_root}/learning-core.sqlite3"
documents_path="${smoke_root}/documents"
runtime_path="${smoke_root}/runtime"
expected_migration_count="$(find "${REPOSITORY_ROOT}/services/learning-core/migrations" -maxdepth 1 -type f -name '[0-9][0-9][0-9]_*.sql' | wc -l | tr -d ' ')"
child_pid=""
preexisting_sidecar_pids="$(pgrep -f -- "${SIDECAR}" | sort -n || true)"

descendant_pids() {
  local root_pid="$1"
  "${PYTHON_BIN}" - "${root_pid}" <<'PY'
import subprocess
import sys

root = int(sys.argv[1])
output = subprocess.check_output(["ps", "-axo", "pid=,ppid="], text=True)
children: dict[int, list[int]] = {}
for line in output.splitlines():
    pid, parent = (int(value) for value in line.split())
    children.setdefault(parent, []).append(pid)
pending = [root]
seen: set[int] = set()
while pending:
    pid = pending.pop()
    if pid in seen:
        continue
    seen.add(pid)
    pending.extend(children.get(pid, ()))
print("\n".join(str(pid) for pid in sorted(seen)))
PY
}

cleanup() {
  exit_status=$?
  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    kill "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi
  if (( exit_status != 0 )) && [[ -f "${stderr_log}" ]]; then
    sed -n '1,240p' "${stderr_log}" >&2
  fi
  rm -rf -- "${smoke_root}"
  return "${exit_status}"
}
trap cleanup EXIT INT TERM

mkdir -m 0700 -- "${documents_path}" "${runtime_path}"
token="$(${PYTHON_BIN} -c 'import secrets; print(secrets.token_hex(32))')"

printf '%s\n' "${token}" | env -i \
  KEEN_SUPERVISOR_PID="$$" \
  TMPDIR="${runtime_path}" \
  "${SIDECAR}" \
  --token-stdin \
  --port 0 \
  --database "${database_path}" \
  --documents-directory "${documents_path}" \
  --seed-demo \
  >"${stdout_log}" 2>"${stderr_log}" &
child_pid=$!

port=""
ready=""
for _attempt in {1..1200}; do
  if ! kill -0 "${child_pid}" 2>/dev/null; then
    wait "${child_pid}" 2>/dev/null || true
    fail "bundled executable exited before READY"
  fi
  port="$(sed -n 's/^KEEN_SIDECAR_PORT=\([0-9][0-9]*\)$/\1/p' "${stdout_log}" | head -n 1)"
  ready="$(sed -n '/^KEEN_SIDECAR_READY=1$/p' "${stdout_log}" | head -n 1)"
  if [[ -n "${port}" && "${ready}" == "KEEN_SIDECAR_READY=1" ]]; then
    break
  fi
  sleep 0.1
done

[[ "${port}" =~ ^[0-9]+$ ]] || fail "bundled executable did not announce a valid port"
(( port > 0 && port <= 65535 )) || fail "announced port is outside the TCP range: ${port}"
[[ "${ready}" == "KEEN_SIDECAR_READY=1" ]] || fail "bundled executable did not announce READY within 120 seconds"

"${PYTHON_BIN}" - "${stdout_log}" <<'PY'
import sys

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
expected = [
    "KEEN_SIDECAR_PHASE=migrating",
    "KEEN_SIDECAR_PHASE=recovering",
    "KEEN_SIDECAR_PHASE=starting_server",
    "KEEN_SIDECAR_READY=1",
]
positions = [lines.index(item) for item in expected]
assert positions == sorted(positions), (expected, positions, lines[:20])
PY

process_pids="$(descendant_pids "${child_pid}")"
inner_pid="$(printf '%s\n' "${process_pids}" | grep -vx -- "${child_pid}" | head -n 1 || true)"
[[ -n "${inner_pid}" ]] || fail "bundled executable did not start its isolated Python process"
for process_pid in ${process_pids}; do
  if ps eww -p "${process_pid}" | grep -Fq -- "${token}"; then
    fail "session token leaked into process ${process_pid} arguments or environment"
  fi
done

KEEN_SMOKE_PORT="${port}" \
KEEN_SMOKE_TOKEN="${token}" \
KEEN_SMOKE_ROOT="${smoke_root}" \
KEEN_SMOKE_RUNTIME="${runtime_path}" \
KEEN_SMOKE_DATABASE="${database_path}" \
KEEN_SMOKE_EXPECTED_MIGRATION_COUNT="${expected_migration_count}" \
KEEN_SMOKE_SIDECAR_PID="${child_pid}" \
KEEN_SMOKE_SIDECAR="${SIDECAR}" \
"${PYTHON_BIN}" - <<'PY'
import io
import json
import os
import sqlite3
import struct
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

port = int(os.environ["KEEN_SMOKE_PORT"])
token = os.environ["KEEN_SMOKE_TOKEN"]
smoke_root = Path(os.environ["KEEN_SMOKE_ROOT"])
runtime_root = Path(os.environ["KEEN_SMOKE_RUNTIME"])
database_path = Path(os.environ["KEEN_SMOKE_DATABASE"])
expected_migration_count = int(os.environ["KEEN_SMOKE_EXPECTED_MIGRATION_COUNT"])
sidecar_pid = int(os.environ["KEEN_SMOKE_SIDECAR_PID"])
sidecar_path = os.environ["KEEN_SMOKE_SIDECAR"]
base_url = f"http://127.0.0.1:{port}"
auth = {"Authorization": f"Bearer {token}"}
terminal_statuses = {"cancelled", "completed", "failed", "interrupted"}


def request(path: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 10):
    data = None
    headers = dict(auth)
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    call = urllib.request.Request(base_url + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(call, timeout=timeout) as response:
            body = response.read()
            return response.status, response.headers, body
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def request_json(path: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 10):
    status, _headers, body = request(path, method=method, payload=payload, timeout=timeout)
    return status, json.loads(body)


def import_file(
    filename: str,
    payload: bytes,
    media_type: str,
    *,
    course_id: str | None = None,
    timeout: float = 15,
):
    boundary = "----keen-bundled-smoke-boundary"
    parts = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {media_type}\r\n\r\n"
        ).encode("ascii"),
        payload,
        b"\r\n",
    ]
    if course_id is not None:
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="course_id"\r\n\r\n',
                course_id.encode(),
                b"\r\n",
            ]
        )
    parts.append(f"--{boundary}--\r\n".encode())
    call = urllib.request.Request(
        base_url + "/v1/documents/import",
        data=b"".join(parts),
        method="POST",
        headers={
            **auth,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(call, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def wait_job(job_id: str, *, terminal: set[str] = terminal_statuses, timeout: float = 45):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        status, latest = request_json(f"/v1/index-jobs/{job_id}")
        assert status == 200, (status, latest)
        if latest["status"] in terminal:
            return latest
        time.sleep(0.03)
    raise AssertionError(("job timeout", job_id, latest))


def wait_running(job_id: str, timeout: float = 10):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        status, latest = request_json(f"/v1/index-jobs/{job_id}")
        assert status == 200, (status, latest)
        if latest["status"] == "running":
            return latest
        if latest["status"] in terminal_statuses:
            raise AssertionError(("job became terminal before running cancel", latest))
        time.sleep(0.01)
    raise AssertionError(("job did not enter running", latest))


def pdf_with_pages(page_count: int, text: str) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for page_number in range(page_count):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        stream = DecodedStreamObject()
        line = f"{text} page {page_number + 1}".replace("(", "[").replace(")", "]")
        stream.set_data(f"BT\n/F1 12 Tf\n72 720 Td\n({line}) Tj\nET\n".encode())
        page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


# Authenticated health is checked only after the explicit READY protocol.
status, health = request_json("/health")
assert status == 200 and health["service"] == "keen-learning-core" and health["status"] == "ok"
unauthorized = urllib.request.Request(
    base_url + "/health", headers={"Authorization": "Bearer wrong-token"}
)
try:
    urllib.request.urlopen(unauthorized, timeout=3)
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError("health endpoint accepted an invalid token")

# Load and execute the sqlite-vec native backend extracted from this one-file bundle.
vec_libraries = list(runtime_root.rglob("vec0.dylib"))
assert len(vec_libraries) == 1, vec_libraries
with sqlite3.connect(":memory:") as vector_connection:
    vector_connection.enable_load_extension(True)
    vector_connection.load_extension(str(vec_libraries[0]))
    vector_connection.enable_load_extension(False)
    assert vector_connection.execute("SELECT vec_version()").fetchone()[0] == "v0.1.9"
    vector_connection.execute("CREATE VIRTUAL TABLE smoke_vec USING vec0(embedding float[3])")
    vector_connection.executemany(
        "INSERT INTO smoke_vec(rowid, embedding) VALUES (?, ?)",
        [(1, "[1,0,0]"), (2, "[0,1,0]")],
    )
    nearest = vector_connection.execute(
        "SELECT rowid FROM smoke_vec WHERE embedding MATCH ? AND k = 1 ORDER BY distance",
        ("[0.9,0.1,0]",),
    ).fetchone()[0]
    assert nearest == 1

# 202 import plus durable polling, authenticated PDF content, and persisted geometry.
normal_pdf = pdf_with_pages(1, "Keen bundled PDF geometry smoke")
status, imported_pdf = import_file("geometry.pdf", normal_pdf, "application/pdf")
assert status == 202, (status, imported_pdf)
pdf_job = wait_job(imported_pdf["job"]["id"])
assert pdf_job["status"] == "completed", pdf_job
pdf_document_id = imported_pdf["document"]["id"]
status, headers, returned_pdf = request(f"/v1/documents/{pdf_document_id}/content")
assert status == 200 and headers.get_content_type() == "application/pdf"
assert returned_pdf == normal_pdf
with sqlite3.connect(database_path) as connection:
    applied_migrations = [
        row[0]
        for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    assert applied_migrations == list(range(1, expected_migration_count + 1)), applied_migrations
    geometry = connection.execute(
        """
        SELECT original_text, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
               page_width, page_height
        FROM document_chunk_geometry geometry
        JOIN document_chunks chunks ON chunks.id = geometry.chunk_id
        WHERE chunks.document_id = ?
        """,
        (pdf_document_id,),
    ).fetchall()
assert geometry, "PDF geometry was not persisted"
assert any("Keen bundled PDF geometry smoke" in row[0] for row in geometry)
assert all(0 <= row[1] < row[3] <= row[5] and 0 <= row[2] < row[4] <= row[6] for row in geometry)

# Migration 021 and the frozen course-create route must travel together. The
# second request proves the bundled service replays the same logical mutation.
course_payload = {
    "title": "Bundled course creation smoke",
    "description": "Migration 021 packaging evidence",
    "idempotencyKey": "bundled-course-smoke-key-0001",
}
status, created_course = request_json("/v1/courses", method="POST", payload=course_payload)
assert status == 201, (status, created_course)
assert created_course["replayed"] is False, created_course
status, replayed_course = request_json("/v1/courses", method="POST", payload=course_payload)
assert status == 200, (status, replayed_course)
assert replayed_course["replayed"] is True, replayed_course
assert replayed_course["course"] == created_course["course"], (
    created_course,
    replayed_course,
)

# Same content is one document linked to two real course rows.
shared = b"Shared thermodynamics source for two course links."
status, first = import_file(
    "shared.txt", shared, "text/plain", course_id="course-calculus"
)
assert status == 202, (status, first)
assert wait_job(first["job"]["id"])["status"] == "completed"
status, second = import_file(
    "shared.txt", shared, "text/plain", course_id="course-physics"
)
assert status == 200, (status, second)
assert second["duplicate"] is True and second["linked"] is True
assert second["document"]["id"] == first["document"]["id"]
assert second["document"]["courseIds"] == ["course-calculus", "course-physics"]

# A real CJK FTS query must find the asynchronously indexed source without a model.
cjk = "叶绿体通过光合作用把光能转化为化学能。".encode()
status, cjk_import = import_file(
    "cjk.txt", cjk, "text/plain", course_id="course-physics"
)
assert status == 202, (status, cjk_import)
assert wait_job(cjk_import["job"]["id"])["status"] == "completed"
status, cjk_search = request_json(
    "/v1/search",
    method="POST",
    payload={"query": "叶绿体光合作用", "courseId": "course-physics", "limit": 8},
)
assert status == 200 and cjk_search["mode"] == "lexical_only", cjk_search
assert any(item["documentId"] == cjk_import["document"]["id"] for item in cjk_search["results"])

# Hold the real worker in PDF parsing, then exercise both queued and running cancellation.
slow_pdf = pdf_with_pages(1500, "Cancellable bundled PDF worker")
status, running_import = import_file("cancel-running.pdf", slow_pdf, "application/pdf")
assert status == 202, (status, running_import)
running_job_id = running_import["job"]["id"]
wait_running(running_job_id)
status, queued_import = import_file(
    "cancel-queued.txt", b"This job must remain queued behind PDF parsing.", "text/plain"
)
assert status == 202, (status, queued_import)
queued_job_id = queued_import["job"]["id"]
status, queued_cancel = request_json(
    f"/v1/index-jobs/{queued_job_id}/cancel", method="POST"
)
assert status == 200 and queued_cancel["status"] == "cancelled", queued_cancel
status, running_cancel = request_json(
    f"/v1/index-jobs/{running_job_id}/cancel", method="POST"
)
assert status == 200 and running_cancel["status"] in {"cancel_requested", "cancelled"}
assert wait_job(queued_job_id)["status"] == "cancelled"
assert wait_job(running_job_id)["status"] == "cancelled"

# The persistent worker remains usable and no cancelled staging rows survive.
status, post_cancel = import_file(
    "after-cancel.txt", b"The durable worker remains usable after cancellation.", "text/plain"
)
assert status == 202, (status, post_cancel)
assert wait_job(post_cancel["job"]["id"])["status"] == "completed"
with sqlite3.connect(database_path) as connection:
    assert connection.execute(
        "SELECT COUNT(*) FROM document_index_jobs WHERE status IN ('queued','running','cancel_requested')"
    ).fetchone()[0] == 0
    for document_id in (
        running_import["document"]["id"],
        queued_import["document"]["id"],
    ):
        assert connection.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?", (document_id,)
        ).fetchone()[0] == 0
        assert connection.execute(
            """
            SELECT COUNT(*) FROM document_chunk_geometry geometry
            JOIN document_chunks chunks ON chunks.id = geometry.chunk_id
            WHERE chunks.document_id = ?
            """,
            (document_id,),
        ).fetchone()[0] == 0

# No cancelled PDF parser process may remain under the one-file process tree.
processes = subprocess.check_output(
    ["ps", "-axo", "pid=,ppid=,command="], text=True
).splitlines()
rows = []
children: dict[int, list[int]] = {}
commands: dict[int, str] = {}
for line in processes:
    fields = line.strip().split(None, 2)
    if len(fields) < 2:
        continue
    pid, parent = int(fields[0]), int(fields[1])
    children.setdefault(parent, []).append(pid)
    commands[pid] = fields[2] if len(fields) == 3 else ""
pending = [sidecar_pid]
descendants = set()
while pending:
    pid = pending.pop()
    if pid in descendants:
        continue
    descendants.add(pid)
    pending.extend(children.get(pid, ()))
for pid in descendants:
    command = commands.get(pid, "")
    if pid == sidecar_pid:
        continue
    if "multiprocessing.resource_tracker" in command:
        continue
    assert "multiprocessing.spawn" not in command, (pid, command)
    assert "--multiprocessing-fork" not in command, (pid, command)
    assert sidecar_path in command, ("unexpected sidecar descendant", pid, command)
PY

for process_pid in $(descendant_pids "${child_pid}"); do
  if ps eww -p "${process_pid}" | grep -Fq -- "${token}"; then
    fail "session token leaked into process ${process_pid} after job execution"
  fi
done

known_sidecar_pids="$(descendant_pids "${child_pid}")"
kill "${child_pid}"
wait "${child_pid}" 2>/dev/null || true
for _attempt in {1..100}; do
  survivors=""
  for process_pid in ${known_sidecar_pids}; do
    if kill -0 "${process_pid}" 2>/dev/null; then
      survivors="${survivors} ${process_pid}"
    fi
  done
  [[ -z "${survivors}" ]] && break
  sleep 0.1
done
[[ -z "${survivors:-}" ]] || fail "bundled sidecar descendants remained after shutdown:${survivors}"

remaining_sidecar_pids="$(pgrep -f -- "${SIDECAR}" | sort -n || true)"
[[ "${remaining_sidecar_pids}" == "${preexisting_sidecar_pids}" ]] || fail "bundled sidecar process set did not return to its pre-smoke baseline"
child_pid=""

printf 'smoke-bundled-sidecar: READY, jobs, cancellation, CJK, M:N, sqlite-vec, PDF geometry/content, token handling, and cleanup passed on port %s\n' "${port}"
