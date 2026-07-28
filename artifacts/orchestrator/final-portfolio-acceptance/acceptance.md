# Final portfolio acceptance — source to adaptive continuation

Date: 2026-07-27
Classification: product acceptance with proportional implementation verification

## Boundary

This isolated run verifies one coherent native Keen journey:

```text
create course
→ import and index one real local source
→ request focused study
→ opening self-report
→ deterministic incorrect Recall
→ real DeepSeek source-grounded explanation
→ evidence-backed prerequisite proposal
→ learner Accept
→ append-only plan version 2
→ canonical Practice
→ resume the inserted unit
→ persisted Feed and History projection
```

This does not claim learning efficacy, reference-product pixel parity,
Developer ID signing, notarization, OCR, or broad autonomous curriculum
planning.

## Isolated runtime

- App:
  `apps/desktop/src-tauri/target/release/bundle/macos/Keen Portfolio Acceptance.app`
- Bundle identifier: `com.keen.learning.portfolio-acceptance`
- Profile:
  `~/Library/Application Support/com.keen.learning.portfolio-acceptance`
- Desktop executable SHA-256:
  `339bfaeafc5caed1b0cf7bb8999fb982b9fbf5a3a514ea6d07451cc60b5a042f`
- Bundled learning-core SHA-256:
  `4e4eeabac57b527a649a1d62a431ff82b579eeb53eb54c86ad25d72ba7af478a`
- Provider:
  `openai-compatible · deepseek-v4-flash` at loopback
  `http://127.0.0.1:4000/`
- Provider configuration file mode: `0600`
- Signature:
  local ad-hoc; `codesign --verify --deep --strict --verbose=2` passed after
  replacing Tauri's invalid temporary bundle signature.

## Authoritative identities

- Course:
  `course-e3364c76da8b446ea683f6f7d2957ced`
- Indexed document:
  `doc-a0ca0a39263e4030b7dee32b9c19fc7d`
- Study Session:
  `focused-session-1375be4e-d86d-514b-9d49-90ff33fd327e`
- Originating Task:
  `focused-task-a0b6bbc5-90d6-568c-a477-98205f71d381`
- Learning Intervention run:
  `run-fb4d0a88300b4976a93e24244ef3e984`
- Adaptive proposal run:
  `run-f540534209df48b7b91540a4c4489992`
- Proposal:
  `plan-proposal-b871e8f197c364d229469d7dca1185b8`

The source is `indexed` with one persisted chunk. The provider configuration
contains only provider, endpoint, and model; it has no plaintext secret.

## Native journey observed

1. Settings saved, restarted, and tested the provider as
   `Connected openai-compatible · deepseek-v4-flash`.
2. Knowledge Base created **Linear Algebra**, imported
   `eigenvectors.md`, linked it to the course, and completed local lexical
   indexing.
3. Focused Study created the goal **Explain eigenvectors and help me recall
   the eigenvalue equation.**
4. The opening self-report recorded low confidence without changing mastery.
5. The first Recall answer was deterministically scored `0 / 1`.
6. **Explain differently** completed a real source-grounded DeepSeek run and
   one adaptive proposal run.
7. The learner selected **Accept adjustment**. The proposal status became
   `accepted` and the plan advanced from version 1 to version 2.
8. The exact remediation and Practice actions both completed.
9. Continuing opened Unit 2 of 3, **Eigenvalue equation refresher**:
   [`01-agent-inserted-unit.png`](native/01-agent-inserted-unit.png).
10. History showed the same Session at 33% with its current and next units:
    [`02-history-after-agent.png`](native/02-history-after-agent.png).

The first Feed observation exposed a product truthfulness defect: Task Detail
said `Not started` because it projected only Task status and ignored the
originating Study Session. The final implementation queries the existing
course-scoped Session history only for the selected live Study task, then
renders `Checking…`, real percent, `Complete`, `Unavailable`, or `Not started`
according to the authoritative read. It does not add an N+1 list query or a
new backend contract.

The same observation also exposed raw inline math delimiters in persisted unit
objectives. Deep Learn, learning-path preview, proposal objective, and source
review now reuse the bounded native MathML renderer already used for lesson
content.

## Persistence state before final cold observation

- Session: `studying`, progress `0.333`, revision `8`.
- Current Unit:
  `unit-72b86898db3048719cfd20b1b69651a4`,
  **Eigenvalue equation refresher**.
- Plan versions: `1`, then accepted `2`.
- Proposal rows: `1`.
- Agent runs: `2`, both completed.
- Agent events: `14`, contiguous within each run.
- Active Recall runs: `1`.
- Practice runs: `1`.
- Adaptive actions:
  one completed remediation and one completed Practice.

## Verification

- `npm test --workspace=@keen/desktop`:
  47 files / 558 tests passed.
- Focused Feed suite:
  25 / 25 passed.
- Focused math, Deep Learn, adaptive review, and proposal suites:
  49 / 49 passed.
- Strict TypeScript: passed.
- ESLint with `--max-warnings 0`: passed.
- `git diff --check`: passed.
- Production frontend and Tauri `.app` build: passed, with the existing Vite
  large-chunk warning.
- Strict deep signature verification after local ad-hoc re-sign: passed.
- Bundled-sidecar smoke: authenticated readiness, jobs, cancellation, CJK,
  many-to-many course links, sqlite-vec, PDF geometry/content, token handling,
  and full process cleanup passed.

Existing non-failing test output includes React Router v7 future-flag
warnings, one React `act` deprecation warning, and the Node PDF legacy-build
notice. They are not rewritten as clean output.

## Acceptance boundary

The portfolio slice demonstrates the intended Agent-native product difference:
the system observes durable learning evidence, decides eligibility in host
code, invokes a model only with bounded source context, validates the returned
artifact, proposes a plan change, waits for learner acceptance, persists an
append-only version, and resumes through the ordinary learning workflow.

The final native cold-start Feed and Deep Learn observations are recorded only
after the rebuilt WebView has been inspected; database state and component
tests are not substituted for that native observation.
