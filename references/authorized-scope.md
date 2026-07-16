# Authorized Reference Scope

This file is the canonical authorization record for visual-reference work in
this repository. `references/notes/authorized-scope.md` is not canonical.

## Authorization record

- Authorized by: the Keen project user directing this repository through Codex.
- Recorded: 2026-07-16 (Asia/Shanghai).
- Authorized source: `https://agent.hyperknow.io/`.
- User instruction: screenshots may be captured and page or visual elements may
  be copied for Keen while work continues.

## Allowed use

- Capture the publicly visible, non-user-specific states reachable from the
  authorized source without bypassing authentication.
- Store screenshots under `references/hyperknow/` as internal design and visual
  regression references.
- Measure and adapt layout, spacing, typography, color, borders, states and
  interaction organization into Keen source code.
- Crop reference details for internal comparison and create derived,
  Keen-branded implementations.

## Excluded use

- Do not bypass login, scrape authenticated/private pages, inspect browser
  storage, or capture another person's account or learning data.
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
