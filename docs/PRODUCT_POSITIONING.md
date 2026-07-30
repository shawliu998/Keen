# Keen product positioning

Status: **frozen for the current Alpha; the bounded Agent-native extension is in progress through verified Slices 0–3**.

This is the canonical scope for product, design, Figma, and implementation decisions. Update it only when the user intentionally changes product direction.

## Positioning

Keen turns a learner's course materials into a guided learning path, so the learner always knows what they are learning, what to do next, and when to return.

The primary user is a self-directed learner studying a bounded subject from their own materials. Keen is a learning workspace with an Agent inside it—not a general AI chat client, a security dashboard, or a collection of future integration previews.

## Primary audience and usage boundary

Keen's initial audience is a learner who:

- has a bounded set of course, certification, or professional-learning materials;
- is pursuing one concrete understanding or skill goal;
- expects to study across multiple sessions rather than receive one disposable answer;
- benefits from source-grounded explanation, active recall, targeted practice, and scheduled review.

University and postgraduate learners are the primary entry cohort. Knowledge workers learning a bounded technical or professional subject are a secondary cohort under the same workflow.

Keen is not currently optimized for open-ended web research, general personal assistance, teacher or cohort administration, collaborative classrooms, content-authoring workflows, enterprise knowledge management, or LMS replacement.

## Core job and loop

The product must make this loop legible and continuous:

1. Choose or add learning materials.
2. State a learning goal or question.
3. See the proposed path, source scope, and expected work.
4. Learn through explanation, evidence, and guided steps.
5. Perform recall or practice and receive grounded feedback.
6. Persist the result, progress, and next action.
7. Return through Home, Learning Feed, History, or Review.

A page, component, or backend capability is valuable in the current phase only if it advances or restores this loop.

## Product principles

- **Next action over dashboard density.** Each screen should make the learner's next meaningful action obvious.
- **Learning record over chat theater.** Conversation is a durable, source-scoped record; Deep Learn is a guided session.
- **Progress over decoration.** Show steps, current position, completed work, and the next handoff—not synthetic scores or ornamental charts.
- **Truth without defensive copy.** Unavailable capabilities are stated once, at the point of action. Normal screens are not dominated by local/security/provider disclaimers.
- **Reference capabilities, Keen identity.** Adapt HyperKnow's useful information architecture, workflow, density, and interaction organization without shipping its brand, user data, or implementation code.

## Stable primary navigation

- New learning
- Home
- Knowledge Base
- Learning Feed
- History
- Review
- Settings

Deep Learn is entered from a learning request, task, or history item. It is a session state, not a permanent top-level destination. Future Planner, Memory, Visualize, Calendar, Drive, Canvas, and provider surfaces remain outside primary navigation until they perform a real user action.

## Binding UI convergence contract

This contract governs the next UI closeout. It narrows presentation without deleting working architecture or reopening the approved visual direction.

- **One start action.** The product exposes one `New learning` entry. Home owns the Ask/Study choice; a separate Sidebar `New study session` action is a duplicate and must be removed.
- **Two Home compositions.** Saved work shows one persisted `Next up` task and a compact New learning entry. Empty or explicit New learning shows intent → source → prompt → one mode-specific action. The two compositions never stack.
- **Task list before calendar.** Learning Feed defaults to Today, Upcoming, and Completed work. Calendar is a secondary view, never the main empty-state canvas. The selected task shows goal, expected steps, current progress, and next action.
- **One primary task action.** Study tasks continue in Deep Learn; Review tasks open Review. Their owning workflow records completion. A real deferral may be grouped under `Later…`; Undo is short-lived feedback after a confirmed reversible change, not a permanent action strip.
- **Two persistent Study columns.** Deep Learn keeps a collapsible path rail and a 65–75ch learning document. Source/citation detail opens on demand. At normal 1180–1280 px windows, a default three-column layout is prohibited.
- **Learning types, not product modules.** Quiz, flash cards, and future visual explanations are steps or blocks inside Study/Review. Planner, Memory, Visualize, `/quiz`, and the `/flashcards` compatibility route remain outside release discovery until each has a truthful independent job.
- **Quiet operational truth.** Healthy local/service state stays compact. Provider, sidecar, permission, recovery, and offline detail appears only where it changes the current action or in Settings.
- **Reference boundary.** HyperKnow informs information architecture and interaction organization; DeepTutor informs selected internal capability contracts. Neither defines Keen's feature count, brand, copy, or navigation.

