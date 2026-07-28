# Agent Slice 05-A review request

Date: 2026-07-27

Repository supplied to the reviewer:

`/Users/a1-6/.codex/worktrees/d309/Keen`

The Pro orchestrator was told it had no repository access and must not invent
paths or interfaces. Codex remained the local executor with technical veto.

The bounded review covered:

- migration `032_learning_intervention_outcomes.sql`;
- immutable intervention-artifact → canonical-Practice exposure lineage;
- published-checkpoint visibility;
- later deterministic Practice and exact Review-item lifecycle projection;
- public completion-summary redaction;
- one failing test that incorrectly expected a private Review identifier in
  the public completion summary.

Requested decisions:

1. accept, modify or reject exposure lineage as Slice 5's first increment;
2. assess crash-between-write-and-publish truthfulness;
3. define the exact Review-attempt join invariant;
4. choose private `ReviewRepository` testing or a wider public contract;
5. restrict required changes to P0/P1/P2 without new UI or platform scope.
