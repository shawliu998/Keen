#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly PYTHON_BIN="${PYTHON_BIN:-${REPOSITORY_ROOT}/.venv/bin/python}"

fail() {
  printf 'verify-macos-dmg: error: %s\n' "$*" >&2
  exit 1
}

[[ "$#" -eq 1 ]] || fail "usage: $0 /absolute/path/to/Keen.dmg"
[[ "$1" == /* ]] || fail "DMG path must be absolute: $1"
readonly DMG_PATH="$1"

[[ -f "${DMG_PATH}" ]] || fail "DMG is missing: ${DMG_PATH}"
[[ -x "${PYTHON_BIN}" ]] || fail "repository Python is missing: ${PYTHON_BIN}"

attach_plist="$(mktemp "${TMPDIR:-/tmp}/keen-dmg-attach.XXXXXX")"
mount_point=""

cleanup() {
  if [[ -n "${mount_point}" && -d "${mount_point}" ]]; then
    hdiutil detach "${mount_point}" >/dev/null 2>&1 || hdiutil detach -force "${mount_point}" >/dev/null 2>&1 || true
  fi
  rm -f -- "${attach_plist}"
}
trap cleanup EXIT INT TERM

hdiutil verify "${DMG_PATH}" >/dev/null
hdiutil attach -readonly -nobrowse -plist "${DMG_PATH}" >"${attach_plist}"
mount_point="$(${PYTHON_BIN} - "${attach_plist}" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "rb") as source:
    payload = plistlib.load(source)
for entity in payload.get("system-entities", []):
    mount_point = entity.get("mount-point")
    if mount_point:
        print(mount_point)
        break
else:
    raise SystemExit("DMG attach result did not contain a mount point")
PY
)"

readonly APP_BUNDLE="${mount_point}/Keen.app"
readonly MAIN_BINARY="${APP_BUNDLE}/Contents/MacOS/keen-desktop"
readonly SIDECAR_BINARY="${APP_BUNDLE}/Contents/MacOS/keen-learning-core"
readonly EMBEDDED_NOTICES="${APP_BUNDLE}/Contents/Resources/THIRD_PARTY_NOTICES.md"

[[ -d "${APP_BUNDLE}" ]] || fail "mounted DMG does not contain Keen.app"
[[ -x "${MAIN_BINARY}" && -x "${SIDECAR_BINARY}" ]] || fail "mounted app executables are missing"
codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}"
cmp --silent "${REPOSITORY_ROOT}/THIRD_PARTY_NOTICES.md" "${EMBEDDED_NOTICES}" || fail "embedded third-party notices differ from the repository"

main_arches="$(lipo -archs "${MAIN_BINARY}")"
sidecar_arches="$(lipo -archs "${SIDECAR_BINARY}")"
[[ "${main_arches}" == "${sidecar_arches}" ]] || fail "main/sidecar architecture mismatch: ${main_arches} vs ${sidecar_arches}"

main_signature_details="$(codesign -dvvv "${MAIN_BINARY}" 2>&1)"
signature_details="$(codesign -dvvv "${SIDECAR_BINARY}" 2>&1)"
if [[ -n "${APPLE_SIGNING_IDENTITY:-}" && "${APPLE_SIGNING_IDENTITY}" != "-" ]]; then
  main_team="$(sed -n 's/^TeamIdentifier=//p' <<<"${main_signature_details}" | head -n 1)"
  sidecar_team="$(sed -n 's/^TeamIdentifier=//p' <<<"${signature_details}" | head -n 1)"
  [[ -n "${main_team}" && "${main_team}" != "not set" ]] || fail "Developer ID app is missing a TeamIdentifier"
  [[ "${main_team}" == "${sidecar_team}" ]] || fail "app/sidecar TeamIdentifier mismatch"
  grep -Eq '^Authority=Developer ID Application:' <<<"${main_signature_details}" || fail "app is not signed with a Developer ID Application identity"
  grep -Eq '^Authority=Developer ID Application:' <<<"${signature_details}" || fail "sidecar is not signed with a Developer ID Application identity"
  grep -Eq 'flags=.*runtime' <<<"${main_signature_details}" || fail "Developer ID app is missing hardened runtime"
  grep -Eq 'flags=.*runtime' <<<"${signature_details}" || fail "Developer ID sidecar is missing hardened runtime"
else
  if grep -Eq 'flags=.*runtime' <<<"${main_signature_details}" || grep -Eq 'flags=.*runtime' <<<"${signature_details}"; then
    fail "ad-hoc app or PyInstaller sidecar unexpectedly enables hardened runtime"
  fi
fi

"${SCRIPT_DIR}/smoke-bundled-sidecar.sh" "${APP_BUNDLE}"

printf 'verify-macos-dmg: verified %s app/sidecar on %s\n' "${main_arches}" "${mount_point}"