The approved implementation order is `Shell/Sidebar → Learning Feed/Task Detail → Deep Learn → supporting-page consistency → packaged Tauri verification → stop`. Do not add a new capability while this closeout is active.

## Capability map for the current UI phase

| Surface | Learner outcome | Reproduce now | Defer |
| --- | --- | --- | --- |
| New learning / Home | Start or resume useful work | Source scope, goal input, Ask/Deep Learn intent, recent work, next action | Generic assistant suggestions and future integrations |
| Knowledge Base | Know which material can be used | Import entry, source/course organization, indexing and recovery state | Cloud-drive success flows before integration exists |
| Conversation | Understand an answer and its basis | Document-style answer, source scope, citations, continuation, durable status | Chat bubbles, invented replies, unsupported citations |
| Learning path | Understand the work before starting | Goal, expected steps, current step, next step, start/continue | Synthetic mastery forecasts |
| Deep Learn | Complete one guided learning unit | Path rail, reading, evidence, recall/practice, pause/resume, handoff | Floating assistant and ornamental dashboards |
| Learning Feed | Act on scheduled or queued work | Current tasks, progress, one Start/Continue/Review action, real `Later…` deferral when available, recovery | General task-manager CRUD and external calendar write until implemented and confirmed |
| History | Resume previous learning | Persisted conversations and sessions, status, source scope, continue action | Generated activity without persisted records |
| Review | Return at the right time | Real due queue, recall, reveal, rating, next item | Sample decks presented as user data |
| Settings | Configure or diagnose capabilities | Service status, provider setup entry, data/privacy, open source | Simulated connected accounts or preference-heavy placeholders |

## First end-to-end slice

The next product slice is one clickable, truthful journey:

`select an existing source or import entry → submit a Deep Learn request → inspect the learning path → complete one study and recall step → see the persisted session in Learning Feed or History → resume it after reload`

Use existing deterministic demo data only when it is visibly labelled and makes no claim of provider, retrieval, citation, scheduling, or import success. The live path must never substitute sample success for a failed service.

## Next phase — lightweight learning continuity

The next phase extends the completed loop without turning Keen into a broad Learning OS. “Journey” means continuity across the records Keen already owns, not a new top-level product:

- Course, persisted task, Study Session, Conversation, Review, Feed, and History remain the source of truth.
- Home chooses one real cross-course `Next up` action and preserves its course/task/session context.
- A learner can identify the active goal, completed work, current step, and next handoff from existing records.
- Journey does not receive a primary navigation item, a parallel component system, synthetic mastery forecasts, or an AI-generated long-range curriculum.

Vector retrieval is an existing optional implementation capability, not a new interface module. Keen retains lexical fallback and the current hybrid-retrieval contract. Further vector work requires a small, source-backed query set showing a material retrieval improvement over lexical search without reducing citation accuracy. Until that gate is met, do not add a new vector database, RAG framework, retrieval dashboard, or embedding-only product surface.

## Current capability phase — bounded Agent-native learning

Keen now connects its existing durable Agent Runtime to the learning loop through bounded, incrementally verified slices. Slices 0–2 provide the source-grounded post-Recall intervention and closed steering; Slice 3 adds an explicit, source-linked plan proposal plus deterministic Accept/Keep and bounded safe Undo. The detailed architecture, state ownership, delivery slices, and acceptance gates are defined in `docs/AGENT_NATIVE_ARCHITECTURE.md`. Later slices remain planned and must not be presented as current runtime behavior.

