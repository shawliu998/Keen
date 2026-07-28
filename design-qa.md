# Design QA — HyperKnow layout return, 2026-07-19

- Source visual truth: `references/hyperknow/2026-07-18/01-home-main.jpg`, `references/hyperknow/2026-07-18/02-learning-feed.jpg`, and the user-supplied light Keen composite recorded by the prior style-return audit.
- Implementation screenshots: `artifacts/ui-audit/2026-07-19/keen-home-1728x907.png`, `artifacts/ui-audit/2026-07-19/keen-learning-feed-1728x907.png`, plus 1180×760 and 900×700 responsive captures in the same directory.
- Full comparisons: `artifacts/ui-audit/2026-07-19/compare-home-reference-current.png` and `artifacts/ui-audit/2026-07-19/compare-learning-feed-reference-current.png`.
- State: deterministic, request-free Browser Demo Home and Learning Feed defaults.
- Viewport caveat: the in-app browser accepted a requested 1728×907 viewport but its available content width was 1462 px. Reference widths were normalized only for a qualitative side-by-side review. These files are not dimension-aligned pixel baselines.

## Findings

No actionable P0, P1 or P2 visual defect remains in the inspected Home and Learning Feed states.

- Layout: Keen now follows the referenced hierarchy—narrow primary Sidebar, quiet Toolbar, centered request workbench, secondary lower queue, and a task rail beside a full month calendar.
- Product adaptation: HyperKnow's branded companion, news, generic tools and service-success claims were not copied. Keen shows only its existing Ask/Study paths, local/sample task evidence and explicit Demo/local-service boundaries.
- Typography and density: the macOS system stack, compact labels, restrained weights, thin dividers and wide reading canvas match the selected light desktop direction.
- Color and elevation: warm off-white canvas, white content surfaces, pale blue-gray selected state, muted slate text, low-saturation badges and minimal shadows replace the rejected dashboard styling.
- Interaction states: selected mode chips expose `aria-pressed`; disabled submit remains visibly inactive; hover/focus/active/disabled rules use shared tokens. A visible keyboard focus ring was captured at 900×700.
- Responsive behavior: Home remained readable at 1180×760 and 900×700. Feed retained two columns at 1180×760 and moved the calendar below the task list at 900×700 without horizontal clipping.
- Motion and runtime: the global reduced-motion rule collapses animation/transition duration; the inspected browser console contained zero errors.

## Iteration history

1. Restored light-only default rendering so the reference direction does not change with the host macOS appearance.
2. Reduced the Sidebar and Toolbar dimensions, removed extra Home tool rows, and changed Home to a single permanent learning-request surface.
3. Tightened Learning Feed task-rail width, card density, calendar framing and toolbar height.
4. Checked 1462×907, 1180×760 and 900×700 captures; kept the compact breakpoint because it preserves the task-first reading order.

## Verification boundary

- `npm run lint`, `npm run typecheck`, 26 Vitest files / 282 tests, and `npm run build` passed.
- The existing visual harness captured Home, Learning Feed and Deep Learn entry, but all three results are `missing_reference`; no mismatch percentage or pixel-parity claim is valid.
- This QA does not cover packaged Tauri rendering, every error/loading/provider state, or a full automated accessibility audit.

final result: passed

## Scoped QA — source-scoped guided-study entry, 2026-07-21

- Scope: Home's existing **Start focused study** mode now selects a real course scope and hands the entered goal to the existing recommendation → persisted session → Deep Learn route.
- Behavioral evidence: `apps/desktop/tests/agentHome.integration.test.tsx` passed 8/8; `services/learning-core/tests/test_autonomous_study_session_api.py` passed 20/20. The session API test covers trimming the entered goal and preserving it on resume.
- Boundary: this is not a visual review. No new capture, Figma comparison, accepted baseline, packaged check, keyboard audit or pixel-parity result exists for the live source-selector state. The source selector scopes to a course; its indexed chunks remain server-selected by the existing task/session coordinator.

final result: behavioral slice passed; visual acceptance unverified

## Scoped QA — real persisted learning-loop restart, 2026-07-21

- Scope: local unsigned `Keen Dev.app`, authenticated sidecar, isolated `com.keen.learning.dev` SQLite data, existing Calculus I course/task, and one clearly local indexed test note.
- Reproduced defect: Home received a valid `covered_by_active_task` recommendation, but the session service rejected that actionable local task as `task_not_autonomous`; no session was created.
- Repair: a validated learner goal is explicit user initiation and may reuse the actionable same-course task. Calls without a learner goal keep the existing autonomous-provenance gate. Course, task-status, concept, source and terminal-session checks remain unchanged.
- Live result: Home created `autonomous-session-d626a3fe-7ec2-593f-9437-dab80e1902be`; diagnostic advanced to the first persisted source unit; the reading rendered the stored chunk; active recall recorded a correct response; History displayed the same session; and a clean app/sidecar restart restored it from History at `practicing` with the recall result preserved and Begin practice next.
- Truth boundary: no provider was configured or invoked, no provider response/citation/model success was fabricated, and the local test note is not product/reference evidence.
- Responsive/visual boundary: no React or CSS changed. Existing History checks at 1180×740 and 820×700 remain the relevant layout evidence; no new screenshot, accepted baseline, pixel diff, reduced-motion package result or complete keyboard/accessibility audit was added.
- Verification: desktop ESLint and strict TypeScript passed; 29 files / 316 desktop tests passed; 87 related Python tests passed with one existing Starlette/httpx deprecation warning; focused Ruff lint/format passed; and the unsigned Debug `.app` build passed with the existing Vite chunk-size warning.

final result: passed for the provider-independent local Study Session loop and restart recovery; visual acceptance remains unchanged

## Scoped QA — real practice completion and Review handoff, 2026-07-21

