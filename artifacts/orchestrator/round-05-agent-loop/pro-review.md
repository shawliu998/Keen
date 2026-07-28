# Round 05 — Adaptive Prerequisite Intervention Loop

Date: 2026-07-27

## Scope reviewed

ChatGPT Pro reviewed the bounded implementation of this loop:

```text
saved Diagnostic + deterministic Recall + validated intervention artifact
→ server-side eligibility decision
→ source-grounded prerequisite proposal
→ learner Accept / Keep
→ versioned persistence / Undo / cold recovery
```

The review was explicitly limited to the current code contract. Packaged
WebView evidence, a real adaptive-provider screenshot and pixel parity were not
presented as completed or as blockers for this review.

## Technical correction accepted before implementation

Pro accepted these corrections to its first proposal:

- reuse `agent_runs` and `study_plan_proposals` instead of adding a candidate
  table;
- trigger only from opening self-report `<= 0.4`, an incorrect deterministic
  Active Recall and a validated source-grounded Learning Intervention
  checkpoint;
- propose only before the nearest future unstarted Unit;
- keep plan writes behind the existing Accept / Keep / Undo boundary.

Its three implementation requirements were:

1. eligibility must be decided only by learning-core;
2. automatic start must be idempotent and bound to Session/plan revision;
3. only a validated intervention artifact may unlock the proposal.

## Evidence supplied for final review

- Python proposal/intervention tests: 28 passed.
- Desktop proposal/intervention/Active Recall tests: 45 passed.
- API-client contract tests: 9 passed.
- The first complete desktop run overlapped the production build and reported
  544/556 with resource-sensitive failures across six files. After the build
  finished, those exact six files passed 146/146 in one isolated rerun.
- Strict TypeScript, ESLint, Ruff check/format and `git diff --check` passed.
- The production frontend build passed with the existing large-chunk warning.

## Final decision

Pro returned:

> ACCEPT FINAL IMPLEMENTATION

It explicitly found all three requirements satisfied and accepted the
implementation as a genuine bounded Agent-native loop:

```text
Observe
→ diagnostic + Recall + validated intervention evidence
→ Decide
→ server-side adaptive trigger
→ Act
→ validated Study Plan Proposal
→ Learner Control
→ Accept / Keep / Undo
→ Persist + Recover
```

It found no model authority over grading, mastery, BKT, FSRS, Task/Session
completion or plan application, and no new planner, memory or parallel Agent
system. It also accepted that Agent autonomy is expressed in evidence-based
timing and proposal, while deterministic domain code and learner approval own
state changes.

This record is an orchestration review, not independent empirical evidence of
learning efficacy, packaged native behavior or visual parity.

## Post-review packaged acceptance

The separately bounded native observation is now complete and recorded in
[`native-acceptance.md`](native-acceptance.md). A real isolated packaged app
showed the DeepSeek-backed proposal before application, persisted Accept as
plan version 2, persisted Undo as recovery version 3, restored the same undone
receipt after a full app/sidecar cold restart, and retained unchanged counts of
one proposal, two Session Agent runs and twelve durable events. This adds
packaged-behavior evidence; it does not change or overstate the Pro decision.
