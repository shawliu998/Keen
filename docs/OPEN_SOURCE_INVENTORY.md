# Open-Source Inventory

## Snapshot and interpretation

At the initial 2026-07-15 repository audit there were no dependency manifests, lockfiles, vendored sources, submodules, upstream checkouts, or third-party source files. Therefore the **incorporated inventory was empty** and no dependency-license scanner could run.

The matrix below is a planning register. A row marked `candidate` is not approval, incorporation, attribution, or a statement that the reviewed source is distributed with Keen.

## Read-only upstream audit (not incorporated)

On 2026-07-15, both requested upstreams were shallow-cloned under `/tmp/keen-upstream-audit.r2uEIA/` for read-only inspection. Nothing from these checkouts was copied into Keen. The SHAs below identify only the revisions reviewed; they are not selected dependency revisions and do not prove that Keen contains either project.

| Upstream | Review SHA | Revision metadata | License evidence read in full | NOTICE/header findings | Incorporation state |
| --- | --- | --- | --- | --- | --- |
| `HKUDS/DeepTutor` | `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a` | Exact tag `v1.5.1`; commit date `2026-07-09T23:23:27+08:00` | Root `LICENSE`: Apache License 2.0; appendix identifies copyright 2025 Data Intelligence Lab, The University of Hong Kong | No tracked top-level `NOTICE`; a tracked-text header search outside assets/lockfiles found only the README's pointer to the root Apache-2.0 license | Temporary `/tmp` review checkout only; not copied, vendored, installed, imported, or distributed by Keen |
| `CAHLR/OATutor-LLM-Learner` | `0d376e23302485bebef6e1cad04da3816a164cd6` | No exact tag; commit date `2025-02-01T19:44:32-05:00` | Root `LICENSE`: MIT License; copyright 2023 Zachary A. Pardos (`@zpardos`) – CAHL research lab | No top-level project `NOTICE`; `src/util/enumify.js` contains its own MIT text and copyright 2020 Axel Rauschmayer; generated `src/kas.js` points to Khan/KAS but contains no license grant; tracked `node_modules` contain many dependency license/notice files | Temporary `/tmp` review checkout only; not copied, vendored, installed, imported, or distributed by Keen |

Audit commands included shallow/filtered `git clone`, `git rev-parse HEAD`, `git show -s`, full reads of each root `LICENSE`, tracked-file searches for `LICENSE`/`NOTICE`/copyright headers, source-tree inspection, and `git status` verification. Both temporary checkouts were clean after review.

OATutor's `src/content-sources/oatutor` is a non-initialized git submodule pointing at gitlink `270ce04096a39b3412a8e08bc626bdce99c0f495`. Its README describes separately licensed/attributed content, but that submodule's license files and per-item attributions were not read because the submodule was not checked out. Therefore no OATutor content, hint text, problem, image, or parameter set is approved for reuse by this audit.

## Live dependency follow-up

Parallel implementation has since introduced `apps/desktop/package.json`, `services/learning-core/pyproject.toml`, `apps/desktop/src-tauri/Cargo.toml`, a root npm `package-lock.json`, and a Rust `Cargo.lock`. There is not yet a Python lockfile in the observed worktree. Tauri and related Rust crates are being validated, but their presence is not a completed license review.

The following dependency families are now declared and must be scanned/reconciled before release:

| Ecosystem | Declared families | Resolution evidence | License verification |
| --- | --- | --- | --- |
| Rust | Tauri 2, Tauri build/dialog/window-state plugins, serde, rand, base64, thiserror, tempfile | `Cargo.lock` exists | Cargo metadata captured for 443 resolved cross-platform packages; 442 reported SPDX-like license metadata and the only null-license package is Keen itself. Manual distributed-target notice reconciliation remains open. |
| JavaScript | React, React DOM/Router, TanStack Query, Zustand, Zod, Lucide, Tauri API, Vite, TypeScript, Vitest, Testing Library, jsdom, ESLint, Playwright/pixelmatch tool | Root `package-lock.json` exists | `npm query` captured 307 unique external resolved packages with license metadata; the six null-license entries are internal Keen workspaces. Runtime npm audit reported zero known vulnerabilities. |
| Python | FastAPI, Pydantic, Uvicorn; dev: httpx, pytest, pytest-cov; local audit tools | Resolved `.venv` report exists, but no committed Python lockfile | `pip-licenses` captured the resolved environment. After upgrading pip/setuptools/pytest, `pip-audit` reported zero known vulnerabilities; reproducible runtime-only locking and notice reconciliation remain open. |

