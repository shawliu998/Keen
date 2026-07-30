# BYOK provider local Alpha package evidence

Date: 2026-07-28

## Artifacts

- App:
  `apps/desktop/src-tauri/target/release/bundle/macos/Keen.app`
- DMG:
  `apps/desktop/src-tauri/target/release/bundle/dmg/Keen_0.1.0_aarch64.dmg`
- DMG size: `34,275,318` bytes
- DMG SHA-256:
  `87072d5c06cda56a0c1a527523887fac03c985d03bbc8b080b8cfe197083e0e2`
- Main executable architecture: `arm64`
- Frozen learning-core architecture: `arm64`

## Command

```bash
npm run package:macos
```

The command exited `0` after:

- rebuilding the Python 3.11 frozen sidecar from the locked dependencies and
  migrations `001–032`;
- building the production React frontend and release Rust binary;
- creating an ad-hoc signed DMG and standalone app;
- verifying the DMG checksum, mounted app, matching architectures, deep
  ad-hoc signature, and embedded notices;
- running the frozen-sidecar import/index/PDF/sqlite-vec/cancellation smoke;
- running the three-generation Review/FSRS restart and idempotent replay smoke;
- running the new three-generation Mock OpenAI-compatible Provider journey.

## Mock Provider journey

The journey used no vendor account or API key. Against a loopback server whose
explicit API base ended in `/api/v1`, the frozen sidecar:

1. tested the configured model at `/api/v1/models`;
2. imported and indexed an Eigenvectors source in a fresh database;
3. generated a structurally cited answer through
   `/api/v1/chat/completions`;
4. created and persisted a focused-study Task, Session, and visible plan;
5. restarted with a missing model and returned a retryable provider failure
   without losing the Session;
6. restarted with the correct model, rejected the previous generation token,
   revalidated the model, restored the same Session, and replayed the original
   focused-study request without duplicate state.

This verifies the packaged transport, explicit API-base mapping, failure and
recovery behavior, local persistence, token rotation, and idempotency. It does
not certify a live vendor.

## Distribution boundary

`codesign --verify --deep --strict` passed. `spctl --assess` rejected the app
because this local Alpha is ad-hoc signed and not notarized. Developer ID,
hardened runtime, notarization, stapling, and clean-Mac public-install
acceptance remain required for frictionless external distribution.
