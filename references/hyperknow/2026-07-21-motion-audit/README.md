# HyperKnow interaction and motion audit — 2026-07-21

Internal design-research evidence only. These captures are covered by
`references/authorized-scope.md`; they are not redistributable Keen product art
or accepted pixel-regression baselines.

## Capture conditions

- Source: `https://agent.hyperknow.io/`
- Session: the user's authenticated Chrome tab
- Captured: 2026-07-21, Asia/Shanghai
- CSS viewport: 1585 × 851
- Device pixel ratio: 2
- Captures crop the 240 px account Sidebar so existing conversation titles and
  account content are not retained.
- Only the previously authorized synthetic photosynthesis learning session was
  inspected. No file upload, integration, calendar write, destructive action,
  browser storage, or private network traffic was used.

## Accepted captures

1. `01-deep-learn-long-content-main.png` — stable learning-path rail, editorial
   reading column, thin definition callout, source chip, generated figure slot,
   and fixed continuation composer.
2. `02-home-tools-menu-main.png` — anchored tool menu opened from the composer.
3. `03-deep-learn-restore-skeleton-main.png` — restoration skeleton preserving
   the final rail, content, header controls, and composer geometry.

## Visible measurements

- Expanded Sidebar: 240 px; width transition 300 ms with
  `cubic-bezier(0.4, 0, 0.2, 1)`.
- Step and ordinary control transitions: 150–200 ms.
- Home tool menu: 200 × 80 px, 12 px radius, one neutral border, anchored below
  the 75 × 33 px trigger; entry animation 200 ms ease-out.
- Tool menu row: 186 × 35 px, 8 px radius, 14 px label, 150 ms hover transition;
  hover changes only the neutral fill.
- Deep Learn status text uses a 400 ms entrance and a 300 ms checkmark state
  change. These are qualitative references, not a requirement to reproduce the
  exact animation name.

## Keen contract produced from this audit

- Use HyperKnow as the page-composition source and DeepTutor as the interaction
  engineering reference.
- Preserve the final layout during loading.
- Keep the learning rail, reading column, and bottom continuation action stable
  while the current step changes.
- Restrict ordinary transitions to 150–200 ms and coordinated Sidebar/panel
  movement to 300 ms.
- Prefer flat content, quiet borders, selection fills, and inline state changes
  over nested cards, floating assistant surfaces, success modals, or decorative
  motion.

The resulting production rule is recorded in `docs/DESIGN_DIRECTION.md` under
`Frozen reference responsibilities` and `Frozen interaction and motion
contract`.
