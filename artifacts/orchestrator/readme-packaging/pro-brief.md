# Pro review brief — Keen GitHub presentation

You are the product-narrative reviewer. Do not invent repository behavior,
tests, screenshots, release status, authorship, or user research.

## Task

Review and reshape Keen's GitHub README and product case-study narrative for a
large-model product/AGI management trainee portfolio.

The author wants the clarity and confidence of
`https://github.com/block/buzz`:

- centered product identity and one-line claim;
- a real full-width product screenshot early;
- plainspoken “what is this, really?” explanation;
- concrete stories before architecture;
- an honest works-now / not-yet boundary;
- technical depth available after the product is understood.

Do not copy Buzz's wording, bee humor, feature breadth, or architecture. Do not
use generic AI-startup language, fake metrics, badges for decoration, “redefine
learning,” “AI-powered,” “revolutionary,” gradient prose, endless card-like
feature bullets, or a defensive wall of security claims.

## Product facts

Keen is a local-first macOS learning Agent for self-directed learners studying
a bounded subject from their own material.

Implemented journey:

```text
choose/import source
→ state a learning goal
→ inspect a visible path
→ lesson
→ deterministic Recall
→ source-grounded help
→ targeted Practice
→ Summary and FSRS Review
→ resume from Home, Feed, History, or Review after restart
```

Distinct Agent loop:

```text
low-confidence opening reflection
+ incorrect deterministic Recall
+ validated source-grounded provider artifact
→ one evidence-backed prerequisite proposal
→ learner Accept or Keep
→ append-only plan version
→ bounded Undo
→ cold recovery without duplicate provider execution
```

The model may generate a bounded explanation or proposal. It may not grade,
write mastery, schedule Review, complete work, or silently mutate a plan.

Current stack:

- Tauri 2, React, strict TypeScript;
- supervised Python 3.11+ FastAPI learning-core sidecar;
- authenticated random-port loopback boundary;
- SQLite durable learning and Agent state;
- local PDF/Markdown/TXT ingestion and lexical/hybrid retrieval;
- explicit OpenAI-compatible/Ollama provider configuration.

Verified evidence currently includes:

- 47 desktop test files / 558 tests passing;
- focused Feed 25/25 and math/Deep Learn/Agent 49/49;
- strict TypeScript, zero-warning ESLint, production app build;
- strict local ad-hoc signature verification and bundled sidecar smoke;
- isolated native DeepSeek Recall → Agent → Accept → Practice flow;
- persisted 33% Session, accepted plan v2, two completed Agent runs, one
  proposal, one Recall, one Practice, and completed remediation lineage.

Honest boundaries:

- no learning-efficacy claim;
- no exact reference-product pixel-parity claim;
- local ad-hoc build is not Developer ID signed or notarized;
- OCR, cloud integrations, and broad autonomous curriculum planning are not
  current capabilities.

## Author's work to foreground

The author owned:

- product framing and competitive-reference selection;
- narrowing the product from a broad “learning OS” to one coherent loop;
- interaction architecture and navigation constraints;
- Agent authority boundaries and learner-approval model;
- acceptance criteria, orchestration, review, and native QA;
- deciding what to remove, defer, or veto.

Model-assisted engineering was used as an implementation multiplier. Do not
make tool orchestration the product story or suggest that the author manually
wrote every line.

## Current proposed narrative

1. Identity + one-line product claim.
2. One real native screenshot.
3. “What is Keen, really?”
4. “The learning loop” with one concise sequence.
5. Three short learner stories.
6. “Why this is an Agent, not a chat wrapper.”
7. Second real screenshot showing accepted plan adjustment.
8. “Works today / Not yet” boundary.
9. Product decisions / case-study link.
10. Quick start.
11. Compact architecture.
12. Verification and honest boundaries.

## Review format

Return:

1. `ACCEPT`, `REVISE`, or `REJECT`.
2. The three highest-impact narrative changes.
3. A final README outline with exact section names.
4. A proposed one-line tagline and the first 250–400 words.
5. What to cut from the current technical README.
6. Any claim that should be softened or removed.

Keep the response concrete enough for Codex to implement without guessing.
