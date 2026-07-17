# Reuse Decision Audit — 2026-07-17

Bounded reuse-decision audit for Keen. Six candidate upstream repositories were
inspected at exact immutable commits. **No upstream source was copied, ported,
vendored, installed, or incorporated by this audit.** Rules applied:
`AGENTS.md` (truthfulness, open-source provenance) and the prior recorded
reviews in `docs/OPEN_SOURCE_INVENTORY.md` / `docs/UPSTREAM_PATCHES.md`.

Verification method (read-only): `git ls-remote` for immutable HEAD SHAs,
GitHub API `git/trees?recursive=1` at each pinned SHA for file inventories,
`raw.githubusercontent.com` reads of `LICENSE` and dependency manifests at each
pinned SHA, plus cross-check against the existing inventory records. Where a
license or repository fact could not be verified, it is marked **unverified**.

## Keen baseline (do not rebuild or duplicate)

Keen already implements and tests the core building blocks needed for this
milestone; orchestration, API and live product flows remain incomplete:

| Capability | Keen location |
|---|---|
| Agent runtime (loop, typed tool registry, permission levels, undo, audit, crash recovery) | `services/learning-core/app/agent/`, `app/services/agent_runtime.py`, `app/services/agent_undo.py`, `app/services/level2_approval.py` |
| Study repositories + state machine | `app/learning/study_state_machine.py`, `app/repositories/study_repository.py`, migrations `011`, `016` |
| Assessment grading (objective, rubric finalizer, hint penalties) | `app/assessment/`, `app/repositories/assessment_repository.py`, migration `012` |
| Weighted mastery evidence (deterministic BKT) | `app/mastery.py`, `app/mastery_evidence.py` (`weighted-bkt/1.0.0`), migration `013` |
| Deterministic misconception rules | `app/misconceptions.py`, migration `014` |
| py-fsrs adapter (pinned, mastery-separated) | `app/review/scheduler.py` (`fsrs-6.3.1-keen-v1`), migrations `015`, `017`; `fsrs==6.3.1` in `pyproject.toml` |
| Feed priority | `app/planner/feed_priority.py` |
| RAG + provider layer (loopback-only, FTS5 CJK + sqlite-vec hybrid, citations) | `app/retrieval_interfaces.py`, `app/local_providers.py`, `app/local_chat_providers.py`, `app/lexical_retrieval.py`, `app/sqlite_vector_store.py`, `app/hybrid_retrieval.py`, `app/retrieval_service.py`, `app/answer_service.py`, `app/index_worker.py` |

Stack: Python `>=3.11,<3.15` (locked 3.11), FastAPI, stdlib `sqlite3` +
sqlite-vec (21 owned migrations), uvicorn; React 18 + strict TypeScript +
Tauri 2. The selected Keen runtime does not require Docker, Postgres, Redis,
or Firebase.

Decision summary:

| Candidate | Commit | License at revision | Reuse mode | Decision |
|---|---|---|---|---|
| shawliu998/lumi | `cd1ebcb1` | **None found — no grant** | reject | Reject |
| shawliu998/spark-agent | `f21158df` | MIT | reference-only | Reference-only |
| shawliu998/contextdelta | `2e206888` | Apache-2.0 | reference-only | Reference-only |
| HKUDS/DeepTutor | `3e3b9a6e` | Apache-2.0 | reference-only (bounded small-code-port candidate deferred) | Reference-only at P0 |
| CAHLR/OATutor-LLM-Learner | `0d376e23` | MIT (root only) | reference-only | Reference-only |
| open-spaced-repetition/py-fsrs | `3abe686e` (tag `v6.3.1`) | MIT | **dependency (already integrated)** | Keep as-is |

---

## 1. shawliu998/lumi — reject (no license)

- **URL:** https://github.com/shawliu998/lumi
- **Commit:** `cd1ebcb17c53268725495e874b3f5980514781cc` (HEAD of `main`, pushed 2026-07-15)
- **License:** **Unverified / none found.** Verified absence: no `LICENSE`,
  `LICENCE`, `COPYING`, or `NOTICE` path anywhere in all 336 tracked entries at
  this revision, and no license mention in `README.md`. Default copyright
  applies; there is no reuse grant of any kind.
