# Changelog

All notable changes to Keen are documented here. Status statements must reflect tested behavior; planned work belongs in `docs/IMPLEMENTATION_PLAN.md`.

## Unreleased

### In progress

- Started the recoverable local learning-loop milestone on `codex/milestone-learning-loop`; the evidence-gated design covers durable Conversation, audited single-Agent tools, Deep Learn, Assessment, deterministic mastery/misconception updates, FSRS Review, explainable Learning Feed, restart recovery and packaged E2E. These capabilities are not claimed as implemented until their dated acceptance evidence is added.

### Added

- Forward-only learning-loop migrations 009–016 and typed persistence repositories for Conversation, Agent run/tool/mutation audit, Study Sessions and versioned plans, Assessment attempts/hints/evaluations, mastery evidence, misconceptions, Review/FSRS state, and explainable Study Tasks. Gate 1 preserves legacy learning rows and has repository/migration evidence only; no live learning-loop UI or Agent execution is claimed yet.
- Forward migration 017 and a pinned py-fsrs 6.3.1 adapter add stable positive review-card identities, upgrade pristine 015 schedules without deleting data, enforce UTC/version/state boundaries, and make repository-created schedules restart-round-trippable. Focused scheduler/repository/migration/vector tests passed 43/43, and the stable full Python suite passed 500/500 with one existing Starlette warning. This is deterministic scheduler/repository evidence only; the Flashcards UI and full assessment-to-review workflow remain open.

- Repository-wide engineering, security, permission, provenance, and verification rules in `AGENTS.md`.
- Initial empty-repository and missing-reference audit.
- Evidence-gated milestone implementation plan.
- Visual-reference intake and regression backlog that explicitly blocks pixel-parity claims until authorized assets arrive.
- Initial open-source candidate matrix and license-scan history, followed by evidence-backed upstream review records.
- Read-only upstream audit with exact review-only SHAs, verified parent licenses, copyright/NOTICE/header findings, and module-level reuse decisions; no upstream source was added to Keen.
- Empty initial upstream patch ledger and third-party notices baseline.
- Tauri 2 macOS shell with native menu/shortcuts, persisted window state, minimal capabilities, provisional application icon, and 256-bit ephemeral token generation.
- React/Vite strict-TypeScript desktop UI with Sidebar, Toolbar, Inspector, command palette, Home, Learning Feed, Knowledge Base, Conversation, Deep Learn, Quiz, Flashcards, Planner, Memory, Visualize, and Settings demo routes.
- Truthful offline/demo states that disable provider persistence, model-generated conversation answers/export, calendar writes, and unimplemented source viewing/highlighting.
- FastAPI loopback learning-core slice with Bearer authentication, structured logs, SQLite migration/idempotent seed, course/task/mastery APIs, deterministic BKT, and explicit offline/no-citation SSE.
- Versioned document schema and bounded PDF/Markdown/TXT ingestion with streamed size limits, extension/MIME/content validation, SHA-256 content-addressed storage and deduplication, recoverable status history, pypdf 6.14.2 extraction, and stored one-based page/chunk locations.
- SQLite FTS5 lexical search plus deterministic extractive `/v1/query` responses whose citations carry document/chunk IDs, section paths, one-based page numbers, and source excerpts; empty retrieval returns no inferred answer.
- Reusable strict-Zod learning-core client and Tauri runtime provider. Learning Feed now reads live task/mastery state, while Knowledge Base can list, upload, and search live local sources with explicit starting, unavailable, error, and browser-Demo states.
- Tauri learning-core supervision with a Python-child-owned random loopback bind, exact trusted-pipe port announcement, a 256-bit token delivered once through stdin instead of argv/environment, authenticated startup and continuing liveness probes, one bounded restart, child-exit detection, dual supervisor/bootloader watchdogs, an isolated process group with whole-tree termination, bounded shutdown, per-generation private extraction directories, stale-generation reclamation, and frontend endpoint rediscovery/cache isolation. No shell capability is granted to the frontend.
- Pre-body ASGI authentication and request caps, request-scoped thread-safe SQLite connections, a canonical-identity cross-process database owner lock, serialized/atomic same-hash imports, symlink-confined document storage, 0600 database/file and 0700 data-directory modes, interrupted-import recovery, and stale temporary-upload cleanup.
- PDF parsing in a spawned worker with wall-clock, CPU, memory, page, extracted-character, and chunk budgets, including frozen-PyInstaller spawn handling and macOS worker-tree RSS monitoring, so compressed/operator-heavy files cannot exhaust the long-lived sidecar process.
- PyInstaller 6.21.0 sidecar build script, fixed external-binary configuration, packaged migration/seed data, target-triple validation, dependency preflight, frozen-binary authentication/PDF/resource-limit smoke tests, and a packaging gate that validates the one newly built DMG and repeats the smoke from its mounted `.app`.
- Separate ad-hoc local and Developer ID release signing paths. The local path disables hardened runtime; the release path passes one `APPLE_SIGNING_IDENTITY` through PyInstaller and Tauri before enabling hardened runtime.
- Artifact-level license evidence for pypdf 6.14.2 and python-multipart 0.0.32, plus installed-license review of PyInstaller 6.21.0 and PyInstaller community hooks 2026.6. Distribution notice reconciliation remains incomplete.
- ESLint, Vitest, pytest, Rust fmt/clippy/tests, visual capture/diff harness, and dependency license/security reports.
- Verified arm64 development `Keen.app` and `Keen_0.1.0_aarch64.dmg` bundles; DMG checksum validation passed.
- Verified a later arm64 development `.app` and `.dmg` containing the frozen learning-core sidecar. Manual application lifecycle smoke covered launch, authenticated loopback-only health, bounded single restart, restart-budget enforcement, and cleanup after application quit. The automated packaging gate covered valid PDF import, compressed-PDF resource rejection, process-set cleanup, `hdiutil verify`, and strict deep code-signature verification against both the build-tree app and the mounted final DMG.
- Final local arm64 artifact: `Keen_0.1.0_aarch64.dmg`, 21,761,944 bytes, SHA-256 `da60e4b08bd3b3c8b77e90bbc2c7a7c625009f810d44400a806081242dfc5e87`; it is ad-hoc signed and unnotarized, not a distributable release.
- Development/production identity isolation, explicit-only demo seeding, a strict sidecar PORT/phase/READY/health protocol, generation-safe manual restart with token rotation, shutdown-intent/reopen lifecycle handling, bounded child-output frames, and frontend recovery states whose Retry action invokes the supervisor instead of merely refetching unavailable state.
- Durable single-worker document index jobs with `202` import, persisted stage/progress, real PDF/process cancellation, retry/delete/restart recovery, conservative storage quarantine/reconciliation, missing-source repair, configurable parser budgets, streaming request-size enforcement, and Knowledge Base job actions backed by the authenticated local API.
- Many-to-many course/document links with legacy backfill, same-hash cross-course file/index reuse, stable `courseIds`, explicit link/unlink APIs, and Knowledge Base course selection, filtering, and real multi-course labels.
- Dual lexical retrieval using the existing Latin `unicode61` index plus a feature-tested CJK `trigram` index, with script routing, bounded CJK shingles, mixed-query reciprocal-rank fusion, course filtering, and chunk deduplication.
- Provider-neutral local embedding/vector interfaces, exact-pinned sqlite-vec and HTTPX dependencies with provenance evidence, loopback-only Ollama/OpenAI-compatible embedding calls, immutable model/version/dimension state, ready-only vector search, bounded hybrid RRF, and explicit lexical-only fallbacks.
- Durable embedding-only reindex jobs with isolated staging and atomic promotion. Model changes expose `needs-reindex`; cancellation, provider failure, unexpected failure and restart interruption preserve existing chunks, FTS search and prior-model vectors.
- Strict API/client and Knowledge Base states for provider missing/failure, lexical-only, hybrid, embedding progress and reindex recovery, including a real model-pinned reindex action and no provider calls in Browser Demo.
- Loopback-only OpenAI-compatible and Ollama chat adapters with bounded streaming protocols, redirect/timeout/size guards, explicit terminal-marker validation, and cancellation that closes the provider response on client disconnect.
- A strict generated-answer SSE contract with retrieval events, incremental deltas, database-owned structural citation mapping, invalid-marker rejection, explicit warnings/errors, and an honest `structural_only` validation declaration.
- Live Tauri Conversation streaming with stop, retry, edit-and-resend, draft persistence, course scope, restart/network/provider/lexical-only states, and mapped citation Inspector. Browser Demo remains an explicit fixed transcript and its tests make no network or Tauri request.
- Migration 008 PDF line geometry, authenticated canonical PDF content/range serving, and a page-on-demand local PDF.js viewer with exact-page highlights for supported pages. Rotated/CropBox/custom-user-unit/translated-box pages fail closed to an explicit page-only citation state; the viewer caps authenticated bytes and canvas pixels, cleans up close/load/render races, traps/restores focus, and never fabricates a rectangle.
- A CPython 3.11/macOS arm64 PEP 751 runtime lock with hashed wheels, enforced clean-environment installation, locked-version/import/native-extension checks, and isolated PyInstaller freezing.
- Final hardening artifact: `Keen_0.1.0_aarch64.dmg`, 33,495,605 bytes, SHA-256 `5246ab0c4955498f2891561789d9fb6a27de9fddb13790282606ddf51fb0f16f`. Both build-tree and mounted-DMG sidecars passed READY, async import/poll/cancel, CJK, same-hash multi-course, sqlite-vec, PDF geometry/content, token secrecy, recovery, and process-cleanup smoke; both app executables are arm64 and the mounted app passed strict deep signature validation.

