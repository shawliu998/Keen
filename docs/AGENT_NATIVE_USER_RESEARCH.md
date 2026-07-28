# Agent-native learner research brief

Status: **directional public evidence and product hypotheses; not primary user research**.

Date: 2026-07-23.

This brief translates public learner discussions and human–AI research into bounded Keen product decisions. It is subordinate to `docs/PRODUCT_POSITIONING.md` and informs `docs/AGENT_NATIVE_ARCHITECTURE.md`. It does not authorize a new navigation item, broad learner profiling, background autonomy, bulk content generation, or a second Agent runtime.

## Question

How can Keen feel genuinely Agent-native while making the learner do more of the thinking, not less?

The working answer is:

> Keen should remember the learner's goal, source scope, current evidence, and next action; notice a meaningful learning event; select one bounded teaching move; show why it is acting and which sources it can use; then return the work to the learner and measure the next independent attempt.

The differentiator is the closed learning loop, not a chat surface:

```text
observe real state
→ select one bounded teaching action
→ expose reason and source scope
→ produce a contract-validated, source-linked artifact
→ require another learner action
→ apply deterministic learning updates
→ persist one next action
```

## Method and limits

This is a purposive qualitative scan, not a representative survey:

- public discussions from Reddit, Anki Forums, and Obsidian Forum were reviewed for concrete study behavior, failure cases, and control expectations;
- recent empirical work on AI tutoring was used to challenge community anecdotes rather than treat them as causal evidence;
- human–AI interaction and deployed-Agent guidance was used for control, feedback, and recovery patterns;
- no bulk scraping, private content, usernames, or personal learning data was retained;
- community posts are self-selected and often include product promotion; a cross-discussion signal below means the theme appeared in more than one included discussion, not that prevalence was measured;
- study results are context-specific and sometimes point in different directions. They support hypotheses and design constraints, not a general claim that one AI-access policy always improves learning.
- the included community sample contains 10 public threads dated 2025-03-16 through 2026-07-19, found through targeted queries about AI study summaries, flash cards and backlogs, source/PDF scope, vault assistants, and Agent permissions. This was not an exhaustive review or saturation study;
- original posts and public visible replies were considered where available. C6 and C10 are product/proposal threads, so they are treated as interaction-design discussion rather than independent evidence of learner demand.

## Directional signals and design inferences

