# Upstream Patch Ledger

## Current state

As of the initial 2026-07-15 audit, Keen contained no vendored, copied, ported, or patched upstream source. There are no upstream patches to report. A later read-only audit used temporary `/tmp` checkouts to verify DeepTutor and OATutor parent revisions/licenses; neither checkout was placed in Keen and no source was copied, ported, or patched. Review-only SHAs belong in `docs/OPEN_SOURCE_INVENTORY.md`, not as patch entries here.

Do not add placeholder or guessed SHAs. Planning candidates belong in `docs/OPEN_SOURCE_INVENTORY.md`, not in this ledger.

The sqlite-vec 0.1.9 integration is an unmodified package dependency at exact tag commit `e9f598abfa0c06b328d8fe5da9c3760cce74be10`. No sqlite-vec source file is copied, ported, vendored, or patched in Keen, so it has no patch entry; its artifact, native-library, license, and PyInstaller collection evidence is recorded in `docs/OPEN_SOURCE_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`.

The pdfminer.six 20260107 integration is an unmodified package dependency at exact tag commit `9e1243c4ad000bf9bbe60e81fc8dde2fccc0ed3b`. No pdfminer.six or pyHanko source file is copied, ported, vendored, or patched in Keen, so it has no patch entry; its exact wheel, main MIT license, and separate MIT notice for pyHanko-derived elements are recorded in `docs/OPEN_SOURCE_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`.

The HTTPX 0.28.1 integration is an unmodified package dependency at exact tag commit `26d48e0634e6ee9cdc0533996db289ce4b430177`. No HTTPX source file is copied, ported, vendored, or patched in Keen, so it has no patch entry; its exact wheel, license, transitive-resolution snapshot, and Python 3.11/PyInstaller evidence are recorded in `docs/OPEN_SOURCE_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`.

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
