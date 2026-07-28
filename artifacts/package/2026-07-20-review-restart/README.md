# Packaged Review restart evidence — 2026-07-20

This ledger records a local ad-hoc arm64 packaging run. It is packaged-service
lifecycle evidence, not automated GUI interaction, notarization, or a release
signature result.

## Commands and results

- `./scripts/package-macos.sh` — passed.
  - Sidecar migration packaging validation covered the continuous `001`–`026` tree.
  - The build-tree frozen sidecar passed the existing authenticated health,
    indexing, cancellation, CJK, M:N linking, sqlite-vec, PDF geometry/content,
    token-secrecy, and process-cleanup smoke.
  - The build-tree frozen sidecar passed the Review restart smoke across three
    process generations and three tokens.
  - The DMG was created and its checksum was accepted by `hdiutil verify`.
- `./scripts/verify-macos-dmg.sh /Users/a1-6/Documents/Keen/apps/desktop/src-tauri/target/release/bundle/dmg/Keen_0.1.0_aarch64.dmg` — passed after the Review smoke was added to the mounted-DMG gate.
  - Strict deep code-signature validation passed for the ad-hoc app.
  - Main app and sidecar were both arm64.
  - Embedded `THIRD_PARTY_NOTICES.md` matched the repository copy.
  - Both bundled-sidecar smoke suites passed from the mounted app.
  - No bundled sidecar process remained after verification.

## Review assertions

The Review smoke uses one explicitly labelled SQLite fixture because Keen does
not expose an arbitrary-card creation route. Product behavior is exercised only
through the frozen authenticated HTTP service:

1. Start the frozen sidecar once to migrate and seed the isolated database.
2. Insert one due local Review fixture while the service is stopped.
3. Start with a new token, reject the old token, read the due item, and record
   one `good` FSRS rating.
4. Restart with another token, reject the previous token, confirm the item is no
   longer due, and replay the exact rating/idempotency key.
5. Confirm revision `1` and exactly one persisted attempt in SQLite.

## Artifact

- File: `Keen_0.1.0_aarch64.dmg`
- Size: `34,084,916` bytes
- SHA-256: `01c4310ebdef3ea7ed9cb90b71bda1bbc0965ac44f929adf2afb531753642769`
- Signing: local ad-hoc
- Notarization: not performed

## Remaining boundary

The packaging gate does not click the Tauri webview or validate macOS assistive
technology behavior. A separate bounded, isolated release-app check captured a
user-visible reconnect transition, rating and post-restart persistence under
`artifacts/ui-audit/2026-07-20/packaged-review/`; it is manual GUI evidence, not
automated `.app` lifecycle coverage.
