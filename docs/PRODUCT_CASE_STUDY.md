# Designing Keen

## From “AI study assistant” to a learning Agent

Keen began with a deliberately practical goal: build a learning product that
looks and behaves like a real macOS application, then use it to answer a harder
product question.

> What should an Agent own in a real learning process?

My role covered product framing, interaction architecture, Agent boundaries,
acceptance criteria, implementation orchestration, and native product review.
Model-assisted engineering was an implementation multiplier; product
decisions and acceptance gates remained human-owned.

## The problem I chose

Learning from personal course material involves more than generating an
answer. The learner still needs a reliable way to decide:

- which material is in scope;
- what to do next;
- whether an explanation actually led to understanding;
- when a failed attempt should change the teaching approach;
- how to resume after closing the app.

Keen gives that workflow one continuous home. The learner keeps the cognitive
work—Recall, Practice, rating, and consequential choices. The Agent carries
context, source scope, intervention timing, plan continuity, and recovery.

## The product bet

Keen turns a learner’s own material into a guided path and maintains one
authoritative next action across Home, Deep Learn, Learning Feed, History, and
Review.

The Agent intervenes only when the saved learning evidence supports it:

```text
bounded source
→ learner goal
→ visible study path
→ real Recall
→ deterministic evaluation
→ source-grounded intervention
→ learner-approved plan change
→ Practice
→ persisted next action
```

The model can explain or propose. It cannot grade the learner, write mastery,
schedule Review, mark work complete, or silently rewrite the plan.

## Five decisions that shaped the product

### 1. One clear creation entry

Keen begins with **New learning**. Home asks for intent, source scope, and goal
before exposing one specific action. Quiz, flash cards, and visual explanation
remain learning-step types inside the same journey.

This was an information-architecture decision, not a cosmetic cleanup.

### 2. Source scope before prompt cleverness

The learner chooses a course and indexed material before starting focused
study. Citations resolve back to durable local source snapshots. Partial or
unavailable source states remain visible instead of being replaced by a
plausible model response.

This keeps the product’s trust model understandable: the learner knows what
Keen may use before the Agent acts.

### 3. Agent-native means a closed loop

The Agent lives inside the study loop:

1. observe an authoritative learning event;
2. select one bounded teaching action in host code;
3. assemble exact source and session context;
4. run the configured provider with a narrow tool profile;
5. validate the returned artifact and source handles;
6. return the work to the learner;
7. use the next independent attempt as evidence;
8. persist and restore one next action.

The visible result is quiet: a better explanation, a clear “why now,” or one
bounded prerequisite proposal at the moment it is useful.

### 4. The model proposes; the domain applies

A failed Recall may justify an alternate explanation. Repeated, persisted
evidence may justify changing the plan. Neither justifies giving the model
write access to learning state.

Keen therefore separates:

- generated explanation and proposal artifacts;
- deterministic eligibility, grading, BKT, FSRS, and completion;
- learner-owned Accept, Keep, and Undo;
- append-only plan versions and durable receipts.

This produced a stronger interaction than a generic approval modal: the
learner sees what will change, why Keen is suggesting it, which sources support
it, and when the change takes effect.

### 5. Recovery is part of the product

Keen restores the exact Session, current Unit, pending Practice, Agent
artifact, plan version, Feed progress, History record, and next action from
SQLite-backed state. Idempotency and reconciliation prevent a reconnect from
silently repeating a provider call or learning-state write.

Cold recovery became a product acceptance criterion, not only an engineering
test.

## A coherent product language

Keen uses one information hierarchy across the learning workspace:
course scope first, a visible learning path, a bounded reading column, one
current action, and source detail on demand. Reading, Recall, Practice, Feed,
and History all project the same persisted Session state.

## Interaction principles

The interface follows a small set of product contracts:

- at most two persistent Study columns;
- a 65–75ch reading measure;
- one primary action per task;
- native MathML for bounded notation and plain-language answer entry;
- Feed and History must project the same Session truth;
- the Agent explains its intervention inline and stays out of primary
  navigation.

## What works today

- create a local course and import PDF, Markdown, or text material;
- index and search the bounded source locally;
- start a source-scoped Ask or focused Study request;
- generate and restore a multi-unit learning path;
- complete opening reflection, lesson, Recall, source review, Practice,
  Summary, and FSRS Review handoff;
- run a real provider-backed alternate explanation after an incorrect Recall;
- produce one evidence-backed prerequisite proposal;
- Accept, Keep, or Undo a versioned plan change;
- resume through Home, Learning Feed, History, or Review after a full restart.

The current evidence verifies product continuity and contract behavior across
the complete local learning loop.

## How I evaluated it

I used native macOS journeys rather than treating component screenshots as
product acceptance. The final acceptance profile created a course, imported
and indexed one source, completed a real Recall → Agent → Accept → Practice
path, and restored the inserted Unit through Feed and History.

Verification includes:

- deterministic and provider-backed paths;
- explicit provider-missing and recovery states;
- strict TypeScript and ESLint;
- desktop component and integration suites;
- Python API, migration, retrieval, learning, and Agent tests;
- bundled sidecar lifecycle and authenticated loopback smoke;
- native app restart with duplicate-run and duplicate-event checks.

The concise walkthrough is in
[`PORTFOLIO_DEMO.md`](PORTFOLIO_DEMO.md). Exact implementation and evidence
boundaries remain in
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

## What I would test next

The next valuable step is not another feature.

I would put the same difficult Recall task in front of 6–8 self-directed
learners and compare:

- a generic **Explain another way** action;
- Keen’s specific intervention showing why it is acting, which source it will
  use, and what the learner must do next.

The key questions are whether learners understand the intervention boundary,
whether the next unassisted Practice improves, and whether delayed Review
holds. Preference for the generated explanation alone is not enough.
