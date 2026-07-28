# HyperKnow benchmark audit

Keen was captured in Chrome at a 1728×851 CSS-pixel viewport and device scale
2. These files verify the Browser Demo surface only; they do not verify the
packaged macOS app or live sidecar behavior.

| File | Captured (Asia/Shanghai) | State |
| --- | --- | --- |
| `01-keen-home-before.jpg` | `2026-07-18T13:29:37+08:00` | Home before the benchmark adjustments, with Inspector open by default |
| `02-keen-planner-before.jpg` | `2026-07-18T13:30:16+08:00` | Planner before the benchmark adjustments, with Inspector open by default |
| `03-keen-home-after.jpg` | `2026-07-18T13:37:06+08:00` | Home after defaulting Inspector closed and widening the centered content bound |
| `04-keen-study-entry-after.jpg` | `2026-07-18T13:37:10+08:00` | Study intent after selecting `New study session`; no session was created |
| `05-keen-planner-after.jpg` | `2026-07-18T13:37:05+08:00` | Planner using the full primary workspace width |
| `06-reference-comparison.png` | `2026-07-18T13:38:08+08:00` | Qualitative 2×2 montage: HyperKnow Home / Keen Home, then HyperKnow Deep Learn entry / Keen Study entry |

The comparison montage resizes and arranges the source screenshots for review.
It is not an overlay, automated visual diff, or pixel-parity measurement.