Agent-native is not a separate user-facing mode. It is valuable only when it improves the existing learning loop by selecting a better bounded teaching action from real learner evidence. The learner continues to interact with Home, Deep Learn, Practice, Review, Feed, and History—not with an Agent console.

The directional user-research basis is recorded in `docs/AGENT_NATIVE_USER_RESEARCH.md`. Public learner discussions and current tutoring/HCI research are treated as product hypotheses, not representative demand or proof of learning efficacy. They reinforce one boundary: Keen should absorb context restoration, source selection within an explicit scope, tactic selection, scheduling projection, and recovery, while preserving the learner's own attempt and deterministic grading as the evidence of learning.

- **Closed learning loop, not generic autonomy.** Agent-native means: observe authoritative learning state → choose one bounded teaching action → use an exact tool profile → validate the artifact contract and source handles → wait for a real learner action → apply deterministic learning updates → persist and restore the next action.
- **Mixed initiative, not prompt work.** Keen's deterministic policy should select and offer one specific eligible teaching move, then explain `why now`, `using which sources`, and `what happens next`; the initial rollout remains learner-activated, and the learner should not need to choose a model, Agent, Playbook, or rewrite the current context as a prompt.
- **Reduce management, preserve effort.** The Agent may carry orchestration and continuity, but it must not replace the learner's first attempt, bulk-generate review debt, infer mastery from consumption, or turn a fluent explanation into completion evidence.
- **One initial intervention.** The first vertical slice is a source-grounded alternate explanation after a real incorrect Recall attempt, displayed inline in Deep Learn and followed by existing parallel Practice.
- **Deterministic state remains authoritative.** Grading, confirmed misconceptions, BKT, FSRS, Task/Session completion, and the current plan pointer stay outside model control.
- **Versioned Teaching Playbooks first.** v1 uses a small code-owned set of declarative teaching procedures. Hermes-like procedure extraction is a later candidate-only phase with human review, evaluation, activation, and rollback; it is not automatic self-modification.
- **No new product surface or runtime stack.** This phase adds no Agent navigation, floating chat, unrestricted tools, multi-Agent system, second Session Store, new RAG/Agent framework, or Journey model. Existing Agent Runtime, provider adapters, retrieval, SQLite, Deep Learn, Feed, History, and Review are extended in place.

### Agent-native functional priority

**Core product — retain and complete**

1. Scope trusted learning materials.
2. Turn one goal into a visible learning path.
3. Explain with source evidence.
4. Require a real Recall or Practice attempt.
5. Persist progress and one next action.
6. Restore the same learning state after interruption.

**Bounded Agent extension — add incrementally**

1. Offer one source-grounded alternate explanation after a real incorrect attempt.
2. Accept closed steering such as shorter, source example, or test me instead.
3. Propose a bounded plan adjustment only after repeated evidence or an explicit goal change.
4. Keep Home, Feed, Deep Learn, History, and Review aligned on one authoritative next action.

**Deferred by product boundary**

- automatic Teaching Playbook extraction or activation before outcome lineage exists;
- broad learner profiling or inferred personality, motivation, fatigue, or fixed learning style;
- generic Memory, Research, Visualize, Planner, Agent activity, or Skill-marketplace products;
- unrestricted tools, background autonomy, or multi-Agent teaching;
- Journey or Goal aggregates that duplicate existing Session and Task state.

## Explicitly not the current focus

- More audit applications, viewport probes, packaging identities, or baseline frameworks.
- Pixel-parity claims or approving every route before the core loop exists.
- Repeating “local workspace,” security, provenance, or trust language throughout ordinary learning screens.
- Calendar, Drive, Canvas, provider, Memory, complex Planner, Visualize, or export previews without working contracts.
- Broad parser or open-source integration work before the current UI flow is coherent.

These concerns remain valid constraints or later capabilities. They do not define the current product experience.
