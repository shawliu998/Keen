# Sidecar and Local RAG Hardening Plan

Date: 2026-07-16
Branch: `codex/milestone-sidecar-rag`

## Status and evidence contract

This plan uses `not started`, `in progress`, `blocked`, `implemented / unverified`, and `verified`. A capability is verified only after the named test or artifact exists. The existing `/v1/query` response is an FTS5-backed extractive response, not model-backed RAG.

Baseline recorded before this round's source changes:

- `npm run lint && npm run typecheck && npm test && npm run build`: passed; 5 Vitest files / 35 tests, zero failed or skipped, and the production build completed.
- `PYTHONPATH=services/learning-core .venv/bin/python -m pytest services/learning-core/tests`: 47 passed, zero failed or skipped, with one Starlette deprecation warning.
- `cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check && cargo clippy --manifest-path apps/desktop/src-tauri/Cargo.toml --all-targets -- -D warnings && cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`: formatting and clippy passed; 19 Rust tests passed, zero failed or skipped.
- `git status --short --branch`: the branch matched `codex/milestone-sidecar-rag`, tracked its remote, and the worktree was clean.

## Current real capability

- Rust launches one authenticated Python sidecar bound by the child to atomic loopback port `0`, passes a Rust-generated 256-bit token once through stdin, confines the advertised base URL to `127.0.0.1`, isolates the child process group, performs health supervision with one automatic restart, and cleans generation-scoped private temporary directories after group exit.
- The Python FastAPI service authenticates routes before request-body parsing, holds a database instance lock, applies versioned SQLite migrations, uses private database/document directories, and exposes health, courses, tasks, deterministic mastery, documents, lexical/hybrid retrieval, extractive query, and model-backed answer streaming when an explicit loopback chat provider is configured.
- PDF, Markdown, and text imports validate metadata and content, copy/hash to bounded content-addressed storage, return a durable job, and run bounded parsing plus page-aware lexical indexing in one cancellable worker. Startup recovery, retry/delete, and conservative storage reconciliation are implemented.
- Documents use an authoritative many-to-many course relation. Latin `unicode61` and CJK `trigram` lexical channels are routed by script and combined with deterministic RRF for mixed queries.
- The live Tauri UI discovers the authenticated sidecar and reads learning/document/job/course state. Knowledge Base exposes real progress and course links. Conversation consumes the authenticated answer stream in Tauri mode. Browser Demo uses a clearly labeled fixed transcript and makes no sidecar, retrieval, or model request.
- Development and production have distinct Tauri identifiers; seed is explicit-only; startup requires strict PORT/PHASE/READY/authenticated-health progression; manual Retry can restart the supervisor; and request guarding counts streaming body chunks without replaying the full upload.

## Problems addressed in this round

1. Development data can contaminate the future production Application Support database.
2. Retry does not recover a supervisor whose automatic restart budget is exhausted.
3. A port announcement is incorrectly treated as sufficient startup progress while migration and recovery are still running.
4. Document parsing/indexing is synchronous, not durably cancellable, and reports no real background progress.
5. Multipart request guarding duplicates the complete request body in memory.
6. A document has only one legacy course link and duplicate content cannot be safely shared across courses.
7. Interrupted/failed imports have incomplete retry, deletion, and storage-reconciliation behavior.
8. `unicode61` does not provide adequate continuous-CJK or mixed Chinese/English retrieval.
9. There is no verified embedding/vector backend, hybrid retrieval, local-provider adapter, generated answer, or structural citation validation.
10. Conversation does not consume live SSE, propagate cancellation through the model request, or render verified citations.
11. PDF chunks do not preserve sufficient geometry for reliable page highlights.
12. Main-window destruction currently risks being conflated with application exit.

## Ordered migration and implementation gates

### Gate 1 — data and lifecycle safety (`verified`)

