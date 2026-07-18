import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LearningCoreResponseError } from "@keen/api-client";
import { DeepLearnPage } from "../src/features/deep-learn/DeepLearnPage";
import { TargetedPractice } from "../src/features/deep-learn/TargetedPractice";

const core = vi.hoisted(() => ({ current: null as never, setInspector: vi.fn() }));
vi.mock("../src/services/LearningCoreProvider", () => ({ useLearningCore: () => core.current, isLearningCoreStarting: () => false }));
vi.mock("../src/state/appStore", () => ({ useAppStore: () => ({ setInspector: core.setInspector }) }));

const time = "2026-07-18T10:00:00+00:00";
const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "SECRET SESSION", mode: "study" as const, goal: "SECRET GOAL", estimated_minutes: 20, status: "practicing" as const, progress: 0.4, revision: 4, created_at: time, updated_at: time, started_at: time };
const unit = { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["SECRET CONCEPT"], source_chunk_ids: ["chunk-secret"], title: "SECRET UNIT", objective: "SECRET OBJECTIVE", content: "SECRET SOURCE TEXT", estimated_minutes: 10, status: "active" as const };
const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "SECRET RATIONALE", units: [unit] };
const protectedUnit = { id: "unit-1", ordinal: 0, estimated_minutes: 10, status: "active" as const, created_at: time, updated_at: time };
const protectedSession = { id: "session-1", course_id: "course-1", status: "practicing" as const, revision: 4, progress: 0.4, estimated_minutes: 20, current_unit_id: "unit-1", created_at: time, updated_at: time, started_at: time, finished_at: null };
const protectedPlan = { id: "plan-1", session_id: "session-1", version: 1, units: [protectedUnit] };
const recallAnswered = { outcome: "answered" as const, course_id: "course-1", session: protectedSession, plan: protectedPlan, current_unit: protectedUnit, checkpoint: { id: "recall-checkpoint", kind: "active_recall" as const, prompt: "Recall prompt", status: "answered" as const, created_at: time, answered_at: time }, run: { id: "recall-run", status: "answered" as const, checkpoint_id: "recall-checkpoint", generator_version: "source-cloze-v1", created_at: time, answered_at: time, cancelled_at: null, cancellation_reason: null }, grade: { correct: true, score: 1, max_score: 1, grader_version: "exact-v1" } };
const practiceNotStarted = { outcome: "not_started" as const, course_id: "course-1", session: protectedSession, plan: protectedPlan, current_unit: protectedUnit, checkpoint: null, run: null, grade: null };
const practicePending = { outcome: "pending" as const, course_id: "course-1", session: protectedSession, plan: protectedPlan, current_unit: protectedUnit, checkpoint: { id: "practice-checkpoint", kind: "practice" as const, prompt: "Which term completes the source statement?", status: "pending" as const, created_at: time, answered_at: null }, run: { id: "practice-run", status: "pending" as const, checkpoint_id: "practice-checkpoint", generator_version: "targeted-practice/1.0.0", created_at: time, answered_at: null, cancelled_at: null, cancellation_reason: null }, grade: null };
const practiceAnswered = { ...practicePending, outcome: "answered" as const, session: { ...protectedSession, status: "summarizing" as const, revision: 5 }, checkpoint: { ...practicePending.checkpoint, status: "answered" as const, answered_at: time }, run: { ...practicePending.run, status: "answered" as const, answered_at: time }, grade: { correct: true, score: 1, max_score: 1, grader_version: "exact-v1" } };

function renderPage(client: Record<string, unknown>) {
  core.current = { status: "healthy", client, connectionGeneration: 1, retry: vi.fn() } as never;
  return render(<MemoryRouter initialEntries={["/deep-learn/session-1?course_id=course-1"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Routes><Route path="/deep-learn/:id" element={<DeepLearnPage />} /></Routes></QueryClientProvider></MemoryRouter>);
}
const study = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session, plan, current_unit_id: "unit-1", recovery_action: null }));
const clientBase = (practice: unknown) => ({ getStudySession: study, getStudySessionActiveRecall: vi.fn(async () => recallAnswered), beginStudySessionActiveRecall: vi.fn(), answerStudySessionActiveRecall: vi.fn(), getStudySessionPractice: vi.fn(async () => practice), beginStudySessionPractice: vi.fn(), answerStudySessionPractice: vi.fn() });

