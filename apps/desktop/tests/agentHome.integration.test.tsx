import { MemoryRouter, useLocation } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LearningCoreResponseError, type AgentRun } from "@keen/api-client";
import type { AgentRuntimeContextValue } from "../src/services/AgentRuntimeProvider";
import { initialAgentActivityState } from "../src/features/agent/agentActivityReducer";
import { HomePage } from "../src/features/home/HomePage";
import { learningTasks } from "../src/data/seed";
import { useAppStore } from "../src/state/appStore";

const runtimeState = vi.hoisted(() => ({ current: null as unknown as AgentRuntimeContextValue }));
const learningCoreState = vi.hoisted(() => ({ current: {
  status: "healthy", client: null, connectionGeneration: 0, demoState: undefined,
  demoStatePending: false, demoStateError: null, retryError: null, retry: vi.fn(),
} }));
const learningFeedState = vi.hoisted(() => ({ current: {
  nextTask: null as null | { id: string; course_id: string; title: string; estimated_minutes: number },
  nextSession: null as null | { id: string; course_id: string; goal: string; progress: number; status: "practicing" },
  nextReview: null as null | { id: string; course_id: string; course_title: string; concept_id: string; concept_name: string },
  nextReviewTask: null as null | { id: string; course_id: string; concept_id: string; source_type: string; source_id: string },
  pending: false, error: null as Error | null, refetch: vi.fn(),
} }));

vi.mock("../src/services/AgentRuntimeProvider", () => ({
  useAgentRuntime: () => runtimeState.current,
}));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => learningCoreState.current,
  isLearningCoreStarting: (status: string) => ["starting", "binding", "migrating", "recovering", "starting_server", "health_checking", "restarting"].includes(status),
}));

vi.mock("../src/features/home/useHomeNextTask", () => ({
  useHomeNextTask: () => learningFeedState.current,
}));

const now = "2026-07-16T10:00:00.000Z";

function agentRun(status: AgentRun["status"]): AgentRun {
  const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(status);
  const unsuccessful = ["failed", "cancelled", "interrupted"].includes(status);
  return {
    id: "run-home-1",
    kind: "deep_learn",
    mode: "study",
    status,
    provider: "test-provider",
    model: "test-model",
    errorCode: unsuccessful ? "test_error" : null,
    errorDetail: unsuccessful ? "The test run ended." : null,
    createdAt: now,
    updatedAt: now,
    startedAt: status === "queued" ? null : now,
    finishedAt: terminal ? now : null,
  };
}

