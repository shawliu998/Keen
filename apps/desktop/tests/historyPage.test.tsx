import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import type { AutonomousStudySession, ConversationSummary, MasteryState } from "@keen/api-client";
import { HistoryPage } from "../src/features/history/HistoryPage";

const coreState = vi.hoisted(() => ({ current: null as never }));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => coreState.current,
  isLearningCoreStarting: (status: string) => status === "starting",
}));

function RouteProbe() {
  const location = useLocation();
  return <div>Restored study session {location.search}</div>;
}

function renderHistory(initialEntry = "/history") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/history" element={<><HistoryPage /><RouteProbe /></>} />
          <Route path="/deep-learn/:id" element={<RouteProbe />} />
          <Route path="/conversation/:id" element={<div>Authoritative conversation record</div>} />
          <Route path="/knowledge" element={<div>Knowledge Base destination</div>} />
          <Route path="/" element={<><div>New learning destination</div><RouteProbe /></>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return Object.assign(view, { queryClient });
}

const persistedSession: AutonomousStudySession = {
  id: "session-1",
  course_id: "course-1",
  originating_task_id: "task-1",
  title: "Limits study",
  mode: "study",
  goal: "Understand limits from the indexed chapter.",
  estimated_minutes: 20,
  status: "paused",
  progress: 0.5,
  revision: 4,
  created_at: "2026-07-20T10:00:00+00:00",
  updated_at: "2026-07-21T10:00:00+00:00",
  started_at: "2026-07-20T10:02:00+00:00",
};

function healthyState(listStudySessions: ReturnType<typeof vi.fn>, courses = [{ id: "course-1", title: "Calculus" }], mastery: MasteryState[] = []) {
  const listConversations = vi.fn(async (_request: unknown, _options: unknown): Promise<{ conversations: ConversationSummary[]; nextCursor: string | null }> => {
    void _request;
    void _options;
    return { conversations: [], nextCursor: null };
  });
  coreState.current = {
    status: "healthy",
    client: { listStudySessions, listConversations },
    connectionGeneration: 2,
    demoState: { courses, tasks: [], mastery },
    demoStatePending: false,
    demoStateError: null,
    retry: vi.fn(),
  } as never;
  return { listConversations };
}

function masteryRow(overrides: Partial<MasteryState>): MasteryState {
  return {
    concept_id: "concept-1",
    course_id: "course-1",
    concept_name: "Eigenvectors",
    probability: 0.5,
    attempts: 4,
    updated_at: "2026-07-21T10:00:00+00:00",
    ...overrides,
  };
}

const savedQuestion: ConversationSummary = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "Why does a limit exist here?",
  status: "active",
  sourceScope: { kind: "course", courseId: "course-1" },
  courseTitle: "Calculus",
  messageCount: 2,
  lastMessagePreview: "A limit exists when nearby values approach the same result.",
  answerStatus: "completed",
  createdAt: "2026-07-20T10:00:00+00:00",
  updatedAt: "2026-07-21T11:00:00+00:00",
};

