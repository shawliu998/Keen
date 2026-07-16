# Keen Learning Core

Local-first FastAPI service for the Keen macOS sidecar. This first slice owns
demo courses, study tasks, deterministic concept mastery, durable document
ingestion, multilingual lexical retrieval, optional local embeddings with
sqlite-vec hybrid search, and optional loopback-only local chat streaming. It
does **not** OCR scanned PDFs or claim that structural citation mapping is
factual-entailment validation.

## Security boundary

- The provided launcher always binds Uvicorn to `127.0.0.1`.
- Every HTTP endpoint, including health, requires a per-process Bearer token.
- The token must contain at least 32 characters (a 128-bit random hex token is
  sufficient) and is never written to logs or SQLite.
- The desktop process generates a fresh 256-bit token and writes it once through
  the child stdin pipe, keeping it out of operating-system argv and environment
  snapshots. The Python child binds loopback port `0` itself and reports the
  kernel-assigned port through its inherited stdout pipe, avoiding a
  release-and-rebind race.
- A 0600 advisory lock is held for the database lifetime. A second process
  cannot race migrations, mark an active import interrupted, or delete another
  process's temporary upload.
- Uploaded file names are display metadata only. Stored paths are generated
  from a SHA-256 digest beneath the settings-controlled documents directory
  (by default, `<database-parent>/documents`). Client-provided paths are never
  used for filesystem access.
- Authentication is checked by an ASGI guard before an unauthorized request
  body is consumed. Document-import requests have a bounded multipart envelope
  and the accepted upload is copied and hashed incrementally with a 25 MiB
  default file limit. The service checks the extension, declared MIME type, PDF
  signature or UTF-8 text content, and removes temporary files after success or
  failure.
- PDF parsing runs in a spawned worker with a 6-second wall budget, 5-second CPU
  limit, 384 MiB memory budget, 2,000-page ceiling, 12 Mi-character extracted
  text ceiling, and 12,000-chunk ceiling. On macOS the parent samples the
  worker tree's resident memory and fails closed if that monitor is repeatedly
  unavailable; other Unix platforms apply kernel address/data limits. This
  avoids treating PyInstaller's sparse macOS virtual mappings as real memory.
  Each worker is isolated in its own process group, watches the reliable
  multiprocessing parent sentinel, and arms an independent wall timer; parent
  death or timeout kills the full worker group. A limit failure is persisted
  with an explicit retry message while the long-lived API process remains
  healthy.
- CORS is restricted to `tauri://localhost`, `http://tauri.localhost`, and the
  development origin `http://127.0.0.1:1430`.

## Run locally

Python 3.11 or newer is required.

```bash
cd services/learning-core
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
TOKEN="$(python3.11 -c 'import secrets; print(secrets.token_hex(16))')"
.venv/bin/python -m app --token "$TOKEN" --port 8765 --database ./keen.db
```

The existing `--token` argument and `KEEN_SESSION_TOKEN` environment fallback
remain compatible for manual launches. The Tauri supervisor uses
`--token-stdin` and writes one newline-terminated token to the child pipe, so
the token is absent from both the operating-system argument and environment
snapshots. Optional document controls are `--documents-directory PATH` and
`--max-document-bytes NUMBER`.

Local embeddings are opt-in and all five values are required together:
`--embedding-provider`, `--embedding-base-url`, `--embedding-model`,
`--embedding-version`, and `--embedding-dimensions`. Supported providers are
`ollama` and `openai-compatible`; the URL must use `http` with an explicit
literal loopback IP and port. Provider redirects are revalidated, proxy
environment variables are ignored, and requests have I/O and total deadlines.
The Tauri supervisor forwards the equivalent non-secret `KEEN_EMBEDDING_*`
values only when the complete set validates. Cloud endpoints and API keys are
not supported.

