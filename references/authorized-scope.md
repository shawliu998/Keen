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
