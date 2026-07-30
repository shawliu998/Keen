import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { createLearningCoreClient, LearningCoreResponseError, type AutonomousStudySession, type AutonomousStudySessionStartResponse, type LearningCoreClient, type LearningSnapshot } from "@keen/api-client";
import { LearningFeedPage } from "../src/features/feed/LearningFeedPage";
import { useAutonomousLearningFeed } from "../src/features/feed/useAutonomousLearningFeed";

const coreState = vi.hoisted(() => ({ current: null as never }));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => coreState.current,
  isLearningCoreStarting: (status: string) => ["starting", "binding", "migrating", "recovering", "starting_server", "health_checking", "restarting"].includes(status),
}));

const task = {
  id: "task-1", course_id: "course-1", concept_id: "concept-1", title: "Persisted limits task", reason: "Mastery is weak.",
  due_at: "2026-07-17T12:00:00+00:00", estimated_minutes: 15, status: "upcoming" as const,
  source_type: "weak_concept", source_id: "concept-1", priority_score: 0.8, recommended_reason: "Mastery is weak.",
  scheduled_for: null, created_at: "2026-07-17T10:00:00+00:00", updated_at: "2026-07-17T10:00:00+00:00",
  completed_at: null,
};
const candidate = {
  id: "concept:concept-1:study_very_weak_concept", action: "study_very_weak_concept" as const,
  target_type: "concept" as const, target_id: "concept-1", concept_id: "concept-1", component: "mastery", priority_tier: 3,
  estimated_minutes: 15, fits_available_minutes: true, priority_score: 0.8, priority_unclamped_score: 0.8,
  priority_algorithm_version: "keen-feed-priority/v1", priority_components: [], priority_explanation: [], why: "Mastery is weak.",
};
const snapshot: LearningSnapshot = {
  course_id: "course-1", as_of: "2026-07-17T10:00:00+00:00", available_minutes: 20,
  due_review_count: 0, incomplete_session_count: 0, mastery_gap_count: 0, misconception_count: 0,
  pending_tasks: [task], completed_tasks: [], candidates: [candidate],
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current test route">{location.pathname}{location.search}</output>;
}

function renderFeed(client: (Pick<LearningCoreClient, "learningSnapshot" | "createAutonomousRecommendation"> & Partial<Pick<LearningCoreClient, "listStudySessions" | "startAutonomousStudySession">>) | null, demo = false, initialEntry = "/feed") {
  coreState.current = {
    status: demo ? "demo" : "healthy", client, connectionGeneration: 1,
    demoState: demo ? undefined : { courses: [{ id: "course-1", title: "Calculus", description: "", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null }, { id: "course-2", title: "Physics", description: "", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null }], tasks: [], mastery: [] },
    demoStatePending: false, demoStateError: null, errorKind: null, serviceMessage: null, retryError: null, retry: vi.fn(),
  } as never;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return Object.assign(
    render(<MemoryRouter initialEntries={[initialEntry]}><QueryClientProvider client={queryClient}><LearningFeedPage /><LocationProbe /></QueryClientProvider></MemoryRouter>),
    { queryClient },
  );
}

function AvailableMinutesHarness({ client, availableMinutes }: { client: LearningCoreClient; availableMinutes: number }) {
  const feed = useAutonomousLearningFeed({ client, courseId: "course-1", availableMinutes, enabled: true, connectionGeneration: 1 });
  return <div>
    <button onClick={() => { void feed.createRecommendation(); }}>Start scoped recommendation</button>
    <span>{feed.recommendation.pending ? "recommendation pending" : "recommendation idle"}</span>
    <span>{feed.snapshot ? `snapshot ${feed.snapshot.available_minutes} minutes` : "snapshot loading"}</span>
  </div>;
}

