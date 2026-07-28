# Keen Home: code, runtime, and Figma mapping

This document is the truthfulness contract for the componentized Home screen in Figma. It resolves mismatches in this order:

1. FastAPI/Pydantic/SQLite/Tauri runtime contracts
2. React/Zod state machines and persisted local data
3. Explicit deterministic browser-demo fixtures
4. Current code tokens and reusable Figma components
5. Authorized visual references

The Figma screen may refine hierarchy, spacing, and interaction presentation. It must not add a runtime capability, result, citation, provider response, mastery value, or successful document-processing state that the code does not supply.

## Default screen state

The Phase 3 default Home screen represents the existing `Browser Demo` state at 1585×907. The three learning rows are the exact deterministic sample tasks already present in `HomePage.tsx`; each row keeps an explicit `sample` disclosure. No model or local service is represented as contacted.

| Figma region | Code/runtime source | Allowed visible data | Required disclosure or state |
| --- | --- | --- | --- |
| Window shell | `Sidebar.tsx`, `Toolbar.tsx` | Home, Learning Feed, Knowledge Base, New learning request, New study session | Browser Demo or actual local service state |
| Page introduction and shell status | Static Home copy plus actual shell state | `Today`, the current explanatory sentence, and Demo/local status | Default uses toolbar `Demo` plus explicit `Sample tasks`; live frames use the real toolbar/footer service state. Do not add a detached duplicate disclosure beside the title. |
| Learning queue | Demo fixture or `snapshot.pending_tasks` | Demo: exact three sample titles/course/estimate pairs. Live: `task.title`, `task.estimated_minutes` | Demo rows end in `sample`; live rows say `persisted local task` |
| Schedule action | React route `/feed` | `Open schedule` | Navigation only; no implied calendar connection or external calendar write |
| Request workbench | `modeCopy`, `studyTools`, `message` | Ask course materials; Start focused study; current mode placeholder | In live mode, submission requires healthy local service and configured runtime |
| Primary action | `submit`, runtime phase | Continue, Cancel, disabled/loading presentation | Demo stores the prompt for local deterministic navigation; it is not a model call |
| Agent activity | `AgentActivityPanel` and runtime issue/state | Real run activity, approval, undo/redo, provider/service issues | Hidden in Browser Demo when no real run exists; never fabricate output |

## Queue state mapping

| Runtime condition | Figma state | Primary recovery |
| --- | --- | --- |
| Browser demo | Three deterministic rows | Open schedule |
| Learning core not healthy | Local tasks are unavailable | Reconnect/restart through the existing service recovery path |
| Demo state or snapshot pending | Loading local learning evidence | Wait; no recommendation is being created |
| Evidence validation error | Local learning evidence could not be validated | Retry |
| No local course | No local course yet | Open Knowledge Base |
| Persisted pending tasks exist | Local evidence rows | Open schedule |
| No pending tasks | No active local tasks | Explain whether an eligible candidate exists without creating it |

## Composer state mapping

| Condition | Text area | Mode controls | Primary action |
| --- | --- | --- | --- |
| Browser demo, empty prompt | Enabled | Enabled | Disabled `Continue` |
| Browser demo, prompt entered | Enabled | Enabled | Enabled `Continue` |
| Live, healthy and idle | Enabled | Enabled | Enabled only with non-empty prompt |
| Live, service offline | Enabled for preserving draft | Enabled only where current code permits | Disabled; service recovery remains visible |
| Creating/recovering/streaming | Disabled | Disabled | Loading/cancel presentation from actual runtime phase |
| Active run | Disabled | Disabled | `Cancel` |
| Provider missing/unavailable | No fabricated response | Preserve the draft | Show the real issue and recovery guidance |

## Deliberately excluded from Home

- Fabricated model replies, citations, mastery percentages, generated study plans, or completion results
- Successful document ingestion, indexing, RAG, provider setup, or sidecar supervision states not verified by runtime data
- Google Drive, Canvas, or system-calendar connection/success claims
- A large disabled feature menu used to imply future scope
- Reference-product news feeds, upgrades, gifts, founder chat, decorative mascots, or unrelated tools

The authorized HyperKnow reference informs compact composition, low-chrome controls, spacing rhythm, and workbench hierarchy only. Keen keeps its own information architecture, brand, local-first disclosure, and implemented functionality.