### Known limitations

- At the initial audit, no HyperKnow reference directory or authorized-scope file existed, so visual parity was not measurable and brand-asset reuse was not authorized by repository evidence.
- At the initial audit, there were no dependency manifests, lockfiles, or upstream checkouts, so license scanning could not run and candidate licenses remained unverified.
- HyperKnow pixel parity remains blocked because references and the canonical authorized-scope file are absent.
- The initial development bundles were ad-hoc/linker-signed, not notarized, and omitted the Python sidecar. The current arm64 app/DMG include the sidecar and use valid ordinary ad-hoc seals for local verification; hardened runtime is deliberately disabled on this no-Team-ID path so the PyInstaller one-file dylibs can load. Gatekeeper rejects the artifact. Intel/Universal builds and the same-Team Developer ID hardened-runtime/notarization path are unverified.
- OCR, reranking, and citation entailment validation are not implemented. PDF highlights are supported only where validated zero-origin, unrotated, unit-scale MediaBox/CropBox geometry is available; other pages explicitly fall back to page navigation without a highlight. The frozen local embedding/hybrid, loopback chat, PDF geometry/content, and vector stacks were verified inside the final mounted DMG.
- Agent orchestration/tool permissions, providers/Keychain, the FSRS-backed Flashcards/assessment workflow, calendar/notifications, complete persistence, automated GUI lifecycle E2E, accessibility/performance, and complete shipped notices remain open.
- HyperKnow references and the canonical authorized-scope file remain absent, so pixel parity is still blocked and no mismatch threshold is claimed.
