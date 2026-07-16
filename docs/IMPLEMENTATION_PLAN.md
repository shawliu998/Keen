# Implementation Plan

## Status contract

Use only these states: `not started`, `in progress`, `blocked`, `implemented / unverified`, and `verified`. “Verified” requires the acceptance evidence named in the row. This document is a living control plane, not proof by itself.

## First-round status (2026-07-15)

| Work item requested for the first round | Status at initial audit | Evidence / blocker |
| --- | --- | --- |
| Audit repository | Verified | `docs/REPOSITORY_AUDIT.md`; initial repository contained only `.git`. |
| List present/missing references and pages | Verified | Audit page matrix and `docs/VISUAL_TODO.md`; all expected references were missing. |
| Create open-source reuse matrix | Verified | `docs/OPEN_SOURCE_INVENTORY.md`; candidates only, no license assumptions. |
| Identify DeepTutor/OATutor adaptation candidates | Verified as read-only audit | Exact parent revisions and root licenses were verified in temporary `/tmp` checkouts; nothing was copied or introduced. Module-level decisions are in `docs/OPEN_SOURCE_INVENTORY.md`. |
| Create implementation plan | Verified | This document. |
| Establish Tauri + React project | Verified for first-round shell | Frontend lint/typecheck/build/tests pass; Rust fmt/clippy/tests pass; actual arm64 `.app` and `.dmg` development bundles were generated and inspected. The Python service is not packaged into them yet. |
| Implement main window, Sidebar, Toolbar, Home | Verified as provisional demo UI | Functional routes and interactions pass 5 Vitest tests; the 1440×920 Home current screenshot exists. HyperKnow visual parity remains unverified because references are absent. |
| Establish first visual regression screenshots | Harness/current capture verified; comparison blocked | `tools/visual-regression` created `artifacts/visual-diff/current/home.png` and a report with `missing_reference`. No mismatch percentage or pass is claimed. |
| Show modified files and test results | Verified for first round | Exact validation evidence is recorded in the update log below. |

## Product slices

Each milestone must produce a vertically testable increment. Do not mark a milestone complete because files exist.

### Milestone 0 — audit and governance

Status: **in progress**. Audit, upstream review, and first dependency scans are recorded; complete shipped-license notice reconciliation remains open.

- Repository/reference audit and explicit evidence gaps.
- Legal/provenance rules and third-party tracking templates.
- Page inventory and visual-reference intake list.
- Architecture, security, permission, persistence, and truthfulness guardrails.
- Exit gate: governance docs reviewed, manifests inventoried, dependency/license scan recorded, and unresolved reference authorization carried as a named blocker.

### Milestone 1 — secure desktop shell

Status: **in progress**. The shell builds, the selected-file document path is connected, and learning-core supervision is implemented. Automated window/restart lifecycle E2E, native file-dialog/drop coverage, and complete state/error coverage remain open.

- Tauri 2 desktop workspace, React/Vite strict TypeScript, routing, query/state layers.
- macOS window: 1440×920 default, 1180×740 minimum, Retina/fullscreen, system traffic lights, integrated titlebar, persisted window state.
- Sidebar, Toolbar, collapsible Inspector, keyboard focus, reduced motion, core shortcuts.
- Provisional design tokens clearly labeled as unmeasured.
- Deterministic browser Demo Mode with no learning-core or provider traffic; Tauri mode may use only the authenticated loopback service until providers are explicitly added.
- Security foundation: minimal capabilities, controlled paths, secret-storage boundary.
- Exit gate: dev launch; lint/typecheck/unit tests; Rust tests; window-state restart test; no false enabled controls.

Historical first-round note: before the initial push, `origin` exposed no branch refs and the first arm64 development bundles omitted the Python sidecar. Commit `2a68a51` is now present on `origin/main`. A later arm64 `.app` and `.dmg` embed the supervised learning-core binary; that does not retroactively change the first-round bundle evidence.

### Milestone 2 — static product surfaces and visual harness

Status: **in progress; visual comparison blocked by missing references**. All named routes have deterministic demo surfaces, the Home current capture exists, and the harness truthfully reports `missing_reference`.

