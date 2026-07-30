# Authorized Reference Scope

This file is the canonical authorization record for visual-reference work in
this repository. `references/notes/authorized-scope.md` is not canonical.

## Authorization record

- Authorized by: the Keen project user directing this repository through Codex.
- Recorded: 2026-07-16 (Asia/Shanghai).
- Authorized source: `https://agent.hyperknow.io/`.
- User instruction: screenshots may be captured and page or visual elements may
  be copied for Keen while work continues.
- Additional user instruction recorded 2026-07-16: Codex may read the currently
  visible page, take and save screenshots, continue clicking, scrolling and
  navigating, and use content that was visible immediately before the instruction
  as an implementation reference without asking again for each ordinary action.
- User attestation recorded 2026-07-16: the user states that permission has been
  obtained to capture protected content for research-only, non-redistributed use.
  This statement is recorded as user-attested and has not been independently
  verified from documentary evidence.
- Additional user instruction recorded 2026-07-19: Codex may upload one
  synthetic, non-personal audit fixture to the authorized HyperKnow account and
  inspect/capture the visible upload, processing, result, settings, motion and
  interaction states for Keen's internal UI research. This authorizes the
  external upload of that fixture only; it does not authorize uploading Keen
  data, personal files, account data or third-party content.
- Additional user instruction recorded 2026-07-19: Codex may continue ordinary
  clicks, navigation and uploads needed to inspect a complete learning flow and
  may test better learning interactions without repeated confirmation. For the
  follow-up run, the only new payload was the synthetic, non-personal fixture
  `references/audit-fixtures/hyperknow-learning-flow-sample.txt`. This remains a
  user attestation for internal research; it does not authorize bulk extraction,
  personal-data retention, calendar/Drive/Canvas connection, sharing or deletion.
- Additional user instruction recorded 2026-07-19: for a fuller synthetic-flow
  test, Codex may generate clearly synthetic model prompts/results and may inspect
  the reachable citation, mastery, review-plan, calendar, Drive, Canvas and file
  processing states. Synthetic calendar/integration actions are authorized when
  they do not require retaining unrelated private content. Account identifiers,
  existing cloud files, existing calendar events and LMS course data must not be
  retained in screenshots or copied into Keen. Any Keen-side simulation remains
  visibly labeled Browser Demo / Sample and is not evidence that a live provider
  or integration is implemented.
- Additional user instruction recorded 2026-07-19: for the Figma screen-audit
  pass, Codex may inspect all design-relevant visible pages, buttons and
  interactions and upload the synthetic, non-personal fixture
  `references/audit-fixtures/keen-figma-flow-audit.txt`. Retained evidence is
  bounded to `references/hyperknow/2026-07-19-figma-screen-audit/`. Account
  identity, existing personal conversations and saved memory remain excluded;
  no integration OAuth flow, destructive delete, share or sign-out is authorized
  by this entry.

## Allowed use

- Capture the publicly visible, non-user-specific states reachable from the
  authorized source without bypassing authentication.
- Interactively inspect user-authorized states already visible in the live browser;
  do not retain account identifiers, personal information or user-generated
  learning content in screenshots or implementation notes.
- Capture and analyze protected visual content covered by the user's attested
  permission for internal research and Keen implementation only.
- Store screenshots under `references/hyperknow/` as internal design and visual
  regression references.
- Measure and adapt layout, spacing, typography, color, borders, states and
  interaction organization into Keen source code.
- Crop reference details for internal comparison and create derived,
  Keen-branded implementations.
- Use `references/audit-fixtures/hyperknow-ui-audit-sample.txt` as the only
  upload payload for the 2026-07-19 flow audit, if the site accepts that format.
- Use `references/audit-fixtures/hyperknow-learning-flow-sample.txt` as the only
  additional upload payload for the documented complete-flow follow-up under
  `references/hyperknow/2026-07-19-complete-flow/`.
- Use `output/pdf/hyperknow-bayesian-learning-fixture.pdf` as the only additional
  upload payload for the documented full synthetic-flow follow-up under
  `references/hyperknow/2026-07-19-full-synthetic-flow/`. The PDF is generated
  from `references/audit-fixtures/create_hyperknow_bayesian_fixture.py` and
  contains no personal or third-party content.
- Use `references/audit-fixtures/keen-figma-flow-audit.txt` as the only
  additional upload payload for the documented Figma screen audit under
  `references/hyperknow/2026-07-19-figma-screen-audit/`.

## Excluded use

- Do not bypass login, automate bulk extraction, inspect authenticated states
  outside the user-attested scope, inspect browser storage, or capture another
  person's account or learning data.
- Do not embed the live HyperKnow site or copy its implementation code.
- Do not ship HyperKnow trademarks, logos, user content or reference screenshots
  in Keen release artifacts unless a later authorization entry explicitly adds
  that redistribution scope.
- StudyFetch and AskSia remain organization-only inspiration as required by
  `AGENTS.md`; this authorization does not apply to them.

## Evidence requirements

Every captured reference must record its source URL, capture timestamp,
viewport, display scale, visible state, local path and any crop or modification.
Pixel-parity claims still require a fixed Keen seed/viewport and an actual
visual-diff result. A missing or authentication-blocked state is not a pass.
