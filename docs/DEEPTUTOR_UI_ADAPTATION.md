# DeepTutor UI adaptation note

Date: 2026-07-24

Work type: verification subordinated to product. This began as a read-only
provenance and UI mapping for Keen's current slice. On 2026-07-26, one official
upstream Home screenshot and its three original logo/wordmark assets were
placed in the private canonical Figma file for a labelled `Reference only`
comparison and editable replica. They are not stored in this repository, used
by the runtime, or included in a distributed artifact.

## Upstream identity

| Field | Evidence |
| --- | --- |
| Canonical repository | `https://github.com/HKUDS/DeepTutor` |
| Organization | `HKUDS` / Data Intelligence Lab at The University of Hong Kong |
| Reviewed immutable revision | `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a` |
| Revision metadata | tag `v1.5.1`; commit date `2026-07-09 23:23:27 +0800`; subject `release: v1.5.1` |
| Temporary checkout | `/tmp/keen-deeptutor-ui-audit.s3Kz4x` |
| License read | root `LICENSE`: Apache License 2.0; appendix copyright 2025 Data Intelligence Lab, The University of Hong Kong |
| NOTICE read | No top-level `NOTICE`, `NOTICE*`, or `COPYING*` found in the reviewed checkout |
| UI header findings | Reviewed relevant `web/app`, `web/components`, and `web/lib` files. The core UI files below had no separate copyright/SPDX headers. `web/components/partners/ChannelIcon.tsx` and `web/components/common/ProviderIcon.tsx` contain third-party icon provenance comments; those assets are outside this reuse scope. |
| Incorporation state | No source/runtime incorporation. The private canonical Figma file retains upstream screenshot node `252:202` plus `logo.png`, `banner.png`, and `logo_black.png` fills used only by editable reference node `257:157`. |

Commands run:

```sh
git status --short
git clone --filter=blob:none https://github.com/HKUDS/DeepTutor.git /tmp/keen-deeptutor-ui-audit.s3Kz4x
git -C /tmp/keen-deeptutor-ui-audit.s3Kz4x checkout 3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a
git -C /tmp/keen-deeptutor-ui-audit.s3Kz4x status --short
git -C /tmp/keen-deeptutor-ui-audit.s3Kz4x show -s --format='%H%n%ci%n%D%n%s' HEAD
find /tmp/keen-deeptutor-ui-audit.s3Kz4x -maxdepth 2 -iname 'LICENSE*' -o -iname 'NOTICE*' -o -iname 'COPYING*'
sed -n '1,260p' /tmp/keen-deeptutor-ui-audit.s3Kz4x/LICENSE
rg -n "Copyright|SPDX|Licensed|Apache|MIT" /tmp/keen-deeptutor-ui-audit.s3Kz4x/web/app /tmp/keen-deeptutor-ui-audit.s3Kz4x/web/components /tmp/keen-deeptutor-ui-audit.s3Kz4x/web/lib
```

Results: the Keen worktree was already dirty before this audit; checkout was
clean after `checkout`; HEAD matched the reviewed SHA; only root `LICENSE` was
found at max depth 2. No dependency, source, route, prompt, component or
distributed asset was introduced. The later private-Figma reference uses
`assets/figs/web-1.4.6+/home/00-overview.png`, `web/public/logo.png`,
`web/public/banner.png`, and `web/public/logo_black.png` from this exact
reviewed revision.
No dependency license scan was run because no package or distributed runtime
material changed. Existing Keen dependency scan history remains in
`docs/OPEN_SOURCE_INVENTORY.md`.

## Reviewed source paths

