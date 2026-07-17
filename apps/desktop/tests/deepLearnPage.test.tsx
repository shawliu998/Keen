import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LearningCoreResponseError } from "@keen/api-client";
import { DeepLearnPage } from "../src/features/deep-learn/DeepLearnPage";

const coreState = vi.hoisted(() => ({ current: null as never }));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => coreState.current,
  isLearningCoreStarting: () => false,
}));
vi.mock("../src/state/appStore", () => ({ useAppStore: () => ({ setInspector: vi.fn() }) }));

const session = {
  id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Limits study", mode: "study" as const,
  goal: "Understand the source-grounded limit definition.", estimated_minutes: 20, status: "studying" as const,
  progress: 0.25, revision: 1, created_at: "2026-07-17T10:00:00+00:00", updated_at: "2026-07-17T10:00:00+00:00", started_at: "2026-07-17T10:00:00+00:00",
};
const plan = {
  id: "plan-1", session_id: "session-1", version: 1, rationale: "Use the indexed course source.", units: [
    { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"], title: "Definition", objective: "Read the definition.", content: "Source display text.", estimated_minutes: 10, status: "active" as const },
    { id: "unit-2", ordinal: 1, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-2"], title: "Examples", objective: "Apply the definition.", content: "More display text.", estimated_minutes: 10, status: "ready" as const },
  ],
};

const openingSession = { ...session, status: "goal_confirmation" as const, revision: 4, progress: 0, started_at: null };
const diagnosingSession = { ...openingSession, status: "diagnosing" as const, revision: 5 };
const studyingSession = { ...session, status: "studying" as const, revision: 6 };
const pendingCheckpoint = { id: "diagnostic-1", session_id: "session-1", unit_id: "unit-1", kind: "diagnostic" as const, prompt: "What do you already know about limits?", status: "pending" as const };
const answeredCheckpoint = { ...pendingCheckpoint, status: "answered" as const };
const notStartedDiagnostic = { outcome: "not_started" as const, course_id: "course-1", session: openingSession, plan, checkpoint: null, current_unit: null, current_unit_id: null };
const pendingDiagnostic = { outcome: "pending" as const, course_id: "course-1", session: diagnosingSession, plan, checkpoint: pendingCheckpoint, current_unit: null, current_unit_id: null };
const answeredDiagnostic = { outcome: "answered" as const, course_id: "course-1", session: studyingSession, plan, checkpoint: answeredCheckpoint, current_unit: plan.units[0], current_unit_id: "unit-1" };

function renderPage(getStudySession: ReturnType<typeof vi.fn>, path = "/deep-learn/session-1?course_id=course-1") {
  coreState.current = { status: "healthy", client: { getStudySession }, connectionGeneration: 1, retry: vi.fn() } as never;
  return renderCurrentCore(path);
}

function renderCurrentCore(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter initialEntries={[path]}><QueryClientProvider client={queryClient}><Routes><Route path="/deep-learn/:id" element={<DeepLearnPage />} /></Routes></QueryClientProvider></MemoryRouter>);
}

function renderOpeningDiagnostic(client: Record<string, unknown>) {
  coreState.current = { status: "healthy", client, connectionGeneration: 1, retry: vi.fn() } as never;
  return renderCurrentCore("/deep-learn/session-1?course_id=course-1");
}

describe("DeepLearnPage persisted session reader", () => {
  it("renders only the validated persisted plan and course-scoped citations", async () => {
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session, plan, current_unit_id: "unit-1", recovery_action: null }));
    renderPage(getStudySession);
    expect(await screen.findByText("Limits study")).toBeInTheDocument();
    expect(screen.getByText("Source display text.")).toBeInTheDocument();
    expect(screen.getAllByText("Definition")).toHaveLength(2);
    expect(screen.queryByText("Deep Learn demo")).not.toBeInTheDocument();
    expect(getStudySession).toHaveBeenCalledWith("session-1", "course-1", expect.anything());
  });

  it("shows typed plan recovery and does not substitute demo content", async () => {
    const getStudySession = vi.fn(async () => ({ outcome: "plan_unavailable" as const, course_id: "course-1", session, plan: null, current_unit_id: null, recovery_action: "Return to the learning feed." }));
    renderPage(getStudySession);
    expect(await screen.findByText("Study plan unavailable")).toBeInTheDocument();
    expect(screen.getByText("Return to the learning feed.")).toBeInTheDocument();
    expect(screen.queryByText("Eigenvectors & eigenspaces")).not.toBeInTheDocument();
  });

  it("requires course scope before requesting a persisted session", async () => {
    const getStudySession = vi.fn();
    renderPage(getStudySession, "/deep-learn/session-1");
    expect(screen.getByText("Study session needs a course")).toBeInTheDocument();
    await waitFor(() => expect(getStudySession).not.toHaveBeenCalled());
  });

  it("keeps Browser Demo request-free and reports offline without sample substitution", () => {
    const getStudySession = vi.fn();
    coreState.current = { status: "demo", client: { getStudySession }, connectionGeneration: 0, retry: vi.fn() } as never;
    const demo = renderCurrentCore("/deep-learn/session-1?course_id=course-1");
    expect(screen.getByText("Deep Learn demo")).toBeInTheDocument();
    expect(getStudySession).not.toHaveBeenCalled();
    demo.unmount();
    coreState.current = { status: "unavailable", client: null, connectionGeneration: 1, retry: vi.fn() } as never;
    renderCurrentCore("/deep-learn/session-1?course_id=course-1");
    expect(screen.getByText("Local study session is unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Eigenvectors & eigenspaces")).not.toBeInTheDocument();
  });

  it("shows a recoverable loading state and an actionable not-found result", async () => {
    const pending = new Promise(() => undefined);
    const loading = renderPage(vi.fn(() => pending));
    expect(screen.getByText("Loading local study session")).toBeInTheDocument();
    loading.unmount();
    const missing = vi.fn(async () => { throw new LearningCoreResponseError(404, null, null); });
    renderPage(missing);
    expect(await screen.findByText("Study session was not found", {}, { timeout: 3_000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to Learning Feed" })).toBeInTheDocument();
    expect(screen.queryByText("Deep Learn demo")).not.toBeInTheDocument();
  });

  it("ignores a late response after the authenticated connection generation changes", async () => {
    let resolve!: (value: unknown) => void;
    const first = vi.fn(() => new Promise((done) => { resolve = done; }));
    const view = renderPage(first);
    expect(screen.getByText("Loading local study session")).toBeInTheDocument();
    const second = vi.fn(async () => ({ outcome: "plan_unavailable" as const, course_id: "course-1", session: { ...session, id: "session-1" }, plan: null, current_unit_id: null, recovery_action: "Current generation recovery." }));
    coreState.current = { status: "healthy", client: { getStudySession: second }, connectionGeneration: 2, retry: vi.fn() } as never;
    view.rerender(<MemoryRouter initialEntries={["/deep-learn/session-1?course_id=course-1"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Routes><Route path="/deep-learn/:id" element={<DeepLearnPage />} /></Routes></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByText("Current generation recovery.")).toBeInTheDocument();
    resolve({ outcome: "ready", course_id: "course-1", session, plan, current_unit_id: "unit-1", recovery_action: null });
    await waitFor(() => expect(screen.queryByText("Source display text.")).not.toBeInTheDocument());
  });

  it("runs the opening diagnostic as an explicit non-scored self-report before the first active unit", async () => {
    const user = userEvent.setup();
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn(async () => notStartedDiagnostic);
    const beginStudySessionDiagnostic = vi.fn(async () => ({ ...pendingDiagnostic, outcome: "applied" as const, mastery_changed: false as const, scoring: "not_performed" as const }));
    const answerStudySessionDiagnostic = vi.fn(async () => ({ ...answeredDiagnostic, outcome: "applied" as const, mastery_changed: false as const, scoring: "not_performed" as const }));
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic });
    expect(await screen.findByRole("button", { name: "Begin diagnostic" })).toBeInTheDocument();
    expect(screen.queryByText("concept-1")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Begin diagnostic" }));
    expect(await screen.findByText("What do you already know about limits?")).toBeInTheDocument();
    expect(screen.getByText("This is your self-report, not a scored assessment. It does not change mastery or schedule review.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your response"), "I know the value gets close to a target.");
    await user.click(screen.getByRole("radio", { name: "Confident" }));
    await user.click(screen.getByRole("button", { name: "Continue to first unit" }));
    await waitFor(() => expect(answerStudySessionDiagnostic).toHaveBeenCalledOnce());
    expect((answerStudySessionDiagnostic.mock.calls as unknown[][])[0]?.[2]).toMatchObject({ response: "I know the value gets close to a target.", self_assessment: "confident" });
    expect((beginStudySessionDiagnostic.mock.calls as unknown[][])[0]?.[1]).toMatchObject({ course_id: "course-1", expected_revision: 4 });
    expect(screen.queryByText("What do you already know about limits?")).not.toBeInTheDocument();
  });

  it("restores a pending diagnostic after an unknown begin outcome instead of sending a duplicate", async () => {
    const user = userEvent.setup();
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn().mockResolvedValueOnce(notStartedDiagnostic).mockResolvedValueOnce(pendingDiagnostic);
    const beginStudySessionDiagnostic = vi.fn(async () => { throw new TypeError("network failed"); });
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin diagnostic" }));
    expect(await screen.findByText("What do you already know about limits?")).toBeInTheDocument();
    expect(beginStudySessionDiagnostic).toHaveBeenCalledOnce();
    expect(getStudySessionDiagnostic).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Begin diagnostic" })).not.toBeInTheDocument();
  });

  it("retries an unknown begin with its frozen idempotency key and revision", async () => {
    const user = userEvent.setup();
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn().mockResolvedValueOnce(notStartedDiagnostic).mockResolvedValueOnce(notStartedDiagnostic);
    const beginStudySessionDiagnostic = vi.fn().mockRejectedValueOnce(new TypeError("network failed")).mockResolvedValueOnce({ ...pendingDiagnostic, outcome: "applied", mastery_changed: false, scoring: "not_performed" });
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin diagnostic" }));
    expect(await screen.findByRole("button", { name: "Retry same diagnostic" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry same diagnostic" }));
    expect(await screen.findByText("What do you already know about limits?")).toBeInTheDocument();
    const calls = beginStudySessionDiagnostic.mock.calls as unknown[][];
    expect(calls[1]?.[1]).toEqual(calls[0]?.[1]);
  });

  it("reconciles a revision conflict by reading the current diagnostic state", async () => {
    const user = userEvent.setup();
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn().mockResolvedValueOnce(notStartedDiagnostic).mockResolvedValueOnce(pendingDiagnostic);
    const beginStudySessionDiagnostic = vi.fn(async () => { throw new LearningCoreResponseError(409, null, null); });
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin diagnostic" }));
    expect(await screen.findByText("What do you already know about limits?")).toBeInTheDocument();
    expect(screen.getByText("This session changed before the action completed. Keen restored the latest local diagnostic.")).toBeInTheDocument();
  });

  it("retries an unknown answer with the frozen idempotency key and original body", async () => {
    const user = userEvent.setup();
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: diagnosingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn().mockResolvedValueOnce(pendingDiagnostic).mockResolvedValueOnce(pendingDiagnostic);
    const answerStudySessionDiagnostic = vi.fn().mockRejectedValueOnce(new TypeError("connection dropped")).mockResolvedValueOnce({ ...answeredDiagnostic, outcome: "applied", mastery_changed: false, scoring: "not_performed" });
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic: vi.fn(), answerStudySessionDiagnostic });
    await user.type(await screen.findByLabelText("Your response"), "I can describe an approaching value.");
    await user.click(screen.getByRole("radio", { name: "Confident" }));
    await user.click(screen.getByRole("button", { name: "Continue to first unit" }));
    expect(await screen.findByRole("button", { name: "Retry same response" })).toBeInTheDocument();
    expect(screen.getByLabelText("Your response")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry same response" }));
    expect(await screen.findByText("Source display text.")).toBeInTheDocument();
    expect(answerStudySessionDiagnostic).toHaveBeenCalledTimes(2);
    const calls = answerStudySessionDiagnostic.mock.calls as unknown[][];
    expect(calls[1]?.[1]).toEqual(calls[0]?.[1]);
    expect(calls[1]?.[2]).toEqual(calls[0]?.[2]);
    expect(getStudySessionDiagnostic).toHaveBeenCalledTimes(2);
  });

  it("keeps a begin action single-flight while the local write is pending", async () => {
    const user = userEvent.setup();
    let resolve!: (value: unknown) => void;
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn(async () => notStartedDiagnostic);
    const beginStudySessionDiagnostic = vi.fn(() => new Promise((done) => { resolve = done; }));
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    const begin = await screen.findByRole("button", { name: "Begin diagnostic" });
    await user.click(begin);
    await user.click(begin);
    expect(beginStudySessionDiagnostic).toHaveBeenCalledOnce();
    resolve({ ...pendingDiagnostic, outcome: "applied", mastery_changed: false, scoring: "not_performed" });
    expect(await screen.findByText("What do you already know about limits?")).toBeInTheDocument();
  });

  it("aborts a cancelled write and restores the same diagnostic instead of starting over", async () => {
    const user = userEvent.setup();
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn().mockResolvedValueOnce(notStartedDiagnostic).mockResolvedValueOnce(notStartedDiagnostic);
    const beginStudySessionDiagnostic = vi.fn((...args: unknown[]) => new Promise((_, reject) => {
      const options = args[2] as { signal?: AbortSignal } | undefined;
      options?.signal?.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")), { once: true });
    }));
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin diagnostic" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(await screen.findByText(/Keen could not safely determine whether this local action was saved/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry same diagnostic" })).toBeInTheDocument();
    expect(getStudySessionDiagnostic).toHaveBeenCalledTimes(2);
  });

  it("allows the completed diagnostic to yield to the next restored learning state", async () => {
    const paused = { ...studyingSession, status: "paused" as const };
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: paused, plan, current_unit_id: "unit-1", recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn(async () => ({ ...answeredDiagnostic, session: paused }));
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic: vi.fn(), answerStudySessionDiagnostic: vi.fn() });
    expect(await screen.findByText("Source display text.")).toBeInTheDocument();
    expect(screen.getByText("Paused local session. Restoring the latest local learning state before showing details.")).toBeInTheDocument();
    expect(screen.queryByText("Opening diagnostic restored")).not.toBeInTheDocument();
  });

  it("does not expose a diagnostic answer form while its pending session is paused", async () => {
    const paused = { ...diagnosingSession, status: "paused" as const };
    const answerStudySessionDiagnostic = vi.fn();
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: paused, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn(async () => ({ ...pendingDiagnostic, session: paused }));
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic: vi.fn(), answerStudySessionDiagnostic });
    expect(await screen.findByText(/No diagnostic action was sent while this session is paused/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your response")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue to first unit" })).not.toBeInTheDocument();
    expect(answerStudySessionDiagnostic).not.toHaveBeenCalled();
  });

  it("does not expose a begin control while a not-started session is paused", async () => {
    const paused = { ...openingSession, status: "paused" as const };
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: paused, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn(async () => ({ ...notStartedDiagnostic, session: paused }));
    const beginStudySessionDiagnostic = vi.fn();
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    expect(await screen.findByText(/No diagnostic action was sent while this session is paused/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /diagnostic/i })).not.toBeInTheDocument();
    expect(beginStudySessionDiagnostic).not.toHaveBeenCalled();
    expect(screen.queryByText("concept-1")).not.toBeInTheDocument();
  });

  it("clears a rejected begin intent after a restored 409 so the next request uses current revision and a new key", async () => {
    const user = userEvent.setup();
    const revised = { ...openingSession, revision: 5 };
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn().mockResolvedValueOnce(notStartedDiagnostic).mockResolvedValueOnce({ ...notStartedDiagnostic, session: revised });
    const beginStudySessionDiagnostic = vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null)).mockResolvedValueOnce({ ...pendingDiagnostic, outcome: "applied", mastery_changed: false, scoring: "not_performed" });
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin diagnostic" }));
    expect(await screen.findByText("This session changed before the action completed. Keen restored the latest local diagnostic.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Begin diagnostic" }));
    expect(await screen.findByText("What do you already know about limits?")).toBeInTheDocument();
    const calls = beginStudySessionDiagnostic.mock.calls as unknown[][];
    expect((calls[0]?.[1] as { expected_revision: number }).expected_revision).toBe(4);
    expect((calls[1]?.[1] as { expected_revision: number }).expected_revision).toBe(5);
    expect((calls[1]?.[1] as { idempotency_key: string }).idempotency_key).not.toBe((calls[0]?.[1] as { idempotency_key: string }).idempotency_key);
  });

  it("blocks writes after a 409 reconciliation failure until a diagnostic restore succeeds", async () => {
    const user = userEvent.setup();
    const revised = { ...openingSession, revision: 5 };
    const getStudySession = vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session: openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn().mockResolvedValueOnce(notStartedDiagnostic).mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce({ ...notStartedDiagnostic, session: revised });
    const beginStudySessionDiagnostic = vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null)).mockResolvedValueOnce({ ...pendingDiagnostic, outcome: "applied", mastery_changed: false, scoring: "not_performed" });
    renderOpeningDiagnostic({ getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic, answerStudySessionDiagnostic: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Begin diagnostic" }));
    expect(await screen.findByText(/This session changed before the action completed, but Keen could not restore the latest local diagnostic/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Begin diagnostic" })).not.toBeInTheDocument();
    expect(beginStudySessionDiagnostic).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Retry diagnostic restore" }));
    expect(await screen.findByRole("button", { name: "Begin diagnostic" })).toBeInTheDocument();
    expect(beginStudySessionDiagnostic).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Begin diagnostic" }));
    const calls = beginStudySessionDiagnostic.mock.calls as unknown[][];
    expect(calls).toHaveLength(2);
    expect((calls[1]?.[1] as { expected_revision: number }).expected_revision).toBe(5);
    expect((calls[1]?.[1] as { idempotency_key: string }).idempotency_key).not.toBe((calls[0]?.[1] as { idempotency_key: string }).idempotency_key);
  });

  it("does not render a late diagnostic response after the route scope changes", async () => {
    let resolveOld!: (value: unknown) => void;
    const secondSession = { ...openingSession, id: "session-2" };
    const getStudySession = vi.fn(async (requestedSessionId: string) => ({ outcome: "ready" as const, course_id: "course-1", session: requestedSessionId === "session-2" ? secondSession : openingSession, plan, current_unit_id: null, recovery_action: null }));
    const getStudySessionDiagnostic = vi.fn((requestedSessionId: string) => requestedSessionId === "session-1"
      ? new Promise((done) => { resolveOld = done; })
      : Promise.resolve({ ...notStartedDiagnostic, session: secondSession }));
    coreState.current = { status: "healthy", client: { getStudySession, getStudySessionDiagnostic, beginStudySessionDiagnostic: vi.fn(), answerStudySessionDiagnostic: vi.fn() }, connectionGeneration: 1, retry: vi.fn() } as never;
    const view = renderCurrentCore("/deep-learn/session-1?course_id=course-1");
    expect(await screen.findByText("Restoring your local opening diagnostic…")).toBeInTheDocument();
    view.rerender(<MemoryRouter key="session-2" initialEntries={["/deep-learn/session-2?course_id=course-1"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Routes><Route path="/deep-learn/:id" element={<DeepLearnPage />} /></Routes></QueryClientProvider></MemoryRouter>);
    expect(await screen.findByRole("button", { name: "Begin diagnostic" })).toBeInTheDocument();
    resolveOld(pendingDiagnostic);
    await waitFor(() => expect(screen.queryByText("What do you already know about limits?")).not.toBeInTheDocument());
  });
});
