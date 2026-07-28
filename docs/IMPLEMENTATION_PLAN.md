# Implementation Plan

## Status contract

Use only these states: `not started`, `in progress`, `blocked`, `implemented / unverified`, and `verified`. “Verified” requires the acceptance evidence named in the row. This document is a living control plane, not proof by itself.

## Current product phase — guided learning flow parity

Status: **verified** for the named guided-learning journey and continuity contract. Packaged Dark, reduced-motion-on, long-content, accepted-reference, Developer ID and notarization evidence remain separate release/visual limits; they are not represented as complete here.

`docs/PRODUCT_POSITIONING.md` is the controlling product scope. The current objective is not another audit or visual-framework milestone; it is one coherent user journey from source selection and learning request through a visible path, one guided study/recall step, and a persisted return point in Learning Feed or History.

### Downloadable BYOK provider setup — 2026-07-28

Status: **verified at the catalog, local configuration, URL-contract and mocked
connection-flow boundary**. Live vendor acceptance was explicitly excluded
from this slice and is not claimed.

Native Settings now keeps first provider setup inside the existing Model
section. The learner chooses Ollama, OpenAI, or a clearly labelled
OpenAI-compatibility preset for DeepSeek, Anthropic Claude, Google Gemini,
OpenRouter, Groq, Mistral, xAI, Qwen or Kimi. Custom API base remains available
for another compatible service. Known presets own their base paths; custom
configuration owns a base URL contract and rejects a final
`/chat/completions` or `/models` URL.

The primary action is one visible state machine: save non-secret configuration
and the Keychain entry, wait for the supervised sidecar generation to change,
then test model access from the restarted learning service. Settings
distinguishes all three outcomes, keeps a Deep Learn return locked until the
current generation verifies, and does not expose secret-bearing error details.
It adds no route, full-screen onboarding, navigation item or Provider admin
surface.

Evidence:

- strict desktop TypeScript passed;
- provider catalog/configuration/browser/recovery coverage passed 4 files / 14
  tests;
- URL composition and provider connectivity coverage passed 37 Python tests;
- provider endpoint/key-origin validation passed 6 scoped Rust tests;
- no live vendor key or request was used, so the result validates catalog
  contracts and the local workflow rather than vendor availability.
- ChatGPT Pro returned `A) ACCEPT` after its five first-review requirements
  were implemented; the bounded review record is
  [`provider-release-readiness`](../artifacts/orchestrator/provider-release-readiness/pro-review.md).

The current packaged local-Alpha gate now repeats the relevant contract against
the frozen sidecar, not only source tests. A loopback OpenAI-compatible mock
with an explicit `/api/v1` base exercised provider test, grounded answer,
focused-study creation, intentional missing-model failure, recovery, token
rotation, Session restore and idempotent replay across three generations. It
passed against both the mounted DMG and retained standalone app during
`npm run package:macos`. The `34,275,318`-byte arm64 DMG has SHA-256
`87072d5c06cda56a0c1a527523887fac03c985d03bbc8b080b8cfe197083e0e2`.
Exact evidence is in
[`2026-07-28-byok-provider`](../artifacts/package/2026-07-28-byok-provider/README.md).
This is verified as an ad-hoc local Alpha; `spctl` rejection confirms that
Developer ID signing and notarization remain open for public distribution.

### Adaptive Prerequisite Intervention Loop — 2026-07-27

Status: **verified at the code, focused-test and packaged adaptive-provider
boundary**. Learning efficacy and fixed-reference visual parity remain open
and are not required to close this implementation slice.

The existing guided loop can now initiate one bounded plan proposal without a
new prompt or product surface. Learning-core is the sole eligibility authority:
the exact saved Session must contain opening Diagnostic self-report `<= 0.4`,
an incorrect deterministic Active Recall and a completed, profile/hash-matched
validated Learning Intervention artifact. The trigger is absent until all
three are true. It proposes only before the nearest future `ready`/`locked`
Unit and never rewrites the current Unit.

Adaptive start is bound to Session revision, plan ID/version, target and the
complete server trigger through a server-derived idempotency key. Start,
artifact publication and Accept each revalidate the same target/revision.
Trigger reason and evidence identities reuse the existing `agent_runs` input
and `study_plan_proposals` reason/trigger fields; Accept, Keep, append-only plan
versioning and safe Undo remain deterministic domain operations. Cold restart
restores the same run and decision. A crash after Practice commit but before
artifact-checkpoint publication now restores the exact predecessor Practice
instead of degrading to source review or creating a duplicate.

Deep Learn consumes the server projection and can start it once under React
StrictMode, waiting while the Session is paused. It shows `Agent suggested ·
not applied`, a bounded `Why now`, evidence count and Accept/Keep. It does not
expose the learner's answer, evidence IDs or a mastery claim. Explain/rephrase
provider actions disclose that the current answer and relevant cited excerpts
are sent to the configured model provider; deterministic local Practice does
not make that claim.

Evidence:

- 28 focused Python proposal/intervention tests passed;
- 45 focused desktop proposal/intervention/Active Recall tests passed;
- 9 API-client contract tests passed;
- strict TypeScript, ESLint, Ruff check/format, `git diff --check` and the
  production frontend build passed;
- an overlapped full desktop/build run reported 544/556 due to failures across
  six resource-sensitive files; after the build finished, those exact six
  files passed 146/146 in one isolated rerun;
- ChatGPT Pro returned `ACCEPT FINAL IMPLEMENTATION` in
  [`round-05-agent-loop`](../artifacts/orchestrator/round-05-agent-loop/pro-review.md).
- an isolated packaged app showed the real DeepSeek-backed proposal, persisted
  Accept as plan version 2, persisted Undo as recovery version 3, and restored
  the same undone receipt after a full app/sidecar cold restart;
- proposal/run/event counts remained `1 / 2 / 12` before and after that cold
  launch, proving that recovery did not create another proposal or provider
  execution. Native evidence is in
  [`native-acceptance.md`](../artifacts/orchestrator/round-05-agent-loop/native-acceptance.md).

This supports the bounded product statement that Keen can observe saved
learning evidence, decide when to propose a source-grounded path adjustment,
wait for learner control and persist/recover the result in the packaged native
app. It does not establish learning efficacy, accepted reference parity,
packaged Dark/reduced-motion coverage, Developer ID signing or notarization.

### Real-Provider Agent acceptance and phase stop — 2026-07-27

Status: **verified** for the existing Provider-backed intervention path in the
dedicated `com.keen.learning.provider-acceptance` profile. Native Settings
saved and tested the non-secret loopback
`openai-compatible · deepseek-v4-flash` configuration. A real source/course
advanced through a focused two-Unit plan, Diagnostic `not_yet`, incorrect
Recall, host-selected `progressive-hint@1`, one contract-validated artifact and
one canonical pending Practice. The immutable outcome row binds the exact
Session, Unit, trigger Recall, Agent run, artifact, Practice, Playbook version
and definition hash. The artifact independently retains its exact source
handle, chunk and content hash and points to the same Practice.

After multiple full app/sidecar exits, rebuilds and cold starts, the isolated
database still contained one Agent run, six events, one intervention outcome,
one Practice and one Recall. The same artifact and Practice restored together
from Home/Deep Learn without another provider execution or lineage write.
Native acceptance found and repaired a too-broad stale-intervention
suppression rule and literal bounded Markdown math delimiters. The verified
artifact now remains visible beside its current Practice, and real Agent
inline/display notation uses accessible native MathML. Focused desktop
evidence passed 4 files / 52 tests, strict TypeScript, ESLint and
`git diff --check`; the final ad-hoc arm64 app build and cold native restore
passed. Evidence and Pro's `A) ACCEPT` are under
[`provider-acceptance`](../artifacts/orchestrator/provider-acceptance/).

Pro's phase decision is **STOP**. UI convergence, durable restart continuity,
and the Provider-backed Agent vertical slice are accepted. Do not add UI,
navigation, schema, orchestration, Playbooks, analytics, or Agent-platform
scope unless a new real product need or explicit product gap reopens work.
Developer ID, notarization, causal learning efficacy, accepted visual diff and
pixel parity remain unclaimed.

### Default packaged vertical acceptance — 2026-07-27

Status: **verified** for the named default guided-learning journey in the
dedicated `com.keen.learning.vertical-acceptance` profile. A real imported and
indexed Eigenvectors source advanced through course scope, focused request,
visible two-Unit path, Diagnostic, both lessons, two Recall and Practice
cycles, Summary, scheduled Review, Home and History. Full app/sidecar restarts
during the journey and after completion restored the exact Session and
authoritative phase. Final read-only SQLite inspection retained one completed
Session at revision 14 and progress 1.0, two Recall runs, two Practice runs,
one Review item, one Agent run and three adaptive actions; the pre/post-restart
counts were identical.

The first failed Recall selected the existing `progressive-hint@1` Playbook.
The isolated profile had no provider, so the native UI truthfully showed
`provider_missing`, retained source review and created no model artifact.
Acceptance found and repaired only concrete current-slice defects: stale
intervention precedence over newer Practice, cold restoration of consumed or
pending Practice, bounded inline formulas rendering as raw delimiters, and a
mid-word deterministic source split. Focused desktop evidence passed 4 files /
50 tests with strict TypeScript and ESLint; focused Python evidence passed
20/20; `git diff --check`, sidecar freezing, final ad-hoc arm64 app bundling
and cold launch passed. Evidence and Pro's `A) ACCEPT` are under
[`vertical-acceptance`](../artifacts/orchestrator/vertical-acceptance/).

The next package is limited to a separately isolated **real-provider
acceptance** of the existing intervention/Playbook → artifact → canonical
Practice → lineage path. It must not add UI, schema, analytics, a coordinator
or an Agent platform. Successful provider output/lineage, Developer ID,
notarization, accepted visual diff and pixel parity are not claimed here.

### Deep Learn workspace refinement — 2026-07-27

Status: **verified** for the bounded Browser Demo reading, Recall and navigation
shell. The existing two-column contract is unchanged: one collapsible
learning-path rail and one bounded reading column, with source detail opened on
demand. The rail now fills the available desktop work area instead of ending
mid-page and returns to content height in the compact single-column layout.
The session header removes a repeated Demo disclosure and uses one compact
Pause control. The bottom action row groups Previous with the secondary source
action while leaving Next unit as the sole primary action; keyboard order still
reaches Recall before source detail. Browser checks at 1180×740 and 1000×720
reported zero horizontal overflow and zero unnamed buttons, and the inspected
run had no console errors. Strict TypeScript, ESLint and 3 focused files / 50
tests passed. Packaged WebView, Dark/reduced-motion, accepted-reference diff
and pixel parity remain unverified.

### Supporting-page density alignment — 2026-07-27

Status: **verified** for the bounded Browser Demo presentation, existing
supporting-page interactions and current ad-hoc packaged WebView. History and
Review already share the same
collection/queue empty-state structure, so this pass deliberately retained
them. Knowledge Base course libraries now behave visually like compact source
filters rather than oversized dashboard cards: each tile is 80 px high with a
tighter internal rhythm and the existing source table begins 60 px earlier in
the 1180×740 viewport. Selecting the first library filtered the sample source
rows from five to two and selecting it again restored all five. Browser checks
at 1180×740 and 1000×720 reported zero horizontal overflow and zero unnamed
buttons. Evidence is
[`knowledge-overview-1180x740.png`](../artifacts/ui-audit/2026-07-27/supporting-consistency/knowledge-overview-1180x740.png).
Strict TypeScript, ESLint and 3 focused files / 44 tests passed. No route,
runtime contract, data state or third-party asset changed.

A current ad-hoc `Keen UI Audit.app` then built successfully with the bundled
learning core. Strict deep code-signature verification and the bundled-sidecar
READY/jobs/cancellation/CJK/M:N/sqlite-vec/PDF/token/cleanup smoke passed. The
native 1180×740 Dark window restored real Knowledge Base, History and Review
states with the service ready; the compact Knowledge Base kept Sources visible
in the first viewport. Evidence is
[`packaged-knowledge-1180x740.png`](../artifacts/ui-audit/2026-07-27/supporting-consistency/packaged-knowledge-1180x740.png).
Normal Command-Q left neither audit app nor sidecar running. Reduced-motion-on,
accepted-reference diff, Developer ID/notarization and pixel parity remain
unverified.

### Learning Feed / task-detail convergence — 2026-07-26

Status: **verified** for the bounded Browser Demo presentation and existing
task-detail interaction contract. The split workspace retains the real
Today/Upcoming/Completed organization, course filter, calendar handoff and one
task-owned action. The visual pass narrows and densifies the task rail, gives
task titles their full row width, moves status metadata away from the title,
uses Keen teal only for current state, and aligns detail content with its sticky
next action. Non-empty sections now open their first task by default, closing
detail restores focus to the originating task and section changes open the new
section's first item. The detail toolbar uses the course as context and one
icon-only close action; Calendar remains available once in the task pane rather
than being repeated in the empty context panel. Browser checks at 1180×740 and
1000×720 reported zero horizontal document overflow; the selected row had zero
internal overflow. The final 1180×740 interaction pass reported one selected
row, one matching detail panel, zero unnamed buttons and no console errors.
Strict TypeScript, ESLint and 2 focused files / 44 tests passed. Packaged
WebView, persistent visual capture, Dark/reduced-motion, accepted-reference
diff and pixel parity remain unverified.

### Reopened Shell/Home convergence — 2026-07-26

Status: **verified** for the bounded Browser Demo Home/Shell slice. Direct
comparison with the reviewed DeepTutor v1.5.1 Home screenshot superseded the
earlier top-aligned draft. The current Keen adaptation follows the reference's
sidebar proportion, borderless Home toolbar, centered serif prompt, bounded
composer and bottom-toolbar organization while retaining only truthful Keen
navigation and actions. Existing Ask/Study submission, saved-work, recovery and
persistence behavior is unchanged. A restrained Keen-teal functional layer now
marks only the primary action, current selection/mode and focus feedback; the
composer keeps one outer focus boundary and its input no longer draws an
internal split line. Browser evidence is
[`home-deeptutor-accent-v3-1180x740.png`](../artifacts/ui-audit/2026-07-26/home-deeptutor-accent-v3-1180x740.png).
Strict TypeScript, ESLint and 3 focused files / 54 tests passed. Packaged
WebView, captured Dark state, accepted-reference diff and pixel parity remain
unverified.

### Guided-learning UI closeout — 2026-07-26

Status: **verified** for the named native keyboard path and browser responsive
boundaries. The packaged audit app retains the product's enforced 1180×740
minimum. In that real app, selecting the saved Upcoming task transfers focus to
its normalized heading; the next Tab reaches the sole `Open study` action.

The same frontend was inspected separately in browser viewports at 1000×720 and
760×700 with reduced motion enabled. Feed retained zero horizontal document
overflow at both widths; Dark Deep Learn Summary at 1000×720 and Dark History
at 760×700 also retained one main landmark, zero unnamed buttons and zero
horizontal overflow. A synthetic display-only no-space title stress case
remained bounded at both widths and did not alter persisted learning data.
Evidence is under
[`release-closeout`](../artifacts/ui-audit/2026-07-26/release-closeout/).

No product code changed in this verification increment. The prior 47 files /
538 tests, strict TypeScript, scoped ESLint, production build, ad-hoc Tauri
bundle and Impeccable results remain current. Complete screen-reader coverage,
packaged Dark/reduced-motion below the enforced native minimum, an accepted
reference diff, Developer ID/notarization and pixel parity remain unverified.
The current UI closeout stops here; further work returns to the learning Agent
and its end-to-end capability rather than unrelated visual polishing.

### Feed and History learning continuity — 2026-07-26

Status: **verified** for the named supporting-page presentation and packaged
states. A shared display-only formatter converts generated weak-concept,
misconception, resumed-session and mode-prefixed titles into learner-facing
copy; persisted task and session values remain unchanged. Feed presents a
plain-language reason, two truthful saved-step expectations and one `Open
study` action. Summary-ready History removes a repeated title/goal and the
misleading zero-progress bar, then shows the saved Recall/Practice result and
the same `Finish and schedule review` handoff used in Deep Learn and Home.

A fresh sidecar-bundled `Keen UI Audit.app` restored both real states at
1180×740. Native accessibility and screenshot inspection covered the Feed
Upcoming task/detail and the History summary record without invoking either
primary action. Evidence is
[`feed-task-detail-1180.png`](../artifacts/ui-audit/2026-07-26/supporting-continuity-native/feed-task-detail-1180.png)
and
[`history-session-1180.png`](../artifacts/ui-audit/2026-07-26/supporting-continuity-native/history-session-1180.png).
The complete desktop suite passed 47 files / 538 tests; strict TypeScript,
scoped ESLint, production frontend build, ad-hoc Tauri app bundle and scoped
Impeccable detection passed. Dark/reduced-motion, complete
keyboard/screen-reader coverage, an accepted reference diff, Developer
ID/notarization and pixel parity remain unverified.

### Deep Learn outcome continuity — 2026-07-26

Status: **verified** for the named result hierarchy and packaged
ready-to-finish state. Recall, targeted practice and ready-to-finish summary
retain their existing deterministic writes, recovery and scheduling contracts,
but now share one learner-facing structure: short state label, explanatory
result, two evidence rows and one truthful next action. Implementation-facing
copy about local FSRS, mastery observations and unchanged schedules no longer
dominates these normal states. The intervention phase is labeled `Learning
Agent`; generated mode prefixes are removed only from the displayed session
title, and the path rail uses the same `Finish and schedule review` handoff as
the primary action.

A fresh sidecar-bundled `Keen UI Audit.app` restored the saved summary at
1180×740 without invoking its final write. Native accessibility inspection
confirmed the normalized session title, aligned Current/Next context, summary
heading, recall/practice result list and final action. Evidence is
[`summary-ready-1180.png`](../artifacts/ui-audit/2026-07-26/deep-learn-flow-native/summary-ready-1180.png).
The complete desktop suite passed 46 files / 531 tests; strict TypeScript,
scoped ESLint, production frontend build, ad-hoc Tauri app bundle and scoped
Impeccable detection passed. Native Recall/Agent/Practice captures,
Dark/reduced-motion, complete keyboard/screen-reader coverage, an accepted
reference diff, Developer ID/notarization and pixel parity remain unverified.

### DeepTutor reference pair 1 — Chat/Home — 2026-07-26

Status: **verified** for the bounded Browser Demo Keen Home adaptation and
**implemented / unverified** for the editable upstream reference replica. The
initial mixed frames `238:157` and `238:327` failed visual review and remain
hidden as Rejected. Canonical Figma page `238:497` contains official upstream
screenshot reference `252:202` and editable replica `257:157`, both 1180×660
and visually inspected. Same-size comparison reported RMSE `0.0734996` and
`2.12031%` of pixels outside 5% fuzz; that replica remains `In Review`, not
accepted parity.

The existing runtime `New learning` state now adapts the useful composition
without a new route or navigation item: Keen-owned mark and copy, one centered
720 px composer, Ask/Focused study controls, the real live source selector and
one send action. Saved-work Home and all source, submit, persistence and
recovery contracts remain unchanged. Acceptance evidence is strict TypeScript,
ESLint, 3 focused desktop files / 45 tests, and the 1280×800 Browser Demo capture
[`home-new-learning-browser-demo.png`](../artifacts/ui-audit/2026-07-26/deeptutor-home/home-new-learning-browser-demo.png),
which recorded zero horizontal overflow, zero unnamed buttons and no console
errors. No DeepTutor code, logo, copy or runtime asset was incorporated.
Packaged WebView, Dark/reduced-motion and pixel parity remain unverified.

### DeepTutor reference pair 2 — Knowledge Base overview — 2026-07-26

Status: **verified** for the bounded Browser Demo overview adaptation. The
reviewed upstream visual is
`assets/figs/web-1.4.6+/knowledge/00-overview.png` at immutable DeepTutor
revision `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a`. Keen did not reproduce the
reference's retrieval-engine catalogue because those provider/admin choices are
not current Keen product capabilities.

Instead, the existing real course scopes now form a two-column `Course
libraries` collection with source and readiness counts derived from runtime
documents. Selecting a library filters the existing source table and native
course filter; selecting it again restores all sources. Import, indexing,
search, course creation, source actions and learning handoff remain the existing
truthful contracts. Acceptance evidence is strict TypeScript, ESLint,
Impeccable detection, 2 focused desktop files / 68 tests, and the 1280×800 plus
900×700 Browser Demo captures under
[`deeptutor-knowledge`](../artifacts/ui-audit/2026-07-26/deeptutor-knowledge/).
At 900×700 the library retained two 377 px columns and left the Sources heading
and first source row visible in the initial viewport. Both inspected widths had
zero horizontal overflow and zero unnamed buttons; the desktop run had no
console errors. No DeepTutor source, component, route, brand or screenshot
asset entered the product. Live source-content preview, packaged WebView,
Dark/reduced-motion and pixel parity remain unverified.

The selected-source workspace delta is now **verified** for the named live-PDF
path in the ad-hoc packaged app. The old inline expansion has become a
course-scoped source rail plus one content stage. Browser Demo remains
metadata-only. In live mode, PDF sources use Keen's authenticated
`getDocumentContent` boundary and PDF.js runtime with bounded bytes,
cancellation, retry and previous/next page controls; unsupported formats show
a truthful unavailable state instead of invented content. Browser checks
measured a 248 px rail / 742 px preview at 1280×720 and a 220 px rail / 542 px
preview at 900×700, with one `main`, zero horizontal overflow and zero unnamed
buttons.

A fresh sidecar-bundled `Keen UI Audit.app` at 1180×740 restored and rendered a
real three-page PDF. Its lower reader hierarchy now exposes Availability and
one `Start focused study` action first, shows index recovery only when
applicable, and moves course membership plus `Delete source` behind a collapsed
`Source settings` disclosure. Native accessibility inspection confirmed the
PDF page image, pagination, study action, and collapsed/expanded settings;
neither learning nor deletion was invoked. Current evidence is under
[`knowledge-reader-native`](../artifacts/ui-audit/2026-07-26/knowledge-reader-native/).
The complete desktop suite passed 46 files / 531 tests; strict TypeScript,
ESLint, production frontend build, ad-hoc Tauri app build and scoped Impeccable
detection passed. The Debug PDF's initial render took about 25 seconds and was
not benchmarked. Dark/reduced-motion, complete keyboard/screen-reader coverage,
an accepted visual diff, Developer ID/notarization and pixel parity remain
unverified.

### Current app rebuild and Reduce Motion blocker — 2026-07-25

Status: **implemented / unverified** for the remaining native visual state. The
current Feed and Deep Learn UI changes are present in a newly rebuilt ad-hoc
arm64 `Keen.app`; production frontend/Rust build, desktop and sidecar
architecture checks, and strict deep code-signature verification passed.

Packaged reduced-motion-on is still blocked. A second attempt reached
Accessibility but the System Settings control channel closed when opening
Display and remained unavailable after reconnect. No preference was changed.
The rebuild therefore provides package integrity, not native reduced-motion or
latest-screen visual evidence.

### Whole-product anti-template pass — 2026-07-25

Status: **verified** for the inspected Browser Demo states at 1180×760. Home,
Feed empty/selected detail, Deep Learn, Knowledge Base, History, Review, and
Settings were reviewed as one product. Demo Deep Learn now reuses the existing
two-column live session-header variant, reducing the header from 120 px to
74 px. Feed's unselected detail no longer renders empty pseudo-fields that
suggest missing data; the real task-detail contract is unchanged. Both repaired
pages retained zero horizontal document overflow.

Focused validation passed **2 files / 50 tests**, strict TypeScript and ESLint;
the scoped Impeccable detector returned no findings. This does not establish
packaged-WebView completion, accepted-reference parity, full accessibility,
Developer ID/notarization, or pixel parity.

### Deep Learn keyboard and long-content boundary — 2026-07-25

Status: **verified** for the Browser Demo slice at 1180×760. The keyboard order
is covered from the session control through the collapsible path and its seven
units to the recall action. The bounded reading column now applies inherited
`overflow-wrap: anywhere`, preventing unbroken formulas, identifiers, and URLs
from being clipped without a horizontal recovery path. A temporary browser
stress case measured 1,794 px of internal paragraph overflow before the change
and zero afterward, with zero document overflow in both measurements; bundled
content was restored by reload.

The focused Deep Learn file passed **27/27 tests**, strict TypeScript and
ESLint. This does not verify every application keyboard route, arbitrary
persisted renderer content, or packaged reduced-motion-on. The latter remains
unverified because the macOS UI-control channel failed before any preference
change; no system preference was changed.

### History current-mastery snapshot — 2026-07-25

Status: **verified** for the bounded component/runtime slice. History now reuses the existing typed `/v1/demo-state` mastery read for the selected course, filters out untouched priors (`attempts = 0`), ranks the weakest recorded concepts first and caps the view at six rows. The bars expose semantic meter values and attempt-count text; they do not simulate a historical trend. New explicit Focused Study requests derive their persisted concept label deterministically from the bounded retrieval topic instead of copying the complete learner goal. Existing concepts and evidence are not migrated or rewritten; legacy long labels are visually ellipsized while their full title and meter name remain available.

Focused History tests passed **20/20** and the complete Focused Study API file passed **19/19**, including long English request, direct topic and Chinese topic labels. Strict TypeScript and scoped ESLint passed. The Python sidecar was freshly frozen, and a rebuilt ad-hoc Debug app displayed the three real persisted Calculus I rows at 13%, 63% and 76% with the legacy request bounded to one line. Strict deep signature verification passed. Native evidence is under `artifacts/ui-audit/2026-07-25/mastery-snapshot/`. No migration, new endpoint, dependency, external chart implementation, efficacy claim, accepted baseline or pixel-parity result was added.

### Shell/Task Detail/History/Review truthfulness fixes — 2026-07-25

Status: **verified** for the bounded component/runtime slice. The Toolbar's duplicate `New learning` button is removed (Sidebar, command palette, ⌘N and native menu behavior unchanged; the app now exposes exactly one visible `New learning` entry). Task Detail drops the fabricated completed `Review the learning goal` Expected-steps item—the goal already appears as neutral text above—and the remaining truthful steps renumber from 1. History replaces the two separate empty lists with one combined empty composition (single `New learning` action to `/?mode=ask`, no `Start study`) only when a course exists and both successful Questions and Study sessions reads are empty; single-empty, error, partial, stale-course and no-course Knowledge Base states are preserved. Review and targeted Practice now share one display-only source-cloze parser: Review keeps ordinary prompts unchanged but presents a cloze as a visible blank, a separate normalized equation and truthful self-review instruction. Persisted prompt, expected answer, grading, FSRS and write contracts remain unchanged.

Focused tests passed **6 files / 100 tests**; strict TypeScript, scoped ESLint, the ad-hoc Debug app build and strict deep signature validation passed. Native inspection verified one visible creation entry, Task Detail steps numbered 1–2 without a fake completion, and the real due Review rendered `y′ = f′(g(x)) · g′(x)` with an accessible blank. The History both-empty composition is covered by component regression rather than manufactured native data. Evidence is under `artifacts/ui-audit/2026-07-25/supporting-pages-refinement/`. No migration, accepted baseline, Developer ID/notarized release or pixel-parity claim is added.

### Deep Learn V3 interaction preview — 2026-07-25

Status: **implemented / unverified**. `docs/design-previews/agent-composer/deep-learn.html` is a design-only interaction preview for the next bounded Deep Learn refinement; it does not change the React/Tauri runtime or persisted learning contracts. It keeps the canonical Sidebar, a collapsible path rail and one 65–75ch learning document, while one stateful Learning Dock moves through Ask, closed-book Recall, deterministic feedback, targeted practice and the next-unit handoff. Quick Recall belongs to the current unit rather than the path, citations open on demand, and completion remains inline.