- Add a development Tauri config with `com.keen.learning.dev` and a visible Keen Dev title; retain `com.keen.learning` for production so Tauri derives distinct standard data/cache directories.
- Pass `--seed-demo` only when `KEEN_SEED_DEMO=1` or when tests explicitly construct that argument. Browser Demo remains memory-only.
- Add strict `PORT`, startup `PHASE`, and `READY` child events. Rust independently waits for port (10 s), ready (90 s), and authenticated health (10 s), and ignores stale-generation or malformed events.
- Add idempotent manual restart/diagnostics commands. A user restart must stop and reap the old process group, remove only its generation directory, rotate the token, reset the one-shot automatic budget, and refuse work during application exit.
- Keep the sidecar alive when the main window closes; shut it down only during real application exit and support macOS reopen without a second sidecar.
- Exit criterion: the complete Rust, Python, and TypeScript baseline commands pass with the added isolation, slow-start, restart, generation, shutdown, and UI-state tests.

Gate 1 evidence recorded on 2026-07-16:

- Frontend lint and strict typecheck passed; Vitest passed 5 files / 53 tests; the Vite production build passed.
- Python pytest passed 57 tests with one existing Starlette deprecation warning; Python 3.11 `compileall` passed. Ruff is not installed or declared in this repository's current virtual environment, so no Ruff result is claimed by the consolidated gate.
- Rust format and strict clippy passed; 33 tests passed. After a full-suite failure exposed a live orphan process at a stopped-wrapper/reparent boundary, force termination was changed to reassert SIGKILL against the same validated process group until ESRCH or the existing deadline. The affected test passed 100 consecutive runs and the full 33-test suite passed 50 consecutive runs before the final consolidated pass.
- Development/production identifiers were parsed as `com.keen.learning.dev` and `com.keen.learning`; root Tauri dev/build command dispatch and `git diff --check` passed.
- GUI Dock reopen, a real WebView IPC restart E2E, bundled READY smoke, `.app`, and `.dmg` remain unverified and are not part of this Gate 1 claim.

### Gate 2 — durable asynchronous document jobs (`verified`)

- Migration `004_document_index_jobs.sql` will add persisted jobs and their lifecycle timestamps, stage, progress, cancellation request, error, and worker generation. Running jobs are marked `interrupted` at controlled shutdown/startup recovery and remain explicitly retryable.
- Import will validate, stream-copy/hash, atomically store, create the document/version/job transactionally, and return `202` before parsing/indexing. One controlled worker processes one heavyweight PDF at a time.
- Add polling, cancel, retry, and delete APIs. Cancellation is checked at page, chunk, and embedding-batch boundaries and must terminate/reap the PDF worker.
- Replace the fixed six-second parse limit with configurable file/page/character/chunk/RSS/no-progress/total-task limits. A 100-page generated fixture is evidence only for that fixture; no 1,000-page support claim follows.
- Replace complete-body replay with a streaming counting `receive` wrapper while retaining pre-body auth, Content-Length fast rejection, an actual byte cap, disconnect propagation, and the second copy/hash size boundary.
- Reconcile missing referenced files, orphan files, stale `.incoming` and generation directories, old running jobs, and duplicate-hash anomalies. Unknown orphan files are quarantined before deletion.
- Exit criterion: 202, real stage progress, cancellation, no surviving worker, interrupted retry, reconciliation, streaming/chunked limit, and disconnect tests pass.

Gate 2 evidence recorded on 2026-07-16:

