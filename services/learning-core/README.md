# Keen Learning Core

Local-first FastAPI service for the Keen macOS sidecar. This first slice owns
demo courses, study tasks, concept mastery, and a deterministic streaming
answer placeholder. It does **not** call a model, ingest documents, or claim to
provide RAG yet.

## Security boundary

- The provided launcher always binds Uvicorn to `127.0.0.1`.
- Every HTTP endpoint, including health, requires a per-process Bearer token.
- The token must contain at least 32 characters (a 128-bit random hex token is
  sufficient) and is never written to logs or SQLite.
- The desktop process should generate a fresh token and choose an unused port
  for each sidecar launch.

## Run locally

Python 3.11 or newer is required.

```bash
cd services/learning-core
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
TOKEN="$(python3.11 -c 'import secrets; print(secrets.token_hex(16))')"
.venv/bin/python -m app --token "$TOKEN" --port 8765 --database ./keen.db
```

Then call, for example:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/health
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/v1/demo-state
```

The database schema is migrated at startup. Pass `--seed-demo` to insert a
small, idempotent local dataset.

## Streaming contract

`POST /v1/answer/stream` returns `text/event-stream` events named `metadata`,
`delta`, and `done`. The current answer is deliberately deterministic and has
no citations; `metadata.mode` is `offline-demo`. A future model/retrieval
adapter can replace this implementation without changing the transport.

## Test

```bash
.venv/bin/pytest
```
