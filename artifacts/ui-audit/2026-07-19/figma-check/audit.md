# Figma checkpoint audit

Date: 2026-07-19 (Asia/Shanghai)

Scope: Figma nodes `7:2`, `8:2`, `9:2`, and `10:2` in file
`ugwiIPdF43v2woYsLM3b9R`, all rendered at their natural 1728×907 size.

This is a combined visual, UX, accessibility-risk, and prototype-structure
audit. It is not a runtime accessibility audit, interaction test, motion test,
responsive test, or pixel-diff result.

## Evidence

- `01-hyperknow-home.png`: authorized-reference HTML reconstruction, Figma node `7:2`
- `02-keen-home-v2.png`: Keen product-first Home, Figma node `9:2`
- `03-hyperknow-feed.png`: authorized-reference HTML reconstruction, Figma node `8:2`
- `04-keen-feed-v2.png`: Keen product-first Learning Feed, Figma node `10:2`
- `05-home-comparison.png`: Home reference and proposal side by side
- `06-feed-comparison.png`: Feed reference and proposal side by side

## Health score

| Dimension | Score | Evidence-backed finding |
| --- | ---: | --- |
| Accessibility | 2/4 | Semantic controls exist, but the prototype has no explicit `:focus-visible`; tertiary text is 4.11:1, shortcuts 2.63:1, and muted calendar dates 1.67:1 on their shown backgrounds. |
| Performance | 4/4 | The static HTML study is small and contains no heavy images, scripts, filters, or animation. This does not measure the React/Tauri runtime. |
| Responsive design | 1/4 | Both proposal frames are fixed at 1728×907 with `min-width: 1200px`; no 1440×920, 1180×740, collapsed-sidebar, or enlarged-text variant exists. |
| Theming | 1/4 | The study uses hard-coded light values and does not exercise the codebase's dark-mode tokens. |
| Anti-patterns | 3/4 | The task-first composition removes the generic assistant landing screen and repeated floating cards; the remaining risk is a highly generic neutral productivity-tool appearance. |
| **Total** | **11/20** | **Acceptable study; not implementation-ready.** |

The deterministic detector returned one advisory for numbered section markers in
`keen-feed-v2.html`; it matched calendar dates `10, 11, 12` and is a false
positive, not a design finding.

## Priority findings

1. **P1 — Fidelity is structural, not precise.** The HyperKnow reconstructions
   omit or substitute visible source assets and controls (illustrations, mascot,
   icons, icon-only utilities), and the Home crop is not aligned to the original
   1488×907 reference. They are useful layout references but cannot support a
   pixel-match claim.
2. **P1 — The Figma output is not a design system.** Metadata contains zero
   components and zero instances: Home has 104 raw frames and 53 text nodes;
   Feed has 139 raw frames and 93 text nodes. Button, badge, navigation, task,
   calendar and status changes would be manual and inconsistent.
3. **P1 — Keyboard focus and small-text contrast are unresolved.** The HTML has
   no `:focus-visible` rule. Several 10–11 px labels use colors below 4.5:1.
4. **P1 — Responsive desktop behavior is missing.** A three-column Feed can
   work at 1728 px but is not proven at Keen's supported 1180 px minimum.
5. **P2 — Required interaction states and motion are absent.** Default visual
   states exist, but hover coverage is partial and focus, active, disabled,
   loading, error and success variants are not represented. The reduced-motion
   media query exists, but there is no normal state motion to reduce.
6. **P2 — Calendar event readability is too low.** Event labels use 9 px text,
   truncate meaningful titles, and lack a shown hover/focus detail treatment.
7. **P2 — Home repeats the same action.** `New study session` appears in both
   Sidebar and the right rail, diluting the primary continuation action.
8. **P3 — Product character is underdeveloped.** The proposal is calmer and
   less AI-like, but could still pass for a generic task manager. A distinctive
   learning-specific element should come from evidence, steps, recall state, or
   source context—not decoration or an assistant mascot.

## What works

- Home starts from a real learning task, goal, progress, next step, and Continue
  action rather than a universal prompt.
- The workspace status truthfully distinguishes connected, offline, unconfigured,
  and in-development capabilities.
- Learning Feed establishes a clear task-list-to-calendar relationship without
  using nested elevated cards.
- Accent color is mostly reserved for selection, progress, and primary action.

## Recommended order

1. Establish native Figma variables and text/effect styles from Keen tokens.
2. Build component sets for Button, Badge, NavItem, SegmentedControl, TaskRow,
   CalendarEvent, StatusRow, Progress, and Input with the full state matrix.
3. Create 1728×907, 1440×920, and 1180×740 screen variants, including sidebar
   collapse and task-rail compression rules.
4. Add purposeful 100–250 ms state motion plus a reduced-motion variant.
5. Run same-viewport reference/proposal comparisons; do not claim pixel parity
   until a fixed crop, seed, baseline, and actual visual diff exist.