- **Relevant modules:** `engine/hermes_kt/` (diagnosis, mastery, guardrails,
  verification — described as a hybrid BKT/PFA/IRT baseline),
  `runtime/hermes_runtime/` (bounded agent loop: machine, state, store, tools),
  `service/hermes_service/` (loopback HTTP sidecar), `domains/` (exam content
  generators), `client/` (React), `desktop/` (Tauri 2), `evals/`.
- **Dependencies/infrastructure:** Python `>=3.10/3.11` packages declaring
  **zero third-party dependencies** (`engine`, `runtime`, `service`
  pyprojects); React/Vite client; Tauri 2 desktop. No Docker or DB manifests
  observed at root; storage mechanism not deeply audited (moot, see below).
- **Stack compatibility:** Architecturally the same shape as Keen (loopback
  sidecar + React + Tauri 2). Legally unusable regardless.
- **Adds DB/Docker/Postgres/Redis/Firebase/provider/RAG:** None observed.
- **Extraction cost:** Moot — no license means no extraction.
- **Allowed reuse mode:** **reject.**
- **Decision:** Reject. No code, content, schema, or prompt may be taken
  without a license grant. Its capabilities (mastery, agent loop, sidecar)
  duplicate what Keen already implements and tests. If the owner later adds a
  license, re-run the full provenance process in `AGENTS.md` before any reuse.

## 2. shawliu998/spark-agent — reference-only

- **URL:** https://github.com/shawliu998/spark-agent
- **Commit:** `f21158df7631e23f5be4481ea20e63c11e8389b1` (HEAD of `main`;
  identical to the SHA recorded in `docs/OPEN_SOURCE_INVENTORY.md`)
- **License:** MIT, copyright 2026 AI4S Workbench contributors — `LICENSE`
  read at this revision. `THIRD_PARTY_NOTICES.md` present (previously read).
- **Relevant modules:** `services/science-core/` (FastAPI evidence,
  provenance, research-workflow service), `services/science-runtime/`,
  `packages/{research-domain,research-sdk,sdk,shared,ui}`,
  `runtime/{harness,kernel,manager,mcp,opencode-profile,skills}`,
  `apps/desktop` (Tauri + React, OpenCode-compatible shell).
- **Dependencies/infrastructure:** pnpm 9 workspace; Python services require
  `>=3.12` with FastAPI, SQLAlchemy + alembic, PyMuPDF, httpx, pydantic;
  optional `paper-qa` literature extra; OpenAI-compatible LLM/embedding
  settings; Jupyter execution in a no-network container.
- **Stack compatibility:** Concept-level fit only (typed plan approvals,
  immutable payload review, evidence-integrity pass, SQLite audit). Code is
  not directly portable: Dockerized services, SQLAlchemy/alembic vs Keen's
  stdlib `sqlite3` + owned migrations, Python 3.12 vs Keen's locked 3.11,
  research (not learning) domain.