Fixed-viewport browser inspection covered 1510×1107, 1280×900 and 1180×800 with zero horizontal document overflow and one visible input. Starting Recall removes the answer-bearing lesson from visual and accessibility presentation, focuses the textarea, compacts the path and places the Dock 36px after the locked-next-step copy. Empty/double submission is blocked; hint use persists across retry; incomplete answers offer Try again plus source review; explicit misconceptions enter one targeted practice; correct completion exposes one Continue action. Continue advances Capturing photons to done, Electron transport to current, and both progress projections to `Step 5 of 6 · 4 completed`, then restores an honestly labelled Ask preview. All named paths, source/Escape, collapse compatibility and console/page errors were checked. This is not an accepted visual baseline, pixel-parity result, complete accessibility audit, packaged-WebView result, live Provider run, persistence result, or approval to replace the current production page. The next step is explicit visual acceptance followed by mapping these states onto the existing Deep Learn runtime components and contracts.

### Deep Learn Recall focus mapping — 2026-07-25

Status: **verified** for the bounded component/runtime slice. The existing typed Active Recall lifecycle remains authoritative: no preview keyword grader, alternate route, backend mutation or parallel session state was copied into production. When the restored outcome is `pending`, Deep Learn now exposes one `Closed-book recall` phase, retains the existing pre-paint lesson/Inspector protection, removes the phase's redundant top separator and focuses the current response field. `not_started`, paused, recovery and terminal states keep their existing controls; an answered result removes focus mode and transfers focus to the real result heading before the established Agent/source-review/Practice routing continues.

Focused validation passed **2 files / 40 tests**. Strict TypeScript, scoped ESLint and `git diff --check` passed. The tests cover hidden source-derived lesson text, the closed-book semantic/class contract, response focus, generated title/goal deduplication, typed begin/answer calls, focus-mode exit and answered-result focus.

The current worktree was then rebuilt as an ad-hoc Debug `Keen Dev.app` with the dev and sidecar configs. After a complete app/sidecar restart, History restored persisted session `focused-session-151b83d4-fed0-5f35-88ab-2c359f0979b2` directly to its pending Recall. Native 1220×768 captures verify the deduplicated session header, `Closed-book recall` label, sole focused textarea, hidden lesson/Inspector, and safe expanded/collapsed path rail. Keyboard traversal reaches the response first and skips the disabled submit. Read-only SQLite confirmed session status `active_recall`, revision `6`, progress `0.0`, one pending Recall with no answer key, no mastery event and no Review handoff; no answer was submitted during inspection. Strict deep code-signature verification passed for the bundled arm64 app and learning-core executable. Evidence is under `artifacts/ui-audit/2026-07-25/recall-focus/`.

This remains a local ad-hoc Debug result, not an accepted reference, complete accessibility audit, Dark/reduced-motion-on capture, Developer ID build, notarized release or pixel-parity result. The remaining V3 preview ideas—one consolidated Ask/Recall Dock, persistent hints and its demonstration-only next-unit choreography—are not production claims and require separate contract decisions.

### Contextual Provider recovery and packaged acceptance — 2026-07-25

Status: **verified for the recovery contract and bounded positive real-provider intervention; local package evidence remains as recorded below**.

This closes the first-run gap in the bounded Agent intervention without adding navigation, a provider-administration product, an open composer, or a second learning-state model. A `provider_missing` intervention now offers one contextual Settings route plus the existing source-review fallback. The return target accepts only the canonical exact Deep Learn Session/Course pair. Settings prevents stale-runtime tests, waits for a newly healthy sidecar generation after save, exposes a bounded retry when restart fails, and returns only after testing that current generation. Python re-offers the persisted failed intervention as eligible after configuration, but never starts it automatically; the learner must explicitly invoke the Agent again.

| Slice | Status | Delivered behavior | Acceptance evidence |
| --- | --- | --- | --- |
| Exact recovery entry and return | verified | Deep Learn passes only its exact `session_id` / `course_id`; external, encoded-path, duplicate-parameter, fragment, control-character and secret-bearing targets fail closed. Settings opens Capabilities with compact context and no Browser Demo credential form. | Focused route/message/Settings/intervention coverage is included in the full desktop **43 files / 500 tests** result. Strict TypeScript, ESLint, production build and `git diff --check` passed. |
| Save → replace → test state machine | verified | A dirty draft cannot test the old runtime; save must produce a newly healthy connection generation; terminal replacement failure enables an explicit retry; only a successful current-generation test exposes the exact return action. Secrets stay outside configuration JSON, argv, environment variables and logs. | Rust format/check/Clippy and **49/49** tests passed. The current arm64 `.app` and DMG passed deep signature, sidecar, token-rotation and Review/FSRS restart/replay smokes. |
| Persisted Provider-missing re-offer | verified | Only the latest `failed/provider_missing` intervention projects back to `eligible` once the replacement runtime has a configured provider. No Agent run is auto-created; other provider/runtime failures retain their existing fallback. | Focused Python Provider/intervention regression passed **107/107**; the earlier combined learning/Provider matrix remains **219/219**. |
| Positive real-provider golden path | verified | A real loopback LiteLLM `openai-compatible` call to `deepseek-v4-flash` after an incorrect Recall created a strictly schema- and source-handle-validated artifact, rendered its explanation/source plus independently scored pending Practice, completed Toolbar/Activity, and restored the same artifact/Practice through full app/sidecar restart and History. | Read-only SQLite keeps five runs, including four development failures. Successful `run-09c9d2d2a4b843ba91eeb26d03ca4b66` has exactly one checkpoint and one done; only `practice-run:c53a6d38-ad61-5192-a893-4af24b02ec0b` is pending. Counts were identical before/after restart: tasks 2, mastery events 3, state mutations 0, tool invocations 1. Latest focused backend 7 files all passed (checkpoint review 63/63); frontend 6 files / 117 tests; full `npm run check` exit 0: frontend 43 files / 503 tests, Python 1127, Rust 49, lint/typecheck pass. |

`npm run package:macos` exited 0 and retained [Keen.app](../apps/desktop/src-tauri/target/release/bundle/macos/Keen.app) plus the 34,197,306-byte [Keen_0.1.0_aarch64.dmg](../apps/desktop/src-tauri/target/release/bundle/dmg/Keen_0.1.0_aarch64.dmg), whose SHA-256 is `2133f67132507c34d2e57810a868052c70cd96b590faccbb7b9e096e03e5c5ec`. `hdiutil verify` returned `VALID`; strict deep code-signature, arm64 desktop/sidecar, bundled-sidecar and restart/recovery smokes passed. Read-only native inspection in the host's dark appearance found no Settings → Capabilities clipping and verified Endpoint → Model Tab order with the disabled save action omitted. This is ad-hoc arm64 evidence, not Developer ID signing, hardened runtime, notarization, universal/Intel support, a stored visual baseline, or pixel parity.

### Current capability phase — bounded Agent-native learning — 2026-07-23

Status: **in progress overall; Slices 0–3 are verified at their named boundaries**. Slices 0–2 retain their bounded real-provider evidence. Slice 3C closes the previously read-only Plan Proposal with explicit Accept/Keep, deterministic revision/source validation, an append-only plan version, a truthful receipt and bounded safe Undo. `docs/AGENT_NATIVE_ARCHITECTURE.md` is the detailed architecture and delivery contract. The current Alpha and lightweight-continuity records below remain the source of truth. The contextual Agent surface restores durable per-Conversation / per-Study-Session activity through the existing on-demand toolbar Activity entry. Deep Learn implements the policy-selected post-Recall intervention, versioned Teaching Playbook, bounded source-grounded artifact contract, explicit Practice handoff, Provider-missing recovery and quiet closed-intent steering without giving the model ownership of learner truth. Candidate extraction and any learning-outcome claim remain out of scope.

`docs/AGENT_NATIVE_USER_RESEARCH.md` now records the directional learner-problem basis from public study/PKM communities, tutoring studies, and human–AI guidance. It is not representative research or proof of demand. It tightens Slices 0–2 around one mixed-initiative, source-inspectable, post-attempt intervention and explicitly rejects bulk generation, hidden review debt, transcript-based learner Memory, generic Agent chrome, and model-authored learning truth.

Entry gate: passed after the current guided-flow/continuity phase was frozen with independent Sol-high **P0 = 0, P1 = 0**, 35 desktop files / 440 tests, strict TypeScript, ESLint, production build and `git diff --check` passing. Retrieval expansion is explicitly not authorized: current Alpha remains lexical-only until a later bounded comparison demonstrates a material benefit. Verified Slice 3 stays inside the existing Deep Learn and plan-version boundaries and does not authorize Slices 4–7 or a new UI surface.

| Order | Slice | Status | Required behavior and acceptance boundary |
| --- | --- | --- | --- |
| 0 | Trusted learning-Agent contract | verified | Purpose-specific Run Profile, authoritative Context Assembler, deterministic eligibility policy and bounded real-provider capability path are verified. The successful host-frozen source excerpt/handle path did not invoke search; a prior failed development attempt used only read-only search. Unsupported capability still fails closed. |
| 1 | Source-grounded intervention | verified | After one real incorrect Recall attempt, a `deepseek-v4-flash` explanation was contract-validated and source-linked, persisted as one artifact/run, rendered with source and pending independent Practice, and restored after reload/full sidecar restart. JSON-object completion, bounded DeepSeek extras/index/reasoning/cache-token compatibility, completion checkpoint envelopes, and GET/SSE legacy normalization are covered. Model output did not grade or mutate BKT/FSRS/Task/Session truth or create bulk future work. |
| 2 | Steering and recovery | verified | One policy-selected primary action appears before generation; one quiet `Try another approach…` disclosure follows generation; exact frozen Retry survives an uncertain write; `practice_ready` hands off once across restore/SSE disconnect; cancel, stale scope, source fallback and restart recovery fail closed. A ready-state alternative submits the selected run/artifact pair, records it in the new immutable run and artifact, rejects missing/stale identity, and permits exact idempotent replay. `Test me instead` uses the same current-head check while reusing Practice. Focused evidence passed Python 12/12, desktop 14/14 and API-client 4/4. The rebuilt ad-hoc `Keen Dev.app` then used `deepseek-v4-flash` to create source-example run `run-fa4861c9139b4c11843a49c5aa8dd1ea` / artifact `artifact-11e7674c50be3d2f95790b2ca9d877a4`, both linked to predecessor run `run-1bd241a95d5742499c630ae62c3c6c8a` / artifact `artifact-12f0d006d1bb9a15ec7f8d99f66a5e11`. Full app/sidecar restart restored the new explanation from History. The session retained one Practice; global mastery events 4, Review items 1, Tasks 5 and misconceptions 0 were unchanged. Strict deep ad-hoc signature verification passed. Native QA previously verified collapsed alternatives are absent from the accessibility tree and appear only after expansion. No open composer, equal-weight default action row, or cross-Session preference. |
| 3 | Proposed plan revision | verified | Slice 3A/B retains the bounded inline proposal, exact retry, stale/provider recovery, source-linked diff and real `deepseek-v4-flash` artifact/restart evidence. Slice 3C adds explicit Accept/Keep; acceptance revalidates the frozen Session revision, plan version, target and durable source handles under one transaction, appends a plan version that becomes effective only after the current step, and returns a persisted receipt. Keep creates no plan version. Undo appends a restore version only inside the bounded window and only before later learning evidence depends on the adjustment. The model never applies the mutation. Focused verification passed Python plan/migration 24/24, desktop component 9/9 and API-client contract 5/5, plus strict TypeScript and ESLint. The client now rejects impossible resolved receipt/apply-state combinations. This is isolated deterministic decision/Undo evidence; no decision was applied to the user's saved learning data during verification. |
| 4 | Session steward | in progress — cross-page/cache recovery verified | Home still prioritizes real due Review and persisted Tasks. When neither exists, it consumes the existing course-scoped `resume_study_session` candidate, resolves the exact current Session, rejects terminal/cross-course/missing matches, and resumes Deep Learn without creating a recommendation, Task, Journey or provider run. Confirmed Deep Learn changes now invalidate exact Session, adaptive state, Session History, Learning Snapshot and due Review queries; Home, Feed and History withhold cached actions while revalidating. A fresh QueryClient restart restores the updated Session through the existing service contracts. Focused cross-page coverage passed 5 files / 76 tests, Review/Summary regression passed 2 files / 30 tests, and strict TypeScript, ESLint and `git diff --check` passed. The current ad-hoc package rebuilt with migrations 001–031; mounted-DMG verification, strict signature, sidecar smoke, isolated Review/FSRS process restart, and a real empty-state packaged UI restart passed. A non-empty persisted Session across packaged UI restart remains the Slice 4 completion gate. |
| 5 | Versioned Teaching Playbooks and outcome lineage | not started | Ship a small code-owned declarative Playbook set with immutable version capture and real attempt/outcome linkage. Playbooks disclose only their relevant procedure to a run. |
| 6 | Hermes-like procedure candidates | not started | Only after real repeated traces exist, extract bounded Candidate procedures in an isolated job. Candidates cannot execute or enter the prompt until reviewed, replay-tested, activated, and rollback-capable. |
| 7 | Broader capability expansion | not started | Journey, new frameworks, additional tools, background Agents, and richer Memory remain outside scope until a demonstrated product need and a separate approved plan exist. |

Slices 0–2 are verified through the bounded real-provider path, and Slice 3 is verified through real proposal generation plus isolated deterministic decision/Undo boundaries. Because migration 031 is not yet a released schema, its current definition includes the decision receipt and Undo lineage; no follow-up migration 032 is required for this unreleased worktree. Slice 4 has closed Home orphan-Session recovery and in-process cross-page cache reconciliation without a coordinator or second store. The current packaged app passed empty-state UI restart and the isolated sidecar passed Review/FSRS restart. Its next executable target is one non-empty persisted Session in an isolated packaged profile: prove Home, Feed, Deep Learn, History and Review choose the same authoritative action before and after the process boundary without writing a fixture to the user's profile. Do not add an Agent page, automatic Skill activation, unrestricted tools, a second runtime/session truth, or a new vector/RAG framework. The existing retrieval comparison gate still governs any vector expansion.

### Lightweight learning continuity and retrieval decision gate — 2026-07-22

Status: **verified**. This phase reuses Course, Task, Conversation, Study Session, Review, Feed, and History. It does not add a `LearningJourney` table, new navigation, long-range AI curriculum, retrieval framework, or vector product surface.

| Slice | Status | Delivered or required behavior | Acceptance evidence |
| --- | --- | --- | --- |
| Cross-course Home `Next up` | verified | Home combines the existing authenticated, snooze-aware per-course Learning Snapshots instead of deriving saved work from the first course only. It deterministically selects by saved priority, due time, and stable identity; displays the task's real course; and preserves exact task scope while retaining the mutually exclusive saved-work/New-learning compositions. | Strict TypeScript and ESLint passed; focused Home/continuity/Feed/Deep Learn/API-client tests passed 5 files / 140 tests, including a higher-priority task from the second course, deterministic ties, empty truth, exact route continuity, and persisted Feed/Deep Learn targets. |
| Goal continuity through existing records | verified | Home resolves the selected task's exact originating Study Session through the existing session-history contract. A match shows the persisted goal, progress, and phase-specific next action and resumes that exact Deep Learn route; a non-Session task continues through its scoped Feed detail. Existing Deep Learn and History remain the detailed current-step and saved-record surfaces. No Journey record or duplicate state was created. | Focused Home/continuity/Feed/Deep Learn/API-client tests passed 5 files / 140 tests. A freshly rebuilt packaged UI-audit app restored the existing Alpha Bayesian task/session before and after restart, showed its exact saved goal and `Finish summary` action, and opened the exact course-scoped Deep Learn route. Both quits released the app, sidecar and database lock. No fixture was created for this check. |
| Retrieval expansion decision | verified | Retain the already verified lexical-only path for the current Alpha. No embedding provider is configured, no bounded lexical/hybrid comparison has demonstrated a material gain, and therefore hybrid/vector expansion is not authorized in this phase. A later comparison may reopen this decision without creating a new evaluation platform. | The real DeepSeek Alpha path completed Ask → persisted answer/citation → reload/History with `lexical_only`; no vector-provider success or semantic-retrieval result is claimed. |
| Next-action reconciliation | verified | Home withholds lower-priority tasks until due Review truth is known, resolves the exact persisted Session across courses, and exposes no cached action while the learning core is unhealthy. Review and Summary mutations invalidate and refetch all due-review, Learning Snapshot and Session History caches; completion navigation stays locked until that refresh settles. Review due time updates while the page remains open, invalid dates fail closed, and IME composition cannot submit Home. | Focused continuity/Home/Review/Summary tests passed 4 files / 54 tests; the complete desktop suite passed 35 files / 440 tests; strict TypeScript, ESLint, production build and `git diff --check` passed. Independent Sol-high final acceptance found P0 = 0 and P1 = 0. |

The repository already contains embedding model/state tables, loopback embedding providers, sqlite-vec search, embedding-only reindex, hybrid RRF fusion, and explicit lexical fallback. This phase therefore evaluates and reuses that implementation rather than introducing another vector store or RAG framework. The current Alpha's real DeepSeek acceptance remained lexical-only because no embedding provider was configured; no new vector-success claim is made here.

### Goal-owned Focused Study Start — 2026-07-22

Status: **verified**. This closes a truthfulness gap in the existing Home → Deep Learn loop; it does not add a `LearningJourney` model, new navigation, provider call, Agent framework, or visual direction.

| Slice | Status | Delivered behavior | Acceptance evidence |
| --- | --- | --- | --- |
| Explicit learner request | verified | Home Study submits one authenticated `POST /v1/focused-study-requests` command instead of first accepting a course-wide Feed recommendation. The canonical selected course and learner goal own the resulting existing task, Study Session, and persisted plan. | Home/client focused tests and independent route inspection confirm Study no longer calls autonomous recommendation or autonomous session start. |
| Source and recovery truth | verified | The command NFKC-normalizes a bounded goal, rejects control characters, retrieves only current indexed chunks in the selected course, and fails closed when no source matches. On success the exact chunk IDs are persisted in task provenance, session goal scope, and plan units; the ordinary Deep Learn diagnostic then continues into `studying`. | Focused service/API coverage for course scope, foreign-source exclusion, lexical no-match, CJK-invalid input, false-pronoun matches, restart, diagnostic continuation, and one active unit. |
| Durable request identity | verified | Additive migration `030` binds `client_request_id` and `idempotency_key` to one canonical request. Payload/key/client drift conflicts; an uncertain committed write replays the same task/session/plan after restart. A blocked request stores only bounded identity metadata, creates no learning-domain record, and may atomically advance only when matching material later becomes available. | Focused request/guard/migration suite 39/39; independent probes cover blocked zero domain writes, both-identity collision rejection, blocked-to-created recovery, and corrupt-link 503 fail-closed behavior. |

Independent Sol-high final acceptance found **P0 = 0, P1 = 0, P2 = 0**. The focused desktop client/Home suite passed 23/23; the proportional Deep Learn/Home regression run passed 67/67; strict TypeScript, ESLint, Ruff check/format, production build, and `git diff --check` passed. Existing Starlette/httpx and React Router future warnings remain non-failing. This is deterministic lexical retrieval only: it does not claim embeddings, semantic/provider retrieval, a real model answer/citation, a new packaged-WebView capture, visual baseline, accessibility-complete pass, signing/notarization, or pixel parity.

### Exact Review task handoff — 2026-07-22

Status: **verified**. This is a narrow correction to the existing Feed → Review return path; it adds no navigation, learning type, provider behavior, visual direction, or synthetic review state.

| Slice | Status | Delivered behavior | Acceptance evidence |
| --- | --- | --- | --- |
| Exact task completion | verified | A Feed task whose source is a due Review opens only its exact course/item/task context. `taskContext { taskId, courseId }` is all-or-none, migration `029` persists its originating task identity, and first rating atomically writes the FSRS attempt/schedule plus an ID/revision-bound completion of that exact active task. Direct Review ratings deliberately complete no Feed task. | Duplicate matching tasks, missing/wrong/inactive tasks, rollback, bare Review, replay, migration and course/source checks are covered by the focused Python suite. |
| Fail-closed recovery | verified | Partial handoff URLs never query or rate a global card. A task-bound 404 or non-retryable 409 closes scoring without substituting another card; 404 returns to Feed, while a still-identifiable 409 returns to the course task without falsely selecting Completed. A forged replay has its own non-retryable `review_attempt_idempotency_conflict` contract. | Focused Review/Feed/API-client desktop tests cover partial URLs, 404, non-retryable 409, both recovery routes, and the preserved completed deep link. |

Independent Sol-high final acceptance found **P0 = 0, P1 = 0**. Focused backend `review_api + review_items + migrations` passed 34/34 (one existing Starlette/httpx deprecation warning); focused desktop `flashcardsPage + learningFeedPage + apiClient` passed 111/111; strict TypeScript, ESLint, relevant Ruff check/format, and `git diff --check` passed. This does not add a packaged Tauri/UI capture, visual-diff result, accepted reference, complete restart replay with task context, SQLite lineage trigger, request-body guard expansion, signing/notarization, or pixel-parity claim.

### Source-tree stability check — 2026-07-22

Status: **verified for the current source tree**. The final stabilization pass corrected seven legacy migration assertions that still treated migration `028` as the latest schema even though the current staged guided loop includes additive migrations `029` and `030`; the stabilization repair adds no schema or runtime learning behavior beyond that staged implementation.

The complete configured Python suite exited successfully after that correction. Desktop validation passed 33 test files / 425 tests; Rust passed 40 tests; ESLint, strict TypeScript, Ruff check/format, `cargo fmt --check`, all-target `cargo clippy -D warnings`, the production Vite build, and `git diff --check` passed. Existing React Router future warnings and the Vite chunk-size warning remain non-failing. This source-only check does not make an earlier `.app` or `.dmg` represent the current tree, add a native visual capture, claim a release package, or change the documented unsigned/notarization and visual-reference limits.

### Packaged current-source verification — 2026-07-22

Status: **verified for the isolated bundled-sidecar lifecycle; not a release-package claim**. After freezing the current learning core with migrations `001` through `030`, a fresh local ad-hoc `Keen UI Audit.app` was rebuilt from this source tree. Its bundled executable is byte-identical to the freshly frozen sidecar and the PyInstaller archive contains migrations `028`, `029`, and `030`.

`codesign --verify --deep --strict` passed. The isolated bundled-sidecar smoke passed, including READY, authenticated service startup, document/index lifecycle, cancellation, PDF content and cleanup; the independent Review-restart smoke also passed token rotation, due reads, FSRS rating, restart recovery, idempotent replay, and single-attempt persistence. These checks used temporary local data and do not claim a user-data migration, native visual interaction, dark/reduced-motion/long-content capture, accepted visual reference, `.dmg`, Developer ID signature, or notarization.

### Alpha 0.1.0 RC baseline — 2026-07-22

Status: **verified as a local ad-hoc Alpha candidate**. The packaging workflow now retains both the standalone `.app` and the unsigned `.dmg`, verifies migrations through `030`, and runs the bundled service plus Review restart/replay/FSRS checks without relying on buffered text-pipe timing. The mounted DMG and standalone app passed deep signature verification and lifecycle smoke.

The repository-local app reached ready, exited without leaving its sidecar or database lock owned, restarted to ready and exited cleanly. A copy installed from the read-only mounted DMG also reached ready and exited cleanly. One pre-existing orphan development sidecar initially owned the production database lock; its parent/identity/age were confirmed before a normal termination, no data or lock file was removed, and the RC recovered through the existing Retry action.

The focused backend loop matrix passed across eight files and the matching desktop workflow matrix passed 6 files / 124 tests. Existing real provider evidence was rechecked read-only rather than regenerated: the isolated Dev state retains indexed material, completed DeepSeek messages, citations, Recall, Practice, Review and a completed task. The exact artifacts, hashes and limits are in `docs/ALPHA_RC.md`. No Developer ID, notarization, public release, vector-provider success, external write, new visual capture, accepted reference or pixel-parity claim is added.

### Adaptive Session remediation — 2026-07-22

Status: **verified** for the bounded first branch; it does not start a general Agent loop or replace the existing Study Session state machine.

| Slice | Status | Delivered behavior | Acceptance evidence |
| --- | --- | --- | --- |
| Deterministic post-recall branch | verified | New production Study Sessions opt into `adaptive-session-policy/1.0.0`. An answered correct Active Recall creates one persisted pending Practice action; an answered incorrect Recall creates one persisted Remediate action. The session remains in `practicing`; legacy sessions remain canonical. | Additive migration `028`, migration/history assertions, 123 focused Python tests, and independent re-acceptance with P0/P1/P2 = 0. |
| Source-grounded remediation | verified | The learner rereads the saved current unit only, then completes one in-place `Continue to practice` action that reveals the existing Practice step. Remediation creates no provider output, plan change, BKT/mastery, FSRS/Review, task, or source mutation. | Transaction/replay/gate tests plus 54 focused desktop tests. |
| Recovery and strict contract | verified | `GET /adaptive-state` and idempotent remediation completion are typed in Pydantic and Zod; pending action, pause/reload, stale revision, 409 reconciliation, unknown-write restore, terminal cancellation, and a late exact replay are explicit. Practice cannot bypass unresolved remediation. | Independent read-only re-acceptance: P0/P1/P2 = 0; focused Python 6/6 and desktop 20/20 rerun. |

The branch is intentionally narrow: it has no `remediating` session status, no new route or navigation item, no dynamic plan rewrite, no LLM decision, no repeated practice adaptation, and no new visual system. The inline Deep Learn state reuses the existing reading column and path rail. It has focused component coverage for source-only content, focus handoff, keyboard-reachable retry, paused state and recovery. It does **not** add a packaged Tauri screenshot, accepted visual reference, pixel-parity result, or live-provider claim; those remain separate evidence limits.

### Binding UI closeout plan — 2026-07-22

Status: **in progress**.

This is the only active product sequence after the completed learning-loop foundations. It changes presentation and information architecture only unless a discovered defect prevents an already-implemented action from remaining truthful. Existing Tauri, React/Vite, FastAPI, SQLite, authentication, sidecar, Provider, Conversation, Study Session, mastery, FSRS, Feed, History, and Review contracts remain authoritative.

| Order | Slice | Status | Required change | Acceptance gate |
| --- | --- | --- | --- | --- |
| 1 | Shell and Sidebar convergence | verified | One `New learning` entry; remove the duplicate New study session action; keep Home, Knowledge Base, Learning Feed, History, Review, and Settings; simplify the healthy footer state; keep future/demo routes undiscoverable | Unique route/action mapping; collapsed and expanded Sidebar; keyboard order and focus; no clipping at 1220×768, 1000×720, or 760×700; focused Shell/navigation tests |
| 2 | Learning Feed and Task Detail convergence | verified | Default to Today/Upcoming/Completed task organization; move calendar behind a secondary view; preserve master/detail context; reduce each task to one primary Start/Continue/Review action plus real `Later…` when supported; completion comes from Study/Review | Populated, empty, loading, unavailable, invalid, cancelled, unknown-outcome, long-title, and cross-course states; wide two-pane and narrow list→detail behavior; focus entry/return; focused Feed tests |
| 3 | Deep Learn convergence | verified | Keep a collapsible path rail and bounded reading column; make citation/source detail on-demand; remove default three-column density and large completion-card treatment; retain real diagnostic, explanation, recall, practice, multi-unit, pause/resume, summary, and Review handoff behavior | Active, paused, restored, intermediate-unit, final-summary, unavailable, conflict, and unknown-write states; long content; 1180–1280 px two-column maximum; locked steps excluded from keyboard flow; focused Study tests |
| 4 | Supporting-page consistency | verified | Verify Home without structural redesign; align Conversation, History, Knowledge Base, Review, and Settings to the same buttons, fields, row density, reading measure, operational copy, and state vocabulary; keep demo routes release-undiscoverable | One primary action per region; 12 px readable auxiliary-text floor; 65–75ch prose; no future integrations or fabricated data; focused page tests only where code changes |
| 5 | Packaged Tauri closeout | partially verified | Rebuild the current ad-hoc audit app after the UI slices; inspect real states without adding a new harness or baseline framework | 1440×900, 1220×768 and the enforced 1180×740 native minimum; 1000×720 remains browser-only stress evidence; keyboard navigation, long content, Light/Dark, reduced motion, state recovery; record `missing_reference` rather than claiming parity where no accepted reference exists |