- Scope: the same persisted dev session `autonomous-session-d626a3fe-7ec2-593f-9437-dab80e1902be`, existing deterministic targeted practice, Summary transaction, Review/FSRS route, Learning Feed, History and full `Keen Dev.app`/sidecar restart.
- Live result: practice generated a source-derived missing-term prompt and recorded `composition` as correct (1/1); Summary completed the session and originating task and created one Review item; Review revealed the persisted expected answer, stored recall text `composition`, applied `good`, and advanced the FSRS schedule to `learning`, revision 1, one repetition and zero lapses.
- Restart result: after a clean app/sidecar quit, Debug app rebuild and reopen against the same SQLite file, History returned the completed record, Summary returned its original review handoff, Review returned the post-rating empty due queue, and Feed reported no active or currently eligible action.
- UI findings and repair: the completion view lacked a next action and juxtaposed 100% session completion with an unexplained 50% planned-unit value. It now distinguishes the completed focused-session lifecycle from the truthful 1-of-2 unit count, provides Review/Feed CTAs, avoids presenting the frozen handoff time as the current schedule after rating, and clears the Summary Inspector on route exit.
- Interaction/state check: existing loading/error/cancelled/unknown/success/service-unavailable component states remain unchanged and covered by the focused/full suites. The new CTAs use the existing keyboard-focusable shared Button; no animation was added, the global reduced-motion rule remains in force, and the supported native window displayed the compact action row without observed clipping. This is not a complete keyboard, accessibility or reduced-motion audit.
- Verification: focused Summary/Deep Learn tests 25/25; complete desktop tests 29 files / 316 tests; desktop ESLint and strict TypeScript passed; targeted Python practice/summary/Review tests 23/23 with one existing Starlette/httpx warning; Debug `.app` build, `git diff --check` and scoped Impeccable detection passed. The build retained the existing Vite chunk-size warning.
- Visual boundary: the live rebuilt Dev.app was inspected directly, but no fixed-viewport screenshot artifact, accepted Deep Learn/Review reference, visual-diff percentage, signed/notarized app or pixel-parity claim was produced.

final result: passed for the local practice → Summary → Review/FSRS → restart handoff; multi-unit progression and visual acceptance remain open

## Scoped QA — UI framework closeout, 2026-07-21

- Direction contract: `docs/DESIGN_DIRECTION.md`.
- Approved Figma references: Home `113:3` and Learning Feed `162:97` in file `ugwiIPdF43v2woYsLM3b9R`.
- Runtime captures: `artifacts/ui-audit/2026-07-21/ui-framework-closeout/` at 1440×920, 1180×740 and 900×700.
- Knowledge Base reference: authorized internal screenshot `references/hyperknow/2026-07-19-figma-screen-audit/07-knowledge-base-list.png`; it is qualitative layout evidence, not a redistributable or dimension-aligned baseline.

### Findings

- Home and Feed preserve the Approved information hierarchy while runtime wording remains more conservative where Demo mode has no service or model connection.
- Knowledge Base adopts the source-management rhythm without copying HyperKnow branding or replacing Keen's truthful sample/index state disclosures.
- At 1180×740, Home and Feed had matching viewport and scroll widths, so neither created horizontal page overflow. At 900×700, Feed intentionally removed the calendar and Knowledge Base changed from table columns to readable rows.
- Conversation retained a roughly 72-character reading measure, an independently scrollable transcript region, and a bottom workbar.
- A manually collapsed wide-window Sidebar had no recovery affordance. The brand row now keeps a state-aware `Expand sidebar` / `Collapse sidebar` control, and a regression covers both transitions.
- Focus order was audited from visible native controls and a focus-visible screenshot was captured. Direct browser Tab injection remained unreliable, so this does not replace the existing component keyboard tests or constitute a complete keyboard audit.
- Reduced-motion emulation matched and forced 0.00001 s transition/animation durations with `scroll-behavior: auto`; the preference was reset after the check.
- Browser logs contained no application errors. The existing React Router future warnings remain.

### Verification

- Desktop ESLint, strict typecheck, production build and 28 Vitest files / 313 tests passed.
- `git diff --check` passed.
- Impeccable detection returned no findings for the changed Sidebar and shared CSS.
- The current captures and Approved Figma images were inspected qualitatively. Existing missing/provisional references were not promoted to accepted baselines, so no pixel-parity or full visual-regression pass is claimed.
- A fresh local ad-hoc packaged `Keen.app` was opened. Home, Learning Feed, Knowledge Base, new Conversation and the no-course Study entry rendered with `Learning core ready`; native focus reached Review due; Sidebar collapsed and recovered through `Expand sidebar`; and `scripts/smoke-bundled-sidecar.sh` passed. Terminating the current sidecar child produced a supervisor-created replacement and a ready UI; the intermediate unavailable UI was not captured. The capture images are 1203×768 px; their CSS viewport was not measured. The evidence matrix is `artifacts/ui-audit/2026-07-21/packaged-webview/README.md`.
- A separate build-time-only `com.keen.learning.ui-audit` app directly exposed live packaged WKWebView metrics. At launch `inner`, root-client and `visualViewport` were all 1440×920 CSS px; native edge resizing produced 1180×740 for all three, and a further shrink attempt remained at that configured minimum. DPR was 2 and the current packaged media query was `reduced=false`. The System Settings control channel closed before the preference could be read or changed, so no packaged `reduced=true` claim or system-setting mutation is made. Normal production build output was checked to exclude the probe. Captures and exact commands are recorded in the evidence matrix.
- To prevent same-name activation of a separately installed app from tainting audit provenance, the native menu now uses the active Tauri config product name and `scripts/open-ui-audit-app.sh` verifies and starts only the repository-local `Keen UI Audit` / `com.keen.learning.ui-audit` bundle. The Rust identity regression locks production, development and audit names/identifiers as distinct. The normal production identity remains `Keen` / `com.keen.learning`; the installed app was not modified.
- The original packaged route captures are not accepted baselines: their CSS viewport and fresh-data fixture are not recorded deterministically, packaged reduced motion was not forced, long learning content and transient unavailable UI were not captured, and only Home/Feed have current Approved Figma nodes. The separate audit probe verifies window metrics only; it does not make those route states deterministic. `artifacts/visual-diff/report.json` now has 2 separate browser-only accepted Home/Feed checks, plus 16 `missing_reference` and eight explicitly provisional comparisons; none converts a packaged capture into a baseline.

final result: passed for the scoped browser UI and bounded packaged-WebView smoke; complete keyboard/accessibility audit remains open

## Scoped QA — Keen-owned Home and Learning Feed regression baselines, 2026-07-21