| Signal or inference | Directional evidence and boundary | Keen implication |
| --- | --- | --- |
| Smooth explanations can create an illusion of understanding | Community accounts describe easy-to-consume summaries or answers that did not transfer to later explanation or problem solving (C1, C2, C8). Kim et al.'s large difference-in-differences study found better outcomes after rollout of a product whose tutoring followed an initial answer, but it did **not** isolate post-answer timing as the cause (R2). A separate 334-student randomized experiment found unrestricted access outperformed a blunt initial-reading gate (R3). | Preserve learner access, but organize Deep Learn around `attempt → help → transfer test`. Do not make “read first for N minutes” a universal gate, and never treat generated explanation as mastery evidence. |
| Bulk AI generation creates low-yield material and can compound review debt | Anki discussions report trivial, inaccurate, or personally irrelevant generated cards (C3, C4); a separate non-AI-specific discussion shows how review volume itself becomes overwhelming (C5). These are self-selected accounts, not prevalence or causal estimates. | Do not generate a deck on import. Use actual attempts and explicit goals to propose at most one bounded next intervention or a very small previewable review candidate set. |
| Source scope is part of trust | Learners and PKM users question partial PDF ingestion and default whole-vault access (C7, C9). In a controlled HCI study, explanations increased reliance on both correct and incorrect outputs, while sources reduced reliance on incorrect outputs (R6). | Source scope, ingestion limits, and citation targets must be visible product state. Agent tools receive the exact current scope; scope expansion is never silent. Do not use an explanation or confidence label as trust decoration. Unsupported diagrams remain a separate known Keen ingestion/citation limit, not a finding attributed to these discussions. |
| Learners want less workflow management, not less thinking | Backlog and fragmented-tool discussions describe overhead while still valuing active questions and personal judgment (C5, C8, C10). | Keen chooses a safe teaching default and presents one `Next up`. It absorbs orchestration work while leaving the learner's attempt, rating, and consequential plan choices explicit. |
| Long chat history is a continuity risk; typed state is a Keen design inference | Community discussion describes long chats drifting or losing the original topic (C8), while PKM/Agent discussion raises stale-context concerns (C10). The evidence does not establish a measured preference for typed state over chat history. | Persist typed state—goal, scope, Session, Unit, attempt, evaluation, due Review, an explicitly saved preference, and next action—not a model-authored learner biography or indiscriminate transcript memory. |
| Quiet contextual proactivity is a design hypothesis | One explicit Anki reply objected to intrusive heuristic warnings (C6); mixed-initiative guidance says intervention timing and uncertainty should be handled carefully (R4, R5). This is not a measured multi-learner preference. | Agent intervention stays inline in Deep Learn at a real checkpoint. The no-avatar, no-floating-composer, no-third-column boundary also comes from Keen's canonical product scope, not from this one forum signal. |
| Control should sit at a meaningful decision boundary | Selection-scoped/read-only preferences appear in PKM discussion (C7). Deployed-Agent reports favor fewer low-risk micro-approvals while retaining plan review, cancellation, and recovery (R8, R9), but those observations are primarily from coding Agents and may not transfer to learning writes. | Read-only work inside an already chosen source scope may be streamlined. Plan changes show a bounded diff and require one explicit decision. Local writes return a receipt and safe Undo; external or destructive actions retain confirmation. |
| System output is not learning evidence | Community discussions distinguish “AI made good notes/cards” from being able to recall or apply them (C1, C3, C4). The tutoring studies separately measure assisted use and later assessment outcomes (R1–R3). | Judge the intervention by subsequent unassisted Practice and delayed Review, not generation success, dwell time, length, likes, or model self-rating. |

## Counter-signals

The community material is not unanimous:

- some replies in the Anki card-generation discussion find AI useful for small, source-bounded card sets when the learner checks and edits them (C3). Keen therefore rejects automatic bulk generation in the current phase, not all future assisted authoring;
- at least one Vault/Agent discussion favors a generic chat entry, wider write access, and less micromanagement (C10). That preference comes from a product-proposal context rather than a validated Keen learning task, so it does not override the current one-entry navigation, deterministic learning-state ownership, or confirmation boundary;
- the unrestricted-access result in R3 is a direct warning against turning `attempt first` into a universal time gate. Keen's current rule is narrower: generated help cannot silently perform or count as the assessed attempt.

## Product decision: what “more Agent-native” means for Keen

Keen should move from a reactive assistant pattern to a mixed-initiative learning pattern:

| Pattern | User experience | Keen decision |
| --- | --- | --- |
| Reactive assistant | The learner restates context, chooses a tactic, and writes a prompt for every turn. | Existing Conversation remains useful for Ask, but this is not the Agent-native learning target. |
| Embedded learning Agent | Keen detects a real learning event, selects one bounded tactic from current state, makes its reason and scope legible, then waits for the learner's next action. | **Target for Agent-native v1.** |
| Learning steward | Keen restores the exact goal and next action across sessions and proposes a local plan adjustment after repeated evidence or an explicit goal/time change. | Later bounded slice, using existing Session, Task, Review, Feed, and History truth. |
| Autonomous curriculum manager | A model creates a long-range plan, bulk content, reviews, reminders, and completion state in the background. | Rejected for the current product boundary. |

An interaction qualifies as Agent-native for the current phase only if all are true:

1. The learner does not need to restate the current goal, source scope, Unit, or previous attempt.
2. Keen selects a context-appropriate bounded teaching action from authoritative state instead of exposing a generic prompt box.
3. The learner can understand `why now`, `using which sources`, and `what happens next` without opening an Agent log.
4. The action produces another learner decision or attempt; it does not end the loop with generated content.
5. Generated prose cannot write grading, BKT, FSRS, mastery, completion, or source truth.
6. The action is steerable, cancellable, and recoverable at the level appropriate to its consequence.
7. The same learning state and next action restore after reload or process restart.

