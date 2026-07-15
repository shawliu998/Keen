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
- Truthful offline/demo states that disable provider persistence, grounded generation/export, calendar writes, and unimplemented source verification.
- FastAPI loopback learning-core slice with Bearer authentication, structured logs, SQLite migration/idempotent seed, course/task/mastery APIs, deterministic BKT, and explicit offline/no-citation SSE.
- ESLint, Vitest, pytest, Rust fmt/clippy/tests, visual capture/diff harness, and dependency license/security reports.
- Verified arm64 development `Keen.app` and `Keen_0.1.0_aarch64.dmg` bundles; DMG checksum validation passed.

### Known limitations

- At the initial audit, no HyperKnow reference directory or authorized-scope file existed, so visual parity was not measurable and brand-asset reuse was not authorized by repository evidence.
- At the initial audit, there were no dependency manifests, lockfiles, or upstream checkouts, so license scanning could not run and candidate licenses remained unverified.
- HyperKnow pixel parity remains blocked because references and the canonical authorized-scope file are absent.
- The generated development bundles are ad-hoc/linker-signed, not notarized, and do not contain the Python sidecar; they are not release-ready.
- PDF ingestion/RAG/citation verification, sidecar supervision/restart, providers/Keychain, FSRS, calendar/notifications, complete persistence, accessibility/E2E/performance, universal/Intel builds, and complete shipped notices remain open.