| Interaction area | DeepTutor paths read | Notes |
| --- | --- | --- |
| Navigation shell | `web/app/(workspace)/layout.tsx`, `web/components/sidebar/WorkspaceSidebar.tsx`, `web/components/sidebar/SidebarShell.tsx` | Two-state left rail, recents, capability-gated nav, footer links. Too broad for Keen release navigation. |
| Main learning/chat workspace | `web/app/(workspace)/home/[[...sessionId]]/page.tsx`, `web/components/chat/home/ChatMessages.tsx` | Capability picker, composer, durable messages, attachments, generated files, streaming events. Useful structure, not a copy candidate. |
| Agent/progress display | `web/components/chat/home/TracePanels.tsx`, `web/components/chat/home/SessionActivityPanel.tsx`, `web/app/(workspace)/book/components/BookProgressTimeline.tsx`, `web/lib/book-progress.ts` | Collapsed trace vocabulary, activity aggregation, stage timeline. Rewrite as Keen-specific study progress and agent evidence. |
| References/material panel | `web/components/chat/home/SessionViewerPanel.tsx`, `web/components/chat/preview/FilePreviewDrawer.tsx`, `web/components/chat/preview/previewerFor.ts`, `web/components/chat/preview/previewers/*`, `web/lib/markdown-display.ts` | Right-side tabbed viewer and citation linkification patterns. Keen should keep source/citation detail on demand, bounded by authenticated local source handles. |
| Guided study/book workspace | `web/app/(workspace)/book/page.tsx`, `web/app/(workspace)/book/components/PageReader.tsx`, `web/app/(workspace)/book/components/BookSidebar.tsx`, `web/app/(workspace)/book/components/BookProgressTimeline.tsx`, `web/app/(utility)/space/learning/page.tsx` | Book/page generation and mastery map are structurally relevant but product semantics differ from Keen's current Deep Learn and Review loop. |

## UI mapping

| DeepTutor pattern | Keen v1 decision | Keen component contract |
| --- | --- | --- |
| Collapsible workspace sidebar plus session recents | Can borrow the structural idea only. Do not copy nav labels, broad feature list, footer GitHub/docs links, logo/banner, or capability-gating UI. | `apps/desktop/src/shell/Sidebar.tsx` keeps exactly one `New learning` action and release nav: Home, Knowledge Base, Learning Feed, History, Review, Settings. Collapsed/expanded states preserve active route, focus, and service status without adding Agent/Memory/Book/Partner/Research surfaces. |
| Home/workspace as a single entry where mode, sources, and prompt are chosen | Rewrite and narrow. DeepTutor's capability picker is too broad; Keen uses intent plus source plus one truthful action. | `apps/desktop/src/features/home/HomePage.tsx` exposes Ask or focused Study inside Home. It must produce a validated learning request or preserve a draft/error; it must not show unsupported model/tool success. |
| Right-side Activity/Viewer panel that aggregates tools, references, attachments, and previews | Adapt as on-demand source/detail surface, not a default third column. | Deep Learn keeps two persistent columns at 1180-1280 px: path rail and 65-75ch document. Source/citation detail opens on demand through existing source/PDF viewer surfaces such as `PdfCitationViewer` or a bounded inspector state. The panel takes authenticated local handles, not arbitrary URLs or upstream file preview assumptions. |
| Trace panels that convert streaming tool events into compact rows | Rewrite as Keen-owned agent/study evidence. | `apps/desktop/src/features/agent/AgentActivityPanel.tsx` and Deep Learn inline states show real run phase, approval/undo when applicable, cancellation, error, retryability, and persisted mutation result. No hidden chain-of-thought or fabricated tool transcript. |
| Multi-stage book generation timeline | Can directly borrow the concept of a compact stage timeline; implementation should be original. | Deep Learn path rail and Feed detail show deterministic stage status: source scope -> path generated -> study -> recall -> practice -> summary/review. Progress comes from SQLite/API state and clamps to truthful pending/running/error/complete labels. |
| Page reader with bounded reading measure, block actions, and failed-block retry | Rewrite to match Keen's source-grounded study unit. | `DeepLearnPage.tsx` keeps a bounded learning document, inline failure/retry states, and one primary next action. Completion remains inline; no large success card or generated book affordances. |
| Mastery path dashboard and "continue in chat" | Do not copy as a separate product surface. | Keen treats Quiz/flashcards/mastery as step/content types inside Study or Review. Learning Feed and Review own the next action and due queue; no top-level Mastery/Book route is added. |
| Citation linkification and references section | Rewrite, but the structural contract is useful. | Citations must resolve to local source IDs/page/chunk/bounding-box data validated by Zod/Pydantic. Missing or stale citations show an explicit unavailable state. Numeric citation heuristics should be tested against math/list content before adoption. |
| File preview tabs, iframe web tabs, provider icons, partner/channel icons | Do not copy for v1. | Keen already uses local PDF rendering and source inspection. Do not import DeepTutor provider icons, partner/channel icons, web iframe behavior, logo assets, prompts, or public branding into runtime/distribution. The one official Home screenshot is an internal Figma reference only. |

## Reuse classification