- Accepted inputs: `references/visual-baselines/keen-home-browser-demo-1180x740-reduced-motion.png` and `references/visual-baselines/keen-learning-feed-browser-demo-1180x740-reduced-motion.png`.
- Fixture: Browser Demo + `visualTest=true`; Feed calendar fixed to July 19, 2026; 1180×740 CSS px; Playwright DPR 1; `prefers-reduced-motion: reduce`; harness animations/transitions disabled.
- Fresh design exports: Figma `ugwiIPdF43v2woYsLM3b9R`, Home compact `155:187` and Feed compact `164:179`, both natural 1× 1180×740 PNG under `references/keen/2026-07-21-figma-baseline/`.
- Combined evidence: `artifacts/visual-diff/comparison/home-figma-current-diff-1180x740.png` and `artifacts/visual-diff/comparison/learning-feed-figma-current-diff-1180x740.png` present matching Figma reference, current screen and diff. They measured 2.0290884104443423% and 1.5566880439761797%, respectively, and remain provisional design-reference comparisons.

### Findings

- The compact task/source/progress hierarchy, typography, borders, crop and Browser Demo labels remain coherent. Visible shell/status and Feed calendar-day differences are documented Keen product adaptations; no React/CSS defect was reproduced, so no UI code changed.
- Interception recorded zero application fetch/XHR calls for both routes. Browser Demo is outside Tauri, so no Tauri command, learning-core or provider request occurred. The tool environment's Figma capture helper was separate from application traffic.
- The self-reference checks passed strict 0%; this detects future Keen changes only. It is not Figma parity or a third-party comparison.
- Knowledge Base, Conversation, Deep Learn, task-detail and operational Feed states remain unapproved.

### Verification

- `node tools/visual-regression/run.mjs`: 26 entries, 2 strict baseline `passed`, 16 `missing_reference`, 8 `compared` / `provisional`.
- Desktop ESLint and strict TypeScript passed. Focused `learningCore.integration` and `learningFeedPage` tests passed 55/55; existing React Router future warnings remain.
- Packaged reduced motion, long learning content and transient unavailable states remain unverified.

final result: accepted only for the two named Keen-owned Browser Demo regression baselines; no Figma parity, complete visual suite, or other-page/state baseline is claimed

## Scoped QA — icon density and capability boundaries, 2026-07-21

- Negative reference: the user-supplied Learner Memory crop showing a repeated brain glyph beside the profile and every memory row.
- Current captures: `artifacts/ui-audit/2026-07-21/icon-reduction/memory.png`, `memory-compact.png`, `new-request.png`, and `settings-capabilities.png`.
- Comparison boundary: the supplied crop identifies an anti-pattern rather than a fixed viewport or target composition. This is a qualitative removal check, not pixel parity.

### Findings

No actionable P0, P1 or P2 issue remains in the scoped change.

- Learner Memory uses type, dividers and three plain capability facts. It contains no decorative brain glyph, seeded learner evidence, synthetic mastery, search/filter toolbar or disabled action.
- `/conversation/new` is a real empty state in Browser Demo. It saves a local question but does not display the fixed example answer, create a reply or claim a citation.
- The Inspector renders only selected context. Its synthetic 64% mastery, unverified source buttons and generated-looking insight fallback were removed.
- Settings combines Provider and Connections under Capabilities and removes redundant content-row icons. The compact settings rail keeps its four navigation icons because they remain the only labels below the compact breakpoint.
- At 1280×800 the inspected Memory, new Conversation and Settings routes each had one `main`, zero horizontal overflow and zero unnamed buttons. Memory and Settings had no disabled buttons; new Conversation disabled only its empty submit action.
- The 900×700 Memory capture keeps the facts and real Knowledge Base action visible without horizontal clipping. Direct Tab injection in the in-app browser did not move focus reliably, so the existing component tests are keyboard evidence and this is not a complete keyboard audit.

### Verification

- Desktop ESLint and strict TypeScript passed.
- The complete desktop suite passed 28 files / 312 tests.
- Production build passed with the existing chunk-size warning.
- Impeccable detection returned no findings for the changed TSX and CSS files.
- The visual harness completed. Sixteen configured routes have no readable reference; eight Figma routes are comparison-only and remain provisional. No accepted mismatch or pixel-parity claim is made.

Residual boundary: accepted Memory/new-request/Capabilities baselines, packaged Tauri rendering and a complete automated keyboard/accessibility audit remain open.

final result: passed

## Scoped QA — Figma page baseline and learning-first Home, 2026-07-19

- Prior implementation: `artifacts/ui-audit/2026-07-19/brand-identity-refinement/home-after-1280x720.png`.
- Current implementation: `artifacts/ui-audit/2026-07-19-core-ui-hardening/01-home-1280x720.png`.
- Same-size comparison: `artifacts/ui-audit/2026-07-19-core-ui-hardening/home-before-after-1280x720.png`.
- Additional current states: `02-feed-1280x720.png` and `03-deep-learn-1280x720.png` in the same directory.
- Figma page baseline: `07 · Product Screens` (`67:2`) in file `ugwiIPdF43v2woYsLM3b9R`; live captures are Home `64:2`, Learning Feed `66:2` and Deep Learn `65:2`.

### Findings

No actionable P0, P1 or P2 visual defect remains in the inspected 1280×720 states.

- Hierarchy: Home now opens with Today, its learning queue and a compact capability disclosure. The request composer remains available but is secondary to the learner's existing work.
- Visual grammar: the composer is flatter, the page uses dividers and reading width instead of nested elevated cards, and the queue preserves a plain list treatment. Feed remains a task rail plus calendar; Deep Learn remains an editorial reading workspace.
- Typography and controls: targeted microcopy was raised toward a 12 px floor and key compact controls were enlarged without turning the interface into a touch-first layout.
- Truthfulness: `Browser Demo`, sample-task, no-service-call and not-persisted disclosures remain visible. No provider reply, citation, mastery record, scheduled review, calendar write or document-processing success was added.
- Runtime and responsive boundary: all three inspected pages had a 1280 px document width in a 1280 px viewport. Feed and Deep Learn extend vertically through ordinary scrolling but have no horizontal overflow. Browser logs contained only the existing React Router future warnings.
- Figma boundary: the three live screens are editable HTML-to-Figma frames suitable for page comparison, but they are not yet instances of the existing Button, IconButton, Badge or Service Banner components and do not establish visual-regression acceptance.

### Verification

- Impeccable detector returned no findings for the changed Home TSX and UI refresh CSS.
- ESLint and strict TypeScript passed.
- Focused Home/App/Feed/Deep Learn tests passed 50/50; the complete desktop suite passed 26 files / 283 tests.
- Production build passed with the existing Vite chunk-size warning.
- `git diff --check` passed.

