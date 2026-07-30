# Agent Slice 05-A orchestrator review

Date: 2026-07-27

## Decision

`STATUS: ACCEPT`

The Pro orchestrator accepted immutable exposure lineage as the correct first
Slice 5 increment and accepted that it records association, not causal
effectiveness.

Accepted invariants:

- a matching durable artifact checkpoint is the only visibility gate;
- lineage without publication remains hidden;
- multiple intervention artifacts may point to one canonical Practice;
- raw learner answers do not enter the projection;
- the public completed-Review summary remains redacted;
- tests use the internal outcome and Review repositories rather than widening
  the public API.

## Codex technical correction

The initial review simultaneously allowed the latest Review attempt and asked
that a later revision not be returned. Codex rejected that contradiction:
FSRS revision changes on the same Review item are the real later lifecycle.

The Pro orchestrator accepted the corrected contract:

```text
practice_run_id
→ study_summary_review_handoffs.review_item_id
→ latest review_attempt within that exact review_item_id
```

The query must never select a session-, course-, concept- or time-window-wide
latest attempt. Internal `review_revision_before` and
`review_revision_after` fields make the selected attempt explicit. A later
attempt on another Review item cannot contaminate the lineage.

## Rejected scope

- frozen Review revisions in the lineage table;
- causal-attribution or effectiveness fields;
- wider public completion fields;
- new schema layers, UI, lineage graph, Agent console or audit framework;
- automatic Playbook optimization before real outcome evidence.

## Final evidence review

After implementation, Codex returned:

- 46 focused intervention/migration/Summary/Review tests passed;
- the complete learning-core suite passed 1141 tests;
- scoped Ruff check and format check passed;
- `git diff --check` passed.

The Pro orchestrator returned `AGENT SLICE 05-A FINAL REVIEW —
STATUS: ACCEPT` with no must-fix items. It assigned one next work package:
Slice 05-B may add exactly one deterministic built-in Playbook-selection
increment inside the existing Deep Learn contracts, without combining Slice 4
packaging, Candidate extraction, analytics, new UI or public API expansion.
