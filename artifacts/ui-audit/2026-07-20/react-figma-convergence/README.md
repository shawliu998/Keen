# React / Figma convergence check

Date: 2026-07-20

This directory contains Browser Demo screenshots captured from the runnable
React app in Google Chrome with `prefers-reduced-motion: reduce` at 1180×740
and 1585×941. `*-before.png` records the pre-convergence state and
`*-after.png` records the bounded Home, Learning Feed and selected-task pass.

The approved Figma direction is in file `ugwiIPdF43v2woYsLM3b9R`, primarily
nodes `155:187`, `164:179`, and `176:340`. The harness now compares their
1180×740 exports with the matching deterministic Browser Demo states. These
references remain provisional design exports rather than accepted product
baselines, so the measured differences below are not parity or pass claims.

Verified in the 1180×740 Browser Demo capture:

- the Home reading/composer column is 720 px and keeps explicit Sample/Demo
  provenance without duplicating the same disclosure in the content header;
- the Feed and selected-task view have no horizontal document overflow;
- selecting the second task scrolls only the task rail (`scrollTop: 205`) and
  leaves the window at `scrollY: 0` with the task-detail toolbar visible at
  61 px from the window top;
- the first eight Tab stops on Home are visible and carry the shared focus-ring
  box shadow at both inspected sizes;
- synthetic uninterrupted long task/detail headings introduce zero document,
  task-panel, or rail horizontal overflow;
- reduced motion was requested for every capture and confirmed through the
  browser media query.
- the compact task-detail panel now follows the measured 11 px inset, 30 px
  content measure and taller fixed footer; its programmatically focused heading
  remains focus-managed without receiving a control-style outline;
- `visualTest=true` freezes the Browser Demo calendar to July 2026 and the
  optional `selectedTask` parameter selects a stable task for screenshots. This
  fixture is gated to Demo and does not create or alter live service data.

The configured visual harness was rerun at 1180×740. Provisional comparisons:

- Home: 1.9878607420980303%;
- Learning Feed: 1.5549702244617498%;
- selected task detail: 3.1582684379294546% (improved from 4.344938158497481%).

Seven older routes still return `missing_reference`. The machine-readable
result and current/diff PNGs live under `artifacts/visual-diff/`.

## Operational states

The same-size comparison now also covers the four compact Figma operational
states. Their development fixture is browser-only, requires `visualTest=true`
plus an explicit `visualCoreState`, and performs no Tauri or network request.
It is screenshot infrastructure, not evidence that a sidecar action ran.

- local service unavailable: 1.3141319285387083%;
- authenticated startup/health loading: 1.2183921209344937%;
- no local courses: 1.0565735226752175%;
- invalid live data: 1.3680714612918004%.

The runtime intentionally differs from the no-course Figma footer: the shared
Sidebar says `Learning core ready`, while the page says `No local courses yet`.
Service health and course inventory are separate states. Chrome checks at
1180×740 found no horizontal overflow, confirmed reduced motion, and reached
`Restart learning core` and `Retry data load` by keyboard with the shared
three-pixel focus ring.

## Deep Learn reading continuity

The default Browser Demo is compared at 1585×950 with editable Figma node
`65:2`. The latest result is 1.6019923626099952%; the current/reference/diff PNGs are
`artifacts/visual-diff/{current,diff}/deep-learn-figma-default.png` and
`artifacts/figma/page-baselines/keen-deep-learn-live-capture-1585x950.png`.
The frame is a provisional current-product export, not an accepted competitor
baseline, so the number is comparison evidence rather than a parity pass.

The code keeps the session header and side rails sticky for long reading and
moves focus to the selected unit heading or submitted feedback. The focused
Deep Learn suite passed 21/21 and the visual harness refreshed the existing
1100×760 Summary capture. Scripted Chrome checks at 1180×740 and 900×700 found
zero horizontal document overflow and confirmed reduced motion. After 1200 px
of QA-only injected lesson scrolling, the session header remained at y=46 and
the learning-path rail at y=128; keyboard activation of Next unit focused the
new `The eigenvalue equation` heading. The injected long copy exists only in
the browser QA run and is not a shipped demo, model reply, citation or learner
record. Captures are `deep-learn-compact-1180x740.png`,
`deep-learn-compact-long-content.png`, `deep-learn-narrow-900x700.png`, and
`deep-learn-narrow-long-content.png` in this directory.

The follow-up accessibility/distillation pass consolidates the repeated Demo
copy, replaces the nested lesson `main` with a labelled section, raises light
tertiary text from 4.26:1 to approximately 4.70:1 on white, and condenses the
primary Sidebar to a 60 px labelled icon rail below 1000 px. Fresh 1585×950 and
900×700 checks found one `main`, zero horizontal overflow, active reduced motion
and correct focus transfer to the next lesson heading. The new captures are
`deep-learn-distilled-default-1585x950.png` and
`deep-learn-distilled-narrow-900x700.png`. The small mismatch increase reflects
intentional copy/contrast changes against the older provisional Figma export;
it is not a regression verdict or parity claim.