- Migration `004_document_index_jobs.sql` adds durable jobs, active-job uniqueness, and backfills existing indexed/failed/interrupted document states without deleting legacy data.
- Import returns `202` after bounded validation/hash/atomic storage and durable job creation; a single persisted worker reports real parse/chunk/lexical/finalize progress. Cancel, retry, delete, queued resume, running interruption, missing-source repair/delete, quarantine recovery, and partial-chunk invisibility are automated.
- Cancel/finalize and delete/retry paths use transactional CAS and a fixed lock order. PDF cancellation terminates and repeatedly reaps the isolated process group; no UI-only cancellation claim is made.
- The request guard streams counted ASGI chunks instead of retaining/replaying the complete multipart body, preserves pre-body auth, rejects invalid/oversized declared lengths before reads, stops on measured overflow, and propagates disconnect.
- Consolidated verification passed: Python 3.11 pytest 90/90 with one existing Starlette warning and compileall; frontend lint/typecheck/build and 69/69 tests; Rust fmt/clippy and 33/33 tests; `git diff --check`. Ruff also passed in the local learning-core Python 3.14 environment, but Ruff is not installed/configured in the root Python 3.11 virtual environment. MyPy is not installed.

### Gate 3 — course links and multilingual lexical retrieval (`verified`)

- Migration `003_course_documents.sql` adds the many-to-many table and backfills every non-null legacy `documents.course_id` without removing the legacy column.
- Importing the same hash links the existing document/version/file to an additional course, returns `duplicate`/`linked`, and performs no second parse or copy. Unlinking one course does not delete a document still linked elsewhere; document deletion remains a separate explicit action.
- Migration `005_cjk_fts.sql` adds a CJK lexical index only after the bundled SQLite trigram tokenizer is feature-tested. Latin queries use `unicode61`; CJK or mixed queries use the applicable indexes and deterministic reciprocal-rank fusion, followed by course filtering and chunk deduplication.
- Knowledge Base uses real `courseIds`, course selection, job-derived status/progress, and available cancel/retry/delete/link actions.
- Exit criterion: two-course same-hash storage/link tests and semantic ranking fixtures for Chinese, English, and mixed queries pass.

Gate 3 evidence recorded on 2026-07-16:

- Migration `003_course_documents.sql` backfills legacy links and makes `course_documents` authoritative while retaining the legacy column. Import/link/unlink responses expose stable `courseIds` and truthful `duplicate`/`linked` semantics; unlinking the final course retains an unscoped document and its index.
- Same-hash import into two courses is covered through the authenticated API: one document, version, job, content-addressed stored file, and two links are asserted; both course filters retrieve it, and unlinking either relation does not delete the document.
- Migration `005_cjk_fts.sql` adds and rebuilds an external-content trigram index with insert/update/delete triggers. Runtime probes passed under Python 3.11 / SQLite 3.53.1 and the service Python 3.14 / SQLite 3.53.3 environment.
- CJK queries use bounded overlapping three-character shingles rather than an entire-sentence phrase. The five required Chinese, English, and mixed fixtures ranked the relevant chunk first; mixed results use RRF and chunk deduplication.
- Knowledge Base uses live course names, import selection, all/unlinked/course filters, multi-course display, link/unlink, and partial course-state errors. Browser Demo equivalents remain memory-only and are tested for zero invoke/fetch.
- Consolidated verification passed: Python 3.11 pytest 121/121 with one existing Starlette warning and compileall; local Python 3.14 Ruff; frontend lint, strict typecheck, 72/72 Vitest tests, and production build; Rust fmt, strict clippy, and 33/33 tests; `git diff --check`. A cancel/claim race exposed during the gate was fixed by moving the read behind `BEGIN IMMEDIATE`; its race test passed 17/17 in five additional consecutive runs.

### Gate 4 — local-only hybrid retrieval (`verified`)

- Before adding a dependency, verify its exact version, license/notice, Apple Silicon and Python 3.11 support, PyInstaller freezing behavior, native-library payload, and migration/loading behavior; update the open-source inventory and notices first.
- Introduce provider-neutral `EmbeddingProvider` and `VectorStore` interfaces. Prefer `sqlite-vec` only if the packaged extension is stable; do not write a custom ANN implementation.
- Allow only explicit loopback OpenAI-compatible or Ollama endpoints, reject wildcard/file/external endpoints and non-loopback redirects, and propagate timeout/cancellation. No cloud API keys are in scope.
- Persist model/version/dimension metadata. Never mix incompatible vectors; model change produces `needs-reindex`. Embedding failure preserves a truthful `indexed-lexical` state.
- Retrieval normalizes the query, obtains bounded lexical/vector candidates, applies RRF, course filtering, deduplication and adjacent merging, and returns the top bounded context.

