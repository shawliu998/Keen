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
    sed -n '1,160p' "${stderr_log}" >&2
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
child_pid=""

cleanup() {
  exit_status=$?
  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    kill "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi
  if (( exit_status != 0 )) && [[ -f "${stderr_log}" ]]; then
    sed -n '1,200p' "${stderr_log}" >&2
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
  >"${stdout_log}" 2>"${stderr_log}" &
child_pid=$!

port=""
for _attempt in {1..100}; do
  if ! kill -0 "${child_pid}" 2>/dev/null; then
    wait "${child_pid}" 2>/dev/null || true
    fail "bundled executable exited before announcing its port"
  fi
  port="$(sed -n 's/^KEEN_SIDECAR_PORT=\([0-9][0-9]*\)$/\1/p' "${stdout_log}" | head -n 1)"
  if [[ -n "${port}" ]]; then
    break
  fi
  sleep 0.1
done

[[ "${port}" =~ ^[0-9]+$ ]] || fail "bundled executable did not announce a valid port"
(( port > 0 && port <= 65535 )) || fail "announced port is outside the TCP range: ${port}"

inner_pid=""
for _attempt in {1..50}; do
  inner_pid="$(pgrep -P "${child_pid}" -f "${SIDECAR}" | head -n 1 || true)"
  if [[ -n "${inner_pid}" ]]; then
    break
  fi
  sleep 0.1
done
[[ -n "${inner_pid}" ]] || fail "bundled executable did not start its isolated Python process"
if ps eww -p "${child_pid}" | grep -Fq -- "${token}"; then
  fail "session token leaked into the bootloader process environment or arguments"
fi
if ps eww -p "${inner_pid}" | grep -Fq -- "${token}"; then
  fail "session token leaked into the Python process environment or arguments"
fi
baseline_sidecar_pids="$(pgrep -f -- "${SIDECAR}" | sort -n)"

KEEN_SMOKE_PORT="${port}" KEEN_SMOKE_TOKEN="${token}" "${PYTHON_BIN}" - <<'PY'
import json
import io
import os
import urllib.error
import urllib.request

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

port = int(os.environ["KEEN_SMOKE_PORT"])
token = os.environ["KEEN_SMOKE_TOKEN"]
url = f"http://127.0.0.1:{port}/health"

request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(request, timeout=3) as response:
    payload = json.load(response)
    assert response.status == 200
    assert payload["service"] == "keen-learning-core"
    assert payload["status"] == "ok"

unauthorized = urllib.request.Request(url, headers={"Authorization": "Bearer wrong-token"})
try:
    urllib.request.urlopen(unauthorized, timeout=3)
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError("health endpoint accepted an invalid token")


def pdf_with_stream(stream_data: bytes) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font),
        }),
    })
    stream = DecodedStreamObject()
    stream.set_data(stream_data)
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def import_pdf(filename: str, payload: bytes, timeout: float = 10) -> tuple[int, dict]:
    boundary = "----keen-bundled-smoke-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("ascii") + payload + f"\r\n--{boundary}--\r\n".encode("ascii")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/documents/import",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


normal_pdf = pdf_with_stream(
    b"BT\n/F1 12 Tf\n72 720 Td\n(Keen bundled PDF worker smoke) Tj\nET\n"
)
status, imported = import_pdf("bundled-smoke.pdf", normal_pdf)
assert status == 201, (status, imported)
assert imported["document"]["status"] == "indexed", imported
assert imported["document"]["chunkCount"] >= 1, imported

compressed_pdf = pdf_with_stream(b"BT\n/F1 12 Tf\n(A) Tj\nET\n" * 700_000)
status, rejected = import_pdf("compressed-operators.pdf", compressed_pdf)
assert status == 422, (status, rejected)
detail = rejected["detail"]
message = detail["message"] if isinstance(detail, dict) else detail
assert "bounded resource budget" in message or "character extraction limit" in message, message

with urllib.request.urlopen(request := urllib.request.Request(
    url,
    headers={"Authorization": f"Bearer {token}"},
), timeout=3) as response:
    assert response.status == 200
PY

sidecar_pids_after_pdf=""
for _attempt in {1..30}; do
  sidecar_pids_after_pdf="$(pgrep -f -- "${SIDECAR}" | sort -n)"
  unexpected_pdf_process=""
  tracker_pid=""
  main_process_group="$(ps -o pgid= -p "${inner_pid}" | tr -d ' ')"
  for baseline_pid in ${baseline_sidecar_pids}; do
    if ! printf '%s\n' "${sidecar_pids_after_pdf}" | grep -qx -- "${baseline_pid}"; then
      unexpected_pdf_process="baseline process ${baseline_pid} disappeared"
      break
    fi
  done
  if [[ -z "${unexpected_pdf_process}" ]]; then
    for observed_pid in ${sidecar_pids_after_pdf}; do
      if printf '%s\n' "${baseline_sidecar_pids}" | grep -qx -- "${observed_pid}"; then
        continue
      fi
      observed_command="$(ps -o command= -p "${observed_pid}")"
      observed_parent="$(ps -o ppid= -p "${observed_pid}" | tr -d ' ')"
      observed_group="$(ps -o pgid= -p "${observed_pid}" | tr -d ' ')"
      if [[ -z "${tracker_pid}" \
        && "${observed_parent}" == "${inner_pid}" \
        && "${observed_group}" == "${main_process_group}" \
        && "${observed_command}" == *"from multiprocessing.resource_tracker import main"* ]]; then
        tracker_pid="${observed_pid}"
        continue
      fi
      unexpected_pdf_process="${observed_pid}"
      break
    done
  fi
  if [[ -z "${unexpected_pdf_process}" ]]; then
    break
  fi
  sleep 0.1
done
if [[ -n "${unexpected_pdf_process}" ]]; then
  ps -o pid=,ppid=,pgid=,stat=,command= -p "${sidecar_pids_after_pdf//$'\n'/,}" >&2 || true
  fail "unexpected PDF process remained after import/resource rejection: ${unexpected_pdf_process}"
fi

kill "${child_pid}"
wait "${child_pid}" 2>/dev/null || true
for _attempt in {1..30}; do
  if ! kill -0 "${inner_pid}" 2>/dev/null; then
    break
  fi
  sleep 0.1
done
remaining_sidecar_pids=""
for _attempt in {1..30}; do
  remaining_sidecar_pids="$(pgrep -f -- "${SIDECAR}" | sort -n || true)"
  if [[ -z "${remaining_sidecar_pids}" ]]; then
    break
  fi
  sleep 0.1
done
if [[ -n "${remaining_sidecar_pids}" ]]; then
  fail "bundled sidecar process set remained after shutdown: ${remaining_sidecar_pids//$'\n'/,}"
fi
child_pid=""

printf 'smoke-bundled-sidecar: auth, isolated PDF parsing, resource limits, and cleanup passed on loopback port %s\n' "${port}"
