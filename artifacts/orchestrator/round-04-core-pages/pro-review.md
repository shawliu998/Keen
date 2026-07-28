# Keen core learning loop — ChatGPT Pro review

Date: 2026-07-27

## Evidence supplied

- Same-viewport qualitative DeepTutor/Keen comparison:
  `artifacts/ui-audit/2026-07-27/core-pages-parallel/01-reference-final-contact.png`
- Product and implementation boundary: local-first Tauri 2 + React/strict
  TypeScript + Python sidecar; one source-scoped request → path → reading →
  recall → feedback/remediation → Feed/History/Review loop.
- Verification reported to Pro: 10 desktop files / 136 tests, strict
  typecheck, ESLint, `git diff --check`, strict app signature verification and
  bundled-sidecar smoke.

## Round 1

Pro returned `SHOULD-FIX (near ACCEPT)` with no must-fix item. Its only
substantive gap was whether Keen merely looked agentic or actually persisted a
decision loop. It recommended exposing why an incorrect recall produces source
review, why a correct/remediated recall produces practice, and why a Review
item is due.

## Executor finding and implementation

The repository already contained the authoritative adaptive loop:
active-recall scoring creates a persisted adaptive action in the same
transaction, with `policy_version`, `reason_code`, `revision` and idempotent
completion. Codex did not add another orchestration layer. The UI now exposes
that saved decision in Deep Learn, and explains Review timing from the real
item source, FSRS state, repetitions and lapses.

## Round 2

Pro returned `ACCEPT` and stated that no blocker remained for presenting Keen
as a DeepSeek AGI core-business management-trainee portfolio project. It
accepted the closed chain:

`observe → diagnose → decide → intervene → remember`

The review is advisory evidence, not a substitute for repository tests,
packaged-app inspection or user research.
