# HyperKnow → Figma screen audit — 2026-07-19

Internal design-research evidence only. These captures are covered by
`references/authorized-scope.md`; they are not redistributable Keen product art
and are not accepted visual-regression baselines.

## Capture conditions

- Source: `https://agent.hyperknow.io/`
- Session: the user's already-authenticated Chrome tab
- Capture date: 2026-07-19, Asia/Shanghai
- CSS viewport: 1585 × 851
- Most Home/Feed captures crop the 220–240 px account Sidebar so existing
  user-created titles are not retained. Knowledge Base and Settings captures use
  the collapsed Sidebar or a bounded crop.
- Display scale was not separately retained. The screenshots support qualitative
  reconstruction and measurement, not pixel-parity claims.
- Synthetic upload:
  `references/audit-fixtures/keen-figma-flow-audit.txt`
- No HyperKnow source code, browser storage or private network traffic was read.

## Screen and state inventory

1. `02-home-clean-main.png` — default Home request surface and learning links.
2. `03-home-tools-menu.png` — compact Deep Learn / Study Planner tool menu.
3. `04-learning-feed-month.png` — Month calendar and empty current-day task rail.
4. `05-learning-feed-week.png` — Week calendar.
5. `06-learning-feed-usage-popover.png` — anchored quota/status popover.
6. `07-knowledge-base-list.png` — completed synthetic file grid.
7. `08-knowledge-base-new-menu.png` — New Folder / Upload File menu.
8. `09-knowledge-base-upload-state.png` — in-place Processing tile.
9. `10-knowledge-base-upload-complete.png` — completed upload tile.
10. `11-knowledge-base-card-hover.png` — hover-only calendar and overflow actions.
11. `12-knowledge-base-card-menu.png` — Delete menu; Delete was not invoked.
12. `13-knowledge-base-calendar-entry.png` — calendar-extraction loading indicator.
13. `14-knowledge-base-calendar-ready.png` — visible “Add to Calendar Again” state.
    This UI state and quota change were observed, but creation of an external
    calendar event was not independently verified.
14. `15-account-menu.png` — generic account menu without account identity.
15. `16-settings-general-sanitized.png` — subscription, coupon, preference and
    integration headings; identity is excluded.
16. `17-settings-integrations-sanitized.png` — Canvas and Google Calendar both
    visibly Not Connected; no connection flow was started.
17. `18-settings-memory.png` — loading and management states; no saved personal
    memory was retained.
18. `19-deep-learn-session.png` — task path, progress, locked review and current
    next-step structure.
19. `20-deep-learn-long-content.png` — long editorial lesson, thin callout,
    generated figure slot and grounded source chip from a synthetic fixture.
20. `21-conversation-review-plan.png` — recommendation-only review plan,
    evidence-of-mastery copy, progress rail and bottom request bar.
21. `22-conversation-citation-popover.png` — side-by-side answer and loaded source
    preview for the synthetic fixture.

## Measured visible style sample

- Body: `Satoshi-Medium, MiSans, PingFang SC, Microsoft YaHei, sans-serif`,
  16/24 px, white background.
- Editorial heading sample: 20/28 px, 700, `#333`.
- Bottom request bar: 700 × 52 px, 24 px radius, 1 px `#efefef` border,
  approximately `0 1px 3px rgba(0,0,0,.02)`.
- Tools button: 75 × 33 px, full-pill radius, 1 px `#e5e5e5`, 9–10 px inline
  padding.
- Citation preview: 594 px wide, white, square outer edge, subtle left shadow.

These measurements describe the inspected viewport only. They are inputs to a
Keen component translation, not a license to copy implementation code.

## Phase-0 findings for Keen

- The strongest transferable structure is not the generic Home composer. It is
  the continuity across task path → current step → long reading → recall/review
  → source preview → explicit next action.
- Useful surfaces are mostly flat: thin borders, quiet cool-gray fills, compact
  anchored menus, restrained navy selection and one reading column. The product
  rarely needs stacked decorative cards.
- Loading and success states stay in place instead of replacing the whole page.
- File hover actions are visually tidy but too hidden to become Keen's only
  primary action. Keen should keep important next actions visible and keyboard
  reachable.
- HyperKnow's Satoshi/MiSans family is not available as a verified distributable
  Keen asset. The production macOS system stack remains the truthful default;
  Figma must be reconciled from Inter to SF Pro Text/Display before code handoff.
- HyperKnow's integration, file-processing, generated response, citation,
  mastery and calendar states remain reference evidence only. Keen will show
  unavailable, not configured, in development or Browser Demo labels until the
  corresponding local capability is actually implemented and verified.

## Privacy and deletion note

One full Settings capture exposed account identity and was immediately deleted;
the retained replacements are cropped and contain no account identifier. The
initial What's New overlay capture was moved to Trash because the blurred
Sidebar could still reveal existing conversation titles. Both operations are
recoverable from macOS Trash until it is emptied.
