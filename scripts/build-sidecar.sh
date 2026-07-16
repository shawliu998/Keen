#!/usr/bin/env bash

set -Eeuo pipefail

readonly PYINSTALLER_VERSION="6.21.0"
readonly PYINSTALLER_HOOKS_VERSION="2026.6"
readonly PIP_VERSION="26.1.2"
readonly SQLITE_VEC_VERSION="0.1.9"
readonly PDFMINER_VERSION="20260107"
readonly CRYPTOGRAPHY_VERSION="49.0.0"
readonly CHARSET_NORMALIZER_VERSION="3.4.9"
readonly CFFI_VERSION="2.1.0"
readonly PYCPARSER_VERSION="3.0"
readonly HTTPX_VERSION="0.28.1"
readonly PYPDF_VERSION="6.14.2"
readonly PYTHON_MULTIPART_VERSION="0.0.32"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly SERVICE_ROOT="${REPOSITORY_ROOT}/services/learning-core"
readonly LOCK_FILE="${SERVICE_ROOT}/pylock.toml"
readonly TAURI_ROOT="${REPOSITORY_ROOT}/apps/desktop/src-tauri"
readonly ENTRYPOINT="${TAURI_ROOT}/sidecar/entrypoint.py"
readonly BUILD_ROOT="${TAURI_ROOT}/target/sidecar-build"
readonly FREEZE_VENV="${BUILD_ROOT}/venv"
readonly FREEZE_PYTHON="${FREEZE_VENV}/bin/python"
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

[[ "$#" -le 1 ]] || fail "usage: $0 [--preflight-only]"
[[ "$#" -eq 0 || "$1" == "--preflight-only" ]] || fail "unknown argument: $1"

[[ -x "${PYTHON_BIN}" ]] || fail "repository Python is missing at ${PYTHON_BIN}; create .venv with Python 3.11+ first"
[[ -f "${ENTRYPOINT}" ]] || fail "fixed PyInstaller entry point is missing: ${ENTRYPOINT}"
[[ -d "${SERVICE_ROOT}/app" ]] || fail "learning-core source is missing: ${SERVICE_ROOT}/app"
[[ -d "${SERVICE_ROOT}/migrations" ]] || fail "learning-core migrations are missing"
[[ -d "${SERVICE_ROOT}/seeds" ]] || fail "learning-core seeds are missing"
[[ -f "${SERVICE_ROOT}/migrations/008_pdf_geometry.sql" ]] || fail "migration 008_pdf_geometry.sql is missing"
[[ -f "${LOCK_FILE}" ]] || fail "learning-core runtime lock is missing: ${LOCK_FILE}"

python_version="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${python_version}" != "3.11" ]]; then
  fail "the locked sidecar environment requires Python 3.11; ${PYTHON_BIN} reports ${python_version}"
fi
platform="$(${PYTHON_BIN} -c 'import platform; print(f"{platform.system()}:{platform.machine()}")')"
[[ "${platform}" == "Darwin:arm64" ]] || fail "the runtime lock targets macOS arm64; ${PYTHON_BIN} reports ${platform}"

if ! "${PYTHON_BIN}" - "${LOCK_FILE}" \
  "${SQLITE_VEC_VERSION}" \
  "${PDFMINER_VERSION}" \
  "${CRYPTOGRAPHY_VERSION}" \
  "${CHARSET_NORMALIZER_VERSION}" \
  "${CFFI_VERSION}" \
  "${PYCPARSER_VERSION}" \
  "${HTTPX_VERSION}" \
  "${PYPDF_VERSION}" \
  "${PYTHON_MULTIPART_VERSION}" <<'PY'
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

lock_path = Path(sys.argv[1])
lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
if lock.get("lock-version") != "1.0":
    raise SystemExit("pylock.toml must use PEP 751 lock-version 1.0")
packages = lock.get("packages")
if not isinstance(packages, list) or not packages:
    raise SystemExit("pylock.toml must contain locked runtime packages")