- Home, Learning Feed, Knowledge Base, Conversation, Deep Learn, Quiz, and Settings.
- Deliberate loading, empty, partial, error, offline, cancelled, provider, sidecar, and indexing/migration states.
- `tools/visual-regression` manifest, deterministic seed, animation/time controls, capture/current/diff outputs.
- Implement remaining Flashcards, Planner, Memory, and Visualize static states early enough to keep shared contracts coherent.
- Exit gate: routes and state fixtures covered by component/E2E checks. Pixel threshold applies only after valid references arrive; no parity claim before then.

### Milestone 3 — local data and recovery

Status: **in progress**. Versioned SQLite migrations now cover courses/concepts/mastery/tasks plus documents, versions, chunks, status events, and an external-content FTS5 index. A process-lifetime advisory lock serializes migration/recovery/temporary-upload ownership across processes. The live frontend reads tasks/mastery/documents and can upload/search supported files. The full required domain schema, durable conversation/Agent state, and restart/recovery E2E remain open.

- SQLite + FTS5, versioned migrations, repositories, seed importer, data-directory policy.
- Domain entities named in the product brief, including Agent run/step/tool/approval records.
- Conversation draft, session, index task, learner state, and window/sidebar persistence.
- Exit gate: migration forward tests, repository tests, deterministic seed reset for tests, restart/recovery E2E without deleting the database.

### Milestone 4 — document ingestion, retrieval, and citations

Status: **in progress**. PDF/Markdown/TXT import is bounded and durable jobs provide real progress, cancellation, retry and restart recovery. Latin/CJK FTS plus optional loopback-only local embeddings and sqlite-vec provide truthful lexical-only or hybrid retrieval with model/version/dimension isolation, RRF, course filtering, deduplication and bounded adjacent merging. Model changes create an embedding-only reindex that preserves the live lexical index until atomic vector promotion.

- Controlled import for PDF/Markdown/TXT/image; MIME/hash checks; parser and OCR fallback.
- Page/section-aware chunks with text location, parser/embedding versions, and content hashes.
- FTS + validated vector backend, metadata filters, RRF, dedupe, rerank, citation validation.
- Virtualized PDF viewer; citation opens exact page and highlights the source chunk.
- Exit gate: ingestion/index cancellation and retry tests; retrieval/citation contract tests; large-document UI does not render all pages.

Current boundary: image import and OCR are not implemented; textless PDFs fail explicitly. Hybrid retrieval, loopback-only chat-model answer streaming, sqlite-vec, PDF geometry/content, and mounted-DMG execution are verified for CPython 3.11/macOS arm64. Generated citations are structurally mapped to a single current database chunk; factual-entailment validation and reranking are not implemented. PDF.js renders only the cited page and highlights validated geometry for ordinary zero-origin, unrotated, unit-scale MediaBox/CropBox pages; rotation, translated boxes, custom user units, CropBox differences, and absent layout explicitly use page-only fallback. `/v1/query` stays deterministic passage extraction; `/v1/answer/stream` is the generated-answer surface.

### Milestone 5 — authenticated learning-core sidecar and Agent runtime

Status: **in progress**. The loopback FastAPI service, pre-body all-route Bearer authentication, bounded imports, health, SQLite/BKT/document slices, recovery, and offline/no-citation SSE endpoint are verified. The Python child owns a port-0 `127.0.0.1` bind and announces it through the trusted child pipe; Rust writes a 256-bit token once through stdin, isolates the sidecar in its own process group, performs authenticated readiness and continuing liveness probes, permits one bounded restart, and performs bounded whole-group shutdown. Each generation uses a confined 0700 extraction directory that is cleaned only after the group exits or reclaimed after a prior supervisor crash. Rust policy/path/token/process tests, an automated final-DMG auth/PDF/resource/token-leak smoke, and manual mounted-app launch/crash/quit tests exist; automated GUI lifecycle E2E, cancellation, log rotation, providers, approvals, and the orchestrator remain open.

- Python 3.11+ sidecar, PyInstaller-equivalent packaging, loopback-only random port.
- Rust-generated ≥128-bit session token; every sidecar request authenticated.
- Health, crash restart, graceful shutdown, log rotation, SSE or WebSocket streaming, cancellation.
- One orchestrator with the specified tool registry; structured run/step/tool/state/citation logs.
- Level 1/2/3 permission and approval flow; prompt-injection boundary for documents.
- Provider adapters with secret-safe UI/storage and explicit missing/rate-limit states.
- Exit gate: API contract, lifecycle, auth rejection, crash recovery, cancellation, approval, and log-redaction tests.

