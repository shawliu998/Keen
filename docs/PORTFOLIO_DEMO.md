# Keen portfolio demo

This three-minute walkthrough follows Keen's complete local-first learning
loop, from an indexed source to an adaptive intervention and a persisted next
action.

## One-sentence product

Keen is a local-first macOS learning Agent that turns a learner's own material
into a persistent study path, observes deterministic learning evidence, and
proposes a bounded plan change without allowing a model to grade, mutate
mastery, or rewrite the curriculum on its own.

## Three-minute walkthrough

### 0:00–0:30 — Start from real material

1. Open **Knowledge Base**.
2. Show one indexed source linked to a course.
3. Start **Focused study** with a concrete goal.

What this proves: the learning scope is explicit and source-grounded. The
Agent is not answering from an unbounded generic chat context.

### 0:30–1:15 — Show the guided learning loop

1. Answer the opening self-report.
2. Read the bounded lesson and its source reference.
3. Answer Recall incorrectly.

What this proves: Recall scoring and learning-state updates are deterministic
domain operations. The model does not decide whether the learner is correct.

### 1:15–2:15 — Show the Agent-native difference

1. Ask Keen to **Explain differently**.
2. Show the provider-backed, source-grounded explanation.
3. Show the inline proposal **Agent suggested · not applied** and its
   evidence-backed “Why now”.
4. Select **Accept adjustment**.
5. Complete the canonical Practice and continue.

What this proves: Keen closes an Agent loop:

```text
Observe evidence
→ choose one bounded intervention
→ use the model with validated source context
→ propose a prerequisite
→ wait for learner acceptance
→ append a new plan version
→ continue the owned learning flow
```

Autonomy lives in observation, timing, source-bounded explanation, and
proposal. Deterministic code and the learner retain authority over grading,
mastery, scheduling, and plan writes.

### 2:15–3:00 — Prove persistence and continuity

1. Open **Learning Feed** and show the same task at its real persisted
   progress.
2. Open **History** and show the current unit and next action.
3. Quit Keen completely, relaunch it, and resume the Agent-inserted unit.

What this proves: Feed, History, Deep Learn, Agent runs, plan versions,
Practice, and recovery read the same SQLite-backed truth. A restart does not
replay the provider call or fabricate completion.

## Architecture talking points

- **Tauri 2 + React/strict TypeScript** owns the macOS client and validated
  loopback API boundary.
- A supervised **Python learning-core sidecar** binds only to `127.0.0.1`,
  authenticates each request, persists to SQLite, and survives app restart.
- The Agent runtime persists runs, steps, events, source handles, validated
  artifacts, approvals, and idempotency identities.
- Deterministic learning services own Recall evaluation, mastery evidence,
  FSRS scheduling, adaptive eligibility, and plan application.
- Provider configuration is explicit. Source content sent to the configured
  provider is disclosed at the point of action.

## What the Agent owns

Keen owns the learner's source scope, session state, evidence, deterministic
evaluation, intervention policy, proposal contract, approval boundary,
versioned mutation, Undo, Feed/History projection, and cold recovery.

The model may produce a bounded explanation or proposal artifact. It cannot
invent learning evidence, write mastery, silently change a plan, or claim that
an unavailable provider succeeded.

## Current release scope

The local Alpha is focused on one coherent macOS learning journey: personal
course material, guided Study, adaptive help, Practice, Review, and reliable
continuity. The current build is intended for local installation and product
evaluation.
