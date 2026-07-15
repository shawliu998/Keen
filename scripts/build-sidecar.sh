#!/usr/bin/env bash

set -Eeuo pipefail

readonly PYINSTALLER_VERSION="6.21.0"
readonly PYINSTALLER_HOOKS_VERSION="2026.6"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly SERVICE_ROOT="${REPOSITORY_ROOT}/services/learning-core"
readonly TAURI_ROOT="${REPOSITORY_ROOT}/apps/desktop/src-tauri"
readonly ENTRYPOINT="${TAURI_ROOT}/sidecar/entrypoint.py"
readonly BUILD_ROOT="${TAURI_ROOT}/target/sidecar-build"
readonly DIST_ROOT="${BUILD_ROOT}/dist"
readonly SPEC_ROOT="${BUILD_ROOT}/spec"
readonly WORK_ROOT="${BUILD_ROOT}/work"
readonly OUTPUT_ROOT="${TAURI_ROOT}/binaries"
readonly SIDECAR_NAME="keen-learning-core"
readonly PYTHON_BIN="${PYTHON_BIN:-${REPOSITORY_ROOT}/.venv/bin/python}"
readonly RUSTC_BIN="${RUSTC_BIN:-rustc}"

fail() {
  printf 'build-sidecar: error: %s\n' "$*" >&2
  exit 1
}

[[ -x "${PYTHON_BIN}" ]] || fail "repository Python is missing at ${PYTHON_BIN}; create .venv with Python 3.11+ first"
[[ -f "${ENTRYPOINT}" ]] || fail "fixed PyInstaller entry point is missing: ${ENTRYPOINT}"
[[ -d "${SERVICE_ROOT}/app" ]] || fail "learning-core source is missing: ${SERVICE_ROOT}/app"
[[ -d "${SERVICE_ROOT}/migrations" ]] || fail "learning-core migrations are missing"
[[ -d "${SERVICE_ROOT}/seeds" ]] || fail "learning-core seeds are missing"

python_version="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python_major="${python_version%%.*}"
python_minor="${python_version#*.}"
if (( python_major != 3 || python_minor < 11 || python_minor >= 15 )); then
  fail "Python 3.11-3.14 is required; ${PYTHON_BIN} reports ${python_version}"
fi

if ! installed_pyinstaller="$(${PYTHON_BIN} -c 'import PyInstaller; print(PyInstaller.__version__)' 2>/dev/null)"; then
  fail "PyInstaller ${PYINSTALLER_VERSION} is required in the repository .venv; install it with: ${PYTHON_BIN} -m pip install 'pyinstaller==${PYINSTALLER_VERSION}'"
fi
if [[ "${installed_pyinstaller}" != "${PYINSTALLER_VERSION}" ]]; then
  fail "PyInstaller ${PYINSTALLER_VERSION} is required for repeatable builds; found ${installed_pyinstaller}"
fi
installed_hooks="$(${PYTHON_BIN} -c 'from importlib.metadata import version; print(version("pyinstaller-hooks-contrib"))')"
if [[ "${installed_hooks}" != "${PYINSTALLER_HOOKS_VERSION}" ]]; then
  fail "pyinstaller-hooks-contrib ${PYINSTALLER_HOOKS_VERSION} is required for repeatable builds; found ${installed_hooks}"
fi
if ! PYTHONPATH="${SERVICE_ROOT}" "${PYTHON_BIN}" -c 'import app.__main__' 2>/dev/null; then
  fail "learning-core runtime dependencies are incomplete; install them with: ${PYTHON_BIN} -m pip install -e '${SERVICE_ROOT}'"
fi

host_triple="$(${RUSTC_BIN} -vV | awk '/^host: / { print $2 }')"
[[ -n "${host_triple}" ]] || fail "could not determine the Rust host target triple"
target_triple="${TARGET_TRIPLE:-${host_triple}}"
case "${target_triple}" in
  *[!A-Za-z0-9_.-]*|'') fail "invalid target triple: ${target_triple}" ;;
esac
[[ "${target_triple}" == *-apple-darwin ]] || fail "Keen sidecar packaging currently supports macOS targets only"
if [[ "${target_triple}" != "${host_triple}" ]]; then
  fail "PyInstaller cannot cross-compile from ${host_triple} to ${target_triple}; run this script on the target architecture"
fi

readonly OUTPUT_PATH="${OUTPUT_ROOT}/${SIDECAR_NAME}-${target_triple}"

rm -rf -- "${BUILD_ROOT}"
mkdir -p -- "${DIST_ROOT}" "${SPEC_ROOT}" "${WORK_ROOT}" "${OUTPUT_ROOT}"

printf 'build-sidecar: building %s with PyInstaller %s for %s\n' "${SIDECAR_NAME}" "${PYINSTALLER_VERSION}" "${target_triple}"
pyinstaller_command=(
  "${PYTHON_BIN}" -m PyInstaller
  --clean
  --noconfirm
  --onefile
  --name "${SIDECAR_NAME}"
  --distpath "${DIST_ROOT}"
  --specpath "${SPEC_ROOT}"
  --workpath "${WORK_ROOT}"
  --paths "${SERVICE_ROOT}"
  --collect-submodules uvicorn
  --add-data "${SERVICE_ROOT}/migrations:migrations"
  --add-data "${SERVICE_ROOT}/seeds:seeds"
)
if [[ -n "${APPLE_SIGNING_IDENTITY:-}" && "${APPLE_SIGNING_IDENTITY}" != "-" ]]; then
  pyinstaller_command+=(--codesign-identity "${APPLE_SIGNING_IDENTITY}")
fi
pyinstaller_command+=("${ENTRYPOINT}")
"${pyinstaller_command[@]}"

[[ -x "${DIST_ROOT}/${SIDECAR_NAME}" ]] || fail "PyInstaller completed without producing ${DIST_ROOT}/${SIDECAR_NAME}"
install -m 0755 "${DIST_ROOT}/${SIDECAR_NAME}" "${OUTPUT_PATH}"
"${OUTPUT_PATH}" --help >/dev/null || fail "the packaged sidecar failed its --help smoke test"

printf 'build-sidecar: wrote %s\n' "${OUTPUT_PATH}"
if [[ -n "${APPLE_SIGNING_IDENTITY:-}" && "${APPLE_SIGNING_IDENTITY}" != "-" ]]; then
  printf 'build-sidecar: bundle with the matching Developer ID release config\n'
else
  printf 'build-sidecar: bundle with the ad-hoc local verification config\n'
fi
