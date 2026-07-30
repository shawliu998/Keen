#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly PYTHON_BIN="${PYTHON_BIN:-${REPOSITORY_ROOT}/.venv/bin/python}"
readonly VALIDATOR="${SCRIPT_DIR}/verify-sidecar-migrations.py"
readonly TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/keen-sidecar-migrations.XXXXXX")"

cleanup() {
  rm -rf -- "${TEST_ROOT}"
}
trap cleanup EXIT

fail() {
  printf 'test-sidecar-migration-preflight: error: %s\n' "$*" >&2
  exit 1
}

[[ -x "${PYTHON_BIN}" ]] || fail "Python is missing at ${PYTHON_BIN}"
[[ -f "${VALIDATOR}" ]] || fail "validator is missing: ${VALIDATOR}"

"${PYTHON_BIN}" "${VALIDATOR}" \
  "${REPOSITORY_ROOT}/services/learning-core/migrations" --minimum-version 21

create_migrations() {
  local destination="$1"
  shift
  mkdir -p -- "${destination}"
  local version
  for version in "$@"; do
    : > "${destination}/${version}_migration.sql"
  done
}

expect_failure() {
  if "$@" >/dev/null 2>&1; then
    fail "command unexpectedly succeeded: $*"
  fi
}

create_migrations "${TEST_ROOT}/gap" 001 003 020
expect_failure "${PYTHON_BIN}" "${VALIDATOR}" "${TEST_ROOT}/gap" --minimum-version 20

create_migrations "${TEST_ROOT}/below-minimum" 001 002 003
expect_failure "${PYTHON_BIN}" "${VALIDATOR}" \
  "${TEST_ROOT}/below-minimum" --minimum-version 21

create_migrations "${TEST_ROOT}/missing-current-tail" 001 002 003 004 005 006 007 008 009 010 011 012 013 014 015 016 017 018 019 020
expect_failure "${PYTHON_BIN}" "${VALIDATOR}" \
  "${TEST_ROOT}/missing-current-tail" --minimum-version 21

create_migrations "${TEST_ROOT}/invalid-name" 001 002 003 004 005 006 007 008 009 010 011 012 013 014 015 016 017 018 019 020
: > "${TEST_ROOT}/invalid-name/021 bad.sql"
expect_failure "${PYTHON_BIN}" "${VALIDATOR}" \
  "${TEST_ROOT}/invalid-name" --minimum-version 21

printf 'test-sidecar-migration-preflight: passed\n'