Execution constraints:

- Use the existing Figma file only for delta frames that resolve an implementation ambiguity. Do not redraw completed Home states, rebuild the component library, create a new file, or wait for Figma when the runtime contract already decides the layout.
- Use one writer for shared Shell/CSS/token files. Mechanical state-matrix checks may run separately only when they do not write overlapping files. A higher-reasoning reviewer performs the final read-only product/truthfulness acceptance.
- Do not modify Python, Rust, SQLite migrations, Provider configuration, retrieval, mastery, FSRS, or sidecar behavior during this UI closeout unless a directly observed P0/P1 defect blocks an existing UI action. Any such exception must be isolated, justified, and re-verified before returning to the UI order.
- Do not implement Complete/Snooze/Reschedule/Undo as a four-action task toolbar. Do not create Planner, Memory, Visualize, Quiz, Agent Activity, integration, or provider-administration navigation. Do not import DeepTutor code for this phase.
- Do not treat documentation, Figma frames, screenshots, a successful build, or Demo fixtures as product completion. Each slice completes only after its runtime behavior and named state matrix pass.

Phase exit requires all five rows to be `verified`, no P0/P1 UI defect in the named journey, and an explicit list of external limits such as accepted visual references, Apple Developer ID, or unavailable third-party integrations. Once those conditions are met, stop; do not automatically start a new capability.

2026-07-22 UI closeout implementation note: rows 1–4 are verified on the existing runtime contracts; row 5 remains `not started` because this bounded pass stops after UI implementation and does not claim a new packaged-app result. Shell now exposes one `New learning` action and six stable destinations, Feed defaults to task context with Calendar behind an explicit secondary action, compact Feed changes from list to detail/calendar instead of stacking both, and Deep Learn adds a labelled collapsible path rail, a 65–75ch document column, flat checkpoint actions and one sticky lesson-navigation row. Home, Conversation, History, Knowledge Base, Review and Settings retain their previously converged structures and passed the complete desktop regression suite. Browser checks found no horizontal document overflow at Home 1220×768, Feed 1000×720, compact Feed 760×700 or Deep Learn 680×740; compact Task Detail returned focus to its originating task. The complete desktop suite passed 389/389, Rust passed 40/40, ESLint, strict TypeScript, the production Vite build, `git diff --check` and scoped Impeccable detection passed. The build retains its existing chunk-size warning and tests retain React Router future warnings. The refreshed visual report is `artifacts/visual-diff/report.json`: 16 pages still have no reference, eight Figma comparisons remain comparison-only, and the intentionally changed Home/Feed zero-tolerance self-baselines fail at 2.222% and 2.612%; they must be reviewed before replacement and are not pixel-parity evidence. No packaged Tauri run, accepted replacement baseline, forced packaged reduced-motion/dark-mode capture, Developer ID signature or notarization is claimed.

2026-07-22 packaged UI closeout note: row 5 is now `partially verified` against the repository-local `Keen UI Audit.app` / `com.keen.learning.ui-audit` built at 13:05 +0800 from the current worktree. WKWebView reported exact, equal `inner`, root-client and visual-viewport dimensions at 1440×900, 1220×768 and the enforced 1180×740 minimum with DPR 2; an additional shrink attempt stayed at 1180×740. Home, empty Feed, secondary Calendar and empty History rendered with `Learning core ready`. Native Tab traversal reached Sidebar, Toolbar, intent, prompt and recovery actions in order, and keyboard Calendar close returned focus to `Open calendar`. A targeted normal termination of the exact audit sidecar parent replaced PID 76471 with PID 22069 and the visible UI returned to ready without deleting data or locks. The final ad-hoc deep signature and bundled-sidecar smoke passed; the final desktop suite passed 29 files / 390 tests, strict TypeScript and ESLint passed, and the existing Vite chunk warning remains. Native verification exposed and closed a no-course Home state conflict; system appearance now drives the existing Light/Dark tokens; the unconditional Figma capture script is absent from normal and packaged output; Demo task completion is explicitly a no-write visual-state preview; Deep Learn's rail icon selector and Task Detail's visible focus were corrected. Evidence is in `artifacts/ui-audit/2026-07-22/packaged-ui-closeout/`. The refreshed visual report truthfully exits non-zero with 16 `missing_reference`, eight provisional comparisons and two superseded zero-tolerance Home/Feed baseline failures at 2.222% and 2.612%; the changed provisional Task Detail comparison is 5.284%, not parity evidence. The current system was Light with reduced motion off, so packaged Dark and `reduced=true` were implemented but not switched or captured. The isolated audit identity also had no safe long persisted study content, so packaged long-content rendering remains unverified; browser/component evidence does not replace it. The app is ad-hoc, not Developer ID signed or notarized. These remaining evidence gaps prevent a full row-5 verification claim and do not reopen the completed UI direction.

- 2026-07-22 — **verified, proportional UI closeout:** kept the existing Home/Feed/History/Conversation/Task Detail architecture and real capability boundary, but removed the remaining native-form and machine-copy artifacts from the current guided learning slice. Home is now intent → compact Source row → prompt → specific action without a surrounding AI-composer card; History and Conversation distinguish editable source choice from persisted context; saved counts and dates are learner-facing; transcript completion scroll is overflow-aware; and long real task content no longer dominates the detail view. Focused tests passed 84 Home/core cases and 99 History/Feed/Conversation/learning-core cases; ESLint, strict TypeScript, production and ad-hoc Debug `.app` builds, scoped Impeccable detection and `git diff --check` passed. The rebuilt app was inspected at 1220×768 with real persisted data and keyboard focus, with evidence under `artifacts/ui-audit/2026-07-22/ui-polish/`. This closes the user-requested small UI polish slice only. It does not claim packaged reduced-motion-on, the 1180×740 minimum, a full accessibility audit, accepted visual regression, distribution signing/notarization or pixel parity.

2026-07-22 DeepSeek Provider closeout note: a user-configured local LiteLLM gateway now exposes the real DeepSeek `deepseek-v4-flash` API to Keen through the existing `openai-compatible` loopback-provider contract. The gateway binds to `127.0.0.1:4000`; its isolated runtime and configuration live outside the repository under `~/Library/Application Support/Keen/provider-gateway`, and the user-selected credential file is plaintext with mode `0600`, not Keychain-backed. No credential value was printed or copied into the repository. A real packaged Debug-app run first exposed a frontend wire-contract defect: retrieval SSE already supplied both `chunkId` and `chunkIds`, but the strict Zod schema omitted `chunkId`, so parsing cancelled the reader and the backend durably recorded `interrupted/client_disconnected`. The schema now requires `chunkId`, requires it to equal `chunkIds[0]`, retains uniqueness and strict unknown-key rejection, and its regressions cover a real 130 ms non-empty retrieval delay plus React StrictMode single-POST/no-abort handoff. Focused desktop validation passed 86/86; the direct local-provider suite passed 27/27; independent Sol-high review found no P0/P1 blocker. The rebuilt ad-hoc Debug `.app` then completed both an existing Conversation Retry and a new Home Ask → Conversation handoff against the indexed Calculus I source. SQLite recorded the new Home turn as `completed`, provider `openai-compatible`, model `deepseek-v4-flash`, one durable citation and zero `client_disconnected`; after a full app/sidecar restart, History reopened the earlier completed answer and source. Native screenshots are under `artifacts/ui-audit/2026-07-22/deepseek-provider/`. Retrieval truthfully remained `lexical_only` because no embedding provider is configured. This verifies the real text/citation/reload path only; the gateway remains a local external adapter, the app is ad-hoc/unsigned and unnotarized, and no tool-capable Agent, vector provider, accepted visual baseline or pixel-parity result is claimed.

2026-07-22 continuity closeout note: three small, already-implemented product slices now share the same guided-learning contract. (A) Global `New learning` entry, including the native menu wording, opens Home Ask rather than a parallel new-request surface; the focused frontend evidence passed 64 tests and the Rust suite passed 40 tests. (B) Knowledge Base hands a course to Home only when its current linked source is truly indexed; stale selection and read failure fail closed instead of carrying a course hint forward. Its focused evidence passed 84 tests, with strict TypeScript, ESLint, production build and `git diff --check` passing. (C) Deep Learn → Learning Feed/History return actions preserve `course_id`, and tasks remain isolated from a different course; the initial focused run passed 55 tests and the corrected follow-up run passed 40 tests. Independent Sol high acceptance found P0/P1/P2 = 0. These are separate focused runs and are not additive full-suite counts. This closeout does not change visual direction, Figma, packaged Tauri WebView evidence, Provider/citation behavior, Apple Developer ID status, accepted visual baselines or pixel-parity limits.

2026-07-22 Home two-state convergence note: Home now has two mutually exclusive compositions instead of stacking saved work and a full request composer. A non-empty queue shows one persisted `Next up` task, a schedule link, a direct task action and a compact new-learning entry. An empty queue or explicit `?mode=ask|study` entry shows the intent selector first, then the truthful source scope, prompt and mode-specific `Ask sources` / `Start focused study` action. Live task continuation uses the formal `/feed?task=…` deep link, which opens the matching persisted Task Detail; Demo remains labelled and request-free. Independent acceptance found that the Demo CTA opened only the Feed and that its hard-coded task could outlive the Demo store state. Home now selects the first unfinished sample from the existing store, opens that exact task, and promotes New learning when no sample remains; live and Demo IDs are explicitly isolated. The canonical Figma file was updated in place with saved-work frame `196:328` and new-learning frame `197:351`. Browser captures at 1180×740 and 760×700 with reduced motion are under `artifacts/ui-audit/`; the final focused Home/Feed run passed 30/30 with desktop ESLint, strict typecheck, production/Debug app build and `git diff --check` passing. The earlier complete 29-file / 361-test suite and scoped Impeccable layout result remain applicable to the pre-fix layout; the final fix is behavioral and covered by the focused run. The rebuilt unsigned Debug app at 1220×768 rendered both Home states with the learning core ready, opened the exact persisted Task Detail, and exposed native Tab order through intent, source and prompt; captures are under `artifacts/ui-audit/2026-07-22/home-packaged/`. The build retains the existing chunk-size warning. Figma's Sidebar is older than runtime and its frames are content-contract evidence only; packaged reduced-motion-on, an accepted baseline, a real Provider answer/citation and pixel parity remain unverified.

2026-07-21 durable Conversation slice note: migration `027` additively extends the existing `conversations`, `messages` and `message_citations` tables; it does not create a second run ledger or alter historical migrations. New writes require explicit `course` or `all_indexed` scope, user/assistant reply identity, bounded retrieval configuration and durable answer timing. Completed content, provider/prompt metadata and source-indexed citation snapshots commit in one transaction before the terminal SSE event; repository transitions use SQLite compare-and-swap row counts, exact create/turn/cancel replay is idempotent, startup/shutdown recovery marks unfinished answers `interrupted`, and `unknown` remains a client-only reconciliation state. The authenticated API now supports idempotent Conversation creation, Conversation/message reads, durable answer streaming and server-confirmed cancellation while preserving legacy `/v1/answer/stream`. `/conversation/new` creates and adopts an authoritative route, saved routes restore the same transcript/citations/status, early EOF and uncertain cancellation reconcile through message GETs, and a missing turn is retried with the same IDs/key. Browser Demo makes no request. Focused evidence is backend 33/33, Request Guard 8/8 and desktop Conversation/API client 79/79; the final complete Python suite passed 1034/1034, with ESLint, strict TypeScript, Ruff, Debug app bundling, `git diff --check`, scoped Impeccable detection and independent Sol acceptance also passing. The most recent complete desktop suite is 321/342 because 21 existing `learningCore.integration.test.tsx` cases still assert superseded UI copy/state outside this slice; the final Conversation repairs are covered by the later 79/79 focused run. The rebuilt Dev.app launched once but the bundled learning core became unavailable, so healthy native persistence/restart is `implemented / unverified`; same-SQLite restart is verified through the authenticated API test process. Home Ask enters this durable path as described below, and the existing History page now lists and reopens persisted Conversations as recorded in the following History note.

2026-07-21 History persisted Conversations note: the authenticated `GET /v1/conversations` contract lists summaries from the existing migration `027` tables using bounded, versioned cursor pagination with stable `updated_at DESC, id DESC` ordering. Cursors validate timezone-aware timestamps and canonical UUIDs and are bound to the active course filter. Summaries expose explicit course or all-indexed scope, authoritative latest-assistant status, a bounded learner-facing preview, message count and timestamps without full content or raw provider payloads. History now presents independent Questions and Study sessions sections; one section's loading/error/empty state does not hide the other, missing courses fail closed as `Course unavailable`, terminal Questions open their authoritative record, and Browser Demo makes no request or record. No migration, History table, navigation, Conversation visual redesign, provider or retrieval change was added. Evidence is 108/108 focused desktop tests, 360/360 complete desktop tests, 5/5 focused Python API tests, ESLint, strict TypeScript, Ruff check/format, `git diff --check`, scoped Impeccable detection, Debug app bundling and independent Sol acceptance. The visually inspected rebuilt Dev.app capture is `artifacts/ui-audit/2026-07-21/history-conversations/01-history-unavailable-real-dev-app.png`; the bundled learning core remained unavailable, so a healthy native list/open/restart is `implemented / unverified`, and no real provider answer or citation is claimed.

2026-07-21 Home Ask → durable Conversation note: Home Ask no longer enters AgentRuntime. It requires a real indexed course scope or an explicit all-indexed choice, generates stable Conversation/turn/idempotency identities under a single-flight guard, creates or authoritatively reconciles one Conversation, navigates to `/conversation/:id`, and passes the question once to the existing durable stream. Course identity and the learner-facing scope label survive the handoff; a missing indexed scope blocks submission with a Knowledge Base recovery action. Unmount aborts the create transport without issuing a background write after a confirmed 404; an authoritative result found after unmount retains its handoff and route id for recovery. Ask failures remain bound to Ask, while non-retryable identity conflicts require a changed question or scope rather than offering a futile Retry. Study keeps its existing persisted Study Session flow and Browser Demo makes no Tauri, SQLite or network request. Final focused Home + Conversation tests passed 34/34, API-client tests passed 59/59, and the focused durable API test passed 1/1 while asserting that no `agent_runs` row was created. Final ESLint, strict TypeScript and `git diff --check` passed. Scoped Impeccable detection and Debug app bundling passed before the final nonvisual recovery repair and were not repeated afterward. The most recent complete desktop suite remains 326/347 because 21 pre-existing cross-page Learning Core integration assertions target superseded Feed/Knowledge/status UI outside this slice. That Debug app rendered Home only with the learning core unavailable, so healthy native create → stream → reload remains `implemented / unverified`; no provider answer or citation is claimed.

2026-07-21 core-loop acceptance note: the final cross-page UI pass made only minimal Conversation state-truthfulness repairs. Route changes now abort and discard the outgoing transient answer, citation/PDF, Inspector and recovery state before loading the incoming route's draft; render gating hides outgoing state before the reset effect commits, and a `new` handoff is consumed only after its draft is read. Unsupported completed answers explicitly state that there was not enough source support, without fake citations. The existing PDF modal is now the sole citation preview, and Retry / Ask again / Reuse question distinguish retry, new execution and composer reuse without implying persisted transcript replacement. Focused component evidence covers route switching, grounded-false completion, preview Escape focus restoration and cleanup; the final 10-file handoff suite passed 110 tests. Browser evidence at 1180×740 and 900×700 found one main, zero unnamed buttons and no document overflow; emulated reduced motion matched, and visually checked `06-conversation-demo-900x700-collapsed-disclosure-fixed.png` retains the compact global Demo disclosure after Sidebar collapse. The latest rebuilt Debug app launched but reached only Home's truthful local-core-unavailable state, so healthy normal UI remains unverified in this turn. No Conversation persistence, Python, SQLite, API/Zod, provider, RAG, FSRS, navigation, dependency or Figma change belongs to this acceptance pass.

2026-07-21 History + Review UI note: History is now a course-scoped Study Session return surface rather than an implied universal history. It sorts the existing at-most-50 response window by real `updated_at`, exposes one focusable row action with a status-specific learner label, renders English dates, and identifies terminal records without a false Continue action. Review keeps the existing due-read and rating-write handlers behind one prompt/optional recall/reveal/provenance/rating flow. It removes full-queue percentages, technical persistence labels and fake source viewing; unsupported expected answers fail closed. Unknown write outcomes conservatively refetch the authoritative queue and retain the exact submission identity for retry, while global shortcuts exclude interactive targets, modifiers and repeats. Browser/component evidence covers empty, loading/error, all History status actions, hidden/revealed/writing/success/conflict/unknown Review states, shortcut isolation and request-free Demo. The latest Debug app reached only truthful unavailable states, so populated History and due Review are implemented but unverified visually in the real app this turn. No Python, SQLite, API/Zod, FSRS, navigation, dependency or Figma change belongs to this slice.

Work order:

1. Reconcile primary navigation and page contracts with the capability map.
2. Implement the first end-to-end slice using existing contracts and truthful boundaries.
3. Complete the required empty, loading, error, cancellation, success, keyboard, compact-window, long-content, and reduced-motion states for that slice.
4. Apply the approved Keen visual system and authorized HyperKnow interaction patterns.
5. Run focused tests and capture only the screenshots needed to verify this slice.

2026-07-21 Knowledge Base + Source Scope UI note: the existing live course creation, document import, indexing poll/cancel/retry/reindex/delete, course link/unlink and search handlers remain unchanged behind a flatter source-management view. Course scopes precede one `Your sources` list; rows show filename/type, course, one real status and changed time, with live actions disclosed only after selection. Browser Demo remains request-free and presents seeded/chosen rows only as `Sample`, never as indexed or failed. Grid mode, repeated sample/index metadata, disabled provider placeholders and duplicate Demo explanations were removed. Browser evidence covers default, selected, geometry-matched loading, unavailable, 1180×740 and 900×700 with no document overflow; focused tests passed 16/16 and frontend lint/typecheck passed. The latest Debug `Keen Dev.app` reached only source unavailable because the bundled learning process exited unexpectedly, so a healthy live source list remains implemented but unverified visually in the real app this turn. Current Home/Conversation routes do not consume a source/course query handoff, so no fake Ask/Study CTA was added.

2026-07-21 Conversation UI note: the existing authenticated `answerStream` contract, course selector, stop/retry/edit handlers, structurally scoped citations and PDF viewer remain unchanged behind one editorial learning-record column. The page no longer exposes retrieval-mode badges, repeated Demo/runtime marketing, an assistant persona or a learner chat bubble. Empty/loading/source-missing/provider-missing/cancelled/error states stay next to the affected scope or action; real citations use the existing PDF viewer, while route change, cancellation and stream failure clear their local preview state. Browser Demo has one global disclosure, `/conversation/new` remains answer-free, and the explicit sample route labels its fixed answer as sample while making zero service requests. This paragraph records the earlier UI-only slice; its process-memory transcript boundary is superseded by the later migration `027` durable Conversation slice above. That earlier UI-only slice did not include Conversation in History; the persisted History slice above now supersedes that boundary. Browser/component evidence covers empty, loading, empty scope, request-free sample/long content, live streaming/cancel/error/citation behavior, 1180×740 and 900×700 without document overflow. The rebuilt Debug app reached only a real startup/recovery state, so a healthy real provider completion is unverified visually this turn. No provider, RAG, navigation, dependency or Figma change belongs to either slice.

2026-07-21 Learning Feed + Task Detail UI note: the existing master-detail route and handlers now present a flat 332 px queue rail plus primary month calendar, with compact status/course controls and one-status task rows. Task selection keeps that queue context and shows the stored goal, due/estimate/progress, expected steps and only the existing Demo completion or live Start/Resume action. No backend, API, SQLite, algorithm, route, calendar integration or dependency changed. Browser/component evidence covers the normal Feed, selected detail, restore geometry, 1180×740, 900×700 reflow and focus return; focused tests passed 33/33 and frontend lint/typecheck passed. The latest bundled Debug `Keen Dev.app` reached only the saved-task unavailable state, so normal Feed and Task Detail remain implemented but unverified in the real app for this turn.

Standalone audit infrastructure, additional packaged probes, broad baseline approval, integration previews, and repeated security/local-first messaging are paused unless they directly block this journey. The phase is not complete until the journey is clickable and its persisted resume state is verified; documentation, Figma frames, or screenshots alone do not complete it.

## Home task-first convergence (2026-07-21)

Status: **implemented / unverified for the real normal Dev.app state**.

Home now derives one truthful composition from the existing course and pending-task snapshot. When saved work exists, Today and the learning queue precede the secondary request workbench in both visual and DOM order. When the resolved queue is empty, or the learner explicitly opens Ask/Study/Review, the request workbench becomes the primary heading and the queue follows. Restore and unavailable states keep the same flat structure and limit recovery language to the affected queue action. Focused component/integration tests verify normal-task and empty ordering. The latest real Debug app rendered and was visually checked in restore and unavailable states at `artifacts/ui-audit/2026-07-21/home-task-first/`; its healthy normal state was not reproduced in this turn, so no live normal-state, compact-window, or reduced-motion acceptance is claimed. No backend, API, SQLite, navigation, dependency, or Figma change belongs to this slice.

## UI Foundation + Deep Learn pilot (2026-07-21)

Status: **verified for the scoped Shell and Deep Learn pilot; accepted visual baseline and packaged reduced-motion-on evidence remain open**.

The existing Shell, token and shared-control layers were reused rather than replaced. Sidebar selection is flat and compact, study icons use the same 16 px rhythm as primary navigation, Toolbar exposes only the current route, non-healthy local-core state when it affects the action, and contextual actions; the normal ready state remains once in the Sidebar. AppShell renders the Inspector only when its store contains a real selected source/citation/task. Recall, practice and summary protection now clears that context rather than inventing an Inspector message. Motion remains CSS/React-only: 150 ms ordinary controls, 190 ms menus/inline replacement and 300 ms Sidebar/coordinated panels share one easing, while the pre-existing `prefers-reduced-motion: reduce` rule removes effective animation and transition duration.

Deep Learn is the only fully migrated page in this slice. Ongoing sessions keep a 204 px source-grounded path rail and one centered 65–75ch editorial column; source material, definitions and task checkpoints use dividers or restrained flat fills instead of nested cards. Diagnostic, recall and practice reuse that shell and expose one primary action, with cancellation/retry/error copy remaining inline. Local-service and query restore render rail/content/bottom-action skeletons with the final geometry. Completed sessions retain the already-implemented single flat result column and never reintroduce a rail or Inspector.

The follow-up polish was verified in the same two persisted sessions: page headers retain the original session title and goal, rail Current/Next owns the phase label, task bodies no longer repeat phase badges or hidden/protected implementation copy, and the completed Review due time uses Keen's English document locale without seconds. Evidence is in `artifacts/ui-audit/2026-07-21/deep-learn-polish/`; the Figma frame remains Provisional.

The existing canonical Figma file `ugwiIPdF43v2woYsLM3b9R` was updated in place, not duplicated. Frame `65:2` is named `Shell + Deep Learn · In Review / Provisional · 1180×740`, uses the existing Keen variables and SF Pro styles, removes the old illustrative mastery aside, and remains Provisional rather than Approved.

Live evidence came from the rebuilt unsigned Debug `Keen Dev.app` and its bundled authenticated sidecar. A new local session `autonomous-session-7ebd97b7-7f59-5d52-aff6-0c8dcb6025ca` advanced through diagnostic to persisted reading and pending active recall, survived a full app/sidecar restart, and resumed from History with the prompt intact. The earlier completed session `autonomous-session-d626a3fe-7ec2-593f-9437-dab80e1902be` still restored as the flat completed result. Final acceptance screenshots cover cold app restore, pending active recall and completed; a real reading capture from the immediately preceding build is retained as iteration evidence but predates the final header-selector and flat-label micro-fix. A separate wide-window real document selection verified Inspector present; pending active recall verified Inspector and its Toolbar toggle absent. Native Tab traversal reached Open Review, Learning Feed and the Shell navigation in order, and the focus ring was visibly present. The Tauri minimum remains 1180×740; the capture service produced 1192×768 images for the minimum-window evidence and 1228×768 for the fullscreen Inspector state, so exact CSS dimensions are not inferred from those files. A separate current-code browser reflow check at 820×700 reported no horizontal overflow, a 60 px collapsed Sidebar, 184 px rail and 576 px content region; it is CSS/component evidence only, not a native-window claim.

Verification evidence: desktop ESLint and strict TypeScript passed; the focused Deep Learn/AppShell set passed 6 files / 58 tests; the complete desktop suite passed 29 files / 317 tests; the unsigned Debug `.app` bundle completed with the existing Vite chunk-size warning; `git diff --check` passed; and scoped Impeccable detection returned `[]`. The stored motion rule and an earlier packaged probe confirm the current system reports `reduced=false`; this run did not change macOS settings, so a packaged `reduced=true` state is not claimed. HyperKnow comparisons were qualitative and the Figma frame is Provisional, so no mismatch percentage, accepted visual-regression result or pixel-parity claim is made.

## Product slice — source-scoped guided study and History resume (2026-07-21)

Status: **verified for the local provider-independent Study Session loop**.

Home now reuses the existing authenticated autonomous-recommendation and persisted Study Session contracts when the learner selects **Start focused study**: the learner chooses a course source scope, enters a goal, receives the existing source-grounded path, and is routed to the existing Deep Learn session. The goal is trimmed and persisted only on first creation; a resume request preserves the original session goal. The existing Deep Learn diagnostic, reading, active-recall/practice and summary steps remain the guided-study portion of the flow, and Learning Feed remains an existing persisted task/session resume surface.

History now adds the missing learner-visible return point without introducing a second session model: `GET /v1/study-sessions?course_id=…` projects the latest existing SQLite sessions, the React page supplies course scope plus loading/empty/error/offline/Demo states, and Continue/View record returns to the existing course-scoped Deep Learn route. Browser Demo performs no History request and does not invent prior work.

The first real Tauri/SQLite run exposed one contract gap: the recommendation coordinator may truthfully return `covered_by_active_task` for an existing manual/local task, while the Study Session service previously accepted only autonomous-provenance tasks. Home therefore reached a 200 blocked response instead of Deep Learn. The session service now treats a validated non-empty learner goal as explicit user initiation and may reuse that actionable same-course task; an autonomous start without a learner goal still fails closed with `task_not_autonomous`. Course, task status, concept, indexed-source and terminal-session checks remain unchanged.

Live evidence used an unsigned local `Keen Dev.app`, the isolated `com.keen.learning.dev` Application Support database, the existing Calculus I course/task, and one clearly local indexed test note. The run created `autonomous-session-d626a3fe-7ec2-593f-9437-dab80e1902be`, completed the non-scored diagnostic, read a persisted source chunk, recorded one correct active-recall observation, showed the same titled session in History, exited the application cleanly, restarted the sidecar against the same SQLite database, and resumed from History with status `practicing`, the recall result preserved, and Begin practice as the next action. Provider output was neither configured nor required.

Verification evidence: desktop ESLint and strict TypeScript passed; the complete desktop suite passed 29 files / 316 tests; 87 related autonomous-session, diagnostic, active-recall, practice and summary Python tests passed with one existing Starlette/httpx deprecation warning; targeted Ruff lint and format checks passed; and the unsigned Debug `.app` build completed with the existing Vite chunk-size warning. Earlier Browser checks at 1180×740 and 820×700 remain the scoped History responsive evidence; this backend repair did not change UI layout. No provider, signed/notarized package, Conversation persistence, accepted visual baseline, pixel parity or complete accessibility audit is claimed.

## Product slice — practice completion and Review handoff (2026-07-21)

Status: **verified for the same local provider-independent Study Session and one persisted FSRS rating**.

The existing targeted-practice, summary-review, Review repository/router/service, FSRS scheduler, History, Review and Learning Feed surfaces were reused; no second practice, task or review model was introduced. The same session `autonomous-session-d626a3fe-7ec2-593f-9437-dab80e1902be` resumed at `practicing`, generated a deterministic fill-in prompt from the persisted Chain rule source, accepted `composition`, recorded a correct 1/1 practice observation, and finalized through the existing summary transaction. SQLite then held session `completed` at revision 10 and progress 1.0, an answered practice run linked to its attempt/evaluation/mastery evidence/event, a summary handoff linked to the same run and one Review item, and the originating task marked completed.

