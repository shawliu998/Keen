# Keen design direction

Status: frozen for the current guided-learning product phase.

This document is the decision layer between product behavior, Figma, competitor research, and React. It prevents a new reference or isolated visual preference from replacing the whole interface direction.

Product scope and priority are defined by `docs/PRODUCT_POSITIONING.md`. This document governs how that product direction is expressed visually; it must not create a competing product strategy.

## Product direction

Keen turns course materials into a continuous guided learning path. Sources, the learner's goal, current step, progress, and next action come before open-ended assistant chrome. Asking a question is one learning tool, not the product's organizing metaphor.

The stable visual register is light, restrained, compact, and familiar to macOS desktop users. Hierarchy comes from typography, spacing, dividers, and selection state. Cards, badges, shadows, and motion are used only when they communicate structure or state.

## Decision hierarchy

When inputs conflict, use this order:

1. Verified runtime behavior and data contracts.
2. This document and the approved page structure below.
3. Figma pages explicitly named `Approved`.
4. Keen design tokens and shared React components.
5. Authorized HyperKnow references.
6. Other competitor and open-source references.
7. Isolated aesthetic feedback.

An item lower in the hierarchy cannot silently replace an item above it. A product-structure change requires an explicit update to this file before Figma or React is changed.

## Figma status contract

Canonical file: `Keen Desktop UI — HyperKnow Layout Study` (`ugwiIPdF43v2woYsLM3b9R`).

- `Approved`: production design specification. React may follow it.
- `Provisional`: implementation snapshot or unresolved proposal. It is evidence, not specification.
- `Reference`: internal research. It may inform measurements and interaction organization but cannot overwrite an approved Keen screen.
- `Draft` / `In review`: exploration that must not be implemented as a new direction before approval.

Current canonical screens:

- `06.01 · Approved · Home`
- `06.02 · Approved · Learning Feed`

Current research and implementation evidence:

- `90 · Reference Studies · HyperKnow`
- `80 · Implementation Snapshots · Provisional`

The remaining core screens become canonical only after they are reconciled, reviewed, and renamed `Approved`.

## Stable information architecture

Primary navigation:

- New learning
- Home
- Knowledge Base
- Learning Feed
- History
- Review due
- Settings

Deep Learn is entered from a request, task, or history item rather than as a fixed top-level destination. Planner, Learner Memory, Quiz specimens, Visualize, and integrations do not enter primary navigation until their underlying state and actions are implemented. Development routes may remain available when visibly labeled.

The contextual Inspector is not an always-populated feature. It appears only after the user selects real or explicitly labeled sample source, citation, task, or learning context.

## Stable page structures

### Home

Home uses one adaptive composition rather than switching between unrelated concepts:

1. `Today` and the learning queue establish what can be continued.
2. The request workbench follows the queue when work exists.
3. The workbench becomes visually primary for first use or an empty queue.
4. Ask and Study are the only persistent request intents in the current UI.

Do not replace this with either a generic assistant landing page or a dashboard-card grid.

### Learning Feed

The desktop composition is a task/schedule workspace with task state and calendar context. Compact layouts prioritize the task list instead of stacking a full calendar below it. Calendar integration and external writes remain outside this layout until implemented.

### Knowledge Base

Knowledge Base is a source-management list. Import is the only dominant action. Course scope, search, filtering, indexing state, recovery, and source actions remain visible without adding overview metrics or a knowledge-graph dashboard.

### Conversation

Conversation is a document-style learning record, not a bubble chat. It contains course/source scope, learner question, response, evidence, citations, recovery state, and a restrained continuation composer. A new conversation starts empty.

### Deep Learn

Deep Learn uses a learning-path rail, an editorial reading column, an end-of-reading practice action, and contextual source inspection. It does not gain a floating assistant, generic recommendations, or synthetic mastery dashboards.

### Review

Review is a focused due-item flow: prompt, optional recall, reveal, source context, FSRS rating, and the next item. Empty and recovery states return the learner to a real next action.

