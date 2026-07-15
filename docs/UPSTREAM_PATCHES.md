# Upstream Patch Ledger

## Current state

As of the initial 2026-07-15 audit, Keen contained no vendored, copied, ported, or patched upstream source. There are no upstream patches to report. A later read-only audit used temporary `/tmp` checkouts to verify DeepTutor and OATutor parent revisions/licenses; neither checkout was placed in Keen and no source was copied, ported, or patched. Review-only SHAs belong in `docs/OPEN_SOURCE_INVENTORY.md`, not as patch entries here.

Do not add placeholder or guessed SHAs. Planning candidates belong in `docs/OPEN_SOURCE_INVENTORY.md`, not in this ledger.

## Recording rules

Create an entry before or in the same change that introduces modified upstream source. One entry may cover a coherent patch series only when all files share the same upstream revision and license.

Required fields:

- component and canonical repository URL;
- exact upstream commit SHA;
- locally verified license and notice paths;
- original source paths and Keen destination paths;
- integration method and reason dependency/adapter reuse was insufficient;
- detailed modifications, including security or API boundary changes;
- retained copyright headers/notices;
- test commands and results;
- update/rebase strategy and known divergence;
- corresponding `THIRD_PARTY_NOTICES.md` and inventory entries.

## Patch entries

None.

<!--
### <component>: <short purpose>

- Canonical repository: <url>
- Upstream commit: <full SHA verified from checkout>
- Verified license: <identifier/name and local LICENSE path>
- Original paths:
  - `<path>`
- Keen paths:
  - `<path>`
- Integration type: copied | ported | vendored | patched submodule
- Why a package/adapter was insufficient: <reason>
- Modifications: <specific changes>
- Preserved notices/headers: <locations>
- Tests: `<command>` — <result/date>
- Update strategy: <how to compare/rebase>
- Known divergence/risks: <items>
-->
