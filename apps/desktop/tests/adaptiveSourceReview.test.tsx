import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LearningCoreResponseError } from "@keen/api-client";
import { AdaptiveSourceReview } from "../src/features/deep-learn/AdaptiveSourceReview";

const time = "2026-07-22T10:00:00+00:00";
const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Limits", mode: "study" as const, goal: "Understand limits.", estimated_minutes: 20, status: "practicing" as const, progress: 0.5, revision: 4, created_at: time, updated_at: time, started_at: time };
const unit = { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1", "chunk-2"], title: "Definition", objective: "Read the definition again.", content: "Existing source content only.", estimated_minutes: 10, status: "active" as const };
const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Use the source.", units: [unit, { ...unit, id: "unit-2", ordinal: 1, source_chunk_ids: ["chunk-3"], status: "ready" as const }] };
const action = { id: "action-1", course_id: "course-1", session_id: "session-1", unit_id: "unit-1", kind: "remediate" as const, status: "pending" as const, reason_code: "active_recall_incorrect" as const, policy_version: "adaptive-session-policy/1.0.0" as const, revision: 0, created_at: time, started_at: null, completed_at: null, cancelled_at: null };
const state = { course_id: "course-1", session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action };

function renderReview(client: Record<string, unknown>, paused = false) {
  const onCompleted = vi.fn(async () => undefined);
  const onReconciled = vi.fn();
  render(<AdaptiveSourceReview client={client as never} sessionId="session-1" courseId="course-1" action={action} unit={unit} paused={paused} onCompleted={onCompleted} onReconciled={onReconciled} />);
  return { onCompleted, onReconciled };
}

describe("AdaptiveSourceReview", () => {
  it("completes after the StrictMode effect replay without remaining pending", async () => {
    const completeStudySessionAdaptiveAction = vi.fn(async () => ({
      outcome: "applied" as const,
      course_id: "course-1",
      session,
      plan,
      completed_action: { ...action, status: "completed" as const, revision: 1, started_at: time, completed_at: time },
      current_action: { ...action, id: "action-2", kind: "practice" as const, reason_code: "remediation_completed" as const },
    }));
    const onCompleted = vi.fn(async () => undefined);

    render(
      <StrictMode>
        <AdaptiveSourceReview
          client={{ completeStudySessionAdaptiveAction, getStudySessionAdaptiveState: vi.fn() } as never}
          sessionId="session-1"
          courseId="course-1"
          action={action}
          unit={unit}
          paused={false}
          onCompleted={onCompleted}
          onReconciled={vi.fn()}
        />
      </StrictMode>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Continue to practice" }));
    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce());
    expect(screen.getByRole("button", { name: "Continue to practice" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Continuing…" })).not.toBeInTheDocument();
  });

  it("renders only persisted unit source context and one continuation", async () => {
    const completed = { ...action, status: "completed" as const, revision: 1, started_at: time, completed_at: time };
    const practice = { ...action, id: "action-2", kind: "practice" as const, reason_code: "remediation_completed" as const };
    const completeStudySessionAdaptiveAction = vi.fn(async () => ({ outcome: "applied" as const, course_id: "course-1", session, plan, completed_action: completed, current_action: practice }));
    const { onCompleted } = renderReview({ completeStudySessionAdaptiveAction, getStudySessionAdaptiveState: vi.fn() });
    expect(screen.getByRole("heading", { level: 2, name: "Review source before practice" })).toBeInTheDocument();
    expect(screen.getByLabelText("Why Keen chose this step")).toHaveTextContent("recall missed the required idea");
    expect(screen.getByLabelText("Why Keen chose this step")).toHaveTextContent("active recall incorrect");
    expect(screen.getByText("Definition")).toBeInTheDocument();
    expect(screen.getByText("Read the definition again.")).toBeInTheDocument();
    expect(screen.getByText("Existing source content only.")).toBeInTheDocument();
    expect(screen.getByText("Chunk chunk-1 · Chunk chunk-2")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Continue to practice" }));
    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce());
    expect(completeStudySessionAdaptiveAction).toHaveBeenCalledWith("session-1", "action-1", expect.objectContaining({ course_id: "course-1", expected_action_revision: 0, idempotency_key: expect.stringMatching(/^adaptive-action-/) }), expect.anything());
  });

  it("keeps the exact action disabled while paused without announcing a restored live update", () => {
    renderReview({ completeStudySessionAdaptiveAction: vi.fn(), getStudySessionAdaptiveState: vi.fn() }, true);
    expect(screen.getByRole("button", { name: "Continue to practice" })).toBeDisabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reconciles an unknown outcome and reuses the same request identity", async () => {
    const completeStudySessionAdaptiveAction = vi.fn()
      .mockRejectedValueOnce(new TypeError("connection dropped"))
      .mockResolvedValueOnce({ outcome: "replayed", course_id: "course-1", session, plan, completed_action: { ...action, status: "completed", started_at: time, completed_at: time }, current_action: { ...action, id: "action-2", kind: "practice", reason_code: "remediation_completed" } });
    const getStudySessionAdaptiveState = vi.fn(async () => state);
    const { onCompleted, onReconciled } = renderReview({ completeStudySessionAdaptiveAction, getStudySessionAdaptiveState });
    await userEvent.click(screen.getByRole("button", { name: "Continue to practice" }));
    expect(await screen.findByRole("button", { name: "Retry same continuation" })).toBeInTheDocument();
    expect(onReconciled).toHaveBeenCalledWith(state);
    await userEvent.click(screen.getByRole("button", { name: "Retry same continuation" }));
    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce());
    const calls = completeStudySessionAdaptiveAction.mock.calls as unknown[][];
    expect(calls[1]?.[2]).toEqual(calls[0]?.[2]);
  });

  it("permits a fresh identity after a confirmed 409 reconciliation, pause, and resume", async () => {
    const user = userEvent.setup();
    const pausedSession = { ...session, status: "paused" as const, resume_from_status: "practicing" as const, revision: 5 };
    const pausedState = { ...state, state: "paused" as const, session: pausedSession };
    const completeStudySessionAdaptiveAction = vi.fn()
      .mockRejectedValueOnce(new LearningCoreResponseError(409, null, null))
      .mockResolvedValueOnce({ outcome: "applied", course_id: "course-1", session, plan, completed_action: { ...action, status: "completed", revision: 1, started_at: time, completed_at: time }, current_action: { ...action, id: "action-2", kind: "practice", reason_code: "remediation_completed" } });
    const client = { completeStudySessionAdaptiveAction, getStudySessionAdaptiveState: vi.fn(async () => pausedState) };
    const onCompleted = vi.fn(async () => undefined);
    const onReconciled = vi.fn();
    const view = render(<AdaptiveSourceReview client={client as never} sessionId="session-1" courseId="course-1" action={action} unit={unit} paused={false} onCompleted={onCompleted} onReconciled={onReconciled} />);

    await user.click(screen.getByRole("button", { name: "Continue to practice" }));
    expect(await screen.findByText(/restored the latest saved step/i)).toBeInTheDocument();
    view.rerender(<AdaptiveSourceReview client={client as never} sessionId="session-1" courseId="course-1" action={action} unit={unit} paused onCompleted={onCompleted} onReconciled={onReconciled} />);
    expect(screen.getByRole("button", { name: "Continue to practice" })).toBeDisabled();
    view.rerender(<AdaptiveSourceReview client={client as never} sessionId="session-1" courseId="course-1" action={action} unit={unit} paused={false} onCompleted={onCompleted} onReconciled={onReconciled} />);
    expect(screen.getByRole("button", { name: "Continue to practice" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Continue to practice" }));
    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce());
    const calls = completeStudySessionAdaptiveAction.mock.calls as unknown[][];
    expect((calls[1]?.[2] as { idempotency_key: string }).idempotency_key).not.toBe((calls[0]?.[2] as { idempotency_key: string }).idempotency_key);
  });
});
