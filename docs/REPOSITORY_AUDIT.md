# Repository Audit

## Audit snapshot

- Audit date: 2026-07-15 (Asia/Shanghai)
- Audited path: `/Users/a1-6/Documents/Keen`
- Branch: `main`
- Git state at initial inspection: repository initialized, no commits
- Git remote at initial inspection: none configured locally
- Non-Git files at initial inspection: none

This is a point-in-time Milestone 0 baseline. Other implementation work may land after this audit; contributors should update the status tables with evidence rather than rewrite the baseline.

## Executive summary

The initial repository contained only `.git` metadata. There was no application code, package manifest, dependency lockfile, test configuration, build configuration, documentation, reference material, license file, or authorized-scope file. Consequently:

- no page was implemented at audit time;
- no visual comparison could be performed;
- no third-party source or license could be verified from a local checkout;
- no dependency/license scan could run because no dependency manifests existed;
- no `.app` or `.dmg` build could be attempted;
- the supplied GitHub URL was not configured as a local remote.

The absence of references is not a reason to stop architecture and functional work, but it is a hard blocker for claims of HyperKnow pixel parity and for reuse of protected brand assets.

## Live follow-up during the first parallel work round

The repository changed while this governance audit was being written. The following is an observation of work in progress, not milestone completion:

- `origin` is now configured as `https://github.com/shawliu998/Keen.git`.
- `git ls-remote --heads origin` returned zero branch refs; the GitHub repository is still remote-empty at this check.
- The local branch remains `main` with no commits.
- Rust is installed: `rustc 1.97.0 (2d8144b78 2026-07-07)` and `cargo 1.97.0 (c980f4866 2026-06-30)`.
- Tauri/Rust source, a `Cargo.lock`, React/TypeScript source, Python source, and validation build artifacts have appeared through parallel implementation.
- Tauri source validation is **in progress**. File presence and `target/` artifacts do not by themselves prove that all tests, launch behavior, security gates, or packaging requirements pass.

## Reference inventory

| Expected path | Initial status | Impact / required action |
| --- | --- | --- |
| `references/` | Missing | Create only when real source material is supplied; do not fabricate references. |
| `references/hyperknow/` | Missing | No authorized screenshots, recordings, Figma exports, or assets available for comparison. |
| `references/notes/interaction-observations.md` | Missing | HyperKnow-specific behavior cannot be verified. |
| `references/authorized-scope.md` | Missing | One path named by the brief; protected assets cannot be reused without it. |
| `references/notes/authorized-scope.md` | Missing | A second path named by the brief; canonical location must be resolved. |

The brief is internally inconsistent about the authorized-scope path. Until the repository provides a canonical document, use neither location as implied permission.

## Required page coverage

“Reference” means a usable screenshot/recording/Figma export in the initial repository. “Implementation” means source code in the initial repository. Both columns were checked independently.

| Page or flow | Reference | Implementation | Initial conclusion |
| --- | --- | --- | --- |
| Shared macOS shell, Sidebar, Toolbar, Inspector | Missing | Missing | Provisional tokens may be used; parity unmeasurable. |
| Home / Agent | Missing | Missing | Orbie/brand artwork must not be invented or copied. |
| Learning Feed | Missing | Missing | Functional states and explainable recommendation copy still required. |
| Knowledge Base | Missing | Missing | Import/index/detail states still required. |
| Conversation and citation navigation | Missing | Missing | Streaming, rendering, trace, retry, and source-jump behavior still required. |
| Deep Learn Session | Missing | Missing | Must be a resumable structured session, not renamed chat. |
| Quiz / Practice | Missing | Missing | Hint/scaffold and deterministic mastery evidence still required. |
| Flashcards | Missing | Missing | FSRS review state still required and separate from mastery. |
| Study Planner | Missing | Missing | Calendar writes require confirmation. |
| Memory / Learner Persona | Missing | Missing | Evidence, edit, delete, and disable controls still required. |
| Visualize / Instruction Video | Missing | Missing | Phase 1 diagram/SVG/export; Manim is later-phase only. |
| Settings | Missing | Missing | Provider configuration and non-revealing secret UI still required. |

## Engineering inventory at initial inspection

| Area | Status | Missing evidence |
| --- | --- | --- |
| Tauri/Rust shell | Not present | `Cargo.toml`, Tauri config, capabilities, tests, native build |
| React/TypeScript UI | Not present | package manifest, strict tsconfig, routes, components, tests |
| Design tokens | Not present | measured reference values and provisional token implementation |
| Python learning core | Not present | package metadata, API, typed modules, tests, sidecar build |
| SQLite/migrations | Not present | schema, migrations, repository tests, restart persistence |
| PDF/RAG | Not present | parser, indexing, retrieval, citations, viewer integration |
| Agent runtime | Not present | orchestrator, tools, approvals, trace, cancellation, streaming |
| Visual regression | Not present | manifest, seed, capture runner, current/diff artifacts |
| CI/quality gates | Not present | lint, typecheck, test, accessibility, security jobs |
| Packaging | Not present | sidecar binary, entitlements, signing strategy, `.app`/`.dmg` evidence |

The table above intentionally preserves the initial empty-repository baseline. Current parallel work has introduced candidate implementations in several areas; their owners must update milestone status only after reporting exact validation commands and results.

## Legal and provenance findings

1. No upstream repository was checked out under this repository at the initial audit.
2. No source file had been copied from DeepTutor, OATutor, HyperKnow, or another third party.
3. No local upstream `LICENSE` or `NOTICE` was available to inspect.
4. Therefore no exact license or source commit SHA is asserted in this audit.
5. Candidate reuse is documented separately in `docs/OPEN_SOURCE_INVENTORY.md`; candidates are not incorporated dependencies.

## Immediate gates

- **Can proceed:** repository scaffolding, secure process boundaries, data contracts, deterministic demo data, provisional design tokens, non-branded page structure, tests, and local persistence.
- **Blocked pending references:** screenshot-derived color/spacing values, page-specific pixel matching, brand/Orbie use, and the requested `<3%` mismatch result.
- **Blocked pending checkout and license verification:** any copying or porting of DeepTutor/OATutor code and any license-specific notice language.
- **Blocked pending real builds/tests:** launch, test, performance, `.app`, `.dmg`, and recovery claims.

## Audit follow-up checklist

- Add the intended GitHub remote and record its URL without overwriting local work.
- Supply `references/hyperknow/`, interaction observations, and one canonical authorized-scope file.
- Inventory every supplied reference by page, viewport, capture date/version, and authorization status.
- Run dependency and license scans once manifests/lockfiles exist.
- Update this audit or add a dated follow-up after scaffolding and after references arrive.

## First-round follow-up — 2026-07-15

- `origin` is now configured to `https://github.com/shawliu998/Keen.git`; the remote still exposes no branch refs. Local work remains uncommitted and unpushed.
- Tauri/React/Python source, lockfiles, tests, visual tooling, and governance files now exist. See `docs/IMPLEMENTATION_PLAN.md` for current evidence rather than the initial empty-repository tables above.
- Frontend lint/typecheck/build and 5 tests pass; Python has 6 passing tests; Rust fmt/clippy and 3 tests pass.
- A 1440×920 Home current screenshot exists, while visual comparison remains blocked by missing authorized references.
- Actual arm64 development `.app` and `.dmg` bundles were produced and the DMG checksum verified. They are ad-hoc, unnotarized, and omit the Python sidecar.
- Resolved dependency metadata/security reports now exist under `artifacts/license-scan/`; notice reconciliation remains incomplete and blocks release distribution.