Residual boundary: accepted fixed-view visual-regression references, full keyboard traversal, all loading/error/provider states, token-bound Figma componentization and packaged Tauri rendering remain open. This is a scoped structural polish pass, not a pixel-parity claim.

final result: passed

## Scoped QA — synthetic evidence and connection previews, 2026-07-19

- Authorized reference inventory: `references/hyperknow/2026-07-19-full-synthetic-flow/README.md`.
- Stable HyperKnow states: `02-recall-feedback.png`, `03-review-plan.png` and `05-pdf-uploaded.png` in that directory, captured at 1700×777 image pixels from synthetic non-personal content.
- Keen implementation: `artifacts/ui-audit/2026-07-19-synthetic-states/01-deep-learn-summary.png`, `02-deep-learn-summary-bottom.png`, `03-connections-not-connected.png` and `04-connections-sample-connected.png`.
- Deterministic reduced-motion captures: `artifacts/visual-diff/current/deep-learn-summary.png`, `settings-connections.png`, `deep-learn-summary-compact.png` and `settings-connections-compact.png` at 1440×920 and 1100×760.

### Findings

- Layout and hierarchy: generated feedback is presented as a reading/evidence block rather than a chat bubble. Citation chips sit beside the statement, and mastery plus review recommendations use one two-column evidence region that collapses through ordinary vertical scrolling at compact height.
- State truthfulness: `Browser Demo`, `Illustrative summary`, `Sample only`, `Not calculated or saved`, `Recommendations only` and an explicit statement that no model/grader/persistence/scheduler ran are visible in the Summary state. Settings labels all external states as visual previews; Google Calendar and Drive success previews are reversible React memory only, while Canvas remains `In development` with no action.
- Navigation density: Settings drops five placeholder categories and retains six categories tied to the current product boundary. No large disabled integration menu was added.
- Interaction/accessibility: the duplicated visible `Preview success` controls have provider-specific accessible names; status changes are polite live regions; citation controls, path steps and preview actions are semantic buttons. A 12-step Tab sample reached shell and page controls in DOM order. The harness used `reducedMotion: reduce` and disables animations/transitions for every capture.
- Responsive/long content: 1440×920 and 1100×760 captures show no horizontal clipping or element overlap. The 1585×851 long Summary view has 227 px of normal vertical scroll, and the bottom capture confirms the footer/navigation remain reachable.
- Reference limits: the source and Keen states differ in content, viewport and product responsibility. Two HyperKnow screenshots containing a transient session-refresh toast are retained only as recovery evidence and rejected as stable design references. The live Calendar/Drive/Canvas reference flow is authentication-blocked, not passed.

### Verification

- Desktop ESLint and strict TypeScript passed.
- Full desktop suite passed 26 files / 283 tests.
- Production build passed with the existing Vite chunk-size warning.
- `git diff --check` passed.
- Visual harness captured seven configured states; all seven are `missing_reference`, so no mismatch percentage or pixel-parity claim exists.

Residual boundary: packaged Tauri rendering, live OAuth/account handling, every service/provider failure and a complete automated accessibility audit remain open.

final result: passed

## Scoped QA — Deep Learn anti-AI polish, 2026-07-19

- Current implementation states: `artifacts/ui-audit/2026-07-19/deep-learn-polish/01-default.png`, `02-answer-empty.png`, `03-success.png`, `04-paused.png`, `05-1024.png` and `05-900.png`.
- Before/after comparison: `artifacts/ui-audit/2026-07-19/deep-learn-polish/06-before-after.png`.
- Authorized-source/current comparison: `artifacts/ui-audit/2026-07-19/deep-learn-polish/07-reference-current.png`.
- Comparison boundary: the HyperKnow capture and Keen Browser Demo have different viewports, crops, content and interaction states. The comparison is qualitative and cannot establish pixel parity.

### Findings

No actionable P0, P1 or P2 visual defect remains in this scoped pass.

- Anti-template grammar: the vertical accent stripe, pill recall label, full-width success bar and disabled Save/Close header controls are removed. The page now relies on reading measure, dividers, type and one subdued note surface.
- Layout and typography: the 690 px editorial column keeps long-form copy near a readable measure and remains left-aligned against the learning rail. At 1024×768 and 900×700, content wraps without horizontal clipping.
- Interaction states: Answer now focuses the textarea with `preventScroll`; observed `scrollY` stayed at zero. Empty submit is disabled, filled submit succeeds, Pause disables unit/previous/next controls, and Resume remains available.
- Accessibility/runtime: the inspected 1280×720 DOM had no duplicate IDs, unnamed focusables or horizontal overflow. A Playwright Tab sequence visibly reached shell and page controls; reduced-motion media matched. Temporary extended lesson text increased vertical scroll height without horizontal overflow. No browser console or page error was observed.
- Truthfulness: the page continues to label Browser Demo as bundled and not persisted. No model response, citation, mastery record, review schedule or provider result was added.

### Verification

- Deep Learn focused suite: 20/20 passed.
- Full desktop suite: 26 files / 282 tests passed.
- ESLint, strict TypeScript, production build and `git diff --check` passed.
- Production build retains the existing Vite chunk-size warning.
- Visual harness: Home, Learning Feed and Deep Learn entry remain `missing_reference`; no mismatch percentage exists.

Residual boundary: packaged Tauri rendering, a complete keyboard/accessibility audit, accepted dimension-aligned visual baselines and every live error/loading/provider state remain open.

final result: passed

## Scoped QA — Deep Learn editorial workspace, 2026-07-19

- Source visual truth: `references/hyperknow/2026-07-19-flow-audit/13-session-thinking.png`, captured from the user-authorized authenticated HyperKnow session after one synthetic non-personal upload.
- Implementation: `artifacts/ui-audit/2026-07-19/deep-learn-reference-refinement/03-keen-after.png` at 1280×720 Browser Demo.
- Combined comparison: `artifacts/ui-audit/2026-07-19/deep-learn-reference-refinement/04-reference-after-comparison.png`.
- Before comparison: `artifacts/ui-audit/2026-07-19/deep-learn-reference-refinement/02-reference-before-comparison.png`.
- State evidence: `06-paused-disabled-state.png` in the same directory.
- Caveat: the 1488×851 reference crop was normalized to the 1280×720 Keen screenshot for qualitative inspection. It is not a dimension-aligned baseline or pixel diff.

### Findings

No actionable P0, P1 or P2 visual defect remains in this scoped Deep Learn state.

