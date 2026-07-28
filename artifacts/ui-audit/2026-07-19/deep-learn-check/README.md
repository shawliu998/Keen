# Deep Learn read-only UI audit — 2026-07-19

## Scope

- Surface: Keen Browser Demo Deep Learn.
- URL: `http://127.0.0.1:1430/deep-learn/demo?course_id=demo`
- Viewport: 1280×720.
- Flow: default lesson → empty answer → success feedback → paused state.
- Product code was not changed by this audit.

## Health score

| Dimension | Score | Key finding |
| --- | ---: | --- |
| Accessibility | 3/4 | Strong semantics; two small-text color pairs measure about 4.11:1. |
| Performance | 3/4 | No expensive page motion; production build retains a >500 kB chunk warning. |
| Responsive | 3/4 | No 1280×720 horizontal overflow; narrower live viewports were not captured in this run. |
| Theming | 2/4 | Tokens exist, but the refined Deep Learn CSS still contains multiple hard-coded light colors. |
| Anti-patterns | 2/4 | Two detector hits for thick side-accent borders, plus repeated uppercase micro-labels. |
| **Total** | **13/20** | **Acceptable; one accessibility repair and a focused anti-AI polish pass remain.** |

## Findings

- **P1 — Small text contrast:** success feedback `#526fc9` on `#edf0f6` and tertiary `#767b83` on `#fbfbfa` both measure about 4.11:1, below 4.5:1 for normal text. Locations: `apps/desktop/src/features.css:152`, `packages/design-tokens/src/tokens.css:15`.
- **P2 — Answer focus scroll jump:** opening the answer changes `scrollY` from 0 to 85 px at 1280×720, hiding the top disclosure/toolbar context. Location: `apps/desktop/src/features/deep-learn/DeepLearnPage.tsx:46` (`autoFocus`).
- **P2 — Remaining AI visual grammar:** the detector reports two side-accent-border warnings at `apps/desktop/src/ui-refresh.css:391` and `:394`. The same region also repeats tiny uppercase labels.
- **P2 — Disabled capability clutter:** `Save unavailable` and the disabled Close control occupy prime header space without enabling a task. They are truthful, but add demo-shell noise. Location: `DeepLearnPage.tsx:42`.
- **P2 — Reading measure:** the visible lesson text column is about 652 px / roughly 80+ characters at 14 px, above the preferred 65–75ch range for long study material. Location: `ui-refresh.css:385`.
- **P2 — Token bypass:** hard-coded light surfaces and text colors in `ui-refresh.css:375–400` will resist future theme changes and make the page visually drift from the shared token system.
- **P2 — Bundle warning:** the production main chunk is 564.31 kB and the PDF worker is 1,078.61 kB; Vite reports the existing >500 kB warning.
- **P3 — Target sizing:** the smallest enabled control measured 32×30 px and unit rows are 34 px high. This clears WCAG 2.2 AA's 24 px target minimum but is below the more comfortable 44 px touch target; lower priority for a mouse/keyboard macOS product.

## Strengths

- No element overlap, duplicate IDs, unnamed enabled focusables or horizontal document overflow was found at the inspected viewport.
- System typography, Lucide icons, neutral surfaces and the reduced card count feel materially more product-like than a floating AI chat layout.
- Heading order, landmarks, labelled textarea, `aria-current`, progressbar semantics, disabled states and `role=status` feedback are present.
- Demo/non-persisted/source-unavailable boundaries remain explicit and no unavailable capability is shown as successful.
- Motion tokens are 140/220 ms and the global reduced-motion rule collapses animation and transition duration.
- ESLint, strict TypeScript and the production build passed; the build retained the known chunk warning.

## Evidence limits

- Browser Tab injection did not move focus reliably, so a complete keyboard traversal is not claimed.
- Only 1280×720 was captured in this audit. Breakpoint CSS exists, but 900/1100 px live reflow was not reverified here.
- Loading, service failure, live persisted source content and summary recovery were inspected in code/tests, not visually captured in this run.
