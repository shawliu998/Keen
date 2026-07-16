# Learning Loop Implementation Plan

## Status and evidence contract

Status: **in progress** on `codex/milestone-learning-loop`.

This document controls the recoverable learning-loop milestone that starts from commit `094c44eb1eaa7ae77c45fd5c07d651587b968fc0`. It does not prove implementation by itself. Use only `not started`, `in progress`, `blocked`, `implemented / unverified`, and `verified`. A feature becomes `verified` only after its named tests and acceptance evidence have actually run.

The 2026-07-16 branch baseline was recorded before learning-loop implementation: `npm run check` passed frontend ESLint and strict TypeScript checks, Vitest 108/108, Python pytest 284/284 with one existing Starlette deprecation warning, and Rust 38/38. These are baseline results, not evidence that the learning loop exists.

## Outcome and vertical acceptance path

The milestone is one local-first, restart-safe path:

```text
create course
→ import PDF/Markdown/TXT
→ wait for real indexing
→ choose a learning goal
→ create Deep Learn Session
→ complete diagnostic
→ persist a versioned learning plan
→ teach and checkpoint one unit with citations
→ attempt Quiz / Active Recall and request a hint
→ deterministically grade and update mastery
→ record evidenced misconception
→ create and schedule Review Item with FSRS
→ rank the next action in Learning Feed
→ close and restart Keen
→ restore Session, Quiz, mastery, review and Feed
→ open the cited PDF page
```

Status: **in progress**. The document/import/retrieval/citation portions exist; the learning-loop portions are `not started` unless a later dated evidence entry says otherwise. No frontend seed or fixed test transcript may satisfy this path.

## Current verified baseline

### Implemented and verified before this milestone

- Tauri 2 macOS shell, React/Vite strict TypeScript desktop application, and a Python 3.11+ FastAPI learning-core sidecar.
- Authenticated `127.0.0.1` sidecar lifecycle with Python-owned random port, Rust-generated 256-bit session token, health/restart/shutdown handling, generation isolation, and arm64 `.app`/`.dmg` local-verification packaging.
- Versioned SQLite migrations `001` through `008`, Application Support data location, cross-process database ownership lock, recovery and storage reconciliation.
- PDF/Markdown/TXT import, durable asynchronous index jobs, cancellation/retry, Latin and CJK FTS5, optional loopback embeddings with sqlite-vec, hybrid retrieval and lexical fallback.
- Loopback-only Ollama/OpenAI-compatible chat adapters, generated-answer SSE, structural citations, authenticated PDF content serving, page-on-demand PDF.js rendering and supported bbox highlights.
- Live Tauri Conversation streaming with stop/retry/edit-and-resend and locally stored unsent draft; Browser Demo remains explicitly separate.
- Courses, concepts, base mastery, mastery events and study tasks from migration `001`; deterministic binary-observation BKT in `app/mastery.py`.
- Learning Feed can read current task/mastery rows, but its live UI is explicitly read-only.

### Present but insufficient for the learning loop

| Area | Current fact | Learning-loop status |
| --- | --- | --- |
| Conversation | `/v1/answer/stream` streams an answer; sent messages and conversation history are held in React state, while only the unsent draft uses local storage | `not started` for durable conversations/messages |
| Deep Learn | 31-line page with bundled eigenvector lesson and illustrative mastery | `not started`; explicitly demo and not persisted |
| Quiz | Three bundled single-choice questions scored in React state | `not started`; no assessment records or mastery/review mutation |
| Flashcards | Bundled sample cards and in-memory ratings | `not started`; FSRS is not connected |
| Learning Feed | Real `/v1/demo-state` task/mastery read with no live mutation | `in progress`; candidate generation, rationale and actions are `not started` |
| Agent | Answer service can retrieve and stream content | `not started` for orchestrator, typed tools, run/step/tool/mutation audit and approvals |
| Mastery | Deterministic BKT accepts only `concept_id` + boolean correctness and writes a basic event | `in progress`; evidence weighting, traceability and algorithm version are `not started` |
| Recovery | Index-job and sidecar recovery exist | `not started` for conversation/session/attempt/review/Agent recovery |

## Existing data model

Migration `001_initial.sql` currently defines:

