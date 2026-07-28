# Round 01 acceptance

## Shell

- [x] Exactly one `New learning` entry.
- [x] Release navigation only: Home, Knowledge Base, Learning Feed, History, Review, Settings.
- [x] Sidebar width and content origin remain stable across Home, Feed, and Settings.
- [x] Active page state remains visible.
- [x] 1280×800 and 1440×900 evidence captured.

## Learning Feed

- [x] Task list is the primary left rail.
- [x] Today / Upcoming / Completed remain the default organization.
- [x] Calendar remains secondary.
- [x] Empty state has one primary route to Knowledge Base.
- [x] Loaded and selected-task states use the same two-column workspace.
- [x] Unselected context copy is height-aware and visually centered.
- [x] Loading and error states preserve the workspace structure.

## Task Detail

- [x] Detail opens in the second column; it does not add a third persistent column.
- [x] Status, facts, learning goal, expected steps, and next action have stable positions.
- [x] The close control restores focus to the owning task.
- [x] Normal state captured at 1440×900.
- [x] No independent loading/error state was invented; owning Feed states are documented instead.

## Verification

- [x] Layout detector: no findings.
- [x] App shell and Learning Feed tests: 33 passed.
- [x] Strict TypeScript check: passed.
- [x] ESLint: passed with zero warnings.
- [x] Production web build: passed.
- [x] Visual screenshots inspected in a contact sheet.