- Layout: progress is now colocated with the path rail, and the lesson begins from a stable left reading edge instead of floating in the center of a large blank canvas.
- Hierarchy: sample/source disclosure, title, objective, lesson body, key idea, recall and navigation form one continuous reading sequence.
- Surfaces: the lesson and checkpoint no longer depend on a rounded shadow card stack. Thin dividers and a vertical callout accent match the reference's editorial treatment while retaining Keen tokens.
- Truthfulness: Browser Demo remains explicitly sample-only and not persisted. The live branch still renders only validated session progress, plan units and source content; no citation, mastery result, provider reply or completed task was invented.
- Interaction states: hint, empty-answer disabled submit, enabled submit, success feedback, Pause, disabled unit navigation and Resume were exercised. Unit controls retain hover, active and focus-visible styles.
- Accessibility/runtime: at 1280×720 the document had no horizontal overflow, duplicate IDs or unnamed focusables. The reduced-motion rule remains in the loaded stylesheet. Browser logs contained the existing React Router future warnings but no application error. Tab-key injection did not move focus reliably, so DOM order and semantic controls are evidence, not a complete keyboard audit.

### Verification

- ESLint passed.
- Strict TypeScript passed.
- Focused Deep Learn suite passed 20/20.
- Full desktop suite passed 26 files / 282 tests.
- Production build passed with the existing Vite chunk-size warning.
- `git diff --check` passed.

final result: passed

## Scoped QA — Keen brand identity refinement, 2026-07-19

- Source visual truth: `references/hyperknow/2026-07-18/01-home-main.jpg` for the authorized centered request-workbench direction, plus the user-supplied Keen mark represented by `apps/desktop/public/brand/keen-mark.svg`.
- Implementation screenshots: `artifacts/ui-audit/2026-07-19/brand-identity-refinement/home-after-1280x720.png` and `artifacts/ui-audit/2026-07-19/brand-identity-refinement/conversation-after-1280x720.png`.
- Viewport: 1280×720 Browser Demo.
- State: request-free Home default, Home focused-study selection, disabled empty submission, and fixed Demo transcript. No live model, retrieval or citation result was invoked.
- Full-view comparison evidence: `artifacts/ui-audit/2026-07-19/brand-identity-refinement/compare-home-full.png` places the height-normalized authorized source and the rendered Keen Home together.
- Focused comparison evidence: `artifacts/ui-audit/2026-07-19/brand-identity-refinement/compare-home-prompt-focus.png` compares the request-heading/composer regions together because the identity asset and surrounding hierarchy are too small to judge reliably in the full view.
- Normalization caveat: source and implementation aspect ratios, Sidebar state and app-specific content differ. This pass judges the scoped identity treatment and structural direction, not pixel parity.

### Findings

No actionable P0, P1 or P2 issue remains in the scoped Home/Conversation identity change.

- Fonts and typography: the existing macOS system stack, 21 px prompt heading and 14 px transcript reading copy remain consistent; replacing the user bubble did not change wrapping or reduce the established reading width.
- Spacing and layout rhythm: the 30 px circular Home identity slot and transcript avatars align with their headings/rows without overlap, clipping or a new nested surface.
- Colors and visual tokens: the mark uses the supplied dark/teal brand colors on the existing neutral surface; the learner row no longer introduces an unrelated blue chat-bubble fill.
- Image quality and asset fidelity: Home and Conversation use the transparent vector-traced Keen asset rather than a text glyph, CSS drawing or placeholder. At the inspected sizes it remained sharp and centered.
- Copy and content: Browser Demo, sample-only, no-model and no-retrieval disclosures remain visible. No product capability, response or citation was invented.
- Interaction/accessibility: Ask/Study switching changed the textarea prompt, empty Continue remained disabled, decorative identity images have empty alternative text inside `aria-hidden` wrappers, and the inspected browser log contained no application error. Existing React Router future warnings remain.

### Comparison history

1. First combined comparison found no scoped P0/P1/P2 mismatch after the implementation change; no post-comparison visual fix was required. The source/current viewport-state differences above prevent a parity claim.

### Residual gaps

- This scoped check does not cover packaged Tauri rendering, all desktop breakpoints, keyboard traversal across the entire application, or every loading/error/success state.
- The visual-regression harness still lacks accepted dimension-aligned baselines, so no mismatch percentage exists.

final result: passed

## Scoped QA — complete learning-flow continuity, 2026-07-19

- Source audit: `references/hyperknow/2026-07-19-complete-flow/README.md` and its
  21 retained screenshots.
- Source state used for direct comparison:
  `references/hyperknow/2026-07-19-complete-flow/22-recall-question-and-next-step.png`.
- Keen implementation:
  `artifacts/ui-audit/2026-07-19/keen-deep-learn-current-next.png`.
- Same-size side-by-side comparison:
  `artifacts/ui-audit/2026-07-19/hyperknow-keen-learning-continuity-comparison.png`.
- Additional states:
  `keen-deep-learn-current-next-paused.png` and
  `keen-deep-learn-current-next-summary.png` in the same artifact directory.

### Findings

- The useful source pattern is continuity, not its floating assistant composer:
  learners can see the current stage, progress, recall question and next step.
- Keen now exposes that continuity in the existing learning rail. Current/Next is
  derived from validated local session state, while the unit list remains the
  source-grounded plan. No second progress widget or floating chat layer was added.
- The visual comparison shows Keen retaining its quieter macOS workspace language:
  one reading column, low-elevation surfaces, system typography, fixed rail and
  persistent navigation. HyperKnow's suggestion chips, quota overlay, bottom
  composer and generated diagram were not copied because Keen cannot truthfully
  promise those behaviors in Browser Demo.
- Browser Demo explicitly ends with “No review is scheduled in Browser Demo”;
  the disabled review action and Not persisted labels remain visible.
- Default, paused and summary states had no horizontal document overflow,
  duplicate IDs or unnamed focusables at 1700×777. Pause disabled all seven unit
  buttons and announced its recovery instruction. Summary kept review scheduling
  disabled. Browser logs contained only the existing React Router future warnings.
- A direct keyboard-focus screenshot was not produced because the constrained
  Chrome locator API did not expose focus control in this run. Existing semantic
  button order and focus-visible CSS remain, but this is not a complete keyboard
  audit.

### Verification

