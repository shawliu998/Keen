# Keen

Keen is a local-first macOS learning Agent. This repository is in active implementation: the desktop shell, deterministic demo experience, authenticated local learning service, and quality harness are present; document ingestion, grounded RAG, model providers, sidecar supervision, and release packaging remain milestone work.

## Current verified slice

- React/Vite desktop experience with the core learning routes and deterministic seed data.
- Tauri 2 macOS window configuration, native menu, persisted window state, minimal capabilities, 256-bit ephemeral token generation, and path-boundary tests.
- FastAPI service bound to `127.0.0.1`, Bearer-token authentication on every endpoint, SQLite migrations/demo seed, study-task APIs, deterministic BKT mastery updates, and an explicitly offline/no-citation SSE response.
- Visual regression capture/diff harness. HyperKnow reference assets are not in this checkout, so the harness records a missing baseline instead of claiming a pixel-match result.

See [the implementation plan](docs/IMPLEMENTATION_PLAN.md), [repository audit](docs/REPOSITORY_AUDIT.md), and [visual reference TODO](docs/VISUAL_TODO.md) for exact status and evidence gaps.

## Prerequisites

- macOS 14+
- Node.js 20+
- Rust stable with the Apple targets needed for your build
- Python 3.11–3.14
- Google Chrome only for the current visual capture harness

## Web development

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:1430`. Demo data is local and deterministic; the current demo does not call a model provider.

## Native desktop development

```bash
source "$HOME/.cargo/env"
npm install
npm run tauri -- dev
```

The Python service is not yet packaged or supervised by Tauri. Until that milestone is complete, the desktop UI truthfully exposes it as unavailable rather than reporting a connected sidecar.

## Learning core

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e 'services/learning-core[dev]'
keen-learning-core \
  --port 18765 \
  --session-token 'replace-with-at-least-32-random-characters' \
  --database "$HOME/Library/Application Support/Keen/keen.sqlite3" \
  --seed-demo
```

The server refuses non-loopback hosts and short session tokens. See [the service README](services/learning-core/README.md) for API examples.

## Checks

```bash
npm run lint
npm run typecheck
npm test
python3.11 -m pytest services/learning-core/tests
source "$HOME/.cargo/env" && cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
```

With the Vite server already running, capture the first visual artifact:

```bash
npm run visual:test
```

Results are written to `artifacts/visual-diff/`. A missing authorized reference is reported as `missing_reference`, not a pass.

## Packaging status

The arm64 desktop shell has been built as both an 11 MB `.app` and a 2.8 MB `.dmg`; `hdiutil verify` passed for the DMG. Reproduce the non-interactive development bundles with:

```bash
source "$HOME/.cargo/env"
cd apps/desktop
../../node_modules/.bin/tauri build --bundles app
CI=true ../../node_modules/.bin/tauri build --bundles dmg
```

Outputs are under `apps/desktop/src-tauri/target/release/bundle/`. They are ad-hoc/linker-signed, not notarized, Apple Silicon only, and do not contain the Python sidecar. Sidecar packaging/supervision, signing/entitlements, universal/Intel validation, and complete third-party notices remain release blockers.

## References and third-party code

This checkout does not contain the authorized HyperKnow reference bundle described by the brief. No HyperKnow, DeepTutor, or OATutor source has been copied. Before protected assets or upstream source are added, follow [AGENTS.md](AGENTS.md), [the open-source inventory](docs/OPEN_SOURCE_INVENTORY.md), and [the upstream patch ledger](docs/UPSTREAM_PATCHES.md).
