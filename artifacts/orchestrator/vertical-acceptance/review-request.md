# Keen vertical acceptance — Pro review request

Date: 2026-07-27
Scope: the default product slice only — choose source scope → submit a focused
learning request → receive a visible two-unit path → complete guided
study/Recall/Practice → schedule Review → return after a full app/sidecar
restart.

## Execution boundary

- Codex inspected the repository, implemented the smallest concrete repairs,
  ran the commands, drove the native packaged app, and retained technical veto.
- ChatGPT Pro receives this repository-derived evidence for decision and
  review; it has not been represented as having direct filesystem or database
  access.
- No ZIP or guessed path was used. The exact worktree was
  `/Users/a1-6/.codex/worktrees/d309/Keen`.
- The dedicated acceptance app is
  `apps/desktop/src-tauri/target/release/bundle/macos/Keen Vertical Acceptance.app`
  with bundle ID `com.keen.learning.vertical-acceptance`.
- Its isolated profile is
  `/Users/a1-6/Library/Application Support/com.keen.learning.vertical-acceptance`.

## Native journey performed

1. Imported and indexed
   `artifacts/orchestrator/vertical-acceptance/eigenvectors.md`, then linked it
   to `Calculus I`.
2. Submitted a focused-study goal and received a visible two-unit plan.
3. Completed the opening diagnostic and entered the first persisted lesson.
4. Quit and restarted the packaged app/sidecar; Home restored one exact
   `Next up` action and reopened the same Session.
5. Answered the first Recall incorrectly. The host selected the bounded
   `progressive-hint@1` Playbook from real diagnostic/Recall evidence.
6. The isolated profile had no configured provider. Keen truthfully showed
   `provider_missing`, preserved the source-review fallback, and never claimed
   a generated explanation artifact.
7. Completed source review and Practice, restarted during the Practice
   transition, and restored the authoritative pending/current Practice instead
   of the obsolete provider fallback.
8. Completed the second lesson, Recall, and Practice; reached Summary and used
   `Finish and schedule review`.
9. Verified the completed Session, one due Review item, Home's `Review now`,
   and one saved History record after another full app/sidecar restart.

Session ID:
`focused-session-7638c0a9-8cd1-5f2c-a9a6-f8b80c812a5f`.

After the final restart, read-only SQLite inspection showed:

| Record | Count |
| --- | ---: |
| `study_sessions` | 1 |
| `study_active_recall_runs` | 2 |
| `study_practice_runs` | 2 |
| `review_items` | 1 |
| `agent_runs` | 1 |
| `study_adaptive_actions` | 3 |

The Session remained `completed`, revision `14`, progress `1.0`, with no
current Unit and `finished_at=2026-07-27T08:08:11.604860+00:00`. The same
counts were observed before and after restart; no duplicate Session, Recall,
Practice, Review, Agent run, or adaptive action was created.

## Concrete defects found and repaired

1. A persisted `provider_missing` intervention could mask a newer pending
   Practice action. Deep Learn now gives the authoritative persisted Practice
   state priority and suppresses the obsolete intervention gate.
2. Cold restore could wait circularly on the old intervention gate while
   hiding the intervention, or fail to restore a started Practice run after its
   adaptive action was consumed. Canonical `practicing` state and a current
   Practice outcome now restore as Practice.
3. Lesson, Recall, Practice, and Review copy could expose raw `\(...\)`
   delimiters. `FormattedMathText` now renders the bounded inline syntax as
   accessible native MathML; matrices and vectors retain their existing path.
4. The deterministic two-unit source split could cut the word `factors.`
   between units. It now chooses the nearest viable whitespace boundary while
   retaining evidence for Recall and distinct Practice in both halves.

No navigation, provider authority, mastery/FSRS algorithm, migration, external
integration, or third-party UI dependency was added.

## Verification

- Focused desktop regression: 4 files / 50 tests passed.
- Desktop strict TypeScript passed.
- Desktop ESLint passed.
- Focused source-split Python API regression: 20/20 passed.
- `git diff --check` passed.
- `scripts/build-sidecar.sh` completed successfully.
- Final ad-hoc arm64 Tauri `.app` build completed successfully and ad-hoc
  signed both executables and the app bundle.
- Final cold launch reported `Learning core ready` and restored the one due
  Review action from the isolated profile.
- Final bundled executable hashes:
  - learning core:
    `1f02a6519c2e13a49705579ca85095e8dd51463e597c89e6f8a5e722b97d75e1`
  - desktop:
    `75cae8ac0340230b7eea96d188dcb848cbf89da8faa94c71bc225f849de3fec1`

Known non-blocking limits:

- The Vite production build retains its existing large-chunk warning.
- Focused Python tests retain the existing Starlette/httpx deprecation warning.
- Because the isolated profile intentionally had no provider, this run proves
  truthful provider-missing recovery and persisted Playbook selection, not a
  successful model artifact or downstream model-output lineage.
- The app is ad-hoc signed; Developer ID and notarization are not claimed.
- Screenshots are native acceptance evidence, not a pixel-parity or visual-diff
  claim.

## Native evidence

- `01-indexed-source.jpeg`
- `02-visible-plan.jpeg`
- `03-first-unit.jpeg`
- `04-restart-home-next-up.jpeg`
- `05-restored-session-route.jpeg`
- `06-provider-missing-recovery.jpeg`
- `07-practice-cold-restore.jpeg`
- `08-pending-practice-cold-restore.jpeg`
- `09-summary-ready.jpeg`
- `10-session-complete.jpeg`
- `11-review-queue.jpeg`
- `12-history-after-restart.jpeg`
- `13-review-mathml.jpeg`

## Decision requested from Pro

Return one strict verdict:

- `ACCEPT` if this evidence closes the default end-to-end guided-learning slice
  and the next work should be a separately bounded real-provider acceptance;
  or
- `REJECT` with only concrete P0/P1 defects that are reproducible from this
  evidence.

Also state whether any proposed next step would improperly expand architecture
or UI scope before this slice is accepted.
