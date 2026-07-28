# Upstream Patch Ledger

## Current state

As of the initial 2026-07-15 audit, Keen contained no vendored, copied, ported, or patched upstream source. There are no upstream patches to report. A later read-only audit used temporary `/tmp` checkouts to verify DeepTutor and OATutor parent revisions/licenses; neither checkout was placed in Keen and no source was copied, ported, or patched. Review-only SHAs belong in `docs/OPEN_SOURCE_INVENTORY.md`, not as patch entries here.

Do not add placeholder or guessed SHAs. Planning candidates belong in `docs/OPEN_SOURCE_INVENTORY.md`, not in this ledger.

The sqlite-vec 0.1.9 integration is an unmodified package dependency at exact tag commit `e9f598abfa0c06b328d8fe5da9c3760cce74be10`. No sqlite-vec source file is copied, ported, vendored, or patched in Keen, so it has no patch entry; its artifact, native-library, license, and PyInstaller collection evidence is recorded in `docs/OPEN_SOURCE_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`.

The pdfminer.six 20260107 integration is an unmodified package dependency at exact tag commit `9e1243c4ad000bf9bbe60e81fc8dde2fccc0ed3b`. No pdfminer.six or pyHanko source file is copied, ported, vendored, or patched in Keen, so it has no patch entry; its exact wheel, main MIT license, and separate MIT notice for pyHanko-derived elements are recorded in `docs/OPEN_SOURCE_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`.

The HTTPX 0.28.1 integration is an unmodified package dependency at exact tag commit `26d48e0634e6ee9cdc0533996db289ce4b430177`. No HTTPX source file is copied, ported, vendored, or patched in Keen, so it has no patch entry; its exact wheel, license, transitive-resolution snapshot, and Python 3.11/PyInstaller evidence are recorded in `docs/OPEN_SOURCE_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`.

The py-fsrs 6.3.1 integration is an unmodified package dependency at exact tag commit `3abe686e9c058d3f3c00bbeb92e68b71211b2b31`. No py-fsrs source file is copied, ported, vendored, or patched in Keen, so it has no patch entry; its exact wheel, MIT license, runtime-dependency boundary, Python 3.11/PyInstaller evidence, and Keen-owned adapter are recorded in `docs/OPEN_SOURCE_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`.

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

### Appica UI: bounded visual-system adaptation

- Canonical repository: `https://github.com/appica-dev/appica-ui`
- Upstream commit: `26de9b1e02d2fb48694ae52d2371b1bbd71ee9d6`
- Verified license: MIT; exact root `LICENSE` read from the detached checkout;
  no root `NOTICE` found
- Original paths:
  - `packages/react/src/components/button/button-variants.ts`
  - `packages/react/src/components/field/field.tsx`
- Keen paths:
  - `packages/ui/src/index.tsx`
  - `packages/design-tokens/src/tokens.css`
  - `apps/desktop/src/styles.css`
- Integration type: specification-level visual adaptation; no upstream source
  file is copied or vendored
- Why a package/adapter was insufficient: the published React package assumes
  Tailwind and Base UI, while Keen already has a small typed component package
  and a global token/CSS system. Installing the package would create a second
  styling and primitive runtime for the same controls.
- Modifications: express Appica's non-wrapping buttons, control scale, soft
  surfaces, hover/press motion, focus treatment, cards, badges, progress and
  field composition through Keen's existing classes and tokens. Keen-specific
  semantic colors, reduced-motion behavior, component props and learning
  contracts remain authoritative.
- Preserved notices/headers: Appica's MIT notice is reproduced in
  `THIRD_PARTY_NOTICES.md`; no source headers existed in the reviewed files.
- Tests: strict TypeScript, ESLint, 79 focused desktop tests, the production
  frontend build and `git diff --check` passed. Home and Learning Feed were
  inspected at 1280×800; Deep Learn was inspected at 1180×760 with no
  horizontal overflow, wrapped shared-button labels or browser-console errors.
  Evidence is under
  `artifacts/ui-audit/2026-07-25/appica-primitives/`.
- Update strategy: re-review an immutable upstream revision before importing
  any additional Appica component or changing this adaptation boundary.
- Known divergence/risks: the public Figma link currently exposes its thumbnail
  page through the connected API, not the underlying component library; Keen
  therefore does not claim component-instance or pixel parity.

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
