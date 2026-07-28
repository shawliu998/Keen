# Round 03 evidence index

| File | Route/state | Review note |
| --- | --- | --- |
| `screenshots/01-home-new-learning-1420x900.png` | `/?mode=study&visualTest=true&visualCoreState=empty` | One New learning composition; visible labeled submit action |
| `screenshots/02-knowledge-data-1420x900.png` | `/knowledge?demo=true&visualTest=true` | Dense course filters and source list; visibly labeled Browser Demo |
| `screenshots/03-feed-task-detail-1420x900.png` | `/feed?demo=true&visualTest=true&selectedTask=t2` | Task-list-first Feed with one selected task and one primary action |
| `screenshots/04-deep-learn-reading-1420x900.png` | `/deep-learn/demo?course_id=demo&demo=true&visualTest=true` | Two-column guided reading and inline recall |
| `screenshots/05-history-empty-1420x900.png` | `/history?demo=true&visualTest=true` | Collection-level empty state with one primary action |
| `screenshots/06-review-empty-1420x900.png` | `/review?demo=true&visualTest=true` | Due-queue empty state with one primary action |
| `screenshots/07-settings-model-1420x900.png` | `/settings?section=capabilities&demo=true&visualTest=true` | Minimal settings navigation; browser truthfully refuses credentials |
| `contact-sheet.png` | Composite | Current-run cross-page visual overview |
| `rejected/02-knowledge-empty-visual-fixture-1420x900.png` | `/knowledge?visualTest=true&visualCoreState=empty` | Rejected: fixture has no authenticated client and cannot verify real empty content |
| `reports/tests.md` | Targeted Vitest | 8 files / 158 tests passed; final Review copy check 1 file / 21 tests passed |
| `reports/frontend.md` | TypeScript, ESLint, production build | All exit 0; existing Vite large-chunk advisory only |
| `reports/visual-regression.md` | Existing visual harness | Capture completed; exit 1 with missing/stale references, documented rather than rebaselined |
| `review-request.md` | Orchestrator handoff | Exact decision request and final audit axes |
| `orchestrator-review.md` | Pro review | Round 03 PASS; final decision ACCEPT; no must-fix items |
| `packaged/01-home-ready.png` | Packaged `Keen.app`, Home | Bundled learning core ready; one New learning entry |
| `packaged/02-knowledge-empty-ready.png` | Packaged `Keen.app`, Knowledge Base | Real zero-data state; one Import source action and optional course disclosure |
| `packaged/03-feed-ready.png` | Packaged `Keen.app`, Learning Feed | Real first-run queue state; one Open Knowledge Base action |
| `packaged/04-history-ready.png` | Packaged `Keen.app`, History | Real zero-record state; one recovery destination |
| `packaged/05-review-ready.png` | Packaged `Keen.app`, Review | Real nothing-due state; continued-learning destinations remain explicit |
| `packaged/06-settings-status-ready.png` | Packaged `Keen.app`, Settings Status | Learning service reports ready in the production WebView |
| `packaged/07-settings-model-ready.png` | Packaged `Keen.app`, Settings Model | Real Ollama/OpenAI-compatible configuration retained without provider-platform expansion |
| `packaged/contact-sheet.png` | Packaged composite | Cross-page production-WebView overview at 1203×768 per capture |
| `reports/packaged.md` | Packaged validation | App build, strict signature, bundled sidecar smoke and native accessibility-tree route inspection |