- `courses`, `concepts`, `mastery`, `mastery_events`, and `study_tasks`;
- BKT parameters on each concept (`bkt_slip`, `bkt_guess`, `bkt_transit`);
- mastery probability constrained to `[0, 1]` and task/mastery event indexes.

Migrations `002`–`008` currently define:

- `documents`, `document_versions`, `document_chunks`, `document_status_events`, and Latin FTS5;
- `course_documents` many-to-many links and legacy link backfill;
- durable `document_index_jobs`, CJK trigram FTS5, embedding model/state/vector tables and atomic reindex staging;
- `document_chunk_geometry` for validated PDF source highlighting.

Important compatibility fact: `mastery_events` and `study_tasks` already contain user data. New migrations must extend or companion them; they must not recreate them, discard rows, or resolve schema changes by deleting the database.

## Existing authenticated API

The current `app/main.py` exposes:

- health/course/state: `GET /health`, `GET /v1/courses`, `GET /v1/courses/{id}`, `GET /v1/demo-state`;
- tasks/mastery: `GET/POST /v1/tasks`, `PATCH /v1/tasks/{id}`, `GET /v1/mastery`, `POST /v1/mastery/attempts`;
- documents/jobs: import/list/content, course link/unlink, job list/get/cancel, retry/reindex/delete;
- retrieval: `POST /v1/search`, deterministic `POST /v1/query`, and generated `POST /v1/answer/stream` SSE.

All routes inherit existing sidecar Bearer authentication and request guards. There is no `POST /v1/courses`, so the real E2E cannot yet perform its required create-course step. No conversation, Agent run, study-session, assessment, misconception, review or explainable Feed API exists yet.

## Reusable modules and required boundaries

Reuse rather than duplicate:

- `Database`, the migration runner and request-scoped connections;
- `DocumentRepository`, `HybridRetrievalService`, `AnswerService`, citation validation, and authenticated PDF content;
- `ChatProvider` / embedding provider protocols and loopback guards;
- `LearningRepository` course/concept/task/mastery queries while it is split by domain;
- `update_bkt` as the first deterministic mastery primitive;
- `@keen/api-client` Zod parsing, `LearningCoreProvider`, React Query cache generation keys, `PdfCitationViewer`, and existing shell/Inspector components;
- the Rust sidecar supervisor and current packaging pipeline, without adding learning-domain logic to Rust.

The 979-line `app/main.py` must stop growing. New work goes into `app/routers`, `app/services`, and `app/repositories`. The 349-line `ConversationPage.tsx` is at the repository size boundary and must be split into message stream, composer, hooks and view components before durable conversation/session behavior expands it. Process-boundary payloads require Pydantic and Zod validation; tool input may not be free-form SQL, arbitrary JSON mutation or arbitrary file paths.

## Target architecture

```text
single Agent Orchestrator
        ↓
typed Tool Registry + permission policy
        ↓
deterministic learning services
        ↓
domain repositories + SQLite transaction
        ↓
durable events, tool audit and reversible state mutations
```

The model may interpret goals, choose registered tools, draft teaching text/questions/rubrics/summaries and propose misconception labels. Deterministic code owns state transitions, objective grading, normalized subjective scores, hint penalties, mastery values, misconception confirmation rules, FSRS dates, Feed priority, permissions, citations and persistence.

## New domain model and migration order

Status for migrations `009`–`017`: **verified** for forward migration, constraints, repositories, and legacy-row preservation. This is persistence evidence only; it does not claim that the HTTP learning loop or UI exists. Responsibilities remain separate even if implementation discovers that a compatibility table or follow-up index is necessary.