- Impeccable detector returned no findings for the changed Deep Learn TSX/CSS.
- Focused Deep Learn tests: 4 files / 37 tests passed.
- Full desktop tests: 26 files / 282 tests passed.
- ESLint, strict TypeScript, production build and `git diff --check` passed.
- Visual harness: Home, Learning Feed and Deep Learn entry all returned
  `missing_reference`; no mismatch percentage exists.

Residual boundary: the captured HyperKnow view and Keen Browser Demo are
different product states, so the comparison is qualitative. Packaged Tauri
rendering, accepted fixed-view baselines and a complete keyboard/accessibility
pass remain open.

final result: passed
## Scoped QA — persisted History return point, 2026-07-21

- Product scope: reuse existing SQLite study sessions and the existing Deep Learn route; no alternate history store, session model, provider response or Demo record was added.
- Browser Demo viewports: 1180×740 and 820×700 CSS px in the in-app browser.
- States inspected: request-free History boundary and its real handoff to `/?mode=study`; populated rows, empty course and route resume are covered by component tests.
- Layout: one bounded reading/list column, flat divided rows, existing Badge/Progress/Button vocabulary, compact Sidebar adaptation, no document overflow at either viewport.
- Accessibility: one `main`, zero unnamed buttons, semantic heading/list records, labelled course selector and explicit action names. Full keyboard traversal and packaged reduced-motion remain outside this focused check.
- Truth boundary: Browser Demo states that it creates no learning record and shows none. No live-session, packaged-app, accepted visual-reference or pixel-parity claim is made.

Verification: strict TypeScript, full desktop ESLint, 83 desktop tests, 21 autonomous-session API tests, Ruff check/format, production build, Impeccable detector and `git diff --check` passed. The production build retains the existing chunk-size warning.

final result: passed

## Scoped QA — UI Foundation + Deep Learn pilot, 2026-07-21

- Source hierarchy: HyperKnow owns Shell density, path rail, editorial reading column, flat inline state and bottom continuation; the reviewed DeepTutor revision remains interaction-engineering reference only. No upstream source was copied or ported.
- Runtime: rebuilt unsigned `/Users/a1-6/Documents/Keen/apps/desktop/src-tauri/target/debug/bundle/macos/Keen Dev.app`, bundled authenticated sidecar, isolated `com.keen.learning.dev` data and real persisted sessions.
- Final acceptance captures: `artifacts/ui-audit/2026-07-21/ui-foundation-deep-learn/02-app-restore-real-dev-app.png`, `04-active-recall-real-dev-app.png`, `01-completed-real-dev-app.png`, plus `05-inspector-present-real-dev-app.png` for a real selected document. `03-reading-real-dev-app.png` is a real persisted reading state retained from the immediately preceding build; it predates the final vertical-header and flat-label micro-fix and is not the final-code acceptance image.
- Figma: canonical file `ugwiIPdF43v2woYsLM3b9R`, frame `65:2`, `Shell + Deep Learn · In Review / Provisional · 1180×740`. It reuses local Keen variables/styles and remains Provisional.

### Findings

- Shell density is stable at the supported desktop minimum: 212 px Sidebar, compact 33–34 px rows, 16–18 px navigation/action icons, flat selected fills and no new decorative shadow system.
- Ongoing Deep Learn has one 204 px path rail and one centered 720 px reading column. Reading, recall and completion do not redefine buttons, radius or elevation; task checkpoints are flat dividers with one primary CTA.
- Cold startup visibly restored the local workspace without a central spinner. The Deep Learn component restore state mirrors header/rail/content/callout/bottom-action geometry and is covered by focused tests.
- A full app/sidecar restart preserved pending active recall for `autonomous-session-7ebd97b7-7f59-5d52-aff6-0c8dcb6025ca`; History resumed it with the source lesson hidden and no Inspector. The earlier completed session still rendered a single flat result column with no rail/Inspector.
- A real `Chain rule study note.md` selection at the wider desktop size opened the Inspector; pending recall removed both the Inspector and its Toolbar toggle. No fake source or model response was introduced.
- Native Tab order moved through Open Review, View Learning Feed, the document root and Shell navigation; the selected Learning Feed link showed the shared visible focus ring.
- Tauri prevented a native 820×700 window. A separate current-code browser reflow at that size had no horizontal overflow and resolved to a 60 px collapsed Sidebar, 184 px rail and 576 px content region; this is not packaged evidence.
- The implementation and the five saved reference images were compared manually. Keen remains denser and less content-rich than HyperKnow, the real indexed fixture is short, and the Figma frame is a structural lock rather than a pixel baseline.
- Follow-up visual polish used the same completed and pending-recall records. `artifacts/ui-audit/2026-07-21/deep-learn-polish/01-completed-english-date-real-dev-app.png` shows an English due date without seconds and one Sidebar ready status; `02-active-recall-deduped-real-dev-app.png` shows the original session context in the header, one phase label in rail Current, no defensive rail message and no Toolbar-ready duplicate. Figma remains Provisional and unchanged.

### Verification

- ESLint: passed.
- Strict TypeScript: passed.
- Focused component tests: 6 files / 58 tests passed.
- Full desktop tests: 29 files / 317 tests passed; existing React Router v7 future warnings only.
- Debug `.app` build: passed; existing Vite >500 kB chunk warning and expected no-notarization warning remain.
- `git diff --check`: passed.
- Impeccable detector: `[]`.
- Follow-up focused verification: 5 files / 80 tests passed; ESLint, strict TypeScript, rebuilt Debug `.app`, `git diff --check` and scoped Impeccable detection passed. The build retained the existing Vite chunk-size and no-notarization warnings.
- Reduced motion: CSS contract remains present and disables skeleton animation/effective transitions; the current packaged system state reported `reduced=false`. This pass did not mutate macOS settings, so packaged `reduced=true` remains unverified.

Residual boundary: no accepted Deep Learn visual baseline, deterministic long-article fixture, packaged reduced-motion-on capture, full accessibility audit, signed/notarized package or pixel-parity claim exists.

final result: passed for the scoped Shell + Deep Learn pilot; visual-baseline approval remains open

## Scoped QA — Home task-first convergence, 2026-07-21

- Approved organization reference: `references/keen/2026-07-21-figma-baseline/home-approved-155-187-1180x740.png`; no Figma node was added or edited.
- Real current-state captures: `artifacts/ui-audit/2026-07-21/home-task-first/01-restore-real-dev-app.png` and `02-error-real-dev-app.png` from the latest Debug `Keen Dev.app`.
- Both captures keep Today/queue before the secondary request workbench and preserve one flat reading axis. Restore and unavailable copy describes the blocked queue action without substituting a task or provider result.
- A healthy normal queue was not reproduced in the real app during this turn. Normal-task and empty request-first order are covered by focused component/integration tests, but they are not same-state visual evidence; compact-window, reduced-motion, and keyboard visual acceptance were not rerun.

