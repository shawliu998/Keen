# Keen UI product audit — 2026-07-21

Scope: current browser Demo at 1280×800 and 900×700. This is a product/interaction audit, not a pixel-parity claim. No product code was changed.

## Positioning conclusion

Keen is strongest when it behaves as a local study workspace: source library → scheduled task → source-grounded learning session → review. Home, Learning Feed, task detail, Knowledge Base, Conversation, Deep Learn, Review, and Privacy & data support that position. Quiz, Planner, Learner Memory, Visualize, provider setup, and integrations should remain hidden development specimens or compact capability boundaries until their data and actions are real.

## Priority findings

### P0 — remove misleading demo behavior from core entry points

1. `/conversation/new` renders the fixed eigenvector transcript in Demo mode. “New learning request” therefore does not look or behave like a new request. Use a truthful empty composer; only open the sample transcript through an explicitly labeled sample action.
2. The global inspector can be opened without selected context and then displays illustrative mastery, unverified source labels, and a demo insight. Hide/disable the global inspector until contextual evidence exists, or show a plain empty state. Do not use synthetic mastery as its fallback.

### P1 — reduce surfaces that outpace implemented capability

1. Learner Memory is the largest mismatch. Its polished profile, search/filter controls, evidence cards, enable/delete actions, and seeded inference-like records outweigh the UI-demo disclaimer. Replace it with a compact unavailable/read-only boundary until durable learner-evidence APIs exist.
2. Settings is over-separated for a read-only build. Keep Status and Privacy & data. Combine Model provider and Connections into a single “Capabilities” section until at least one can be configured. Keep Open source as a concise legal/inventory section.
3. Review has a truthful empty state but no recovery/next action. Add a real route back to Learning Feed or a study-session start.

### P2 — clarify hierarchy and interaction semantics

1. Home has both “Today” and “Learning queue” as strong headings. Make Today the page context and Learning queue the primary work section, with a slightly quieter queue heading.
2. Feed repeats Demo/sample status in the toolbar, intro, and task content. One persistent Demo marker plus one explanatory notice is enough.
3. Feed’s “Active tasks” treatment and single “Month” control should not look like switchers unless alternate states are implemented.
4. Task detail’s checked first item under “Expected workflow” can be mistaken for actual progress. Rename to “How this task works” or remove completion styling.
5. Conversation needs a visible course/source scope near its title. The document-like transcript is otherwise a strong alternative to chat bubbles.
6. Knowledge Base is information-dense compared with Home. Retain the list/table structure, but keep Import as the only dominant action and avoid adding dashboard cards.

## Page decisions

| Surface | Decision | Reason |
| --- | --- | --- |
| Home | Keep, refine | Best default entry; focused and truthful |
| Learning Feed | Keep, simplify | Core task/schedule workspace |
| Task detail | Keep, prioritize | Best expression of goal, evidence, progress, next action |
| Knowledge Base | Keep | Core local-first source surface |
| Conversation | Keep, fix new state | Strong document reading pattern; new route currently misleading |
| Deep Learn | Keep as Demo/future target | Strong learning flow, but illustrative progress must stay explicit |
| Review | Keep, add recovery CTA | Real local review boundary |
| Quiz | Hide from production IA | Polished UI demo without assessment persistence |
| Planner | Hide/redirect | Roadmap-like empty page is not a current feature |
| Learner Memory | Replace with boundary | Strongest over-promise and disabled-control clutter |
| Visualize | Keep hidden specimen | Truthful fixed example; not a current main feature |
| Settings | Compress | Only Status and Privacy have substantial current value |

## Navigation and global controls

- Primary sidebar should remain: Home, Learning Feed, Knowledge Base, New study session, Review, Settings.
- Keep one prominent “New learning request” entry plus `⌘N`; the toolbar plus, sidebar button, Home composer, and command palette are acceptable only when they all lead to the same truthful empty state.
- Command palette is well-scoped and keyboard-friendly.
- Remove the always-available inspector button. Contextual “View source/evidence” actions should open it when real or explicitly labeled sample context exists.
- At 900×700 the icon rail, list-based Feed fallback, content widths, and Deep Learn split layout remain usable with no horizontal overflow observed.

## Capability boundary

Current copy generally labels Browser Demo, sample, fixed seed, not implemented, and local-only behavior correctly. The remaining risk is visual, not textual: a disclaimer cannot fully offset a complete-looking fake workflow. Future provider, calendar, Drive/Canvas, durable memory, adaptive quiz, generated visualization, and model-backed mastery should stay out of primary navigation until their underlying state and recovery paths exist.

## Evidence

Screenshots `01`–`16` cover the desktop pages and Settings sections at 1280×800. Screenshots `17`–`23` cover representative compact states at 900×700. The audit found no horizontal overflow or unnamed buttons in the inspected desktop pages; disabled controls were limited mainly to valid empty-submit states, except Learner Memory’s unavailable edit/settings controls.
