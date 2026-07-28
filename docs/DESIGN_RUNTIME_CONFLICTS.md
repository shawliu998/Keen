# Design, Data, and Runtime Source of Truth

This ledger prevents Figma specimens, deterministic Demo data, API projections, and runtime code from becoming competing versions of the product. It applies to UI design and implementation work.

## Precedence

| Priority | Source | Governs | Rule |
| --- | --- | --- | --- |
| 1 | FastAPI/Pydantic contracts, SQLite migrations and trusted Tauri boundaries | Whether data and capabilities exist; legal states; permissions; persistence | Runtime wins. Do not add a Figma field or success state that the trusted boundary cannot produce. |
| 2 | Strict TypeScript/Zod projections and feature state machines | What the desktop may render and which actions are available | Unknown or rejected fields are omitted; they are never inferred from a reference product. |
| 3 | Deterministic Demo fixtures and visual-regression seeds | Repeatable screenshot content | Demo content must remain visibly Sample/Demo and must not be cited as persisted learner evidence. |
| 4 | `packages/design-tokens`, current React components and verified browser behavior | Implemented geometry, tokens, focus, motion and recovery behavior | A Figma difference is recorded below before either side is changed. |
| 5 | Keen Figma file and authorized visual references | Layout intent, hierarchy, reusable component vocabulary and proposed interaction | Figma is a decision record, not independent evidence that a backend or integration works. |

## Required mapping for a screen

Before a Figma screen is selected for React implementation, record:

- the API/Zod fields or deterministic fixture keys that supply each visible datum;
- the legal empty, loading, partial, offline, error, cancelled and recovery states;
- whether each action is read-only, reversible local mutation, or confirmation-required external action;
- the fallback copy when a field or service is absent;
- the fixed viewport, seed and screenshot evidence used for comparison.

If a visible value has no runtime or deterministic-fixture source, remove it or label it as a design-only specimen. Do not synthesize a mastery score, citation, provider answer, upload success, calendar connection or integration result to fill the layout.

## Current conflicts and decisions

| Area | Figma / reference | Runtime / data | Decision | Status |
| --- | --- | --- | --- | --- |
| Typography | Phase-1 foundations use native SF Pro; the approved compact screens render with Inter, and Button `33:2` previously referenced an unavailable SF Pro Medium | Production uses the macOS system font stack | Button labels now use Inter Medium so Figma overrides work. Treat the screen family as visual intent and verify the real system-stack render by screenshot. | Component override repaired; runtime visually checked |
| Button geometry | Earlier Figma components use 36 px height / 12 px horizontal padding; compact product screens use 34 px controls | Shared React Button now uses 34 px / 13 px by default and an explicit 30 px small size | Use the compact screen geometry and retain smaller controls only for dense secondary actions. Loading, variants and compatibility rules are recorded in `docs/figma/COMPONENT_RUNTIME_SPEC.md`. | Shared runtime aligned; accepted baseline pending |
| Nav Row | Figma has expanded/collapsed Default, Hover, Focus and Current variants plus hover/click prototype reactions | React has real navigation and focus behavior, but has not been rebuilt from this component set | Runtime route state remains authoritative; map the Figma variants during the later UI-only implementation slice. | Design ready; runtime pending |
| Segmented Control | The parent set has three selected positions; its visible segments use local layers because automated nested text overrides were blocked by Figma font availability | React segmented filters already own the legal filter values and keyboard semantics | Keep the Figma visual API, but do not claim a fully nested-instance composition or replace runtime values. | Figma limitation recorded |
| Progress | Figma defines 0/25/50/75/100 specimens and one 48→240 px, 220 ms Motion track | Runtime clamps 0–100, exposes ARIA values and animates `transform: scaleX()` using `--motion-standard: 220ms` | Bind only to real task, upload or deterministic learning progress. Reduced motion updates immediately. | Runtime aligned; accepted baseline pending |
| Warning soft color | Figma foundations contain Light/Dark `warning-soft` semantic values | Production previously used repeated literal warning backgrounds | `--warning-soft` now exists in both CSS themes and is the shared Badge warning surface. | Resolved in shared tokens |
| Status Indicator | Figma adds Ready, Starting, Offline, Error and Not configured vocabulary | A visible state must come from the local-service/configuration state machine | Component specimens are not evidence that a sidecar, provider or integration succeeded. | Design ready; runtime mapping pending |
| HyperKnow timing | Reference captures show visible transitions but no independently measured timings | Keen currently defines 140 ms fast and 220 ms standard tokens | Use Keen tokens; do not attribute exact timing parity to HyperKnow. | Resolved truthfully |
| Raw Figma product screens | Nodes `64:2`, `66:2`, `65:2` are editable captures of earlier Browser Demo states | Runtime code can continue to change | Re-capture or reconcile before implementation; never treat these frames as automatically current. | Drift-prone |
| No-course Sidebar status | Figma node `179:998` labels the Sidebar footer `No local courses` | `LearningCoreStatus` reports service lifecycle only; course availability is page data | Keep `Learning core ready` in the shared Sidebar and show `No local courses yet` in the Feed pane. Do not conflate a healthy local service with its current data inventory. | Runtime wins; intentional visual difference |
| Study Planner future UI | Earlier Demo UI showed fixed sessions, mutable completion and a calendar confirmation preview | There is no syllabus-to-plan contract, persisted planner state, calendar adapter or executable Level 3 write | Keep only the not-implemented boundary. Reintroduce import after validated syllabus parsing exists; schedule editing after typed API/SQLite persistence and recovery exist; calendar preview/confirmation only when an adapter can produce an exact proposal and execute a confirmed write. | Demo removed; activation gates recorded |

## Change protocol

1. Add or update a row before resolving a material conflict.
2. Name the winning source and why it wins.
3. Update Figma and code in separate, reviewable slices unless the user explicitly requests both.
4. Run the checks appropriate to the changed side.
5. Link screenshots or tests; if no accepted reference exists, report `missing_reference` rather than a mismatch percentage.
