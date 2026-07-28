# ChatGPT Pro review — Keen GitHub presentation

Date: 2026-07-27
Input: the bounded product facts, author-role boundary, Buzz reference
principles, and the complete first README draft.

## Decision

`REVISE`

Pro judged the direction close to a strong product-led GitHub page, but found
that technical credibility still outweighed product appeal too early. For an
AI-product portfolio, the first screen should establish why this Agent needs
to exist before proving how carefully it is engineered.

## Three required changes

1. Replace the capability-led tagline with user value plus the Agent
   distinction. Recommended direction:
   “Keen is a local-first learning Agent that adapts your study path only when
   your learning evidence supports it.”
2. Put one real learning moment before architecture:
   `wrong Recall → evidence → intervention → prerequisite proposal → learner
   Accept → new plan version`.
3. Compress Product decisions to four ideas or fewer and keep the reference
   selection, reversals, and detailed trade-offs in
   `docs/PRODUCT_CASE_STUDY.md`.

## Recommended order

1. Identity, value proposition, real screenshot.
2. What is Keen, really?
3. A learner story: when the first explanation fails.
4. A learning loop that can adapt.
5. Why this is an Agent, not a chat wrapper.
6. Built and verified today / Not yet.
7. Short Product decisions.
8. Architecture.
9. Verification.
10. Quick start.
11. Repository map.

## Claim review

- `Agent` is supported because the implemented loop observes, decides, acts,
  waits for approval, persists, and recovers.
- “earns the right to change the plan” should be softened so it cannot imply
  that the Agent owns curriculum control. Prefer “proposes changes when
  evidence supports them.”
- Do not use `AGI` as a product capability claim.
- Keep engineering boundaries, but do not repeat model authority, approval,
  and deterministic ownership across every section.

## Codex technical judgment

Accepted. The final copy keeps the product-level Pro changes while preserving
the repository's narrower truth: the Agent proposes a bounded change; the
learner accepts or keeps it; deterministic domain code applies the version.

## Final review after revision

`ACCEPT README`

Pro confirmed that the revised page:

- leads with learner value and the evidence-supported Agent distinction;
- tells the complete Recall failure → intervention → proposal → learner
  decision → plan-version story before architecture;
- separates built and verified behavior from efficacy, parity, release, and
  broad-autonomy claims;
- presents the author's product framing, competitive analysis, interaction
  architecture, Agent boundaries, acceptance criteria, orchestration, and
  review role without implying sole manual authorship of the code;
- avoids generic AI-startup language and unsupported AGI or autonomous-tutor
  claims;
- works for both product and technical portfolio reviewers.
