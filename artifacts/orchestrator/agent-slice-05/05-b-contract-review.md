# Agent Slice 05-B contract review

Date: 2026-07-27

## Actual code supplied to the reviewer

- two existing immutable procedures:
  `source-grounded-rephrase@1` and `source-grounded-example@1`;
- `test_me_instead` already bypasses the model for canonical Practice;
- Active Recall has no meaningful hint signal;
- Diagnostic persists an exact zero-weight `user_report` evidence value:
  `not_yet=0.0`, `partial=0.5`, `confident=1.0`.

## Accepted rule

The Pro orchestrator returned `05-B CONTRACT ACCEPT` for exactly:

```text
intent == explain_differently
AND no predecessor artifact
AND exact current-Unit Diagnostic user-report score == 0.0
→ progressive-hint@1
```

Every other existing intent mapping remains unchanged. A successor
`explain_differently` request selects the existing rephrase rather than
repeating the hint.

The reviewer required:

- deterministic host selection, never model policy choice;
- the exact current-Unit evidence ID and score in frozen provenance;
- the existing artifact contract, profile, Practice and lineage;
- fall back to rephrase when Diagnostic evidence is missing;
- no learner trait, efficacy or causal interpretation;
- no new UI, API, schema, analytics or Candidate extraction.

## Codex compatibility addition

Before completion, Codex identified that extending the context fingerprint
could hide already persisted intervention runs after upgrade. The
implementation therefore accepts the old fingerprint only when the historical
run input lacks `diagnosticSelfReport`. New runs always freeze and revalidate
the new evidence-aware fingerprint.

## Validation

- 58 focused intervention/Diagnostic/Recall/migration tests passed;
- the complete learning-core suite passed 1144 tests;
- scoped Ruff check and format check passed;
- `git diff --check` passed.

The only warning was the existing Starlette/httpx deprecation warning.

## Final decision and stop boundary

The Pro orchestrator returned `05-B FINAL ACCEPT` with no must-fix items.
It initially proposed another generic selection branch. Codex vetoed that
expansion because all remaining listed signals were either constant, already
consumed, or retrieval-capability facts rather than evidence of a distinct
learner need.

The Pro orchestrator accepted the veto:

- stop Playbook-selection expansion after 05-B;
- do not implement 05-C;
- return to Slice 4's one remaining non-empty packaged Session restart truth
  gate.

This prevents an arbitrary heuristic from being presented as Agent-native
adaptation.