describe("Deep Learn targeted practice", () => {
  it("restores a practice prompt before painting lesson or inspector source details", async () => {
    core.setInspector.mockClear();
    renderPage(clientBase(practicePending));
    expect(await screen.findByText("Which term completes the source statement?")).toBeInTheDocument();
    expect(screen.queryByText("SECRET SOURCE TEXT")).not.toBeInTheDocument();
    expect(screen.queryByText("SECRET UNIT")).not.toBeInTheDocument();
    expect(screen.queryByText("SECRET CONCEPT")).not.toBeInTheDocument();
    expect(screen.queryByText("SECRET SESSION")).not.toBeInTheDocument();
    expect(core.setInspector).toHaveBeenCalledWith({ eyebrow: "Targeted practice", title: "Source details hidden", body: "Source details stay hidden while you answer this practice prompt." });
  });

  it("begins and records a practice response with no Review or FSRS claim", async () => {
    const user = userEvent.setup();
    const client = clientBase(practiceNotStarted);
    client.beginStudySessionPractice = vi.fn(async () => ({ ...practicePending, outcome: "applied" as const }));
    client.answerStudySessionPractice = vi.fn(async () => ({ ...practiceAnswered, outcome: "applied" as const }));
    renderPage(client);
    await user.click(await screen.findByRole("button", { name: "Begin practice" }));
    await user.type(await screen.findByLabelText("Your response"), "target term");
    await user.click(screen.getByRole("button", { name: "Submit response" }));
    expect(await screen.findByText(/One practice mastery observation was recorded; no Review or FSRS schedule changed/)).toBeInTheDocument();
    expect(client.beginStudySessionPractice).toHaveBeenCalledWith("session-1", expect.objectContaining({ expected_revision: 4, course_id: "course-1", idempotency_key: expect.any(String) }), expect.anything());
    expect(client.answerStudySessionPractice).toHaveBeenCalledWith("session-1", "practice-run", expect.objectContaining({ expected_revision: 4, response: "target term" }), expect.anything());
  });

  it("restores a conflict rather than retrying a stale practice write", async () => {
    const user = userEvent.setup();
    const client = clientBase(practiceNotStarted);
    client.getStudySessionPractice = vi.fn().mockResolvedValueOnce(practiceNotStarted).mockResolvedValueOnce({ ...practiceNotStarted, session: { ...protectedSession, revision: 9 } });
    client.beginStudySessionPractice = vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null));
    renderPage(client);
    await user.click(await screen.findByRole("button", { name: "Begin practice" }));
    expect(await screen.findByText(/This session changed before the action completed/)).toBeInTheDocument();
    expect(client.beginStudySessionPractice).toHaveBeenCalledOnce();
  });

  it("retries an unknown answer with its original durable intent", async () => {
    const user = userEvent.setup();
    const client = clientBase(practicePending);
    client.getStudySessionPractice = vi.fn().mockResolvedValueOnce(practicePending).mockResolvedValueOnce(practicePending);
    client.answerStudySessionPractice = vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce({ ...practiceAnswered, outcome: "applied" as const });
    renderPage(client);
    await user.type(await screen.findByLabelText("Your response"), "target term");
    await user.click(screen.getByRole("button", { name: "Submit response" }));
    await user.click(await screen.findByRole("button", { name: "Retry same response" }));
    await screen.findByText(/One practice mastery observation/);
    const calls = (client.answerStudySessionPractice as ReturnType<typeof vi.fn>).mock.calls as unknown[][];
    expect(calls[1]?.[1]).toBe(calls[0]?.[1]);
    expect(calls[1]?.[2]).toEqual(calls[0]?.[2]);
  });

  it("aborts an in-flight practice write on unmount", async () => {
    const user = userEvent.setup();
    let signal: AbortSignal | undefined;
    const client = clientBase(practiceNotStarted);
    client.beginStudySessionPractice = vi.fn((_: string, __: unknown, options: { signal?: AbortSignal }) => new Promise(() => { signal = options.signal; }));
    const view = renderPage(client);
    await user.click(await screen.findByRole("button", { name: "Begin practice" }));
    await waitFor(() => expect(client.beginStudySessionPractice).toHaveBeenCalledOnce());
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("does not invent a practice run before begin in paused or terminal states", async () => {
    const pausedState = { ...practiceNotStarted, session: { ...protectedSession, status: "paused" as const } };
    const pausedClient = clientBase(pausedState);
    const pausedView = render(<TargetedPractice client={pausedClient as never} sessionId="session-1" courseId="course-1" stateScope="scope-paused" session={{ ...session, status: "paused" as const }} paused onSessionChanged={vi.fn()} onOutcomeChange={vi.fn()} />);
    expect(await screen.findByText("Practice has not started")).toBeInTheDocument();
    expect(screen.queryByText("Practice restored")).not.toBeInTheDocument();
    pausedView.unmount();

    const cancelledState = { ...practiceNotStarted, outcome: "cancelled" as const, session: { ...protectedSession, status: "cancelled" as const } };
    render(<TargetedPractice client={clientBase(cancelledState) as never} sessionId="session-1" courseId="course-1" stateScope="scope-cancelled" session={{ ...session, status: "cancelled" as const }} paused={false} onSessionChanged={vi.fn()} onOutcomeChange={vi.fn()} />);
    expect(await screen.findByText("Session ended before practice")).toBeInTheDocument();
    expect(screen.queryByText("This practice run ended with the local session.")).not.toBeInTheDocument();
  });
});