| Classification | Items | Conditions |
| --- | --- | --- |
| Can borrow structurally | Two-state sidebar; compact stage timeline; activity/detail panel as an optional surface; bounded reading column; source chips leading to detail; step-progress wording model | Use Keen-owned React/CSS/components and Keen runtime state. Do not copy source files, CSS classes, prompts, icons, names, or broad navigation into runtime. The official Home screenshot may remain only as the recorded internal Figma reference. |
| Rewrite and adapt | Trace/progress event vocabulary; source/reference aggregation; attachment/source preview flow; citation rendering; guided study page reader; mastery path map as progress semantics | Keep Keen local-first contracts, permission levels, idempotency, cancellation, recoverability, SQLite persistence, and deterministic mastery/FSRS separation. |
| Should not ship | `web/public/logo*.png`, `web/public/banner.png`, `assets/figs/**`, provider/partner/channel icons, route map, capability picker breadth, Web/auth/admin/partner/memory/agents surfaces, prompts, screenshots, generated outputs, third-party user data | These create trademark/asset/provenance/product-scope risk and are outside Keen v1. The Home screenshot exception is reference-only in private Figma and must not enter the product or distribution. Apache-2.0 does not grant trademark permission, and icon files may carry separate third-party terms. |

## Future copying gate

If future work copies or ports any DeepTutor component, record before or in the
same change:

- canonical repository URL and exact commit SHA;
- source path and Keen destination path for every file;
- verified root license plus any source header or asset-level license;
- retained copyright and Apache-2.0 text/NOTICE handling;
- modifications made, including removed product branding and security changes;
- why an original rewrite or dependency boundary was insufficient;
- scanner command/date/result and unresolved items;
- tests proving Keen behavior, including local path/citation/auth boundaries.

First-release conclusion: Keen can use DeepTutor as a structural reference for
UI organization at the reviewed Apache-2.0 revision, but the implementation
remains a Keen-owned rewrite. The official Home screenshot is approved only as
the private Figma reference recorded here; no DeepTutor file or asset is
approved for runtime or distribution.

## 2026-07-26 Figma page-replication decision

The user requested a more systematic DeepTutor-led design process instead of
continuing from isolated inspiration. The reviewed source remains immutable
commit `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a` (`v1.5.1`). Its `web/app`
route inventory contains more than 50 route files, but many are authentication,
administration, provider configuration, Memory, partner, Agent, Co-Writer and
Book-product surfaces that do not map to Keen's current release contract.

“One-to-one” therefore has two distinct meanings:

1. **Reference study:** a Figma frame may reproduce a covered DeepTutor page's
   visible information architecture closely, labelled `Reference only`, with
   no claim that Keen implements the page.
2. **Keen adaptation:** a second frame keeps only the interaction pattern that
   maps to truthful Keen runtime state, using Keen components, variables,
   navigation and copy. This frame may become a Provisional page contract.

Reference frames do not enter release navigation and are not implementation
requirements by themselves. A study terminates only when it produces a Keen
page contract or an explicit `reject` decision.

### Route-family disposition

| DeepTutor route family at the reviewed commit | Reference study | Keen destination | Decision |
| --- | --- | --- | --- |
| `/(workspace)/home/[[...sessionId]]` unified Chat workspace | High fidelity: two-state sidebar, central thread/composer, optional Activity/source panel | Home Ask composition and existing contextual Agent Activity | **Adapt now.** Keep one `New learning` entry and no public capability/tool picker breadth. |
| `/(utility)/knowledge` | High fidelity: collection navigation, file list, selected-file detail and processing states | Knowledge Base | **Adapt now.** Preserve Keen indexing truth and local source boundaries. |
| `/(utility)/space/learning` mastery path | High fidelity: path list plus selected objective map | History + Review, with Deep Learn rail as current-step context | **Adapt selectively.** Do not add a primary Mastery product or duplicate BKT/FSRS truth. |
| `/(workspace)/book` reader state | High fidelity: bounded reader, chapter/spine rail, contextual chat and source references | Deep Learn | **Adapt reading hierarchy only.** Reject generated-book creation, thirteen block types and a new Book route. |
| `/(utility)/notebook` | Medium fidelity: filters/categories, saved entry list and inline edit state | Saved lesson notes inside History/Knowledge context | **Defer implementation.** Study the organization pattern; do not add navigation until a truthful note action exists. |
| `/(utility)/settings` hub and model/status subroutes | High fidelity for hub hierarchy and recovery states | Settings | **Adapt now.** Collapse DeepTutor's many provider/tool pages into Keen's existing bounded settings sections. |
| `/(utility)/space/chat-history`, `/questions`, `/notebooks` | Flow study only | History and Review | **Merge.** Do not create three parallel archives. |
| `/(workspace)/co-writer/**` | Low-priority reference | none in current slice | **Reject for v1.** It is a separate writing product. |
| `/(utility)/memory/**` | Architecture study only | none in current slice | **Reject for v1 UI.** Learner Memory needs evidence, privacy and edit/delete controls before discoverability. |
| `/(utility)/agents/**`, `/settings/agents`, `/settings/mcp`, `/settings/tools` | Architecture study only | contextual Activity and current Settings recovery | **Reject as primary UI.** Keen has no Agent marketplace or unrestricted tool administration. |
| `/(workspace)/partners/**` | none | none | **Reject.** Multi-channel partner management is outside the macOS learning client. |
| `/(auth)/**`, `/(admin)/**`, `/profile` | none | none | **Reject.** Keen is local-first and does not copy DeepTutor's multi-user administration. |
| `/playground` and capability-specific configuration | internal study only | existing Browser Demo/development routes | **Do not ship.** No release navigation or fabricated availability. |

