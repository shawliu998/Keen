# Visual Reference and Regression TODO

## Current gate

At the initial 2026-07-15 audit, `references/` did not exist. The canonical authorization scope is now recorded at `references/authorized-scope.md`, but there are still no accepted HyperKnow screenshots, recordings, Figma exports, or brand assets to measure. No page can currently be described as pixel-matched, and no `<3%` mismatch result can be computed.

The product may proceed with the brief's provisional tokens and non-branded placeholders. Those values must remain identifiable as provisional until measured from authorized references.

## Authorization intake

Resolve these before copying any protected visual asset:

- [x] Supply one canonical authorization document. `references/authorized-scope.md` is the canonical path; the notes-path variant is noncanonical.
- [ ] List every allowed screenshot, recording, Figma export, icon, illustration, logo, and Orbie asset.
- [ ] State allowed use: inspect only, derive measurements, modify, redistribute in source, and/or redistribute in built artifacts.
- [ ] Record prohibited pages/assets and any attribution or expiration conditions.
- [x] Record the user's attested internal-research permission for protected HyperKnow content. Ordinary interactive inspection is allowed; authentication bypass, bulk extraction, private data retention and redistribution remain prohibited.

2026-07-16 authorization note: the canonical scope now permits reading the currently visible user-authorized page, screenshot saving, ordinary navigation and implementation use of covered protected visual content for internal research. The permission is a user attestation, not independently verified. The in-app browser client could not initialize because it attempted to redefine a non-configurable runtime `process` property. A desktop-accessibility fallback reached the public sign-in state and then encountered an existing authenticated session; the task stopped without saving a screenshot. A later separate no-session capture did not complete after browser focus changed. No HyperKnow page screenshot or visual element has been accepted into the manifest or used for a parity claim.

## Missing page references

| Priority | Page/state | Required evidence | Status |
| --- | --- | --- | --- |
| P0 | Shared 1440×920 shell | Expanded Sidebar, Toolbar, main canvas, Inspector, traffic-light/titlebar relationship | Missing |
| P0 | Home / Agent | Default, composer focus, attachment/context menu, generating, stopped, recommendation cards | Missing |
| P0 | Conversation | Streaming, markdown/table/code/KaTeX/Mermaid, citations, tool trace, source preview/highlight | Missing |
| P0 | Knowledge Base | List/grid, drop state, each index status, failed/partial, document Inspector/preview | Missing |
| P0 | Deep Learn | Goal, diagnostic, map, unit, checkpoint, recall, practice, summary, paused/resumed | Missing |
| P0 | Quiz / Practice | Each item type, hint/scaffold depth, feedback, completion summary | Missing |
| P1 | Learning Feed | Today/upcoming/overdue/completed, course filters, rationale/trace, empty/error | Missing |
| P1 | Settings | All sections, provider states, secret input, notices | Missing |
| P1 | Flashcards | Front/back, rating controls, due/empty/edit/source states | Missing |
| P1 | Study Planner | Syllabus import, constraints, daily plan, reschedule, calendar proposal/confirm | Missing |
| P1 | Memory / Persona | Goals, preferences, evidence, inference, edit/delete/disable | Missing |
| P2 | Visualize | Task progress, Mermaid/SVG preview, error, export; later Manim states | Missing |
| P2 | Responsive shell | 1180×740 minimum, resized Sidebar, collapsed icon rail, Inspector hidden/collapsed | Missing |

For every page above, also collect its empty, loading, partial, error, offline, permission-denied, cancelled, sidecar-unavailable, and applicable provider/index/migration failure state.

2026-07-16 hardening note: the implemented shell now distinguishes binding, migrating, recovering, starting-server, health-checking, restarting, unavailable, and configuration-error service states. No authorized reference or new screenshot/diff evidence exists for these states, so their visual acceptance remains missing.

2026-07-16 Gate 3 note: Knowledge Base now has real course selection, multi-course labels, relation actions, course filters, and partial course-state errors. These states passed component/integration behavior tests, but no authorized visual reference or screenshot/diff evidence exists, so visual acceptance remains missing.

2026-07-16 Gate 4 note: Knowledge Base now renders provider-missing/failure, indexed-lexical, indexed-hybrid, embedding, cancelled/interrupted, and needs-reindex states with real warnings and actions. Component/integration behavior tests passed, but no authorized reference or screenshot/diff exists; visual acceptance and any parity claim remain blocked.

2026-07-16 Gate 5 note: Conversation now renders real Tauri streaming, locally stopped, provider-missing, disconnected, lexical-only, structural-citation, and empty live states; Browser Demo is explicitly labeled and performs no request. Behavioral tests passed, but no authorized reference or visual-diff evidence exists, so visual acceptance remains missing.

2026-07-16 Gate 6 note: Conversation now opens an authenticated page-on-demand PDF citation dialog with supported-geometry highlights, original excerpts, truthful loading/offline/error/page-only states, bounded canvas allocation, keyboard focus trapping/restoration, and a bundled local PDF.js worker. Behavioral tests passed, but no authorized reference screenshot or visual-diff evidence exists; no pixel-parity claim is made.