- **Adds DB/Docker/Postgres/Redis/Firebase/provider/RAG:** **Docker Compose**
  (`science-core` + `science-runtime`), container-based Jupyter execution,
  PaperQA, PyMuPDF (on Keen's explicit not-installed list), OpenAI-compatible
  provider. No Postgres/Redis/Firebase observed.
- **Extraction cost:** High for code; already-absorbed for concepts.
- **Allowed reuse mode:** **reference-only.**
- **Decision:** Reference-only, matching the recorded 2026-07-17 inventory
  audit (reviewed candidate / not incorporated). Keen's agent runtime already
  has approval levels, undo, audit, persistence, and restart recovery; the
  approval/provenance UX ideas may inform future UI specs, nothing more.

## 3. shawliu998/contextdelta — reference-only

- **URL:** https://github.com/shawliu998/contextdelta
- **Commit:** `2e206888a37796fb08a0c0d3d0b5c99bf6f36a2c` (HEAD of `main`;
  identical to the recorded inventory SHA)
- **License:** Apache-2.0 — `LICENSE` read at this revision; no `NOTICE` found.
- **Relevant modules:** `contextdelta/` package — execution benchmark for
  stale-state failures in tool-using agents: order/calendar/config
  environments, typed freshness contracts (`expected_version` write
  preconditions), context-reduction strategies, end-state/stale-action
  graders; `tests/`, `examples/`, `configs/`.
- **Dependencies/infrastructure:** Python `>=3.11`; FastAPI, SQLAlchemy +
  alembic (defaults to SQLite URL), pandas, streamlit dashboard, typer,
  pydantic-settings. `Dockerfile` + `docker-compose.yml` (api + dashboard).
- **Stack compatibility:** Same language/framework family (FastAPI/Pydantic
  3.11), but it is a benchmark harness, not a learning feature module;
  SQLAlchemy/alembic/pandas/streamlit are not Keen dependencies.
- **Adds DB/Docker/Postgres/Redis/Firebase/provider/RAG:** Docker +
  docker-compose (optional dev path), Streamlit second app. No
  Postgres/Redis/Firebase observed.
- **Extraction cost:** N/A for code; low for ideas.
- **Allowed reuse mode:** **reference-only.**
- **Decision:** Reference-only, matching the recorded inventory audit. Value
  is limited to concepts and negative-test ideas — versioned write
  preconditions and stale/duplicate-action checks — for hardening tests of
  Keen's existing typed tool registry (`app/agent/registry.py`). No code,
  dependency, or workflow is selected.

## 4. HKUDS/DeepTutor — reference-only at P0

- **URL:** https://github.com/HKUDS/DeepTutor
- **Commit:** `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a` (tag `v1.5.1`, HEAD
  of `main`; identical to the recorded full-checkout review SHA)
- **License:** Apache-2.0 — `LICENSE` read at this revision (copyright 2025
  Data Intelligence Lab, The University of Hong Kong); no top-level `NOTICE`.
- **Relevant modules (per the recorded module decision matrix):**
  `deeptutor/core/tool_protocol.py` +
  `deeptutor/runtime/registry/tool_registry.py` (bounded, selective-adaptation
  candidate); parser contracts/cache (best bounded adaptation candidate);
  `deeptutor/core/agentic/{loop,labeled_step,tool_dispatch}.py`,
  `deeptutor/services/{rag,pipelines}/`,
  `deeptutor/services/session/sqlite_store.py`,
  `deeptutor/agents/{question,research}/pipeline.py`,
  `deeptutor/capabilities/mastery/`, `deeptutor/learning/policy.py` —
  specification-level rewrite or do-not-reuse. Its `learning/mastery.py` is
  recency-weighted accuracy (**not BKT**) and its scheduler is **not FSRS**.
- **Dependencies/infrastructure (verified from `requirements/` at this
  revision):** heavy — `llama-index` + BM25/FAISS retrievers (`faiss-cpu`),
  PyMuPDF, OpenAI/Anthropic/dashscope/perplexity SDKs, MCP client,
  PocketBase, JWT/bcrypt auth, websockets, IM channel SDKs
  (Telegram/WeCom/Lark/DingTalk/Slack), `ddgs` web search, arxiv,
  docx/pptx/pdfplumber/reportlab. `Dockerfile` ×2, `docker-compose*.yml` ×3,
  web + CLI + partners multi-user product (1,990 tracked entries).
- **Stack compatibility:** Poor as a dependency: multi-engine RAG
  (LlamaIndex/FAISS/PageIndex/GraphRAG/LightRAG per the recorded review),
  external PocketBase service, and a broad provider/channel surface conflict
  with Keen's minimal loopback sidecar (stdlib sqlite3 + sqlite-vec hybrid
  retrieval already implemented).
- **Adds DB/Docker/Postgres/Redis/Firebase/provider/RAG:** **Yes** — Docker,
  PocketBase (external DB service), FAISS, many LLM providers, IM channels,
  multi-engine RAG. No Postgres/Redis/Firebase observed in the audited files.