If the user must repeatedly prompt the system to remember context or decide the teaching tactic, the experience is still assistant-led. If the system silently chooses goals, sources, grades, or plan mutations, it is uncontrolled automation. Keen's target is the bounded middle.

## Product contracts informed by research and canonical Keen scope

These contracts combine community signals, HCI guidance, and binding decisions already present in `docs/PRODUCT_POSITIONING.md`. They are conservative product choices, not claims that every listed UI constraint was directly requested by forum participants.

### Home / New learning

- Ask only for intent, explicit source scope, goal, and later—when it affects the plan—an optional time budget or deadline.
- Do not ask the learner to choose a model, Agent, Teaching Playbook, retrieval method, or study-method taxonomy.
- Before creation, make the selected source scope and any partial ingestion state inspectable.
- Saved work continues to show one real cross-course `Next up`; do not replace it with an AI-generated dashboard or a list of speculative recommendations.

### Deep Learn

- After a persisted incorrect Recall attempt, the deterministic policy chooses one specific eligible help action, initially a source-grounded alternate explanation.
- The inline offer communicates three facts in compact language:
  - `Why now`: the recorded Recall did not meet the expected answer.
  - `Scope`: before activation, enumerate the intended current document(s) and eligible excerpt/page range for this Unit and label partial text or unavailable diagrams. Activation must revalidate and freeze the actual scope; if source or Session revision changed, refresh or fail closed instead of silently using the preview.
  - `Then`: continue to a new Practice attempt.
- The offer must be more specific than `Ask AI` or a blank `Explain another way` prompt. The first fixed Playbook can be expressed as `Generate an explanation from these excerpts`; later policy-selected variants may be `Use an example from these excerpts` or `Start with a hint`.
- v1 remains learner-activated while trust and usefulness are being validated. It should take one action, not ask the learner to author a prompt. A later automatic low-risk start requires explicit product evidence and an easy opt-out; “Agent-native” alone is not permission to spend provider resources or interrupt the lesson.
- The ready state has one primary action, `Continue practice`. `View sources` discloses the durable excerpt/page context supported by the current citation capability and visibly fails or degrades when extraction/geometry is partial; `Try another approach…`, `Test me instead`, and `Return to source` stay secondary.
- An intervention may address the submitted response, but a model-inferred misconception is a hypothesis, not confirmed learner state. It must not be persisted as fact until deterministic or explicit evidence supports it.
- No generated artifact, including a perfect explanation, can advance mastery or complete the Unit.

### Source disclosure

- Reuse the existing Conversation/PDF evidence pattern so a Deep Learn citation can open the saved excerpt, page, section, and document revision where the current capability supports them.
- State partial extraction, unsupported diagrams, stale versions, and unavailable source geometry at the point where they limit the action.
- Never silently add web results or another course to make an answer easier.

### Learning Feed and History

- Feed exposes one actionable next item while keeping the real workload discoverable; it must not hide review debt behind a reassuring empty state.
- Agent proposals say why an item resurfaced—for example, a due Review, an unfinished Session, or repeated independent difficulty—using recorded reason codes rather than model-authored motivation claims.
- History preserves the intervention, source snapshots, learner steering, and subsequent attempt lineage. It is a learning record, not a chain-of-thought or tool-console transcript.

### Review

- Keep FSRS scheduling and learner ratings deterministic and explicit.
- Do not bulk-create Review items from imported text. A future candidate item must be source-anchored, motivated by real difficulty or an explicit learner choice, previewable, and bounded in count.
- A future workload-recovery proposal may pause new work or defer a bounded set, but it must not falsify grades, silently erase backlog, or rewrite scheduling history.

## Prioritized product hypotheses

These hypotheses terminate in the existing learning loop and do not add primary navigation.

