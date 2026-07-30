# Keen real-provider acceptance — Pro review request

Date: 2026-07-27
Scope: the existing intervention/Playbook → verified artifact → canonical
Practice → immutable outcome-lineage path only.

## Isolated environment

- App:
  `apps/desktop/src-tauri/target/release/bundle/macos/Keen Provider Acceptance.app`
- Bundle ID/profile: `com.keen.learning.provider-acceptance`
- Profile:
  `/Users/a1-6/Library/Application Support/com.keen.learning.provider-acceptance`
- No user database or learning record was copied.
- Native Settings saved only:
  - `provider=openai-compatible`
  - `endpoint=http://127.0.0.1:4000/`
  - `model=deepseek-v4-flash`
- The local gateway owns its external credential. No credential was read,
  copied, logged, placed in the repository, or returned to Pro.
- The saved non-secret configuration is mode `0600`. Native Provider test
  returned `Connected openai-compatible · deepseek-v4-flash`.

## Real native journey

1. Imported and indexed `eigenvectors.md`.
2. Created `Linear Algebra`, linked the indexed source, and submitted:
   `Explain eigenvectors and help me recall the eigenvalue equation.`
3. Received a persisted two-Unit focused path.
4. Recorded Diagnostic `not_yet`.
5. Answered the first Recall incorrectly.
6. Selected `Explain differently`.
7. The host selected `progressive-hint@1`; the real
   `deepseek-v4-flash` provider returned one contract-validated,
   source-grounded artifact and one canonical independently scored Practice.
8. Fully quit the app and sidecar, rebuilt from the repaired source, restarted
   twice, and opened the exact Session from Home.
9. The same Agent artifact and exact pending Practice restored together.
10. A final full quit left no acceptance app or sidecar process.

Session:
`focused-session-cdb204c7-94a2-550b-a628-6cd2b37aa9f0`

## Exact persisted binding

- Agent run:
  `run-db37e1a21a034efeb547524c266779cf`
- Artifact:
  `artifact-307bc95869d19386b649301f782479db`
- Trigger Recall:
  `active-recall-run:4f76dc29-f897-5600-99b0-cc92fa6f8d3f`
- Practice:
  `practice-run:468b3e92-4097-58cb-9939-46ec97cad466`
- Unit:
  `focused-session-cdb204c7-94a2-550b-a628-6cd2b37aa9f0:unit:1`
- Source handle:
  `source-05ef47aad5c99c671bcec45d03b5f7ef`
- Source chunk:
  `chunk-version-a53370bb02a44bd38e4ce11b3b2c888a-0`
- Source chunk hash:
  `3aefe0dc7671f3c3095736ec6d1040c0028133f447a1903afcd5fe786dbfc20c`
- Playbook definition hash:
  `b302b4e75263ea96a65212c3e2f69ad7f61d6aa98def654a09f01c1563024f80`

The immutable `learning_intervention_outcomes` row binds that exact run,
artifact, Recall, Practice, Session, Unit, `progressive-hint`, version `1`, and
definition hash. The published artifact's `whatNext.practiceRunId` is the same
Practice ID and its source entry retains the same handle/chunk/hash. No causal
learning-efficacy claim is made.

## Restart and duplication evidence

After the final restart and again after the final full quit:

| Record | Count |
| --- | ---: |
| `agent_runs` | 1 |
| `agent_events` | 6 |
| `learning_intervention_outcomes` | 1 |
| `study_practice_runs` | 1 |
| `study_active_recall_runs` | 1 |

The Session remains truthfully `practicing`, revision `7`, with Unit 1 current
and the exact Practice `pending`. The six Agent events remain one metadata, one
content delta, one checkpoint, two status, and one done event. No provider
execution, artifact, Practice, or lineage was duplicated by restart, rebuild,
route restore, or Provider retest.

## Concrete defects found and repaired

1. A successful verified artifact was hidden after its generated Practice
   became current. The earlier stale-fallback repair was too broad. Deep Learn
   now keeps the intervention restore probe mounted, hides only obsolete
   failure/source-review fallback, and restores a verified artifact beside its
   exact current Practice.
2. Real provider Markdown used `\[...\]` and `\(...\)` notation. The display
   equation and inline `A`, `v`, and `lambda` now reuse bounded accessible
   native MathML; no math dependency or new design system was added.

No UI route, schema, Playbook, coordinator, analytics, Agent platform, provider
authority, grading, mastery, or FSRS behavior changed.

## Verification

- Focused desktop regression: 4 files / 52 tests passed.
- Strict TypeScript passed.
- Desktop ESLint passed.
- `git diff --check` passed.
- Final ad-hoc arm64 Tauri app build and ad-hoc signing passed.
- Final cold native restore showed:
  - `Learning core ready`;
  - one exact `Continue practice` Home action;
  - `Agent completed`;
  - the verified artifact;
  - accessible `A v equals lambda v` MathML;
  - the exact pending Practice in the same document flow.
- Final executable hashes:
  - desktop:
    `289bf8deba2fe928d1c738fc7e7b2982cf18257fa51df71a063c95d08d8cb865`
  - learning core:
    `1f02a6519c2e13a49705579ca85095e8dd51463e597c89e6f8a5e722b97d75e1`

Native screenshots:

- `01-home-cold-restore.jpeg`
- `02-artifact-practice-mathml.jpeg`
- `03-provider-connected.jpeg`

Known non-blocking limits:

- The app is ad-hoc signed, not Developer ID signed or notarized.
- The Vite build retains its existing large-chunk warning.
- React Router focused tests retain existing v7 future-flag warnings.
- The Practice is deliberately pending so the artifact/Practice binding
  remains directly inspectable; no efficacy or completed Review claim belongs
  to this package.
- Screenshots are native evidence, not pixel-parity or visual-diff evidence.

## Decision requested

Return:

- `A) ACCEPT` if the bounded real-provider acceptance is closed; or
- `B) REJECT` with only concrete reproducible P0/P1 defects.

If accepted, state whether further UI/architecture expansion remains stopped
and name at most one next bounded product package, or `STOP` if no higher-value
package is justified now.