The new due Review appeared on `/review` with the persisted prompt, expected answer, course and concept. Revealing it and rating `good` with recall text `composition` created exactly one Review attempt and advanced the existing FSRS schedule to `learning`, revision 1, repetitions 1 and lapses 0. Its next due time moved beyond the current queue, so Review truthfully became empty and Learning Feed truthfully showed no active or currently eligible local action. After quitting the complete app and sidecar, rebuilding the unsigned Debug `Keen Dev.app`, and reopening against the same `com.keen.learning.dev` database, History returned the session as a completed record, Summary restored the original review handoff, Review restored the post-rating empty queue, and the SQLite identities/revisions remained unchanged.

The live run exposed two user-visible handoff defects rather than a backend break: Summary had no next-action control, and a completed one-unit focused session displayed `100% session progress` beside an unexplained `50% units complete` because one further planned unit remained outside that slice's single-unit finalization. The UI stated `1 of 2 planned units completed · focused session closed`, retained 100% as the completed session lifecycle, described the handoff as a review created for its original time instead of presenting that frozen snapshot as the current schedule, provided real Review due and Learning Feed actions, and cleared the protected Summary Inspector on exit. That historical one-unit closure is superseded by the multi-unit progression slice below.

Verification evidence: desktop ESLint and strict TypeScript passed; focused Summary/Deep Learn component validation passed 25/25; the complete desktop suite passed 29 files / 316 tests; 23 targeted practice, summary and Review Python tests passed with one existing Starlette/httpx deprecation warning; the Debug `.app` build passed with the existing Vite chunk-size warning; `git diff --check` passed; and the scoped Impeccable detector returned no findings. The rebuilt Dev.app was operated directly for the restart checks, but no fixed-viewport artifact, accepted visual reference, visual diff, signed/notarized package or complete keyboard/accessibility audit was produced.

## Product slice — persisted multi-unit Study Session progression (2026-07-22)

Status: **verified at the Python domain/API and strict desktop component/client boundaries; packaged WebView operation remains unverified for this slice**.

The existing practice answer is now the durable unit boundary. When the current active unit has exactly one contiguous locked successor, the same transaction seals the deterministic practice attempt/evaluation/mastery evidence, completes the old unit, activates the successor, updates `current_unit_id` plus fractional progress, and moves the existing session from `practicing` back to `studying`. It does not create a Review or summary handoff and does not complete the originating task. When no successor exists, and only then, practice enters `summarizing`; the existing Summary transaction creates one FSRS handoff and completes the final unit, task, and session. No migration, endpoint, navigation item, secondary task model, or second review model was added.

Active Recall and Practice restore the run belonging to the authoritative current unit; terminal restore selects the final unit's run, while exact old-key replay remains safe and returns the current authoritative session without duplicating attempts, mastery events, reviews, or task writes. Contiguous ordinals, one active unit, locked successor state, revision CAS, and transaction rollback are enforced fail-closed. A real two-unit service test follows Unit 1 recall/practice into persisted Unit 2, repeats recall/practice there, and only then finalizes Summary and Review.

Deep Learn reuses the approved path rail and reading/checkpoint components. The server pointer is the only current unit; completed or skipped units are read-only, ready/locked units are disabled and cannot reveal source content, and a missing/forged pointer or multiple active units renders the existing plan-unavailable recovery instead of guessing. Recall and practice scope includes the current unit so late Unit 1 responses cannot affect Unit 2. An intermediate answer remains visible as `Unit complete` until the learner chooses `Continue to next unit`; reload goes directly to the persisted successor. Final Summary/Review remains exclusive to the last unit.

Evidence: the independent backend mechanical matrix passed 147/147 with the one existing Starlette/httpx deprecation warning; Ruff check and format passed for the current Python tree. The final combined rerun passed 48/48 focused Python tests and 6 desktop files / 112 tests, plus strict TypeScript; scoped `git diff --check` passed. Sol-high read-only acceptance found no P0/P1 and two P2 guards: replay responses did not reject multiple active units, and paused Summary used a generic conflict despite safely rejecting before writes. Both were repaired; the focused final reruns passed 2 desktop files / 7 tests with strict TypeScript and 6/6 Python Summary tests, with no new warning. The final Sol-high re-check confirmed P0/P1/P2 = 0 and made no edits. No packaged Tauri WebView run, native screenshot, accepted reference, visual diff, Provider call, signed/notarized artifact, or complete accessibility audit is claimed for this slice.

## Execution and independent-acceptance constraints

For bounded implementation work, a cost-efficient lower-reasoning execution pass may implement, run commands, collect artifacts, and repair directly reproducible defects. A separate higher-reasoning acceptance pass is mandatory before handoff when the task explicitly requires it or changes truthfulness, persistence, security, packaging, visual acceptance, or user-visible state boundaries.

- The execution handoff must name exact files, commands and exit results; each capture must record its real dimensions, fixture/state, motion setting, and reference/Figma status. Unmeasured values are `unverified`, never inferred from a filename or expected window setting.
- The acceptance pass is read-only by default. It must independently inspect the diff, artifacts and report counts; identify unsupported claims and residual gaps; and return actionable findings by severity.
- The execution pass must repair every accepted finding, re-run the smallest relevant checks, and obtain a final acceptance re-check. It may not claim the acceptance result before that re-check.
- Parallel agents may not edit overlapping files or treat another agent's summary as proof. Evidence created by a prior run must be checked for current timestamps/content before being cited.
- Expensive full suites, packaging, visual capture and high-reasoning review run once per coherent change unless a repair affects their result. Focused checks are preferred for documentation-only or localized UI repairs.

## UI framework direction freeze (2026-07-21)

Status: **verified for the browser UI scope and a bounded packaged-WebView smoke; Home and Learning Feed have a narrowly scoped Keen-owned regression baseline**. `docs/DESIGN_DIRECTION.md` now fixes Keen's task/source/progress workspace direction, decision hierarchy, stable navigation and page structures, and the bounded HyperKnow adoption matrix. In Figma file `ugwiIPdF43v2woYsLM3b9R`, Home and Learning Feed are the only current `Approved` product pages; implementation snapshots are `Provisional` and HyperKnow studies are `Reference`. The Approved Home text nodes were synchronized to the verified Browser Demo disclosure instead of implying working retrieval.

The runtime audit covered Home, Learning Feed, Knowledge Base and Conversation at 1440×920, 1180×740 and 900×700 where applicable. It found and fixed one recoverability defect: a manually collapsed wide-window Sidebar had no visible expand action. The control now switches between accessible `Collapse sidebar` and `Expand sidebar` states, with a component regression. The inspected routes had no document-level horizontal overflow; the Feed preserves task/calendar columns at supported desktop widths and intentionally removes the calendar at 900 px; Knowledge Base changes from table to list; Conversation uses a bounded reading measure and an independently scrollable transcript. Emulated reduced motion produced 0.00001 s animation/transition durations and `scroll-behavior: auto`. A visible focus-ring capture and DOM focus-order audit supplement component keyboard tests; direct browser Tab injection remains unreliable and is not claimed as a complete keyboard audit.

Evidence: `artifacts/ui-audit/2026-07-21/ui-framework-closeout/`, the Approved Figma nodes `113:3` and `162:97`, desktop ESLint, strict typecheck, production build, 28 test files / 313 tests, `git diff --check`, and the Impeccable detector. A fresh local ad-hoc packaged app was also opened: Home, Feed, Knowledge Base, empty Conversation and no-course Study entry rendered with the authenticated local sidecar ready; keyboard focus reached Review due; and Sidebar collapse/re-expand recovered through the labelled control. Terminating its current sidecar child caused the supervisor to start a replacement and the UI returned to ready; the transient unavailable UI was not captured. Those original screenshots are 1203×768 px and did not themselves measure their CSS viewport. A subsequent independent ad-hoc `com.keen.learning.ui-audit` bundle used a build-time-only visible probe to measure packaged WKWebView `inner`, root-client and `visualViewport` dimensions: all three were 1440×920 CSS px at launch and 1180×740 after native edge resizing to the configured minimum, with DPR 2; a further shrink attempt remained at 1180×740. Its current packaged media query was `reduced=false`. The System Settings control channel closed before that preference could be read or changed, so packaged `reduced=true` remains unverified and no system setting was modified. Packaged long-learning-content and transient unavailable UI states are also unverified. To avoid same-name activation of a separately installed old app, the audit bundle is launched only through the verified repository-local `scripts/open-ui-audit-app.sh`; native menu text derives from the active config product name, and Rust tests lock production, development and audit identities as distinct. Production `Keen` / `com.keen.learning` is unchanged. Captures and their fixture/motion/Figma-node limitations are in `artifacts/ui-audit/2026-07-21/packaged-webview/`; bundled-sidecar smoke passed. The deterministic visual report now records 2 strict-0% accepted Keen baseline passes (Home and Learning Feed Browser Demo, 1180×740 CSS px, DPR 1 and reduced motion), 16 `missing_reference`, and eight `provisional` Figma comparisons. The two fixtures made no application fetch/XHR, Tauri, learning-core or provider request; their hashes and fresh Figma nodes Home `155:187` / Feed `164:179` are recorded in `references/visual-baselines/README.md`. This is future-change detection, not pixel parity or a complete visual-regression pass; every other page/state stays missing or provisional.

## Scoped UI-boundary refinement (2026-07-21)

Status: **verified for the browser UI scope**. Learner Memory is now a non-simulated capability boundary; `/conversation/new` opens without the fixed Demo answer; the Inspector has no fallback mastery/source/insight content; and provider plus external integrations share one read-only Capabilities section. Evidence: `artifacts/ui-audit/2026-07-21/icon-reduction/`, the scoped entry in `design-qa.md`, desktop ESLint, strict typecheck, production build, 28 test files / 312 tests, and the Impeccable detector. The visual harness now has two accepted Home/Feed browser baselines, while 16 routes still report `missing_reference` and eight Figma comparisons remain provisional. Packaged Tauri rendering, additional page/state baselines and complete keyboard/accessibility coverage remain open.

## First-round status (2026-07-15)

| Work item requested for the first round | Status at initial audit | Evidence / blocker |
| --- | --- | --- |
| Audit repository | Verified | `docs/REPOSITORY_AUDIT.md`; initial repository contained only `.git`. |
| List present/missing references and pages | Verified | Audit page matrix and `docs/VISUAL_TODO.md`; all expected references were missing. |
| Create open-source reuse matrix | Verified | `docs/OPEN_SOURCE_INVENTORY.md`; candidates only, no license assumptions. |
| Identify DeepTutor/OATutor adaptation candidates | Verified as read-only audit | Exact parent revisions and root licenses were verified in temporary `/tmp` checkouts; nothing was copied or introduced. Module-level decisions are in `docs/OPEN_SOURCE_INVENTORY.md`. |
| Create implementation plan | Verified | This document. |
| Establish Tauri + React project | Verified for first-round shell | Frontend lint/typecheck/build/tests pass; Rust fmt/clippy/tests pass; actual arm64 `.app` and `.dmg` development bundles were generated and inspected. The Python service is not packaged into them yet. |
| Implement main window, Sidebar, Toolbar, Home | Verified as provisional demo UI | Functional routes and interactions pass 5 Vitest tests; the 1440×920 Home current screenshot exists. HyperKnow visual parity remains unverified because references are absent. |
| Establish first visual regression screenshots | Harness/current capture verified; comparison blocked | `tools/visual-regression` created `artifacts/visual-diff/current/home.png` and a report with `missing_reference`. No mismatch percentage or pass is claimed. |
| Show modified files and test results | Verified for first round | Exact validation evidence is recorded in the update log below. |

## Product slices

Each milestone must produce a vertically testable increment. Do not mark a milestone complete because files exist.

### Milestone 0 — audit and governance

Status: **in progress**. Audit, upstream review, and first dependency scans are recorded; complete shipped-license notice reconciliation remains open.

- Repository/reference audit and explicit evidence gaps.
- Legal/provenance rules and third-party tracking templates.
- Page inventory and visual-reference intake list.
- Architecture, security, permission, persistence, and truthfulness guardrails.
- Exit gate: governance docs reviewed, manifests inventoried, dependency/license scan recorded, and unresolved reference authorization carried as a named blocker.

### Milestone 1 — secure desktop shell

Status: **in progress**. The shell builds, the selected-file document path is connected, and learning-core supervision is implemented. Automated window/restart lifecycle E2E, native file-dialog/drop coverage, and complete state/error coverage remain open.

- Tauri 2 desktop workspace, React/Vite strict TypeScript, routing, query/state layers.
- macOS window: 1440×920 default, 1180×740 minimum, Retina/fullscreen, system traffic lights, integrated titlebar, persisted window state.
- Sidebar, Toolbar, collapsible Inspector, keyboard focus, reduced motion, core shortcuts.
- Provisional design tokens clearly labeled as unmeasured.
- Deterministic browser Demo Mode with no learning-core or provider traffic; Tauri mode may use only the authenticated loopback service until providers are explicitly added.
- Security foundation: minimal capabilities, controlled paths, secret-storage boundary.
- Exit gate: dev launch; lint/typecheck/unit tests; Rust tests; window-state restart test; no false enabled controls.

Historical first-round note: before the initial push, `origin` exposed no branch refs and the first arm64 development bundles omitted the Python sidecar. Commit `2a68a51` is now present on `origin/main`. A later arm64 `.app` and `.dmg` embed the supervised learning-core binary; that does not retroactively change the first-round bundle evidence.

### Milestone 2 — static product surfaces and visual harness

Status: **in progress; visual comparison blocked by dimension-aligned baselines**. All named routes have deterministic demo surfaces. Three authorized HyperKnow references now cover Home composer, Learning Feed/calendar and the Deep Learn composer-entry state, and Keen has an implementation pass aligned to their visible structure without shipping reference assets or branded content. The harness captures all three Keen states at 1440×920 and truthfully reports `missing_reference` because no accepted dimension-aligned Keen baseline exists.

- Home, Learning Feed, Knowledge Base, Conversation, Deep Learn, Quiz, and Settings.
- Deliberate loading, empty, partial, error, offline, cancelled, provider, sidecar, and indexing/migration states.
- `tools/visual-regression` manifest, deterministic seed, animation/time controls, capture/current/diff outputs.
- User-supplied raster mark and wordmark are available as transparent light/reverse SVG browser assets and are used by the Sidebar and browser favicon. The user-selected flat mark was redrawn as a clean three-path SVG and now also drives the generated Tauri platform icon set from `apps/desktop/src-tauri/icons/icon.svg`; it remains an implementation asset rather than an original vector master.
- Implement remaining Flashcards, Planner, Memory, and Visualize static states early enough to keep shared contracts coherent.
- Exit gate: routes and state fixtures covered by component/E2E checks. Pixel threshold applies only after valid references arrive; no parity claim before then.

### Milestone 3 — local data and recovery

Status: **in progress**. Versioned SQLite migrations now cover courses/concepts/mastery/tasks plus documents, versions, chunks, status events, an external-content FTS5 index and the first durable Conversation ask/restore slice. A process-lifetime advisory lock serializes migration/recovery/temporary-upload ownership across processes. The live frontend can create a real local course, select it for an import, read tasks/mastery/documents while uploading/searching supported files, and restore an authenticated persisted Conversation transcript by id. Durable Agent run/audit state, Conversation terminal state and startup terminal recovery are implemented, while concept creation and a healthy real Dev.app Conversation persistence/restart E2E remain open.

- SQLite + FTS5, versioned migrations, repositories, seed importer, data-directory policy.
- Domain entities named in the product brief, including Agent run/step/tool/approval records.
- Conversation draft, session, index task, learner state, and window/sidebar persistence.
- Exit gate: migration forward tests, repository tests, deterministic seed reset for tests, restart/recovery E2E without deleting the database.

### Milestone 4 — document ingestion, retrieval, and citations

Status: **in progress**. PDF/Markdown/TXT import is bounded and durable jobs provide real progress, cancellation, retry and restart recovery. Latin/CJK FTS plus optional loopback-only local embeddings and sqlite-vec provide truthful lexical-only or hybrid retrieval with model/version/dimension isolation, RRF, course filtering, deduplication and bounded adjacent merging. Model changes create an embedding-only reindex that preserves the live lexical index until atomic vector promotion.

- Controlled import for PDF/Markdown/TXT/image; MIME/hash checks; parser and OCR fallback.
- Page/section-aware chunks with text location, parser/embedding versions, and content hashes.
- FTS + validated vector backend, metadata filters, RRF, dedupe, rerank, citation validation.
- Virtualized PDF viewer; citation opens exact page and highlights the source chunk.
- Exit gate: ingestion/index cancellation and retry tests; retrieval/citation contract tests; large-document UI does not render all pages.

Current boundary: image import and OCR are not implemented; textless PDFs fail explicitly. Hybrid retrieval, loopback-only chat-model answer streaming, sqlite-vec, PDF geometry/content, and mounted-DMG execution are verified for CPython 3.11/macOS arm64. Generated citations are structurally mapped to a single current database chunk; factual-entailment validation and reranking are not implemented. PDF.js renders only the cited page and highlights validated geometry for ordinary zero-origin, unrotated, unit-scale MediaBox/CropBox pages; rotation, translated boxes, custom user units, CropBox differences, and absent layout explicitly use page-only fallback. `/v1/query` stays deterministic passage extraction; `/v1/answer/stream` is the generated-answer surface.

### Milestone 5 — authenticated learning-core sidecar and Agent runtime

Status: **in progress**. The loopback FastAPI service, pre-body all-route Bearer authentication, bounded imports, health, SQLite/BKT/document slices, recovery, offline/no-citation SSE endpoint, authenticated durable Agent run API, visible Home Agent Activity/Undo runtime, provider-private multi-turn tool feedback, safe recoverable Level 1 read-error feedback, and configured loopback Ollama/OpenAI-compatible Agent provider are verified. When a run has persisted course scope, the provider may select three host-scoped Level 1 reads: Study Feed, due Review, and indexed course-knowledge lexical search. It may also propose the exact `complete_study_task` Level 2 action using task ID and expected revision only; the host binds course/time, pauses the run, displays a safe approval summary, and executes the reversible mutation atomically only after confirmation. Direct model execution, other Level 2 tools, and all Level 3 tools remain denied. A Unix-only real-Uvicorn/socket test also verifies partial Agent SSE, process-group SIGKILL, same-database/new-token restart, old-token rejection, deterministic interrupted recovery and Last-Event-ID replay. The Python child owns a port-0 `127.0.0.1` bind and announces it through the trusted child pipe; Rust writes a 256-bit token once through stdin, isolates the sidecar in its own process group, performs authenticated readiness and continuing liveness probes, permits one bounded restart, and performs bounded whole-group shutdown. Each generation uses a confined 0700 extraction directory that is cleaned only after the group exits or reclaimed after a prior supervisor crash. Rust policy/path/token/process tests, an automated final-DMG auth/PDF/resource/token-leak smoke, and manual mounted-app launch/crash/quit tests exist; broader approval domains, automated Tauri/GUI relaunch E2E, hybrid Agent retrieval, and the wider learning workflow remain open.

- Python 3.11+ sidecar, PyInstaller-equivalent packaging, loopback-only random port.
- Rust-generated ≥128-bit session token; every sidecar request authenticated.
- Health, crash restart, graceful shutdown, log rotation, SSE or WebSocket streaming, cancellation.
- One orchestrator with the specified tool registry; structured run/step/tool/state/citation logs.
- Level 1/2/3 permission and approval flow; prompt-injection boundary for documents.
- Provider adapters with secret-safe UI/storage and explicit missing/rate-limit states.
- Exit gate: API contract, lifecycle, auth rejection, crash recovery, cancellation, approval, and log-redaction tests.

### Milestone 6 — learning engine

Status: **in progress**. Deterministic BKT code and persisted Deep Learn diagnostics, active recall, targeted practice, summary-to-FSRS handoff, and the first authenticated due-Review/rating path now run through the strict desktop client. After an incorrect Recall, the first bounded Agent intervention can create a validated, source-grounded explanation and hand off to the existing independent Practice flow; eligibility, source scope, practice creation, mastery and scheduling remain deterministic. Review ratings are revision-checked and idempotent, persist an optional recall response, and update only FSRS state—not mastery. Generated-card editing/deletion, broader assessment item types, planner, and memory integration remain open.

- Structured Deep Learn sessions, diagnostics, concept map, checkpoints, active recall, practice, summary, resume.
- Quiz item types, layered hints/scaffolds, deterministic grading evidence, error review.
- Deterministic BKT-style mastery service; LLM may explain but not choose arbitrary mastery values.
- FSRS-backed flashcards maintained separately from concept mastery.
- Explainable proactive feed and planner with rescheduling; calendar proposals require confirmation.
- Editable, evidenced learner memory and persona.
- Exit gate: BKT/FSRS fixtures, hint-weight tests, planner/restart E2E, and auditability of every mastery mutation.

Review slice evidence, 2026-07-20: `GET /v1/reviews/due` and `POST /v1/reviews/{item_id}/attempts` expose the existing SQLite/FSRS repository through authenticated, strict Pydantic and Zod contracts. The desktop `/review` route replaces sample cards with real due, reveal, rating, empty and recovery states and remains request-free in Browser Demo. Review writes are now connection-generation isolated: credential rotation aborts the old write and it cannot paint a false success into the new queue. Recreating FastAPI against the same SQLite file preserves the rated item's FSRS due time, revision and single attempt; the existing Rust supervisor suite separately verifies token rotation and generation-isolated lifecycle state. A new packaging-gate smoke launches the frozen sidecar for three real generations against one database and verifies old-token rejection, due read, one FSRS rating, post-restart recovery, same-key replay and one persisted attempt. It passed against both the build-tree app and the final mounted DMG. The ad-hoc arm64 DMG is 34,084,916 bytes, SHA-256 `01c4310ebdef3ea7ed9cb90b71bda1bbc0965ac44f929adf2afb531753642769`; checksum, strict deep signature, architecture, embedded notices and mounted-service smoke passed. It is not notarized or Developer ID signed. The full Python suite passed 1021/1021; Ruff check/format check passed. The complete desktop suite passed 309/309; ESLint, strict typecheck and production build passed. Rust tests passed 38/38. Browser checks at 1280×800, 760×700, 1440×900 and 980×700 found no horizontal overflow or unnamed controls, and reduced-motion emulation disabled the loading animation. A bounded isolated-release WebView run exercised due, restart, recovery, rating, app restart and post-restart empty states; screenshots are under `artifacts/ui-audit/2026-07-20/packaged-review/`. The visual harness produced current Review captures with missing references. The packaged evidence ledger is [`artifacts/package/2026-07-20-review-restart/README.md`](../artifacts/package/2026-07-20-review-restart/README.md). Automated `.app` GUI interaction, accepted visual baselines, broader accessibility automation, generated-card editing/deletion and course filtering remain open; this is not the full Flashcards milestone exit.

### Milestone 7 — macOS integration

Status: **in progress**. Native macOS menu items, shortcut event bridge, titlebar/window configuration, icon set, window-state plugin, Application Support database path, sidecar exit handling, and the first origin-bound macOS Keychain provider-secret path are present. Notifications, calendar, native file-dialog/drop completion, real packaged Keychain/restart verification, and permission-denial tests remain open.

- Native menu, shortcuts, notifications, file dialogs/drop, Keychain/Stronghold, calendar confirmation.
- Sidecar termination on exit, app support/cache paths, entitlements and least privilege.
- Exit gate: permission-denial states, shortcut/menu tests where practical, calendar preflight/confirmation test, signed-or-explicitly-unsigned `.app` build evidence.

### Milestone 8 — release quality

Status: **in progress**. Lint/typecheck/unit/build/Rust/Python checks, first visual capture, dependency scans, an arm64 sidecar executable, and arm64 `.app`/`.dmg` artifacts containing that sidecar exist. The packaging path installs a hashed CPython 3.11/macOS arm64 runtime lock in an isolated freeze environment and rejects a bundled sidecar that cannot start or pass the expanded authenticated smoke. The DMG checksum and mounted app's strict deep ad-hoc signature verify. Automated GUI lifecycle/provider E2E, performance, universal/Intel builds and locks, Developer ID hardened-runtime signing/notarization, complete notices, and authorized visual comparison remain open.

- Visual regression on authorized references, accessibility, performance and large-data tests.
- Complete dependency/license inventory, notices, upstream patch ledger, vulnerability review.
- Reproducible `.app` and `.dmg`; build/run/package docs.
- Exit gate: all acceptance conditions mapped to real artifacts; no known high-severity security issue; no false completion states.

### Milestone 9 — recoverable learning loop

Status: **in progress** on `codex/milestone-learning-loop`. The branch starts from `094c44eb1eaa7ae77c45fd5c07d651587b968fc0`; the pre-implementation baseline passed frontend lint/strict typecheck and 108 Vitest tests, 284 Python tests with one existing Starlette deprecation warning, and 38 Rust tests. This baseline does not verify any new learning-loop behavior.

- Implementation control document: `docs/LEARNING_LOOP_IMPLEMENTATION_PLAN.md`.
- Persist Conversation, Agent run/tool/mutation audit, Deep Learn sessions/plans/events, assessments/hints/evaluations, mastery evidence, misconceptions, Review/FSRS state and explainable Study Tasks.
- Keep one Agent orchestrator over typed tools and deterministic learning services. The model must not choose mastery values, final normalized scores, misconception confirmation, review dates, Feed priority or arbitrary database mutations.
- Connect Conversation, Deep Learn, Quiz, Flashcards and Learning Feed to authenticated local state with cancellation, Undo where applicable, restart recovery and truthful failure/provider states.
- Exit gate: the real 18-step imported-PDF learning loop, restart recovery, frontend/Python/Rust checks, arm64 `.app`/`.dmg` mounted smoke and dependency/license evidence all pass and are linked. Static Demo state, seed data or schema existence does not satisfy the gate.

## Cross-milestone acceptance evidence

| Claim | Minimum evidence |
| --- | --- |
| “Runs” | Exact command, environment, successful launch, date |
| “Tested” | Exact command and pass/fail/skip totals |
| “Persists” | Restart E2E covering the named state |
| “Secure sidecar” | Bind-address, token, path, capability, redaction, crash/shutdown tests |
| “Pixel matched” | Authorized reference ID, viewport, seed, current/diff images, mismatch percentage `<3%` |
| “Supports 1000-page PDF” | Fixture and measured memory/interaction result, not a loading mock |
| “Packaged” | Actual `.app`/`.dmg` paths and build output |
| “License compliant” | Lockfile-based scan plus verified upstream revisions/notices |

## Required end-to-end spine

Build toward one recoverable E2E path: create course → import PDF → observe real index progress → ask → open page citation/highlight → generate quiz → answer → deterministic mastery update → create review task → restart → verify all state restored.

## Update log

- 2026-07-25: Verified the bounded positive Agent intervention against the real loopback LiteLLM `openai-compatible` DeepSeek `deepseek-v4-flash` provider. One incorrect Recall led to a strictly schema/source-handle-validated artifact, visible Agent explanation/source and pending independently scored Practice; Toolbar/Activity showed completed, then a full app/sidecar quit-restart restored the same artifact and Practice in History. Read-only SQLite confirms five total runs (four retained development failures), successful `run-09c9d2d2a4b843ba91eeb26d03ca4b66` with one checkpoint plus one done, and sole pending `practice-run:c53a6d38-ad61-5192-a893-4af24b02ec0b`; counts did not change across restart (tasks 2, mastery events 3, state mutations 0, tool invocations 1). Legacy raw checkpoints normalize on read only, with no SQLite rewrite. Focused backend selected tests: latest 7 files all passed, including checkpoint review 63/63; frontend 6 files / 117 tests; full `npm run check` exit 0: frontend 43 files / 503 tests, Python 1127, Rust 49, lint/typecheck pass. Gateway credentials remain plaintext mode `0600`, not Keychain-backed, and local loopback gateway authentication remains a limitation. No vector, efficacy, visual parity, notarization, or new packaging claim is made.