describe("HistoryPage", () => {
  it("renders a persisted session with one primary tab stop and restores its scoped route", async () => {
    const user = userEvent.setup();
    const listStudySessions = vi.fn(async () => ({ course_id: "course-1", sessions: [persistedSession] }));
    healthyState(listStudySessions);
    renderHistory();

    expect(await screen.findByRole("heading", { name: "Study sessions" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Questions" })).toBeInTheDocument();
    expect(await screen.findByText("Paused")).toBeInTheDocument();
    expect(screen.getByText("Session paused")).toBeInTheDocument();
    expect(screen.getByText("Resume the saved step")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText(/Jul 21, 2026/)).toBeInTheDocument();
    expect(screen.getByText("1 saved")).toBeInTheDocument();
    const row = screen.getByRole("article");
    expect(within(row).getAllByRole("button")).toHaveLength(1);
    await user.click(within(row).getByRole("button", { name: "Resume session: Limits study" }));
    expect(screen.getByText(/course_id=course-1/)).toBeInTheDocument();
  });

  it("presents a summary-ready session as one continuous learner-facing record", async () => {
    const summarySession: AutonomousStudySession = {
      ...persistedSession,
      title: "Study: Learn limits.",
      goal: "Learn limits.",
      status: "summarizing",
      progress: 0,
    };
    healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [summarySession] })));
    renderHistory();

    const row = await screen.findByRole("article");
    expect(within(row).getAllByText("Learn limits.")).toHaveLength(1);
    expect(within(row).queryByText("0%")).not.toBeInTheDocument();
    expect(within(row).getByText("Recall and practice are saved. Finish the session to schedule review.")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Finish and schedule review: Learn limits." })).toBeInTheDocument();
  });

  it("sorts by updated time and maps every persisted status to a learner-facing action", async () => {
    const statuses: Array<[AutonomousStudySession["status"], string]> = [
      ["draft", "Start session"], ["goal_confirmation", "Start session"], ["diagnosing", "Continue reflection"],
      ["planning", "Continue session"], ["studying", "Continue reading"], ["checkpoint", "Continue reading"],
      ["active_recall", "Continue recall"], ["practicing", "Continue practice"], ["summarizing", "Finish and schedule review"],
      ["review_scheduling", "Finish and schedule review"], ["paused", "Resume session"], ["completed", "View record"],
      ["cancelled", "View record"], ["failed", "View record"],
    ];
    const sessions = statuses.map(([status], index) => ({
      ...persistedSession,
      id: `session-${index}`,
      title: `Session ${status}`,
      status,
      updated_at: `2026-07-${String(index + 1).padStart(2, "0")}T10:00:00+00:00`,
    }));
    healthyState(vi.fn(async () => ({ course_id: "course-1", sessions })));
    renderHistory();

    const buttons = await screen.findAllByRole("button", { name: /Session / });
    expect(buttons[0]).toHaveAccessibleName("View record: Session failed");
    statuses.forEach(([status, action]) => expect(screen.getByRole("button", { name: `${action}: Session ${status}` })).toBeInTheDocument());
    expect(screen.getByText("The learning session and its result are complete.")).toBeInTheDocument();
    expect(screen.getByText("The session ended before completion.")).toBeInTheDocument();
    expect(screen.getByText("The session stopped with a recoverable record.")).toBeInTheDocument();
  });

  it("keeps Browser Demo request-free and does not invent sessions", () => {
    const listStudySessions = vi.fn();
    const listConversations = vi.fn();
    coreState.current = { status: "demo", client: { listStudySessions, listConversations }, connectionGeneration: 0, demoState: undefined, demoStatePending: false, demoStateError: null, retry: vi.fn() } as never;
    renderHistory();
    expect(screen.getByText("Your learning history starts here")).toBeInTheDocument();
    expect(screen.queryByText(/Browser Demo/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start new learning" })).toBeInTheDocument();
    expect(listStudySessions).not.toHaveBeenCalled();
    expect(listConversations).not.toHaveBeenCalled();
  });

  it("routes no-course and empty states to real next actions", async () => {
    const user = userEvent.setup();
    healthyState(vi.fn(), []);
    const view = renderHistory();
    await act(async () => {
      screen.getByRole("button", { name: "Open Knowledge Base" }).click();
    });
    expect(await screen.findByText("Knowledge Base destination")).toBeInTheDocument();
    view.unmount();

    const { listConversations } = healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [] })));
    listConversations.mockResolvedValue({ conversations: [savedQuestion], nextCursor: null });
    renderHistory();
    await user.click((await screen.findAllByRole("button", { name: "Start study" }))[0]!);
    expect(screen.getByText("New learning destination")).toBeInTheDocument();
    expect(screen.getByText(/mode=study&course_id=course-1/)).toBeInTheDocument();
  });

  it("renders one combined empty state when questions and sessions are both empty", async () => {
    const user = userEvent.setup();
    const listStudySessions = vi.fn(async () => ({ course_id: "course-1", sessions: [] }));
    const { listConversations } = healthyState(listStudySessions);
    renderHistory();

    expect(await screen.findByText("No saved history yet")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Questions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Study sessions" })).not.toBeInTheDocument();
    expect(screen.queryByText("No saved questions yet")).not.toBeInTheDocument();
    expect(screen.queryByText("No study sessions yet")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start study" })).not.toBeInTheDocument();
    expect(listConversations).toHaveBeenCalled();
    expect(listStudySessions).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "New learning" }));
    expect(screen.getByText("New learning destination")).toBeInTheDocument();
    expect(screen.getByText(/\?mode=ask/)).toBeInTheDocument();
  });

  it("restores and updates a validated course query for study history", async () => {
    const user = userEvent.setup();
    const listStudySessions = vi.fn(async (courseId: string) => ({ course_id: courseId, sessions: [] }));
    healthyState(listStudySessions, [{ id: "course-1", title: "Calculus" }, { id: "course-2", title: "Physics" }]);
    renderHistory("/history?course_id=course-2");

    expect(await screen.findByLabelText("Study session course")).toHaveValue("course-2");
    await waitFor(() => expect(listStudySessions).toHaveBeenCalledWith("course-2", expect.anything()));
    await user.selectOptions(screen.getByLabelText("Study session course"), "course-1");
    await waitFor(() => expect(listStudySessions).toHaveBeenCalledWith("course-1", expect.anything()));
    expect(screen.getByText(/course_id=course-1/)).toBeInTheDocument();
  });

  it("does not substitute another course when a history link is stale", async () => {
    const listStudySessions = vi.fn(async () => ({ course_id: "course-1", sessions: [] }));
    healthyState(listStudySessions, [{ id: "course-1", title: "Calculus" }, { id: "course-2", title: "Physics" }]);
    renderHistory("/history?course_id=course-removed");

    expect(await screen.findByText("Selected course is unavailable")).toBeInTheDocument();
    expect(screen.getByLabelText("Study session course")).toHaveValue("");
    expect(listStudySessions).not.toHaveBeenCalled();
  });

  it("keeps service and course-read failures local and retryable", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    coreState.current = { status: "unavailable", client: null, connectionGeneration: 1, demoState: undefined, demoStatePending: false, demoStateError: null, retry } as never;
    const view = renderHistory();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(1);
    view.unmount();

    const listStudySessions = vi.fn(async () => { throw new Error("read failed"); });
    healthyState(listStudySessions);
    renderHistory();
    await user.click(await screen.findByRole("button", { name: "Retry sessions" }, { timeout: 3_000 }));
    expect(listStudySessions).toHaveBeenCalledTimes(3);
  });

  it("lists durable questions independently and opens the authoritative conversation route", async () => {
    const user = userEvent.setup();
    const { listConversations } = healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [] })));
    listConversations.mockResolvedValue({ conversations: [savedQuestion], nextCursor: null });
    renderHistory();

    const questionRow = await screen.findByRole("button", { name: "Open record: Why does a limit exist here?" });
    expect(within(questionRow).getByText("Calculus")).toBeInTheDocument();
    expect(within(questionRow).getByText("Answered")).toBeInTheDocument();
    expect(within(questionRow).getByText("2 messages")).toBeInTheDocument();
    expect(within(questionRow.closest("article")!).getAllByRole("button")).toHaveLength(1);
    await user.click(questionRow);
    expect(screen.getByText("Authoritative conversation record")).toBeInTheDocument();
  });

  it("keeps question and session failures independent", async () => {
    const listStudySessions = vi.fn(async () => ({ course_id: "course-1", sessions: [persistedSession] }));
    const { listConversations } = healthyState(listStudySessions);
    listConversations.mockRejectedValue(new Error("questions failed"));
    renderHistory();

    expect(await screen.findByText("Questions could not be loaded", {}, { timeout: 3_000 })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Resume session: Limits study" })).toBeInTheDocument();
  });

  it("keeps the Questions loading and empty states local while sessions remain available", async () => {
    let resolveQuestions!: (value: { conversations: ConversationSummary[]; nextCursor: null }) => void;
    const listStudySessions = vi.fn(async () => ({ course_id: "course-1", sessions: [persistedSession] }));
    const { listConversations } = healthyState(listStudySessions);
    listConversations.mockReturnValue(new Promise((resolve) => { resolveQuestions = resolve; }));
    renderHistory();

    expect(screen.getByRole("status", { name: "Loading saved questions" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Resume session: Limits study" })).toBeInTheDocument();
    await act(async () => { resolveQuestions({ conversations: [], nextCursor: null }); });
    expect(await screen.findByText("No saved questions yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume session: Limits study" })).toBeInTheDocument();
  });

  it("keeps truthful question scope labels visible when the Study sessions read fails", async () => {
    const listStudySessions = vi.fn(async () => { throw new Error("sessions failed"); });
    const { listConversations } = healthyState(listStudySessions);
    listConversations.mockResolvedValue({
      conversations: [
        { ...savedQuestion, courseTitle: null },
        { ...savedQuestion, id: "22222222-2222-4222-8222-222222222222", title: "Question across my library", sourceScope: { kind: "all_indexed" }, courseTitle: null },
      ],
      nextCursor: null,
    });
    renderHistory();

    expect(await screen.findByText("Course unavailable")).toBeInTheDocument();
    expect(screen.getByText("All indexed sources")).toBeInTheDocument();
    expect(await screen.findByText("Study sessions could not be loaded", {}, { timeout: 3_000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `Open record: ${savedQuestion.title}` })).toBeInTheDocument();
  });

  it.each([
    ["failed", "Needs attention"],
    ["cancelled", "Cancelled"],
    ["interrupted", "Interrupted"],
  ] as const)("opens terminal %s questions as records", async (answerStatus, label) => {
    const { listConversations } = healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [] })));
    listConversations.mockResolvedValue({ conversations: [{ ...savedQuestion, answerStatus }], nextCursor: null });
    renderHistory();
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `Open record: ${savedQuestion.title}` })).toBeInTheDocument();
  });

  it("loads another bounded question page with the server cursor", async () => {
    const user = userEvent.setup();
    const { listConversations } = healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [] })));
    listConversations
      .mockResolvedValueOnce({ conversations: [savedQuestion], nextCursor: "next-page" })
      .mockResolvedValueOnce({ conversations: [{ ...savedQuestion, id: "22222222-2222-4222-8222-222222222222", title: "Second saved question", updatedAt: "2026-07-20T09:00:00+00:00" }], nextCursor: null });
    renderHistory();
    await user.click(await screen.findByRole("button", { name: "Load more questions" }));
    expect(await screen.findByText("Second saved question")).toBeInTheDocument();
    expect(listConversations).toHaveBeenLastCalledWith({ limit: 25, cursor: "next-page" }, expect.any(Object));
  });

  it("renders the Current mastery snapshot after the saved history sections", async () => {
    healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [persistedSession] })), [{ id: "course-1", title: "Calculus" }], [masteryRow({})]);
    renderHistory();

    const heading = await screen.findByRole("heading", { name: "Current mastery" });
    const section = heading.closest("section")!;
    expect(within(section).getByText("Based on recorded recall and practice attempts.")).toBeInTheDocument();
    expect(section.compareDocumentPosition(screen.getByRole("heading", { name: "Questions" })) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    expect(section.compareDocumentPosition(screen.getByRole("heading", { name: "Study sessions" })) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    expect(within(section).getByRole("list")).toBeInTheDocument();
    expect(within(section).getByRole("meter", { name: "Eigenvectors" })).toBeInTheDocument();
  });

  it("does not describe History as empty when recorded mastery exists", async () => {
    healthyState(
      vi.fn(async () => ({ course_id: "course-1", sessions: [] })),
      [{ id: "course-1", title: "Calculus" }],
      [masteryRow({})],
    );
    renderHistory();

    expect(await screen.findByRole("heading", { name: "Current mastery" })).toBeInTheDocument();
    expect(screen.queryByText("No saved history yet")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Questions" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Study sessions" })).toBeInTheDocument();
  });

  it("keeps cached study sessions visible during a background refresh", async () => {
    let resolveRefresh!: (value: { course_id: string; sessions: AutonomousStudySession[] }) => void;
    const listStudySessions = vi.fn()
      .mockResolvedValueOnce({ course_id: "course-1", sessions: [persistedSession] })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve; }));
    healthyState(listStudySessions);
    const { queryClient } = renderHistory();

    expect(await screen.findByRole("button", { name: "Resume session: Limits study" })).toBeInTheDocument();
    await act(async () => {
      void queryClient.invalidateQueries({ queryKey: ["learning-core", "study-session-history"] });
    });
    await waitFor(() => expect(listStudySessions).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "Resume session: Limits study" })).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading study sessions" })).not.toBeInTheDocument();

    await act(async () => {
      resolveRefresh({ course_id: "course-1", sessions: [persistedSession] });
    });
  });

  it("ranks weakest concepts first, caps at six, and exposes exact meter values", async () => {
    const mastery = [
      masteryRow({ concept_id: "c4", concept_name: "Derivatives", probability: 0.72, attempts: 9 }),
      masteryRow({ concept_id: "c7", concept_name: "Matrices", probability: 0.95, attempts: 12 }),
      masteryRow({ concept_id: "c-prior", concept_name: "Untouched prior", probability: 0.05, attempts: 0 }),
      masteryRow({ concept_id: "c1", concept_name: "Vectors", probability: 0.416, attempts: 5 }),
      masteryRow({ concept_id: "c6", concept_name: "Series", probability: 0.9, attempts: 7 }),
      masteryRow({ concept_id: "c2", concept_name: "Continuity", probability: 0.5, attempts: 1 }),
      masteryRow({ concept_id: "c5", concept_name: "Integrals", probability: 0.83, attempts: 2 }),
      masteryRow({ concept_id: "c3", concept_name: "Limits", probability: 0.61, attempts: 3 }),
    ];
    healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [persistedSession] })), [{ id: "course-1", title: "Calculus" }], mastery);
    renderHistory();

    const meters = await screen.findAllByRole("meter");
    expect(meters.map((meter) => meter.getAttribute("aria-label"))).toEqual(["Vectors", "Continuity", "Limits", "Derivatives", "Integrals", "Series"]);
    expect(screen.queryByRole("meter", { name: "Matrices" })).not.toBeInTheDocument();
    expect(screen.queryByRole("meter", { name: "Untouched prior" })).not.toBeInTheDocument();

    const weakest = meters[0]!;
    expect(weakest).toHaveAttribute("aria-valuemin", "0");
    expect(weakest).toHaveAttribute("aria-valuemax", "100");
    expect(weakest).toHaveAttribute("aria-valuenow", "42");
    expect(weakest).toHaveAttribute("aria-valuetext", "42% current mastery from 5 attempts");
    expect(weakest.firstElementChild).toHaveStyle(`width: ${0.416 * 100}%`);
    const weakestRow = weakest.closest("li")!;
    expect(within(weakestRow).getByText("Vectors")).toBeInTheDocument();
    expect(within(weakestRow).getByText("42%")).toBeInTheDocument();
    expect(within(weakestRow).getByText("5 attempts")).toBeInTheDocument();
    expect(within(meters[1]!.closest("li")!).getByText("1 attempt")).toBeInTheDocument();
  });

  it("filters the mastery snapshot to the selected course", async () => {
    const user = userEvent.setup();
    const listStudySessions = vi.fn(async (courseId: string) => ({ course_id: courseId, sessions: [] }));
    healthyState(listStudySessions, [{ id: "course-1", title: "Calculus" }, { id: "course-2", title: "Physics" }], [
      masteryRow({ concept_id: "c-cal", concept_name: "Eigenvectors", course_id: "course-1", probability: 0.4, attempts: 5 }),
      masteryRow({ concept_id: "c-phy", concept_name: "Momentum", course_id: "course-2", probability: 0.7, attempts: 3 }),
    ]);
    renderHistory();

    expect(await screen.findByRole("meter", { name: "Eigenvectors" })).toBeInTheDocument();
    expect(screen.queryByRole("meter", { name: "Momentum" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Study session course"), "course-2");
    expect(await screen.findByRole("meter", { name: "Momentum" })).toBeInTheDocument();
    expect(screen.queryByRole("meter", { name: "Eigenvectors" })).not.toBeInTheDocument();
  });

  it("hides the mastery snapshot when the course has only untouched priors", async () => {
    healthyState(vi.fn(async () => ({ course_id: "course-1", sessions: [persistedSession] })), [{ id: "course-1", title: "Calculus" }], [
      masteryRow({ concept_id: "p1", concept_name: "Eigenvectors", probability: 0.5, attempts: 0 }),
      masteryRow({ concept_id: "p2", concept_name: "Limits", probability: 0.5, attempts: 0 }),
    ]);
    renderHistory();

    expect(await screen.findByRole("heading", { name: "Study sessions" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Current mastery" })).not.toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });
});
