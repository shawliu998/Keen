# Home status cleanup — 2026-07-20

This is current-product UI evidence, not an accepted visual baseline or a
pixel-parity result.

## Scope

- Removed the isolated right-side `Local workspace` disclosure from Home.
- Removed the duplicate live `Local evidence` badge from the queue heading.
- Hid `Open schedule` while the local learning service is unavailable.
- Split automatic startup/recovery from a retryable service failure.
- Kept the local/provider boundary in the single-column introduction.

## Checks

- `home-unavailable-1440x900.png`: deterministic browser-only unavailable
  fixture at 1440×900.
- `home-unavailable-980x700.png`: the same fixture at 980×700.
- `home-unavailable-draft-1440x900.png`: the refined state explaining that the
  composer accepts a local draft but cannot send before service recovery.
- The visible keyboard order reached Retry before the composer and contained
  no hidden or placeholder action between them.
- Enter in the unavailable composer retained the draft and created zero Agent
  activity panels.
- Complete desktop suite: 308/308 passed.
- ESLint and strict TypeScript checks passed.
- The visual harness completed. The provisional Home/Figma comparison measured
  2.018%; it is comparison-only and does not establish pixel parity.

The fixture calls neither Tauri nor the learning service and does not substitute
sample tasks for a failed local read.
