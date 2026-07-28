# Keen aesthetic and anti-AI audit

Date: 2026-07-19

Scope: current deterministic Browser Demo Home and Learning Feed at 1440×900,
1180×760 and 900×700. This is a read-only audit; no runtime UI was changed.
The earlier user-provided two-screen reference was used only as optional
comparison context.

## Verdict

Audit health: **11/20 · Acceptable, significant visual-system work needed**.

| Dimension | Score | Evidence summary |
| --- | ---: | --- |
| Accessibility | 2/4 | Good landmarks and names, but microtext, placeholder contrast and 21 px calendar-event targets remain |
| Performance | 3/4 | No runtime errors; layout-property transitions remain |
| Responsive | 2/4 | No horizontal overflow, but the full calendar stacks below the task pane at 900 px and creates 1370 px page height |
| Theming | 3/4 | Light/Dark tokens exist, but component CSS still contains hard-coded state colors |
| Anti-patterns | 1/4 | Centered assistant composer, nested rounded surfaces, repeated pills and border-plus-shadow cards remain strong AI/template signals |

Severity count: P0 0, P1 4, P2 4, P3 1.

## Accepted screenshots

1. `01-home-default.png` — Home at 1440×900; structurally stable, visually generic.
2. `02-learning-feed.png` — Feed at 1440×900; structurally stable, visually over-layered.
3. `03-learning-feed-1180x760.png` — Feed at 1180×760; no horizontal collision, calendar labels truncate.
4. `04-home-1180x760.png` — Home at 1180×760; no overlap, generic composer remains dominant.
5. `05-home-900x700.png` — Home at 900×700; stable but typography becomes very small.
6. `06-learning-feed-900x700.png` — Feed at 900×700; task pane is stable while the full calendar moves below the fold.

`07-focus-attempt-unverified.png` is retained only as a rejected focus-capture
attempt. Browser keyboard focus did not enter the document, so it is not used
as evidence of focus behavior.

## P1 findings

1. **Home still reads as a generic AI assistant.** The centered circular book
   mark, question headline and oversized empty composer repeat the dominant AI
   chat pattern (`HomePage.tsx:129`, `ui-refresh.css:105`). The reference itself
   uses this structure, so further one-to-one copying preserves the problem.
2. **Learning Feed has excessive container nesting.** Sidebar, introduction,
   heading band, demo disclosure, segmented control, select, task card, reason
   inset and badges each introduce another surface or boundary
   (`LearningFeedPage.tsx:321`, `ui-refresh.css:201`). This slows scanning and
   creates the perceived element stacking even though boxes do not overlap.
3. **Micro typography is overused.** At 900×700, 79 of 87 visible leaf text
   nodes computed below 12 px; 13 were below 11 px and five below 10 px. The
   tertiary token is 4.26:1 on white and the effective placeholder color is
   4.14:1, below the 4.5:1 target for normal text (`ui-refresh.css:90`).
4. **Calendar events are undersized controls.** Visible event buttons measure
   about 84×21 px with 9–10 px labels (`ui-refresh.css:280`, `ui-refresh.css:404`),
   below WCAG 2.5.8's 24 px target-size minimum.

## P2 findings

1. **Border and shadow noise.** Home workbench and calendar both pair a 1 px
   border with a shadow (`ui-refresh.css:140`, `ui-refresh.css:254`), while the
   Feed adds internal grid lines and more bordered controls. Use a divider or a
   compact shadow, not both on every major surface.
2. **Narrow Feed becomes a long vertical stack.** At ≤930 px the task rail and
   the complete 650 px calendar become one column (`ui-refresh.css:407`); the
   measured 900 px page height was 1370 px. A list-first switcher is more useful
   than placing a full month below the tasks.
3. **Icon library is consistent but hierarchy is overencoded.** All inspected
   icons use the same Lucide 2 px stroke, which is good, but 19 icons use eight
   different rendered sizes from 13 to 22 px and several receive separate
   rounded containers. Reduce to 14/16/20 px roles and remove decorative icon
   holders that do not indicate an action or state.
4. **Theme tokens are bypassed in older rules.** Hard-coded active, badge and
   status colors remain in `styles.css:21`, `styles.css:26` and
   `styles.css:79`; these can drift from the Light/Dark semantic tokens.

## P3 finding

The Browser Demo boundary is truthful but repeated in the sidebar footer and
again in page content. Keep the persistent footer state, and show an inline
explanation only when it changes the next action.

## Positive findings

- The supplied Keen brand mark is used; no placeholder letter or fake logo is visible.
- Runtime typography uses one appropriate macOS system stack rather than mixed display fonts.
- Lucide icon strokes are consistent; no emoji, handcrafted SVG or mixed icon family was observed.
- The inspected state had no unnamed buttons and no duplicate IDs.
- No horizontal document overflow occurred at 1440, 1180 or 900 px.
- Reduced-motion rules exist. Runtime logs contained no application error, only React Router future-flag warnings.

## Recommended order

1. `$impeccable distill` — remove Home's decorative hero grammar and flatten the Feed surface hierarchy.
2. `$impeccable typeset` — establish a 12 px normal-UI floor, reserve 10–11 px for exceptional metadata, and repair placeholder/tertiary contrast.
3. `$impeccable layout` — replace the ≤930 px Feed stack with an explicit Tasks/Calendar view switch.
4. `$impeccable polish` — normalize borders, icon roles, states and remaining token usage.

Re-run `$impeccable audit` after fixes. Screenshots alone do not establish full
WCAG compliance, packaged macOS behavior or keyboard focus order.
