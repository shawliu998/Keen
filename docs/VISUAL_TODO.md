# Visual Reference and Regression TODO

## Current gate

At the initial 2026-07-15 audit, `references/` did not exist. There are no authorized screenshots, recordings, Figma exports, or brand assets to measure. No page can currently be described as pixel-matched, and no `<3%` mismatch result can be computed.

The product may proceed with the brief's provisional tokens and non-branded placeholders. Those values must remain identifiable as provisional until measured from authorized references.

## Authorization intake

Resolve these before copying any protected visual asset:

- [ ] Supply one canonical authorization document. The brief names both `references/authorized-scope.md` and `references/notes/authorized-scope.md`.
- [ ] List every allowed screenshot, recording, Figma export, icon, illustration, logo, and Orbie asset.
- [ ] State allowed use: inspect only, derive measurements, modify, redistribute in source, and/or redistribute in built artifacts.
- [ ] Record prohibited pages/assets and any attribution or expiration conditions.
- [ ] Ensure no authenticated-page scraping or competitor-private asset enters `references/`.

## Missing page references

| Priority | Page/state | Required evidence | Status |
| --- | --- | --- | --- |
| P0 | Shared 1440×920 shell | Expanded Sidebar, Toolbar, main canvas, Inspector, traffic-light/titlebar relationship | Missing |
| P0 | Home / Agent | Default, composer focus, attachment/context menu, generating, stopped, recommendation cards | Missing |
| P0 | Conversation | Streaming, markdown/table/code/KaTeX/Mermaid, citations, tool trace, source preview/highlight | Missing |
| P0 | Knowledge Base | List/grid, drop state, each index status, failed/partial, document Inspector/preview | Missing |
| P0 | Deep Learn | Goal, diagnostic, map, unit, checkpoint, recall, practice, summary, paused/resumed | Missing |
| P0 | Quiz / Practice | Each item type, hint/scaffold depth, feedback, completion summary | Missing |
| P1 | Learning Feed | Today/upcoming/overdue/completed, course filters, rationale/trace, empty/error | Missing |
| P1 | Settings | All sections, provider states, secret input, notices | Missing |
| P1 | Flashcards | Front/back, rating controls, due/empty/edit/source states | Missing |
| P1 | Study Planner | Syllabus import, constraints, daily plan, reschedule, calendar proposal/confirm | Missing |
| P1 | Memory / Persona | Goals, preferences, evidence, inference, edit/delete/disable | Missing |
| P2 | Visualize | Task progress, Mermaid/SVG preview, error, export; later Manim states | Missing |
| P2 | Responsive shell | 1180×740 minimum, resized Sidebar, collapsed icon rail, Inspector hidden/collapsed | Missing |

For every page above, also collect its empty, loading, partial, error, offline, permission-denied, cancelled, sidecar-unavailable, and applicable provider/index/migration failure state.

2026-07-16 hardening note: the implemented shell now distinguishes binding, migrating, recovering, starting-server, health-checking, restarting, unavailable, and configuration-error service states. No authorized reference or new screenshot/diff evidence exists for these states, so their visual acceptance remains missing.

2026-07-16 Gate 3 note: Knowledge Base now has real course selection, multi-course labels, relation actions, course filters, and partial course-state errors. These states passed component/integration behavior tests, but no authorized visual reference or screenshot/diff evidence exists, so visual acceptance remains missing.

2026-07-16 Gate 4 note: Knowledge Base now renders provider-missing/failure, indexed-lexical, indexed-hybrid, embedding, cancelled/interrupted, and needs-reindex states with real warnings and actions. Component/integration behavior tests passed, but no authorized reference or screenshot/diff exists; visual acceptance and any parity claim remain blocked.

2026-07-16 Gate 5 note: Conversation now renders real Tauri streaming, locally stopped, provider-missing, disconnected, lexical-only, structural-citation, and empty live states; Browser Demo is explicitly labeled and performs no request. Behavioral tests passed, but no authorized reference or visual-diff evidence exists, so visual acceptance remains missing.

2026-07-16 Gate 6 note: Conversation now opens an authenticated page-on-demand PDF citation dialog with supported-geometry highlights, original excerpts, truthful loading/offline/error/page-only states, bounded canvas allocation, keyboard focus trapping/restoration, and a bundled local PDF.js worker. Behavioral tests passed, but no authorized reference screenshot or visual-diff evidence exists; no pixel-parity claim is made.

## Reference manifest fields

Every accepted reference should have a manifest entry with:

- stable `reference_id` and source file path;
- page/route and state name;
- capture viewport in CSS pixels and display scale;
- app/version/capture date if known;
- required deterministic seed fixture;
- authorization-scope entry;
- higher-resolution/newer precedence information;
- ignored dynamic regions and why;
- mismatch threshold (default target below 3% for primary pages);
- notes for expected macOS-native variance.

## Regression harness status

- [x] Create `tools/visual-regression/` without fabricated baseline images.
- [x] Add a machine-readable page manifest (schema validation remains open).
- [x] Start from deterministic frontend seed data and a direct route.
- [x] Disable motion/transitions/caret and request reduced motion (fixed clock/locale/timezone remain open).
- [x] Capture the Home application viewport at 1440×920 and display scale 1.
- [x] Produce `current` and a machine-readable report under `artifacts/visual-diff/`; diff and mismatch are emitted only when a real reference exists.
- [ ] Exclude only documented truly dynamic regions.
- [ ] Retain failed artifacts in CI.
- [ ] Iterate in order: layout, panel widths, typography, spacing, color/border, radius, shadow, icons, micro-motion.
- [ ] Record measured colors and dimensions in `packages/design-tokens`; do not silently overwrite provenance.

## Provisional design values

The values supplied in the brief—such as `#F6F8FA` app background, 248 px Sidebar, 336 px Inspector, and 52 px Toolbar—are starting hypotheses, not reference measurements. Implementation and tests should name them accordingly until a manifest-backed measurement replaces them.

## Visual acceptance record

A current-image run has completed, but comparison cannot run without an authorized reference. `missing_reference` is a blocker state, not a pass.

| Date | Reference ID | Route/state | Viewport | Seed | Mismatch | Artifact paths | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-15 | Missing | `/?demo=true&visualTest=true` | 1440×920 @1x | Deterministic frontend seed | Not computed | `artifacts/visual-diff/current/home.png`, `artifacts/visual-diff/report.json` | `missing_reference`; no parity claim |