final result: blocked for real normal-state visual acceptance; restore/error composition visually checked

## Scoped QA — Learning Feed + Task Detail convergence, 2026-07-21

- References: Approved Feed `references/keen/2026-07-21-figma-baseline/learning-feed-approved-164-179-1180x740.png`, authorized HyperKnow month organization, and the existing Keen task-detail capture. No Figma file or frame changed.
- Current Browser Demo evidence: `artifacts/ui-audit/2026-07-21/feed-task-detail/01-feed-default-browser-1180x740.png`, `02-task-detail-browser-1180x740.png`, and `03-feed-reflow-browser-900x700.png`; qualitative side-by-sides are `05-approved-vs-feed-default.png` and `06-old-vs-task-detail.png`.
- At 1180×740 the Feed had no document overflow, a 332 px task rail, ellipsized long row copy and one global Demo disclosure. The detail view kept the rail, focused the task heading, removed implementation/evidence copy and exposed one Complete sample action. Back to calendar returned focus to the original row with the shared visible focus ring.
- At 900×700 the workspace changed to a single column with no horizontal overflow; the calendar follows the queue below the first viewport. Reduced-motion coverage is CSS/component evidence only.
- Real current-state evidence: `artifacts/ui-audit/2026-07-21/feed-task-detail/04-feed-error-real-dev-app.png` from the latest rebuilt Debug app. It truthfully shows the affected queue error plus retry while preserving the calendar geometry. The app did not reach a healthy queue, so neither normal Feed nor selected Task Detail is accepted as real-app visual evidence this turn.

final result: passed for Browser/component Feed and Task Detail composition; blocked for real normal-state visual acceptance

## Scoped QA — Knowledge Base + Source Scope convergence, 2026-07-21

- References: authorized HyperKnow Knowledge Base list/empty/upload states, frozen Keen Design Direction and the existing desktop foundation; Figma was not edited because no new design direction or structure needed locking.
- Browser evidence: `artifacts/ui-audit/2026-07-21/knowledge-source-scope/01-browser-demo-default-1180x740.png`, `02-browser-demo-selected-1180x740.png`, `03-browser-demo-reflow-900x700.png`, `04-browser-loading-1180x740.png`, and `05-browser-unavailable-1180x740.png`. The qualitative reference/current comparison is `07-reference-current-side-by-side.png`.
- The page has one compact course-scope disclosure, one search/filter row and one flat source list. Demo rows carry one `Sample` state and selected availability copy; no synthetic indexed/embedding/failed state or per-row Demo action is shown.
- At 1180×740 and 900×700 the document/root scroll width equalled the viewport, selected inline detail stayed within the list, and no unnamed buttons were found. Source row focus is explicit in CSS and semantic DOM order is covered by integration tests; the in-app browser's direct Tab injection did not advance focus reliably, so a complete keyboard traversal is not claimed.
- Emulated `prefers-reduced-motion: reduce` matched and reduced row/disclosure transition durations to `0.00001s`. Loading preserves the scope/tools/list geometry rather than using a central spinner.
- Real current-state evidence: `artifacts/ui-audit/2026-07-21/knowledge-source-scope/06-real-dev-app-unavailable.png` from the rebuilt Debug app. It truthfully reports that the learning process exited unexpectedly and keeps import disabled; a healthy live list and live indexing/failed progress were not reproduced visually in the Dev.app this turn.
- Focused integration: 16 passed / 25 skipped. ESLint, strict TypeScript, Debug `.app` build, scoped `git diff --check` and Impeccable detector `[]` passed. The build retained the existing Vite >500 kB chunk warning and expected ad-hoc/no-notarization warning.

final result: passed for Browser/component Knowledge Base composition; blocked for healthy real-app visual acceptance

## Scoped QA — Conversation learning record convergence, 2026-07-21

- References: authorized HyperKnow long-answer/citation organization, frozen Keen Design Direction, and the existing Shell/reading tokens. No Figma node or external code changed.
- Browser evidence: `artifacts/ui-audit/2026-07-21/conversation-foundation/01-empty-browser-demo-1180x740.png`, `02-sample-long-content-browser-demo-1180x740.png`, and `03-sample-long-content-browser-demo-900x700.png`. The qualitative reference/current comparison is `05-reference-implementation-side-by-side.png`.
- The question and answer form one flat 65–75ch reading record; the composer remains in the page frame. The explicit sample route labels its answer once and makes no Tauri or network request; the new route contains no answer.
- At 900×700 root scroll width equalled client width and no unnamed buttons were found. Component tests cover submit, completion focus, cancel focus, retry, provider recovery, citation scope, Inspector cleanup, loading/empty scope and request-free Demo. Browser focus showed the shared 3 px focus ring; direct Tab injection did not advance reliably, so a complete browser keyboard traversal is not claimed.
- Real current-state evidence: `artifacts/ui-audit/2026-07-21/conversation-foundation/04-real-dev-app-recovering-1220x768.png` from the rebuilt Debug `Keen Dev.app`. It shows the latest UI in a truthful startup/recovery state; a healthy live provider completion was not reproduced visually.
- Persistence boundary: the unsent draft is localStorage-backed. The current transcript, generated conversation id and streamed answer exist only in the active React runtime; this is not persisted Conversation History.

final result: passed for Browser/component Conversation composition; blocked for healthy real-provider visual acceptance

## Scoped QA — History + Review convergence, 2026-07-21

