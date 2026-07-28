# HyperKnow full synthetic-flow audit — 2026-07-19

## Scope

- Authorized source: `https://agent.hyperknow.io/` under the user-attested scope in `references/authorized-scope.md`.
- Browser: the user's authenticated Chrome session; no browser storage, private network traffic or implementation source was inspected.
- Display evidence: 1700×777 image pixels at device scale 2.
- Payloads: synthetic non-personal learning content only. The new upload was `output/pdf/hyperknow-bayesian-learning-fixture.pdf`, a three-page generated PDF with page anchors and no personal or third-party content.
- Privacy: no account identifiers, existing cloud files, calendar events, LMS courses or unrelated user-created learning data were intentionally retained.

## Observed flow

1. Submitted a synthetic learner answer to the existing eigenvectors recall prompt.
2. HyperKnow advanced the visible plan to `Next Steps · 80%` and produced source chips tied to the uploaded synthetic text fixture.
3. Requested a three-item review plan that explicitly distinguished recommendations from completed actions.
4. HyperKnow advanced the plan to `Review Plan · 90%` and returned suggested review times, evidence-of-mastery statements and page-labelled source chips.
5. Uploaded the generated three-page Bayesian learning PDF. Knowledge Base quota advanced from 2/5 to 3/5 and the card appeared with a three-page preview.
6. Navigating Home triggered an expired-session redirect to `/signin`. Google sign-in did not recover the session or open an account-selection tab. Calendar, Drive and Canvas live entry states were therefore not tested in this run; they remain authentication-blocked rather than passed.

## Screenshot inventory

| File | State | Acceptance |
| --- | --- | --- |
| `01-current-recall-state.png` | Existing recall conversation with a transient session-refresh toast | Retained as recovery evidence; rejected as a stable design reference |
| `02-recall-feedback.png` | Stable 80% next-step result with source chips and two messages remaining | Accepted for qualitative interaction reference |
| `03-review-plan.png` | Stable review-plan completion, recommendation language and 90% progress | Accepted for qualitative interaction reference |
| `04-review-plan-details.png` | Review-plan heading and first item with a transient session-refresh toast | Retained as recovery evidence; rejected as a stable design reference |
| `05-pdf-uploaded.png` | Knowledge Base three-card state with the generated PDF preview and 3/5 upload usage | Accepted for qualitative file-processing reference |

## Product conclusions used in Keen

- Preserve visible current/progress/next continuity, but avoid HyperKnow's floating bottom composer and quota overlay.
- Review output works better as a document-like evidence summary than as another assistant bubble.
- Citation chips should stay compact and adjacent to the statement they support.
- Suggested review timing and evidence-of-mastery are useful together, but Browser Demo must label both as illustrative and unscheduled.
- Integration state testing should be explicit and reversible. Keen now exposes `Sample connected` previews only inside Settings demo mode; they do not open OAuth, read accounts, persist state or imply an implemented adapter.

This audit is qualitative. No accepted fixed reference baseline or pixel mismatch percentage exists, and no HyperKnow trademark, screenshot or personal content is shipped in Keen.
