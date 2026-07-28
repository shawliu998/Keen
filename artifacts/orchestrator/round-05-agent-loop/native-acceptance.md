# Round 05 native acceptance — Adaptive Prerequisite Intervention Loop

Date: 2026-07-27
Classification: verification subordinate to the implemented product slice

## Boundary

This run verifies the real packaged macOS flow for one isolated learner
profile:

```text
persisted low-confidence Diagnostic
+ deterministic incorrect Recall
+ validated DeepSeek LearningIntervention artifact
→ one adaptive prerequisite proposal
→ learner Accept
→ append-only plan version 2
→ learner Undo
→ append-only recovery version 3
→ full quit and cold recovery
```

It does not claim learning efficacy, fixed-reference visual parity, packaged
Dark/reduced-motion coverage, Developer ID signing or notarization.

## Isolated runtime

- App:
  `apps/desktop/src-tauri/target/release/bundle/macos/Keen Provider Acceptance.app`
- Bundle identifier: `com.keen.learning.provider-acceptance`
- Profile:
  `~/Library/Application Support/com.keen.learning.provider-acceptance`
- Desktop executable SHA-256:
  `eea2c98fb19f1d5704b37c86df83c05f8df0fc14d3729f52daf695fb349735c4`
- Bundled learning-core SHA-256:
  `4e4eeabac57b527a649a1d62a431ff82b579eeb53eb54c86ad25d72ba7af478a`
- `codesign --verify --deep --strict --verbose=2` passed.

The isolated provider configuration was already present with file mode `0600`.
The app and sidecar were fully stopped before the database baselines were
read.

## Authoritative identities

- Course:
  `course-b3014472961f4de3ab7cd6731dd2c887`
- Study Session:
  `focused-session-cdb204c7-94a2-550b-a628-6cd2b37aa9f0`
- Learning Intervention run:
  `run-db37e1a21a034efeb547524c266779cf`
- Adaptive proposal run:
  `run-67a71681b1c6408884f22efa4f1ceacf`
- Proposal:
  `plan-proposal-2a91002bdfc9d1d5fd235385442ef58c`
- Validated proposal artifact:
  `plan-proposal-artifact-4cb836b5dc04cc1ac7283d44556c9ac9`

Both Agent runs completed through the configured `openai-compatible`
`deepseek-v4-flash` provider and each owns six durable events. Exactly one run
has `mode = plan`.

## Native observations

All screenshots are 1203×768:

1. [`01-agent-suggested-not-applied.png`](native/01-agent-suggested-not-applied.png)
   shows the restored Recall and validated Learning Agent explanation at the
   top of the same document before the proposal was accepted. Computer Use's
   accessibility read of that live state also exposed `Agent suggested · not
   applied`, the reason, three saved evidence items, one cited source, and the
   learner-owned Accept/Keep choices below the visible fold. The screenshot
   itself does not place those lower controls in the viewport.
2. [`02-adjustment-saved-plan-v2.png`](native/02-adjustment-saved-plan-v2.png)
   shows `Adjustment saved`, plan version 2, the delayed application boundary,
   and the real `Undo adjustment` action.
3. [`03-adjustment-undone-plan-v3.png`](native/03-adjustment-undone-plan-v3.png)
   shows `Adjustment undone` and recovery plan version 3 after invoking Undo.
4. [`04-cold-restart-undone-restored.png`](native/04-cold-restart-undone-restored.png)
   shows the same undone receipt and plan version 3 after a complete `⌘Q`,
   sidecar shutdown, cold app launch, Home continuity handoff, and exact
   Session restoration.

The Keep path was not fabricated by resetting or mutating this accepted
evidence chain. It remains covered by component and service tests; this native
run exercises the higher-risk append/Undo/restart path.

## Persistence and duplicate-call check

After Undo and before cold launch:

- proposal status: `undone`;
- base / accepted / undo plan versions: `1 / 2 / 3`;
- Study Plan Proposal rows for the Session: `1`;
- Agent runs for the Session: `2`;
- durable Agent events for those runs: `12`.

After the cold launch restored Deep Learn and the app was fully quit again,
the same query returned:

- proposal status: `undone`;
- base / accepted / undo plan versions: `1 / 2 / 3`;
- Study Plan Proposal rows for the Session: `1`;
- Agent runs for the Session: `2`;
- durable Agent events for those runs: `12`.

The three append-only plan rationales are:

1. the original deterministic two-Unit plan;
2. `Accepted source-grounded prerequisite`;
3. `Undo restored the previous unstarted sequence`.

Therefore cold recovery did not create another proposal, another plan-mode
provider run or additional Agent events.

## Related implementation evidence

- Python proposal/intervention tests: 28 passed.
- Desktop proposal/intervention/Active Recall tests: 45 passed.
- API-client contract tests: 9 passed.
- The production frontend build passed with the existing large-chunk warning.
- Strict TypeScript, ESLint, Ruff check/format and `git diff --check` passed at
  implementation review.
- The first complete desktop run overlapped the production build and reported
  544/556; the six affected files subsequently passed 146/146 in one isolated
  rerun. This record does not rewrite that first run as a complete-suite pass.
- ChatGPT Pro returned `ACCEPT FINAL IMPLEMENTATION`; see
  [`pro-review.md`](pro-review.md).

## Acceptance

The packaged native acceptance gate for the bounded Adaptive Prerequisite
Intervention Loop is closed:

```text
Observe → Decide → Propose → Learner Accepts → Persist → Undo → Recover
```

Further same-loop UI polishing, another proposal branch, a new Agent surface,
or a second planning framework is not required for this product slice.