- References: authorized HyperKnow History/review organization, frozen Keen Design Direction, and the existing Shell/Feed/Deep Learn tokens. No Figma node or external code changed.
- Browser evidence: `artifacts/ui-audit/2026-07-21/history-review-foundation/01-history-empty-browser-demo-1180x740.png`, `02-review-empty-browser-demo-1180x740.png`, `03-review-empty-browser-demo-900x700.png`, and `04-review-empty-compact-590x700.png`. Browser Demo remained request-free; the 590 px compact stress check measured equal client and scroll widths and found no unnamed buttons.
- Real current-state evidence: `05-history-unavailable-real-dev-app.png` and `06-review-unavailable-real-dev-app.png` in the same directory, captured from the latest Debug `Keen Dev.app` at 1220×768. Both truthfully preserve the current area and Retry action while the learning process is unavailable.
- Qualitative composites `07-history-reference-implementation-side-by-side.png` and `08-review-reference-implementation-side-by-side.png` show compatible flat hierarchy and density, but compare different states. They cannot establish same-state fidelity or pixel parity.
- Component tests cover populated/empty History, every persisted session status, one row tab stop, English dates, route identity, Review loading/read error/unavailable, reveal/rating, writing/cancel, known conflict, unknown-outcome reconciliation, exact-submission retry, unsupported expected answer, shortcut isolation and focus after success. Reduced-motion behavior remains shared CSS/component evidence; it was not forced in the packaged app.
- Visual blocker: the real app did not reach a healthy populated History or due/revealed Review state. No focused same-state crop was accepted, and image-asset quality is not applicable to these text-led surfaces.

final result: passed for Browser/component empty and responsive composition; blocked for healthy same-state real-app visual acceptance

## Scoped QA — core-loop handoff and minimal Conversation repair, 2026-07-21

- Scope: final cross-page continuity verification only. The code change is limited to Conversation route teardown/draft identity, unsupported-answer truthfulness, a single PDF citation preview and action wording; no new page, design direction, Figma node, API, provider, SQLite or persisted Conversation record was added.
- Current Browser evidence: `artifacts/ui-audit/2026-07-21/core-loop-handoff/01-conversation-demo-1180x740.png`, `02-conversation-demo-900x700.png`, and `06-conversation-demo-900x700-collapsed-disclosure-fixed.png`. The last was opened and checked after the compact Sidebar repair: it visibly retains the single `Demo` disclosure at 900 px after a persisted collapsed rail. The inspected DOM had one `main`, zero unnamed buttons and equal client/scroll width at 900 px. Emulated `prefers-reduced-motion: reduce` matched; no visible skeleton animation was present in that Demo state.
- Reference comparison: `references/hyperknow/2026-07-19-figma-screen-audit/22-conversation-citation-popover.png` and the current sample-answer capture share the frozen quiet reading column, divider and continuation hierarchy. They are not the same content or citation state: the reference shows source context while Browser Demo deliberately has no citation. This is qualitative organization evidence only, not a pixel comparison.
- Focused tests cover Conversation route switching, abort/cleanup, route-scoped drafts, grounded-false completion, citation modal Escape focus restoration, retry semantics and the existing Home/Knowledge Base/Deep Learn/Feed/History/Review handoffs. The latest Debug `Keen Dev.app` launched from the rebuilt bundle but only reached Home's truthful local-core-unavailable state: `03-home-unavailable-real-dev-app.png`. Healthy normal state was not reproduced, and no sidecar diagnosis was pursued.

final result: passed for scoped Browser/component continuity; blocked for fresh healthy Dev.app normal-state visual acceptance

## Scoped QA — Learning Feed selected-task hierarchy, 2026-07-27

- Rejected reference:
  `/var/folders/21/lq2y7qwx7nz2czy8zxyyc6480000gn/T/codex-clipboard-1a8b1093-85c0-417e-9930-2fea3e4a6787.png`.
- Current implementation:
  `artifacts/ui-audit/2026-07-27/learning-feed-refine-final.png`.
- Combined visual inspection:
  `artifacts/ui-audit/2026-07-27/learning-feed-refine-comparison.png`.
- State and viewport: Browser Demo, selected Today task `t2`, 1203×768.

### Findings

- P0/P1/P2: none remain in the inspected state.
- The task rail and detail pane now have separate, stable jobs: selection on
  the left and one readable continuation decision on the right.
- The rejected four-column fact table, large timeline, duplicate status pills
  and internal preview/inspection wording no longer dominate the page.
- The segmented labels remain complete; the selected row, metadata, learning
  reason, two study actions and primary Demo action are readable without
  horizontal overflow or clipped action text.
- The global Browser Demo disclosure remains the product-level boundary; the
  action footer adds only the specific no-save consequence.

### Verification boundary

- Strict TypeScript passed.
- `learningFeedPage.test.tsx` and `app.test.tsx`: 44/44 passed.
- The comparison normalizes two different crops and states. It is qualitative,
  not an accepted fixed-reference diff or a pixel-parity claim.
- Packaged Tauri, Dark, reduced-motion, long persisted copy and exact
  DeepTutor-state comparison remain unverified.

final result: passed for the selected Browser Demo state; packaged and exact-reference parity remain open

## Scoped QA — Deep Learn + Review + History, 2026-07-27

- Qualitative comparison input:
  `artifacts/ui-audit/2026-07-27/core-pages-parallel/01-reference-final-contact.png`.
  Each pair combines one reviewed DeepTutor state with the current Keen state
  at the same viewport. Different data states mean this is a structural review,
  not pixel parity.
- Current captures:
  `artifacts/ui-audit/2026-07-27/core-pages-parallel/final/01-deep-learn.png`,
  `02-review.png`, `03-history.png`, `04-deep-learn-feedback.png`, and
  `05-history-no-course.png`.
- Deep Learn has two persistent columns at the inspected width, one bounded
  reading axis, native math, natural-language recall and an inline feedback
  result. Review and History preserve truthful empty states instead of seeding
  success data.
- The persisted adaptive reason is now visible in the real remediation/practice
  flow; Review timing is explained from the real item source and FSRS state.
  These states are covered by focused tests. A real due card and persisted
  remediation were not available in the current packaged profile, so no
  fabricated screenshot was created.
- ChatGPT Pro Round 1 found no must-fix item and requested visible Agent
  decision reasons. After those existing persisted reasons were surfaced,
  Round 2 returned `ACCEPT`.
- Fresh packaged-Light evidence:
  `artifacts/ui-audit/2026-07-27/core-pages-parallel/packaged/02-history-final.jpeg`
  and
  `artifacts/ui-audit/2026-07-27/core-pages-parallel/packaged/03-review-final.jpeg`.
  The production executable reached `Learning core ready`; the apparent
  earlier binding screen did not reproduce when the final executable was
  launched directly, and authenticated `/health` requests returned 200 until
  the normal `⌘Q` shutdown completed.

final result: passed for scoped structure, interaction, truthful-state QA and packaged-Light empty-state startup/shutdown; exact same-state parity, packaged due/remediation captures, Dark/reduced-motion and efficacy remain open
