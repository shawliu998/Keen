import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { createLearningCoreClient, LearningCoreResponseError, type AutonomousStudySessionStartResponse, type LearningCoreClient, type LearningSnapshot } from "@keen/api-client";
import { LearningFeedPage } from "../src/features/feed/LearningFeedPage";
import { useAutonomousLearningFeed } from "../src/features/feed/useAutonomousLearningFeed";

const coreState = vi.hoisted(() => ({ current: null as never }));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => coreState.current,
  isLearningCoreStarting: () => false,
}));

const task = {
  id: "task-1", course_id: "course-1", concept_id: "concept-1", title: "Persisted limits task", reason: "Mastery is weak.",
  due_at: "2026-07-17T20:00:00+00:00", estimated_minutes: 15, status: "upcoming" as const,
  source_type: "weak_concept", source_id: "concept-1", priority_score: 0.8, recommended_reason: "Mastery is weak.",
  scheduled_for: null, created_at: "2026-07-17T10:00:00+00:00", updated_at: "2026-07-17T10:00:00+00:00",
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
  pending_tasks: [task], candidates: [candidate],
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current test route">{location.pathname}{location.search}</output>;
}

function renderFeed(client: (Pick<LearningCoreClient, "learningSnapshot" | "createAutonomousRecommendation"> & Partial<Pick<LearningCoreClient, "startAutonomousStudySession">>) | null, demo = false) {
  coreState.current = {
    status: demo ? "demo" : "healthy", client, connectionGeneration: 1,
    demoState: demo ? undefined : { courses: [{ id: "course-1", title: "Calculus", description: "", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null }, { id: "course-2", title: "Physics", description: "", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null }], tasks: [], mastery: [] },
    demoStatePending: false, demoStateError: null, errorKind: null, serviceMessage: null, retryError: null, retry: vi.fn(),
  } as never;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return Object.assign(
    render(<MemoryRouter initialEntries={["/feed"]}><QueryClientProvider client={queryClient}><LearningFeedPage /><LocationProbe /></QueryClientProvider></MemoryRouter>),
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
  it("renders a validated persisted snapshot and creates one task with an explicit result", async () => {
    const user = userEvent.setup();
    type CreatedResult = { outcome: "task_created"; course_id: string; snapshot: LearningSnapshot; task: typeof task; candidate: typeof candidate; bootstrap: null };
    let resolve!: (value: CreatedResult) => void;
    const createAutonomousRecommendation = vi.fn(() => new Promise<CreatedResult>((done) => { resolve = done; }));
    const client = { learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation };
    renderFeed(client);
    expect(await screen.findByText("Persisted limits task")).toBeInTheDocument();
    expect(screen.queryByText("Browser Demo")).not.toBeInTheDocument();
    const button = screen.getByRole("button", { name: /Plan next local action/i });
    fireEvent.click(button);
    expect(createAutonomousRecommendation).toHaveBeenCalledOnce();
    resolve({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: null });
    expect(await screen.findByText(/Keen created one local study task/i)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Select course for local learning feed"), "course-2");
    await waitFor(() => expect(client.learningSnapshot).toHaveBeenLastCalledWith({ courseId: "course-2", availableMinutes: 20 }, expect.anything()));
  });

  it("reports empty, unavailable, and demo without inventing a task", async () => {
    const user = userEvent.setup();
    const emptyClient = { learningSnapshot: vi.fn(async () => ({ ...snapshot, pending_tasks: [], candidates: [] })), createAutonomousRecommendation: vi.fn(async () => ({ outcome: "empty" as const, course_id: "course-1", snapshot: { ...snapshot, pending_tasks: [], candidates: [] }, task: null, candidate: null, bootstrap: null })) };
    const { unmount } = renderFeed(emptyClient);
    await user.click(await screen.findByRole("button", { name: /Plan next local action/i }));
    expect(await screen.findByText(/No eligible action was found/i)).toBeInTheDocument();
    unmount();
    const unavailable = { learningSnapshot: vi.fn(async () => snapshot), createAutonomousRecommendation: vi.fn(async () => { throw new LearningCoreResponseError(503, null, null); }) };
    renderFeed(unavailable);
    await user.click(await screen.findByRole("button", { name: /Plan next local action/i }));
    await waitFor(() => expect(unavailable.createAutonomousRecommendation).toHaveBeenCalledOnce());
    expect(await screen.findByText("Local recommendation service is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Plan next local action/i })).toBeDisabled();
    const unavailableSnapshotCalls = unavailable.learningSnapshot.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh feed" }));
    await waitFor(() => expect(unavailable.learningSnapshot.mock.calls.length).toBeGreaterThan(unavailableSnapshotCalls));
    await waitFor(() => expect(screen.queryByText("Local recommendation service is unavailable")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Plan next local action/i })).toBeEnabled();
    const demoClient = { learningSnapshot: vi.fn(), createAutonomousRecommendation: vi.fn() };
    renderFeed(demoClient, true);
    expect(screen.getByText("Browser Demo")).toBeInTheDocument();
    expect(demoClient.learningSnapshot).not.toHaveBeenCalled();
  });

  it("keeps self-consistent wrong-scope responses out of the snapshot cache", async () => {
    const poisonedTask = { ...task, course_id: "course-2", title: "Wrong-course task" };
    const poisonedSnapshot = { ...snapshot, course_id: "course-2", pending_tasks: [poisonedTask] };
    const snapshotFetch = vi.fn(async () => new Response(JSON.stringify(poisonedSnapshot), { status: 200, headers: { "Content-Type": "application/json" } }));
    const snapshotClient = createLearningCoreClient("http://127.0.0.1:8080", "a".repeat(64), snapshotFetch as unknown as typeof fetch);
    const snapshotView = renderFeed(snapshotClient);
    expect(await screen.findByText("Learning feed could not be validated", {}, { timeout: 3_000 })).toBeInTheDocument();
    expect(snapshotView.queryClient.getQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20])).toBeUndefined();
    snapshotView.unmount();

    const user = userEvent.setup();
    const responseFetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(snapshot), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ outcome: "task_created", course_id: "course-2", snapshot: poisonedSnapshot, task: poisonedTask, candidate, bootstrap: null }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const responseClient = createLearningCoreClient("http://127.0.0.1:8080", "a".repeat(64), responseFetch as unknown as typeof fetch);
    const responseView = renderFeed(responseClient);
    await user.click(await screen.findByRole("button", { name: /Plan next local action/i }));
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
    await user.click(await screen.findByRole("button", { name: /Plan next local action/i }));
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
    await screen.findByText("Persisted limits task");

    const plan = screen.getByRole("button", { name: /Plan next local action/i });
    act(() => {
      plan.click();
      plan.click();
    });
    expect(createAutonomousRecommendation).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: /Plan next local action/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Cancel recommendation/i }));
    expect(await screen.findByText("Recommendation request cancelled")).toBeInTheDocument();

    const snapshotCalls = learningSnapshot.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh feed" }));
    await waitFor(() => expect(learningSnapshot.mock.calls.length).toBeGreaterThan(snapshotCalls));
    await waitFor(() => expect(screen.queryByText("Recommendation request cancelled")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Plan next local action/i })).toBeEnabled();
    resolve({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: null });
    await waitFor(() => expect(screen.queryByText(/Keen created one local study task/i)).not.toBeInTheDocument());
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
    await user.click(await screen.findByRole("button", { name: /Plan next local action/i }));
    expect(await screen.findByText(/existing active local task already covers this action/i)).toBeInTheDocument();
    expect(screen.queryByText(/Keen created one local study task/i)).not.toBeInTheDocument();
    unmount();

    const unknownSnapshot = vi.fn()
      .mockResolvedValueOnce(snapshot)
      .mockRejectedValue(new Error("snapshot refresh failed"));
    const unknownClient = {
      learningSnapshot: unknownSnapshot,
      createAutonomousRecommendation: vi.fn(async () => { throw new Error("connection ended without a confirmed result"); }),
    };
    renderFeed(unknownClient);
    await user.click(await screen.findByRole("button", { name: /Plan next local action/i }));
    expect(await screen.findByText("Recommendation could not be confirmed")).toBeInTheDocument();
    expect(screen.getByText(/could not confirm whether a task was saved/i)).toBeInTheDocument();
    expect(screen.queryByText(/Keen created one local study task/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Plan next local action/i })).toBeDisabled();
    const unknownSnapshotCalls = unknownSnapshot.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh feed" }));
    await waitFor(() => expect(unknownSnapshot.mock.calls.length).toBeGreaterThan(unknownSnapshotCalls));
    expect(screen.getByText("Recommendation could not be confirmed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Plan next local action/i })).toBeDisabled();
  });

  it("does not render a replayed completed task as an active task", async () => {
    const user = userEvent.setup();
    const completedTask = { ...task, title: "Completed limits task", status: "completed" as const };
    const replaySnapshot = { ...snapshot, pending_tasks: [] };
    const client = {
      learningSnapshot: vi.fn(async () => replaySnapshot),
      createAutonomousRecommendation: vi.fn(async () => ({ outcome: "replay" as const, course_id: "course-1", snapshot: replaySnapshot, task: completedTask, candidate, bootstrap: null })),
    };
    renderFeed(client);

    await user.click(await screen.findByRole("button", { name: /Plan next local action/i }));
    expect(await screen.findByText(/already exists or was completed today/i)).toBeInTheDocument();
    expect(screen.getByText("No active local tasks")).toBeInTheDocument();
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
    const start = await screen.findByRole("button", { name: "Start / resume" });
    act(() => { start.click(); start.click(); });
    expect(startAutonomousStudySession).toHaveBeenCalledOnce();
    expect(screen.getByText("/feed")).toBeInTheDocument();
    resolve({ outcome: "session_created", course_id: "course-1", task: startTask, session, plan, blocked_reason: null, recovery_action: null });
    await waitFor(() => expect(screen.getByText("/deep-learn/session-1?course_id=course-1")).toBeInTheDocument());
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
    await user.click(await screen.findByRole("button", { name: "Start / resume" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Start / resume" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Recover start" }));
    expect(await screen.findByText("Local study service is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start / resume" })).toBeDisabled();
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
    await user.click(await screen.findByRole("button", { name: "Start / resume" }));
    expect(await screen.findByText("Study session could not be confirmed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Recover start" }));
    expect(await screen.findByText("Wait for indexing.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Recover start" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start / resume" })).toBeEnabled();
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
    await screen.findByText("Persisted limits task");
    fireEvent.click(screen.getByRole("button", { name: /Plan next local action/i }));
    await user.selectOptions(screen.getByLabelText("Select course for local learning feed"), "course-2");
    await waitFor(() => expect(screen.getByRole("button", { name: /Plan next local action/i })).toBeEnabled());
    const lateTask = { ...task, title: "Late task from old course" };
    const lateSnapshot = { ...snapshot, pending_tasks: [lateTask] };
    resolve({ outcome: "task_created", course_id: "course-1", snapshot: lateSnapshot, task: lateTask, candidate, bootstrap: null });

    await waitFor(() => expect(client.learningSnapshot).toHaveBeenLastCalledWith({ courseId: "course-2", availableMinutes: 20 }, expect.anything()));
    expect(screen.queryByText(/Keen created one local study task/i)).not.toBeInTheDocument();
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
    await screen.findByText("Persisted limits task");
    fireEvent.click(screen.getByRole("button", { name: /Plan next local action/i }));

    coreState.current = { ...(coreState.current as unknown as Record<string, unknown>), connectionGeneration: 2 } as never;
    view.rerender(<MemoryRouter><QueryClientProvider client={view.queryClient}><LearningFeedPage /></QueryClientProvider></MemoryRouter>);
    await screen.findByText("Generation two task");
    await waitFor(() => expect(screen.getByRole("button", { name: /Plan next local action/i })).toBeEnabled());
    const lateTask = { ...task, title: "Late task from old generation" };
    const lateSnapshot = { ...snapshot, pending_tasks: [lateTask] };
    resolve({ outcome: "task_created", course_id: "course-1", snapshot: lateSnapshot, task: lateTask, candidate, bootstrap: null });

    await waitFor(() => expect(screen.queryByText(/Keen created one local study task/i)).not.toBeInTheDocument());
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
