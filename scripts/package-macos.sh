#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly DMG_OUTPUT_DIR="${REPOSITORY_ROOT}/apps/desktop/src-tauri/target/release/bundle/dmg"

if [[ -n "${APPLE_SIGNING_IDENTITY:-}" && "${APPLE_SIGNING_IDENTITY}" != "-" ]]; then
  readonly TAURI_SIDECAR_CONFIG="src-tauri/tauri.sidecar.release.conf.json"
  printf 'package-macos: using Developer ID identity %s with hardened runtime\n' "${APPLE_SIGNING_IDENTITY}"
else
  readonly TAURI_SIDECAR_CONFIG="src-tauri/tauri.sidecar.conf.json"
  printf 'package-macos: building an ad-hoc local verification bundle without hardened runtime\n'
fi

cd -- "${REPOSITORY_ROOT}"
"${SCRIPT_DIR}/build-sidecar.sh"

npm run tauri --workspace=@keen/desktop -- build \
  --bundles app \
  --config "${TAURI_SIDECAR_CONFIG}"

"${SCRIPT_DIR}/smoke-bundled-sidecar.sh"

mkdir -p -- "${DMG_OUTPUT_DIR}"
shopt -s nullglob
old_dmg_paths=("${DMG_OUTPUT_DIR}"/*.dmg)
shopt -u nullglob
if (( ${#old_dmg_paths[@]} > 0 )); then
  rm -f -- "${old_dmg_paths[@]}"
fi

CI=true npm run tauri --workspace=@keen/desktop -- build \
  --bundles dmg \
  --config "${TAURI_SIDECAR_CONFIG}"

shopt -s nullglob
dmg_paths=("${DMG_OUTPUT_DIR}"/*.dmg)
shopt -u nullglob
if (( ${#dmg_paths[@]} != 1 )); then
  printf 'package-macos: error: expected exactly one newly built DMG in %s, found %d\n' \
    "${DMG_OUTPUT_DIR}" "${#dmg_paths[@]}" >&2
  exit 1
fi

readonly DMG_PATH="${dmg_paths[0]}"
[[ -f "${DMG_PATH}" ]] || {
  printf 'package-macos: error: generated DMG is not a regular file: %s\n' "${DMG_PATH}" >&2
  exit 1
}

"${SCRIPT_DIR}/verify-macos-dmg.sh" "${DMG_PATH}"