### Milestone 6 — learning engine

Status: **in progress**. Deterministic BKT code and live read-only Feed task/mastery data exist, but Quiz attempts do not yet mutate the learning core end-to-end. FSRS, evidence weighting, structured Deep Learn persistence, planner, and memory integration remain open.

- Structured Deep Learn sessions, diagnostics, concept map, checkpoints, active recall, practice, summary, resume.
- Quiz item types, layered hints/scaffolds, deterministic grading evidence, error review.
- Deterministic BKT-style mastery service; LLM may explain but not choose arbitrary mastery values.
- FSRS-backed flashcards maintained separately from concept mastery.
- Explainable proactive feed and planner with rescheduling; calendar proposals require confirmation.
- Editable, evidenced learner memory and persona.
- Exit gate: BKT/FSRS fixtures, hint-weight tests, planner/restart E2E, and auditability of every mastery mutation.

### Milestone 7 — macOS integration

Status: **in progress**. Native macOS menu items, shortcut event bridge, titlebar/window configuration, icon set, window-state plugin, Application Support database path, and sidecar exit handling are present. Notifications, Keychain, calendar, native file-dialog/drop completion, and permission-denial tests remain open.

- Native menu, shortcuts, notifications, file dialogs/drop, Keychain/Stronghold, calendar confirmation.
- Sidecar termination on exit, app support/cache paths, entitlements and least privilege.
- Exit gate: permission-denial states, shortcut/menu tests where practical, calendar preflight/confirmation test, signed-or-explicitly-unsigned `.app` build evidence.

### Milestone 8 — release quality

Status: **in progress**. Lint/typecheck/unit/build/Rust/Python checks, first visual capture, dependency scans, an arm64 sidecar executable, and arm64 `.app`/`.dmg` artifacts containing that sidecar exist. The packaging path installs a hashed CPython 3.11/macOS arm64 runtime lock in an isolated freeze environment and rejects a bundled sidecar that cannot start or pass the expanded authenticated smoke. The DMG checksum and mounted app's strict deep ad-hoc signature verify. Automated GUI lifecycle/provider E2E, performance, universal/Intel builds and locks, Developer ID hardened-runtime signing/notarization, complete notices, and authorized visual comparison remain open.

- Visual regression on authorized references, accessibility, performance and large-data tests.
- Complete dependency/license inventory, notices, upstream patch ledger, vulnerability review.
- Reproducible `.app` and `.dmg`; build/run/package docs.
- Exit gate: all acceptance conditions mapped to real artifacts; no known high-severity security issue; no false completion states.

### Milestone 9 — recoverable learning loop

Status: **in progress** on `codex/milestone-learning-loop`. The branch starts from `094c44eb1eaa7ae77c45fd5c07d651587b968fc0`; the pre-implementation baseline passed frontend lint/strict typecheck and 108 Vitest tests, 284 Python tests with one existing Starlette deprecation warning, and 38 Rust tests. This baseline does not verify any new learning-loop behavior.

- Implementation control document: `docs/LEARNING_LOOP_IMPLEMENTATION_PLAN.md`.
- Persist Conversation, Agent run/tool/mutation audit, Deep Learn sessions/plans/events, assessments/hints/evaluations, mastery evidence, misconceptions, Review/FSRS state and explainable Study Tasks.
- Keep one Agent orchestrator over typed tools and deterministic learning services. The model must not choose mastery values, final normalized scores, misconception confirmation, review dates, Feed priority or arbitrary database mutations.
- Connect Conversation, Deep Learn, Quiz, Flashcards and Learning Feed to authenticated local state with cancellation, Undo where applicable, restart recovery and truthful failure/provider states.
- Exit gate: the real 18-step imported-PDF learning loop, restart recovery, frontend/Python/Rust checks, arm64 `.app`/`.dmg` mounted smoke and dependency/license evidence all pass and are linked. Static Demo state, seed data or schema existence does not satisfy the gate.

## Cross-milestone acceptance evidence