Gate 4 evidence recorded on 2026-07-16:

- `sqlite-vec==0.1.9` and `httpx==0.28.1` were selected only after exact tag/wheel/license/native/Python 3.11/PyInstaller review; hashes, notices, macOS deployment evidence, and remaining lock/notice work are recorded in the inventory.
- Loopback-only Ollama/OpenAI-compatible embedding adapters reject DNS names, wildcard/external/file/HTTPS endpoints, unsafe authorities and non-loopback redirects; proxy inheritance is disabled and response size, redirect count, I/O timeouts, total wall time and cancellation are bounded.
- Migrations 006/007 persist immutable model identity, dimension-checked cosine-safe float32 vectors, embedding state, model-pinned embedding-only jobs and isolated staging. Complete vectors are promoted atomically; cancellation/failure/interruption removes staging while chunks, FTS and prior-model vectors remain available.
- Search uses one NFKC-normalized query, offloads SQLite work from the request event loop, takes up to 30 lexical and 30 ready/complete compatible vector candidates, and applies RRF/course filtering/deduplication plus a three-chunk/12,000-character adjacent-merge cap. Unavailable/incompatible paths return explicit `lexical_only` warnings.
- Knowledge Base and the strict Pydantic/Zod client expose provider-missing/failure, indexed-lexical, indexed-hybrid, embedding, cancellation/interruption and needs-reindex states. Reindex creates the durable embedding-only job; Browser Demo makes no sidecar/provider request.
- Independent consolidated verification passed: Python 3.11 pytest 260/260 with one existing Starlette warning and compileall; Ruff; frontend ESLint, strict typecheck, 79/79 Vitest tests and production build (1,678 modules); Rust fmt, strict clippy and 34/34 tests; `git diff --check`.
- Residual non-blocking risk: vector ranking is an exact scalar cosine scan. It is offloaded from the event loop, but a cancelled coroutine does not yet interrupt an already-running SQLite scan, and large-index performance is not benchmarked. Frozen arm64 loading and the CPython 3.11/macOS arm64 runtime lock are now verified in Gate 7; complete notices, other targets, and large-index performance remain open.

### Gate 5 — model answer and live Conversation (`verified`)

- Add `/v1/answer/stream` with metadata, retrieval, delta, citation, warning, done, and error SSE events.
- Put untrusted source text only inside structured user-context boundaries. The system instruction states that source instructions are data, cannot alter behavior or invoke tools, and unsupported answers must disclose uncertainty.
- The model may emit only source indexes. The server maps valid indexes to retrieval-owned chunk/document/course/page metadata; invented source indexes or page numbers are rejected. Structural validation is not claimed as factual-entailment validation.
- Tauri Conversation consumes SSE incrementally, persists drafts, supports stop/retry/edit-resend, propagates disconnect cancellation into the provider request, and renders lexical-only/provider/restart/network/citation states. Browser Demo remains explicitly non-live.

Gate 5 evidence recorded on 2026-07-16:

