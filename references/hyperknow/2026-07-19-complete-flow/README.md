# HyperKnow complete-flow audit — 2026-07-19

Internal research evidence only. The user authorized ordinary authenticated
navigation and one synthetic upload for Keen UI research. No HyperKnow source
code, browser storage, private network traffic, third-party trademarks, account
identity, or personal learning data was copied into Keen.

## Capture conditions

- Source: `https://agent.hyperknow.io/`
- Capture date: 2026-07-19, Asia/Shanghai
- Browser: the user's already-authenticated Chrome session
- Primary capture size: 1700×777 image pixels. CSS viewport/display scale were
  not separately retained, so these files are qualitative references rather
  than accepted pixel baselines.
- Learning Feed fallback captures: 1420×768 image pixels from the visible Chrome
  window. CSS viewport/display scale were not separately retained.
- Synthetic upload:
  `references/audit-fixtures/hyperknow-learning-flow-sample.txt`
- External actions deliberately not performed: Delete, calendar connection or
  write, Drive/Canvas connection, share/export, and any personal-data action.

## Step inventory

1. `01-current-deep-learn.png` — existing Deep Learn lesson, persisted progress
   and unit navigation. Route: `/deep-learn-session/9074065f-ecf0-450a-9eaa-a738c02f3990`.
2. `02-unit-complete-prompt.png` — first completion viewport after marking a
   unit complete. Same route.
3. `03-unit-complete-actions.png` — completion summary with Proceed/Later.
4. `05-learning-feed-empty.png` — Month Learning Feed empty state. Route:
   `/learning-feed`.
5. `06-learning-feed-week.png` — Week calendar view. Route: `/learning-feed`.
6. `07-learning-feed-pending.png` — Pending Tasks mode and its empty canvas.
   Route: `/learning-feed`.
7. `08-knowledge-base-existing-file.png` — Knowledge Base before the new upload.
   Route: `/knowledge-base`.
8. `09-knowledge-base-new-menu.png` — New Folder / Upload File menu.
9. `10-upload-processing.png` — the synthetic file processing in place.
10. `11-file-card-hover.png` — hover-only calendar and overflow actions.
11. `12-file-card-menu.png` — file menu showing Delete; Delete was not invoked.
12. `13-knowledge-search-no-match.png` — content-like search term returns no
    result, consistent with filename search in the inspected state.
13. `14-history-conversations.png` — History / Conversations. Route: `/history`.
14. `15-history-deep-learn.png` — History / Deep Learn Sessions.
15. `16-home-new-conversation.png` — default new-conversation Home. Route: `/`.
16. `17-home-attachment-ready.png` — synthetic text file attached to the request.
17. `18-conversation-planning.png` — generated learning plan and activity trace.
    Route: `/response/a3a68054-f5aa-4eb6-bee6-ce290c1cc33a`.
18. `19-diagnostic-question.png` — diagnostic result loaded while its question is
    below the fold.
19. `20-diagnostic-question-content.png` — actual diagnostic question, citation,
    next-action copy and suggested follow-ups.
20. `21-concept-explanation-and-recall.png` — plan/progress after the learner's
    diagnostic response; concept explanation was generated from the synthetic
    file and progress reached 40%.
21. `22-recall-question-and-next-step.png` — explanation tail, source citation,
    quick-recall question and explicit next step.

The missing number `04` is intentional: the attempted screenshot of the next
unit's loading state timed out and no file was created. DOM observation showed
progress moving from 42% to 75% and “Agent is thinking,” but this is not cited as
visual evidence.

## Findings used in Keen

- Keep the strong continuity pattern: current step, progress, next step,
  grounded explanation, recall, and a deliberate completion handoff.
- Do not copy the generic AI Home, wide empty canvases, unnamed Send control,
  hover-hidden primary file actions, quota overlay, or filename-search ambiguity.
- HyperKnow's next-unit thinking state exposed no phase, ETA, cancellation, retry,
  or recovery detail in the inspected viewport. Keen retains its explicit local
  loading, cancellation, unknown-write and recovery states instead.
- This audit supports qualitative organization and visual direction only. It is
  not a fixed-seed, dimension-aligned visual-regression baseline and proves no
  pixel parity.
