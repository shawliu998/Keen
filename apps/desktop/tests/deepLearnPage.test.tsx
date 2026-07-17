import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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

function renderPage(getStudySession: ReturnType<typeof vi.fn>, path = "/deep-learn/session-1?course_id=course-1") {
  coreState.current = { status: "healthy", client: { getStudySession }, connectionGeneration: 1, retry: vi.fn() } as never;
  return renderCurrentCore(path);
}

function renderCurrentCore(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter initialEntries={[path]}><QueryClientProvider client={queryClient}><Routes><Route path="/deep-learn/:id" element={<DeepLearnPage />} /></Routes></QueryClientProvider></MemoryRouter>);
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
});