versions: dict[str, str] = {}
for package in packages:
    if not isinstance(package, dict):
        raise SystemExit("pylock.toml contains an invalid package record")
    name = package.get("name")
    package_version = package.get("version")
    if not isinstance(name, str) or not isinstance(package_version, str):
        raise SystemExit("every locked package must have a name and version")
    normalized_name = re.sub(r"[-_.]+", "-", name).lower()
    if normalized_name == "keen-learning-core" or "directory" in package:
        raise SystemExit("pylock.toml must not contain the local learning-core package")
    if normalized_name in versions:
        raise SystemExit(f"duplicate locked package: {normalized_name}")
    versions[normalized_name] = package_version
    wheels = package.get("wheels")
    if not isinstance(wheels, list) or not wheels:
        raise SystemExit(f"{name} must be locked to at least one wheel")
    if "sdists" in package or "vcs" in package or "archive" in package:
        raise SystemExit(f"{name} must be supplied only by locked wheels")
    for wheel in wheels:
        url = wheel.get("url") if isinstance(wheel, dict) else None
        digest = wheel.get("hashes", {}).get("sha256") if isinstance(wheel, dict) else None
        parsed = urlsplit(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
            raise SystemExit(f"{name} wheel must use an explicit files.pythonhosted.org URL")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise SystemExit(f"{name} wheel must have a SHA-256 hash")

expected = {
    "sqlite-vec": sys.argv[2],
    "pdfminer-six": sys.argv[3],
    "cryptography": sys.argv[4],
    "charset-normalizer": sys.argv[5],
    "cffi": sys.argv[6],
    "pycparser": sys.argv[7],
    "httpx": sys.argv[8],
    "pypdf": sys.argv[9],
    "python-multipart": sys.argv[10],
}
for name, required in expected.items():
    if versions.get(name) != required:
        raise SystemExit(
            f"pylock.toml must pin {name}=={required}; found {versions.get(name)!r}"
        )
PY
then
  fail "learning-core runtime lock validation failed"
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

if [[ "${1:-}" == "--preflight-only" ]]; then
  printf 'build-sidecar: preflight passed for Python %s and %s\n' "${python_version}" "${target_triple}"
  exit 0
fi

rm -rf -- "${BUILD_ROOT}"
mkdir -p -- "${DIST_ROOT}" "${SPEC_ROOT}" "${WORK_ROOT}" "${OUTPUT_ROOT}"

printf 'build-sidecar: creating isolated Python %s freeze environment from %s\n' "${python_version}" "${LOCK_FILE}"
"${PYTHON_BIN}" -m venv "${FREEZE_VENV}"
"${FREEZE_PYTHON}" -m pip install --disable-pip-version-check "pip==${PIP_VERSION}"
"${FREEZE_PYTHON}" -m pip install --disable-pip-version-check --only-binary=:all: \
  "pyinstaller==${PYINSTALLER_VERSION}" \
  "pyinstaller-hooks-contrib==${PYINSTALLER_HOOKS_VERSION}"
"${FREEZE_PYTHON}" -m pip install --disable-pip-version-check -r "${LOCK_FILE}"
"${FREEZE_PYTHON}" -m pip install --disable-pip-version-check --no-deps "${SERVICE_ROOT}"
"${FREEZE_PYTHON}" -m pip check

if ! "${FREEZE_PYTHON}" - "${LOCK_FILE}" \
  "${PYINSTALLER_VERSION}" "${PYINSTALLER_HOOKS_VERSION}" <<'PY'
import importlib
import re
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

lock = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for package in lock["packages"]:
    name = re.sub(r"[-_.]+", "-", package["name"]).lower()
    installed = version(name)
    if installed != package["version"]:
        raise SystemExit(
            f"locked runtime mismatch for {name}: expected {package['version']}, found {installed}"
        )

expected = {
    "keen-learning-core": "0.1.0",
    "pyinstaller": sys.argv[2],
    "pyinstaller-hooks-contrib": sys.argv[3],
}
for name, required in expected.items():
    installed = version(name)
    if installed != required:
        raise SystemExit(f"{name} {required} is required; found {installed}")

for module in (
    "app.__main__",
    "app.answer_service",
    "app.local_chat_providers",
    "app.local_providers",
    "pdfminer.high_level",
    "pdfminer.layout",
    "cryptography.hazmat.bindings._rust",
    "charset_normalizer",
    "httpx",
    "httpcore",
    "anyio",
    "certifi",
    "idna",
    "h11",
    "sqlite_vec",
):
    importlib.import_module(module)

import sqlite_vec

sqlite_vec_library = Path(sqlite_vec.loadable_path()).with_suffix(".dylib")
if not sqlite_vec_library.is_file():
    raise SystemExit("sqlite-vec native library is missing from the freeze environment")
PY
then
  fail "isolated freeze environment does not match the runtime lock"
fi

printf 'build-sidecar: building %s with PyInstaller %s for %s\n' "${SIDECAR_NAME}" "${PYINSTALLER_VERSION}" "${target_triple}"
pyinstaller_command=(
  "${FREEZE_PYTHON}" -m PyInstaller
  --clean
  --noconfirm
  --onefile
  --name "${SIDECAR_NAME}"
  --distpath "${DIST_ROOT}"
  --specpath "${SPEC_ROOT}"
  --workpath "${WORK_ROOT}"
  --collect-submodules uvicorn
  --collect-submodules charset_normalizer
  --collect-submodules cryptography
  --collect-submodules cffi
  --collect-data pdfminer
  --collect-binaries cryptography
  --collect-binaries charset_normalizer
  --collect-binaries sqlite_vec
  --hidden-import app.answer_service
  --hidden-import app.local_chat_providers
  --hidden-import app.local_providers
  --hidden-import cryptography.hazmat.bindings._rust
  --hidden-import httpx
  --hidden-import httpcore
  --hidden-import anyio
  --hidden-import certifi
  --hidden-import idna
  --hidden-import h11
  --hidden-import cffi
  --hidden-import pycparser
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
