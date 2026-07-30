import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DeepLearnPage } from "../src/features/deep-learn/DeepLearnPage";
import { SettingsPage } from "../src/features/settings/SettingsPage";
import { LearningCoreResponseError, LearningCoreSchemaError } from "@keen/api-client";

const core = vi.hoisted(() => ({ current: null as never, setInspector: vi.fn() }));
vi.mock("../src/services/LearningCoreProvider", () => ({ useLearningCore: () => core.current, isLearningCoreStarting: () => false }));
vi.mock("../src/state/appStore", () => ({ useAppStore: () => ({ setInspector: core.setInspector }) }));
const time = "2026-07-18T10:00:00+00:00";
const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Limits study", mode: "study" as const, goal: "Learn limits.", estimated_minutes: 20, status: "studying" as const, progress: 0.2, revision: 2, created_at: time, updated_at: time, started_at: time };
const unit = { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"], title: "Definition", objective: "Read the definition.", content: "Source display text.", estimated_minutes: 10, status: "active" as const };
const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Source grounded.", units: [unit, { ...unit, id: "unit-2", ordinal: 1, title: "Examples", status: "ready" as const }] };
const recallUnit = { id: "unit-1", ordinal: 0, estimated_minutes: 10, status: "active" as const, created_at: time, updated_at: time };
const recallSession = { id: "session-1", course_id: "course-1", status: "studying" as const, revision: 2, progress: 0.2, estimated_minutes: 20, current_unit_id: "unit-1", created_at: time, updated_at: time, started_at: time, finished_at: null };
const baseRecall = { course_id: "course-1", session: recallSession, plan: { id: "plan-1", session_id: "session-1", version: 1, units: [recallUnit, { ...recallUnit, id: "unit-2", ordinal: 1, status: "ready" as const }] }, current_unit: recallUnit };
const notStarted = { outcome: "not_started" as const, ...baseRecall, checkpoint: null, run: null, grade: null };
const pending = { outcome: "pending" as const, ...baseRecall, session: { ...recallSession, status: "active_recall" as const, revision: 3 }, checkpoint: { id: "checkpoint-1", kind: "active_recall" as const, prompt: "What does a limit describe?", status: "pending" as const, created_at: time, answered_at: null }, run: { id: "run-1", status: "pending" as const, checkpoint_id: "checkpoint-1", generator_version: "source-cloze-v1", created_at: time, answered_at: null, cancelled_at: null, cancellation_reason: null }, grade: null };
const answered = { ...pending, outcome: "answered" as const, session: { ...pending.session, status: "practicing" as const, revision: 4 }, checkpoint: { ...pending.checkpoint, status: "answered" as const, answered_at: time }, run: { ...pending.run, status: "answered" as const, answered_at: time }, grade: { correct: true, score: 1, max_score: 1, grader_version: "exact-v1" } };
const answeredIncorrect = { ...answered, grade: { ...answered.grade, correct: false, score: 0 } };
const remediation = { id: "action-1", course_id: "course-1", session_id: "session-1", unit_id: "unit-1", kind: "remediate" as const, status: "pending" as const, reason_code: "active_recall_incorrect" as const, policy_version: "adaptive-session-policy/1.0.0" as const, revision: 0, created_at: time, started_at: null, completed_at: null, cancelled_at: null };
const practiceAction = { ...remediation, id: "action-2", kind: "practice" as const, reason_code: "remediation_completed" as const };
const practiceNotStarted = { outcome: "not_started" as const, course_id: "course-1", session: answered.session, plan: answered.plan, current_unit: recallUnit, checkpoint: null, run: null, grade: null };

function renderPage(client: Record<string, unknown>) {
  core.current = { status: "healthy", client, connectionGeneration: 1, retry: vi.fn() } as never;
  return render(<MemoryRouter initialEntries={["/deep-learn/session-1?course_id=course-1"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Routes><Route path="/deep-learn/:id" element={<DeepLearnPage />} /><Route path="/settings" element={<SettingsPage />} /></Routes></QueryClientProvider></MemoryRouter>);
}
const study = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session, plan, current_unit_id: "unit-1", recovery_action: null }));