No license names are asserted for these dependencies until verified from the exact resolved artifacts. Add final dependency records after locks are stable; the candidate matrix below still describes the larger reuse decision set.

## Candidate reuse matrix

| Candidate | Potential Keen use | Preferred integration boundary | Checkout / copy status | License status | Decision gate |
| --- | --- | --- | --- | --- | --- |
| `HKUDS/DeepTutor` | Agent loop, tool registry, RAG/ingestion, memory, quiz, guided learning, research, visualization | Do not depend on the complete package for the first release; selectively adapt only bounded modules after a file-level decision | Reviewed at the SHA above in `/tmp`; **not copied or introduced** | Apache-2.0 verified for the reviewed parent revision; transitive dependency and asset rights still require separate review | Record exact source/destination paths and modifications before any later port; re-verify if the chosen source revision changes. |
| `CAHLR/OATutor-LLM-Learner` | Hint/scaffold progression and BKT reference behavior | Specification-level reimplementation behind Keen's deterministic mastery/tutoring interfaces | Reviewed at the SHA above in `/tmp`; **not copied or introduced** | MIT verified for the reviewed parent revision; embedded third-party files and separate content submodule require their own review | Do not copy content or legacy UI; create independent tests for BKT edge cases and hint-evidence weighting. |
| `KaTeX/KaTeX` | Inline/block math rendering | Package dependency behind message renderer | Not installed | Pending lockfile/revision verification | Verify package license/notice and rendering/accessibility needs. |
| `open-spaced-repetition/free-spaced-repetition-scheduler` | FSRS flashcard scheduling | Package dependency behind a domain scheduling interface | Not installed | Pending lockfile/revision verification | Verify exact package/version/license; preserve separation from concept mastery. |
| `mozilla/pdf.js` | PDF rendering/navigation | Package dependency behind document viewer | Not installed | Pending lockfile/revision verification | Verify worker/bundling behavior and required notices. |
| `run-llama/llama_index` or relevant LlamaIndex package | Optional ingestion/retrieval building blocks | Python dependency behind retrieval interfaces | Not installed | Pending exact package/version verification | Compare weight/sidecar packaging to focused local implementations; inspect transitive deps. |
| `pymupdf/PyMuPDF` / PyMuPDF4LLM | PDF extraction and page geometry | Python dependency behind parser adapter | Not installed | Pending exact package/version and distribution-use verification | License review is mandatory before selection; compare alternate parsers if obligations conflict. |
| `facebookresearch/faiss` / platform package | Vector index | Python dependency behind vector-store interface | Not installed | Pending exact package/version verification | Validate macOS arm64/x86 packaging, persistence, notices, and operational complexity. |
| Tauri official plugins | Window state, dialogs, notifications, shortcuts, secure storage as applicable | Rust/plugin dependencies with minimal capabilities | Tauri plus dialog/window-state plugins are declared and locked; broad fs/opener permissions were deliberately removed | Resolved license metadata captured; installed license/NOTICE files still require distribution reconciliation | Review each plugin separately; do not grant broad capabilities by default. |
| Radix UI | Accessible UI primitives | Frontend package dependencies wrapped by `packages/ui` | Not installed | Pending package/version verification | Inventory each package actually installed. |
| shadcn/ui | Optional generated component patterns | Owned source in `packages/ui`, with source provenance per copied file | Not installed/copied | Pending exact template/source verification | Because code may be copied into the repo, record source path/revision for every imported component. |
| TipTap | Rich-text notes only if required | Package dependency behind editor feature | Not installed | Pending package/version and extension verification | Avoid until editing requirements justify it; inventory extensions individually. |
| CodeMirror | Code/editor surface only if required | Package dependency behind editor feature | Not installed | Pending package/version verification | Do not add solely for static code rendering. |
| Mermaid | Diagram rendering | Package dependency isolated/sandboxed in visualization renderer | Not installed | Pending package/version verification | Review content sanitization, CSP, bundle cost, and notices. |

## DeepTutor module decision matrix