| Migration | New or extended entities | Compatibility and invariants |
| --- | --- | --- |
| `009_conversations.sql` | `conversations`, `messages`, `message_citations`, `message_attachments` | Message states `pending/streaming/completed/cancelled/failed`; attachments reference controlled local entities, not arbitrary paths; only unsent draft may remain outside SQLite |
| `010_agent_runs.sql` | `agent_runs`, `agent_steps`, `agent_events`, `tool_invocations`, `state_mutations`, `approval_requests` | Unique `(run_id, step_ordinal)` or an equivalent idempotency key; redact sensitive arguments and never log source document bodies or model hidden reasoning |
| `011_study_sessions.sql` | `study_sessions`, `study_plan_versions`, `study_units`, `study_checkpoints`, `study_session_events` | Event-log every state transition; optimistic `revision`; persisted current unit, plan version and `resume_from_status` |
| `012_assessments.sql` | `assessments`, `assessment_items`, `assessment_attempts`, `answer_evaluations`, `hint_events` | Immutable submitted answers/evaluations; current item and draft recovery; unique evaluation per submitted attempt/version; validated JSON |
| `013_mastery_evidence.sql` | `mastery_evidence`; additive version/evidence/session metadata for existing `mastery_events` | Preserve every old event; backfill a named legacy algorithm/version; every new mutation traces to evidence; never recreate the table |
| `014_misconceptions.sql` | `misconceptions`, `misconception_evidence` | Status checks, evidence counts, course/concept scope, no single error auto-confirms a long-term misconception |
| `015_review_items.sql` | `review_items`, `review_attempts`, `review_schedules` | FSRS state is separate from concept mastery; idempotent schedule writes; UTC timestamps and scheduler version |
| `016_study_plans.sql` | additive `study_tasks` source/priority/rationale/schedule/completion/feedback fields and `study_task_feedback` (the filename follows the requested migration sequence; its bounded responsibility is Feed/task planning state) | Preserve existing tasks/statuses with compatible backfill; store explainable priority components and source identity; no calendar write |
| `017_review_fsrs_identity.sql` | additive stable identity and validated adapter state for `review_schedules` | Preserve applied 015 data; backfill a unique positive `fsrs_card_id`; make pristine new rows restartable under the pinned Keen v1 scheduler; enforce identity/state agreement without rewriting migration 015 |

Every JSON text column must pass Pydantic/Zod validation at the boundary and `json_valid` where SQLite supports the invariant. Use foreign keys, status checks, indexes for recovery and due queries, transactionally consistent writes, and explicit `created_at`/`updated_at`. Migration tests must cover empty database, `001` legacy database, current `008` database with user rows, repeated startup, constraint failure and interrupted upgrade. No destructive reset is an accepted recovery action.

## Agent runs, tools and permissions

Status: **verified** for the persistence/permission repository boundary; the Agent orchestrator, registered product tools, SSE execution, Undo UI, and provider integration remain `not started`.

One orchestrator uses a typed `AgentTool` registry. Each invocation records permission level, validated arguments, bounded result summary, status and timing. A Level 2 write and its `tool_invocation`/`state_mutation` records commit in the same SQLite transaction. Replayed or recovered runs use the idempotency key and never repeat a completed mutation.

Initial tool groups:

- sources: search sources, get controlled source page/chunks, list course documents;
- concepts: list/get concepts, mastery evidence and misconceptions;
- study: create/read/advance/pause/resume/complete sessions and persist plan units;
- assessment: create validated items, submit answer, grade, request hint;
- learner state: record evidence, update mastery, record/resolve misconception;
- review: create item, record rating, schedule and list due items;
- tasks: create/update/complete/list recommended tasks.

Permission policy:

| Level | Behavior | Examples |
| --- | --- | --- |
| 1 | Automatic read or pure draft; no durable user-state mutation | retrieval, source page lookup, concept/mastery reads, due-review list, study-outline or assessment draft |
| 2 | Local reversible write with visible Undo and `state_mutations` audit | create session/assessment/review/task, record answer/evidence, pause or advance local learning state |
| 3 | Confirm before destructive or external action | destructive deletes, export/share, system calendar, cloud upload, email/LMS |

Level 3 infrastructure may exist, but calendar, cloud, email and LMS tools remain unavailable in this milestone. Existing document deletion must not be silently exposed as an automatic Agent tool. Documents are untrusted content and cannot become system/tool instructions.

## Deep Learn state machine

Status: **verified** for the provider-free transition primitive; session API,
repository orchestration, generated teaching content, and restart E2E remain
`not started`.

Canonical flow:

```text
draft
→ goal_confirmation
→ diagnosing
→ planning
→ studying
→ checkpoint
→ active_recall
→ practicing
→ summarizing
→ review_scheduling
→ completed
```

