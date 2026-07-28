# HyperKnow authenticated flow audit — 2026-07-19

This folder contains internal design-research evidence covered by
`references/authorized-scope.md`. It is not redistributable Keen product art and
is not an accepted pixel-regression baseline.

## Capture scope

- Source: `https://agent.hyperknow.io/`, using the user's already authenticated
  Chrome session.
- Captured: 2026-07-19, Asia/Shanghai.
- Product captures: 1488×851 main-area crops for most states; Learning Feed was
  captured at 1700×777 with the compact Sidebar. The earlier signed-out blocker
  remains as `00-auth-blocked.png` at 1280×720.
- Upload fixture:
  `references/audit-fixtures/hyperknow-ui-audit-sample.txt` — synthetic,
  non-personal and uploaded exactly once for this audit.
- No HyperKnow implementation source, browser storage or private network traffic
  was inspected or copied.

## Captured sequence

1. `01-knowledge-base-empty.png` — empty Knowledge Base.
2. `02-new-menu.png` — anchored New menu.
3. `03-upload-processing.png` — inline processing tile.
4. `04-upload-complete.png` — completed file tile.
5. `05-file-card-hover.png` — hover actions.
6. `06-quota-popover.png` — compact plan-usage popover.
7. `07-file-actions.png` — file overflow menu; Delete was not executed.
8. `08-deep-learn-entry.png` and `09-deep-learn-filled.png` — selected Deep
   Learn intent and filled request.
9. `10-deep-learn-starting.png` and `11-deep-learn-result.png` — disabled
   start state, visible creation trace and result card.
10. `12-deep-learn-outline.png` — two-unit outline.
11. `13-session-thinking.png` through `17-next-step-content.png` — reading,
    completion, next-step loading and resumed content/progress states.
12. `18-account-menu.png`, `19-settings-general-cropped.png` and
    `20-settings-integrations.png` — generic account menu and settings. The
    General capture is cropped to exclude identity.
13. `21-learning-feed-empty.png` and `22-learning-feed-week.png` — empty Month
    and Week schedule states.

## Design findings used by Keen

- File work happens in place: processing overlays the stable tile and completion
  swaps the preview without a success modal.
- Deep Learn creation exposes a short audited activity trace before a result card.
- The study session is organized as a compact progress/path rail beside a long,
  editorial reading column. Definition/key-point content uses thin vertical
  accents rather than nested rounded cards.
- Unit completion and recovery are inline. The next-step loading state updates
  the path rail and gives one stop action instead of inventing completed content.
- Settings and quota details use anchored popovers or one centered modal; no large
  disabled navigation inventory is shown.
- Measured visible transitions were generally 150–200 ms ease; Sidebar labels and
  collapsible learning-path sections used roughly 300 ms transitions. Reduced
  motion was not independently verified on the reference product.

## Privacy and capability boundary

- Existing user-created sidebar content was excluded from the retained product
  crops. No screenshot containing account identity or saved personal memory was
  retained.
- No calendar connection, integration sign-in, destructive delete or external
  share was performed.
- HyperKnow-generated study text is reference evidence only. It is not shipped as
  Keen learner data, a model result, a citation or a verified source.
- These captures support qualitative layout and interaction adaptation only. The
  viewports do not align with the current Keen Browser Demo, so no pixel-parity or
  mismatch-percentage claim is valid.
