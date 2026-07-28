# Keen Learning Feed: code, runtime, and Figma mapping

This document is the truthfulness contract for the componentized Learning Feed. Precedence is:

1. FastAPI/Pydantic/SQLite/Tauri runtime contracts
2. React/Zod state and persisted local data
3. Deterministic Browser Demo fixtures
4. Current Keen tokens and reusable Figma components
5. Authorized reference-product layout evidence

## Default Browser Demo

The default design uses the existing deterministic tasks from `useAppStore`, filtered by the implemented `today | upcoming | overdue | completed` states and course selector. Each sample task remains labelled `Sample` or `Browser Demo`. Calendar items are derived from those same tasks; they are not system-calendar records.

| Region | Runtime source | Allowed content | Explicit limit |
| --- | --- | --- | --- |
| Task pane | `LearningFeedPage.tsx`, `mapDemoStateTasks` | task title, status, due text, reason, course, duration, concepts | Demo items remain sample data |
| Status/course filters | local React state | Today, Upcoming, Overdue, Completed, available courses | Filter-only; no recommendation is created |
| Calendar | `LearningCalendar.tsx` | 42-day month grid, previous/next month, up to two derived task events per day | Month view only; no Week control and no external calendar connection |
| Task selection | `selectedTaskId` | selected task styling and matching calendar event | Selection changes local UI state only |
| Task detail | `TaskDetailPanel.tsx` | goal/reason, due, estimate, workflow, available evidence and Demo-only sample update actions | No real session is assumed before authenticated confirmation |

## Selected Browser Demo task

Figma nodes `172:262` and `176:340` show the deterministic `Active recall:
cellular respiration` sample selected. The 68% course-mastery readout is copied
from the existing Browser Demo task and remains labelled `Illustrative sample`.
`Snooze sample` and `Mark sample complete` represent the existing in-memory
`updateTask` behavior only; they do not create a session, write mastery, schedule
a review, call a provider, or persist after reload.

## Operational-state Figma nodes

| Figma node | Runtime branch represented | Required truth boundary |
| --- | --- | --- |
| `178:418` | learning core `unavailable` | stored records are not replaced; restart is a recovery request, not proof of success |
| `179:596` | startup / authenticated health checking | no Demo tasks or mastery are substituted while local startup completes |
| `179:998` | healthy service with zero local courses | no recommendation request is sent; the learner must first create a course and indexed source |
| `179:1400` | healthy service with invalid tasks/mastery response | no record is modified and no Demo data is substituted; retry remains explicit |

These are editable design states, not runtime test results. The Month calendar is
empty in all four states because no local task data is available to derive an
event; this does not imply an external calendar connection.

## Live/local states

| Condition | Visible state | Recovery/action |
| --- | --- | --- |
| Learning core starting or unhealthy | service state, no substituted Demo tasks | existing retry/restart action |
| Healthy service, Demo state pending/error | loading or validation failure | retry health/data load |
| No local courses | explicit empty state | create a course and indexed source; no recommendation request sent |
| Snapshot loading/error | loading or validation failure | retry feed; no task created |
| Pending tasks exist | persisted local task rows and derived month events | View details; start only through authenticated service |
| No pending tasks, candidate exists | empty state explaining eligible action | Find next task may create one local task |
| No pending tasks/candidates | clear empty state | no action invented |
| Recommendation/start cancelled or uncertain | explicit reconciliation state | refresh/recover before retrying to avoid duplicates |

## Reference boundaries

The authorized HyperKnow reference may inform the left task rail, large month calendar, compact toolbar and event density. Keen does not copy or imply:

- Week view, calendar write, calendar connection or external scheduling when those are not implemented;
- provider/model success, document ingestion, RAG or sidecar supervision success;
- fabricated mastery, citations, generated replies, completed tasks or recommendation outcomes;
- HyperKnow branding, companion copy, quota/free-tier controls, upgrade controls or unrelated product navigation.