`paused`, `cancelled` and `failed` are explicit side states. Pausing persists `resume_from_status`; resuming returns only to a valid saved state. Illegal transitions fail without mutation. Cancellation records terminal/cancelled work but does not commit incomplete generated content. A prior streaming run is marked `interrupted` on startup and its session becomes paused/recoverable rather than falsely completed.

Session input persists goal, course, controlled document scope, estimated duration, teaching preference and target difficulty. Diagnostic uses 3–7 low-cost prerequisite questions and low evidence weight. A versioned plan has 2–8 editable units with objective, concepts, prerequisites, source chunks, estimate and checkpoint type. Each unit teaches with real citations, includes a checkpoint and asks for active recall before revealing the answer. Summary persists completed work, mastery evidence, misconceptions, errors, review schedule, next action and used sources.

## Assessment, hints and grading

Status: **verified** for provider-free objective grading, bounded rubric
normalization, final subjective scoring, and versioned hint penalties. Durable
assessment orchestration and HTTP/UI flows remain `not started`.

Supported item types: `single_choice`, `multiple_choice`, `true_false`, `fill_blank`, `short_answer`, and `step_by_step`. Generated drafts are rejected or regenerated unless they have a valid concept, current source chunks/pages, legal type/options/answer, complete rubric, bounded difficulty/max score and no obvious answer leakage. Source text is data, not generation policy.

Objective grading is deterministic:

- exact option identity for single-choice/true-false;
- canonical set comparison for multiple-choice;
- configured normalization and accepted-answer sets for fill-blank;
- no answer/feedback disclosure before submission.

For short-answer and step-by-step items, the model may return a schema-bounded rubric suggestion with criterion scores, detected errors and feedback. Deterministic code validates criterion IDs/ranges, caps the score, applies independence and hint penalties, records grader/prompt versions, and stores no hidden chain of thought.

Hints have four durable levels: direction, key concept, partial steps and near-complete solution. Every request writes `hint_events`. Penalty parameters are centralized and versioned; more assistance cannot increase evidence weight.

## Mastery and misconception rules

Status: **verified** for deterministic evidence weighting, weighted BKT input,
misconception merge/threshold/lifecycle rules, and algorithm/version validation.
Transactional assessment-to-evidence orchestration and learner UI remain
`not started`.

The first version adapts the existing BKT update but adds deterministic evidence weight from correctness, independence, hint level, difficulty, confidence calibration and response type. Central configuration—not prompts or scattered constants—defines weights. Initial target ordering is independent/high-difficulty > independent/ordinary > one hint > multiple hints > partial result > content read; a self-reported “I understand” has zero mastery weight.

Every accepted update must:

- constrain before/after to `[0, 1]`;
- reference immutable `mastery_evidence` rows and the triggering attempt/session;
- record algorithm and algorithm version;
- be idempotent and transactional with assessment/review/task effects;
- keep mastery separate from Review/FSRS scheduling.

The model may propose a misconception label/description. Deterministic rules merge candidates, count repeated equivalent errors, detect repeated distractors or failure steps, and increase confidence for confidently wrong answers. One error stays `suspected`; only rule thresholds or user confirmation may enter `confirmed`. Allowed lifecycle is `suspected → confirmed → improving → resolved`, with `dismissed` as an explicit alternative. Each transition remains evidenced and reversible where appropriate.

## FSRS review integration

Status: **verified** for the pinned adapter, migration 017, repository round
trip, deterministic ratings, UTC/state/version validation, and stable card
identity. Flashcards UI and assessment-to-review orchestration remain
`not started`.

Do not invent a scheduler. Integrate a mature, license-compatible Python FSRS implementation behind:

```python
class ReviewScheduler(Protocol):
    def new_schedule(self, *, card_id: int, now: datetime) -> Schedule: ...

    def review(
        self, *, current: Schedule, rating: Rating, reviewed_at: datetime
    ) -> Schedule: ...
```

Ratings are `again`, `hard`, `good`, and `easy`. Review items may come from a Deep Learn unit, wrong answer, confirmed misconception, user flashcard or editable Agent-generated flashcard. Persist difficulty, stability, state, due time, repetitions, lapses, last review, scheduler name/version and the originating evidence. Tests freeze UTC time and disable any fuzzing so expected schedules are reproducible.

