# Deep Learn closed-book Recall runtime check

Date: 2026-07-25
App: local ad-hoc Debug `Keen Dev.app` (`com.keen.learning.dev`)
Viewport evidence: 1220×768 captured image pixels

The current worktree was rebuilt with:

```text
npm run tauri -- build --debug \
  --config src-tauri/tauri.dev.conf.json \
  --config src-tauri/tauri.sidecar.conf.json \
  --bundles app
```

The bundled arm64 desktop and learning-core executables passed strict deep
code-signature verification. The app restored persisted session
`focused-session-151b83d4-fed0-5f35-88ab-2c359f0979b2` after a complete
app/sidecar restart.

Verified in the restored pending Recall:

- the learning core returned to `ready`;
- the phase is exposed as `Closed-book recall step`;
- the generated `Study: <goal>` title is not followed by a duplicate goal line;
- the source-derived lesson and Inspector are absent;
- the response textarea owns focus;
- the disabled submit action is skipped by keyboard traversal;
- the learning-path rail can collapse and expand without exposing lesson text.

SQLite was inspected read-only after capture. The session remained
`active_recall`, revision `6`, progress `0.0`; its single Recall run remained
`pending`, with no answer idempotency key, mastery event, or Review handoff.
No Recall answer was submitted.

Files:

- `closed-book-recall-expanded.jpg`
- `closed-book-recall-collapsed.jpg`

These screenshots verify this local Debug runtime state only. They are not an
accepted visual-regression baseline, pixel-parity result, Developer ID build,
notarized release, Dark capture, reduced-motion-on capture, long-answer result,
or complete accessibility audit.