- **Extraction cost:** High; only the parser contract/cache shapes are
  bounded. Not faster than Keen's existing, tested modules.
- **Allowed reuse mode:** **reference-only** at P0. A future bounded
  **small-code-port** of parser contract/cache shapes remains a gated
  candidate only if it is demonstrably faster than extending Keen's existing
  `app/documents.py` pipeline — and only after re-verifying the exact
  revision, recording provenance in `docs/OPEN_SOURCE_INVENTORY.md` /
  `docs/UPSTREAM_PATCHES.md`, and preserving Apache notices.
- **Decision:** Reference-only. Do not depend on the package. The recorded
  module matrix stands; nothing new is selected.

## 5. CAHLR/OATutor-LLM-Learner — reference-only

- **URL:** https://github.com/CAHLR/OATutor-LLM-Learner
- **Commit:** `0d376e23302485bebef6e1cad04da3816a164cd6` (HEAD of `main`;
  identical to the recorded review SHA)
- **License:** MIT at root, copyright 2023 Zachary A. Pardos (`@zpardos`) —
  CAHL research lab; read at this revision. Embedded `src/util/enumify.js`
  carries its own MIT; generated `src/kas.js` points to Khan/KAS with **no
  license grant**; the `src/content-sources/oatutor` content submodule
  (gitlink `270ce040…`) was never audited — **no content reuse**.
- **Relevant modules:** `src/util/BKT-brain.js` (14-line BKT formula
  reference) and hint/scaffold progression semantics — behavioral reference
  only.
- **Dependencies/infrastructure:** React 16 + Material-UI legacy app;
  `firebase`, `aws-sdk`, `algebrite`, `mathlive`, `react-katex`; tracks its
  `node_modules` (≈15.8k of ≈16k tracked files per the recorded review;
  18,378 tree entries at this revision).
- **Stack compatibility:** None — JS/Firebase courseware vs Keen's
  Python/SQLite sidecar and React 18.
- **Adds DB/Docker/Postgres/Redis/Firebase/provider/RAG:** **Firebase** and
  AWS SDK. No Docker observed.
- **Extraction cost:** N/A — behavioral reference only.
- **Allowed reuse mode:** **reference-only.**
- **Decision:** Reference-only, matching the recorded matrix. Its BKT update
  semantics and progressive-hint behavior are already independently
  re-implemented and tested in Keen (`app/mastery_evidence.py`
  `weighted-bkt/1.0.0`, `app/assessment/hints.py` `hint-penalties/1.0.0`).
  No code, content, parameters, or legacy UI.

## 6. open-spaced-repetition/py-fsrs — dependency (already integrated)

- **URL:** https://github.com/open-spaced-repetition/py-fsrs
- **Commit:** `3abe686e9c058d3f3c00bbeb92e68b71211b2b31` — HEAD of `main`
  **and** tag `v6.3.1` point to this commit; identical to the recorded
  selection SHA.
- **License:** MIT, copyright 2022 Open Spaced Repetition — read at this
  revision; no NOTICE; full text reproduced in `THIRD_PARTY_NOTICES.md`.
- **Relevant modules:** `fsrs/` package (`Scheduler`); tag `v6.3.1`.
- **Dependencies/infrastructure:** Single runtime dependency
  `typing-extensions` (already locked); Python `>=3.10`. The optimizer extra
  (torch/numpy/pandas) is **not** selected.
- **Stack compatibility:** Full — pure-Python wheel, verified with Python
  3.11 arm64 and PyInstaller one-file import smoke.
- **Adds DB/Docker/Postgres/Redis/Firebase/provider/RAG:** None.
- **Extraction cost:** Zero — integration is complete: `fsrs==6.3.1` exact
  pin (`pyproject.toml`), wrapped behind Keen's owned `ReviewScheduler`
  protocol (`app/review/scheduler.py`, `fsrs-6.3.1-keen-v1`: retention 0.9,
  max interval 36,500 days, fuzz off, no constructor overrides), persistence
  via `app/repositories/review_repository.py` and migrations `015`/`017`,
  wheel SHA-256 recorded in the inventory.