The reviewed `deeptutor` package declares a broad default dependency set spanning multiple provider SDKs, LlamaIndex, FAISS, PyMuPDF, document formats, FastAPI/WebSockets, authentication, PocketBase, and more; its distribution also includes the Web app. Keen should not take a whole-package dependency merely to obtain a few primitives.

| Reviewed area and paths | Evidence at review SHA | Decision for Keen | Required adaptation/gate |
| --- | --- | --- | --- |
| Tool protocol: `deeptutor/core/tool_protocol.py`; registry: `deeptutor/runtime/registry/tool_registry.py` | The protocol is bounded, but the registry imports DeepTutor built-ins and prompt composition and uses process-global access | **Selective adaptation candidate**, not a direct dependency | Re-express typed schemas in Keen; add permission level, approval request, Undo metadata, cancellation, idempotency, and durable run/tool records. If code is ported, preserve Apache notices and file provenance. |
| Agent loop/dispatch: `deeptutor/core/agentic/loop.py`, `labeled_step.py`, `tool_dispatch.py`; `deeptutor/runtime/orchestrator.py` | Label-driven loop is 456 lines; dispatcher is 512 lines and runs calls in parallel (capped at eight) through DeepTutor StreamBus/context/trace types | **Specification-level rewrite** | Keen needs one simpler orchestrator, explicit Level 1/2/3 gates, document prompt-injection boundaries, ordered state mutation, per-step persistence, cancellation, and authenticated sidecar lifecycle. Reuse test ideas, not the coupled loop wholesale. |
| Parsing contracts/cache: `deeptutor/services/parsing/base.py`, `types.py`, `signature.py`, `cache.py` | Small engine protocol, readiness model, stable parser signature, and content-addressed cache pattern are separated from RAG | **Best bounded adaptation candidate** | Extend the IR with page number, section path, bounding/text location, parser version, and cancellation; canonicalize paths; exclude secrets from signatures; add atomic cache/migration tests. A later port must log exact files and modifications. |
| Parsing service/engines: `deeptutor/services/parsing/service.py` and `engines/` | Service selects settings/factory engines and writes canonical Markdown/optional structured blocks | **Adapt concepts, avoid wholesale copy** | Keen should own parser policy/status state and integrate only chosen parsers; no silent model downloads; preserve real queued/OCR/chunking/failed states. |
| RAG: `deeptutor/services/rag/` and `pipelines/` | Multi-engine framework covers LlamaIndex, PageIndex, GraphRAG, LightRAG and versioned storage; LlamaIndex loader is tied to DeepTutor embedding, LLM, file routing, and validators | **Do not reuse wholesale; depend on selected underlying libraries directly** | Build a narrow Keen retrieval interface for FTS/vector/metadata/RRF/dedupe/rerank/citation validation. Page-level geometry and offline packaging are mandatory. Review every selected library independently. |
| Session persistence: `deeptutor/services/session/sqlite_store.py` | A 1,844-line store combines sessions, branches, turns, events, notebook entries, legacy migration, and DeepTutor path conventions | **Specification-level rewrite** | Reuse schema/test ideas for replayable turn events and message branches, but implement Keen migrations/repositories around the required domain model and Application Support paths. |
| Memory: `deeptutor/services/memory/` | File-backed L1 JSONL trace → L2 Markdown → L3 synthesis, with consolidator modules and reference parsing | **Specification-level rewrite** | Keen requires SQLite evidence links, per-memory edit/delete/disable, privacy controls, and deterministic provenance. Do not import prompts, memory files, or hidden consolidation behavior. |
| Learning/mastery: `deeptutor/learning/mastery.py`, `policy.py`, `scheduler.py`, `service.py` | `mastery.py` is recency-weighted accuracy with confidence caps, **not BKT**; scheduler uses fixed interval sequences, **not FSRS**; service has useful deterministic mutation sequencing | **Do not use as Keen's BKT or FSRS implementation; adapt service-boundary ideas only** | Implement and test Keen's BKT/evidence weighting and FSRS separately. The pattern “record attempt → deterministic update → schedule → persist” is a useful behavioral specification. |
| Grading: `deeptutor/learning/grading.py` | Exact/SequenceMatcher/keyword thresholds with coarse error classification | **Do not reuse for authoritative grading** | Build typed per-question graders with explicit normalization and math evaluation; LLM explanations cannot choose mastery values. |
| Quiz/question pipeline: `deeptutor/agents/question/pipeline.py` | 2,184-line pipeline coupled to labeled agent loop, prompts, trace, sandbox, tools, and DeepTutor context | **Specification-level rewrite** | Keep generation, validation, answer key, attempt, hint use, and mastery mutation as separate testable Keen stages. Do not copy DeepTutor UI or prompts. |
| Guided learning/capabilities: `deeptutor/capabilities/mastery/`, `deeptutor/learning/policy.py` | Explicit stages/gates and review queue concepts, but bound to DeepTutor learning models and capabilities | **Adapt state-machine concepts only** | Implement Keen's required goal → diagnostic → map → unit → checkpoint → recall → practice → summary → mastery → review flow with restart-safe state. |
| Research: `deeptutor/agents/research/pipeline.py` | 2,844-line multi-stage labeled pipeline tightly coupled to DeepTutor tool/trace/prompt infrastructure | **Do not port in the first release** | Later create a bounded cancellable Keen research job with validated citations and partial-failure semantics. |
| Visualize: `deeptutor/agents/visualize/` | Analysis/code/review multi-agent chain | **Do not reuse for Phase 1** | The brief requires one orchestrator, Mermaid/SVG first, and truthful progress. Implement a narrow renderer/export path independently. |
| Math Animator: `deeptutor/agents/math_animator/` | Separate request/retry/render modules invoke Manim through subprocess and require system dependencies | **Potential later selective adaptation**, not current reuse | Only after Phase 1 and a sandbox/security review. Generated code execution, path allowlists, resource limits, cancellation, artifact isolation, and packaging must be proven. |
| API/auth/web/partners/subagents/assets/prompts | Designed for DeepTutor's Web/CLI/multi-user/channel product and includes broad operational surface | **Do not reuse** | Keen owns loopback-token authentication, macOS UX, provider settings, prompt versions, and authorized visual assets. |