## Learning-loop live-state gap

Status on 2026-07-16: **in progress** at the milestone level; the following live page connections are `not started`.

| Page | Current rendered behavior | Required real-state visual coverage |
| --- | --- | --- |
| Conversation | Live RAG streaming exists, but sent messages/history are not durable and Study mode does not create a Session | persisted history, Ask/Teach/Study/Review/Plan, creation confirmation, restart recovery, Agent activity and interrupted run |
| Deep Learn | Live Start/Resume can render a persisted plan and bounded source citations from the selected active task; the view is read-only and does not write progress, answers, mastery, or completion. Browser Demo remains explicitly sample-only and makes zero requests. | goal confirmation, diagnostic, editable plan, teaching, checkpoint, active recall, practice, summary, persisted progress/pause/resume/recovery and all service/provider failures |
| Quiz | Three bundled single-choice items with in-memory score/hints | six real item types, confidence, four hint levels, submit/feedback, mastery evidence/delta, misconception and scheduled review |
| Flashcards | Bundled sample deck; rating remains in UI state and edit is disabled | real due/empty/front/back/source/edit/delete/error states and Again/Hard/Good/Easy schedule results |
| Learning Feed | Live course-scoped Snapshot/recommendation Feed renders candidates, persisted tasks, Plan and Start/Resume actions with explicit loading/empty/error/offline/cancelled/unknown-reconciliation states; Start/Resume opens the real read-only persisted Deep Learn view. | captured course/budget/candidate/task/rationale states; Complete/Snooze/Reschedule/feedback, mutation rollback, persisted progress and Session create/resume visual coverage |

No screenshot or current UI fixture for these Demo/read-only surfaces is evidence that the learning workflow is connected. Pixel comparison for the required states also remains blocked: canonical authorization is present, but no authorized HyperKnow screenshot/asset has been captured and accepted into the manifest. Covered protected visuals may now be used for internal implementation after capture; until then, continue with provisional non-branded design values and do not claim parity.

2026-07-16 learning-loop Gate 3 note: Home now visibly consumes authenticated
Agent create/get/cancel/events, renders durable activity and recovery states,
and exposes terminal-only Study Task Undo/Redo backed by recorded inverse
actions. Browser Demo remains request-free; waiting approval is explicitly
read-only; the still-seeded Feed and statistics are labeled Sample. Component
and integration behavior tests passed. A new 1440×920 current capture was
written to `artifacts/visual-diff/current/home.png`; the report remains
`missing_reference`, so no diff percentage exists. The Home / Agent visual row
therefore remains Missing rather than passed, and no pixel-parity claim is made.

2026-07-16 Agent provider-hardening note: the production-default empty tool
allowlist and strict local-chat stop-reason validation are backend-only changes;
they add no rendered state or new visual evidence. The Home / Agent reference,
failure-state captures and parity comparison therefore remain Missing.

2026-07-17 Agent course-scope note: migration 019 and trusted run-scope
resolution are persistence-only changes. They do not add a rendered tool state,
reference capture or visual-diff result; the Home / Agent visual row and scoped
tool activity states therefore remain Missing.

2026-07-17 structured read-tool note: the loopback provider can now execute two
host-scoped Level 1 reads through a strict multi-round protocol, but this batch
changes only the Python runtime and backend tests. It adds no rendered state,
authorized reference capture, visual-diff artifact or parity measurement. The
Home / Agent tool trace, loading/error/permission states and HyperKnow visual
comparison therefore remain Missing.

2026-07-17 course-knowledge tool note: the Agent can now perform bounded,
course-scoped lexical retrieval as a third Level 1 tool, with private source
feedback and backend E2E evidence. This batch adds no rendered citation state,
source preview, authorized reference capture or visual-diff artifact. The Home /
Agent retrieval trace, source interaction states and HyperKnow comparison remain
Missing; no visual parity claim is made.

2026-07-17 course-setup note: Knowledge Base now contains a functional local
course-creation form with component/integration evidence, including Demo and
service-unavailable behavior. No authorized HyperKnow reference, fixed-viewport
capture, accessibility scan or visual-diff artifact was produced for this
state. Its layout and error states therefore remain implemented but visually
unverified, and no parity claim is made.

2026-07-17 autonomous-foundation note: indexed-document concept bootstrap and
the deterministic Learning Snapshot are backend-only building blocks. They add
no rendered Agent status, Feed recommendation, Deep Learn state, screenshot or
visual-diff evidence. All autonomous-learning visual rows therefore remain
Missing; no product-flow or parity claim is made from backend tests.

2026-07-17 autonomous-recommendation note: the backend can now persist one
real, explainable Study Task from the deterministic Snapshot, including a
truthful replay/covered/empty outcome. It is not exposed through an API or
rendered by the desktop in this slice, and no Start action is connected. The
Home/Feed recommendation, state matrix, screenshot and visual-diff rows remain
Missing.

