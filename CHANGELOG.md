# Changelog

All notable changes to Keen are documented here. Status statements must reflect tested behavior; planned work belongs in `docs/IMPLEMENTATION_PLAN.md`.

## Unreleased

### Added

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

### Known limitations

- At the initial audit, no HyperKnow reference directory or authorized-scope file existed, so visual parity was not measurable and brand-asset reuse was not authorized by repository evidence.
- At the initial audit, there were no dependency manifests, lockfiles, or upstream checkouts, so license scanning could not run and candidate licenses remained unverified.
- HyperKnow pixel parity remains blocked because references and the canonical authorized-scope file are absent.
- The initial development bundles were ad-hoc/linker-signed, not notarized, and omitted the Python sidecar. The current arm64 app/DMG include the sidecar and use valid ordinary ad-hoc seals for local verification; hardened runtime is deliberately disabled on this no-Team-ID path so the PyInstaller one-file dylibs can load. Gatekeeper rejects the artifact. Intel/Universal builds and the same-Team Developer ID hardened-runtime/notarization path are unverified.
- The document slice is lexical and text-only. OCR, embeddings, vector/hybrid retrieval, reranking, PDF rendering/page navigation/highlighting, model providers, and semantic answer generation are not implemented.
- Agent orchestration/tool permissions, providers/Keychain, FSRS, calendar/notifications, complete persistence, automated GUI lifecycle E2E, accessibility/performance, and complete shipped notices remain open.
- HyperKnow references and the canonical authorized-scope file remain absent, so pixel parity is still blocked and no mismatch threshold is claimed.
