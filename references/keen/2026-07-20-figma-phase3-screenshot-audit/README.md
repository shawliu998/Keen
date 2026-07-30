# Phase 3 Home screenshot correction

Date: 2026-07-20
Figma file: `ugwiIPdF43v2woYsLM3b9R`
Frames: default `113:3`, offline `130:52`, provider missing `131:195`

## Why the previous export looked strange

Fresh 1585×907 exports confirmed four concrete layout defects rather than a subjective style disagreement:

1. `⌘N` exceeded the clipped New Learning Request container by 1 px in all three frames.
2. The default Sidebar status text retained stale Figma glyph bounds and exceeded its clipped parent by 9 px.
3. The page-level operational disclosure floated to the right of the `Today` introduction, visually detached from the task and recovery state.
4. Offline and provider states repeated the same explanation in both the floating disclosure and the queue/error content; their fixed-height state panels also contained unnecessary vertical space.

## Correction

- Removed the redundant page-level disclosure from all three states.
- Kept Browser Demo truthfulness in the toolbar `Demo` status and the queue's `Sample tasks` label.
- Kept offline/provider truthfulness in the toolbar/footer status and the explicit queue/error state.
- Removed the stale default footer status row; `Local workspace` remains bottom-aligned.
- Repaired the `⌘N` text boxes to fit their clipped control containers.
- Expanded the introduction copy area and changed offline/no-task/provider panels from fixed height to content-hugging height.
- Tightened the provider issue panel from 116 px to 95 px and the empty-state panels from 84 px to 74 px.

No React, Tauri, FastAPI, SQLite, service, provider, or persistence behavior changed.

## Evidence

Before:

- `01-default-before.png`
- `02-offline-before.png`
- `03-provider-before.png`

After:

- `04-default-after.png`
- `05-offline-after.png`
- `06-provider-after.png`

The Phase 3 canonical exports were refreshed from the accepted after frames:

- `../2026-07-20-figma-phase3/home-default-final.png`
- `../2026-07-20-figma-phase3/home-offline.png`
- `../2026-07-20-figma-phase3/home-provider-missing.png`

## Validation and limits

Final Plugin API inspection found zero visible text nodes outside a clipping ancestor and zero visible text nodes with non-positive geometry across the three frames. Each final PNG is 1585×907 and was opened after download.

This is a fixed-viewport Figma correction. It is not a React/runtime accessibility, keyboard, responsive, dark-mode, reduced-motion, accepted-baseline, mismatch-percentage, or pixel-parity result.