| Claim | Minimum evidence |
| --- | --- |
| “Runs” | Exact command, environment, successful launch, date |
| “Tested” | Exact command and pass/fail/skip totals |
| “Persists” | Restart E2E covering the named state |
| “Secure sidecar” | Bind-address, token, path, capability, redaction, crash/shutdown tests |
| “Pixel matched” | Authorized reference ID, viewport, seed, current/diff images, mismatch percentage `<3%` |
| “Supports 1000-page PDF” | Fixture and measured memory/interaction result, not a loading mock |
| “Packaged” | Actual `.app`/`.dmg` paths and build output |
| “License compliant” | Lockfile-based scan plus verified upstream revisions/notices |

## Required end-to-end spine

Build toward one recoverable E2E path: create course → import PDF → observe real index progress → ask → open page citation/highlight → generate quiz → answer → deterministic mastery update → create review task → restart → verify all state restored.

## Update log

Append short dated entries. Link artifacts or commands; do not replace historical facts.

- 2026-07-15: Initial plan created from an empty local repository. References, upstream checkouts, licenses, tests, and builds were unavailable at audit time.
- 2026-07-15: Parallel work introduced Tauri/React/Python source and validation artifacts. Rust 1.97.0 was installed; the later entries below record consolidated test and packaging evidence. Milestone 1 remains in progress because its remaining integration gates are not satisfied.
- 2026-07-15: Read-only `/tmp` audit verified DeepTutor `3e3b9a6e…` as Apache-2.0 and OATutor `0d376e23…` as MIT at their reviewed parent revisions. Neither was introduced; implementation choices remain independently gated.
- 2026-07-15: Frontend ESLint and strict typecheck passed; Vitest passed 2 files / 5 tests; Vite built 1,658 modules. Python pytest passed 6 tests. Rust fmt check, clippy with `-D warnings`, and 3 tests passed.
- 2026-07-15: Visual harness captured Home at 1440×920 and reported `missing_reference`; this is not a pixel-match pass. The capture/report are local gitignored artifacts, not durable evidence in this repository.
- 2026-07-15: Generated an 11 MB arm64 `Keen.app` and a 2.8 MB `Keen_0.1.0_aarch64.dmg`. `hdiutil verify` passed; the app is ad-hoc/linker-signed, not distribution-signed or notarized, and the bundles do not yet contain learning-core.
- 2026-07-15: npm production audit and the upgraded Python environment audit reported zero known vulnerabilities. npm/Python/Cargo license metadata reports were generated under the local gitignored `artifacts/license-scan/`; they are not present in a GitHub checkout. Cargo vulnerability audit and complete notice reconciliation remain open.
- 2026-07-16: Added migration `002_documents.sql`, bounded PDF/Markdown/TXT ingestion, SHA-256 storage/deduplication, pypdf page extraction, status history, page/section/character-aware chunks, FTS5 search, and deterministic extractive citations. OCR, embeddings/vector search, PDF viewing/highlighting, and model-backed RAG remain absent.
- 2026-07-16: Connected the Tauri UI to a strict loopback/Zod client. Browser runs stay in explicit Demo mode; Tauri Learning Feed and Knowledge Base use authenticated live state and do not silently substitute Demo data on service failure.
- 2026-07-16: Added PyInstaller 6.21.0 packaging and Tauri sidecar supervision. The generated arm64 binary and sidecar-bearing `.app` launched successfully; manual crash testing observed one restart on a new PID/port and no second restart, while application quit removed both PyInstaller processes and the listener. This is manual smoke evidence, not automated lifecycle E2E.
- 2026-07-16: Rebuilt `Keen_0.1.0_aarch64.dmg` with the 17,828,608-byte sidecar embedded. The DMG was 21,555,102 bytes; `hdiutil verify` passed, both executables were arm64, and the mounted app passed `codesign --verify --deep --strict`. A later runtime check showed that ad-hoc hardened runtime prevents the PyInstaller dylib from loading, so this historical artifact was superseded by the explicit non-hardened local-verification path. `spctl --assess` returned rejection status 3 because Developer ID signing and notarization are absent.
- 2026-07-16: Current checks passed: frontend ESLint and strict typecheck; Vitest 5 files / 35 tests; Python `PYTHONPATH=services/learning-core .venv/bin/python -m pytest services/learning-core/tests` 47 tests with one Starlette deprecation warning; Rust fmt, clippy `-D warnings`, and 19 tests.
- 2026-07-16: Exact pypdf 6.14.2 and python-multipart 0.0.32 wheel hashes/licenses were verified, and installed PyInstaller/community-hook license files were inspected. `THIRD_PARTY_NOTICES.md` remains explicitly incomplete pending full shipped-subset reconciliation.
- 2026-07-16: The final local-verification packaging gate rebuilt `Keen_0.1.0_aarch64.dmg` at 21,761,944 bytes (SHA-256 `da60e4b08bd3b3c8b77e90bbc2c7a7c625009f810d44400a806081242dfc5e87`). `hdiutil verify`, arm64 architecture checks, and mounted-app `codesign --verify --deep --strict` passed. Both the build-tree app and the exact mounted DMG passed authenticated loopback health, valid PDF import, compressed-PDF resource rejection, post-rejection health, token-leak, isolated-worker/resource-tracker accounting, and full process-cleanup smoke tests. This is an ad-hoc, non-notarized local artifact, not a distributable release.
- 2026-07-16: Sidecar/RAG hardening Gate 1 separated development (`com.keen.learning.dev`) and production identities, removed implicit debug seed, added strict PORT/phase/READY/health startup gates, manual restart/token rotation/generation serialization, shutdown-intent and macOS reopen handling, bounded child-output frames, and real frontend restart/status behavior. Consolidated checks passed: frontend lint/typecheck/build and 53 tests; Python 57 tests plus compileall; Rust fmt/clippy and 33 tests. GUI reopen, real IPC restart, bundled READY smoke, and new packaging remain unverified.
- 2026-07-16: Hardening Gate 2 replaced synchronous indexing with migration-backed single-worker jobs and `202` import, real progress, server cancellation, retry/delete, interrupted recovery, missing/orphan/quarantine reconciliation, configurable PDF budgets, and a streaming ASGI request cap. Transactional race and real PDF process-group cancellation tests are included. Consolidated checks passed: frontend 69 tests plus lint/typecheck/build; Python 3.11 90 tests plus compileall; Rust 33 tests plus fmt/clippy. Ruff passed only in the local Python 3.14 service environment; root Python 3.11 Ruff and MyPy are not configured.
- 2026-07-16: Hardening Gate 3 added backfilled many-to-many course/document links, same-hash cross-course reuse, live course selection/link/filter UI, and dual Latin/CJK lexical retrieval with mixed-query RRF. The five required multilingual fixtures ranked their relevant chunk first. Consolidated checks passed: frontend 72 tests plus lint/typecheck/build; Python 3.11 121 tests plus compileall and local Python 3.14 Ruff; Rust 33 tests plus fmt/clippy. Hybrid/vector retrieval, providers, generated answers, and citation viewing remain not started.
- 2026-07-16: Hardening Gate 4 added exact-pinned sqlite-vec/HTTPX provenance, provider-neutral interfaces, guarded loopback local embeddings, ready/complete-only vector search, hybrid RRF, truthful lexical fallback, and model-pinned embedding-only reindex with atomic staging. Consolidated source checks passed: frontend 79 tests plus lint/typecheck/build; Python 3.11 260 tests plus Ruff/compileall; Rust 34 tests plus fmt/clippy. Generated answers, PDF citation geometry/viewing, and final frozen app/DMG verification remain open.
- 2026-07-16: Hardening Gate 5 added loopback-only OpenAI-compatible/Ollama chat streaming, bounded provider protocols, strict seven-event answer SSE, untrusted-source prompt boundaries, server-owned structural citation remapping, end-to-end disconnect cancellation, and the real Tauri Conversation client with bounded SSE parsing, incremental output, stop/retry/edit/draft, provider/retrieval/restart states and citation Inspector. Browser Demo makes zero model/retrieval/Tauri requests. Monitoring checks passed Python 3.11 276/276 and the frontend Gate 5 subset 45/45; execution-window checks passed frontend 93/93 plus lint/typecheck/build, Ruff/format/compileall, Rust 35 plus fmt/clippy, and `git diff --check`. PDF geometry/viewing and final packaging remain open.
- 2026-07-16: Hardening Gate 6 added migration-backed pdfminer span geometry, single-chunk generated-answer sources, exact cross-page citation mapping, authenticated canonical PDF content/range serving, and a page-on-demand local PDF.js dialog with highlight/page-only states, byte/canvas caps, cleanup-race handling, and modal keyboard focus management. Real rotation and CropBox PDFs prove fail-closed `bbox: null`; ordinary-page geometry remains highlighted. Consolidated checks passed frontend 108/108 plus lint/typecheck/build, Python 284/284 plus Ruff/format/compileall/pip check, and Rust 38/38 plus fmt/clippy; independent review found no remaining P0/P1.
- 2026-07-16: Hardening Gate 7 added a 24-package hashed CPython 3.11/macOS arm64 PEP 751 runtime lock and isolated frozen build, then ran the actual app/DMG pipeline. `Keen_0.1.0_aarch64.dmg` is 33,495,605 bytes with SHA-256 `5246ab0c4955498f2891561789d9fb6a27de9fddb13790282606ddf51fb0f16f`; checksum, arm64 architecture, strict deep ad-hoc signature, and build-tree/mounted-DMG READY/jobs/cancel/CJK/M:N/vector/PDF/token/process smoke passed. It remains non-notarized and Gatekeeper-rejected; complete notices, Universal/Intel, credentialed distribution signing, automated GUI/provider E2E, and authorized visual parity remain open.
- 2026-07-16: Started the recoverable learning-loop milestone on `codex/milestone-learning-loop` from `094c44e`. Gate 0 records a clean pre-implementation baseline of frontend lint/strict typecheck and Vitest 108/108, Python pytest 284/284 with one existing warning, and Rust 38/38. Conversation persistence, Agent audit/tools, Deep Learn, Assessment, mastery evidence, misconceptions, FSRS Review and explainable Feed mutation remain `not started` unless later evidence updates this log.
- 2026-07-16: Learning-loop Gate 1 added forward-only migrations 009–016 and typed, transaction-composable repositories for durable Conversation, Agent audit/permissions, Study Sessions/versioned plans, Assessment, mastery evidence/events, misconceptions, Review/FSRS state, and explainable Study Tasks. Legacy `mastery_events` and `study_tasks` are preserved and backfilled; an actual 008-to-016 fixture passed consistency checks. Gate 1 migration/repository tests passed 46/46, the current full Python suite passed 374/374 with one existing warning, Ruff lint/format passed for 86 files, and independent review found no remaining P0/P1. This verifies persistence boundaries only; HTTP, orchestration, FSRS scheduling, and live frontend workflows remain open.
- 2026-07-16: Learning-loop Gate 2 added the exact-pinned py-fsrs 6.3.1 adapter and forward migration 017. Review scheduling now uses fixed, versioned Keen v1 parameters, UTC-aware validated state, stable positive identities allocated under a SQLite write transaction, complete 015 backfill for pristine new schedules, and repository-to-scheduler restart round trips. Focused scheduler/repository/migration/vector tests passed 43/43, the stable full Python suite passed 500/500 with one existing Starlette warning, and Ruff lint/format passed for all 97 learning-core Python files. This does not claim the Flashcards UI or assessment-to-review orchestration is connected.
- 2026-07-16: Gate 3 foundation added a closed typed Agent tool registry, permission/effect policy, cancellable single-step executor, Level 2 caller-owned transaction handoff, executable typed inverse mutation, bounded untrusted-document context, and redacted audit summaries while separately passing raw typed mutations to the controlled persistence boundary. Agent-focused tests passed 35/35 and independent review found no remaining P0/P1 in this slice. SQLite AuditSink integration, idempotent replay, Undo execution, product tools, orchestrator, SSE/reconnect and UI remain open; Gate 3 is not marked verified.
- 2026-07-16: The first Gate 3 product-tool slice added typed real-data tools for Study Feed reads, due Review reads and course-scoped Study Task completion, plus a Level 3 export declaration that remains blocked by the executor. Focused SQLite tests passed 6/6 for closed schemas, UTC, course scope, caller-transaction rollback and executable Undo output. Additional tool groups, persistent audit/replay, Undo execution and orchestration remain open.
- 2026-07-16: The Gate 3 service slice added a single-provider orchestrator protocol, fixed automation-only provider, durable SQLite event store, ordered/redacted public Agent events, real tool-step lifecycle, stable invocation replay handling, bounded action/content/payload budgets, cancellation/error terminal states and Last-Event-ID SSE continuation. Focused tests passed 17/17 and the combined Agent subset passed 63/63. FastAPI Agent routes, UI, real provider selection and process-restart continuation remain open, so Gate 3 is still in progress.