- 2026-07-24: Implemented the first bounded Agent-native bridge while keeping the release information architecture unchanged. The Keen shell now uses the canonical mark/wordmark, a compact Sidebar and one on-demand Activity / Sources / Outline context drawer; the drawer renders the existing durable public Agent events and never becomes Deep Learn's default third column. The latest-activity endpoint and client restore one exact Conversation or Study Session run with fail-closed snapshot/SSE/mutation reconciliation. The post-Recall slice is now connected end to end: deterministic eligibility freezes the current incorrect attempt and source handles; a versioned, source-grounded Agent playbook publishes only a validated durable artifact; the learner can ask for a different explanation, a source example, or immediate Practice; and the existing adaptive/Practice services own the resulting write. Deep Learn exposes the intervention only for the matching current unit, locks direct Practice until the verified handoff, renders model text as inert plain text, and preserves source review on cancellation, provider failure, unavailable evidence, or unverified state. Eligible learners can select the persisted source-review path without a Provider call; a ready explanation leaves Practice as the only primary action; StrictMode no longer strands Agent restore or source-review completion. The earlier Activity review closed at **P0 = 0, P1 = 0**. DeepTutor, OATutor and OpenTutor remain structural references only; no external runtime, UI, prompts, or assets were incorporated. The current combined learning/Provider Python regression passed **219/219**, the combined desktop product regression passed **127/127**, and the API-client intervention regression passed **4/4**. Strict TypeScript, scoped ESLint, Ruff, Rustfmt and the production Vite build pass; the build retains its existing large-chunk warning. Rust compilation/tests, live persisted intervention capture, real Provider connectivity/Keychain use and packaged Tauri checks remain unverified, so this establishes no visual parity, packaged artifact, provider-quality or learning-efficacy claim.
- 2026-07-24: Continued the smallest coherent guided-learning journey rather than widening the product. A focused-study request still creates the existing task/session/plan atomically, but Deep Learn now presents that validated persisted route before the opening reflection: unit order, objective, per-unit/total minutes and unique source-chunk count are visible while unit body, chunk identities and navigation remain locked. The same slice closes three truthfulness gaps. Autonomous learning no longer falls back to arbitrary same-course chunks for a weak concept, so unrelated Recall cannot update that concept's mastery. Focused Study reuses the production deterministic generators to require two exact units that can each produce Recall plus a distinct Practice before any concept/task/session/plan is written; the dead-end `Alpha` / `Alpha` case blocks without pending adaptive state. Home binds a due Review to a Feed task only when course, review item, concept and review provenance match uniquely, then reuses the existing task-aware Review contract so completion returns under Completed; ambiguous evidence opens the unbound queue. This adds no navigation, migration, Provider request or alternate learning model. Verification passed Python **219/219**, desktop **127/127**, API client **4/4**, strict TypeScript, scoped ESLint, Ruff check/format and the production Vite build. Browser Demo captures exist for the current Home/Deep Learn shell, but the persisted path, Agent transient states and packaged WebView remain visually unverified.
- 2026-07-23: Added the directional Agent-native learner research brief and used it to tighten the planned product contract. The qualitative scan covers public study, spaced-repetition and PKM discussions plus current tutoring and human–AI research; it is explicitly not representative user research or learning-efficacy evidence. The resulting decision keeps the first implementation as one source-scoped post-Recall intervention, adds a specific mixed-initiative `why now / source scope / then` UI contract and capability-bounded citation inspection with partial/unsupported states visible, retains learner activation for the initial rollout, and rejects bulk generation, hidden review debt, transcript Memory, generic Agent chrome and model-authored learning state. No runtime, migration, endpoint, provider call, UI state, test result or learning outcome changed.
- 2026-07-22: Completed the bounded Study Session pause/resume product slice on the existing Deep Learn surface. Two authenticated course-scoped commands apply revision-CAS and durable event-ledger idempotency without a schema migration; replay returns current authoritative state, restart preserves the exact `resume_from_status`, and pause/resume performs no mastery, Review or attempt write. Deep Learn replaces phase guessing with that persisted state, adds one header action, keeps paused work read-only, safely retries an unknown outcome with the same key, refreshes on conflict and leaves terminal sessions without a control. Plan-unavailable and pre-unit paused states remain recoverable rather than trapping the learner. Full verification passed: ESLint, strict TypeScript, Ruff check/format, `git diff --check`, desktop 389/389, Python 1045/1045 and production Vite build. Existing React Router, Starlette/httpx and Vite chunk-size warnings remain. No Rust, migration, provider, Figma, packaged WebView, screenshot, external write, signed/notarized artifact or pixel-parity claim belongs to this slice.
- 2026-07-20: Distilled Agent Activity into a continuous local learning-run record without changing Agent events, provider behavior, approvals, Undo/Redo or persistence. The panel no longer uses an elevated rounded container, filled generic status card or nested mutation cards; response text is 13 px and supporting operational text is 11–12 px instead of 9–10 px. Error and warning emphasis remains semantic. An explicit development-only Browser Demo fixture renders only the honest empty state and states that no Agent ran or data changed. Browser checks at 980×900 found one `main`, no horizontal overflow, no unnamed buttons, reduced-motion coverage, zero panel radius/shadow and a transparent status row. Focused tests passed 24/24 and the complete desktop suite passed 310/310; strict typecheck, ESLint, production build and Impeccable detection passed. The visual harness saved `artifacts/visual-diff/current/home-agent-activity-empty.png`, but its reference is missing, so no mismatch percentage or parity result exists. The refreshed ad-hoc arm64 DMG is 34,084,482 bytes with SHA-256 `ba49211cd61d98591054a501b1a6b010bd17fcbf1ed2e8d4eaa45c0458d21df6`; after one failed DMG-script attempt, a bounded direct retry and the complete mounted verification passed. Evidence is recorded in `artifacts/package/2026-07-21-agent-activity/README.md`.
- 2026-07-20: Tightened Home's real Agent action ownership without changing the runtime or API. The composer now maps non-cancellable create/recover/finish/cancel phases to labelled shared loading states, exposes the stop icon and `Cancel` only for a genuinely active run, and remains the single cancellation control on the page. Agent Activity retains process/evidence presentation but omits cancellation when its consumer supplies no executable callback, avoiding duplicate or dead controls. Focused Home/Activity validation passed 23/23; the complete desktop suite passed 309/309; strict typecheck, ESLint and production build passed. These transient states have no accepted fixed-viewport reference, so the existing provisional Home comparison was not rerun or represented as parity.
- 2026-07-20: Replaced the direct Study Planner Demo with a truthful not-implemented boundary while preserving a future implementation contract. Removed the fixed July week, invented session totals/countdown/availability, local completion toggles, disabled import/navigation/add/rationale controls and non-executable calendar-confirmation modal. The route has one real alternative action to Learning Feed and three non-interactive gates: validated course inputs, typed/persisted/recoverable planning state, and an external calendar adapter with Level 3 proposal confirmation. Future UI is reintroduced only when its API/SQLite/permission boundary exists; no current Demo state is kept as a compatibility layer. Browser checks at 1280×800 and 760×700 found one `main`, zero horizontal overflow, zero disabled controls and zero dialogs. One new workflow regression brings the desktop suite to 299/299; strict typecheck, ESLint, production build, Impeccable detection and the visual harness passed. Evidence is under `artifacts/ui-audit/2026-07-20/planner/` and `artifacts/visual-diff/current/planner-boundary.png`; the accepted Planner reference is absent, so the harness reports `missing_reference`.
- 2026-07-20: Distilled the direct Visualize development route from a simulated generation workspace into one fixed teaching specimen. Removed prompt editing, output-format choices, timer-driven progress/success, disabled source/export/motion actions and the future renderer setup card. The route now presents an accessible bundled eigenvector SVG and states exactly what is local/offline versus not implemented; it performs no file read, model/service call, source grounding, generation, animation, export or artifact write. Browser checks at 1280×800 and 820×720 found one `main`, no horizontal overflow, no unnamed buttons and no disabled controls; the compact page has 674 px of viewport height and 918 px of intentional internal scroll content. One new regression raises the desktop suite to 298/298; strict typecheck, ESLint, production build, Impeccable detection and the visual harness passed. Current captures are under `artifacts/ui-audit/2026-07-20/visualize/` and `artifacts/visual-diff/current/visualize-demo.png`. The configured Visualize reference is absent, so the harness reports `missing_reference` and no parity claim is made.
- 2026-07-20: Distilled the app-level command surface without removing development routes or changing runtime capability. The command palette exposes only two real entry actions and four primary pages, groups Actions/Pages, searches intent keywords, handles empty search, supports wraparound Arrow selection, Enter, Escape, Tab trapping and opener-focus restoration. Learner Memory was removed from ordinary command discovery; Quiz, Flashcards, Planner, Learner Memory and Visualize keep their direct routes for deterministic UI development but display `UI demo` in the toolbar. Browser inspection at 1280×720 and 720×520 found zero horizontal overflow, correct search focus and visible Demo labeling. Two new workflow regressions bring the desktop suite to 297/297; strict typecheck, ESLint, production build, Impeccable detection and the visual harness passed. Evidence is under `artifacts/ui-audit/2026-07-20/command-palette/`. No provider, memory ingestion, FSRS scheduling, calendar write, visualization generation or accepted visual baseline was added.
- 2026-07-20: Completed a bounded shared-component convergence pass. `@keen/ui` Button now exposes compatible variant, size and loading props; its loading state sets `aria-busy`, blocks repeat activation and preserves feature-owned busy state when shared loading is inactive. IconButton is non-submitting by default, Badge accepts semantic span attributes, and Progress remains bounded/labelled. Canonical control geometry and default/hover/focus/active/disabled/loading behavior moved into the shared desktop stylesheet; duplicated refresh overrides were removed. Accent and status literals now use semantic tokens, including a new Light/Dark `--warning-soft` production token aligned with the existing Figma foundation. `docs/figma/COMPONENT_RUNTIME_SPEC.md` records the implemented contract and truthfulness boundary. Browser inspection at 1280×720 across Home, Feed, Knowledge Base, Conversation and Settings found one `main`, no horizontal overflow and no unnamed buttons on every route; visible Badges were consistently 22 px with 11 px text and shared Buttons 34 px with 8 px radius. Four new shared-component tests bring the complete desktop suite to 295/295; strict typecheck, scoped ESLint, production build, Impeccable detection and the visual harness passed. Provisional comparisons now measure Home 1.993%, Feed 1.528%, task detail 3.180%, Deep Learn 1.654%, and Feed state fixtures 1.056–1.368%; they remain provisional, while other routes remain `missing_reference`, so no accepted-baseline or pixel-parity claim was added.
- 2026-07-20: Continued the bounded UI-only convergence with Settings as an honest capability ledger. The page now exposes five purposeful sections—Status, Model provider, Connections, Privacy & data and Open source—while removing the duplicate `main`, fake Save state, non-persisting provider/API-key form, disabled preview switches, simulated external-connection success and repeated disabled viewer actions. Existing Learning Core state drives the runtime row, and supervised Retry is shown only when the desktop runtime reports a retryable non-starting failure. No provider secret, OAuth flow, calendar/Drive/Canvas adapter, preference persistence or notice viewer was added. Focused App/Learning Core validation passed 54/54 and the complete desktop suite passed 291/291; strict typecheck, scoped ESLint, production build and the scoped Impeccable detector passed. Browser inspection at 1280×720 found one `main`, no horizontal overflow, one selected settings section, zero unnamed buttons and zero disabled form controls. The visual harness refreshed Status at 1440×920 and 900×700 plus Connections at 1440×920 and 1100×760; each remains `missing_reference`, so no accepted baseline, mismatch percentage, complete accessibility audit, packaged-app result or pixel-parity claim was added.
- 2026-07-20: Continued the bounded UI-only convergence with Conversation as a study record rather than a floating-chat surface. Existing authenticated streaming, stop, retry, edit, course scope, validated citations, PDF viewer and service recovery remain intact. The compact heading exposes Demo/live/unavailable provenance; messages use a bounded Question/Answer reading flow; citations are grouped as Sources; and the bottom workbar replaces the floating gradient composer. Permanently unavailable copy, branch and attachment controls are absent instead of disabled, while Browser Demo still makes no network or Tauri request. Focused Conversation/Learning Core validation passed 46/46 and the full desktop suite passed 291/291; strict typecheck, scoped ESLint, production build and the scoped Impeccable detector passed. Chrome checks at 1510×950 and 900×700 found no horizontal document overflow, one `main`, no unnamed buttons, a bottom-aligned composer and independent long-transcript scrolling. The visual harness now records 1510×950 and 900×700 Conversation captures as `missing_reference`; no accepted baseline, mismatch percentage, live-provider screenshot, complete accessibility audit, packaged-app result or pixel-parity claim was added.
- 2026-07-20: Continued the bounded UI-only convergence with Knowledge Base as a source-first local workspace. The existing real upload, indexing-job polling, retry/cancel/reindex/delete, course-link and error-recovery behavior is unchanged; the page now presents one Import source action with an in-place panel, progressively discloses course creation, keeps stable list rows for processing/status feedback, and removes nonessential add-link controls from Browser Demo while preserving its explicit sample/no-upload/no-index boundary. The collapsed import panel remains mounted to preserve the existing form contract but uses the native `hidden` boundary so its controls leave the accessibility tree and Tab order. Current Browser Demo captures at 1510×950, 1100×760 and 900×700 plus the open import state are stored under `artifacts/visual-diff/current/knowledge-base*.jpg`. Focused Knowledge/course tests passed 50/50 including the new keyboard-order check; the complete desktop suite passed 291/291; strict typecheck, scoped ESLint, production build and Impeccable detection passed. The visual harness completed and refreshed its configured captures, but Knowledge Base is not yet configured because it has no accepted baseline. The authorized HyperKnow captures were used as qualitative structure evidence only. No accepted Knowledge Base baseline, mismatch percentage, provider/RAG capability, live ingestion result, packaged-app verification, complete accessibility audit or pixel-parity claim was added.
- 2026-07-20: Continued the bounded UI-only convergence with the current Deep Learn page represented by editable Figma node `65:2`. The implementation keeps the session header and side rails available through long content, focuses selected lesson headings and post-answer feedback, raises the light tertiary text token from 4.26:1 to approximately 4.70:1 on white, removes the nested Deep Learn `main`, consolidates repeated Demo disclaimers, condenses the primary Sidebar to a labelled 60 px icon rail below 1000 px, and replaces shared progress width animation with transform animation. Browser Demo content remains bundled, illustrative, unverified and discarded on exit; no model, provider, citation verification, mastery write or review scheduling was added. Strict typecheck and ESLint passed, focused App/Deep Learn tests passed 34/34, and the scoped Impeccable detector returned no findings. Chrome checks at 1585×950 and 900×700 found one `main`, zero horizontal overflow, reduced-motion support and correct next-heading focus. The visual harness measured 1.602% at the matching 1585×950 viewport and refreshed the existing 1100×760 compact Summary screenshot. Node `65:2` is a provisional current-product Figma export, not an accepted reference, so no parity claim is made; packaged-app and complete accessibility validation remain open.
- 2026-07-20: Continued the bounded React convergence pass for Figma nodes `155:187`, `164:179`, and `176:340`. Home now uses a 720 px reading/composer column, avoids a duplicated Demo disclosure and removes the decorative send glyph from the disabled Continue control while retaining truthful Demo/Sample labels. A shell sizing defect was fixed with `min-height: 0` on `.main-area`; lower task selection now scrolls only the task rail, leaving `window.scrollY=0` and the task-detail toolbar visible at 1180×740. The compact detail panel now uses the measured Figma inset, content padding, workflow rhythm and footer height; programmatic heading focus no longer paints a control-style ring. Browser Demo alone accepts `visualTest=true` to freeze July 2026 and an optional `selectedTask` fixture for repeatable captures; live Tauri/service behavior is unchanged. Figma Button `33:2` now uses Inter Medium for all 18 variant labels; Code Connect was attempted but blocked by the current seat requirement. Reduced-motion Chrome captures at 1180×740 and 1585×941 are under `artifacts/ui-audit/2026-07-20/react-figma-convergence/`. Strict typecheck, ESLint, 19 focused Home/Feed tests and `git diff --check` passed. The visual harness now has three provisional same-size comparisons—Home 1.988%, Feed 1.555%, selected detail 3.158%—and seven older `missing_reference` routes. These figures are not accepted baselines or pixel parity. Live operational-state captures, complete keyboard/a11y inspection and accepted baselines remain open.
- 2026-07-20: Extended the same bounded convergence pass to the four truthful compact Feed operational states in Figma nodes `178:418`, `179:596`, `179:998`, and `179:1400`. A development/browser-only visual fixture can render unavailable, startup, no-course and validation-error states without Tauri or network calls; it requires `visualTest=true` plus an explicit `visualCoreState` and is not active in packaged/live behavior. Runtime Feed actions are now absent until a valid local course and snapshot exist, and the no-course branch no longer leaks the fallback filter/task empty state. Chrome at 1180×740 found no horizontal overflow, honored reduced motion and exposed visible focus rings on the unavailable/error recovery controls. Four provisional Figma comparisons measured 1.314%, 1.218%, 1.057%, and 1.368% respectively. Focused Learning Core/Feed tests passed 54/54; accepted baselines and full accessibility coverage remain open.
- 2026-07-20: Continued Figma-only Phase 4 with selected-task default `172:262`, selected-task compact `176:340`, local-service unavailable `178:418`, authenticated-health loading `179:596`, no-courses empty `179:998`, and live-data validation error `179:1400`. The selected task remains a deterministic Browser Demo record; its 68% mastery is labelled illustrative and its update actions explicitly create no session. The four local operational screens copy current React recovery semantics, use an empty Month calendar, and do not fall back to Demo tasks. Final Plugin API checks found no missing fonts, non-finite geometry or horizontal root overflow. `references/keen/2026-07-20-figma-phase4/README.md` inventories direct exports, a state contact sheet and the qualitative current-screenshot/Figma comparison. React implementation, runtime keyboard/reduced-motion/accessibility checks, actual live-state captures and accepted visual baselines remain pending; no pixel-parity claim is made.
- 2026-07-20: Completed the bounded Figma-only Phase-4 compact/responsive and Learning Feed componentization pass in `ugwiIPdF43v2woYsLM3b9R`. Home compact `155:187` is a 1180×740 reflow rather than a scaled desktop frame. Feed Task Card `159:220` and Calendar Event `160:111` cover the visual states used by the current page; default Feed `162:97` replaces raw task/event layers with component instances, while compact Feed `164:179` uses flexible grid tracks to retain seven calendar columns at 1180×740. `docs/figma/LEARNING_FEED_DATA_MAPPING.md` records API/React/Demo precedence and explicitly excludes Week view, calendar connection/write and invented success data. Final Figma inspection found zero missing fonts, non-finite geometry or horizontal root overflow; the compact rail's lower card remains expected scroll content. Evidence and rejected first-pass captures are inventoried under `references/keen/2026-07-20-figma-phase4/`. No React source, runtime capability, accepted visual baseline, mismatch percentage or pixel-parity claim changed; selected task-detail, loading/error/offline screens, runtime keyboard/reduced-motion/accessibility verification and React implementation remain next.
- 2026-07-20: Re-audited the three Phase-3 Home Figma exports after user review identified that the screenshots looked abnormal. Fresh 1585×907 captures proved 1 px `⌘N` overflow in all states, a 9 px stale-text overflow in the default Sidebar footer, detached floating operational copy, duplicated offline/provider explanation and overly tall fixed state panels. Targeted Figma edits removed the redundant disclosure/footer layers, widened the introduction, repaired shortcut geometry and changed empty/error panels to hug content. A final Plugin API pass found zero visible text nodes outside clipping ancestors and zero non-positive visible text geometry across `113:3`, `130:52`, and `131:195`. Before/after captures and limits are under `references/keen/2026-07-20-figma-phase3-screenshot-audit/`. React implementation remains unchanged and no responsive, accessibility, accepted-baseline, mismatch-percentage or pixel-parity claim is added.
- 2026-07-20: Completed the bounded Figma-only Phase-3 Home reconstruction in `ugwiIPdF43v2woYsLM3b9R`. Home Screen `113:2` contains default Browser Demo `113:3`, learning-core offline `130:52`, and provider-not-configured `131:195` states at 1585×907; Queue Row `121:26` covers Default, Hover and Focus while the page reuses the existing Nav Row, Badge, Button and icon components. `docs/figma/HOME_DATA_MAPPING.md` makes runtime/API and deterministic Demo data authoritative over Figma and reference-product content. Final Plugin API inspection found only SF Pro visible text, positive text geometry, no temporary lorem/shimmer artifacts, no `Completed` or provider-success claims, and the required offline/provider-missing disclosures. Captures and limitations are under `references/keen/2026-07-20-figma-phase3/`. Visual QA removed redundant operational badges after the Figma API exposed stale/wrapping SF Pro overlays. React implementation remains not started for this phase pending user confirmation; compact/dark/collapsed states, runtime keyboard/accessibility/reduced-motion checks, accepted baselines and Code Connect remain open. No mismatch percentage or pixel-parity claim is made.
Append short dated entries. Link artifacts or commands; do not replace historical facts.