- Explicit all-or-none chat configuration supports loopback-only OpenAI-compatible SSE and Ollama NDJSON endpoints. Proxy inheritance is disabled; redirects are revalidated; media type, UTF-8, line length, response size, I/O timeout, total timeout, configured model identity when supplied, and required terminal markers are enforced.
- `/v1/answer/stream` emits strict camelCase metadata, retrieval, delta, citation, warning, done, and error events. Source records are JSON-encoded only in the user message and are declared untrusted by the fixed system instruction. The model emits only `[[source:N]]`; the server removes invalid markers and remaps accepted indexes through current database-owned chunk, document, course, page, section, and excerpt data.
- `grounded` means that at least one citation passed structural mapping. The stream explicitly reports `citationValidation: structural_only`; no factual-entailment validation is claimed. Missing providers, failed retrieval/generation, lexical-only retrieval, no sources, invalid markers, disconnects, and client cancellation do not become successful completion.
- The frontend parser requires authenticated `text/event-stream`, bounded valid UTF-8/JSON, one metadata event, ordered retrieval/deltas/warnings/citations, one terminal event, matching run/conversation/limit metadata, unique source/chunk/citation identities, and citation fields/excerpts that map to the retrieval event. Browser Demo tests assert zero `fetch` and zero Tauri `invoke`.
- Independent monitoring verification passed Python 3.11 pytest 276/276 with one existing Starlette warning and the Gate 5 frontend subset 45/45. The execution windows also passed Ruff/format/compileall, frontend ESLint/strict typecheck/full 93/93 tests/production build (1,678 modules), Rust fmt/strict clippy/35 tests, and `git diff --check`.
- Conversation final-state persistence is not implemented, so cancellation has no final conversation record to suppress. The implementation still aborts the frontend transport, detects backend disconnect, cancels/closes the provider stream, and labels UI stop as locally requested rather than independently confirmed by a server `done` event.

### Gate 6 — PDF citation location (`verified`)

- Verify and record the exact permissive geometry parser dependency before inclusion. Persist original/normalized text, block/span identifiers, bbox, and page dimensions.
- Use PDF.js with page-on-demand or virtualized rendering. A valid bbox produces a highlight; absent geometry produces the explicit page-only fallback and never a fabricated rectangle.

Gate 6 evidence recorded on 2026-07-16:

- Exact-pinned `pdfminer.six==20260107` geometry and `pdfjs-dist==5.4.624` rendering dependencies were reviewed at immutable upstream revisions with artifact hashes and license evidence recorded before use. Migration `008_pdf_geometry.sql` stores page, original/normalized span text, block/span identifiers, validated bbox, page dimensions, and coordinate-system metadata without rewriting prior chunks.
- Answer sources are expanded from fused groups into bounded single current-database chunks before prompting. Citation mapping revalidates the exact indexed document, course relation, chunk, page, excerpt, and optional geometry; a real cross-page merged-result regression proves `[[source:2]]` resolves to the second chunk/page rather than the first merged chunk.
- Geometry is emitted only for finite zero-origin, unit-scale, unrotated pages whose CropBox equals MediaBox. Real rotated and differing-CropBox PDFs index and serve normally but return `bbox: null`; the frontend states that the page is located and the highlight unavailable. No rectangle is inferred. Textless PDFs still fail explicitly because OCR is absent.
- The authenticated PDF content route canonicalizes the stored path, serves only PDFs, supports browser range requests, and sets no-store/nosniff headers. The client requires `application/pdf`, `%PDF-`, exact declared/streamed lengths, valid UTF-8 protocol data, a 32 MiB response cap, and abort propagation.
- The dialog lazy-loads the bundled local PDF.js worker, renders only the cited page, converts validated PDF coordinates through the page viewport, caps each canvas side at 8,192 pixels and total allocation at 16 Mi pixels, cleans up fetch/import/load/render close races, traps/restores focus, and exposes truthful loading/offline/error/fallback states.
- Consolidated verification passed frontend ESLint, strict typecheck, production build (1,684 modules, local worker), and 108/108 tests; Python 3.11 pytest 284/284 plus Ruff/format/compileall/pip check; Rust fmt, strict clippy, and 38/38 tests. Independent reviews found no remaining P0/P1 after the citation, geometry, cleanup, accessibility, truthfulness, and canvas-limit fixes.

### Gate 7 — packaging and documentation (`verified`)

- Freeze migrations, provider HTTP code, verified vector extension/native libraries, and verified geometry dependencies into the sidecar.
- Expand bundled-sidecar smoke coverage for READY, async jobs/cancel, CJK, shared course links, vector loading, process cleanup, and token secrecy. Re-run mounted-DMG verification.
- Preserve the accurate ad-hoc, non-notarized status. No Gatekeeper-distributable claim is allowed without Developer ID signing and notarization.
- Update implementation/visual plans and changelog with exact evidence and unresolved items, then commit the coherent verified scope on the current branch.