### Settings

Settings contains Status, Capabilities, Privacy & data, and Open source. Provider and external integrations stay grouped under Capabilities until configuration is implemented.

## HyperKnow adoption matrix

| Reference pattern | Keen decision |
| --- | --- |
| Compact sidebar proportions and selected navigation | Adapt |
| Full-width primary workspace before contextual inspection | Adopt |
| Home request workbench | Adapt below/alongside the learning queue |
| Generic assistant landing-page grammar | Reject |
| Feed task rail and calendar relationship | Adopt |
| Knowledge Base list, upload states, hover actions, and menus | Adapt to real Keen import/index states |
| Conversation planning and citation organization | Adapt |
| Chat-bubble visual language | Reject |
| Deep Learn path, current/next continuity, and reading flow | Adopt |
| Review-plan continuity | Adopt only when backed by persisted Keen state |
| Synthetic mastery, memory inference, or recommendation values | Reject |
| Calendar, Drive, Canvas, and provider success states | Defer until implemented |
| HyperKnow trademarks, user content, and implementation source | Reject for distribution |

## Frozen reference responsibilities

The approved direction is not a visual blend chosen independently on each
page. Each source has one bounded responsibility:

- **HyperKnow owns workspace composition:** navigation density, learning-path
  rail, editorial reading column, inline loading/recovery states, compact
  anchored menus, and continuity between the current step and next action.
- **DeepTutor owns interaction engineering references:** master-detail learning
  maps, accessible picker behavior, focus restoration, drawer/content
  coordination, and reduced-motion handling. Its chat-first product structure,
  feature inventory, branding, and decorative motion do not become Keen's
  information architecture.
- **Keen owns identity and product truth:** macOS desktop proportions, Keen
  assets, course/source scope, persisted tasks and sessions, deterministic
  learning state, and capability boundaries.

When two references disagree, use HyperKnow for page structure, DeepTutor for
the behavior of an equivalent control, and Keen for copy, data, state, and
brand. Do not alternate the dominant source between pages.

## Frozen interaction and motion contract

Motion communicates state change; it does not decorate pages.

- Hover, focus, selected, and ordinary control transitions: `150ms`.
- Menus, popovers, and inline state replacement: `180–200ms`.
- Sidebar collapse or coordinated panel resize: `300ms` using one shared
  standard easing curve.
- Loading skeletons preserve the final page geometry. Do not replace a stable
  workspace with a centered spinner, success modal, or unrelated loading card.
- Step changes update selection, content, progress, and next action in place.
  The shell and reading position remain stable unless navigation genuinely
  changes the page.
- Popovers originate at their trigger, use one quiet border and restrained
  elevation, close on Escape/outside interaction, restore focus, and never
  become floating feature showcases.
- Drawers and inspectors resize or overlay the content as one coordinated
  transition. A contextual panel is absent until a real source, citation, task,
  or learning object is selected.
- Completion is a flat result state with one primary next action. It is not a
  celebratory modal, assistant bubble, or nested card stack.
- Under `prefers-reduced-motion: reduce`, looping animation stops and required
  state transitions become effectively immediate while preserving focus and
  status communication.

Pages may not introduce a new duration, easing curve, radius family, shadow
family, or animation pattern without first changing this contract. This is the
anti-churn boundary for the remaining UI migration.

## Change control

Visual feedback should be resolved at the smallest responsible layer:

1. Copy and labels.
2. Icon choice or size.
3. Token, border, radius, shadow, or typography.
4. Component composition.
5. Page hierarchy.
6. Product structure.

Only level 6 changes this document. A new competitor screenshot alone is never a level-6 decision.

An approved baseline can change only for a recorded functional change, component-system correction, accessibility correction, or explicit design decision. Every accepted screen records its viewport, deterministic fixture, interaction state, reduced-motion setting, Figma node, and React capture. A differently sized competitor capture is qualitative evidence, not a pixel baseline.