- 2026-07-19: Exercised an authorized synthetic learning answer, review-plan request and three-page PDF upload in HyperKnow. Stable 1700×777 captures, rejected transient-toast captures, payload provenance and the expired-authentication blocker are inventoried in `references/hyperknow/2026-07-19-full-synthetic-flow/README.md`. Calendar/Drive/Canvas live entry testing did not pass because Home navigation redirected the session to `/signin`; no personal account chooser, cloud file, event or LMS course was retained. Applied a bounded UI-only response in Keen: `DemoLearningEvidence` adds clearly sample-only feedback, page-labelled demo citations, illustrative mastery and recommendation-only review timing to Browser Demo Summary; Settings now exposes only six categories and a `Connections` preview whose Google Calendar/Drive success states are React-memory simulations and whose Canvas adapter remains `In development`. Live learning, provider, OAuth, persistence, FSRS and Level 3 boundaries are unchanged. The visual harness now captures seven routes/states at 1440×920 and 1100×760 with reduced motion; every result is `missing_reference`, so mismatch and parity remain unverified. ESLint, strict typecheck, production build, 26 files / 283 tests and `git diff --check` passed. Packaged Tauri rendering and a complete accessibility audit were not run.
- 2026-07-19: Extended the authorized HyperKnow audit through unit completion, Proceed, Learning Feed Month/Week/Pending, Knowledge Base upload/processing/search/hover/menu, History, new-conversation attachment, generated plan, diagnostic, grounded explanation and quick recall. The 21 retained captures and evidence limits are documented in `references/hyperknow/2026-07-19-complete-flow/README.md`; the only new upload was `references/audit-fixtures/hyperknow-learning-flow-sample.txt`. Delete, calendar/integration connection, Drive/Canvas, sharing, personal-data retention, browser storage, private traffic and source-code inspection were not performed. HyperKnow showed useful current/progress/next continuity but also generic Home AI grammar, wide empty states, a filename-only-looking search mismatch, hover-hidden file actions and an unnamed Send control. This remains qualitative research, not an accepted pixel baseline.
- 2026-07-19: Applied a bounded Deep Learn continuity pass from that audit. The existing learning-path rail now derives and presents Current/Next state across diagnostic, source study, active recall, targeted practice, summary, completion and terminal recovery; Browser Demo explicitly states that it schedules no review. No runtime, schema, provider, persistence, citation or calendar capability changed. Evidence includes default, paused/disabled and summary/disabled-review captures plus `artifacts/ui-audit/2026-07-19/hyperknow-keen-learning-continuity-comparison.png`. Browser inspection at 1700×777 found no horizontal overflow, duplicate IDs, unnamed focusables or application errors; full keyboard traversal was not re-established. Focused tests passed 37/37, full desktop tests 282/282, and ESLint, strict typecheck, production build, Impeccable detection and `git diff --check` passed. The build warning and three visual-harness `missing_reference` results remain; no packaged-app, complete accessibility or pixel-parity claim is made.
- 2026-07-19: Completed the authorized authenticated HyperKnow audit after the user provided an already signed-in Chrome state. The synthetic, non-personal fixture `references/audit-fixtures/hyperknow-ui-audit-sample.txt` was uploaded once. Internal-only captures under `references/hyperknow/2026-07-19-flow-audit/` cover Knowledge Base upload processing/completion and menus, Deep Learn request/trace/result/outline/reading/loading/completion, generic cropped Settings, and Month/Week Learning Feed. No personal identity or memory screenshot was retained; existing user-created sidebar content was cropped out; Delete, calendar/integration connection and external share were not performed. The reference is qualitative, not an accepted fixed-viewport pixel baseline, and no source code, browser storage or private network traffic was inspected.
- 2026-07-19: Applied a bounded UI-only Deep Learn refinement from that audit. Progress moved from the header into the learning-path rail, the lesson became a left-aligned editorial reading column with thin-accent callouts, the recall card was flattened into an end-of-reading checkpoint, and the real persisted source material uses the same reading treatment. Existing live/session protection, recovery, persistence and Demo disclosure behavior is unchanged. Evidence under `artifacts/ui-audit/2026-07-19/deep-learn-reference-refinement/` includes the source/current before and after comparisons, final 1280×720 view and paused/disabled state. Browser checks exercised disabled, active and success feedback behavior and found no horizontal overflow, duplicate IDs, unnamed focusables or application errors; Tab-key traversal could not be fully verified. ESLint, strict typecheck, 26 files / 282 tests, production build and `git diff --check` passed with the existing Vite chunk-size warning. No packaged-app or pixel-parity claim is made.
- 2026-07-19: Follow-up Deep Learn polish removed the remaining assistant-template signals from the bounded reading view: disabled decorative header actions, vertical accent strips, pill-like recall labeling and full-width feedback bars. The 690 px editorial column, tokenized surfaces, inline pause notice and end-aligned answer action preserve the existing lesson/session behavior. Programmatic Browser Demo checks at 1280×720, 1024×768 and 900×700 found no horizontal overflow, duplicate IDs, unnamed focusables or application errors; opening the textarea preserved `scrollY=0`, reduced motion matched, the visible Tab sequence reached page actions, and temporary extended lesson copy remained vertically scrollable. Evidence is under `artifacts/ui-audit/2026-07-19/deep-learn-polish/`. ESLint, strict typecheck, 20/20 focused tests, 26 files / 282 full tests, production build and `git diff --check` passed. The existing bundle warning and three visual-harness `missing_reference` results remain; no packaged-app, complete accessibility or pixel-parity claim is made.
- 2026-07-19: Continued the UI-only HyperKnow/Keen identity refinement without changing navigation, data contracts or runtime capability boundaries. Home's prompt heading and Conversation's Keen answer identity now use the transparent traced Keen mark; learner messages are flat transcript rows rather than generic assistant-chat bubbles. Browser Demo Home and Conversation captures at 1280×720, plus combined full/focused Home comparisons, are under `artifacts/ui-audit/2026-07-19/brand-identity-refinement/`. The source/current aspect ratios and states differ, so the comparison is qualitative and no pixel-parity result is claimed. Ask/Study mode switching and disabled empty submission were exercised, the console showed no application errors, and desktop ESLint, strict typecheck, 26 files / 282 tests, production build and `git diff --check` passed. Whole-app interaction-state coverage, accepted visual baselines and packaged Tauri inspection remain open.
- 2026-07-19: Continued the Figma-native Keen design-system pass in `ugwiIPdF43v2woYsLM3b9R`. Phase 1 now has five collections / 99 variables after adding token-bound Light/Dark warning-soft values, plus nine text and six effect styles. Phase 2 retains verified Cover, Color, Type and Layout captures under `artifacts/ui-audit/2026-07-19/figma-foundations/`. Phase 3 now includes Button `33:2` (18 variants), IconButton `45:30` (six states and a nested icon-swap property), Badge `52:12` (five runtime-aligned tones) and Service Banner `59:32` (four supervised learning-core startup/failure groups). IconButton uses internal Simple Design System Plus/Refresh library instances only as design references; production continues to use the existing Lucide children. Badge intentionally has no hover/focus/loading variants. Service Banner deliberately omits a healthy-success banner because runtime uses compact `LearningCoreStatus`, and it is documented as a composition specification rather than an existing shared React export. Component structure, names, editable text references, geometry and semantic bindings were inspected. Direct captures and a Button before/after diff are under `artifacts/ui-audit/2026-07-19/figma-components/`; the responsive-label repair changed 7,185 pixels (0.697%) in the same-size Figma page render and was visually checked. This is not an accepted product baseline, pixel-parity, runtime accessibility, responsive, motion or packaged-app milestone. React Loading support, Button geometry synchronization, shared Service Banner extraction and the remaining navigation/page components stay open.
- 2026-07-19: A read-only aesthetic/anti-AI audit captured the current Browser Demo Home and Learning Feed at 1440×900, 1180×760 and 900×700 under `artifacts/ui-audit/2026-07-19/final-aesthetic-audit/`. The inspected layouts do not overlap or overflow horizontally, but the current composition still inherits the reference's centered assistant-composer grammar and compounds it with nested rounded surfaces, repeated status pills, pervasive 9–11 px text and border-plus-shadow containers. Measured evidence includes 79/87 visible leaf text nodes below 12 px at 900×700, 4.26:1 tertiary-on-white contrast, 4.14:1 effective placeholder contrast, about 84×21 px calendar event controls, and a 1370 px document height when the ≤930 px Feed stacks its full calendar below the task pane. The audit found no unnamed buttons, duplicate IDs or application console errors; keyboard focus traversal remained unverified. No runtime source was changed by this audit. The next UI order is distill Home/Feed structure, typeset the microcopy floor, replace the narrow Feed stack with an explicit view switch, then polish borders/icons/tokens.
- 2026-07-19: Applied the user-provided 204×228 Keen icon to the Sidebar and browser-demo favicon only. The packaged Tauri icon set remains unchanged because the supplied raster is not packaging-resolution evidence. The inspected 1440×920 capture is `artifacts/ui-audit/2026-07-19/keen-home-brand-1440x920.png`; desktop ESLint, strict typecheck, 26 files / 282 tests, production build and `git diff --check` passed. The visual harness produced three `missing_reference` results, so it does not establish a visual-regression or pixel-parity pass.
- 2026-07-23: The user selected the flat dark-and-teal Keen mark for the product identity. A clean three-path SVG was generated from that reference before it replaced the unrelated provisional line-art `K` in the Tauri icon source; the checked-in macOS, Windows, iOS and Android icon outputs were then regenerated from that single source. This updates source assets only; no fresh `.app`/`.dmg`, signing, notarization or packaged visual result is claimed.
- 2026-07-15: Initial plan created from an empty local repository. References, upstream checkouts, licenses, tests, and builds were unavailable at audit time.
- 2026-07-15: Parallel work introduced Tauri/React/Python source and validation artifacts. Rust 1.97.0 was installed; the later entries below record consolidated test and packaging evidence. Milestone 1 remains in progress because its remaining integration gates are not satisfied.
- 2026-07-15: Read-only `/tmp` audit verified DeepTutor `3e3b9a6e…` as Apache-2.0 and OATutor `0d376e23…` as MIT at their reviewed parent revisions. Neither was introduced; implementation choices remain independently gated.
- 2026-07-15: Frontend ESLint and strict typecheck passed; Vitest passed 2 files / 5 tests; Vite built 1,658 modules. Python pytest passed 6 tests. Rust fmt check, clippy with `-D warnings`, and 3 tests passed.
- 2026-07-15: Visual harness captured Home at 1440×920 and reported `missing_reference`; this is not a pixel-match pass. The capture/report are local gitignored artifacts, not durable evidence in this repository.
- 2026-07-15: Generated an 11 MB arm64 `Keen.app` and a 2.8 MB `Keen_0.1.0_aarch64.dmg`. `hdiutil verify` passed; the app is ad-hoc/linker-signed, not distribution-signed or notarized, and the bundles do not yet contain learning-core.
- 2026-07-15: npm production audit and the upgraded Python environment audit reported zero known vulnerabilities. npm/Python/Cargo license metadata reports were generated under the local gitignored `artifacts/license-scan/`; they are not present in a GitHub checkout. Cargo vulnerability audit and complete notice reconciliation remain open.
- 2026-07-16: Added migration `002_documents.sql`, bounded PDF/Markdown/TXT ingestion, SHA-256 storage/deduplication, pypdf page extraction, status history, page/section/character-aware chunks, FTS5 search, and deterministic extractive citations. OCR, embeddings/vector search, PDF viewing/highlighting, and model-backed RAG remain absent.
- 2026-07-16: Connected the Tauri UI to a strict loopback/Zod client. Browser runs stay in explicit Demo mode; Tauri Learning Feed and Knowledge Base use authenticated live state and do not silently substitute Demo data on service failure.
- 2026-07-16: Added PyInstaller 6.21.0 packaging and Tauri sidecar supervision. The generated arm64 binary and sidecar-bearing `.app` launched successfully; manual crash testing observed one restart on a new PID/port and no second restart, while application quit removed both PyInstaller processes and the listener. This is manual smoke evidence, not automated lifecycle E2E.
- 2026-07-16: Rebuilt `Keen_0.1.0_aarch64.dmg` with the 17,828,608-byte sidecar embedded. The DMG was 21,555,102 bytes; `hdiutil verify` passed, both executables were arm64, and the mounted app passed `codesign --verify --deep --strict`. A later runtime check showed that ad-hoc hardened runtime prevents the PyInstaller dylib from loading, so this historical artifact was superseded by the explicit non-hardened local-verification path. `spctl --assess` returned rejection status 3 because Developer ID signing and notarization are absent.
- 2026-07-16: Current checks passed: frontend ESLint and strict typecheck; Vitest 5 files / 35 tests; Python `PYTHONPATH=services/learning-core .venv/bin/python -m pytest services/learning-core/tests` 47 tests with one Starlette deprecation warning; Rust fmt, clippy `-D warnings`, and 19 tests.
- 2026-07-16: Exact pypdf 6.14.2 and python-multipart 0.0.32 wheel hashes/licenses were verified, and installed PyInstaller/community-hook license files were inspected. `THIRD_PARTY_NOTICES.md` remains explicitly incomplete pending full shipped-subset reconciliation.
- 2026-07-16: The final local-verification packaging gate rebuilt `Keen_0.1.0_aarch64.dmg` at 21,761,944 bytes (SHA-256 `da60e4b08bd3b3c8b77e90bbc2c7a7c625009f810d44400a806081242dfc5e87`). `hdiutil verify`, arm64 architecture checks, and mounted-app `codesign --verify --deep --strict` passed. Both the build-tree app and the exact mounted DMG passed authenticated loopback health, valid PDF import, compressed-PDF resource rejection, post-rejection health, token-leak, isolated-worker/resource-tracker accounting, and full process-cleanup smoke tests. This is an ad-hoc, non-notarized local artifact, not a distributable release.
- 2026-07-16: Sidecar/RAG hardening Gate 1 separated development (`com.keen.learning.dev`) and production identities, removed implicit debug seed, added strict PORT/phase/READY/health startup gates, manual restart/token rotation/generation serialization, shutdown-intent and macOS reopen handling, bounded child-output frames, and real frontend restart/status behavior. Consolidated checks passed: frontend lint/typecheck/build and 53 tests; Python 57 tests plus compileall; Rust fmt/clippy and 33 tests. GUI reopen, real IPC restart, bundled READY smoke, and new packaging remain unverified.
- 2026-07-16: Hardening Gate 2 replaced synchronous indexing with migration-backed single-worker jobs and `202` import, real progress, server cancellation, retry/delete, interrupted recovery, missing/orphan/quarantine reconciliation, configurable PDF budgets, and a streaming ASGI request cap. Transactional race and real PDF process-group cancellation tests are included. Consolidated checks passed: frontend 69 tests plus lint/typecheck/build; Python 3.11 90 tests plus compileall; Rust 33 tests plus fmt/clippy. Ruff passed only in the local Python 3.14 service environment; root Python 3.11 Ruff and MyPy are not configured.
- 2026-07-16: Hardening Gate 3 added backfilled many-to-many course/document links, same-hash cross-course reuse, live course selection/link/filter UI, and dual Latin/CJK lexical retrieval with mixed-query RRF. The five required multilingual fixtures ranked their relevant chunk first. Consolidated checks passed: frontend 72 tests plus lint/typecheck/build; Python 3.11 121 tests plus compileall and local Python 3.14 Ruff; Rust 33 tests plus fmt/clippy. Hybrid/vector retrieval, providers, generated answers, and citation viewing remain not started.
- 2026-07-16: Hardening Gate 4 added exact-pinned sqlite-vec/HTTPX provenance, provider-neutral interfaces, guarded loopback local embeddings, ready/complete-only vector search, hybrid RRF, truthful lexical fallback, and model-pinned embedding-only reindex with atomic staging. Consolidated source checks passed: frontend 79 tests plus lint/typecheck/build; Python 3.11 260 tests plus Ruff/compileall; Rust 34 tests plus fmt/clippy. Generated answers, PDF citation geometry/viewing, and final frozen app/DMG verification remain open.
- 2026-07-16: Hardening Gate 5 added loopback-only OpenAI-compatible/Ollama chat streaming, bounded provider protocols, strict seven-event answer SSE, untrusted-source prompt boundaries, server-owned structural citation remapping, end-to-end disconnect cancellation, and the real Tauri Conversation client with bounded SSE parsing, incremental output, stop/retry/edit/draft, provider/retrieval/restart states and citation Inspector. Browser Demo makes zero model/retrieval/Tauri requests. Monitoring checks passed Python 3.11 276/276 and the frontend Gate 5 subset 45/45; execution-window checks passed frontend 93/93 plus lint/typecheck/build, Ruff/format/compileall, Rust 35 plus fmt/clippy, and `git diff --check`. PDF geometry/viewing and final packaging remain open.
- 2026-07-16: Hardening Gate 6 added migration-backed pdfminer span geometry, single-chunk generated-answer sources, exact cross-page citation mapping, authenticated canonical PDF content/range serving, and a page-on-demand local PDF.js dialog with highlight/page-only states, byte/canvas caps, cleanup-race handling, and modal keyboard focus management. Real rotation and CropBox PDFs prove fail-closed `bbox: null`; ordinary-page geometry remains highlighted. Consolidated checks passed frontend 108/108 plus lint/typecheck/build, Python 284/284 plus Ruff/format/compileall/pip check, and Rust 38/38 plus fmt/clippy; independent review found no remaining P0/P1.
- 2026-07-16: Hardening Gate 7 added a 24-package hashed CPython 3.11/macOS arm64 PEP 751 runtime lock and isolated frozen build, then ran the actual app/DMG pipeline. `Keen_0.1.0_aarch64.dmg` is 33,495,605 bytes with SHA-256 `5246ab0c4955498f2891561789d9fb6a27de9fddb13790282606ddf51fb0f16f`; checksum, arm64 architecture, strict deep ad-hoc signature, and build-tree/mounted-DMG READY/jobs/cancel/CJK/M:N/vector/PDF/token/process smoke passed. It remains non-notarized and Gatekeeper-rejected; complete notices, Universal/Intel, credentialed distribution signing, automated GUI/provider E2E, and authorized visual parity remain open.
- 2026-07-16: Started the recoverable learning-loop milestone on `codex/milestone-learning-loop` from `094c44e`. Gate 0 records a clean pre-implementation baseline of frontend lint/strict typecheck and Vitest 108/108, Python pytest 284/284 with one existing warning, and Rust 38/38. Conversation persistence, Agent audit/tools, Deep Learn, Assessment, mastery evidence, misconceptions, FSRS Review and explainable Feed mutation remain `not started` unless later evidence updates this log.
- 2026-07-16: Learning-loop Gate 1 added forward-only migrations 009–016 and typed, transaction-composable repositories for durable Conversation, Agent audit/permissions, Study Sessions/versioned plans, Assessment, mastery evidence/events, misconceptions, Review/FSRS state, and explainable Study Tasks. Legacy `mastery_events` and `study_tasks` are preserved and backfilled; an actual 008-to-016 fixture passed consistency checks. Gate 1 migration/repository tests passed 46/46, the current full Python suite passed 374/374 with one existing warning, Ruff lint/format passed for 86 files, and independent review found no remaining P0/P1. This verifies persistence boundaries only; HTTP, orchestration, FSRS scheduling, and live frontend workflows remain open.
- 2026-07-16: Learning-loop Gate 2 added the exact-pinned py-fsrs 6.3.1 adapter and forward migration 017. Review scheduling now uses fixed, versioned Keen v1 parameters, UTC-aware validated state, stable positive identities allocated under a SQLite write transaction, complete 015 backfill for pristine new schedules, and repository-to-scheduler restart round trips. Focused scheduler/repository/migration/vector tests passed 43/43, the stable full Python suite passed 500/500 with one existing Starlette warning, and Ruff lint/format passed for all 97 learning-core Python files. This does not claim the Flashcards UI or assessment-to-review orchestration is connected.
- 2026-07-16: Gate 3 foundation added a closed typed Agent tool registry, permission/effect policy, cancellable single-step executor, Level 2 caller-owned transaction handoff, executable typed inverse mutation, bounded untrusted-document context, and redacted audit summaries while separately passing raw typed mutations to the controlled persistence boundary. Agent-focused tests passed 35/35 and independent review found no remaining P0/P1 in this slice. SQLite AuditSink integration, idempotent replay, Undo execution, product tools, orchestrator, SSE/reconnect and UI remain open; Gate 3 is not marked verified.
- 2026-07-16: The first Gate 3 product-tool slice added typed real-data tools for Study Feed reads, due Review reads and course-scoped Study Task completion, plus a Level 3 export declaration that remains blocked by the executor. Focused SQLite tests passed 6/6 for closed schemas, UTC, course scope, caller-transaction rollback and executable Undo output. Additional tool groups, persistent audit/replay, Undo execution and orchestration remain open.
- 2026-07-16: The Gate 3 service slice added a single-provider orchestrator protocol, fixed automation-only provider, durable SQLite event store, ordered/redacted public Agent events, real tool-step lifecycle, stable invocation replay handling, bounded action/content/payload budgets, cancellation/error terminal states and Last-Event-ID SSE continuation. Focused tests passed 17/17 and the combined Agent subset passed 63/63. FastAPI Agent routes, UI, real provider selection and process-restart continuation remain open, so Gate 3 is still in progress.
- 2026-07-16: The Gate 3 audit/Undo slice added migration 018, an atomic SQLite audit/idempotency adapter, uncertain-commit reconciliation, allowlisted Study Task Undo/redo and an authorizer-backed Level 2 session that denies transaction control and cross-table access. The stable full Python suite passed 548/548 with one existing Starlette warning; Ruff lint/format passed 109 files, and independent adversarial review passed 59/59 focused tests with no remaining P0/P1. The restricted write session currently covers only `study_tasks`; FastAPI Agent routes, process-restart provider continuation, visible Undo, remaining tool groups and real provider selection remain open, so Gate 3 is still in progress.
- 2026-07-16: The Gate 3 API slice exposed authenticated Agent run create/get/cancel and durable SSE event routes, with app-scoped background ownership of the audit database, idempotent startup terminal recovery events, real `mutationId` values on normal mutation events, a 64 KiB request guard, and truthful `provider_missing` behavior by default. Independent verification passed the full Python suite 566/566 and the related subset 105/105; the execution window also passed an expanded focused subset 113/113. Ruff lint, Ruff format and `git diff --check` passed. Gate 3 remains in progress: a real provider, Undo HTTP, strict API-client/frontend Agent activity, and kill-restart/socket E2E are still open.
- 2026-07-16: The Gate 3 client slice added strict Zod contracts for Agent create/get/cancel and durable SSE, safe provider/busy error mapping, event-ID preservation, Last-Event-ID/cursor reconnect and fail-closed hidden-reasoning/unknown-field validation. Desktop ESLint and strict typecheck passed, all 124 Vitest tests passed, and the Agent/API-client subset passed 61/61. The visible Agent Activity runtime and UI remain open.
- 2026-07-16: The Gate 3 inverse-action slice exposed authenticated Study Task Undo/Redo HTTP resources backed only by recorded allowlisted inverses and the atomic Level 2 audit boundary. It enforces terminal-run ownership, cross-run denial, run-scoped semantic idempotency, 64 KiB declared/chunked limits, durable post-terminal events and restart recovery for step-only, running-invocation and committed-before-event crash windows. The full Python suite passed 577/577, Ruff lint/format passed 117 files, and final independent review found no remaining P0/P1. Gate 3 remains in progress because real provider configuration, visible Agent Activity/Undo, additional tool groups and kill-restart/socket E2E remain open.
- 2026-07-16: The Gate 3 visible-runtime slice added strict Undo/Redo client contracts, post-terminal audit replay, a bounded public activity reducer, app-level run lifecycle with explicit create/cancel, Last-Event-ID and token-rotation recovery, terminal-only visible Undo/Redo, and a real Home Agent composer using Ask/Teach/Study/Review/Plan. Browser Demo remains request-free, waiting approval is read-only, and tool results/hidden reasoning are not retained by the activity model. Focused tests passed API client 26/26, reducer 8/8, panel 14/14, runtime 9/9 and Home 5/5; desktop ESLint, strict typecheck, production build and all 170/170 Vitest tests passed. The 1440×920 current Home capture completed as `missing_reference`; no lifecycle socket E2E, authorized visual reference or parity result is claimed, so Gate 3 remains in progress.
- 2026-07-16: The Gate 3 local-provider slice automatically adapts an existing configured loopback Ollama/OpenAI-compatible chat model into a real text-only Agent provider, while preserving `provider_missing` with no configuration and explicit test-provider precedence. It emits only bounded public text plus a completion action after the guarded transport's real terminal marker and non-empty user-facing output; it exposes no model-selected tools, versions durable run metadata with both configured model revision and adapter prompt protocol (using a deterministic SHA-256 fingerprint when the revision would exceed the database bound), and fails with a stable safe recovery error—without blank content or `done`—on empty/transport-error or common split hidden-reasoning output. The full Python suite passed 588/588 with one existing Starlette warning; Ruff lint/format passed all 119 learning-core Python files and `git diff --check` passed. This does not implement the provider↔tool-result multi-turn protocol, approval execution, or kill-restart/socket E2E, so Gate 3 remains in progress.
- 2026-07-16: The Gate 3 socket-recovery slice added a Unix-only test helper, not a production provider, and exercised a real Uvicorn listener on a random loopback port. It created a real Agent run, consumed and saved a partial durable SSE cursor, SIGKILLed the isolated server process group, restarted the same database with a new token, rejected the old token, recovered the run as `interrupted/process_restarted`, replayed only the two recovery events after Last-Event-ID, and proved a third startup adds no duplicate recovery events. The focused socket test passed repeatedly, the socket/API subset passed 23/23, and the full Python suite passed 589/589 with one existing Starlette warning; Ruff lint/format passed all 121 learning-core Python files and `git diff --check` passed. This verifies the Python socket/auth/SQLite crash boundary but not automatic Tauri supervisor relaunch or packaged GUI lifecycle, so Gate 3 remains in progress.
- 2026-07-16: The Gate 3 multi-turn protocol slice added provider-private, durable-first tool-result feedback without exposing it as a public event. Registered tools now require recursively closed strict result models; validated fresh results use `untrusted_tool_data/full`, replay uses only `audit_summary`, and neither path includes mutation before/after/undo. Tests prove a final answer waits for real feedback, two sequential calls remain correlated, raw private text stays absent from SSE, replay fidelity is explicit, a provider without feedback support cannot execute a tool, cancellation cleanup remains bounded even for a hostile provider, and cumulative tool-round limits stop before the next side effect. Production read-list results pass the strict executor boundary. A repeated provider `call_id` with identical arguments executes once, returns private full→audit-summary feedback and emits only one public result; changed arguments fail without re-execution. Deterministic tool-event IDs and startup reconciliation recover a committed Level 2 mutation whose public events were not yet published, then mark its run interrupted without duplicate events. The full Python suite passed 621/621 with one existing Starlette warning; Ruff lint/format passed all 122 learning-core Python files and `git diff --check` passed. The current loopback LocalChat adapter remains text-only; production tool selection, run-derived course/session scope, recoverable tool-error feedback and Level 3 approval remain open, so Gate 3 is not complete.
- 2026-07-16: Gate 3 provider hardening changed the app runtime from an implicit full-registry execution surface to a production-default empty tool allowlist. Only the exact in-process `FixedAutomationProvider` test fixture can exercise registered tools; another feedback-capable provider requesting `complete_study_task` is rejected before a public `tool_start`, audit reservation or domain mutation. The text chat transports now also require normal termination (`finish_reason=stop` plus `[DONE]` for OpenAI-compatible, `done_reason=stop` plus `done=true` for Ollama) and reject missing, duplicate, length-limited or otherwise non-normal stop reasons. Focused provider/API tests passed 30/30; the full Python suite passed 623/623 with one existing Starlette warning; Ruff lint/format passed all 122 files and `git diff --check` passed. A production catalog must still use the same closed allowlist as execution, inject trusted course/time scope, and persist enough scope evidence for audit before LocalChat may receive read tools.
- 2026-07-17: Gate 3 migration 019 added immutable `agent_runs.course_scope_id` audit evidence. Creation and idempotent replay resolve it only from persisted study-session/conversation relationships, reject missing or conflicting contexts with stable `ValueError`, and ignore forged scope values in input/provider text. Historical runs backfill session-first then conversation; existing `ON DELETE SET NULL` can detach either/both live contexts while retaining the historical course scope, and the course itself remains `RESTRICT` protected. The first trigger version incorrectly blocked context deletion; independent Codex acceptance found the P1, the update trigger and conversation-only/session-only/both migration tests were corrected, and acceptance then found no remaining P0/P1. The full Python suite passed 628/628 with one existing Starlette warning; Ruff lint/format passed all 123 files and `git diff --check` passed. LocalChat remains text-only and the production runtime remains zero-tool: catalog/allowlist/read-only registry unification plus host-injected fixed run time/course arguments are still open.
- 2026-07-17: Gate 3 connected configured loopback Ollama/OpenAI-compatible models to a bounded structured multi-round protocol. A single registry-derived capability now supplies the provider catalog, execution allowlist and executor; production exposes only `list_study_feed` and `list_due_reviews`, whose public schemas contain only `limit`, while trusted persisted course scope and the immutable run creation time are constructor-bound by the host. Strict full-response parsers reject duplicate JSON keys, non-finite values, hidden reasoning, unknown models/tools, mixed or parallel tool calls and malformed terminal states; response/history/tool-round budgets and private durable-first feedback remain bounded. Concrete API tests exercise tool call → real SQLite result → final answer, prove raw review text stays out of public SSE, and prove Level 2/3 tools cannot start or mutate state. Wire-level tool rounds currently use non-streaming JSON, while public Agent actions and final content still use durable SSE. Initial Sol acceptance identified four P1 issues in cancellation cleanup, fixture subtype trust, capability pairing/deep immutability and due-review query bounds; all four were fixed with adversarial tests, and final Sol re-audit found no open P0/P1. The final full Python suite passed 768/768 with one existing Starlette warning; Ruff lint/format passed all 129 files and `git diff --check` passed. ContextDelta `2e206888…`, Spark Agent `f21158df…` and Vera `5611699e…` were reviewed only at exact revisions; no third-party source or dependency was incorporated. Approval UI, recoverable provider tool-error feedback, packaged GUI/provider E2E, and HyperKnow visual parity remain open, so Gate 3 is not complete.
- 2026-07-17: Gate 3 added `search_course_knowledge` as the third production Level 1 tool by reusing Keen's existing `DocumentRepository.search` → Latin/CJK FTS path; no dependency or parallel search engine was added. The provider can supply only an NFKC-normalized searchable query of at most 512 characters and limit 1–5; persisted run scope is constructor-bound. Results truthfully declare `lexical_only`, include bounded chunk/document/page/section provenance, mark source text `untrusted_course_data`, cap excerpts at 1,200 characters each and 6,000 total, and explicitly mark text/section truncation and `has_more`. The connection is `query_only`; FTS runs off-loop with SQLite progress interruption and connection closure on cancellation. Tests cover all non-indexed states, cross-course and shared-metadata leakage, malformed metadata, forged provider scope/path, unscoped zero-tool behavior, write rejection, cancellation, prompt-injection-shaped source data, private tool feedback, public SSE/audit redaction, and zero mutations. A concrete Ollama two-round API run retrieved the current course source then produced the final answer. Final Sol review found no open P0/P1; focused acceptance passed 91/91, the full Python suite passed 781/781 with one existing Starlette warning, and Ruff lint/format plus `git diff --check` passed. This is lexical retrieval only; hybrid Agent retrieval, recoverable tool errors, approval execution and full citation UI integration remain open.
- 2026-07-17: Gate 3 added bounded provider-private recovery for safe failures of the trusted Level 1 read runtime. Argument validation returns only `invalid_arguments`; explicitly classified SQLite BUSY/LOCKED reads return only `temporary_read_failure`. Cancellation, permission/Level 2/3, output-contract, provider-protocol and uncertain-audit failures remain terminal. The failed step and redacted public `tool_result` are committed atomically before any private OpenAI/Ollama `role=tool` error feedback; feedback remains subject to the existing round/byte caps plus a four-error total and one-identical-failure cap. Concrete Ollama API coverage proves an invalid scoped knowledge call can be corrected with a new call ID, retrieve real current-course data and finish in the same run without public source/path/SQL/exception leakage or mutation. The frontend validates failed-tool events and settles unfinished attempts on terminal run states instead of leaving them running. The full Python suite passed 797/797 with one existing Starlette warning; desktop lint, strict typecheck, production build and 178/178 Vitest tests passed; Ruff lint/format, compileall and `git diff --check` passed. Final Sol re-review found no remaining P0/P1/P2. No dependency or third-party source was added. Approval execution, hybrid Agent retrieval, packaged GUI/provider E2E and visual parity remain open, so Gate 3 is not complete.
- 2026-07-17: Gate 3 now includes one closed Level 2 proposal/approval path for `complete_study_task`. Migration 020 stores immutable canonical host arguments separately from public summaries; provider schemas omit course/time; confirmation performs the task write, execution audit, reversible mutation, approval resolution and terminal events in one SQLite transaction. Reject, cancel, stale revision and restart fail closed with no domain mutation; same-key confirmation replays without a second write; the existing Undo resource reverses a confirmed completion. Invalid proposals are durably recorded with only `invalid_arguments` before private correction feedback. The Home activity panel exposes an offline-aware, single-flight Confirm/Reject card, reuses its idempotency key when the HTTP outcome is unknown, and treats a conflicting resolution as non-retryable pending an activity refresh. The full Python suite passed 811/811 with one existing Starlette warning; desktop ESLint, strict typecheck, production build and 191/191 Vitest tests passed. Ruff lint/format, compileall and `git diff --check` passed, and final independent Sol review found no remaining P0/P1/P2. The visual harness ran at 1440×920 and still reported `missing_reference`, so no parity result exists. This verifies only the one local task-completion action; broader Level 2 domains, Level 3 actions, packaged GUI/provider E2E, hybrid Agent retrieval and the full learning loop remain open.
- 2026-07-17: The first real course-setup slice added migration 021, authenticated idempotent `POST /v1/courses`, strict Pydantic/Zod request and response contracts, and a live Knowledge Base creation form. NFKC/whitespace/case title identity is checked against both legacy and new rows under `BEGIN IMMEDIATE`; legacy duplicate titles remain unchanged, identical retries replay, and conflicting title/key requests create no new row. The UI is single-flight, aborts on unmount, keeps Browser Demo request-free, isolates caches by sidecar generation, and selects a confirmed course for the next import. Full local validation passed Python 820/820 with one existing Starlette warning, desktop 205/205 and Rust 38/38 plus Ruff lint/format, compileall, migration/sidecar preflight, ESLint, strict typecheck, production build and `git diff --check`. The new GitHub Actions workflow has not run remotely yet; its macOS package job is manual-only and is not release/signing/notarization evidence. No dependency or third-party source was added. Real concept creation, source-to-plan orchestration, assessment/Review UI, packaged GUI E2E and visual acceptance remain open.
- 2026-07-17: Autonomous-learning foundation A added an indexed-course-document bootstrap and a read-only Learning Snapshot without adding a migration, runtime, database or algorithm. Bootstrap uses safe persisted section/display metadata to create one deterministic concept and a zero-attempt BKT prior under a write lock; it creates no evidence/event and never labels existing mastery as newly initialized. Snapshot reads due Review, incomplete Study Session, mastery gaps/states, actionable misconceptions and pending tasks from one SQLite snapshot, then applies fixed product tiers and the existing versioned feed-priority score. It explicitly exposes missing mastery and never manufactures a probability. Full Python validation passed 838/838 with one existing Starlette warning; Ruff lint/format, compileall and `git diff --check` passed. Independent Sol acceptance found no remaining P0/P1/P2. No API, UI, autonomous execution, package rebuild or visual result is claimed yet, and no dependency or upstream source was added.
- 2026-07-17: Autonomous-learning foundation B added a deterministic coordinator that atomically composes optional concept bootstrap, Learning Snapshot observation, active real-target coverage and ordinary Study Task persistence. It stores complete Feed-priority provenance and bounded real titles/reasons, distinguishes coordinator replay from coverage by a manual or legacy task, and uses one write lock so same-day and cross-midnight concurrent observers cannot create two active recommendations. Failure rolls back both bootstrap and task state. Full Python validation passed 852/852 with one existing Starlette warning; the focused coordinator/Snapshot/bootstrap/Feed suite passed 50/50; Ruff lint/format, compileall and `git diff --check` passed. Independent Sol acceptance found no remaining P0/P1/P2. API exposure, desktop rendering, recommended-action execution, packaged E2E and visual evidence remain open; no dependency or upstream source was added.
- 2026-07-17: Autonomous-learning foundation C exposed authenticated read/observe resources at `GET /v1/learning-snapshot` and `POST /v1/autonomous-recommendations`. Both use strict snake_case response models and server-owned UTC time; the POST is inside the 64 KiB streaming body guard and returns a same-transaction post-write Snapshot. Compatibility tests cover manual/legacy high priority, same-day completed replay, missing courses, cross-course documents, finite numeric evidence, and historical date-only/naive UTC task timestamps without weakening the client timestamp contract. Read and potentially durable write failures use distinct redacted recovery envelopes. Focused Python validation passed 56/56; Ruff lint/format and `git diff --check` passed; final independent Sol acceptance found P0/P1/P2 all zero. The desktop client/UI, Start action, packaged E2E and visual evidence remain open in this backend slice.
- 2026-07-17: Autonomous-learning foundation D added migration 022 and a transactionally idempotent task-to-session coordinator. `study_sessions.originating_task_id` is nullable for old/manual sessions but unique when present, FK-protected, and guarded in both task and session course-update directions. An active coordinator task either resumes its real incomplete source session, resumes its unique originating session, or creates one `goal_confirmation` session and two bounded units citing only current-version indexed chunks linked to the same course. A single chunk is deterministically divided into two non-empty original-text parts; insufficient source blocks with zero writes. Cross-course results omit the foreign task, terminal sessions do not masquerade as resumable, and no mastery/evidence/answer/completion is created. The combined focused migration/session/state suite passed 34/34; Ruff lint/format and `git diff --check` passed; final Sol acceptance found P0/P1/P2 all zero. Start-session HTTP/UI, assessment progression, Review scheduling, packaged E2E and visual evidence remain open.
- 2026-07-17: Autonomous-learning foundation E added authenticated `POST /v1/autonomous-study-sessions` with strict input, server-owned UTC, the 64 KiB authenticated streaming guard, and closed `session_created`/`resumed`/`blocked` results. Before serialization, the router verifies the request course/task and all task/session/plan identities; the service independently rejects a corrupted cross-course originating session. Real tests drop the consistency trigger and corrupt local state to prove a redacted 503 without foreign title/goal/task leakage, and cover unknown durable writes, legacy UTC normalization, malformed timestamps/internal JSON, 201/200 semantics and all eight blocked reasons. Candidate snapshots additionally expose nullable concept linkage for strict downstream misconception attribution. Final Sol acceptance found P0/P1/P2 all zero; focused API/service, recommendation-inclusive and migration-inclusive suites passed 18/18, 40/40 and 33/33. Ruff lint/format and `git diff --check` passed. Desktop Start/Resume, session progression through assessment, Review scheduling, packaged E2E and visual evidence remain open.
- 2026-07-17: Autonomous-learning desktop slice now gives the live Learning Feed a strict Zod client for Snapshot and recommendation responses, course and available-minutes selection, visible candidates and persisted task outcomes, and a single-flight `Plan next local action` request. Loading, empty, error, offline, cancelled and unknown-outcome reconciliation states are explicit; request scope, cache keys and late responses are isolated by course, budget and sidecar generation. The live Home no longer presents seeded Feed/statistics as current learner data, while Browser Demo remains request-free and labels its sample values. Strict response checks bind task/candidate/source/concept relationships and recommendation result scope before rendering. Focused desktop tests passed 64/64, all desktop tests passed 216/216, and strict typecheck, ESLint and production build passed; focused Python Snapshot/recommendation tests passed 30/30. Final independent Sol acceptance found P0/P1/P2 all zero. No screenshot, visual-diff or accessibility evidence was produced, so this is not a visual-parity claim. The desktop Start/Resume control is not implemented, Deep Learn still renders its hard-coded demo, and a real session reader remains in progress.
- 2026-07-17: Autonomous-learning foundation F implements the persisted Study Session reader and the first real Feed-to-Deep-Learn execution path. A selected active Study Task can Start/Resume through the authenticated session boundary, then Deep Learn renders the persisted plan and its bounded source citations after strict desktop source-ID validation. Reader-focused validation passed 42/42 and independent Sol acceptance found P0/P1/P2 all zero; source-ID contract validation passed 62/62. Desktop focused validation passed 69/69, the full desktop suite passed 226/226, and strict typecheck, ESLint and production build passed; final desktop Sol acceptance found P0/P1/P2 all zero. The final Python suite passed 905/905 with Ruff lint/format passing; Rust formatting, Clippy with warnings denied, and 38/38 tests passed. This is a read-only Deep Learn slice: it does not persist progress, answers, mastery evidence, task completion, or FSRS changes. Browser Demo stays explicitly sample-only and sends no requests. No screenshot, visual-diff, accessibility run, packaged E2E, or HyperKnow-parity result exists. Assessment, mastery/misconception progression and FSRS Review progression remain in progress.
- 2026-07-17: Autonomous-learning foundation G adds forward migration 023 and authenticated diagnostic begin/read/answer routes, moving a source-grounded Study Session from goal confirmation through a recoverable reflection into its first active unit. The reflection stores only immutable zero-weight `user_report` evidence: its self-assessment is preserved as reported, explicitly not scored, and does not change mastery, attempts, Review/FSRS state, task completion or unit completion. Begin and answer are independently idempotent, transactionally restart-safe, course-scoped and guarded before body parsing with the existing 64 KiB limit. Paused sessions restore the effective diagnostic phase, unknown write outcomes reconcile through the read route, answered evidence and its unit-concept relationship are frozen and revalidated, and concurrent answers converge on one evidence/event. A real schema 22-to-23 upgrade preserves legacy answered checkpoints and passes SQLite integrity/foreign-key checks. Focused final review passed 70/70 with P0/P1/P2 all zero; the complete Python suite passed 935/935 with one existing Starlette warning, and Ruff lint/format plus `git diff --check` passed. The desktop diagnostic interaction is still open in this backend slice; no visual or autonomous mastery-progression claim is made. No dependency or third-party source was added.
- 2026-07-17: Autonomous-learning foundation H connects the live Deep Learn route to the persisted opening diagnostic. Strict Zod contracts bind each response to its course, session, first plan unit, checkpoint and unique active unit; Browser Demo remains request-free. Live sessions restore `not_started`, `pending` or `answered`, hide locked unit content and concept metadata until the diagnostic completes, and keep every paused phase read-only. Begin and answer are single-flight and cancellable; unknown outcomes reconcile through GET and retain the exact key, revision and answer payload for an edit-locked retry, while a known 409 discards the rejected intent and requires a successful authoritative read before another write. The UI labels the reflection as unscored and non-mastery-changing, caps input at the API's 8,000-character boundary, and does not fabricate feedback. Final independent Sol acceptance found P0/P1/P2 all zero. Desktop validation passed 16 files / 246 tests, strict typecheck, ESLint and production build; the diagnostic-focused subset passed 26/26. No screenshot, visual-diff, accessibility audit or packaged-app E2E was produced, so visual quality and HyperKnow parity remain unverified. No dependency or third-party source was added.
- 2026-07-18: Autonomous-learning foundation I adds the Python domain core for the first real active-recall observation, without yet exposing HTTP or desktop controls. A pure versioned generator derives one fill-blank item only from text still present in the unit's cited course chunk; the hidden accepted answer remains in the immutable published assessment and is removed from every public session/plan/unit/run projection. Forward migration 024 binds one run to the exact course/session/unit/checkpoint/assessment/item/concept/source graph, snapshots prior mastery attempts, permits exactly one attempt and evidence application, and freezes the deterministic scoring chain. Answering atomically performs objective grading, positive-weight `active_recall` evidence and concept-parameter weighted BKT, advances to `practicing`, and leaves FSRS untouched; exact retries and concurrent writers converge. Pending work can pause/resume, while session cancellation/failure atomically records a cancelled run and skipped checkpoint with no learner evidence. Answered history remains readable in later study phases. Request-time timestamps are coherent across the graph. Final independent Sol acceptance found P0/P1/P2 all zero; its focused suite passed 58/58, the complete Python suite passed 978/978 with one existing Starlette warning, and Ruff lint/format plus `git diff --check` passed. Authenticated routes, strict TypeScript contracts, desktop interaction, screenshots, accessibility, packaging and visual parity remain open. No dependency or third-party source was added.
- 2026-07-18: Autonomous-learning foundation J exposes the active-recall core through authenticated GET/begin/answer Study Session routes and strict snake_case Pydantic contracts. Authentication precedes path/query/body validation and both dynamic POST resources use the existing streamed 64 KiB guard. The HTTP projection independently revalidates course/session/plan/current-unit/run/checkpoint/grade relationships, normalizes stored UTC timestamps and removes source text/IDs, concept/assessment/item IDs, answer keys, raw learner responses and idempotency proofs. Missing and cross-course resources are indistinguishable 404s; known state/revision/payload conflicts are 409; read failures and potentially durable unknown write outcomes are separate redacted 503s. Begin uses 201 only when applied and 200 on replay; answer updates an existing run and returns 200 for applied or replay, including exact cancelled-begin reconciliation. Final independent Sol acceptance found P0/P1/P2 all zero; the HTTP acceptance subset passed 35/35, the complete Python suite passed 982/982 with one existing Starlette warning, and Ruff lint/format plus `git diff --check` passed. TypeScript contracts, desktop rendering, screenshots, accessibility, packaged E2E and visual parity remain open. No dependency or third-party source was added.
- 2026-07-18: Autonomous-learning foundation K connects the active-recall HTTP core to a strict TypeScript/Zod client and the live Deep Learn route. GET/begin/answer validate course/session/run scope and action-specific HTTP/state semantics; response schemas reject extra fields and never accept answer keys, raw learner responses, source/concept/assessment/item identities or idempotency evidence. Deep Learn restores before enabling actions and conservatively hides lesson text, unit/session labels, goals, concepts, source controls and the global Inspector before a pending/unresolved prompt can paint. The lock is scoped to course, session and sidecar generation. Begin/answer are single-flight and cancellable; a potentially durable unknown outcome is reconciled by GET and can only retry the frozen key, revision, run and response, while known 409/4xx states clear stale controls if authoritative recovery fails. Paused sessions first restore the opening diagnostic and then the applicable read-only active-recall state; answered copy explicitly reports that no Review schedule changed. Browser Demo remains request-free. Final independent Sol acceptance found P0/P1/P2 all zero. Focused validation passed 32/32, the complete desktop suite passed 259/259, and strict typecheck, ESLint, production build and `git diff --check` passed. No screenshot, accessibility audit, packaged-app E2E, dependency, third-party source or visual-parity result was added.
- 2026-07-18: Autonomous-learning foundation L adds deterministic targeted practice after active recall. The versioned generator derives a distinct accepted answer only from source text still present in the cited course chunk and excludes the active-recall answer. Forward migration 025 persists a sealed practice ledger bound to the course/session/unit, content fingerprint and answer-key fingerprint; one answer atomically creates one objective attempt/evaluation and one positive practice-weighted BKT evidence/event, with no Review or FSRS write. Authenticated strict-Pydantic GET/begin/answer routes authenticate and apply the streamed 64 KiB body cap before validation, preserve course scope, distinguish replay from a new begin and allow late exact replay after the terminal transition. The focused targeted-practice/active-recall/migration suite passed 108/108; the full Python suite passed 1013/1013 with one existing Starlette/httpx deprecation warning; Ruff lint/format and `git diff --check` passed; final independent Sol acceptance found P0/P1/P2 all zero. TypeScript/UI client, summary, Review scheduling/FSRS handoff, screenshots, accessibility, packaged E2E and visual parity remain not started/open. No dependency or third-party source was added.
- 2026-07-18: Autonomous-learning foundation M connects targeted practice to the strict TypeScript/Zod client and live Deep Learn route. GET/begin/answer reject extra or private fields, bind course/session/run/checkpoint relationships and preserve 201/200/200 action semantics, including cancelled-before-begin, paused recovery and cross-unit late replay. After Active Recall is answered, Deep Learn restores practice before unlocking source-derived header, navigation, lesson, concepts or Inspector state; pending and unresolved prompts remain protected before paint. Writes are single-flight and cancellable; unknown results reconcile through GET and retain the exact key, revision, run and response, while 409/4xx responses cannot revive stale controls. Paused and terminal copy distinguishes a real run from practice that never began, and answered copy states that one practice mastery observation was recorded without claiming a Review/FSRS schedule change. Final independent Sol acceptance found P0/P1/P2 all zero. The targeted-practice subset passed 11/11; the complete desktop suite passed 270/270; strict typecheck, ESLint, production build and `git diff --check` passed. Browser Demo remains request-free. No screenshot, accessibility audit, packaged-app E2E, dependency, third-party source or visual-parity result was added. Summary and Review scheduling/FSRS handoff remain open.
- 2026-07-18: Autonomous-learning foundation N adds the first runnable summary-to-Review framework for the implemented one-unit path. Forward migration 026 freezes a redacted recap and the exact answered-practice-to-review lineage while `ReviewRepository` creates one real `fsrs-6.3.1-keen-v1` card/schedule. Finalization is one course-scoped, authenticated, 64 KiB-bounded and idempotent transaction that creates the schedule, snapshots its original due state, completes the current active unit and session, and resolves the originating local task without another mastery/BKT write. Exact retries replay and different commands conflict; the public contract omits prompts, answers, source text, concept/assessment/item/review identities and the current-unit pointer. The live Deep Learn client restores a dedicated safe projection, protects source-derived UI during summary, and reconciles unknown writes before an exact-key retry. Focused Python validation passed 32/32 and the complete Python suite passed 1017/1017 with one existing Starlette/httpx deprecation warning; the complete desktop suite passed 278/278 with strict typecheck, ESLint and production build passing. Ruff lint/format and `git diff --check` passed. A 1280×760 Browser Demo shell capture exists only for UI discussion and does not verify the live persisted summary. Multi-unit progression, direct task-completion Undo, live-summary screenshot/accessibility coverage, packaged E2E and visual parity remain open. No dependency or third-party source was added.
- 2026-07-18: A focused current-product UI audit covered the runnable Home, Learning Feed, Deep Learn and Summary Browser Demo path before implementation work continued. It corrected Deep Learn header/content shrink behavior, replaced the semantically wrong Summary recall card with a clearly illustrative no-write handoff, made Demo Pause suspend learning controls, cleared transient recall state on unit changes, kept Learning Feed rationale actions intact, and added programmatic selected/current states to Home modes, segmented filters and unit navigation. The before/after captures under `artifacts/ui-audit/2026-07-18/` are visible Browser Demo evidence only; they are not authorized-reference inputs, a visual diff, live persisted-session evidence, an accessibility scan or packaged `.app` evidence. Focused interaction validation passed 42/42; the complete desktop suite passed 280/280, and strict typecheck, ESLint, production build and `git diff --check` passed. The build retained the existing Rollup chunk-size warning. HyperKnow parity, fixed supported-window capture, accessibility automation and broader page/state coverage remain open.
- 2026-07-18: The first authorization-backed HyperKnow benchmark captured and inventoried the Home composer, Learning Feed/calendar, and Deep Learn composer-entry states for internal research. The references showed two useful structural patterns: preserve a full-width primary workspace until contextual inspection is requested, and select Deep Learn as an intent before creating external work. Keen now defaults the Inspector closed and provides a `New study session` Sidebar action that opens Home in a mode-specific Study state without creating a session. Current Keen before/after captures and a side-by-side qualitative comparison are stored under `artifacts/ui-audit/2026-07-18/hyperknow-benchmark/`. The reference crops deliberately exclude personal/user-created sidebar content; no prompt was submitted and no external session or calendar write occurred. Focused validation passed 16/16 with strict typecheck and ESLint; the complete desktop suite passed 281/281, production build and `git diff --check` passed, with the existing Rollup chunk-size warning. This is not a pixel-parity result: the viewports/crops differ and no fixed-seed visual diff, accessibility run or packaged-app validation was performed.
- 2026-07-18: The authorized HyperKnow UI study received a Keen-branded implementation pass across Home, Learning Feed/calendar and Deep Learn entry. The primary Sidebar was reduced to Home, Learning Feed, Knowledge Base and one study-session action; seeded recents are no longer presented as navigation. Home now follows the captured centered-composer and lower learning-list structure while retaining truthful Demo/local disclosures. Learning Feed now renders the existing task/recommendation behavior in a responsive task rail plus real month calendar without adding a calendar write. Shared tokens, controls, Conversation and Deep Learn reading surfaces were tightened for contrast, focus, state and 1180×740 behavior. Strict typecheck and ESLint passed; the complete desktop suite passed 281/281; production build and `git diff --check` passed with the existing Rollup chunk warning. Focused Playwright DOM/keyboard checks at 1180×740 found no document/page horizontal overflow, duplicate IDs or unnamed focusable controls on Home, Feed, Study entry, Conversation or Demo Deep Learn, and reduced motion collapsed transitions to `0.00001s`. Current captures are under `artifacts/visual-diff/current/` and `artifacts/ui-audit/2026-07-18/keen-ui-refresh/`. The three visual results remain `missing_reference`, so no mismatch percentage or pixel-parity claim exists; packaged-app validation and a complete accessibility audit were not run.
- 2026-07-18: A second UI-only polish pass closed three review findings without changing the learning-core or persistence boundary. Home now uses the `Home` toolbar label and a height-sensitive first-view layout that keeps all three task rows visible at 1180×740. Learning Feed calendar events are real focusable controls linked to their existing task card; selecting an event switches the Demo status filter when required, scrolls the matching card into view and exposes selected state with `aria-pressed`/`aria-current`, but performs no calendar write or task mutation. Semantic canvas, reading, overlay, progress and status-soft tokens replace targeted hard-coded light surfaces and let an unset/system theme follow macOS dark appearance; tested dark token combinations are at least 5.42:1 across the primary dark surfaces. Browser QA at 1180×740 found no horizontal document overflow, duplicate IDs, unnamed focusables or console errors on the inspected Home/Feed states, showed all three Home rows in the first viewport, confirmed calendar-to-task selection, and measured reduced-motion transitions at `0.00001s`. Light/dark screenshots are under `artifacts/ui-audit/2026-07-18/keen-ui-refresh-2/`. Strict typecheck and ESLint passed, all 282 desktop tests passed, production build and `git diff --check` passed with the existing Rollup chunk-size warning. The visual harness again returned three `missing_reference` states; automated Browser Tab injection was unsupported in this control session, so the prior Playwright keyboard evidence was not upgraded to a complete accessibility claim. Packaged-app validation and pixel parity remain open.
- 2026-07-18: A third UI-only refinement responds to the review that the workspace still felt like a generic AI assistant. The default Home state is now a `Today` learning workspace: the task queue and five concrete study tools appear before any input, while a compact workbench is revealed only after the learner chooses Ask, Teach, Study, Review or Plan. The idle Agent response panel, mascot treatment, prompt-card grid, floating service badge and nonfunctional attachment/voice controls were removed from the default state. Existing live run creation/cancellation, Demo session-only behavior, task navigation and provider/service failure handling remain unchanged. Learning Feed now uses scheduling/task language and utilitarian icons instead of sparkle, Agent and recommendation framing; this is a presentation change, not a new planning or calendar capability. Browser QA at 1180×740 found zero default Home textboxes, all three sample tasks and five study tools visible, no horizontal document overflow, duplicate IDs, unnamed focusables or console errors on the inspected Home/Feed states. Screenshots are under `artifacts/ui-audit/2026-07-18/keen-ui-workspace/`. Strict typecheck and ESLint passed, all 282 desktop tests passed, production build and `git diff --check` passed with the existing Rollup chunk-size warning. The visual harness returned three `missing_reference` states. This pass deliberately diverges from the captured HyperKnow centered-composer structure after user feedback; no parity, packaged-app or complete accessibility claim is made.
- 2026-07-18: A fourth UI-only refinement makes task inspection and action the primary Learning Feed workflow without adding a task-detail route, API field or backend behavior. Selecting a task replaces the calendar with a bounded detail workspace assembled only from validated Demo, authenticated fallback or autonomous task data. It presents the stored reason as the learning goal, real due/estimate/state fields, an explicitly expected workflow rather than fabricated unit progress, available evidence, and one next-action area. Demo snooze/completion remains in-memory and labeled Sample; authenticated fallback tasks expose no start action; persisted autonomous tasks keep the existing confirmed Start/Resume, cancellation and uncertain-result recovery logic. Card-level mastery and mutation controls moved into the detail context. The panel focuses its heading on entry, returns focus to the originating card on close and announces completed Demo feedback. Browser screenshots at 1000×720, 1180×740 and 1440×920 are under `artifacts/ui-audit/2026-07-18/keen-task-detail/`; inspection found no unnamed buttons, unlabeled form fields or duplicate detail-title IDs. The 1000×720 pass identified and fixed a footer-height and narrow-copy problem. Strict typecheck and ESLint passed, all 282 desktop tests passed, production build and `git diff --check` passed with the existing Rollup chunk-size warning. The visual harness returned three `missing_reference` states. Browser Tab injection did not move focus reliably, so component focus tests are the current keyboard evidence and no complete accessibility, packaged-app or parity claim is made.
- 2026-07-18: User review selected the earlier light Keen desktop style over an uncommitted enterprise-dashboard experiment. The rejected dark navigation, saturated dashboard-blue actions, heavier panel framing and Toolbar search treatment were removed without rolling back the task-first Home, inline task detail, local-service boundaries or any backend behavior. Browser Demo Home and Feed were recaptured at 1180×740; `design-qa.md` records the source, full comparison, focused Feed comparison and `final result: passed`. Strict typecheck, ESLint, 26 files / 282 desktop tests, production build and `git diff --check` passed. The visual harness still reports three `missing_reference` results, so no pixel mismatch or parity claim is made; packaged-app validation was not run.
- 2026-07-19: Began the user-approved HyperKnow-layout return as a bounded UI-only pass. The primary Sidebar remains Home, Learning Feed and Knowledge Base plus one study entry; Home now uses the referenced centered request workbench with only Keen's existing Ask/Study modes and a lower learning queue; Learning Feed retains real/sample task behavior in a tighter rail-plus-calendar layout. No backend, route, provider, ingestion, persistence or calendar-write capability was added. Browser captures cover the inspected default states at 1462×907, 1180×760 and 900×700 under `artifacts/ui-audit/2026-07-19/`; keyboard focus and compact breakpoint behavior were checked and the browser console returned no errors. Frontend lint, strict typecheck, 26 files / 282 tests and production build passed. The visual harness captured all three configured pages but reported three `missing_reference` results, so no mismatch percentage, pixel match, packaged-app or complete accessibility claim is made.
- 2026-07-19: Added an internal Figma comparison checkpoint without changing runtime behavior. Authorized HyperKnow Home and Learning Feed screenshots were reconstructed as local HTML and converted to editable raw Figma frames (`ugwiIPdF43v2woYsLM3b9R`, nodes `7:2` and `8:2`). A product-first Keen alternative, nodes `9:2` and `10:2`, retains the current Sidebar and truthful sample/local/provider/index boundaries while replacing the default assistant prompt and elevated card stack with a task-first Today workspace, plain task rows and a flat month grid. Source studies live under `artifacts/figma/hyperknow-html-reference/`; side-by-side comparisons live under `artifacts/figma/comparisons/`. The frames are not yet design-system instances and no code from AppFlowy, SiYuan, Super Productivity, Khoj or another benchmark was incorporated. Native Figma variables, reusable state variants, motion prototypes, accessibility checks and implementation selection remain open; no pixel-parity claim is made.
- 2026-07-19: A read-only Figma checkpoint audit re-rendered the two internal reference reconstructions and two Keen proposals at 1728×907. The resulting report and comparisons are under `artifacts/ui-audit/2026-07-19/figma-check/`. The proposal passes the intended task-first direction, truthful capability boundaries and low-card visual organization, but remains blocked for implementation selection by raw non-componentized frames, missing focus/state coverage, small-text contrast failures, fixed-width layout, absent dark variant and unrepresented motion. The deterministic detector's only advisory was a false positive on calendar dates. No runtime source, backend capability or dependency changed, and no visual-parity or accessibility pass is claimed.
- 2026-07-19: Promoted Figma from a component/research checkpoint to a page-level UI baseline for the current runnable product. The live Browser Demo Home, Learning Feed and Deep Learn pages were converted to editable raw frames on `07 · Product Screens` in file `ugwiIPdF43v2woYsLM3b9R`: Home `64:2`, Learning Feed `66:2`, and Deep Learn `65:2`. Local render evidence is stored under `artifacts/figma/page-baselines/`. In code, Home now presents the learning queue and explicit Demo/local-service boundary before the existing request surface; control sizing and small-label legibility were tightened across the core UI without changing Tauri, React routing, learning-core APIs, SQLite, authentication, provider behavior or persistence. Browser checks at 1280×720 found no horizontal overflow on all three inspected pages and no application error; only the existing React Router future warnings remained. ESLint, strict typecheck, 26 files / 283 desktop tests, production build, Impeccable detection and `git diff --check` passed, with the existing Vite chunk-size warning. The Figma captures remain raw page frames rather than token-bound reusable instances, the visual harness still lacks accepted references, and no pixel-parity, packaged-app or complete accessibility claim is made.
- 2026-07-19: Completed Phase 0 of the user-requested competitor-operation → Figma componentization → React implementation workflow without mutating Figma or runtime UI. The authenticated HyperKnow audit retained 21 sanitized states at a 1585×851 CSS viewport, including the full synthetic upload/processing/completion path, settings and integration-not-connected states, Deep Learn progress/locked/long-reading states, review-plan continuity and a loaded source-preview panel. Evidence and privacy deletions are documented in `references/hyperknow/2026-07-19-figma-screen-audit/README.md`. Phase 1 is in progress only after explicit user approval: reconcile code/Figma typography and Button geometry, build local component coverage for navigation, path/progress, menus/popovers, calendar, file tiles, reading/citation and request-bar states, then reconstruct selected screens. No code implementation, responsive/accessibility pass, accepted baseline, visual-diff percentage or pixel-parity claim was added by this audit.
- 2026-07-19: Completed the bounded Figma-only foundations portion of Phase 1 in file `ugwiIPdF43v2woYsLM3b9R`. Existing collections were reused and validated: 54 primitive, 27 semantic color, 8 spacing, 5 radius and 5 dimension variables; Light/Dark aliases resolve and numeric values match `packages/design-tokens/src/tokens.css`. The nine Keen text styles moved from the Inter rendering proxy to the verified native SF Pro family, and existing Button, Badge and Service Banner text instances inherit the update. The six effect styles retain the current CSS shadow/focus values with clearer usage descriptions. Fresh visual review of Color `16:4`, Type `16:5` and Layout `16:6` found one malformed Typography eyebrow; it was replaced with the verified single-line header node `76:2` and re-rendered. Evidence is under `references/keen/2026-07-19-figma-phase1/`. No React/runtime behavior, backend boundary, responsive/accessibility result, accepted reference or pixel-parity claim changed. Reusable navigation/content/state components and selected screen reconstruction remain the next Phase-1 work.
- 2026-07-19: Continued the Figma-only design-system build with reusable navigation, progress, segmented-control, motion and operational-status primitives. Nav Row `80:56` has eight expanded/collapsed state variants plus 140 ms hover/click prototype reactions; Progress `89:46` has five deterministic values; `102:11` has a structurally verified 48→240 px WIDTH track over 0.22 seconds; Segmented Control `91:54` / `92:71` covers building-block states and three selected positions; Status Indicator `104:56` has five truthfully named state specimens. Final screenshots and exact limitations are under `references/keen/2026-07-19-figma-phase2/`. The available Figma tools did not expose video export, and the Segmented composite is not fully nested-instance-based, so those limitations remain explicit. `docs/DESIGN_RUNTIME_CONFLICTS.md` now makes API/SQLite and strict client contracts authoritative over Demo fixtures, code, Figma and reference products. Selected full-screen reconstruction, user confirmation, React implementation, supported-window/reduced-motion runtime checks, complete accessibility coverage and accepted visual regression baselines remain in progress; no pixel-parity claim is made.
- 2026-07-22: Closed the bounded Alpha guided-learning acceptance slice in the packaged ad-hoc `Keen UI Audit.app`. The real persisted course `Alpha Eigenvectors Current` restored the same completed session `autonomous-session-adc7fb35-ebc8-55a6-b08d-86341b5d53df` through Completed Feed → read-only Task Detail → History → completed Deep Learn summary; Review exposed the persisted FSRS item and Knowledge Base truthfully reported lexical search available with local embeddings unconfigured. Read-only SQLite verification found one completed originating task, two completed units, two answered active-recall runs, two answered practice runs, one summary handoff, one review item and one review attempt; session progress is `1.0`, revision `14`, and same-day recommendation identity remains a single row. A normal `⌘Q`, clean process check, relaunch, History course selection and record reopen restored the same session; the second `⌘Q` again left no audit app or sidecar process. Native evidence at 1180×740 CSS px, DPR 2, Light appearance and `reduced=false` is under `artifacts/ui-audit/2026-07-22/alpha-golden-path/`. Focused desktop tests passed 107/107 and focused Python tests passed 38/38; strict TypeScript, ESLint, Ruff and `git diff --check` passed. A fresh sidecar build, ad-hoc app build and bundled-sidecar smoke passed. This closes the internal Alpha loop only: no embedding-provider success, accepted visual baseline, pixel parity, packaged dark/reduced-motion-on result, Developer ID signature or notarization is claimed. Journey/Adaptive work remains outside this slice.
- 2026-07-22: Final independent Alpha closeout audit found P0/P1 = 0 and made no product-code change. A fresh focused recheck passed Python 40/40, desktop 106/106 and Rust 40/40; `git diff --check` and the current audit-app deep-signature verification passed. Two non-blocking P2 limits remain recorded for a later compatibility pass: a same-day completed replay can fall outside the 50-item completed-snapshot window in an extreme course, and its SQLite UTC range query relies on the established canonical `+00:00` text timestamp format for legacy compatibility. These do not invalidate the current Alpha evidence and do not upgrade the broader UI closeout row: packaged Dark, `reduced=true`, long-content and accepted-reference verification remain open.
## 2026-07-25 release-page interaction audit