Gate 7 evidence recorded on 2026-07-16:

- `services/learning-core/pylock.toml` locks 24 external runtime packages to hashed wheels for CPython 3.11 on macOS arm64. The build rejects other platforms, unhashed/non-wheel/non-PyPI/local/VCS entries, duplicate packages, and critical-version drift; it installs the local project with `--no-deps` in an isolated freeze environment. Clean install, `pip check`, imports, sqlite-vec native loading, PyInstaller 6.21.0 freeze, and frozen `--help` passed.
- `npm run package:macos` rebuilt the sidecar, app, and `Keen_0.1.0_aarch64.dmg`; build-tree and mounted-DMG smoke passed READY, async import/job polling, queued/running cancellation and recovery, CJK FTS, same-hash multi-course links, sqlite-vec loading/KNN, ordinary PDF geometry/content, token absence from argv/environment, shutdown, and process cleanup.
- Final DMG path: `apps/desktop/src-tauri/target/release/bundle/dmg/Keen_0.1.0_aarch64.dmg`; 33,495,605 bytes; SHA-256 `5246ab0c4955498f2891561789d9fb6a27de9fddb13790282606ddf51fb0f16f`. `hdiutil verify` reported a valid checksum. Both app executables are thin arm64 Mach-O files. The build-tree and mounted app passed `codesign --verify --deep --strict`; the packaging script removes its intermediate build-tree `.app` after producing the DMG.
- This is an ad-hoc local-verification artifact (`TeamIdentifier` absent), not Developer ID signed or notarized; `spctl --assess` rejects it as expected. Universal/Intel builds, the credentialed hardened-runtime/notarization path, automated GUI lifecycle/provider E2E, and a complete distribution-wide notice bundle remain unresolved release blockers.
- Vulnerability checks reported zero known npm runtime and locked Python vulnerabilities. Cargo audit reported no vulnerability failure and 17 warnings; Linux-only GTK3/glib warnings are outside the arm64-Apple target, while six unmaintained `unic-*` crates remain in Tauri's macOS urlpattern graph and are recorded for upstream tracking.

## Database migration plan

Planned responsibilities are intentionally separated:

- `003_course_documents.sql`: add and index `course_documents`; backfill legacy course links.
- `004_document_index_jobs.sql`: durable job/status/stage/progress/cancellation/worker-generation state and indexes.
- `005_cjk_fts.sql`: CJK lexical table/triggers/rebuild, conditional on verified tokenizer availability in every shipped SQLite runtime.
- `006_embeddings.sql`: embedding model/version/dimension metadata and vector-store bookkeeping; the native vector table follows the verified backend's supported migration path.
- `007_embedding_job_kind.sql`: full-index versus model-pinned embedding-reindex job state and isolated staging.
- `008_pdf_geometry.sql`: add nullable per-chunk PDF page/block/span original/normalized text, bbox, page dimensions, and coordinate-system records; existing chunks remain valid with no geometry rows.

Every migration is applied in the existing `BEGIN IMMEDIATE` transaction with its schema version inserted in the same transaction. Tests cover 001-to-latest, 001+002-to-latest, empty latest, seeded latest, indexed-document preservation, course-link backfill, and interrupted-job state. No migration deletes the user database. The legacy `documents.course_id` column is retained during compatibility migration and stops being authoritative; no destructive reverse migration is promised.

## API compatibility strategy

