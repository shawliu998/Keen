# Packaged Tauri WebView audit — 2026-07-21

This directory is evidence from a newly built local ad-hoc arm64 `Keen.app`,
not a distributed or notarized release. The app was launched from
`apps/desktop/src-tauri/target/release/bundle/macos/Keen.app` and its local
sidecar reported `Learning core ready`.

## Application identity and launch boundary

An older `Keen.app` can remain installed elsewhere on the machine with the
same normal production product identity. Its source revision is not inferred
from the shared `0.1.0` version string, and it is never deleted, overwritten,
or used as this audit's provenance. The normal production identity remains
`Keen` / `com.keen.learning`.

Packaged UI evidence that needs a visible native app must instead use the
separate audit identity `Keen UI Audit` / `com.keen.learning.ui-audit` through
`scripts/open-ui-audit-app.sh`. The script accepts no app path: it verifies the
repository-local audit `Info.plist` display name, bundle identifier and version
before calling `open -n` on that exact absolute path. Its startup output is the
process-path record for the capture. The audit app has its own application-data
identity and cannot validate normal-production user-data migration behavior.

The native application-menu label now comes from the active Tauri config's
`productName`: production remains `Keen`, development is `Keen Dev`, and the
audit bundle is visibly `Keen UI Audit`.

## Captured states

| Capture | Keen state | Window content viewport | Fixture | Reduced motion | Figma node | Baseline decision |
| --- | --- | --- | --- | --- | --- | --- |
| `home-service-ready-window-unverified-1203x768.jpeg` | Home, fresh local data, no course | Screenshot: 1203×768 px; CSS viewport unverified | Fresh packaged local data; no seeded course | Not forced in packaged WebView | Home `113:3` is Approved, but does not specify this live empty state | Rejected: CSS viewport and deterministic fixture/reference are not established |
| `feed-service-ready-window-unverified-1203x768.jpeg` | Learning Feed, no local course | Screenshot: 1203×768 px; CSS viewport unverified | Fresh packaged local data; no seeded course | Not forced in packaged WebView | Learning Feed `162:97` is Approved, but is not this empty state | Rejected: CSS viewport and deterministic fixture/reference are not established |
| `knowledge-empty-service-ready-window-unverified-1203x768.jpeg` | Knowledge Base, no documents | Screenshot: 1203×768 px; CSS viewport unverified | Fresh packaged local data; no documents | Not forced in packaged WebView | No Approved node | Rejected: no CSS viewport, Approved node, or accepted reference |
| `conversation-empty-service-ready-window-unverified-1203x768.jpeg` | New Conversation empty state | Screenshot: 1203×768 px; CSS viewport unverified | Fresh packaged local data | Not forced in packaged WebView | No Approved node | Rejected: no CSS viewport, deterministic fixture, node, or accepted reference |
| `deep-learn-entry-no-course-window-unverified-1203x768.jpeg` | Study-intent Home entry; no course | Screenshot: 1203×768 px; CSS viewport unverified | Fresh packaged local data; no course | Not forced in packaged WebView | No Approved Deep Learn node | Rejected: no CSS viewport, deterministic fixture, node, or accepted reference |
| `deep-learn-entry-keyboard-focus-window-unverified-1203x768.jpeg` | Study-intent Home with native keyboard focus on Review due | Screenshot: 1203×768 px; CSS viewport unverified | Same fresh local data | Not forced in packaged WebView | No applicable node | Audit evidence only; not a baseline |
| `sidebar-collapsed-window-unverified-1203x768.jpeg` | Study-intent Home after Sidebar collapse | Screenshot: 1203×768 px; CSS viewport unverified | Same fresh local data | Not forced in packaged WebView | No applicable node | Audit evidence only; `Expand sidebar` was invoked and restored successfully |
| `service-recovered-window-unverified-1203x768.jpeg` | Study-intent Home after a supervised sidecar replacement | Screenshot: 1203×768 px; CSS viewport unverified | Same fresh local data; the current packaged sidecar child was terminated for this test | Not forced in packaged WebView | No applicable node | Bounded recovery evidence only: a replacement sidecar appeared and the UI returned to `Learning core ready`; the transient unavailable UI was not captured |

## Native CSS viewport probe

An isolated ad-hoc `Keen UI Audit.app` was built with bundle identifier
`com.keen.learning.ui-audit`. The normal production build does not enable its
probe; the probe is compiled in only when `VITE_NATIVE_UI_AUDIT=true`. It
reports the WKWebView's live `window.innerWidth`, `window.innerHeight`, root
client size, `visualViewport`, device-pixel ratio and reduced-motion media
query in both visible text and the document title.

| Capture | Native action | Live WKWebView result | Boundary |
| --- | --- | --- | --- |
| `native-ui-audit-css-1440x920-reduced-false.jpeg` | Launched the independent packaged audit app at its configured default size | `inner=1440x920`; `client=1440x920`; `visual=1440x920`; `dpr=2`; `screen=1728x1117`; `reduced=false` | The JPEG capture service downscaled this screenshot to 1203×768 pixels; the CSS dimensions come from the visible live probe, not the image dimensions. This is audit evidence, not a visual baseline. |
| `native-ui-audit-css-1180x740-reduced-false.jpeg` | Resized the native window by its lower-right edge to the configured minimum | `inner=1180x740`; `client=1180x740`; `visual=1180x740`; `dpr=2`; `screen=1728x1117`; `reduced=false` | A second drag toward a smaller size left all three CSS sizes at 1180×740, confirming the native minimum constraint. This is audit evidence, not a visual baseline. |

Commands that completed for this probe:

```text
npm run typecheck
VITE_NATIVE_UI_AUDIT=true npm run tauri -- build --bundles app \
  --config src-tauri/tauri.sidecar.conf.json \
  --config src-tauri/tauri.ui-audit.conf.json
codesign --verify --deep --strict --verbose=2 \
  "apps/desktop/src-tauri/target/release/bundle/macos/Keen UI Audit.app"
```

TypeScript typecheck, the production frontend build used by the bundle and
strict deep ad-hoc signature verification passed. The build retained the
existing Vite chunk-size warning and expected no-notarization warning. The
packaged media query proved only the current `reduced=false` state. Computer
Use could not read the System Settings app because its native control channel
closed, so the system preference was not changed and a packaged
`reduced=true` state remains unverified.

This packaged matrix also does not exercise long learning content or the
transient unavailable UI. Those remain unverified packaged states; earlier
browser/Figma evidence does not substitute for this matrix.

The following normal-production checks also completed after the audit build:

```text
npm run lint --workspace=@keen/desktop
npm run build --workspace=@keen/desktop
rg -n "Native UI audit metrics|visualViewport" apps/desktop/dist
git diff --check
```

Lint, the normal production build and `git diff --check` exited successfully.
The `rg` command exited 1 (no audit-probe text in normal `dist`), which is the
expected exclusion result.

## Related deterministic visual run

`tools/visual-regression/run.mjs` captured its configured Browser Demo and
visual-core fixtures with a 1× device scale factor, explicit viewport per
`tools/visual-regression/visual.config.json`, disabled transitions, and
`reducedMotion: "reduce"`. Its 2026-07-21 report is
`artifacts/visual-diff/report.json`: 16 `missing_reference` results and eight
`compared` results against explicitly `provisional` Figma exports. The report
is current-product evidence only. No packaged screenshot or Browser Demo
capture is an approved Keen visual baseline, and no pixel-parity result exists.
