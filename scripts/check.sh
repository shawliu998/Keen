#!/usr/bin/env bash
set -euo pipefail

npm run check
PYTHON_BIN="${PYTHON_BIN:-$(test -x .venv/bin/python && echo .venv/bin/python || command -v python3.11 || command -v python3)}"
"$PYTHON_BIN" -m pytest services/learning-core/tests

if command -v cargo >/dev/null 2>&1; then
  cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
else
  echo "cargo not installed; Rust tests skipped" >&2
fi