- Existing authenticated health/course/task/mastery/list/search/query routes remain available while their callers migrate.
- `POST /v1/documents/import` changes from `201` completed indexing to `202` accepted with a document plus durable job. Frontend callers must poll the job; they may not infer success from upload completion.
- Document responses add `courseIds` and job-derived indexing capability/state without removing existing fields during this round.
- New job cancel, document retry/delete, course link/unlink, and answer SSE routes use the same pre-body Bearer guard and strict loopback origin policy.
- Existing `/v1/query` remains explicitly extractive/lexical during transition. It is not renamed or documented as generated RAG. `/v1/answer/stream` is the only model-generated answer surface.
- New optional fields are introduced before old fields are retired. Zod and Pydantic schemas reject malformed process-boundary data.

## Test matrix

| Boundary | Required evidence |
| --- | --- |
| Data isolation | distinct identifiers/derived directories; default debug has no seed arg; opt-in seed is idempotent and never touches production |
| Supervisor | exact protocol parsing, slow migration, missing READY, post-READY failed health, stale generation, concurrent/manual restart, token rotation, group reap, shutdown race |
| Window lifecycle | close/reopen retains one sidecar; actual exit refuses restart and terminates the full group |
| Import/job | 202 before parse completion, persisted stages/progress, cancellation/reaping, retry, delete transaction, startup recovery |
| Request guard | auth before parsing; Content-Length, chunked overflow, and disconnect behavior without full-body retention |
| Storage | missing reference, orphan quarantine, stale incoming/generation, duplicate hash, file-delete failure reporting |
| Course links | one document/file/version across two courses; both filters retrieve; unlink preserves the remaining link |
| Lexical retrieval | ranked Chinese, English, and mixed fixtures; RRF and course filtering |
| Hybrid | provider/vector interfaces, version/dimension isolation, loopback/redirect guard, lexical-only fallback, deterministic RRF |
| Answer stream | SSE framing, source-index mapping, invented-source rejection, prompt-injection boundary, provider/disconnect cancellation |
| Frontend | true retry, startup phases, job states/actions, course selection, SSE/stop/retry/edit, verified citation click/fallback |
| Packaging | frozen migrations/dependencies/extensions, mounted sidecar smoke, architecture/signature/notices/token/process checks |

## Rollback and recovery risks

- A newer binary can read the upgraded database, but an older binary may not understand new status values/tables. Rollback therefore means restoring the prior app while retaining a backup and avoiding writes that assume old status constraints; it does not mean deleting the database.
- Backfilling course links is additive. The retained legacy column reduces compatibility risk, but any period of dual-writing must be tested to avoid divergent sources of truth.
- A crash between physical-file movement and database commit can leave an orphan or missing reference. Atomic rename, transactions, startup reconciliation, and quarantine bound this risk but cannot make the filesystem and SQLite one transaction.
- Manual restart must not overlap an unreaped generation. The safer failure mode is `Unavailable` with diagnostics, not spawning another child.
- Native vector extensions and PDF geometry libraries remain platform-sensitive even after the exact arm64 mounted-app smoke passed. Every new Python/platform lock and release artifact must repeat native loading, KNN, geometry, content, cancellation, and cleanup smoke.
- Changing embedding model/version can require a full embedding reindex; lexical data must remain usable during that operation.
- Local model availability, latency, protocol variance, cancellation, and malformed citation output remain external-provider risks. The UI must expose them rather than silently substituting demo output.
- Startup reconciliation is intentionally conservative: ambiguous orphan material is quarantined, not immediately destroyed.

## Explicitly out of scope

- Cloud model providers, cloud uploads, API-key storage, arbitrary provider hosts, or redirects outside loopback.
- Multi-agent orchestration, Planner, FSRS, calendar writes, notifications, or unrelated static product pages.
- Custom ANN algorithms or an unlicensed/unverified PDF implementation.
- Factual-entailment verification beyond structural source/citation validation.
- OCR/image import unless separately authorized, licensed, implemented, and tested.
- A 1,000-page PDF support claim without a representative fixture and measured evidence.
- Pixel parity while authorized reference assets and visual-diff evidence remain absent.
- Developer ID signing, notarization, or a Gatekeeper-distributable claim without the required credentials and successful verification.