2026-07-17 autonomous-recommendation API note: authenticated strict resources
now expose the real Snapshot and persisted recommendation outcome, but this
backend slice adds no rendered state, screenshot, accessibility result or
visual-diff artifact. Home/Feed visuals and the Start action remain Missing.

2026-07-17 autonomous-session note: migration 022 and the backend coordinator
can create or recover a source-cited Study Session from a persisted autonomous
task, but no HTTP Start resource or desktop control is included in this slice.
Deep Learn/session states, screenshots and visual diffs therefore remain
Missing.

2026-07-17 autonomous-session API note: the authenticated sidecar now exposes
the real Start/Resume boundary and bounded cited plan data, but no desktop
control or rendered study state is included in this backend slice. Deep Learn,
blocked/created/resumed visuals, screenshots and visual diffs remain Missing.

2026-07-17 autonomous-learning desktop note: the live Learning Feed now renders
the authenticated Snapshot and recommendation outcome with course and study-time
selection, candidates, persisted task state and an explicit Plan action. Its
loading, empty, error, offline, cancelled and unknown-outcome reconciliation
states have behavior-test evidence; scope/cache/late-response isolation is also
tested. Home live mode no longer displays seeded Feed/statistics as learner data,
while Browser Demo remains visibly sample/request-free. No screenshot,
accessibility run, authorized reference capture or visual-diff was produced for
this slice. Therefore Learning Feed and Home/Agent visual rows remain Missing,
and no visual or pixel-parity claim is made. Desktop Start/Resume is still
unimplemented; Deep Learn remains its hard-coded demo while a real session
reader is in progress.

2026-07-17 autonomous Deep Learn note: the live Learning Feed now starts or
resumes a persisted Study Session and routes to a read-only Deep Learn view
that renders the stored plan and bounded source citations. Focused desktop and
source-ID contract tests passed, and independent acceptance found no open
P0/P1/P2; this is behavioral evidence only. The view does not write learner
progress, answers, mastery, task completion, or FSRS scheduling. Browser Demo
remains visibly sample-only and request-free. No screenshot, authorized visual
reference, visual-diff, or accessibility run was produced, so the Deep Learn
and Learning Feed visual rows remain Missing and no HyperKnow or pixel-parity
claim is made.

## Reference manifest fields

Every accepted reference should have a manifest entry with:

- stable `reference_id` and source file path;
- page/route and state name;
- capture viewport in CSS pixels and display scale;
- app/version/capture date if known;
- required deterministic seed fixture;
- authorization-scope entry;
- higher-resolution/newer precedence information;
- ignored dynamic regions and why;
- mismatch threshold (default target below 3% for primary pages);
- notes for expected macOS-native variance.

## Regression harness status

- [x] Create `tools/visual-regression/` without fabricated baseline images.
- [x] Add a machine-readable page manifest (schema validation remains open).
- [x] Start from deterministic frontend seed data and a direct route.
- [x] Disable motion/transitions/caret and request reduced motion (fixed clock/locale/timezone remain open).
- [x] Capture the Home application viewport at 1440×920 and display scale 1.
- [x] Produce `current` and a machine-readable report under `artifacts/visual-diff/`; diff and mismatch are emitted only when a real reference exists.
- [ ] Exclude only documented truly dynamic regions.
- [ ] Retain failed artifacts in CI.
- [ ] Iterate in order: layout, panel widths, typography, spacing, color/border, radius, shadow, icons, micro-motion.
- [ ] Record measured colors and dimensions in `packages/design-tokens`; do not silently overwrite provenance.

## Provisional design values

The values supplied in the brief—such as `#F6F8FA` app background, 248 px Sidebar, 336 px Inspector, and 52 px Toolbar—are starting hypotheses, not reference measurements. Implementation and tests should name them accordingly until a manifest-backed measurement replaces them.

## Visual acceptance record

A current-image run has completed, but comparison cannot run without an authorized reference. `missing_reference` is a blocker state, not a pass.

The 2026-07-17 recoverable-read slice adds a red recoverable-failure dot, grey cancelled/stopped dots, and explicit lifecycle copy. Its event/schema/reducer/panel behavior is tested, but no new screenshot or authorized visual diff was captured; spacing, color and copy remain provisional visual work rather than parity evidence.

The 2026-07-17 Level 2 slice adds a Home Agent confirmation card with a safe task/course/effect summary, Confirm/Reject controls, pending feedback, offline blocking and explicit unknown-outcome copy. Component/runtime tests cover those states. The visual harness was rerun at 1440×920 against the deterministic Home route and produced `missing_reference`; that route does not fixture a live waiting-approval run, and no authorized HyperKnow reference is present. Approval-card spacing, typography, button treatment and responsive behavior therefore remain `implemented / unverified` visually, with no mismatch percentage or parity claim.

| Date | Reference ID | Route/state | Viewport | Seed | Mismatch | Artifact paths | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-15 | Missing | `/?demo=true&visualTest=true` | 1440×920 @1x | Deterministic frontend seed | Not computed | `artifacts/visual-diff/current/home.png`, `artifacts/visual-diff/report.json` | `missing_reference`; no parity claim |