Implemented the highest-priority product fixes from a read-only audit of Shell,
Home, Knowledge Base, Learning Feed/Task Detail, Deep Learn, History, Review,
Conversation and Settings. The real persisted Calculus session was restored in
the bundled Debug app and verified through incorrect Recall, provider-backed
Agent explanation and pending targeted Practice. Provider output is now
rendered safely as editorial rich text instead of raw Markdown; Practice has a
bounded prompt hierarchy and readable chain-rule notation. Home, Feed,
Conversation and Settings recovery/action issues were also corrected without
adding routes, dependencies or primary navigation.

Evidence: focused Deep Learn tests 62/62; combined Home/Feed tests 69/69;
combined Feed/Conversation/Settings tests 52/52; strict TypeScript and scoped
ESLint passed; the Debug `.app` production frontend build and ad-hoc signing
passed with the existing Vite chunk-size warning. Native evidence:
`artifacts/ui-audit/2026-07-25/feedback-flow/`.

Remaining P1: a saved Conversation transcript retry has component behavior but
does not yet have a dedicated failure-then-success regression test. Broader
Dark, reduced-motion-on, fixed-reference visual diff, complete accessibility,
Developer ID signing and notarization remain outside this slice.

## 2026-07-25 Deep Learn rail and cloze refinement

