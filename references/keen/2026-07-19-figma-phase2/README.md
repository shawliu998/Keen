# Keen Figma Phase 2 — Components and Motion

Date: 2026-07-19
Figma file: `ugwiIPdF43v2woYsLM3b9R`
Scope: Figma and evidence documentation only. No React, Tauri, FastAPI, SQLite or packaging behavior changed in this phase.

## Created or completed

| Page | Main node | Coverage |
| --- | --- | --- |
| Icons `79:2` | `Icon/Home` `79:6`, `Icon/CalendarDays` `79:18`, `Icon/FileStack` `79:24` | Production-derived Lucide vectors reused from existing Keen frames; no handcrafted icon approximation. |
| Navigation `80:2` | `Nav Row` `80:56` | Expanded/collapsed × Default/Hover/Focus/Current, Label and Icon swap properties. Default/Hover/Focus variants have 140 ms Smart Animate hover/click reactions to Hover or Current. |
| Progress `89:2` | `Progress` `89:46` | 0/25/50/75/100 geometry at 240×5 px. |
| Segmented Control `91:4` | `Building Blocks/Segment` `91:54`; `Segmented Control` `92:71` | Default/Hover/Focus/Disabled building blocks and three selected positions. |
| Foundation Motion `98:2` | `Motion & Interaction / Documentation` `98:3` | Current 140/220 ms behavior matrix, reduced-motion rules and a standard/reduced progress specimen. |
| Status Indicator `104:2` | `Status Indicator` `104:56` | Ready, Starting, Offline, Error and Not configured with one Label property. |

Two text styles were added for compact segmented controls: `Keen/Control` and `Keen/Control Emphasis`. The file therefore has 11 local Keen text styles after this phase.

## Validation performed

- Re-read component structure, property definitions, text content, font family and token bindings through the Figma Plugin API.
- Confirmed all inspected component text uses SF Pro Regular, Medium or Semibold styles.
- Confirmed Progress indicator widths are 1, 60, 120, 180 and 240 px for 0, 25, 50, 75 and 100 percent specimens.
- Confirmed Nav Row has eight variants and the final hover/click reactions resolve to real variant node IDs with 0.14 second Smart Animate transitions.
- Confirmed the standard motion specimen contains a WIDTH track on node `102:11`, from 48 px at 0 seconds to 240 px at 0.22 seconds with Ease Out. The reduced-motion specimen has no interpolated track.
- Confirmed Status Indicator exposes one `State` variant property and one merged `Label` text property across five variants.
- Visually inspected every screenshot below and repaired title glyph caching, clipped recovery text and the clipped Segmented Control specification.

## Screenshots

- `nav-row.png`
- `progress.png`
- `segmented-control.png`
- `motion-interaction.png`
- `status-indicator.png`

These are direct Figma renders, not accepted product baselines or visual-diff outputs.

## Limitations

- The available Figma tools did not expose video export, so Motion validation covers track/reaction structure and resting screenshots, not sampled animation frames.
- The Segmented Control parent variants use local segment layers rather than nested `Building Blocks/Segment` instances. Automated nested text overrides were blocked by Figma font availability. The visual component set is valid, but full nested-instance composition remains open.
- Figma new-text rendering required an Inter glyph-cache refresh before reapplying the verified SF Pro style. Final node metadata and screenshots were both checked after the workaround.
- No React implementation, runtime keyboard test, responsive-window test, dark-mode screen reconstruction, complete accessibility audit, packaged-app test or accepted reference comparison was performed.
- Status labels are component vocabulary only. They do not prove a provider, sidecar, upload, integration or external service succeeded.
- HyperKnow timing was not independently measured. The motion page records Keen's current `140ms` and `220ms` tokens.

The source-of-truth and conflict policy is recorded in `docs/DESIGN_RUNTIME_CONFLICTS.md`.