function runtime(overrides: Partial<AgentRuntimeContextValue> = {}): AgentRuntimeContextValue {
  return {
    activity: initialAgentActivityState,
    run: null,
    activityContext: null,
    activityContextReady: true,
    phase: "idle",
    issue: null,
    mutationAction: { target: null, pending: null, error: null, lastResult: null },
    learningCoreStatus: "healthy",
    startRun: vi.fn(async () => agentRun("queued")),
    cancelRun: vi.fn(async () => true),
    undoMutation: vi.fn(async () => true),
    redoMutation: vi.fn(async () => true),
    setActivityContext: vi.fn(),
    ...overrides,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current test route">{location.pathname}{location.search}</output>;
}

function renderHome(initialEntry = "/?mode=ask") {
  return render(<MemoryRouter initialEntries={[initialEntry]}><HomePage /><LocationProbe /></MemoryRouter>);
}

beforeEach(() => {
  sessionStorage.clear();
  useAppStore.setState({ tasks: learningTasks });
  runtimeState.current = runtime();
  learningCoreState.current = {
    status: "healthy", client: null, connectionGeneration: 0, demoState: undefined,
    demoStatePending: false, demoStateError: null, retryError: null, retry: vi.fn(),
  };
  learningFeedState.current = {
    nextTask: null, nextSession: null, nextReview: null, nextReviewTask: null, pending: false, error: null, refetch: vi.fn(),
  };
});

describe("Agent Home", () => {
  it("turns a source-scoped Study goal into one dedicated focused-study request", async () => {
    const user = userEvent.setup();
    const createAutonomousRecommendation = vi.fn();
    const startAutonomousStudySession = vi.fn();
    const focusedStudyRequest = vi.fn(async () => ({ outcome: "session_created", session: { id: "session-study-1" } }));
    learningCoreState.current = {
      status: "healthy",
      client: { createAutonomousRecommendation, startAutonomousStudySession, focusedStudyRequest, listDocuments: vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]) } as never,
      connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
      demoStatePending: false,
      demoStateError: null,
      retryError: null,
      retry: vi.fn(),
    };
    renderHome("/?mode=study&course_id=course-1");
    expect(runtimeState.current.startRun).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Message Keen" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Agent response")).not.toBeInTheDocument();

    expect(await screen.findByLabelText("Learning source course")).toHaveValue("course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Build a plan from my notes");
    await user.click(screen.getByRole("button", { name: "Start focused study" }));

    expect(focusedStudyRequest).toHaveBeenCalledOnce();
    expect(focusedStudyRequest).toHaveBeenCalledWith({
      course_id: "course-1",
      goal: "Build a plan from my notes",
      client_request_id: expect.stringMatching(/^[0-9a-f-]{36}$/i),
      idempotency_key: expect.stringMatching(/^[0-9a-f-]{36}$/i),
    }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(createAutonomousRecommendation).not.toHaveBeenCalled();
    expect(startAutonomousStudySession).not.toHaveBeenCalled();
    expect(runtimeState.current.startRun).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/deep-learn/session-study-1?course_id=course-1");
    expect(screen.queryByText("78%")).not.toBeInTheDocument();
    expect(screen.queryByText("5 sources")).not.toBeInTheDocument();
    expect(screen.queryByText("18 insights")).not.toBeInTheDocument();
  });

  it("retries an unknown focused-study result with the same request identities", async () => {
    const user = userEvent.setup();
    const focusedStudyRequest = vi.fn()
      .mockRejectedValueOnce(new TypeError("transport closed"))
      .mockResolvedValueOnce({ outcome: "replayed", session: { id: "session-reconciled-1" } });
    const createAutonomousRecommendation = vi.fn();
    const startAutonomousStudySession = vi.fn();
    learningCoreState.current = {
      status: "healthy",
      client: {
        focusedStudyRequest,
        createAutonomousRecommendation,
        startAutonomousStudySession,
        listDocuments: vi.fn(async () => [
          { id: "doc-z", status: "indexed", chunkCount: 2, courseIds: ["course-1"] },
          { id: "doc-a", status: "indexed", chunkCount: 3, courseIds: ["course-1"] },
        ]),
      } as never,
      connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Bayesian Learning" }], tasks: [], mastery: [] } as never,
      demoStatePending: false,
      demoStateError: null,
      retryError: null,
      retry: vi.fn(),
    };
    renderHome("/?mode=study&course_id=course-1");

    expect(await screen.findByLabelText("Learning source course")).toHaveValue("course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Understand Bayesian updating");
    await user.click(screen.getByRole("button", { name: "Start focused study" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("could not confirm whether this focused study session was started");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(focusedStudyRequest).toHaveBeenCalledTimes(2));
    expect(focusedStudyRequest.mock.calls[1]?.[0]).toEqual(focusedStudyRequest.mock.calls[0]?.[0]);
    expect(createAutonomousRecommendation).not.toHaveBeenCalled();
    expect(startAutonomousStudySession).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/deep-learn/session-reconciled-1?course_id=course-1");
  });

  it("shows authoritative blocked recovery without fabricating a session", async () => {
    const user = userEvent.setup();
    const focusedStudyRequest = vi.fn(async () => ({
      outcome: "blocked", session: null, recovery_action: "Index at least one source for this course, then try again.",
    }));
    const createAutonomousRecommendation = vi.fn();
    const startAutonomousStudySession = vi.fn();
    learningCoreState.current = {
      status: "healthy",
      client: { focusedStudyRequest, createAutonomousRecommendation, startAutonomousStudySession, listDocuments: vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]) } as never,
      connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
      demoStatePending: false,
      demoStateError: null,
      retryError: null,
      retry: vi.fn(),
    };
    renderHome("/?mode=study&course_id=course-1");

    await screen.findByLabelText("Learning source course");
    expect(screen.getByText(/goal is saved with the source-grounded task and focused study session/i)).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Keep this goal");
    await user.click(screen.getByRole("button", { name: "Start focused study" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Index at least one source for this course");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message Keen" })).toHaveValue("Keep this goal");
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/?mode=study&course_id=course-1");
    expect(createAutonomousRecommendation).not.toHaveBeenCalled();
    expect(startAutonomousStudySession).not.toHaveBeenCalled();
  });

  it("preserves a valid indexed course while switching between Study and Ask", async () => {
    const user = userEvent.setup();
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments: vi.fn(async () => [
        { id: "doc-ready", status: "indexed", chunkCount: 4, courseIds: ["course-2"] },
        { id: "doc-unready", status: "stored", chunkCount: 0, courseIds: ["course-1"] },
      ]) } as never,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }, { id: "course-2", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome("/?mode=study&course_id=course-2");

    const studyScope = await screen.findByLabelText("Learning source course");
    expect(studyScope).toHaveValue("course-2");
    expect(studyScope).not.toHaveTextContent("Calculus");
    await user.click(screen.getByRole("button", { name: "Ask sources mode" }));
    expect(screen.getByRole("status", { name: "Current test route" })).toHaveTextContent("/?mode=ask&course_id=course-2");
    expect(screen.getByLabelText("Question source scope")).toHaveValue("course:course-2");
  });

  it("fails a stale or unindexed requested course closed without selecting another course", async () => {
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments: vi.fn(async () => [
        { id: "doc-unready", status: "stored", chunkCount: 0, courseIds: ["course-1"] },
        { id: "doc-ready", status: "indexed", chunkCount: 4, courseIds: ["course-2"] },
      ]) } as never,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }, { id: "course-2", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome("/?mode=study&course_id=course-1");

    const studyScope = await screen.findByLabelText("Learning source course");
    await waitFor(() => expect(studyScope).toHaveValue(""));
    expect(studyScope).not.toHaveTextContent("Calculus");
    expect(studyScope).toHaveTextContent("Linear Algebra");
    expect(screen.getByRole("alert")).toHaveTextContent("no longer has indexed material");
    expect(screen.getByRole("button", { name: "Start focused study" })).toBeDisabled();
  });

  it("shows one shared material-read error in Study and restores the requested course after Retry", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn()
      .mockRejectedValueOnce(new TypeError("document read failed"))
      .mockResolvedValueOnce([{ id: "doc-ready", status: "indexed", chunkCount: 4, courseIds: ["course-1"] }]);
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments } as never,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }], tasks: [], mastery: [] } as never,
    };
    renderHome("/?mode=study&course_id=course-1");

    expect(await screen.findByRole("alert")).toHaveTextContent("could not check which course materials are ready");
    expect(screen.queryByText(/selected course no longer has indexed material/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Learning source course")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Start focused study" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByLabelText("Learning source course")).toHaveValue("course-1"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listDocuments).toHaveBeenCalledTimes(2);
  });

  it("presents one recoverable queue error without duplicate evidence badges or schedule actions", async () => {
    const user = userEvent.setup();
    const retry = vi.fn(async () => undefined);
    learningCoreState.current = {
      status: "error", client: null, connectionGeneration: 0, demoState: undefined,
      demoStatePending: false, demoStateError: null, retryError: null, retry,
    };
    runtimeState.current = runtime({ learningCoreStatus: "error" });
    renderHome();

    expect(screen.getByRole("alert")).toHaveTextContent("learning service is not connected");
    expect(screen.queryByText("Local evidence")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Open schedule/i })).not.toBeInTheDocument();
    expect(screen.getByText("Choose a learning mode and source, then tell Keen what you want to understand.")).toBeInTheDocument();

    const composer = screen.getByRole("textbox", { name: "Message Keen" });
    await user.type(composer, "Keep this draft{Enter}");
    expect(composer).toHaveValue("Keep this draft");
    expect(runtimeState.current.startRun).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Ask sources" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Retry connection" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("shows one saved next task without competing with the request workbench", async () => {
    const user = userEvent.setup();
    learningCoreState.current = {
      status: "healthy", client: { listDocuments: vi.fn(async () => []) } as never, connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }, { id: "course-2", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
      demoStatePending: false, demoStateError: null, retryError: null, retry: vi.fn(),
    };
    learningFeedState.current = {
      ...learningFeedState.current,
      nextTask: { id: "task-2", course_id: "course-2", title: "Review eigenvectors", estimated_minutes: 5 },
      nextSession: { id: "session-2", course_id: "course-2", goal: "Explain eigenvectors without notes", progress: 0.5, status: "practicing" },
    };
    renderHome("/");

    const queue = screen.getByRole("heading", { level: 1, name: "Today" });
    expect(queue).toBeInTheDocument();
    expect(screen.getByText("Explain eigenvectors without notes")).toBeInTheDocument();
    expect(screen.getByText("Linear Algebra")).toBeInTheDocument();
    expect(screen.getByText("50% complete · Continue practice")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What shall we explore?" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue practice" })).toBeInTheDocument();
    expect(screen.queryByText(/stored on this Mac|configured provider|local learning evidence/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue practice" }));
    expect(screen.getByRole("status", { name: "Current test route" })).toHaveTextContent("/deep-learn/session-2?course_id=course-2");
  });

  it("puts a real due review ahead of a saved task and opens Review", async () => {
    const user = userEvent.setup();
    learningCoreState.current = {
      status: "healthy", client: { listDocuments: vi.fn(async () => []) } as never, connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }], tasks: [], mastery: [] } as never,
      demoStatePending: false, demoStateError: null, retryError: null, retry: vi.fn(),
    };
    learningFeedState.current = {
      ...learningFeedState.current,
      nextTask: { id: "task-1", course_id: "course-1", title: "Continue limits", estimated_minutes: 10 },
      nextReview: { id: "review-1", course_id: "course-1", course_title: "Calculus", concept_id: "concept-1", concept_name: "Limits" },
      nextReviewTask: { id: "task-review-1", course_id: "course-1", concept_id: "concept-1", source_type: "review", source_id: "review-1" },
    };
    renderHome("/");

    expect(screen.getByText("Review Limits")).toBeInTheDocument();
    expect(screen.getByText("Due now · continue scheduled review")).toBeInTheDocument();
    expect(screen.queryByText("Continue limits")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review now" }));
    expect(screen.getByRole("status", { name: "Current test route" })).toHaveTextContent("/review?course_id=course-1&review_item_id=review-1&task=task-review-1");
  });

  it("opens bare Review when no exact persisted review task can be proven", async () => {
    const user = userEvent.setup();
    learningCoreState.current = {
      status: "healthy", client: { listDocuments: vi.fn(async () => []) } as never, connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }], tasks: [], mastery: [] } as never,
      demoStatePending: false, demoStateError: null, retryError: null, retry: vi.fn(),
    };
    learningFeedState.current = {
      ...learningFeedState.current,
      nextReview: { id: "review-1", course_id: "course-1", course_title: "Calculus", concept_id: "concept-1", concept_name: "Limits" },
      nextReviewTask: null,
    };
    renderHome("/");

    await user.click(screen.getByRole("button", { name: "Review now" }));
    expect(screen.getByRole("status", { name: "Current test route" })).toHaveTextContent(/^\/review$/);
  });

  it("opens the displayed Browser Demo task and stops presenting completed samples as next up", async () => {
    const user = userEvent.setup();
    learningCoreState.current = { ...learningCoreState.current, status: "demo" };
    const view = renderHome("/");

    await user.click(screen.getByRole("button", { name: "Continue task" }));
    expect(screen.getByRole("status", { name: "Current test route" })).toHaveTextContent("/feed?task=t1");

    view.unmount();
    act(() => useAppStore.setState({ tasks: learningTasks.map((task) => ({ ...task, status: "completed" })) }));
    renderHome("/");
    expect(screen.getByRole("heading", { level: 1, name: "What shall we explore?" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue task" })).not.toBeInTheDocument();
  });

  it("promotes the request workbench when the queue is empty", async () => {
    learningCoreState.current = {
      status: "healthy", client: { listDocuments: vi.fn(async () => []) } as never, connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }], tasks: [], mastery: [] } as never,
      demoStatePending: false, demoStateError: null, retryError: null, retry: vi.fn(),
    };
    learningFeedState.current = {
      ...learningFeedState.current,
      nextTask: null,
    };
    renderHome("/");

    expect(screen.getByRole("heading", { level: 1, name: "What shall we explore?" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Today" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Add and index course material before asking/)).toBeInTheDocument());
  });

  it("does not present a disabled no-course feed query as a loading queue", async () => {
    learningCoreState.current = {
      status: "healthy", client: { listDocuments: vi.fn(async () => []) } as never, connectionGeneration: 1,
      demoState: { courses: [], tasks: [], mastery: [] } as never,
      demoStatePending: false, demoStateError: null, retryError: null, retry: vi.fn(),
    };
    learningFeedState.current = {
      ...learningFeedState.current,
      pending: true,
    };
    renderHome("/");

    expect(screen.getByRole("heading", { level: 1, name: "What shall we explore?" })).toBeInTheDocument();
    expect(screen.queryByText("Loading your learning queue")).not.toBeInTheDocument();
    expect(screen.queryByText("Your saved next actions are loading.")).not.toBeInTheDocument();
    await screen.findByText(/Add and index course material before asking/);
  });

  it("keeps Browser Demo request-free and records only the local conversation handoff", async () => {
    const user = userEvent.setup();
    learningCoreState.current = { ...learningCoreState.current, status: "demo" };
    renderHome();

    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Demo question");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));

    expect(runtimeState.current.startRun).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("keen-new-message")).toBe("Demo question");
  });

  it("does not submit when Enter confirms an IME composition", () => {
    learningCoreState.current = { ...learningCoreState.current, status: "demo" };
    renderHome();
    const composer = screen.getByRole("textbox", { name: "Message Keen" });
    fireEvent.change(composer, { target: { value: "中文问题" } });
    fireEvent.keyDown(composer, { key: "Enter", code: "Enter", isComposing: true });
    expect(sessionStorage.getItem("keen-new-message")).toBeNull();
    expect(screen.getByRole("status", { name: "Current test route" })).toHaveTextContent("/?mode=ask");
    expect(composer).toHaveValue("中文问题");
  });

  it("creates one durable course-scoped question and never starts an Agent run", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    const createConversation = vi.fn(async (request: { id: string; question: string; sourceScope: unknown }) => ({
      conversation: { id: request.id, courseId: "course-1", title: request.question, mode: "ask", status: "active", sourceScope: request.sourceScope, createdAt: now, updatedAt: now, archivedAt: null }, replayed: false,
    }));
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome();

    await user.selectOptions(await screen.findByLabelText("Question source scope"), "course:course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Explain eigenvectors");
    await user.dblClick(screen.getByRole("button", { name: "Ask sources" }));

    expect(createConversation).toHaveBeenCalledOnce();
    expect(createConversation).toHaveBeenCalledWith(expect.objectContaining({ question: "Explain eigenvectors", sourceScope: { kind: "course", courseId: "course-1" } }), expect.anything());
    expect(runtimeState.current.startRun).not.toHaveBeenCalled();
    expect([...Array(sessionStorage.length)].map((_, index) => sessionStorage.key(index)).filter((key) => key?.startsWith("keen-durable-conversation-handoff:"))).toHaveLength(1);
  });

  it("requires an explicit all-indexed choice and preserves that scope", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    const createConversation = vi.fn(async (request: { id: string; question: string; sourceScope: unknown }) => ({
      conversation: { id: request.id, courseId: null, title: request.question, mode: "ask", status: "active", sourceScope: request.sourceScope, createdAt: now, updatedAt: now, archivedAt: null }, replayed: false,
    }));
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome();

    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Compare my indexed courses");
    expect(screen.getByRole("button", { name: "Ask sources" })).toBeDisabled();
    await user.selectOptions(await screen.findByLabelText("Question source scope"), "all_indexed");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));

    expect(createConversation).toHaveBeenCalledWith(expect.objectContaining({ sourceScope: { kind: "all_indexed" } }), expect.anything());
    expect(runtimeState.current.startRun).not.toHaveBeenCalled();
  });

  it("adopts an authoritative conversation after an unknown create response", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    const createConversation = vi.fn(async () => { throw new TypeError("transport closed"); });
    const getConversation = vi.fn(async (id: string) => ({
      id, courseId: "course-1", title: "Explain eigenvectors", mode: "ask", status: "active",
      sourceScope: { kind: "course", courseId: "course-1" }, createdAt: now, updatedAt: now, archivedAt: null,
    }));
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation, getConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome();

    await user.selectOptions(await screen.findByLabelText("Question source scope"), "course:course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Explain eigenvectors");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));

    await waitFor(() => expect(getConversation).toHaveBeenCalledOnce());
    expect(createConversation).toHaveBeenCalledOnce();
    expect([...Array(sessionStorage.length)].map((_, index) => sessionStorage.key(index)).filter((key) => key?.startsWith("keen-durable-conversation-handoff:"))).toHaveLength(1);
  });

  it("retries a confirmed missing create with the same conversation and turn identities", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    const createRequests: Array<{ id: string; question: string; sourceScope: unknown }> = [];
    const createConversation = vi.fn(async (request: { id: string; question: string; sourceScope: unknown }) => {
      createRequests.push(request);
      if (createRequests.length === 1) throw new TypeError("transport closed");
      return { conversation: { id: request.id, courseId: "course-1", title: request.question, mode: "ask", status: "active", sourceScope: request.sourceScope, createdAt: now, updatedAt: now, archivedAt: null }, replayed: false };
    });
    const getConversation = vi.fn(async () => { throw new LearningCoreResponseError(404, null, null); });
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation, getConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome();

    await user.selectOptions(await screen.findByLabelText("Question source scope"), "course:course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Explain eigenvectors");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));

    await waitFor(() => expect(createConversation).toHaveBeenCalledTimes(2));
    expect(createRequests[1]).toEqual(createRequests[0]);
    const handoffKey = [...Array(sessionStorage.length)].map((_, index) => sessionStorage.key(index)).find((key) => key?.startsWith("keen-durable-conversation-handoff:"));
    const handoff = JSON.parse(sessionStorage.getItem(handoffKey!) ?? "{}") as Record<string, string>;
    expect(handoff.conversationId).toBe(createRequests[0].id);
    expect(handoff.userMessageId).toBeTruthy();
    expect(handoff.assistantMessageId).toBeTruthy();
    expect(handoff.idempotencyKey).toBeTruthy();
  });

  it("fails a create conflict without generating a replacement identity", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    const createConversation = vi.fn(async () => { throw new LearningCoreResponseError(409, null, null); });
    const getConversation = vi.fn(async (id: string) => ({
      id, courseId: null, title: "Different saved request", mode: "ask", status: "active",
      sourceScope: { kind: "all_indexed" }, createdAt: now, updatedAt: now, archivedAt: null,
    }));
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation, getConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome();

    await user.selectOptions(await screen.findByLabelText("Question source scope"), "course:course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Explain eigenvectors");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("different saved request");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(createConversation).toHaveBeenCalledOnce();
    expect(getConversation).not.toHaveBeenCalled();
    expect([...Array(sessionStorage.length)].map((_, index) => sessionStorage.key(index)).filter((key) => key?.startsWith("keen-durable-conversation-handoff:"))).toHaveLength(0);
  });

  it("does not replay a confirmed-missing create after Home unmounts", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    const createConversation = vi.fn((_request: unknown, options?: { signal?: AbortSignal }) => new Promise((_, reject) => {
      options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    }));
    const getConversation = vi.fn(async () => { throw new LearningCoreResponseError(404, null, null); });
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation, getConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    const view = renderHome();

    await user.selectOptions(await screen.findByLabelText("Question source scope"), "course:course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Explain eigenvectors");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));
    expect(createConversation).toHaveBeenCalledOnce();
    view.unmount();

    await waitFor(() => expect(getConversation).toHaveBeenCalledOnce());
    expect(createConversation).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem("keen-durable-home-ask-resume")).toBeNull();
  });

  it("keeps an authoritative create found after Home unmounts for route recovery", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    let requestId = "";
    const createConversation = vi.fn((request: { id: string }, options?: { signal?: AbortSignal }) => {
      requestId = request.id;
      return new Promise((_, reject) => {
        options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
    });
    const getConversation = vi.fn(async (id: string) => ({
      id, courseId: "course-1", title: "Explain eigenvectors", mode: "ask", status: "active",
      sourceScope: { kind: "course", courseId: "course-1" }, createdAt: now, updatedAt: now, archivedAt: null,
    }));
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation, getConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    const view = renderHome();

    await user.selectOptions(await screen.findByLabelText("Question source scope"), "course:course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Explain eigenvectors");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));
    view.unmount();

    await waitFor(() => expect(getConversation).toHaveBeenCalledOnce());
    expect(sessionStorage.getItem("keen-durable-home-ask-resume")).toBe(requestId);
    expect(sessionStorage.getItem(`keen-durable-conversation-handoff:${requestId}`)).not.toBeNull();
  });

  it("clears an Ask retry when switching to Study", async () => {
    const user = userEvent.setup();
    const listDocuments = vi.fn(async () => [{ id: "doc-1", status: "indexed", chunkCount: 3, courseIds: ["course-1"] }]);
    const createConversation = vi.fn(async () => { throw new TypeError("transport closed"); });
    const getConversation = vi.fn(async () => { throw new TypeError("read failed"); });
    learningCoreState.current = {
      ...learningCoreState.current,
      client: { listDocuments, createConversation, getConversation } as never,
      demoState: { courses: [{ id: "course-1", title: "Linear Algebra" }], tasks: [], mastery: [] } as never,
    };
    renderHome();

    await user.selectOptions(await screen.findByLabelText("Question source scope"), "course:course-1");
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Explain eigenvectors");
    await user.click(screen.getByRole("button", { name: "Ask sources" }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Focused study mode" }));
    expect(screen.queryByText(/could not confirm whether this question was started/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
