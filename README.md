# Keen

Keen is a local-first macOS learning Agent. This repository is in active implementation: the desktop shell, authenticated/supervised local learning service, live frontend client, deterministic browser Demo, bounded document ingestion, FTS5 lexical retrieval, and quality harness are present. This is not yet a complete Agent or semantic RAG product.

## Current verified slice

- React/Vite desktop experience with the core learning routes, explicit browser Demo state, and a Zod-validated loopback client. In Tauri, Learning Feed reads live tasks/mastery and Knowledge Base lists, imports, and searches live local documents; it does not silently substitute Demo records when the service is unavailable.
- Tauri 2 macOS window configuration, native menu, persisted window state, minimal frontend capabilities, and a supervised learning-core process group. The Python child atomically binds a random `127.0.0.1` port and announces it over its trusted stdout pipe; Rust generates a 256-bit session token, sends it through the child's stdin pipe, performs startup and continuing authenticated health checks, permits one bounded restart, and terminates the full PyInstaller process group on failure or application exit.
- FastAPI bound to `127.0.0.1` with pre-body Bearer authentication on every endpoint, bounded request bodies, SQLite migrations/demo seed, study-task APIs, deterministic BKT, and an explicitly offline/no-citation SSE response.
- Bounded PDF/Markdown/TXT ingestion with extension/MIME/content validation, incremental file hashing/copying, atomic same-hash deduplication, a cross-process database owner lock, SHA-256 content-addressed storage, resource-isolated pypdf 6.14.2 extraction, persisted/recoverable status history, FTS5 search, and deterministic extractive citations with one-based page numbers.
- Visual regression capture/diff harness. HyperKnow reference assets are not in this checkout, so the harness records a missing baseline instead of claiming a pixel-match result.

Not implemented: OCR, embeddings, vector or hybrid retrieval, reranking, a PDF viewer/page highlight flow, model providers, the Agent orchestrator/tool permission runtime, secure provider-key storage, and a complete shipped third-party notice bundle.

See [the implementation plan](docs/IMPLEMENTATION_PLAN.md), [repository audit](docs/REPOSITORY_AUDIT.md), and [visual reference TODO](docs/VISUAL_TODO.md) for exact status and evidence gaps.

## Prerequisites

- macOS 14+
- Node.js 20+
- Rust stable with the Apple targets needed for your build
- Python 3.11–3.14
- PyInstaller 6.21.0 and pyinstaller-hooks-contrib 2026.6 only when building the bundled learning-core executable
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
python3.11 -m venv .venv
.venv/bin/python -m pip install -e 'services/learning-core[dev]'
npm run tauri -- dev
```

In development, Tauri starts only the fixed repository command `.venv/bin/python -m app` from `services/learning-core`; the frontend cannot choose a process or arguments. The supervisor writes the per-process token once through the child's stdin pipe, so it is absent from argv and the child environment. The child owns the port-0 loopback bind, and the supervisor accepts only an exact port announcement from that child pipe before it performs authenticated startup and liveness checks. Each launch runs in an isolated process group and gets a private 0700 PyInstaller extraction directory; cleanup happens only after the group is gone, while stale generations are reclaimed after a previous supervisor crash. The frontend also polls discovery and health and isolates query caches by connection generation, including a restart that reuses the same port with a new token. Plain Vite/browser development remains an explicitly labeled Demo and makes no learning-core calls.

## Learning core

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e 'services/learning-core[dev]'
PYTHONPATH=services/learning-core .venv/bin/python -m app \
  --port 18765 \
  --token 'replace-with-at-least-32-random-characters' \
  --database "$HOME/Library/Application Support/Keen/keen.sqlite3" \
  --seed-demo
```

`--token` and `KEEN_SESSION_TOKEN` remain supported for manual compatibility. The Tauri supervisor uses the stronger stdin protocol instead:

```bash
python3.11 -c 'import secrets; print(secrets.token_hex(32))' | \
  PYTHONPATH=services/learning-core .venv/bin/python -m app \
  --token-stdin \
  --port 18765 \
  --database "$HOME/Library/Application Support/Keen/keen.sqlite3"
```

The launcher binds only to loopback and rejects missing, short, or malformed session tokens. One process exclusively owns a database for its whole lifetime, preventing a second instance from racing migrations, recovery, or temporary uploads. See [the service README](services/learning-core/README.md) for the API and current document/resource limits.

## Checks

```bash
npm run check
source "$HOME/.cargo/env"
cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check
cargo clippy --manifest-path apps/desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
```

With the Vite server already running, capture the first visual artifact:

```bash
npm run visual:test
```

Results are written to the local, gitignored `artifacts/visual-diff/` workspace. They are not durable evidence in a GitHub checkout. A missing authorized reference is reported as `missing_reference`, not a pass.

## Packaging status

The arm64 app embedded in the current DMG contains the PyInstaller learning-core executable. Manual application lifecycle testing covered launch, authenticated loopback health, one bounded restart, enforcement of the restart budget, and shutdown without a residual listener. The automated packaging command builds the sidecar and app, exercises authentication plus isolated PDF parsing/resource limits and full process cleanup, creates one fresh DMG, mounts that exact artifact read-only, verifies its signatures and architectures, and repeats the executable smoke test from the mounted app:

```bash
source "$HOME/.cargo/env"
.venv/bin/python -m pip install 'pyinstaller==6.21.0' 'pyinstaller-hooks-contrib==2026.6'
npm run package:macos
```

`build-sidecar.sh` produces a target-triple-suffixed executable under the gitignored `apps/desktop/src-tauri/binaries/`; the override config declares it as Tauri `externalBin`. The default Tauri configuration intentionally disables bundling so a fresh checkout cannot accidentally publish a sidecar-less installer and can still run Rust tests before packaging.

Without `APPLE_SIGNING_IDENTITY`, `package:macos` creates an ad-hoc local
verification bundle and explicitly disables hardened runtime. This is required
because re-signing a PyInstaller one-file executable as ad-hoc hardened code
causes macOS library validation to reject its extracted Python dylib. With a
real `APPLE_SIGNING_IDENTITY`, the build passes that same identity to
PyInstaller and Tauri and selects the hardened-runtime release config. That
Developer ID path still needs to be exercised with project credentials and
notarized before release.

The current sidecar-bearing arm64 DMG passes `hdiutil verify`; after a read-only
mount, `codesign --verify --deep --strict` passes for the app and embedded
sidecar, and the mounted sidecar repeats the authenticated PDF/resource smoke.
The locally generated 2026-07-16 artifact is 21,761,944 bytes with SHA-256
`da60e4b08bd3b3c8b77e90bbc2c7a7c625009f810d44400a806081242dfc5e87`;
the DMG itself is gitignored rather than committed. Gatekeeper still rejects
the local artifact because it has no Apple Developer ID signature or
notarization ticket. Universal/Intel validation, distribution
signing/notarization, reproducible Python locking, and complete third-party
notices remain release blockers.

## References and third-party code

This checkout does not contain the authorized HyperKnow reference bundle described by the brief, so pixel parity remains blocked and no protected brand asset is reused. No HyperKnow, DeepTutor, or OATutor source has been copied. pypdf, python-multipart, PyInstaller, and PyInstaller community hooks are package/build-tool dependencies recorded in [the open-source inventory](docs/OPEN_SOURCE_INVENTORY.md); their presence does not make the current notice bundle complete. Before protected assets or upstream source are added, follow [AGENTS.md](AGENTS.md), the inventory, and [the upstream patch ledger](docs/UPSTREAM_PATCHES.md).
