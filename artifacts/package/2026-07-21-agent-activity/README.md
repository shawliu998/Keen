# Agent Activity UI package refresh — 2026-07-21

This ledger records the local ad-hoc arm64 package refresh after the bounded
Agent Activity visual distillation. It is not notarization, Developer ID
signing, automated GUI interaction, or a release signature result.

## Commands and results

- `./scripts/package-macos.sh` — build-tree app creation and both bundled
  sidecar smoke suites passed; the first generated DMG-script invocation failed
  before producing an image.
- `CI=true npm run tauri --workspace=@keen/desktop -- build --bundles dmg --config src-tauri/tauri.sidecar.conf.json` — the bounded DMG retry passed.
- `./scripts/verify-macos-dmg.sh /Users/a1-6/Documents/Keen/apps/desktop/src-tauri/target/release/bundle/dmg/Keen_0.1.0_aarch64.dmg` — passed.
  - `hdiutil verify` accepted the checksum.
  - Strict deep ad-hoc code-signature validation passed.
  - Main app and bundled sidecar were arm64.
  - Authenticated health, indexing, cancellation, CJK, M:N linking,
    sqlite-vec, PDF geometry/content, token handling and cleanup smoke passed.
  - Review token rotation, due read, FSRS rating, restart recovery, idempotent
    replay and single-attempt persistence smoke passed.

## Artifact

- File: `Keen_0.1.0_aarch64.dmg`
- Size: `34,084,482` bytes
- SHA-256: `ba49211cd61d98591054a501b1a6b010bd17fcbf1ed2e8d4eaa45c0458d21df6`
- Signing: local ad-hoc
- Notarization: not performed

## Remaining boundary

The empty Agent Activity visual fixture is development-only and explicitly
states that no Agent ran or data changed. Its current screenshot has no accepted
reference. The packaging gate does not automate Tauri webview interaction or
macOS assistive-technology behavior.
