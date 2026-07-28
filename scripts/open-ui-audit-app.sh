#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly AUDIT_APP="${REPOSITORY_ROOT}/apps/desktop/src-tauri/target/release/bundle/macos/Keen UI Audit.app"
readonly PLIST_PATH="${AUDIT_APP}/Contents/Info.plist"
readonly AUDIT_EXECUTABLE="${AUDIT_APP}/Contents/MacOS/keen-desktop"
readonly TAURI_CONFIG="${REPOSITORY_ROOT}/apps/desktop/src-tauri/tauri.conf.json"
readonly STARTUP_ATTEMPTS=150

fail() {
  printf 'open-ui-audit-app: error: %s\n' "$*" >&2
  exit 1
}

[[ -d "${AUDIT_APP}" ]] || fail "audit app is missing: ${AUDIT_APP}"
[[ -f "${PLIST_PATH}" ]] || fail "audit app Info.plist is missing: ${PLIST_PATH}"
[[ -x "${AUDIT_EXECUTABLE}" ]] || fail "audit app executable is missing: ${AUDIT_EXECUTABLE}"
[[ -f "${TAURI_CONFIG}" ]] || fail "Tauri config is missing: ${TAURI_CONFIG}"

display_name="$(plutil -extract CFBundleDisplayName raw "${PLIST_PATH}")"
bundle_identifier="$(plutil -extract CFBundleIdentifier raw "${PLIST_PATH}")"
bundle_executable="$(plutil -extract CFBundleExecutable raw "${PLIST_PATH}")"
version="$(plutil -extract CFBundleShortVersionString raw "${PLIST_PATH}")"
expected_version="$(node -e 'const fs = require("node:fs"); process.stdout.write(JSON.parse(fs.readFileSync(process.argv[1], "utf8")).version);' "${TAURI_CONFIG}")"

[[ "${display_name}" == "Keen UI Audit" ]] || fail "unexpected display name: ${display_name}"
[[ "${bundle_identifier}" == "com.keen.learning.ui-audit" ]] || fail "unexpected bundle identifier: ${bundle_identifier}"
[[ "${bundle_executable}" == "$(basename -- "${AUDIT_EXECUTABLE}")" ]] || fail "unexpected executable: ${bundle_executable}"
[[ -n "${version}" && "${version}" == "${expected_version}" ]] || fail "unexpected version: ${version} (expected ${expected_version})"

find_running_audit_pids() {
  local matches
  local status

  if matches="$(pgrep -f -x -- "${AUDIT_EXECUTABLE}")"; then
    printf '%s\n' "${matches}"
    return 0
  else
    status=$?
  fi
  (( status == 1 )) || fail "could not inspect the audit app process state"
}

running_pids="$(find_running_audit_pids)"
if [[ -n "${running_pids}" ]]; then
  fail "audit app is already running (PID ${running_pids//$'\n'/, }); use the native Keen UI Audit > Quit Keen UI Audit command (Command-Q) before launching it again"
fi

printf 'open-ui-audit-app: verified %s (%s, version %s)\n' \
  "${AUDIT_APP}" "${bundle_identifier}" "${version}"
open "${AUDIT_APP}" || fail "Launch Services could not open the verified audit bundle"

launched_pids=""
for (( attempt = 1; attempt <= STARTUP_ATTEMPTS; attempt += 1 )); do
  launched_pids="$(find_running_audit_pids)"
  [[ -n "${launched_pids}" ]] && break
  sleep 0.1
done

[[ -n "${launched_pids}" ]] || fail "the verified audit executable did not appear within 15 seconds"
printf 'open-ui-audit-app: launched verified audit executable (PID %s)\n' \
  "${launched_pids//$'\n'/, }"