describe("LearningFeedPage autonomous learning", () => {
  const taskPane = () => within(screen.getByRole("region", { name: "Learning tasks" }));

  it("opens the persisted task selected by a Home deep link", async () => {
    const client = { learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation: vi.fn() };
    const view = renderFeed(client, false, "/feed?task=task-1");

    expect(await screen.findByText("Expected steps")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Persisted limits task" })).toBeInTheDocument();
    expect(screen.queryByText("Review the learning goal")).not.toBeInTheDocument();
    const steps = [...view.container.querySelectorAll(".task-flow > li")];
    expect(steps.map((step) => step.querySelector("i")?.textContent)).toEqual(["1", "2"]);
  });

  it("shows the selected task's persisted session progress instead of calling it not started", async () => {
    const activeSession: AutonomousStudySession = {
      id: "session-1",
      course_id: "course-1",
      originating_task_id: "task-1",
      title: "Persisted limits task",
      mode: "study",
      goal: "Study limits.",
      estimated_minutes: 15,
      status: "studying",
      progress: 1 / 3,
      revision: 8,
      created_at: "2026-07-17T10:00:00+00:00",
      updated_at: "2026-07-17T11:00:00+00:00",
      started_at: "2026-07-17T10:02:00+00:00",
    };
    const listStudySessions = vi.fn(async () => ({
      course_id: "course-1",
      sessions: [activeSession],
    }));
    renderFeed({
      learningSnapshot: vi.fn(async () => snapshot),
      createAutonomousRecommendation: vi.fn(),
      listStudySessions,
    }, false, "/feed?task=task-1");

    expect(await screen.findByText("33% complete")).toBeInTheDocument();
    expect(screen.queryByText("Not started")).not.toBeInTheDocument();
    expect(listStudySessions).toHaveBeenCalledWith("course-1", expect.anything());
  });

  it("does not claim a task is unstarted when its session progress cannot be checked", async () => {
    renderFeed({
      learningSnapshot: vi.fn(async () => snapshot),
      createAutonomousRecommendation: vi.fn(),
      listStudySessions: vi.fn(async () => {
        throw new Error("session read failed");
      }),
    }, false, "/feed?task=task-1");

    expect(await screen.findByText("Unavailable", {}, { timeout: 3_000 })).toBeInTheDocument();
    expect(screen.queryByText("Not started")).not.toBeInTheDocument();
  });

  it("opens an exact persisted completion read-only from a completed deep link", async () => {
    const user = userEvent.setup();
    const completedTask = { ...task, id: "task-completed", title: "Completed limits task", status: "completed" as const, completed_at: "2026-07-17T21:00:00+00:00", updated_at: "2026-07-17T21:00:00+00:00" };
    const completedSnapshot: LearningSnapshot = { ...snapshot, pending_tasks: [], completed_tasks: [completedTask], candidates: [] };
    const startAutonomousStudySession = vi.fn();
    renderFeed({ learningSnapshot: vi.fn(async () => completedSnapshot), createAutonomousRecommendation: vi.fn(), startAutonomousStudySession }, false, "/feed?status=completed&task=task-completed&course_id=course-1");

    expect(await screen.findByRole("button", { name: "Completed" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("heading", { name: "Completed limits task" })).toBeInTheDocument();
    expect(screen.getByText(/saved task is read-only/i)).toBeInTheDocument();
    const completedLabel = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(completedTask.completed_at));
    expect(screen.getByText(completedLabel)).toBeInTheDocument();
    expect(screen.queryByText("Expected steps")).not.toBeInTheDocument();
    expect(screen.queryByText("Review the learning goal")).not.toBeInTheDocument();
    expect(screen.queryByText("Task completed")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start \/ resume/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Demo preview|Completed-state preview/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View History" }));
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/history?course_id=course-1");
    expect(startAutonomousStudySession).not.toHaveBeenCalled();
  });

  it("keeps overdue work in Today and separates only future work into Upcoming", async () => {
    const user = userEvent.setup();
    const todayTask = { ...task, id: "task-today", title: "Today task", due_at: "2026-07-17T12:00:00+00:00" };
    const upcomingTask = { ...task, id: "task-upcoming", title: "Upcoming task", due_at: "2026-07-18T08:00:00+00:00" };
    const overdueTask = { ...task, id: "task-overdue", title: "Overdue task", due_at: "2026-07-16T08:00:00+00:00", status: "overdue" as const };
    const overdueTodayTask = { ...task, id: "task-overdue-today", title: "Overdue today task", due_at: "2026-07-17T09:00:00+00:00", status: "overdue" as const };
    const datedSnapshot: LearningSnapshot = { ...snapshot, pending_tasks: [todayTask, upcomingTask, overdueTask, overdueTodayTask] };
    renderFeed({ learningSnapshot: vi.fn(async () => datedSnapshot), createAutonomousRecommendation: vi.fn() });
    const taskPane = within(screen.getByRole("region", { name: "Learning tasks" }));

    expect(await taskPane.findByText("Today task")).toBeInTheDocument();
    expect(taskPane.getByText("Overdue task")).toBeInTheDocument();
    expect(taskPane.getByText("Overdue today task")).toBeInTheDocument();
    expect(taskPane.queryByText("Upcoming task")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Overdue" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Upcoming" }));
    expect(taskPane.getByText("Upcoming task")).toBeInTheDocument();
    expect(taskPane.queryByText("Today task")).not.toBeInTheDocument();
    expect(taskPane.queryByText("Overdue task")).not.toBeInTheDocument();
  });

  it.each([
    ["UTC+8", "2026-07-17T10:00:00+08:00", "2026-07-17T20:00:00+08:00"],
    ["UTC-7", "2026-07-17T10:00:00-07:00", "2026-07-17T20:00:00-07:00"],
  ])("keeps a real %s recommendation due on that learner date in Today", async (zone, asOf, dueAt) => {
    const zonedTask = { ...task, id: `task-${zone}`, title: `${zone} recommendation`, due_at: dueAt };
    const zonedSnapshot: LearningSnapshot = { ...snapshot, as_of: asOf, pending_tasks: [zonedTask] };
    renderFeed({ learningSnapshot: vi.fn(async () => zonedSnapshot), createAutonomousRecommendation: vi.fn() });

    const taskPane = within(screen.getByRole("region", { name: "Learning tasks" }));
    expect(await taskPane.findByText(`${zone} recommendation`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps the validated course scope in the URL without dropping a task deep link", async () => {
    const user = userEvent.setup();
    const courseTwoSnapshot: LearningSnapshot = { ...snapshot, course_id: "course-2", pending_tasks: [], candidates: [] };
    const client = {
      learningSnapshot: vi.fn(async ({ courseId }: { courseId: string }) => courseId === "course-2" ? courseTwoSnapshot : snapshot),
      createAutonomousRecommendation: vi.fn(),
    };
    renderFeed(client, false, "/feed?task=task-1&course_id=course-2");

    expect(await screen.findByLabelText("Select course for learning feed")).toHaveValue("course-2");
    await waitFor(() => expect(client.learningSnapshot).toHaveBeenCalledWith({ courseId: "course-2", availableMinutes: 20 }, expect.anything()));
    expect(screen.queryByRole("heading", { name: "Persisted limits task" })).not.toBeInTheDocument();
    expect(screen.queryByText("Expected steps")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Select course for learning feed"), "course-1");
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/feed?task=task-1&course_id=course-1");
    expect(await screen.findByRole("heading", { name: "Persisted limits task" })).toBeInTheDocument();
  });

  it("fails closed when a linked course is stale", async () => {
    const client = { learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation: vi.fn() };
    renderFeed(client, false, "/feed?course_id=course-removed");

    expect(await screen.findByText("Selected course is unavailable")).toBeInTheDocument();
    expect(screen.getByLabelText("Select course for learning feed")).toHaveValue("");
    expect(client.learningSnapshot).not.toHaveBeenCalled();
  });

  it("renders a validated persisted snapshot and creates one task with an explicit result", async () => {
    const user = userEvent.setup();
    type CreatedResult = { outcome: "task_created"; course_id: string; snapshot: LearningSnapshot; task: typeof task; candidate: typeof candidate; bootstrap: null };
    let resolve!: (value: CreatedResult) => void;
    const createAutonomousRecommendation = vi.fn(() => new Promise<CreatedResult>((done) => { resolve = done; }));
    const client = { learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation };
    renderFeed(client);
    expect(await taskPane().findByText("Persisted limits task")).toBeInTheDocument();
    expect(taskPane().queryByText("Mastery is weak.")).not.toBeInTheDocument();
    expect(screen.queryByText("Browser Demo")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open task: Persisted limits task" }));
    expect(screen.getByText("Expected steps")).toBeInTheDocument();
    expect(screen.getByText(/Continue at the next saved learning step/i)).toBeInTheDocument();
    expect(screen.getByText(/below your current mastery target/i)).toBeInTheDocument();
    expect(screen.queryByText("Available evidence")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close details" }));
    const button = screen.getByRole("button", { name: /Find next task/i });
    fireEvent.click(button);
    expect(createAutonomousRecommendation).toHaveBeenCalledOnce();
    resolve({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: null });
    expect(await screen.findByText(/One local study task was created/i)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Select course for learning feed"), "course-2");
    await waitFor(() => expect(client.learningSnapshot).toHaveBeenLastCalledWith({ courseId: "course-2", availableMinutes: 20 }, expect.anything()));
  });

  it("reports empty, unavailable, and demo without inventing a task", async () => {
    const user = userEvent.setup();
    const emptyClient = { learningSnapshot: vi.fn(async () => ({ ...snapshot, pending_tasks: [], candidates: [] })), createAutonomousRecommendation: vi.fn(async () => ({ outcome: "empty" as const, course_id: "course-1", snapshot: { ...snapshot, pending_tasks: [], candidates: [] }, task: null, candidate: null, bootstrap: null })) };
    const { unmount } = renderFeed(emptyClient);
    await user.click(await screen.findByRole("button", { name: /Find next task/i }));
    expect(await screen.findByText(/No eligible action was found/i)).toBeInTheDocument();
    unmount();
    const unavailable = { learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation: vi.fn(async () => { throw new LearningCoreResponseError(503, null, null); }) };
    const unavailableView = renderFeed(unavailable);
    await user.click(await screen.findByRole("button", { name: /Find next task/i }));
    await waitFor(() => expect(unavailable.createAutonomousRecommendation).toHaveBeenCalledOnce());
    expect(await screen.findByText("Local recommendation service is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Find next task/i })).toBeDisabled();
    const unavailableSnapshotCalls = unavailable.learningSnapshot.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh feed" }));
    await waitFor(() => expect(unavailable.learningSnapshot.mock.calls.length).toBeGreaterThan(unavailableSnapshotCalls));
    await waitFor(() => expect(screen.queryByText("Local recommendation service is unavailable")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Find next task/i })).toBeEnabled();
    unavailableView.unmount();
    const demoClient = { learningSnapshot: vi.fn(), createAutonomousRecommendation: vi.fn() };
    renderFeed(demoClient, true);
    expect(screen.queryByText("Browser Demo")).not.toBeInTheDocument();
    expect(demoClient.learningSnapshot).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Upcoming" }));
    expect(screen.getByRole("button", { name: "Upcoming" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the calendar secondary and freezes its Demo date only for the explicit visual-test route", async () => {
    const user = userEvent.setup();
    renderFeed({ learningSnapshot: vi.fn(), createAutonomousRecommendation: vi.fn() }, true, "/feed?visualTest=true");
    const emptyDetail = screen.getByRole("region", { name: "Choose a task to continue" });
    expect(within(emptyDetail).queryByText("Learning goal")).not.toBeInTheDocument();
    expect(within(emptyDetail).queryByText("Steps and progress")).not.toBeInTheDocument();
    expect(within(emptyDetail).queryByText("Next action")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Learning task calendar" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    const fixedDay = screen.getByRole("gridcell", { name: "Sunday, July 19, 2026" });
    expect(within(fixedDay).getByText("19")).toBeInTheDocument();
    expect(within(fixedDay).getByRole("button", { name: "Show task: Review eigenvectors before Chapter 6" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to tasks" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Open calendar" })).toHaveFocus());
  });

  it("keeps restore geometry aligned with the task rail and context panel", () => {
    coreState.current = {
      status: "starting", client: null, connectionGeneration: 1, demoState: undefined,
      demoStatePending: false, demoStateError: null, errorKind: null, serviceMessage: null, retryError: null, retry: vi.fn(),
    } as never;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<MemoryRouter initialEntries={["/feed"]}><QueryClientProvider client={queryClient}><LearningFeedPage /></QueryClientProvider></MemoryRouter>);
    expect(screen.getByText("Restoring your learning queue")).toBeInTheDocument();
    expect(container.querySelectorAll(".feed-restore-rows > div")).toHaveLength(3);
    expect(screen.getByRole("heading", { name: "Choose a task to continue" })).toBeInTheDocument();
  });

  it("can render a deterministic selected-task visual fixture without changing live state", () => {
    renderFeed({ learningSnapshot: vi.fn(), createAutonomousRecommendation: vi.fn() }, true, "/feed?visualTest=true&selectedTask=t2");
    expect(screen.getByRole("heading", { level: 2, name: "Active recall: cellular respiration" })).toBeInTheDocument();
    expect(screen.queryByText(/changes reset when this browser session ends/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try demo task" })).toBeInTheDocument();
    expect(screen.getByText("Try the interaction. No learning progress will be saved.")).toBeInTheDocument();
    expect(screen.queryByText(/bundled task|deterministic browser|available evidence/i)).not.toBeInTheDocument();
  });

  it("keeps self-consistent wrong-scope responses out of the snapshot cache", async () => {
    const poisonedTask = { ...task, course_id: "course-2", title: "Wrong-course task" };
    const poisonedSnapshot = { ...snapshot, course_id: "course-2", pending_tasks: [poisonedTask] };
    const snapshotFetch = vi.fn(async () => new Response(JSON.stringify(poisonedSnapshot), { status: 200, headers: { "Content-Type": "application/json" } }));
    const snapshotClient = createLearningCoreClient("http://127.0.0.1:8080", "a".repeat(64), snapshotFetch as unknown as typeof fetch);
    const snapshotView = renderFeed(snapshotClient);
    expect(await screen.findByText("Learning queue could not be loaded", {}, { timeout: 3_000 })).toBeInTheDocument();
    expect(snapshotView.queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20])).toBeUndefined();
    snapshotView.unmount();

    const user = userEvent.setup();
    const responseFetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(snapshot), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ outcome: "task_created", course_id: "course-2", snapshot: poisonedSnapshot, task: poisonedTask, candidate, bootstrap: null }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const responseClient = createLearningCoreClient("http://127.0.0.1:8080", "a".repeat(64), responseFetch as unknown as typeof fetch);
    const responseView = renderFeed(responseClient);
    await user.click(await screen.findByRole("button", { name: /Find next task/i }));
    expect(await screen.findByText("Recommendation could not be confirmed")).toBeInTheDocument();
    expect(responseView.queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20])).toEqual(snapshot);
    expect(screen.queryByText("Wrong-course task")).not.toBeInTheDocument();
    responseView.unmount();

    const bootstrap = {
      course_id: "course-1", document_id: "document-1", concept_id: "concept-1", concept_name: "Limits",
      mastery_probability: 0.2, mastery_attempts: 0, concept_created: true, mastery_initialized: true,
      mastery_initialization_algorithm: "bootstrap/v1", mastery_initialization_algorithm_version: "1.0.0",
    };
    const emptySnapshot = { ...snapshot, pending_tasks: [], candidates: [] };
    const unexpectedBootstrapFetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(snapshot), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ outcome: "empty", course_id: "course-1", snapshot: emptySnapshot, task: null, candidate: null, bootstrap }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const unexpectedBootstrapClient = createLearningCoreClient("http://127.0.0.1:8080", "a".repeat(64), unexpectedBootstrapFetch as unknown as typeof fetch);
    const unexpectedBootstrapView = renderFeed(unexpectedBootstrapClient);
    await user.click(await screen.findByRole("button", { name: /Find next task/i }));
    expect(await screen.findByText("Recommendation could not be confirmed")).toBeInTheDocument();
    expect(unexpectedBootstrapView.queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20])).toEqual(snapshot);
  });

  it("keeps recommendation creation single-flight, cancels it, and refreshes persisted evidence", async () => {
    const user = userEvent.setup();
    type CreatedResult = { outcome: "task_created"; course_id: string; snapshot: LearningSnapshot; task: typeof task; candidate: typeof candidate; bootstrap: null };
    let resolve!: (value: CreatedResult) => void;
    const learningSnapshot = vi.fn(async () => snapshot);
    const createAutonomousRecommendation = vi.fn(() => new Promise<CreatedResult>((done) => { resolve = done; }));
    renderFeed({ learningSnapshot, createAutonomousRecommendation });
    await taskPane().findByText("Persisted limits task");

    const plan = screen.getByRole("button", { name: /Find next task/i });
    act(() => {
      plan.click();
      plan.click();
    });
    expect(createAutonomousRecommendation).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: /Find next task/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Cancel recommendation/i }));
    expect(await screen.findByText("Recommendation request cancelled")).toBeInTheDocument();

    const snapshotCalls = learningSnapshot.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh feed" }));
    await waitFor(() => expect(learningSnapshot.mock.calls.length).toBeGreaterThan(snapshotCalls));
    await waitFor(() => expect(screen.queryByText("Recommendation request cancelled")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Find next task/i })).toBeEnabled();
    resolve({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: null });
    await waitFor(() => expect(screen.queryByText(/One local study task was created/i)).not.toBeInTheDocument());
  });

  it("distinguishes covered and unknown recommendation results without claiming a new task", async () => {
    const user = userEvent.setup();
    const manualTask = { ...task, source_type: "manual", source_id: null };
    const coveredSnapshot = { ...snapshot, pending_tasks: [manualTask] };
    const coveredClient = {
      learningSnapshot: vi.fn(async () => coveredSnapshot),
      createAutonomousRecommendation: vi.fn(async () => ({ outcome: "covered_by_active_task" as const, course_id: "course-1", snapshot: coveredSnapshot, task: manualTask, candidate, bootstrap: null })),
    };
    const { unmount } = renderFeed(coveredClient);
    await user.click(await screen.findByRole("button", { name: /Find next task/i }));
    expect(await screen.findByText(/active task already covers this action/i)).toBeInTheDocument();
    expect(screen.queryByText(/One local study task was created/i)).not.toBeInTheDocument();
    unmount();

    const unknownSnapshot = vi.fn()
      .mockResolvedValueOnce(snapshot)
      .mockRejectedValue(new Error("snapshot refresh failed"));
    const unknownClient = {
      learningSnapshot: unknownSnapshot,
      createAutonomousRecommendation: vi.fn(async () => { throw new Error("connection ended without a confirmed result"); }),
    };
    renderFeed(unknownClient);
    await user.click(await screen.findByRole("button", { name: /Find next task/i }));
    expect(await screen.findByText("Recommendation could not be confirmed")).toBeInTheDocument();
    expect(screen.getByText(/could not confirm whether a task was saved/i)).toBeInTheDocument();
    expect(screen.queryByText(/One local study task was created/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Find next task/i })).toBeDisabled();
    const unknownSnapshotCalls = unknownSnapshot.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh feed" }));
    await waitFor(() => expect(unknownSnapshot.mock.calls.length).toBeGreaterThan(unknownSnapshotCalls));
    expect(screen.getByText("Recommendation could not be confirmed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Find next task/i })).toBeDisabled();
  });

  it("does not render a replayed completed task as an active task", async () => {
    const user = userEvent.setup();
    const completedTask = { ...task, title: "Completed limits task", status: "completed" as const, completed_at: "2026-07-17T21:00:00+00:00", updated_at: "2026-07-17T21:00:00+00:00" };
    const replaySnapshot = { ...snapshot, pending_tasks: [], completed_tasks: [completedTask] };
    const client = {
      learningSnapshot: vi.fn(async () => replaySnapshot),
      createAutonomousRecommendation: vi.fn(async () => ({ outcome: "replay" as const, course_id: "course-1", snapshot: replaySnapshot, task: completedTask, candidate, bootstrap: null })),
    };
    renderFeed(client);

    await user.click(await screen.findByRole("button", { name: /Find next task/i }));
    expect(await screen.findByText(/already exists or was completed today/i)).toBeInTheDocument();
    expect(screen.getByText("No today tasks")).toBeInTheDocument();
    expect(screen.queryByText("Completed limits task")).not.toBeInTheDocument();
  });

  it("starts a persisted task once and navigates only after a confirmed created session", async () => {
    const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Limits study", mode: "study" as const, goal: "Study limits.", estimated_minutes: 20, status: "goal_confirmation" as const, progress: 0, revision: 0, created_at: "2026-07-17T10:00:00+00:00", updated_at: "2026-07-17T10:00:00+00:00", started_at: null };
    const startTask = { id: "task-1", course_id: "course-1", concept_id: "concept-1", title: "Persisted limits task", reason: "Mastery is weak.", estimated_minutes: 15, status: "upcoming" as const, source_type: "weak_concept", source_id: "concept-1" };
    const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Use indexed evidence.", units: [
      { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"], title: "Part one", objective: "Read.", content: "Source one.", estimated_minutes: 10, status: "ready" as const },
      { id: "unit-2", ordinal: 1, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-2"], title: "Part two", objective: "Connect.", content: "Source two.", estimated_minutes: 10, status: "locked" as const },
    ] };
    let resolve!: (value: AutonomousStudySessionStartResponse) => void;
    const startAutonomousStudySession = vi.fn(() => new Promise<AutonomousStudySessionStartResponse>((done) => { resolve = done; }));
    renderFeed({ learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation: vi.fn(), startAutonomousStudySession });
    fireEvent.click(await screen.findByRole("button", { name: "Open task: Persisted limits task" }));
    const start = await screen.findByRole("button", { name: "Open study" });
    act(() => { start.click(); start.click(); });
    expect(startAutonomousStudySession).toHaveBeenCalledOnce();
    expect(screen.getByText("/feed")).toBeInTheDocument();
    resolve({ outcome: "session_created", course_id: "course-1", task: startTask, session, plan, blocked_reason: null, recovery_action: null });
    await waitFor(() => expect(screen.getByText("/deep-learn/session-1?course_id=course-1")).toBeInTheDocument());
  });

  it("opens a persisted review task in Review with exact course, item, and Feed identity", async () => {
    const user = userEvent.setup();
    const reviewTask = { ...task, id: "task-review-1", title: "Review the chain rule", source_type: "review", source_id: "review-1" };
    const reviewSnapshot: LearningSnapshot = { ...snapshot, pending_tasks: [reviewTask], candidates: [] };
    const startAutonomousStudySession = vi.fn();
    renderFeed({ learningSnapshot: vi.fn(async () => reviewSnapshot), createAutonomousRecommendation: vi.fn(), startAutonomousStudySession });

    await user.click(await screen.findByRole("button", { name: "Open task: Review the chain rule" }));
    expect(screen.queryByRole("button", { name: "Open study" })).not.toBeInTheDocument();
    expect(screen.getByText("Review the exact saved item that created this task.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review" }));

    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/review?course_id=course-1&review_item_id=review-1&task=task-review-1");
    expect(startAutonomousStudySession).not.toHaveBeenCalled();
  });

  it("keeps cancelled and 503 starts locked to an idempotent same-task recovery", async () => {
    const user = userEvent.setup();
    const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Limits study", mode: "study" as const, goal: "Study limits.", estimated_minutes: 20, status: "goal_confirmation" as const, progress: 0, revision: 0, created_at: "2026-07-17T10:00:00+00:00", updated_at: "2026-07-17T10:00:00+00:00", started_at: null };
    const startTask = { id: "task-1", course_id: "course-1", concept_id: "concept-1", title: "Persisted limits task", reason: "Mastery is weak.", estimated_minutes: 15, status: "upcoming" as const, source_type: "weak_concept", source_id: "concept-1" };
    const unresolved = new Promise(() => undefined);
    const startAutonomousStudySession = vi.fn()
      .mockReturnValueOnce(unresolved)
      .mockRejectedValueOnce(new LearningCoreResponseError(503, null, null))
      .mockResolvedValueOnce({ outcome: "resumed", course_id: "course-1", task: startTask, session, plan: null, blocked_reason: null, recovery_action: null });
    renderFeed({ learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation: vi.fn(), startAutonomousStudySession });
    await user.click(await screen.findByRole("button", { name: "Open task: Persisted limits task" }));
    await user.click(await screen.findByRole("button", { name: "Open study" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Open study" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Recover start" }));
    expect(await screen.findByText("Local study service is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open study" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Recover start" }));
    await waitFor(() => expect(screen.getByText("/deep-learn/session-1?course_id=course-1")).toBeInTheDocument());
    expect(startAutonomousStudySession).toHaveBeenCalledTimes(3);
    expect(startAutonomousStudySession.mock.calls.every((call) => call[0].task_id === "task-1")).toBe(true);
  });

  it("clears the uncertain lock only for a typed blocked recovery", async () => {
    const user = userEvent.setup();
    const startTask = { id: "task-1", course_id: "course-1", concept_id: "concept-1", title: "Persisted limits task", reason: "Mastery is weak.", estimated_minutes: 15, status: "upcoming" as const, source_type: "weak_concept", source_id: "concept-1" };
    const startAutonomousStudySession = vi.fn()
      .mockRejectedValueOnce(new Error("connection ended"))
      .mockResolvedValueOnce({ outcome: "blocked", course_id: "course-1", task: startTask, session: null, plan: null, blocked_reason: "no_indexed_source", recovery_action: "Wait for indexing." });
    renderFeed({ learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation: vi.fn(), startAutonomousStudySession });
    await user.click(await screen.findByRole("button", { name: "Open task: Persisted limits task" }));
    await user.click(await screen.findByRole("button", { name: "Open study" }));
    expect(await screen.findByText("Study session could not be confirmed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Recover start" }));
    expect(await screen.findByText("Wait for indexing.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Recover start" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open study" })).toBeEnabled();
  });

  it("ignores a late recommendation result after the course changes", async () => {
    const user = userEvent.setup();
    type CreatedResult = { outcome: "task_created"; course_id: string; snapshot: LearningSnapshot; task: typeof task; candidate: typeof candidate; bootstrap: null };
    let resolve!: (value: CreatedResult) => void;
    const createAutonomousRecommendation = vi.fn(() => new Promise<CreatedResult>((done) => { resolve = done; }));
    const courseTwoSnapshot: LearningSnapshot = { ...snapshot, course_id: "course-2", pending_tasks: [], candidates: [] };
    const client = {
      learningSnapshot: vi.fn(async ({ courseId }: { courseId: string }) => courseId === "course-1" ? snapshot : courseTwoSnapshot),
      createAutonomousRecommendation,
    };
    const view = renderFeed(client);
    await taskPane().findByText("Persisted limits task");
    fireEvent.click(screen.getByRole("button", { name: /Find next task/i }));
    await user.selectOptions(screen.getByLabelText("Select course for learning feed"), "course-2");
    await waitFor(() => expect(screen.getByRole("button", { name: /Find next task/i })).toBeEnabled());
    const lateTask = { ...task, title: "Late task from old course" };
    const lateSnapshot = { ...snapshot, pending_tasks: [lateTask] };
    resolve({ outcome: "task_created", course_id: "course-1", snapshot: lateSnapshot, task: lateTask, candidate, bootstrap: null });

    await waitFor(() => expect(client.learningSnapshot).toHaveBeenLastCalledWith({ courseId: "course-2", availableMinutes: 20 }, expect.anything()));
    expect(screen.queryByText(/One local study task was created/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Late task from old course")).not.toBeInTheDocument();
    expect(view.queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-2", 20])).toEqual(courseTwoSnapshot);
    expect(view.queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20])).toEqual(snapshot);
  });

  it("ignores a late recommendation result after the connection generation changes", async () => {
    type CreatedResult = { outcome: "task_created"; course_id: string; snapshot: LearningSnapshot; task: typeof task; candidate: typeof candidate; bootstrap: null };
    let resolve!: (value: CreatedResult) => void;
    const createAutonomousRecommendation = vi.fn(() => new Promise<CreatedResult>((done) => { resolve = done; }));
    const generationTask = { ...task, id: "task-generation-2", title: "Generation two task" };
    const generationSnapshot: LearningSnapshot = { ...snapshot, pending_tasks: [generationTask] };
    const learningSnapshot = vi.fn()
      .mockResolvedValueOnce(snapshot)
      .mockResolvedValueOnce(generationSnapshot);
    const client = { learningSnapshot, createAutonomousRecommendation };
    const view = renderFeed(client);
    await taskPane().findByText("Persisted limits task");
    fireEvent.click(screen.getByRole("button", { name: /Find next task/i }));

    coreState.current = { ...(coreState.current as unknown as Record<string, unknown>), connectionGeneration: 2 } as never;
    view.rerender(<MemoryRouter><QueryClientProvider client={view.queryClient}><LearningFeedPage /></QueryClientProvider></MemoryRouter>);
    await taskPane().findByText("Generation two task");
    await waitFor(() => expect(screen.getByRole("button", { name: /Find next task/i })).toBeEnabled());
    const lateTask = { ...task, title: "Late task from old generation" };
    const lateSnapshot = { ...snapshot, pending_tasks: [lateTask] };
    resolve({ outcome: "task_created", course_id: "course-1", snapshot: lateSnapshot, task: lateTask, candidate, bootstrap: null });

    await waitFor(() => expect(screen.queryByText(/One local study task was created/i)).not.toBeInTheDocument());
    expect(screen.queryByText("Late task from old generation")).not.toBeInTheDocument();
    expect(view.queryClient.getQueryData(["learning-core", "learning-snapshot", 2, "course-1", 20])).toEqual(generationSnapshot);
    expect(view.queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20])).toEqual(snapshot);
  });

  it("isolates recommendation state and cache when available minutes changes", async () => {
    type CreatedResult = { outcome: "task_created"; course_id: string; snapshot: LearningSnapshot; task: typeof task; candidate: typeof candidate; bootstrap: null };
    let resolve!: (value: CreatedResult) => void;
    const createAutonomousRecommendation = vi.fn(() => new Promise<CreatedResult>((done) => { resolve = done; }));
    const thirtyMinuteSnapshot: LearningSnapshot = { ...snapshot, available_minutes: 30 };
    const learningSnapshot = vi.fn(async ({ availableMinutes }: { availableMinutes: number }) => availableMinutes === 20 ? snapshot : thirtyMinuteSnapshot);
    const client = { learningSnapshot, createAutonomousRecommendation } as unknown as LearningCoreClient;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><AvailableMinutesHarness client={client} availableMinutes={20} /></QueryClientProvider>);
    await screen.findByText("snapshot 20 minutes");
    fireEvent.click(screen.getByRole("button", { name: "Start scoped recommendation" }));
    expect(screen.getByText("recommendation pending")).toBeInTheDocument();

    view.rerender(<QueryClientProvider client={queryClient}><AvailableMinutesHarness client={client} availableMinutes={30} /></QueryClientProvider>);
    expect(screen.getByText("recommendation idle")).toBeInTheDocument();
    await screen.findByText("snapshot 30 minutes");
    const lateSnapshot = { ...snapshot, pending_tasks: [{ ...task, title: "Late task for 20 minutes" }] };
    resolve({ outcome: "task_created", course_id: "course-1", snapshot: lateSnapshot, task: lateSnapshot.pending_tasks[0]!, candidate, bootstrap: null });

    await waitFor(() => expect(screen.getByText("recommendation idle")).toBeInTheDocument());
    expect(queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 30])).toEqual(thirtyMinuteSnapshot);
    expect(queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20])).toEqual(snapshot);
  });
});
