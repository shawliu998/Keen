import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DeepLearnPage } from "../src/features/deep-learn/DeepLearnPage";
import { LearningCoreResponseError } from "@keen/api-client";

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

function renderPage(client: Record<string, unknown>) {
  core.current = { status: "healthy", client, connectionGeneration: 1, retry: vi.fn() } as never;
  return render(<MemoryRouter initialEntries={["/deep-learn/session-1?course_id=course-1"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Routes><Route path="/deep-learn/:id" element={<DeepLearnPage />} /></Routes></QueryClientProvider></MemoryRouter>);
}
const study = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session, plan, current_unit_id: "unit-1", recovery_action: null }));

describe("Deep Learn active recall", () => {
  it("restores a pending prompt without exposing source-derived lesson details", async () => {
    core.setInspector.mockClear();
    renderPage({ getStudySession: study, getStudySessionActiveRecall: vi.fn(async () => pending), beginStudySessionActiveRecall: vi.fn(), answerStudySessionActiveRecall: vi.fn() });
    expect(await screen.findByText("What does a limit describe?")).toBeInTheDocument();
    expect(screen.queryByText("Source display text.")).not.toBeInTheDocument();
    expect(screen.queryByText("Definition")).not.toBeInTheDocument();
    expect(screen.queryByText("concept-1")).not.toBeInTheDocument();
    expect(screen.queryByText("Limits study")).not.toBeInTheDocument();
    expect(screen.queryByText("Learn limits.")).not.toBeInTheDocument();
    expect(core.setInspector).toHaveBeenCalledWith({ eyebrow: "Active recall", title: "Source details hidden", body: "Source details stay hidden while you answer this prompt." });
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
    expect(await screen.findByText(/One local mastery observation was recorded/)).toBeInTheDocument();
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
    expect(await screen.findByText(/One local mastery observation was recorded/)).toBeInTheDocument();
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
