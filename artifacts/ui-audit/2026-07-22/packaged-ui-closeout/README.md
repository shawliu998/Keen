# Packaged UI closeout — 2026-07-22

This directory records a bounded inspection of the repository-local ad-hoc
`Keen UI Audit.app` (`com.keen.learning.ui-audit`). It is an isolated audit
identity, not the installed production app and not a signed or notarized
release.

## Build and runtime

```text
VITE_NATIVE_UI_AUDIT=true npm run tauri -- build --bundles app \
  --config src-tauri/tauri.sidecar.conf.json \
  --config src-tauri/tauri.ui-audit.conf.json
```

The final bundle executables were produced at `2026-07-22 13:05:20 +0800`.
`codesign --verify --deep --strict` passed with the configured ad-hoc identity.
`scripts/smoke-bundled-sidecar.sh` passed READY, jobs, cancellation, CJK,
many-to-many course/document state, sqlite-vec, PDF geometry/content, token
handling and cleanup.

The visible audit probe reported matching `inner`, root-client and visual
viewport dimensions with DPR 2:

- 1440×900
- 1220×768
- 1180×740, the configured native minimum

A further shrink attempt remained at 1180×740. The earlier 1000×720 result is
browser-only stress evidence and is not represented as a packaged window.

## Captures

| File | State |
| --- | --- |
| `home-1440x900-light.png` | Empty-source Home, service ready |
| `home-1220x768-light.png` | Empty-source Home, service ready |
| `home-1180x740-minimum-light.png` | Empty-source Home at native minimum |
| `feed-empty-1180x740-minimum-light.png` | Empty Learning Feed at native minimum |
| `feed-calendar-empty-1180x740-minimum-light.png` | Secondary Calendar at native minimum |
| `history-empty-1440x900-light.png` | Empty persisted-record surface |
| `sidecar-recovered-feed-calendar-1180x740-light.png` | UI ready after supervised sidecar replacement |

Native Tab traversal covered Sidebar, Toolbar, Home intent and prompt actions.
Opening Calendar with the keyboard and activating `Back to tasks` returned
focus to `Open calendar`. A targeted normal termination of the exact audit
sidecar parent replaced PID 76471 with PID 22069; the app process remained and
the visible service state returned to `Learning core ready`.

## Repairs found by the packaged pass

- A disabled no-course Feed query no longer leaves Home permanently showing
  both loading and no-course states.
- macOS color-scheme preference now selects the existing light or dark tokens.
- The external Figma HTML-capture script is absent from normal and packaged
  application output.
- Demo task completion is labelled as a visual preview and states that it
  writes no learning data.
- Task Detail programmatic focus is visible, Calendar restores its opener, and
  the Deep Learn rail sizes the actual shared `.icon-button` class.

## Verification and limits

The final desktop suite passed 29 files / 390 tests. Strict TypeScript, ESLint,
the production/audit builds and `git diff --check` passed. The Vite build keeps
its existing chunk-size warning and tests keep the existing React Router future
warnings.

The host preference was Light with reduced motion off. Dark mode and reduced
motion are implemented, but this run did not change macOS settings and does not
claim packaged Dark or `reduced=true` captures. The audit identity contained no
safe persisted long Study Session or Conversation, so long-content packaged
rendering was not invented and remains unverified. The current visual report
contains 16 `missing_reference`, eight provisional comparisons and two failures
against superseded zero-tolerance Home/Feed self-baselines; no pixel-parity or
accepted-replacement-baseline claim exists.
