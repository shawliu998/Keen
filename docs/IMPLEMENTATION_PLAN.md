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

Status: **in progress**. PDF/Markdown/TXT import validates filename extension, declared MIME, PDF signature or UTF-8 text content, copies/hashes incrementally to a bounded temporary file, stores under a generated content-addressed path, and deduplicates indexed content. pypdf 6.14.2 extraction runs in a spawned process with wall-clock, CPU, memory, page, extracted-character, and chunk ceilings; a compressed-operator regression confirms the API process remains healthy when the worker is rejected. Deterministic chunks persist section paths, character locations, parser/content hashes, and status history. FTS5 search and extractive query responses return verifiable page-numbered excerpts.

- Controlled import for PDF/Markdown/TXT/image; MIME/hash checks; parser and OCR fallback.
- Page/section-aware chunks with text location, parser/embedding versions, and content hashes.
- FTS + validated vector backend, metadata filters, RRF, dedupe, rerank, citation validation.
- Virtualized PDF viewer; citation opens exact page and highlights the source chunk.
- Exit gate: ingestion/index cancellation and retry tests; retrieval/citation contract tests; large-document UI does not render all pages.

Current boundary: image import and OCR are not implemented; textless PDFs fail with an explicit recovery message and their stored input is removed. `embedding_version` remains `NULL`; there is no embedding model, vector/hybrid search, RRF, reranker, semantic answer generation, PDF viewer, page navigation, bounding-box geometry, or source highlight flow. `/v1/query` is deterministic FTS5 passage extraction, not model-backed RAG.

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

Status: **in progress**. Lint/typecheck/unit/build/Rust/Python checks, first visual capture, dependency scans, an arm64 sidecar executable, and arm64 `.app`/`.dmg` artifacts containing that sidecar exist. The packaging path now rejects a bundled sidecar that cannot start or pass authenticated health. The DMG checksum and mounted app's strict deep ad-hoc signature verify. Accessibility/automated GUI lifecycle E2E/performance, universal/Intel builds, Developer ID hardened-runtime signing/notarization, reproducible Python runtime locking, and complete notices remain open.

- Visual regression on authorized references, accessibility, performance and large-data tests.
- Complete dependency/license inventory, notices, upstream patch ledger, vulnerability review.
- Reproducible `.app` and `.dmg`; build/run/package docs.
- Exit gate: all acceptance conditions mapped to real artifacts; no known high-severity security issue; no false completion states.

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
