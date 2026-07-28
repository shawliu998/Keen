# Round 03 packaged verification

## Build

Command:

`npm run tauri --workspace=@keen/desktop -- build --bundles app --config src-tauri/tauri.sidecar.conf.json`

Result: exit 0. A production `Keen.app` was built at
`apps/desktop/src-tauri/target/release/bundle/macos/Keen.app`. The build used
an ordinary local ad-hoc signature; Developer ID signing and notarization were
not attempted.

## Signature

Command:

`codesign --verify --deep --strict --verbose=2 apps/desktop/src-tauri/target/release/bundle/macos/Keen.app`

Result: exit 0; the app was valid on disk and satisfied its designated
requirement.

## Bundled learning core

Command:

`scripts/smoke-bundled-sidecar.sh`

Result: exit 0. The bundled sidecar reached READY and passed the repository
smoke for jobs, cancellation, CJK, same-hash multi-course behavior,
sqlite-vec, PDF geometry/content, token handling and cleanup.

## Native inspection

The freshly relaunched packaged app reached `Learning core ready`. Home,
Knowledge Base, Learning Feed, History, Review, Settings Status and Settings
Model were inspected through the macOS accessibility tree and captured at
1203×768. The exact zero-data Knowledge Base, History and Review states are
therefore packaged-WebView evidence rather than browser-fixture assumptions.

This is not a full WCAG audit, Dark/reduced-motion acceptance, Developer ID
release attestation, notarization result or pixel-parity claim.