| Priority | Hypothesis | Product slice | Evidence needed before expansion |
| --- | --- | --- | --- |
| P0 | After a real incorrect Recall, a learner-activated cited alternate explanation can lead coherently into another independent attempt without obscuring source scope or grading authority. This is a synthesized hypothesis; the cited studies did not directly compare this Keen interaction with fixed rereading. | Existing Agent-native Slices 0–1: exact Run Profile, authoritative context, contract-validated source-linked inline artifact, then parallel Practice and restart recovery. | Subsequent unassisted Practice and delayed Review as non-causal outcome signals; request-for-another-approach/cancel rate; source-contract failures; and qualitative understanding of `why/scope/next`. Any claim of improvement over rereading requires a separately designed comparison. |
| P0 | Source grounding is more trustworthy and actionable when the learner can inspect the supporting evidence and its limits. | Make Deep Learn Agent citations open the durable excerpt/page context supported by the existing citation system, with partial/unsupported states visible. | Task-based source verification with supported and partial/unsupported documents; no wrong-revision resolution. |
| P1 | Closed steering makes the Agent adaptable without turning Study into chat. | Existing Slice 2: shorter, source example, different explanation, direct test, cancel; one active run and immutable superseding artifacts. | Whether learners can recover from an unhelpful explanation without leaving the lesson or authoring a prompt. |
| P1 | One visible, authoritative next action reduces management overhead without hiding workload. | Existing Session Steward work, after Feed projects the real Session phase consistently. | Cross-page/restart consistency and usability evidence that the learner can distinguish the immediate action from total due work. |
| P2 | A bounded plan diff after repeated independent failure is more useful than automatic replanning. | Existing Slice 3: insert/split/reorder only unstarted work; reason codes, citations, explicit accept/keep, receipt, and safe Undo. | Repeated-evidence trigger quality, acceptance/Undo behavior, downstream unassisted outcomes, and no increase in abandonment or hidden review debt. |
| Explore later | A valuable Ask answer should be convertible into Practice or Focused Study without re-entering context. | Contextual action from the existing Conversation record into the existing Focused Study contract; no new route or Session type. | First complete Slices 0–2 and validate that users actually want to continue Ask into active learning. |

## What not to build

The following may look Agent-native but conflict with the research and Keen's product boundary:

- an Agent home page, activity feed, assistant avatar, floating chat, or multiple teaching personas;
- automatic whole-course summaries, decks, quizzes, or long-range curricula after import;
- default whole-library context, silent web search, or cross-course source expansion;
- mastery updates from reading, clicks, dwell time, generated notes, or model confidence;
- raw conversation history treated as durable learner Memory;
- inferred personality, motivation, fatigue, anxiety, or fixed “learning style” profiles;
- automatic plan, Review, calendar, completion, export, share, or destructive mutations;
- pop-up warnings after every weak attempt or a permanent row of competing Agent actions;
- token counts, tool-call counts, generated length, or engagement time presented as learning success;
- a multi-Agent runtime or framework introduced before one bounded intervention improves the real loop.

## Candidate primary-research follow-up — not authorized or scheduled

Public discussions identify risks and language; they do not validate Keen's exact interaction. Before expanding beyond the first intervention and closed steering:

1. If separately approved, recruit 6–8 self-directed university, postgraduate, or professional learners who study a bounded subject from their own materials. Any external outreach requires explicit user authorization, community-rule review, informed consent, a minimal data/retention plan, and a way for participants to withdraw; this document authorizes none of those actions.
2. Use one source-scoped learning task with an intentionally difficult Recall. Compare a generic `Explain another way` offer with the specific mixed-initiative `why/scope/next` contract.
3. Test four moments: incorrect Recall, steering to another approach, supported excerpt/page inspection with partial-state disclosure, and reload/restart return.
4. Ask participants to explain in their own words why Keen intervened, what it used, what it changed, and what they must do next.
5. Treat confusion about scope, grading authority, plan mutation, or completion as a blocking product defect even if participants like the generated explanation.
6. Interview separately about workload recovery and Ask-to-Practice before scheduling either capability.

This qualitative round should refine copy and control placement. It is not large enough to claim learning efficacy; the product must still use subsequent independent Practice and delayed Review evidence.

## Source set

Community evidence:

- C1 — Reddit / r/studytips, 2026-07-05, original post and discussion: [I used AI. It goes horribly wrong](https://www.reddit.com/r/studytips/comments/1uogrex/i_used_ai_it_goes_horribly_wrong/)
- C2 — Reddit / r/GetStudying, 2026-04-14, original post and discussion: [Anyone actually using auto-summarizing tools for studying?](https://www.reddit.com/r/GetStudying/comments/1sl6h3w/anyone_actually_using_autosummarizing_tools_for/)
- C3 — Reddit / r/Anki, 2025-08-01, original post and discussion: [Problem with AI-generated flashcards](https://www.reddit.com/r/Anki/comments/1mewr8p/problem_with_aigenerated_flashcards/)
- C4 — Anki Forums, 2025-06-06, original post and replies: [LLM-made cards flooded my Anki with low-yield cards](https://forums.ankiweb.net/t/turns-out-llms-made-cards-flooded-my-anki-too-much-low-yield-cards-i-didnt-use-anki-much-for-my-final-exam/62266)
- C5 — Reddit / r/Anki, 2026-06-20, original post and discussion: [Overwhelmed with Anki cards](https://www.reddit.com/r/Anki/comments/1uanj7t/overwhelmed_with_anki_cards/)
- C6 — Anki Forums, 2025-06-26, product proposal and replies: [An intelligent Card Quality Assistant](https://forums.ankiweb.net/t/an-intelligent-card-quality-assistant-to-help-users-avoid-common-pitfalls/63138)
- C7 — Reddit / r/ObsidianMD, 2025-03-16, original post and discussion: [Any unintrusive and privacy-friendly AI plugins?](https://www.reddit.com/r/ObsidianMD/comments/1jcdt0b/any_unintrusive_and_privacyfriendly_ai_plugins/)
- C8 — Reddit / r/GetStudying, 2025-11-19, original post and discussion: [Do you use AI in your studies?](https://www.reddit.com/r/GetStudying/comments/1p0zh2z/do_you_use_it_in_your_studies/)
- C9 — Reddit / r/notebooklm, 2026-07-19, original post and discussion: [What am I doing wrong with PDFs?](https://www.reddit.com/r/notebooklm/comments/1v0bfr9/what_am_i_doing_wrong_with_pdfs/)
- C10 — Obsidian Forum, 2026-01-31, product proposal and replies: [Vault Intelligence: active reasoning for your vault](https://forum.obsidian.md/t/vault-intelligence-active-reasoning-for-your-vault/110675)

Research and interaction guidance:

- R1 — Bastani et al., PNAS 2025, peer-reviewed field experiment: [Generative AI Without Guardrails Can Harm Learning](https://doi.org/10.1073/pnas.2422633122)
- R2 — Kim et al., 2025 working paper, large product rollout analyzed with difference-in-differences: [Generative AI Can Improve Performance and Engagement without Harming Learning](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5929576)
- R3 — Fischer, Rau, and Rilke, IZA Discussion Paper 18338, randomized experiment with 334 university students: [AI Tutoring Enhances Student Learning Without Crowding Out Reading Effort](https://www.iza.org/publications/dp/18338/ai-tutoring-enhances-student-learning-without-crowding-out-reading-effort)
- R4 — Amershi et al., CHI 2019, human–AI interaction guidance: [Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/)
- R5 — Horvitz, CHI 1999, mixed-initiative design principles: [Principles of Mixed-Initiative User Interfaces](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/chi99horvitz.pdf)
- R6 — Microsoft Research, CHI 2025, controlled study of explanations, sources, inconsistencies, and reliance: [Fostering Appropriate Reliance on Large Language Models](https://www.microsoft.com/en-us/research/publication/fostering-appropriate-reliance-on-large-language-models-the-role-of-explanations-sources-and-inconsistencies/)
- R7 — Anthropic, 2024, engineering guidance: [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- R8 — Anthropic, 2026, deployed-Agent control patterns, primarily from coding use: [Trustworthy agents in practice](https://www.anthropic.com/research/trustworthy-agents)
- R9 — Anthropic, 2026, autonomy observations, primarily from coding use: [Measuring AI agent autonomy in practice](https://www.anthropic.com/research/measuring-agent-autonomy)