Then call, for example:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/health
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/v1/demo-state
```

The database schema is migrated at startup. Interrupted `queued`, `parsing`, or
`chunking` imports are moved to an explicit retryable failed state, and stale
`.incoming` files are removed. Pass `--seed-demo` to insert a small, idempotent
local dataset.

## Local document retrieval

`POST /v1/documents/import` accepts multipart fields `file` and optional
`course_id`. Supported inputs are PDF (`application/pdf`), Markdown
(`text/markdown` or `text/plain`), and TXT (`text/plain`). A new import returns
HTTP 202 with a durable job; an existing SHA-256 returns HTTP 200 with
`duplicate: true`. Job status and real progress are available under
`/v1/index-jobs`; cancel, retry, deletion, restart recovery, and many-to-many
course links are persisted. Imports are claimed with an atomic SQLite
transaction so concurrent same-hash requests converge on one stored document.

`GET /v1/documents` lists imported records. `POST /v1/search` accepts
`{"query":"...","courseId":null,"limit":8}`. It normalizes once, retrieves
bounded Latin/CJK lexical and compatible vector candidates, applies RRF,
course filtering, deduplication and bounded adjacent merging, and returns
`hybrid` only when the vector channel succeeds. Other cases return
`lexical_only` with a recovery warning. `POST /v1/query` remains extractive;
when nothing matches it returns `grounded: false`, an empty citation list, and
an explicit note. Citations include document/chunk identifiers, one-based page
number, section path, and a verbatim excerpt. Document chunks also persist
normalized-text character locations. Model/version/dimensions and embedding
state are persisted separately, and incompatible vectors never mix. A model
change produces `needs-reindex`; its embedding-only job stages then atomically
promotes vectors without hiding the lexical index. PDF geometry/bounding boxes
use pdfminer character boxes aggregated into persisted line spans for standard,
unrotated pages whose CropBox equals the zero-origin MediaBox. Rotated pages,
translated boxes, custom user units, CropBox differences, and unavailable layout
data deliberately keep the real page number with `bbox: null`; Keen does not
invent a highlight. The authenticated document-content route serves only the
canonical stored PDF and supports bounded browser range requests.

Scanned or image-only PDFs are persisted with `failed` status and a recovery
message stating that OCR is unavailable. The failed input file is removed.

## Streaming contract

`POST /v1/answer/stream` returns authenticated `text/event-stream` events named
`metadata`, `retrieval`, `delta`, `citation`, `warning`, `done`, and `error`.
When an explicit loopback chat provider is configured, it performs bounded
hybrid/lexical retrieval and streams the local model. Source text is encoded as
untrusted user-context data; the model may cite only `[[source:N]]`, and the
server expands merged retrieval hits into at most ten single, current database
chunks and maps accepted indexes back to that exact metadata. The done
event says `citationValidation: structural_only`: this validates source identity,
course, chunk, page, section, and excerpt structure, not factual entailment.
Missing providers and failed/truncated generation end with an error, not a
successful offline substitute. Client disconnect cancels and closes the provider
stream. Browser Demo does not call this route.

## Parser dependency evidence

No upstream source was copied. The service uses package dependencies through
Python packaging. On 2026-07-15, the exact downloaded wheel artifacts were
inspected before adding them:

- `pypdf-6.14.2-py3-none-any.whl`, SHA-256
  `3f07891af76dc002657e04993ab9b4de81de29f9013b9761d0b7968bff12e946`.
  Its embedded `METADATA` declares `License-Expression: BSD-3-Clause`, and
  `pypdf-6.14.2.dist-info/licenses/LICENSE` contains the BSD 3-Clause terms and
  copyright beginning with Mathieu Fenniak (2006-2008).
- `pdfminer_six-20260107-py3-none-any.whl`, SHA-256
  `366585ba97e80dffa8f00cebe303d2f381884d8637af4ce422f1df3ef38111a9`,
  exact tag commit `9e1243c4ad000bf9bbe60e81fc8dde2fccc0ed3b`. Its main
  license is MIT; the exact source's separate notice for pyHanko-derived elements
  is also MIT. Both full notices are retained in `THIRD_PARTY_NOTICES.md`.
- `python_multipart-0.0.32-py3-none-any.whl`, SHA-256
  `ff6d3f776f16878c894e52e107296ffc890e913c611b1a4ec6c44e2821fe2e23`.
  Its embedded `METADATA` declares `License-Expression: Apache-2.0`, and
  `python_multipart-0.0.32.dist-info/licenses/LICENSE.txt` contains the Apache
  License 2.0.
- `sqlite_vec-0.1.9-py3-none-macosx_11_0_arm64.whl`, SHA-256
  `1d52e30513bae4cc9778ddbf6145610434081be4c3afe57cd877893bad9f6b6c`.
  The exact source tag `v0.1.9` resolves to
  `e9f598abfa0c06b328d8fe5da9c3760cce74be10` and contains MIT and Apache-2.0
  license options with no NOTICE; Keen selects MIT. The wheel carries an arm64
  `sqlite_vec/vec0.dylib` (SHA-256
  `193e480c50b59a55977d166f4aaf0e1bc8832d6963516e5950f39e4d2ce0b793`)
  but no license file. Its actual Mach-O deployment minimum is macOS 14.0,
  matching Keen's declared target rather than the wheel tag's broader claim.
  Python 3.11 load/KNN smoke passed; PyInstaller must collect this library
  explicitly.

Evidence commands used `python3 -m pip download --no-deps --only-binary=:all:`,
`shasum -a 256`, `unzip -p <wheel> '*/METADATA'`, and `unzip -p <wheel>
'*/licenses/LICENSE*'`. Distribution-level notice aggregation still belongs in
the repository-wide third-party inventory before a release.

## Test

```bash
.venv/bin/pytest
```