describe("Deep Learn active recall", () => {
  it("replaces practice with persisted source review after incorrect recall and focuses the single next route", async () => {
    const user = userEvent.setup();
    const actionRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: remediation };
    const practiceRequired = { ...actionRequired, action: practiceAction };
    const getStudySessionAdaptiveState = vi.fn().mockResolvedValueOnce(actionRequired).mockResolvedValueOnce(practiceRequired);
    const completeStudySessionAdaptiveAction = vi.fn(async () => ({
      outcome: "applied" as const,
      course_id: "course-1",
      session: answered.session,
      plan,
      completed_action: { ...remediation, status: "completed" as const, revision: 1, started_at: time, completed_at: time },
      current_action: practiceAction,
    }));
    renderPage({
      getStudySession: study,
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState,
      completeStudySessionAdaptiveAction,
      getStudySessionPractice: vi.fn(async () => practiceNotStarted),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { level: 2, name: "Review needed" })).toHaveFocus();
    expect(screen.getByRole("heading", { level: 2, name: "Review source before practice" })).toBeInTheDocument();
    expect(screen.queryByText("Existing source content only.")).not.toBeInTheDocument();
    expect(screen.getByText("Source display text.")).toBeInTheDocument();
    expect(screen.getByLabelText("Current and next learning step")).toHaveTextContent("RecallCurrentReview sourceNextTargeted practiceUpdated after recall.");
    expect(screen.queryByRole("button", { name: "Begin practice" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue to practice" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Targeted practice" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Begin practice" })).toBeInTheDocument();
    expect(getStudySessionAdaptiveState).toHaveBeenCalledTimes(2);
  });

  it("lets a persisted practice action supersede an older provider-missing fallback", async () => {
    const user = userEvent.setup();
    const activeSession = { ...session, status: "practicing" as const, revision: 4 };
    const actionRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: remediation };
    const practiceRequired = { ...actionRequired, action: practiceAction };
    const getStudySessionAdaptiveState = vi.fn()
      .mockResolvedValueOnce(actionRequired)
      .mockResolvedValue(practiceRequired);
    renderPage({
      getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null })),
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState,
      completeStudySessionAdaptiveAction: vi.fn(async () => ({
        outcome: "applied" as const,
        course_id: "course-1",
        session: answered.session,
        plan,
        completed_action: { ...remediation, status: "completed" as const, revision: 1, started_at: time, completed_at: time },
        current_action: practiceAction,
      })),
      getCurrentLearningIntervention: vi.fn(async () => ({
        status: "source_review" as const,
        courseId: "course-1",
        sessionId: "session-1",
        reason: "provider_missing",
        actions: ["Explain differently", "Show a source example", "Test me instead"] as const,
        run: {
          id: "run-provider-missing",
          status: "failed" as const,
          provider: "unavailable",
          model: "unavailable",
          createdAt: time,
          updatedAt: time,
          errorCode: "provider_missing",
        },
        artifact: null,
        practice: null,
        fallback: { action: "source_review" as const, label: "Return to source", retryable: true },
      })),
      startLearningIntervention: vi.fn(),
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getStudySessionPractice: vi.fn(async () => practiceNotStarted),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { name: "Connect a provider to continue with the Agent" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review source instead" }));
    await user.click(await screen.findByRole("button", { name: "Continue to practice" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Targeted practice" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Begin practice" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Connect a provider to continue with the Agent" })).not.toBeInTheDocument();
    expect(getStudySessionAdaptiveState).toHaveBeenCalledTimes(2);
  });

  it("restores a persisted practice action without waiting on an obsolete intervention gate", async () => {
    const activeSession = { ...session, status: "practicing" as const, revision: 4 };
    const practiceRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: practiceAction };
    const getCurrentLearningIntervention = vi.fn();
    renderPage({
      getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null })),
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState: vi.fn(async () => practiceRequired),
      completeStudySessionAdaptiveAction: vi.fn(),
      getCurrentLearningIntervention,
      startLearningIntervention: vi.fn(),
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getStudySessionPractice: vi.fn(async () => practiceNotStarted),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { level: 2, name: "Targeted practice" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Begin practice" })).toBeInTheDocument();
    expect(screen.getByLabelText("Current and next learning step")).toHaveTextContent("CurrentTargeted practiceNextLearning summary");
    expect(screen.queryByText("Checking the current learning intervention…")).not.toBeInTheDocument();
    expect(getCurrentLearningIntervention).toHaveBeenCalledTimes(1);
  });

  it("restores a started practice run after its adaptive action has been consumed", async () => {
    const activeSession = { ...session, status: "practicing" as const, revision: 5 };
    const canonicalState = {
      course_id: "course-1",
      session: { ...answered.session, revision: 5 },
      plan,
      current_unit: unit,
      current_unit_id: "unit-1",
      state: "canonical" as const,
      action: null,
    };
    const restoredPractice = {
      ...practiceNotStarted,
      outcome: "pending" as const,
      session: { ...practiceNotStarted.session, revision: 5 },
      checkpoint: { id: "practice-checkpoint", kind: "practice" as const, prompt: "Fill in a different missing term using the source context:\n\nEigenvectors have [...] that describe their scale factor.", status: "pending" as const, created_at: time, answered_at: null },
      run: { id: "practice-run", status: "pending" as const, checkpoint_id: "practice-checkpoint", generator_version: "targeted-practice/1.0.0", created_at: time, answered_at: null, cancelled_at: null, cancellation_reason: null },
    };
    const getCurrentLearningIntervention = vi.fn();
    renderPage({
      getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null })),
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState: vi.fn(async () => canonicalState),
      completeStudySessionAdaptiveAction: vi.fn(),
      getCurrentLearningIntervention,
      startLearningIntervention: vi.fn(),
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getStudySessionPractice: vi.fn(async () => restoredPractice),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { level: 2, name: "Complete the missing term" })).toBeInTheDocument();
    expect(screen.getByLabelText("Missing term")).toBeInTheDocument();
    expect(screen.getByLabelText("Current and next learning step")).toHaveTextContent("CurrentTargeted practiceNextLearning summary");
    expect(screen.queryByRole("heading", { name: "Connect a provider to continue with the Agent" })).not.toBeInTheDocument();
    expect(getCurrentLearningIntervention).toHaveBeenCalledTimes(1);
  });

  it("restores a verified Agent explanation beside its exact pending practice", async () => {
    const activeSession = { ...session, status: "practicing" as const, revision: 5 };
    const canonicalState = {
      course_id: "course-1",
      session: { ...answered.session, revision: 5 },
      plan,
      current_unit: unit,
      current_unit_id: "unit-1",
      state: "canonical" as const,
      action: null,
    };
    const restoredPractice = {
      ...practiceNotStarted,
      outcome: "pending" as const,
      session: { ...practiceNotStarted.session, revision: 5 },
      checkpoint: { id: "practice-checkpoint", kind: "practice" as const, prompt: "Fill in a different missing term using the source context:\n\nEigenvectors have [...] that describe their scale factor.", status: "pending" as const, created_at: time, answered_at: null },
      run: { id: "practice-run", status: "pending" as const, checkpoint_id: "practice-checkpoint", generator_version: "targeted-practice/1.0.0", created_at: time, answered_at: null, cancelled_at: null, cancellation_reason: null },
    };
    renderPage({
      getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null })),
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState: vi.fn(async () => canonicalState),
      completeStudySessionAdaptiveAction: vi.fn(),
      getCurrentLearningIntervention: vi.fn(async () => ({
        status: "ready" as const,
        courseId: "course-1",
        sessionId: "session-1",
        reason: null,
        actions: ["Explain differently", "Show a source example", "Test me instead"] as const,
        run: null,
        artifact: {
          kind: "learning_intervention_artifact" as const,
          whyNow: "The Recall answer needs a source-grounded repair.",
          summary: "Keep direction; scale magnitude",
          explanationMarkdown: "The verified explanation remains visible.",
          sources: [{
            sourceHandle: "source-1",
            documentId: "document-1",
            documentName: "Eigenvectors.md",
            pageNumber: 1,
            sectionPath: ["Eigenvectors"],
            metadata: {},
            quote: "Eigenvectors preserve their direction.",
          }],
          whatNext: {
            label: "Continue with the exact pending Practice.",
            action: "continue_practice" as const,
            practiceRunId: "practice-run",
            practicePrompt: restoredPractice.checkpoint.prompt,
            sessionRevision: 5,
          },
        },
        practice: {
          label: "Continue with the exact pending Practice.",
          action: "continue_practice" as const,
          practiceRunId: "practice-run",
          practicePrompt: restoredPractice.checkpoint.prompt,
          sessionRevision: 5,
        },
        fallback: null,
      })),
      startLearningIntervention: vi.fn(),
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getStudySessionPractice: vi.fn(async () => restoredPractice),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { name: "Keep direction; scale magnitude" })).toBeInTheDocument();
    expect(screen.getByText("The verified explanation remains visible.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Complete the missing term" })).toBeInTheDocument();
    expect(screen.getByLabelText("Missing term")).toBeInTheDocument();
  });

  it("gates incorrect Recall behind the Learning Agent and hands Test me instead to the existing Practice flow", async () => {
    const user = userEvent.setup();
    const activeSession = { ...session, status: "practicing" as const, revision: 4 };
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null }));
    const actionRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: remediation };
    const practiceRequired = { ...actionRequired, action: practiceAction };
    const getStudySessionAdaptiveState = vi.fn()
      .mockResolvedValueOnce(actionRequired)
      .mockResolvedValue(practiceRequired);
    const getCurrentLearningIntervention = vi.fn(async () => ({
      status: "eligible" as const,
      courseId: "course-1",
      sessionId: "session-1",
      reason: null,
      actions: ["Explain differently", "Show a source example", "Test me instead"] as const,
      run: null,
      artifact: {
        whyNow: "This Recall answer needs a source-grounded repair before practice.",
        sources: [{ sourceHandle: "source-1", documentId: "document-1", documentName: "Limits.pdf", pageNumber: 4, sectionPath: ["Definition"], metadata: {} }],
        whatNext: { label: "Apply the repaired distinction in targeted practice.", action: "continue_practice" as const },
      },
      practice: null,
      fallback: { action: "source_review" as const, label: "Return to source" },
    }));
    const practiceReady = {
      status: "practice_ready" as const,
      courseId: "course-1",
      sessionId: "session-1",
      reason: null,
      actions: [],
      run: null,
      artifact: null,
      practice: { label: "Apply the repaired distinction in targeted practice.", action: "continue_practice" as const, practiceRunId: "practice-1", practicePrompt: "What does delta control?", sessionRevision: 5 },
      fallback: null,
    };
    const startLearningIntervention = vi.fn(async () => practiceReady);
    const getStudySessionPractice = vi.fn(async () => practiceNotStarted);
    const view = renderPage({
      getStudySession,
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState,
      completeStudySessionAdaptiveAction: vi.fn(),
      getCurrentLearningIntervention,
      startLearningIntervention,
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getStudySessionPractice,
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" })).toBeInTheDocument();
    expect(screen.getByText("Limits.pdf · p. 4")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Review source before practice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Begin practice" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try another approach…" }));
    await user.click(screen.getByRole("button", { name: "Test me instead" }));

    expect(await screen.findByRole("heading", { name: "Targeted practice" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Begin practice" })).toBeInTheDocument();
    const primaryButtons = view.container.querySelectorAll("button.primary");
    expect(primaryButtons).toHaveLength(1);
    expect(primaryButtons[0]).toHaveAccessibleName("Begin practice");
    expect(startLearningIntervention).toHaveBeenCalledWith("session-1", expect.objectContaining({
      courseId: "course-1",
      unitId: "unit-1",
      expectedSessionRevision: 4,
      intent: "test_me_instead",
    }), expect.anything());
    expect(getStudySessionPractice).toHaveBeenCalled();
    expect(getStudySessionAdaptiveState).toHaveBeenCalledTimes(2);
  });

  it("lets an eligible learner return to the persisted source review without first failing the Agent", async () => {
    const user = userEvent.setup();
    const activeSession = { ...session, status: "practicing" as const, revision: 4 };
    const actionRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: remediation };
    const startLearningIntervention = vi.fn();
    renderPage({
      getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null })),
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState: vi.fn(async () => actionRequired),
      completeStudySessionAdaptiveAction: vi.fn(),
      getCurrentLearningIntervention: vi.fn(async () => ({
        status: "eligible" as const,
        courseId: "course-1",
        sessionId: "session-1",
        reason: null,
        actions: ["Explain differently", "Show a source example", "Test me instead"] as const,
        run: null,
        artifact: {
          whyNow: "This Recall answer needs a source-grounded repair before practice.",
          sources: [{ sourceHandle: "source-1", documentId: "document-1", documentName: "Limits.pdf", pageNumber: 4, sectionPath: ["Definition"], metadata: {} }],
          whatNext: { label: "Apply the repaired distinction in targeted practice.", action: "continue_practice" as const },
        },
        practice: null,
        fallback: { action: "source_review" as const, label: "Return to source" },
      })),
      startLearningIntervention,
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getStudySessionPractice: vi.fn(async () => practiceNotStarted),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to source" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Review source before practice" })).toBeInTheDocument();
    expect(screen.getByText("Source display text.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Choose how Keen should repair this gap" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Begin practice" })).not.toBeInTheDocument();
    expect(startLearningIntervention).not.toHaveBeenCalled();
  });

  it("opens Settings Model with a validated return to the current Deep Learn session", async () => {
    const user = userEvent.setup();
    const activeSession = { ...session, status: "practicing" as const, revision: 4 };
    const actionRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: remediation };
    const view = renderPage({
      getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null })),
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState: vi.fn(async () => actionRequired),
      completeStudySessionAdaptiveAction: vi.fn(),
      getCurrentLearningIntervention: vi.fn(async () => ({
        status: "source_review" as const,
        courseId: "course-1",
        sessionId: "session-1",
        reason: "provider_missing",
        actions: ["Explain differently", "Show a source example", "Test me instead"] as const,
        run: {
          id: "run-provider-missing",
          status: "failed" as const,
          provider: "local-provider",
          model: "configured-model",
          createdAt: time,
          updatedAt: time,
          errorCode: "provider_missing",
        },
        artifact: null,
        practice: null,
        fallback: { action: "source_review" as const, label: "Return to source", retryable: true },
      })),
      startLearningIntervention: vi.fn(),
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getCurrentStudyPlanProposal: vi.fn(async () => ({
        status: "none" as const,
        courseId: "course-1",
        sessionId: "session-1",
        reason: null,
        run: null,
        artifact: null,
        receipt: null,
      })),
      startStudyPlanProposal: vi.fn(),
      getStudySessionPractice: vi.fn(async () => practiceNotStarted),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { name: "Connect a provider to continue with the Agent" })).toBeInTheDocument();
    const configure = screen.getByRole("button", { name: "Configure learning provider" });
    expect(configure).toHaveClass("primary");
    expect(screen.getByRole("button", { name: "Review source instead" })).not.toHaveClass("primary");
    expect(view.container.querySelectorAll(".intervention-actions button.primary")).toHaveLength(1);

    await user.click(configure);

    expect(await screen.findByRole("heading", { level: 1, name: "Model" })).toBeInTheDocument();
    expect(screen.getByText("Provider needed for this learning step")).toBeInTheDocument();
    expect(screen.getByText(/restore its current Recall result/i)).toBeInTheDocument();
    expect(screen.queryByText(/api[_ -]?key=.*session|secret=/i)).not.toBeInTheDocument();
  });

  it("keeps Begin practice as the only primary action beside a ready Agent explanation", async () => {
    const activeSession = { ...session, status: "practicing" as const, revision: 5 };
    const actionRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: remediation };
    const practice = { label: "Apply the repaired distinction in targeted practice.", action: "continue_practice" as const, practiceRunId: "practice-1", practicePrompt: "What does delta control?", sessionRevision: 5 };
    const view = renderPage({
      getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: activeSession, plan, current_unit_id: "unit-1", recovery_action: null })),
      getStudySessionActiveRecall: vi.fn(async () => answeredIncorrect),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState: vi.fn(async () => actionRequired),
      completeStudySessionAdaptiveAction: vi.fn(),
      getCurrentLearningIntervention: vi.fn(async () => ({
        status: "ready" as const,
        courseId: "course-1",
        sessionId: "session-1",
        reason: null,
        actions: ["Explain differently", "Show a source example", "Test me instead"] as const,
        run: null,
        artifact: {
          kind: "learning_intervention_artifact" as const,
          whyNow: "The last Recall answer conflated two distances.",
          summary: "Separate input and output distance",
          explanationMarkdown: "Delta controls input distance; epsilon bounds output distance.",
          sources: [{
            sourceHandle: "source-1",
            documentId: "document-1",
            documentName: "Limits.pdf",
            pageNumber: 4,
            sectionPath: ["Definition"],
            metadata: {},
            quote: "Delta bounds input distance.",
          }],
          whatNext: practice,
        },
        practice,
        fallback: null,
      })),
      startLearningIntervention: vi.fn(),
      cancelLearningIntervention: vi.fn(),
      learningInterventionEvents: vi.fn(),
      getCurrentStudyPlanProposal: vi.fn(async () => ({
        status: "none" as const,
        courseId: "course-1",
        sessionId: "session-1",
        reason: null,
        run: null,
        artifact: null,
        receipt: null,
      })),
      startStudyPlanProposal: vi.fn(),
      getStudySessionPractice: vi.fn(async () => practiceNotStarted),
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { name: "Separate input and output distance" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Begin practice" })).toHaveClass("primary");
    expect(screen.getByRole("button", { name: "Try another approach…" })).toBeInTheDocument();
    expect(screen.getByText("Need a bridge before Examples?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suggest prerequisite" })).not.toHaveClass("primary");
    const primaryButtons = view.container.querySelectorAll("button.primary");
    expect(primaryButtons).toHaveLength(1);
    expect(primaryButtons[0]).toHaveAccessibleName("Begin practice");
  });

  it.each([
    ["service failure", new LearningCoreResponseError(503, null, null), /local learning service could not restore/i],
    ["schema failure", new LearningCoreSchemaError("/v1/study-sessions/session-1/adaptive-state"), /returned a next step Keen could not verify/i],
  ])("keeps practice gated behind inline recovery after %s", async (_label, failure, message) => {
    const user = userEvent.setup();
    const practiceRequired = { course_id: "course-1", session: answered.session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: practiceAction };
    const getStudySessionAdaptiveState = vi.fn()
      .mockRejectedValueOnce(failure)
      .mockRejectedValueOnce(failure)
      .mockResolvedValue(practiceRequired);
    const getStudySessionPractice = vi.fn(async () => practiceNotStarted);
    renderPage({
      getStudySession: study,
      getStudySessionActiveRecall: vi.fn(async () => answered),
      beginStudySessionActiveRecall: vi.fn(),
      answerStudySessionActiveRecall: vi.fn(),
      getStudySessionAdaptiveState,
      completeStudySessionAdaptiveAction: vi.fn(),
      getStudySessionPractice,
      beginStudySessionPractice: vi.fn(),
      answerStudySessionPractice: vi.fn(),
    });

    expect(await screen.findByRole("heading", { level: 2, name: "Next learning step unavailable" }, { timeout: 4_000 })).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Begin practice" })).not.toBeInTheDocument();
    expect(getStudySessionPractice).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Retry next step" }));
    expect(await screen.findByRole("button", { name: "Begin practice" })).toBeInTheDocument();
    expect(getStudySessionAdaptiveState).toHaveBeenCalledTimes(3);
    expect(study).toHaveBeenCalled();
  });
  it("restores a pending prompt without exposing source-derived lesson details", async () => {
    core.setInspector.mockClear();
    renderPage({ getStudySession: study, getStudySessionActiveRecall: vi.fn(async () => pending), beginStudySessionActiveRecall: vi.fn(), answerStudySessionActiveRecall: vi.fn() });
    expect(await screen.findByText("What does a limit describe?")).toBeInTheDocument();
    expect(screen.queryByText("Source display text.")).not.toBeInTheDocument();
    expect(screen.queryByText("Definition")).not.toBeInTheDocument();
    expect(screen.queryByText("concept-1")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Limits study" })).toBeInTheDocument();
    expect(screen.getByText("Learn limits.")).toBeInTheDocument();
    expect(screen.getByLabelText("Closed-book recall step")).toHaveClass("is-closed-book-recall");
    expect(document.querySelector(".deep-learn-page")).toHaveClass("is-closed-book-recall");
    expect(screen.getByText("Closed-book recall")).toBeInTheDocument();
    expect(screen.getByLabelText("Your response")).toHaveFocus();
    expect(screen.queryByText(/details stay hidden|without lesson details/i)).not.toBeInTheDocument();
    expect(core.setInspector).toHaveBeenCalledWith(null);
  });

  it("begins then records one response through the typed client", async () => {
    const user = userEvent.setup();
    const get = vi.fn(async () => notStarted);
    const begin = vi.fn(async () => ({ ...pending, outcome: "applied" as const }));
    const answer = vi.fn(async () => ({ ...answered, outcome: "applied" as const }));
    renderPage({ getStudySession: study, getStudySessionActiveRecall: get, beginStudySessionActiveRecall: begin, answerStudySessionActiveRecall: answer });
    await user.click(await screen.findByRole("button", { name: "Begin active recall" }));
    expect(await screen.findByText("What does a limit describe?")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your response"), "Approaching a value");
    await user.click(screen.getByRole("button", { name: "Submit response" }));
    expect(await screen.findByText("Mastery evidence")).toBeInTheDocument();
    expect(screen.queryByLabelText("Closed-book recall step")).not.toBeInTheDocument();
    expect(document.querySelector(".deep-learn-page")).not.toHaveClass("is-closed-book-recall");
    expect(screen.getByRole("heading", { level: 2, name: "Recalled correctly" })).toHaveFocus();
    expect(begin).toHaveBeenCalledWith("session-1", expect.objectContaining({ course_id: "course-1", expected_revision: 2, idempotency_key: expect.any(String) }), expect.anything());
    expect(answer).toHaveBeenCalledWith("session-1", "run-1", expect.objectContaining({ response: "Approaching a value", expected_revision: 3 }), expect.anything());
  });

  it("aborts a pending write on unmount", async () => {
    const user = userEvent.setup();
    let signal: AbortSignal | undefined;
    const begin = vi.fn((_: string, __: unknown, options: { signal?: AbortSignal }) => new Promise(() => { signal = options.signal; }));
    const view = renderPage({ getStudySession: study, getStudySessionActiveRecall: vi.fn(async () => notStarted), beginStudySessionActiveRecall: begin, answerStudySessionActiveRecall: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin active recall" }));
    await waitFor(() => expect(begin).toHaveBeenCalledOnce());
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("restores after a conflict before allowing a fresh active-recall action", async () => {
    const user = userEvent.setup();
    const revised = { ...notStarted, session: { ...notStarted.session, revision: 5 } };
    const get = vi.fn().mockResolvedValueOnce(notStarted).mockResolvedValueOnce(revised);
    const begin = vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null));
    renderPage({ getStudySession: study, getStudySessionActiveRecall: get, beginStudySessionActiveRecall: begin, answerStudySessionActiveRecall: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin active recall" }));
    expect(await screen.findByText(/This session changed before the action completed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Begin active recall" })).toBeInTheDocument();
    expect(begin).toHaveBeenCalledOnce();
  });

  it("locks the old action behind explicit restore when a conflict reconciliation fails", async () => {
    const user = userEvent.setup();
    const get = vi.fn().mockResolvedValueOnce(notStarted).mockRejectedValueOnce(new TypeError("offline"));
    const begin = vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null));
    renderPage({ getStudySession: study, getStudySessionActiveRecall: get, beginStudySessionActiveRecall: begin, answerStudySessionActiveRecall: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin active recall" }));
    expect(await screen.findByRole("button", { name: "Retry active-recall restore" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Begin active recall" })).not.toBeInTheDocument();
  });

  it("retries an unknown answer with its frozen idempotency key, revision, response, and run", async () => {
    const user = userEvent.setup();
    const get = vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(pending);
    const answer = vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce({ ...answered, outcome: "applied" as const });
    renderPage({ getStudySession: study, getStudySessionActiveRecall: get, beginStudySessionActiveRecall: vi.fn(), answerStudySessionActiveRecall: answer });
    await user.type(await screen.findByLabelText("Your response"), "Approaching a value");
    await user.click(screen.getByRole("button", { name: "Submit response" }));
    expect(await screen.findByRole("button", { name: "Retry same response" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry same response" }));
    expect(await screen.findByText("Mastery evidence")).toBeInTheDocument();
    const calls = answer.mock.calls as unknown[][];
    expect(calls).toHaveLength(2);
    expect(calls[1]?.[0]).toBe(calls[0]?.[0]);
    expect(calls[1]?.[1]).toBe(calls[0]?.[1]);
    expect(calls[1]?.[2]).toEqual(calls[0]?.[2]);
  });

  it("restores paused active recall only after an answered opening diagnostic and sends no write", async () => {
    const pausedSession = { ...session, status: "paused" as const };
    const diagnostic = { outcome: "answered" as const, course_id: "course-1", session: pausedSession, plan, checkpoint: { id: "diagnostic-1", session_id: "session-1", unit_id: "unit-1", kind: "diagnostic" as const, prompt: "What do you know?", status: "answered" as const }, current_unit: unit, current_unit_id: "unit-1" };
    const getRecall = vi.fn(async () => ({ ...notStarted, session: { ...notStarted.session, status: "paused" as const } }));
    const begin = vi.fn();
    const answer = vi.fn();
    renderPage({ getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: pausedSession, plan, current_unit_id: "unit-1", recovery_action: null })), getStudySessionDiagnostic: vi.fn(async () => diagnostic), getStudySessionActiveRecall: getRecall, beginStudySessionActiveRecall: begin, answerStudySessionActiveRecall: answer });
    expect(await screen.findByText("Active recall restored")).toBeInTheDocument();
    expect(getRecall).toHaveBeenCalledOnce();
    expect(begin).not.toHaveBeenCalled();
    expect(answer).not.toHaveBeenCalled();
  });
});