- **Allowed reuse mode:** **dependency** (already integrated).
- **Decision:** Keep exactly as-is. Remains the only selected upstream
  learning dependency. Re-audit before any version, parameter, or
  optimizer-extra change.

---

## P0 decision (final)

1. **Reuse Keen's existing modules.** No candidate offers an independently
   licensed module that is clearly faster to adapt than what Keen already
   implements and tests (agent runtime, study state machine, assessment
   grading, weighted mastery, misconception rules, FSRS scheduling, feed
   priority, hybrid RAG, provider layer). Do not rebuild or duplicate them.
2. **py-fsrs stays the single selected upstream dependency**, pinned at
   `fsrs==6.3.1` behind the Keen-owned `ReviewScheduler` protocol.
3. **All other candidates are reference-only or rejected.** No new upstream
   source, dependency, content, prompt, or workflow is incorporated at P0.
4. **Build only orchestration/API/UI plus a minimal indexed-document-to-concept
   bootstrap:**
   - Wire the labeled demo/placeholder pages to the existing sidecar backends
     (deep-learn → study sessions, quiz → assessment grading, flashcards →
     FSRS review items; memory/planner/visualize remain honestly labeled until
     real backends exist).
   - Add the Keen-owned question-generation and mastery-update orchestration
     on top of existing deterministic modules (spec-level design may cite the
     recorded DeepTutor/OATutor matrices; no code reuse).
   - Use the small deterministic bootstrap that derives one concept from safe
     metadata on an already-indexed course document and initializes an explicit
     zero-attempt BKT prior. It creates no learner evidence or mastery event;
     assessment/review flows remain the only source of learning evidence.
5. **No new DB, Docker, Postgres, Redis, Firebase, provider, or RAG engine**
   is introduced by any decision in this audit.

## What was verified (2026-07-17)

- `git status --porcelain` — worktree was clean when this audit began.
  `docs/REUSE_DECISIONS.md` is the audit's only write. Concurrent coordinator
  work appeared in separate learning-core files during the audit and was not
  read, modified or attributed to Kimi by this document.
- `git ls-remote https://github.com/<repo>` for all six candidates — HEAD of
  `main` SHAs as listed above; py-fsrs HEAD equals tag `v6.3.1`. SHAs for
  spark-agent, contextdelta, DeepTutor, OATutor, py-fsrs are identical to
  those recorded in `docs/OPEN_SOURCE_INVENTORY.md`.
- GitHub API `repos/<owner>/<repo>/git/trees/<sha>?recursive=1` at each pinned
  SHA — file inventories (lumi 336, spark-agent 734, contextdelta 142,
  DeepTutor 1,990, OATutor 18,378, py-fsrs 35 entries), LICENSE
  presence/absence, Docker/compose files, dependency manifests.
- `LICENSE` contents read at each pinned SHA via `raw.githubusercontent.com`
  (spark-agent MIT, contextdelta Apache-2.0, DeepTutor Apache-2.0, OATutor
  MIT, py-fsrs MIT). lumi: no license file exists at the audited revision —
  rights **unverified**, treated as no grant.
- Dependency manifests read at each pinned SHA: lumi
  `engine/runtime/service` pyprojects (zero third-party deps), spark-agent
  root `package.json` + `compose.yaml` + `services/science-core/pyproject.toml`,
  contextdelta `pyproject.toml` + `docker-compose.yml`, DeepTutor
  `requirements/{cli,server,partners}.txt`, OATutor `package.json`, py-fsrs
  `pyproject.toml`.
- Keen baseline modules confirmed by direct inspection of
  `services/learning-core` (paths in the baseline table) and
  `docs/OPEN_SOURCE_INVENTORY.md` / `docs/UPSTREAM_PATCHES.md` (no vendored or
  patched upstream source exists in Keen).
- `git diff --check` — see audit report in the accompanying task summary.