The live rail now uses the document surface instead of a tinted panel, reports
`Unit n of m` plus completed units, and renders one compact step sequence. The
pending targeted-practice contract remains the same deterministic persisted
prompt and hidden answer; only its learner-facing composition changed. A saved
prompt is presented as a visible blank, source statement, normalized formula
and one 200-character text field. The learner is explicitly told to enter only
the missing word or short phrase, can submit with Enter, and does not need to
retype the formula.

Focused Deep Learn tests passed 49/49, the keyboard submission test passed in
the 9/9 targeted-Practice suite, strict TypeScript and scoped ESLint passed, and
the ad-hoc Debug app rebuilt successfully. Native screenshots are under
`artifacts/ui-audit/2026-07-25/practice-refinement/`.

## 2026-07-25 Figma guided-learning delta

Status: first-row design delta complete; second-row validation in progress;
runtime comparison pending.

The existing canonical Figma file now includes one bounded section,
`07 · Guided Learning Flow Deltas · 2026-07-25` (`200:108`), with:

- Home saved work (`200:630`): one persisted `Next up` item and one primary
  `Continue` action;
- Home new learning (`202:660`): source, prompt, Ask/Focused Study choice and
  one disabled-until-ready continuation;
- Deep Learn reading (`207:149`): release navigation, a collapsible-path rail,
  one bounded reading column, readable math, and an inline recall handoff.
- Closed-book Recall (`220:151`): one bounded response field accepting plain
  language or math, with uncertainty kept as a secondary action;
- Agent intervention (`220:451`): the learner response remains visible beside
  one focused correction and the governing equation;
- Targeted Practice (`220:751`): one smaller question derived from the missing
  inner-derivative link.

The frames reuse the existing Keen shell, variables, local components, and
brand assets. Visible product text uses SF Pro; the equation uses STIX Two
Math. Screenshot evidence is under `artifacts/figma/2026-07-25-delta/`.

Recall has been visually inspected. Agent intervention and targeted Practice
were written successfully but remain implemented-unverified because the Figma
screenshot service returned an internal error for new and previously accepted
nodes. Next: re-run their visual and font checks, correct their learning-path
rail states, then compare the six-state delta against the packaged application
at a fixed viewport. No pixel-parity or accepted-runtime-baseline claim is
made.

## 2026-07-25 Appica primitive convergence

Status: bounded implementation and scoped runtime verification complete.

Keen now adapts the bounded high-frequency treatment reviewed from Appica UI
commit `26de9b1e02d2fb48694ae52d2371b1bbd71ee9d6` through the existing token,
component and global-CSS layers. This changes Button, Field, Card, Badge and
Progress presentation across the current product without adding a second
component runtime, route, learning contract or information architecture.
Keen's canonical brand, release navigation, semantic status colors and
accessibility contracts remain authoritative.

The upstream React package was intentionally not installed because it assumes
Tailwind and Base UI. The public Figma connection exposes the supplied
community-file thumbnail but not the underlying component pages, so this pass
does not claim Figma instance reuse, component parity or pixel parity.
Provenance is recorded in `docs/OPEN_SOURCE_INVENTORY.md`,
`docs/UPSTREAM_PATCHES.md` and `THIRD_PARTY_NOTICES.md`.

Strict TypeScript, scoped ESLint, 79 focused desktop tests, the production
frontend build and `git diff --check` passed. Home and Learning Feed were
inspected at 1280×800; Deep Learn was inspected at 1180×760 with no horizontal
overflow, shared-button wrapping or browser-console errors. The inspection also
corrected the demo learning-path Current/Next hierarchy exposed by the new
control scale. Runtime evidence is under
`artifacts/ui-audit/2026-07-25/appica-primitives/`.

The canonical Figma Recall frame now uses two equal 128×40 action instances
with a 12 px gap; screenshot evidence is
`artifacts/figma/2026-07-25-delta/deep-learn-recall-appica-buttons.png`.

A supporting-page refinement then kept long Feed task titles readable across
two lines, made Settings section descriptions task-specific, removed
non-actionable future-integration rows, and scoped provider/Keychain disclosure
to Capabilities. Strict TypeScript, ESLint and 3 focused desktop files / 31
tests passed. Live Browser Demo inspection at 1280×800 verified the task list,
selected task detail, Settings Status and Settings Capabilities with no
horizontal document overflow. This does not replace packaged-WebView, Dark,
reduced-motion-on or accepted-reference validation.

History and Review now use one shared, restrained empty-state composition
instead of unrelated left- and center-aligned structures; both retain one
truthful `New learning` action, and explanatory copy renders at 13 px. Settings
no longer repeats Browser Demo/Desktop-runtime status in its section header;
the global disclosure and contextual Status rows remain authoritative. The
focused History, Review, Settings Browser Demo and shell workflow files passed
63/63 tests, including the release constraint that Calendar, Drive and Canvas
are not advertised. Strict TypeScript and ESLint passed, and live 1280×720
inspection found no horizontal overflow on all four inspected states. This is
browser evidence only; packaged-WebView and complete accessibility verification
remain open.

Browser Demo New learning now preserves the actual product boundary. Ask keeps
one editable question draft and its existing non-generating Conversation
handoff. Focused study no longer accepts a goal and redirects it to that
unrelated handoff; it explains that a saved guided path requires an indexed
desktop course and offers one real route to sample Knowledge Base organization.
Demo orientation copy no longer tells the learner to use an absent source
selector. Knowledge Base also renders `1 page` rather than `1 pages`. Three
focused desktop files passed 90/90 tests, strict TypeScript and ESLint passed,
and live 1280×720 inspection found no horizontal overflow across Home Ask, Home
Focused study and Knowledge Base. No desktop Study behavior, API, storage or
source contract changed.

## 2026-07-25 packaged supporting-page pass

Status: **verified for the current Light packaged-app states inspected**.

The native production-named ad-hoc `Keen.app` was opened at 1204×768 with its
bundled authenticated learning core. Home, Knowledge Base, Learning Feed,
History, Review and Settings were inspected without creating learning data.
History, Review and Settings retained the shared supporting-page hierarchy.
Learning Feed's no-course state failed the task-first rule because it exposed an
empty two-column detail shell and promoted Calendar before any task existed.

The no-course state now uses one bounded onboarding composition with three
truthful steps and one Knowledge Base action. The existing task rail, selected
detail and secondary calendar remain unchanged for real or Demo tasks. Focused
validation passed 3 desktop files / 90 tests, strict TypeScript and ESLint. The
production frontend and current ad-hoc `.app` rebuilt successfully, and strict
deep signature verification passed. A complete DMG/checksum/sidecar/Review
restart smoke also passed before the final frontend-only Feed adjustment; the
earlier DMG is not treated as the current visual artifact.

Next closeout remains bounded to packaged Dark, reduced-motion-on, long-content
and keyboard traversal, followed by the existing anti-template review. No new
route, learning-core contract, design system, accepted visual baseline or
pixel-parity claim was added.

## 2026-07-25 Dark and motion token closeout

Status: **verified for Browser Dark/reduced-motion and packaged-app Dark states
named below**.

The product audit found two concrete Dark contrast failures and one shared-token
gap. Primary action text measured 2.42:1 against the Dark accent and the Deep
Learn Demo disclosure measured 2.11:1. They now use the existing ink/accent and
semantic warning roles, measuring 7.33:1 and approximately 6.13:1 respectively.
Four previously undefined variables—`surface-subtle`, `radius-md`, `shadow-xs`,
and `motion-inline`—are now defined in the shared token package, restoring the
intended Practice surface, radius, subtle elevation and inline transitions. The
intervention quote uses a full subtle border rather than a decorative side
stripe.

At 1180×760, Browser Deep Learn, Learning Feed and Settings showed zero
horizontal document overflow in Dark; the inspected reduced-motion controls
reported 0.01 ms transition and animation durations. The scoped Impeccable
detector returned no findings. Focused validation passed 5 desktop files / 84
tests, strict TypeScript, ESLint and production frontend build.

The current ad-hoc `Keen.app` was rebuilt and native Home, no-course Learning
Feed and Settings were inspected in macOS Dark with the bundled learning core
ready. Strict deep signature verification passed. The macOS appearance setting
was returned to its original Automatic value. Packaged reduced-motion-on, long
persisted content, complete keyboard-only traversal and accepted-reference
visual diff remain open; no new product route, behavior or parity claim was
added.

Packaged reduced-motion-on, accepted-reference visual diff, Developer ID and
notarization remain outside this visual convergence slice.

### Final UI anti-template acceptance gate — planned

Status: **not started**. After the current release pages are built, run one
bounded whole-product review using the existing Keen page/runtime contracts,
Impeccable critique workflow and fixed-viewport browser/package evidence.
Hallmark informs the review's anti-template checks—clear hierarchy, deliberate
specificity, restraint, structural variety, complete component states and no
invented proof—but is not being installed, copied or treated as a replacement
design system.

Acceptance requires the guided-learning journey to read as one product across
Shell, Feed/Task Detail, Deep Learn and supporting pages; no repeated
dashboard-card scaffolding, gratuitous pills/gradients/glass, generic
AI-assistant language, fake metrics/progress, meaningless whitespace,
inconsistent wrapping, competing primary actions or nonfunctional
affordances. Run deterministic detection and an independent product/design
assessment against the same build, then verify Browser Demo at 1280×800,
1180×760 and the supported compact desktop width. Finish with packaged-WebView
Light, Dark, reduced-motion, long-content and keyboard-path inspection.
Hallmark's landing-page and phone-width rules are adapted rather than copied
because Keen is a local-first macOS product UI. Evidence and unresolved
findings must be recorded in `docs/VISUAL_TODO.md`; no parity claim is allowed
without an accepted reference and a real visual diff.

## 2026-07-26 Deep Learn recall continuity

Status: **implemented and browser-verified for the bundled Demo slice**.

The default Deep Learn lesson remains a two-column composition: collapsible
learning path plus bounded reading column. Its checkpoint now behaves as one
continuous read → answer → feedback → revise interaction rather than separate
input and status fragments. Plain-language and unformatted formula input are
explicitly supported; editing temporarily removes competing unit navigation
and preserves a cancelled draft. The App shell remains the single global Demo
disclosure owner.

Focused validation passed 27/27 Deep Learn tests, strict TypeScript and scoped
ESLint. Browser inspection covered default, input and revision states at
1280×768 and the default state at 900×768. The compact state had zero
horizontal overflow, one `main`, and no unnamed buttons. Evidence is stored
under `artifacts/ui-audit/2026-07-26/deep-learn-next/`. Packaged-WebView,
Dark/reduced-motion, long-content and accepted-reference visual diff remain
open; no pixel-parity claim is made.

## 2026-07-26 Supporting empty-state continuity

Status: **implemented; browser-verified for empty states and packaged-verified for populated continuity**.

The two supporting pages retain the structure of their populated product state
instead of showing a generic empty canvas or a three-column onboarding strip.
History is framed as a saved-record collection and Review as a due queue. Each
shows one truthful zero count, a bounded empty body and one primary action.
HyperKnow informed the list-first structure; StudyFetch and RemNote informed
the object/queue-first hierarchy. No route, sample record, simulated completion
or third-party visual asset was added.

Focused History, Review and App workflow validation passed 62/62 tests, strict
TypeScript, scoped ESLint, the Impeccable detector and the production frontend
build. Browser inspection covered both pages at 1280×768 and History at
900×768; the compact state had no horizontal overflow, one `main`, and no
unnamed buttons. Current evidence is under
`artifacts/ui-audit/2026-07-26/supporting-empty-states-v2/`. Exact empty-state
packaged-WebView reproduction and whole-product
keyboard/long-content acceptance remain open.

A fresh ad-hoc Debug `Keen UI Audit.app`, built with the bundled learning-core
sidecar, subsequently reached ready at the native 1180×740 minimum and restored
Home, populated History, a due Review, Learning Feed Upcoming/task detail and a
persisted Deep Learn Summary. This pass was read-only. It exposed raw
bracket-string matrices/vectors in Review, so the display path now applies
native MathML to unambiguous matrix/vector notation without changing persisted
content or adding a dependency. The rebuilt app visibly and accessibly rendered
the 2×2 sample matrix. Packaged evidence is under
`artifacts/ui-audit/2026-07-26/packaged-supporting-v2/`. The exact zero-record
History/Review compositions remain browser-verified rather than packaged-
verified because the isolated native fixture contains saved records.

## 2026-07-27 DeepTutor-structure packaged polish

Status: **implemented and verified for the packaged Light empty/supporting
states named below**.

The reviewed DeepTutor v1.5.1 screenshots were used as a structural reference
only: fixed content starts, compact secondary navigation, one primary action
and progressive disclosure. Keen retains its own brand, release navigation,
runtime contracts and source-grounded learning flow. Home now starts its
creation surface higher in the viewport; Knowledge Base keeps import and course
management collapsed until requested; History shows one contextual empty state
instead of stacking question and session empties; and Settings uses
learner-facing Status, Capabilities, Privacy & data and Open source sections.
Disabled primary actions use a neutral unavailable treatment, and shared
selects use the same control geometry and explicit chevron as text fields.

A fresh production-named ad-hoc `Keen.app` was inspected with the bundled local
learning service ready across Home, Knowledge Base, Learning Feed, History,
Review, Settings Status and Settings Capabilities. Captures are under
`artifacts/ui-audit/2026-07-27/deeptutor-polish/`. The full desktop suite passed
47 files / 543 tests; strict TypeScript, ESLint, production frontend build,
the scoped Impeccable detector and `git diff --check` passed. The complete
macOS packaging gate passed before the final CSS-only rebuild, including the
DMG checksum, mounted strict signature, bundled sidecar smoke and Review
restart/idempotency smoke; the final CSS-only app and DMG were then rebuilt
from that unchanged sidecar and rechecked. The existing Vite large-chunk
warning remains.

This is not a source-code incorporation or pixel-parity claim. No accepted
DeepTutor baseline, fixed-reference visual diff, packaged Dark/reduced-motion
pass, Developer ID signature or notarization was added.

## 2026-07-27 Round 03 convergence gate

Status: **accepted for the current Light-mode release-page slice; return to
the guided learning Agent loop**.

Round 03 reconciled the release shell, Feed/task detail, Deep Learn and
supporting pages without adding routes or a parallel component system. The
final fixed evidence set is under `artifacts/orchestrator/round-03/`.
ChatGPT Pro reviewed UI/design, interaction, learning-Agent and architecture
and returned `ACCEPT` with no must-fix items. Codex retained the technical
boundary that Model settings must keep the real local/Ollama and
OpenAI-compatible provider configuration needed by the product, while
rejecting provider marketplace, cloud-management and Agent-platform breadth.

A fresh bundled `Keen.app` reached `Learning core ready` and reproduced the
real zero-data Knowledge Base, Feed, History and Review states plus Settings
Status and Model. Strict deep signature validation and
`scripts/smoke-bundled-sidecar.sh` passed. Current-run packaged evidence is in
`artifacts/orchestrator/round-03/packaged/`.

The next product slice is the repository default journey: choose a source
scope → submit a learning request → receive a visible learning path → complete
one grounded study/recall step → return to persisted Feed or History state.
Work should deepen grounded planning, adaptive intervention and review
continuity inside the existing routes. It must not reopen release navigation
or expand provider/platform administration.

The existing visual-regression command remains an open verification gate
because accepted references are missing or stale. It is not a blocker for
Agent implementation, and no rebaseline or parity claim is authorized by this
acceptance.

## 2026-07-27 Agent Slice 05-A outcome-lineage closure

Status: **implemented and verified for the internal persistence/query
contract; no UI or causal-effect claim**.

Migration `032` adds an immutable exposure ledger that links a published
learning-intervention artifact to its existing canonical Practice. The
internal projection can later read deterministic Practice correctness and the
latest FSRS attempt for the exact Review item created from that Practice.
Multiple steered artifacts may point to the same Practice; this records the
learner's exposure path and never attributes a later result to one generated
artifact.

The projection hides rows without a matching durable artifact publication
checkpoint, does not return raw learner responses, and scopes Review lookup
through the persisted Practice handoff rather than a session/course/concept
latest query. Review schedule revisions are returned only as internal
before/after audit fields. The public completion summary remains redacted.

ChatGPT Pro returned `ACCEPT`, then accepted Codex's technical correction that
the Review relation follows one item lifecycle rather than freezing its first
revision. Evidence is under
`artifacts/orchestrator/agent-slice-05/`.

Verification:

- intervention + migration + Summary + Review: 46 passed;
- complete learning-core Python suite: 1141 passed, with one existing
  Starlette/httpx deprecation warning;
- scoped Ruff check and format check passed for the Slice 05 implementation
  and focused tests;
- `git diff --check` passed.

This sequencing note is superseded: Slice 05-B and Slice 4's packaged
service/durable-state restart evidence are now both complete. Do not begin
Candidate extraction, outcome ranking, self-optimization, a lineage UI or an
Agent platform.

## 2026-07-27 Agent Slice 05-B deterministic progressive hint

Status: **implemented and verified for one host-selected built-in Playbook
branch; no UI or efficacy claim**.

The exact current Unit's persisted zero-weight Diagnostic user-report is now
part of the frozen intervention context. Only the conjunction
`not_yet + incorrect Recall + first explain_differently request` selects the
immutable `progressive-hint@1` procedure. A partial, confident or absent
Diagnostic signal keeps the existing source-grounded rephrase. Any successor
request also returns to rephrase, while source-example and direct deterministic
Practice behavior are unchanged.

The selector is deterministic host code. It reuses the existing source-search
tool, profile budgets, artifact schema, canonical Practice and migration `032`
lineage. The selected slug/version/hash and exact Diagnostic evidence ID/score
persist with the run. Historical runs without the new context field restore
through an explicitly bounded legacy fingerprint path; new runs cannot use
that compatibility branch.

The Pro orchestrator accepted this pre-implementation contract. Codex added
the historical fingerprint compatibility requirement before calling the
increment complete. Verification passed 58 focused
intervention/Diagnostic/Recall/migration tests and the complete 1144-test
learning-core suite, with the same existing Starlette/httpx deprecation
warning. Scoped Ruff check/format and `git diff --check` passed.

No special artifact type, schema migration, public API field, page, analytics,
playbook ranking, inferred learner style or self-optimization loop was added.

The Pro orchestrator returned `05-B FINAL ACCEPT` with no must-fix items, then
accepted Codex's veto of a generic 05-C branch because no unused authoritative
signal currently distinguishes another teaching need. Slice 4's non-empty
packaged service restart package subsequently passed and was accepted; Playbook
selection does not expand again merely to increase branch count.

## 2026-07-27 Slice 4 packaged non-empty Session restart closure

Status: **verified and Pro-accepted for the packaged service/durable-state
restart gate; native WebView presentation remains a separate non-blocking
observation**.

`scripts/package-macos.sh` rebuilt the ad-hoc arm64 app and DMG from current
source with migrations `001–032`. DMG checksum verification, mounted and
standalone strict signature checks, bundled-sidecar smoke, and the existing
Review/FSRS restart/replay smoke passed. The resulting
`Keen_0.1.0_aarch64.dmg` is 34,264,522 bytes with SHA-256
`14fd4446b071dbdda0d760f90af762fb32e695c88ea239d92bd8e6a934fcd38d`.

An isolated temporary profile used one canonical content-addressed indexed
source fixture, then created its Task, non-empty Session, two-Unit plan and
pending Diagnostic only through the public focused-study and Diagnostic APIs.
After a complete packaged-sidecar stop/restart against the same SQLite file,
authoritative Session, Diagnostic and History reads restored the exact
Session, plan and checkpoint at revision 2 with `diagnosing`/`pending` state.
The original focused request returned `replayed`, the prior-generation token
returned 401, and all pre/post Task/Session/plan/Unit/checkpoint/Agent/lineage
counts were identical. No provider call, duplicate lineage write or user
profile mutation occurred.

ChatGPT Pro returned `A) ACCEPT` and explicitly classified native WebView
hydration/route rendering as a separate UI observation rather than a blocker
for this persistence result. Evidence and the decision are under
`artifacts/orchestrator/slice-04-restart/`. This does not claim Developer ID
signing, notarization, packaged native-state screenshots, visual parity or
learning efficacy.

## 2026-07-27 Learning Feed task-detail hierarchy repair

Status: **implemented and browser-verified for the deterministic selected-task
state; packaged and fixed-reference parity remain open**.

The selected task no longer reads like a generated analytics report. The
four-column facts panel became compact title metadata, the learning reason is
one bounded brief, and the old numbered timeline became a short next-action
list. The task rail now uses compact two-row controls so Today/Upcoming/
Completed never truncate at the verified 1203×768 viewport. Browser Demo copy
describes learning actions and keeps one low-key no-save disclosure instead of
internal preview/inspection language.

Evidence:
`artifacts/ui-audit/2026-07-27/learning-feed-refine-final.png` and
`artifacts/ui-audit/2026-07-27/learning-feed-refine-comparison.png`.
Strict TypeScript and the focused Feed/App suites passed 44/44. This is a
qualitative correction against the user-supplied rejected crop, not a
DeepTutor pixel-parity result.

## 2026-07-27 Core reader pages + visible adaptive-decision loop

Status: **implemented, focused-test verified and Pro-accepted; exact
same-state pixel parity and learning-efficacy claims remain open**.

Deep Learn, Review and History now use one coherent DeepTutor-bounded
interaction structure without copying upstream runtime code or feature
breadth. Deep Learn stays within a collapsible path rail plus 65–75ch reading
column, renders mathematical notation with native MathML, and accepts
plain-language recall. Review is a real queue/reveal/FSRS-rating flow. History
is a compact list browser with one row action and a bounded first-use state.

The existing persisted adaptive ledger is now visible instead of merely
internal. Source review and targeted practice explain the saved
`reason_code`; Review explains why the item is due using its real source,
FSRS state, repetitions and lapses. No new page, navigation item, provider,
fake progress, inferred learning style or parallel Agent framework was added.

Evidence:

- `artifacts/ui-audit/2026-07-27/core-pages-parallel/01-reference-final-contact.png`
- `artifacts/ui-audit/2026-07-27/core-pages-parallel/final/`
- `artifacts/ui-audit/2026-07-27/core-pages-parallel/packaged/02-history-final.jpeg`
- `artifacts/ui-audit/2026-07-27/core-pages-parallel/packaged/03-review-final.jpeg`
- `artifacts/orchestrator/round-04-core-pages/pro-review.md`

The pre-decision integration run passed 10 files / 136 tests; the visible
decision increment passed 7 files / 105 tests, strict TypeScript, ESLint and
`git diff --check`. A fresh production `.app` build passed strict deep-signature
verification and the bundled-sidecar smoke. The packaged executable reached
`Learning core ready`, rendered the real zero-data History and Review states,
and shut the sidecar down cleanly on `⌘Q`. These packaged captures verify the
current truthful empty states only; they are not visual pixel parity or
evidence for a due Review/remediation state.