The selected dependency is py-fsrs 6.3.1, exact wheel SHA-256
`ac1bf9939573592d8c9bc1e11a00bd17e04146dc9f2c913127e2bcc431b9040b`,
tag commit `3abe686e9c058d3f3c00bbeb92e68b71211b2b31`, MIT. It is pinned in
the runtime lock and isolated behind Keen's adapter; provenance, notices, and
packaging evidence are recorded in the repository inventory documents.

## Learning Feed

Status: **verified** for the deterministic, versioned priority calculation and
component/rationale output; live candidate generation, Feed actions, API and
UI mutation remain `not started`.

Real candidate sources are due FSRS reviews, deadline urgency, weak mastery, forgetting risk, prerequisite importance, unfinished/recoverable session, confirmed misconception and manual task. A deterministic planner computes:

```text
priority =
  deadline_urgency
  + forgetting_risk
  + mastery_weakness
  + prerequisite_importance
  + goal_alignment
  - effort_penalty
```

Weights and caps live in one versioned configuration with unit tests. Every result returns title, reason, course/concept/source, estimate, priority score and full component breakdown, deadline, current mastery and available actions. `Why this?` renders stored components rather than model-invented rationale.

Actions are Start, Complete, Snooze, Reschedule, Too easy, Too hard and Not relevant. Start creates or resumes a real session. Mutations use React Query invalidation or optimistic updates with tested rollback. Feedback is stored for later learner-persona work but this milestone does not build the persona product or write a system calendar.

## API and streaming contract

Status: **not started** for these additions.

Add separate routers/services/repositories for conversations, Agent, study sessions, assessments, mastery, reviews and learning Feed. Minimum resource APIs:

- courses: add authenticated `POST /v1/courses` with a typed request/response and repository uniqueness/error handling so E2E creates a real course instead of relying on demo seed;
- conversations: create/list/detail and post message;
- Agent: create/get/cancel run and durable run events;
- sessions: create/list/detail/start/pause/resume/advance/complete;
- assessments: create/detail, submit attempt, request hint;
- mastery: course/concept state and evidence reads;
- review: due list, create item and submit rating;
- Feed/tasks: explainable Feed read and task mutation.

All routes retain sidecar authentication. All frontend responses are Zod-validated. Agent SSE emits at least `metadata`, `status`, `tool_start`, `tool_result`, `content_delta`, `checkpoint`, `state_mutation`, `warning`, `done`, and `error`, without hidden reasoning or sensitive arguments. Durable event IDs permit reconnect/resume; database events, not Python memory, are the source of truth.

## Cancellation, recovery and concurrency

Status: **not started** for learning-loop operations.

Agent runs, session generation, Quiz generation, subjective grading and flashcard generation propagate cancellation from frontend `AbortController`, through disconnect-aware FastAPI tasks, to provider cancellation. An incomplete operation never writes a false completion. Completed reversible mutations remain audited.

Startup recovery marks active Agent streams interrupted, pauses affected sessions, preserves submitted attempts/evaluations, restores current Quiz item and does not duplicate Review schedules or tool invocations. Unsubmitted answer drafts require a deliberate persistence policy and must be scoped to their attempt/session. Session and attempt revisions reject stale concurrent writes. Listener cleanup and React Query keys include the sidecar generation so a restart cannot reuse invalid endpoint state.

## Frontend integration and truthful states

Status: **not started** for real Deep Learn, Quiz and Flashcards; Feed mutation and durable Conversation are **not started**.

Home, Learning Feed, Knowledge Base, Conversation, Deep Learn, Quiz and Flashcards are the only learning surfaces connected in this milestone. Planner, Memory and Visualize remain visibly future/demo surfaces. Each major live page must deliberately render empty, loading, partial, error, offline, permission-denied, provider-missing/rate-limited, cancelled and relevant sidecar/index/migration/recovery failures. Unavailable controls remain disabled and cannot produce fake loading or success feedback.

Deep Learn retains unit navigation, central cited teaching/checkpoint content and Inspector mastery/misconception/source/Agent activity. Quiz adds real navigation, hints, confidence, feedback, summary, mastery delta and review schedule. Flashcards adds due progress, source, editing and FSRS ratings. Conversation gains durable Ask/Teach/Study/Review/Plan modes and shows goal/scope/time/unit/source confirmation before a Study session is created.