### Figma execution order

Use the existing canonical file `ugwiIPdF43v2woYsLM3b9R`; do not create a
parallel design file or component system.

1. Duplicate a visually verified existing Keen frame so SF Pro text, variables,
   instances and screenshot rendering are inherited.
2. Build one `Reference only` frame from the reviewed DeepTutor code structure.
3. Build its paired `Keen adaptation / Provisional` frame using current runtime
   contracts.
4. Check the pair at 1180×740 for hierarchy, density, line wrapping, one primary
   action, error/loading/empty truth and no unsupported navigation.
5. Record node IDs and screenshots before moving to the next pair.

Pair order: Chat/Home → Knowledge Base → Mastery/History+Review → Book/Deep
Learn → Settings → Notebook/deferred decision.

An initial attempt to create a fresh DeepTutor study page on 2026-07-26 was
removed after visual verification showed that newly created SF Pro text nodes
were present in metadata but absent from Figma screenshots. No empty or
placeholder study page remains. The corrected attempt uses the upstream
screenshot as the visual source and fresh Geist/Lora nodes for the editable
reference instead of mutating a Keen frame.

### Study 1 result — DeepTutor Home reference

The first bounded reference study is now present on Figma page
`238:497` (`91 · Reference Studies · DeepTutor`):

| Purpose | Figma node | Status |
| --- | --- | --- |
| Official DeepTutor visual reference | `252:202` (`Reference only · Official DeepTutor Home screenshot · tracked v1.5.1 · 1180×660`) | Exact-aspect Figma image from upstream `assets/figs/web-1.4.6+/home/00-overview.png`; visually inspected |
| Editable visual replica | `257:157` (`Reference only · Editable DeepTutor Home replica · In Review · 1180×660`) | Geist/Lora, measured shell/sidebar/composer geometry, Lucide-equivalent vectors, and upstream reference-only logo fills; visually inspected |
| Rejected structural draft | `238:157` (`Rejected · mixed Keen/DeepTutor draft · do not use`) | Hidden; retained only for recovery/history |
| Rejected Keen adaptation | `238:327` (`Rejected · previous Keen Home Ask adaptation · do not use`) | Hidden; no longer a Provisional page contract |

The initial reference/adaptation pair mixed DeepTutor labels with the existing
Keen Home skeleton. Visual review correctly rejected it as sparse, inconsistent
and AI-generated in character. Both draft frames are now hidden. Node `252:202`
instead preserves the upstream Home screenshot at its exact 2939×1644 aspect
ratio, scaled to 1180×660 without cropping or black bars.

Node `257:157` is the first editable replica measured against `252:202`.
ImageMagick comparison at 1180×660 reported RMSE `0.0734996` and 16,513 pixels
outside 5% fuzz (`2.12031%`). The large identical white canvas makes the latter
number look better than local component fidelity, so the replica remains
`In Review`, not pixel parity. A separate Keen adaptation has not restarted.
The references include DeepTutor branding because they reproduce the upstream
screen, but remain internal/reference-only and must not enter Keen runtime or
distribution.