## OATutor module decision matrix

OATutor's parent code is MIT at the reviewed SHA, but the repository is a React 16/Material UI/Firebase-era application and tracks 15,837 `node_modules` files out of 16,009 tracked files. Whole-repository or UI copying would import unnecessary legacy and third-party provenance risk.

| Reviewed area and paths | Evidence at review SHA | Decision for Keen | Required adaptation/gate |
| --- | --- | --- | --- |
| BKT update: `src/models/BKT/BKT-brain.js` | 14-line in-place update using mastery, slip, guess, and transit probabilities; no range validation, denominator guard, evidence confidence, or persistence contract | **Specification-level rewrite; no direct dependency needed** | Implement typed deterministic BKT in Python with parameter validation, numerical edge tests, evidence count/confidence/forgetting risk, and weighted observations. Cross-check formula test vectors without copying the mutable JS implementation. |
| Problem selection: `src/models/BKT/problem-select-heuristics/*.js`; `src/platform-logic/Platform.js` | Selects by aggregate mastery and breaks ties with `Math.random`; Platform mutates problem objects and couples selection to React/context/storage | **Specification-level rewrite** | Use deterministic seeded selection, prerequisites, deadline/forgetting risk, explainable rationale, and stable tests. |
| Hint/scaffold flow: `src/components/problem-layout/HintSystem.js`, `SubHintSystem.js`, `ProblemCard.js`, `Problem.js` | Dependency-indexed hint unlocking, nested scaffolds, and logging; React class components are tied to Material UI, Firebase, localization, content schema, and browser state. First hint use is treated as a binary incorrect observation. | **Reuse interaction semantics only; do not copy UI** | Define owned hint/scaffold domain events and nuanced evidence weights (none/small/large hint). Build Keen UI from its design system; keep mastery mutation deterministic. |
| Answer checking: `src/platform-logic/checkAnswer.js`, generated `src/kas.js` | Supports arithmetic/string/numeric paths but depends on bundled generated KAS; `src/kas.js` only points to Khan/KAS and lacks an embedded license grant | **Do not reuse** | Select a maintained math evaluator under separately verified terms and implement explicit tolerance/normalization/security limits. |
| Adaptive learning shell/UI/storage | React 16, Material UI 4, Firebase/localForage, LTI middleware, browser local storage | **Do not reuse** | Keen already targets React 18+, Tauri, SQLite, Keychain, and a loopback sidecar. |
| `src/util/enumify.js` | Contains a separate MIT license/copyright for Axel Rauschmayer and a local modification note | **Do not reuse** | Use native TypeScript/Python enums; avoid adding a third-party copy for a trivial utility. |
| OATutor content submodule | Gitlink present but submodule uninitialized; content license/attribution not independently verified in this audit | **Do not reuse any content or parameters** | If ever considered, checkout the exact submodule revision separately and audit every applicable license, attribution, source, and redistribution condition. |
| AWS/LTI/Firebase tooling and tracked `node_modules` | Large legacy deployment surface and thousands of third-party files/notices | **Do not reuse** | Use Keen's owned local-first APIs and locked dependencies; never vendor upstream `node_modules`. |

