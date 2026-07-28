# Keen Figma Phase 4: compact Home and componentized Learning Feed

Date: 2026-07-20
Figma file: `ugwiIPdF43v2woYsLM3b9R`
Editable file: <https://www.figma.com/design/ugwiIPdF43v2woYsLM3b9R>

This phase is Figma-only. It does not change React, Tauri, FastAPI, SQLite,
authentication, sidecar behavior, provider behavior, document ingestion, RAG,
calendar integration, task persistence, or packaged application behavior.

## Editable design inventory

| Item | Figma node | State / size | Evidence |
| --- | --- | --- | --- |
| Home compact | `155:187` | Browser Demo, 1180×740 | `home-compact-1180x740-final.png` |
| Feed task card | `159:220` | Default, Hover, Selected | `feed-task-card-component-final.png` |
| Calendar event | `160:111` | Active Default/Hover/Selected, Overdue Default, Complete Default | `calendar-event-component-final.png` |
| Learning Feed default | `162:97` | Browser Demo, nominal Figma frame 1585×941 | `feed-componentized-final.png` (1585×942 raster export because of Figma fractional render bounds) |
| Learning Feed compact | `164:179` | Browser Demo, 1180×740 | `feed-compact-1180x740-final.png` |
| Selected task default | `172:262` | Browser Demo, nominal Figma frame 1585×941 | `feed-selected-task-default-final.png` |
| Selected task compact | `176:340` | Browser Demo, 1180×740 | `feed-selected-task-compact-final.png` |
| Local service unavailable | `178:418` | Local state, 1180×740 | `feed-state-unavailable-1180x740.png` |
| Authenticated-health loading | `179:596` | Local state, 1180×740 | `feed-state-loading-1180x740.png` |
| No local courses | `179:998` | Local empty state, 1180×740 | `feed-state-empty-1180x740.png` |
| Live-data validation error | `179:1400` | Local error state, 1180×740 | `feed-state-error-1180x740.png` |

The exact runtime/data boundary is recorded in
`docs/figma/LEARNING_FEED_DATA_MAPPING.md`.

## Design decisions

- The compact Home is a real reflow, not a scaled desktop screenshot: the
  Sidebar remains 212 px and the main reading/composer column is bounded at
  720 px.
- Learning Feed keeps the implemented task rail + month calendar structure.
  It does not add the reference product's Week mode, external calendar state,
  quota controls, upgrade affordances, or branding.
- Task cards are reusable instances with editable title, due, rationale,
  status, course, duration, concepts, and visual state properties.
- Calendar event labels use one-line ending truncation at compact widths. The
  compact calendar still renders all seven columns; it does not horizontally
  crop a desktop calendar.
- At 1180×740 the task rail is vertically scrollable, so the second card
  continues below the visible frame. That is expected scroll content, not a
  hidden success state or lost task.
- Task detail replaces the calendar while retaining the selected task in the
  rail. Its 68% mastery value is explicitly labelled `Illustrative sample`,
  and Snooze/Complete are described as Browser Demo updates that create no
  real session.
- Loading, empty, unavailable and validation-error screens use the current
  React recovery copy. They use an empty Month calendar and never substitute
  Browser Demo tasks for unavailable local data.

## Figma QA evidence

Plugin API inspection after the final edits reported:

- Home compact `155:187`: 1180×740, 11 visible instances, 28 visible text
  nodes, zero missing fonts, zero non-finite geometry, zero horizontal or
  vertical root overflow.
- Learning Feed default `162:97`: 1585×941, seven visible instances, 104
  visible text nodes, zero missing fonts, zero non-finite geometry, zero root
  overflow.
- Learning Feed compact `164:179`: 1180×740, seven visible instances, 103
  visible text nodes, zero missing fonts, zero non-finite geometry, and zero
  horizontal root overflow. The recorded vertical overflow consists of the
  lower task-card content in the scrollable rail.
- Selected task default `172:262` and compact `176:340`: zero missing fonts,
  zero non-finite geometry and zero horizontal root overflow. The compact
  content column scrolls while the truthful next-action footer remains visible.
- Operational screens `178:418`, `179:596`, `179:998` and `179:1400`: zero
  missing fonts, zero non-finite geometry and zero horizontal root overflow.
  `feed-operational-states-contact-sheet.png` is the four-state visual review
  sheet.

The initial compact Feed export retained desktop fixed grid tracks and showed
only four calendar columns. `feed-compact-1180x740-v1.png` is retained as the
rejected diagnostic capture; the final export uses flexible seven-column and
six-row tracks. The earlier `*-component.png` and `*-v1.png` files are working
captures, not final acceptance images.

## Reference and acceptance limits

`references/hyperknow/2026-07-19-figma-screen-audit/04-learning-feed-month.png`
was used as authorized qualitative layout evidence for rail/calendar density.
It was compared against Keen's current raw Feed export before componentization.
The products, state semantics, and captured viewport differ, and no accepted
same-size reference or visual-diff threshold exists. These screenshots therefore
support design review only; they do not establish pixel parity or a visual
regression pass.

The current React task-detail screenshot
`artifacts/ui-audit/2026-07-19-post-completion-audit/03-task-detail-1440x920.png`
was placed beside `feed-selected-task-default-v1.png` in
`feed-selected-task-comparison-v1.png`. The comparison is qualitative because
the shell and viewport differ; it verifies hierarchy and content treatment,
not pixel parity.

Runtime keyboard navigation, reduced motion, actual live loading/error/offline
captures, Tauri rendering, React implementation of this Figma slice, and
accepted visual-regression baselines remain pending.

## Subsequent bounded implementation

Later on 2026-07-20, the first React convergence pass implemented the compact
Home measure and selected-task layout behavior. Its before/after screenshots
and verification limits are under
`artifacts/ui-audit/2026-07-20/react-figma-convergence/`. Figma Button `33:2`
also moved all 18 labels from unavailable SF Pro Medium to Inter Medium.
Code Connect was attempted but the current account lacks the required
Organization/Enterprise Dev or Full seat. Live operational-state capture,
complete keyboard/accessibility checks and accepted visual baselines remain
pending; no pixel-parity claim was added.