## Test and Gate plan

### Gate 0 — branch and evidence baseline

Status: **in progress**.

- Branch `codex/milestone-learning-loop` exists from `094c44e`.
- Baseline checks recorded above passed.
- This plan, the parent implementation plan, visual backlog and changelog are being updated.
- Exit: documents reflect repository facts and no new dependency/provenance claim is made.

### Gate 1 — schema and repositories

Status: **verified** on 2026-07-16 for schema and repository scope.

- Apply migrations `009`–`017`; add typed repositories and transaction helpers.
- Test empty/legacy/current databases, existing-row preservation, JSON/status constraints, rollbacks, uniqueness, idempotency and recovery queries.
- Exit: forward migrations and repository tests pass without data deletion.

Evidence: the Gate 1 migration/repository subset passed 46/46 tests after independent review and remediation of trigger ordering, cross-course parent updates, nested audit redaction, permission fail-closed behavior, and composable transaction boundaries. The subsequent full Python suite, including concurrent deterministic-engine tests, passed 374/374 with one existing Starlette deprecation warning. Ruff lint and format checks passed for all 86 Python files. Independent final review found no remaining Gate 1 P0/P1. No HTTP, orchestrator, FSRS algorithm, or live frontend behavior is claimed by this evidence.

### Gate 2 — deterministic engine

Status: **verified** on 2026-07-16 for the provider-free algorithm and scheduler
scope.

- Test legal/illegal session transitions, objective grading, rubric bounds, hint penalties, evidence-weighted BKT, misconception thresholds, FSRS fixtures and Feed priority.
- Exit: all core algorithms pass with no LLM/provider.

Evidence: the current deterministic-engine focus passed 156/156 tests for the
study transition machine, objective/subjective grading, hint penalties,
evidence-weighted mastery, misconception rules, Feed priority, FSRS adapter and
Review repository. The FSRS/repository/migration/vector subset passed 43/43.
The stable full Python suite passed 500/500 with one existing Starlette
deprecation warning; Ruff lint and format checks passed all 97 learning-core
Python files, and `git diff --check` passed. Independent FSRS/provenance review
found no remaining P0/P1. This evidence does not claim Agent orchestration,
HTTP resources, frontend learning flows, or the vertical assessment-to-review
transaction.

### Gate 3 — Agent orchestrator

Status: **not started**.

- Test tool schemas, Level 1/2/3 policy, atomic audit/mutation, Undo, redaction, SSE ordering, cancel, reconnect and replay idempotency.
- Use a fixed automation-only provider; never substitute it in the real UI.
- Exit: every tool/mutation is traceable and no model path can write arbitrary state.

### Gate 4 — durable Conversation and Deep Learn

Status: **not started**.

- Test message history, goal/diagnostic/plan/unit/checkpoint/recall/summary, plan edits and pause/restart/resume.
- Start the integration path through real `POST /v1/courses`, then import and index a real source; no pre-seeded course may satisfy the create-course acceptance step.
- Reuse retrieval/citation/PDF viewer and explicitly separate course-source content, general model supplement and unknown content.
- Exit: real session restart E2E passes.

### Gate 5 — assessment, mastery, misconception and review

Status: **not started**.

- Test six item types, pre-submit secrecy, hint events, subjective normalization and transactional `evaluation → evidence → mastery event → misconception evidence → review/task`.
- Test FSRS rating/edit/delete boundaries and generated-card editability.
- Exit: answer-to-review vertical integration passes.

### Gate 6 — explainable Feed

Status: **not started**.

- Test candidate sources, deterministic breakdown, Start/Complete/Snooze/Reschedule/feedback, optimistic rollback and real session creation/resume.
- Exit: live Feed contains no seed substitution and every recommendation is explainable.

### Gate 7 — full acceptance and packaging

Status: **not started**.