Conclusion: neither upstream should be a direct whole-project dependency. DeepTutor offers a few bounded Apache-2.0 adaptation candidates, led by parser contracts/signatures/cache and possibly tool protocol shapes. OATutor is most valuable as a behavioral reference for BKT and progressive hints; Keen should independently implement those specifications and tests.

## Required record for incorporated material

Add one record per copied/ported file or per dependency boundary:

| Field | Required value |
| --- | --- |
| Component/package | Exact name |
| Source repository | Canonical URL |
| Immutable source revision | Commit SHA or immutable release artifact; never guess |
| Source path(s) | Original paths |
| Destination path(s) | Keen paths |
| Integration type | Dependency, adapter, submodule, vendored, copied, or ported |
| Verified license | From the exact checkout/artifact |
| Copyright/NOTICE | Required retained text and installed location |
| Modifications | Concise functional description |
| Scanner evidence | Command, date, output/report path, unresolved findings |
| Owner/reviewer | Person responsible for approval |

## License scanning

Initial result: **not run / not applicable at audit time**, because the repository had no package manifests or lockfiles. First-round metadata scans have now run, but they are not by themselves a complete distribution notice review.

Once dependencies exist:

1. scan JavaScript, Rust, and Python lockfiles with tools appropriate to each ecosystem;
2. produce machine-readable reports under a gitignored build-artifact directory and summarize them here;
3. manually verify source-copied, vendored, git, and generated-template material that lockfile scanners miss;
4. reconcile all packages with `THIRD_PARTY_NOTICES.md` and distribution bundles;
5. block release on unknown, missing, incompatible, or policy-unreviewed license entries.

## Scan history

| Date | Scope | Command/tool | Result | Report | Unresolved |
| --- | --- | --- | --- | --- | --- |
| 2026-07-15 | Initial empty repository | Not run | No manifests/lockfiles existed; no conclusion about future dependencies | None | All candidate licenses and future transitive dependencies |
| 2026-07-15 | npm resolved workspace | `npm query ':not(:root)' --json` with unique name/version/license extraction | 307 unique external packages reported license metadata; 6 null-license records were only internal Keen workspaces | `artifacts/license-scan/npm-query.json`, `npm-production.json` | Separate production/dev subset reconciliation; inspect CC-BY data-package attribution; assemble shipped notices |
| 2026-07-15 | Python development environment | `pip-licenses --format=json --with-urls` | Resolved package/license report created; includes development/audit tools as well as runtime | `artifacts/license-scan/python.json` | Commit a runtime lock; generate runtime-only distribution inventory and notices |
| 2026-07-15 | Rust lock/target universe | `cargo metadata --format-version 1` plus license-field aggregation | 443 resolved cross-platform packages; one null-license package was `keen-desktop`; no unknown external license field | `artifacts/license-scan/cargo-metadata.json` | Reduce to actually bundled macOS target, inspect license files/notices, run Cargo vulnerability audit |
| 2026-07-15 | npm production vulnerability audit | `npm audit --omit=dev --registry=https://registry.npmjs.org` | 0 info/low/moderate/high/critical vulnerabilities | `artifacts/license-scan/npm-audit.json` | Development dependency audit and ongoing monitoring |
| 2026-07-15 | Python resolved-environment vulnerability audit | `pip-audit --format=json` after upgrading pip ≥26.1.2, setuptools ≥83, pytest ≥9.0.3 | 0 known vulnerabilities; local `keen-learning-core` correctly skipped as non-PyPI | `artifacts/license-scan/python-audit.json` | Runtime-only locked audit and Cargo vulnerability audit |