- Python: formatting/lint/type checks where configured; migrations, repositories, permissions, sessions/recovery, grading, hints, mastery, misconceptions, FSRS, Feed, cancellation and full-loop pytest.
- TypeScript: lint, strict typecheck, unit/component/integration tests for real pages, mutations/rollback, Agent activity and restart recovery; Playwright/accessibility/visual checks where configured.
- Rust: fmt, clippy, cargo tests and only proportional lifecycle/cancellation additions if required; no new domain logic.
- E2E: execute the full 18-step path at the top with a real imported PDF and fixed automation provider.
- Packaging: rebuild arm64 sidecar, `.app` and `.dmg`; validate architecture, checksum, signing status, mounted authenticated smoke, source citation opening, shutdown and restart recovery. Developer ID/notarization remain separate unless credentials are actually available.
- Licenses: update locks, exact artifact/revision/license/notices and scans for every introduced dependency before shipping.
- Exit: link exact commands, pass/fail/skip totals and artifacts from `docs/IMPLEMENTATION_PLAN.md`; only then mark the milestone verified.

Performance acceptance includes usable session lists at 1,000 rows, paged/virtualized Agent events, on-demand mastery history, no full rendering of 100 Quiz details, no duplicate generation on page navigation and no heavyweight provider/scoring work on the event loop.

## Packaging impact

Status: **in progress**. The pinned FSRS dependency passed isolated lock,
license, import and PyInstaller one-file checks; the latest adapter/migration
still requires the final Gate 7 `.app`/`.dmg` rebuild and mounted smoke.

Python packages added for FSRS or learning services must enter the CPython 3.11/macOS arm64 PEP 751 lock with hashes, pass isolated PyInstaller import/native-extension checks and be present in mounted-DMG tests. Migrations `009`–`017` must be bundled and verified from an upgraded user database. New recovery/cancel behavior must not weaken the existing random-port/token/process-group lifecycle. Any release claim still requires actual Developer ID hardened-runtime signing and notarization; existing ad-hoc arm64 evidence is local verification only.

## Risks and mitigations

| Risk | Mitigation / acceptance |
| --- | --- |
| Legacy schema/data loss | Additive migrations, explicit backfills, migration fixtures from `001` and `008`, no database reset |
| Too many coupled states | Schema/repositories and deterministic services precede UI; illegal transitions and transaction rollback are tested |
| Duplicate work after restart | Durable events, revisions and idempotency keys around every tool/schedule mutation |
| Model controls learning truth | Restrict model output to typed drafts/suggestions; deterministic code owns scores, mastery, misconception state and due dates |
| Subjective grading variance | Bound rubric schema/ranges, normalize deterministically, store versions; do not claim fully deterministic model judgment |
| Cancellation leaves partial state | Propagate abort/disconnect/provider cancellation and commit domain writes atomically |
| Provider absent or failing | Fixed provider only in automation; real UI shows provider-missing/rate-limited/error and never fabricates completion |
| FSRS package/packaging failure | Adapter boundary, exact provenance/lock, frozen import check and mounted-DMG scheduling smoke |
| Oversized files | Split `main.py` and Conversation before adding behavior; feature folders and domain services remain bounded |
| Sensitive audit content | Store summaries/IDs, redact arguments, never log secrets, full document text or hidden reasoning |
| Visual/legal overreach | Use provisional design system only; no protected HyperKnow asset until canonical authorized scope and references exist |

## Explicit non-goals

Status: **not started by design**. Do not bring these into this milestone:

- multi-Agent discussion or delegation inside the product;
- cloud model API keys, cloud sync, multi-user, teacher or mobile products;
- Canvas, Moodle or other LMS; Google Drive, OneDrive or external uploads;
- system calendar writes, notifications, email, export/share or user-visible external programs;
- OCR, audio courses, automatic video, Manim or broad RAG/performance rewrites;
- Planner, learner Memory/Persona or Visualize product completion beyond truthful future/demo states;
- copying DeepTutor/OATutor UI or whole repositories, or any StudyFetch/AskSia code/assets;
- full HyperKnow pixel calibration or protected brand assets before authorized references and scope exist;
- Intel/Universal distribution, notarization or release signing unless separately authorized and actually verified.

## Completion rule

This milestone remains **in progress** until the full path is implemented, tested and linked as acceptance evidence. A static UI, schema-only change, fixed transcript, test-only provider response, isolated unit test, successful baseline check, or arm64 bundle by itself is not completion. Every unavailable surface must remain honestly labeled throughout implementation.
