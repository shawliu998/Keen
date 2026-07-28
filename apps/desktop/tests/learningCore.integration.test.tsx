import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "../src/App";

const tauriMocks = vi.hoisted(() => ({
  isTauri: vi.fn(() => false),
  invoke: vi.fn(),
  listen: vi.fn(async () => vi.fn()),
}));

vi.mock("@tauri-apps/api/core", () => ({ isTauri: tauriMocks.isTauri, invoke: tauriMocks.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: tauriMocks.listen }));

const token = "b".repeat(64);
const connection = { available: true, port: 43123, baseUrl: "http://127.0.0.1:43123", token, status: "ready", phase: null, message: null };
const health = { status: "ok", service: "keen-learning-core", version: "0.1.0" };
const demoState = {
  courses: [{ id: "course-live", title: "Live Course", description: "From SQLite", created_at: "2026-07-01T09:00:00+00:00", concept_count: 1, average_mastery: 0.63 }],
  tasks: [{ id: "task-live", course_id: "course-live", course_title: "Live Course", title: "Live server task", reason: "Returned by the authenticated learning core.", due_at: "2026-07-14T09:00:00+00:00", estimated_minutes: 20, status: "overdue", concept_id: "concept-live", created_at: "2026-07-01T09:00:00+00:00", updated_at: "2026-07-14T09:00:00+00:00" }],
  mastery: [{ concept_id: "concept-live", course_id: "course-live", concept_name: "Live concept", probability: 0.63, attempts: 3, updated_at: "2026-07-14T09:00:00+00:00" }],
};
const documentRecord = { id: "doc-live", name: "Live Notes.txt", mimeType: "text/plain", sizeBytes: 42, contentHash: "d".repeat(64), status: "indexed", pageCount: 1, chunkCount: 2, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null, courseIds: ["course-live"], indexState: "indexed-lexical", embeddingStatus: "provider-missing", embeddingModel: null, embeddingError: null, retrievalWarning: "Local embeddings are not configured. Existing lexical search remains available.", providerConfigured: false };
const completedIndexJob = { id: "job-live", documentId: "doc-live", status: "completed", stage: "finalizing", progress: 100, cancelRequested: false, error: null, createdAt: "2026-07-15T12:00:00+00:00", updatedAt: "2026-07-15T12:01:00+00:00", startedAt: "2026-07-15T12:00:01+00:00", finishedAt: "2026-07-15T12:01:00+00:00", operation: "full_index" };
const queuedIndexJob = { ...completedIndexJob, id: "job-queued", status: "queued", stage: "queued", progress: 0, startedAt: null, finishedAt: null };
const liveFeedTask = {
  id: "task-live", course_id: "course-live", concept_id: "concept-live", title: "Live server task",
  reason: "Returned by the authenticated learning core.", due_at: "2026-07-14T09:00:00+00:00", estimated_minutes: 20,
  status: "overdue", source_type: "manual", source_id: null, priority_score: 0.8,
  recommended_reason: "Returned by the authenticated learning core.", scheduled_for: null,
  created_at: "2026-07-01T09:00:00+00:00", updated_at: "2026-07-14T09:00:00+00:00",
  completed_at: null,
};
const learningSnapshot = {
  course_id: "course-live", as_of: "2026-07-21T09:00:00+00:00", available_minutes: 20,
  due_review_count: 0, incomplete_session_count: 0, misconception_count: 0, mastery_gap_count: 0,
  pending_tasks: [liveFeedTask], completed_tasks: [], candidates: [],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderApp(route: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const view = render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
  return { ...view, queryClient };
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  tauriMocks.isTauri.mockReturnValue(false);
  tauriMocks.invoke.mockReset();
  tauriMocks.listen.mockClear();
  vi.unstubAllGlobals();
});

describe("learning-core runtime states", () => {
  it("uses an explicit browser Demo without invoking Tauri or fetching", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/feed");
    expect(within(screen.getByRole("region", { name: "Learning tasks" })).getByText("Review eigenvectors before Chapter 6")).toBeInTheDocument();
    expect(screen.getByLabelText("Browser Demo · no service calls")).toBeInTheDocument();
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["unavailable", "Learning queue unavailable"],
    ["loading", "Restoring your learning queue"],
    ["empty", "Build your first learning queue"],
    ["error", "Learning queue could not be loaded"],
  ])("renders the %s visual fixture without invoking Tauri or fetching", async (visualCoreState, expected) => {
    window.history.replaceState(null, "", `/?visualTest=true&visualCoreState=${visualCoreState}`);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/feed");
    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(screen.queryByText("Browser Demo")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Find next task" })).not.toBeInTheDocument();
    if (visualCoreState === "empty") expect(screen.queryByText("No today tasks")).not.toBeInTheDocument();
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps browser Knowledge imports as metadata-only Demo state", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderApp("/knowledge");
    await user.selectOptions(screen.getByLabelText("Course for imported document"), "demo-course-1");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    fireEvent.change(input!, { target: { files: [new File(["private contents"], "demo-only.txt", { type: "text/plain" })] } });

    expect(await screen.findByText(/Added demo-only\.txt.*under Linear Algebra.*No file was uploaded or indexed/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open source details: demo-only.txt" }));
    expect(screen.getAllByText("Sample").length).toBeGreaterThan(0);
    expect(screen.getByText(/Sample source organization only; no file or index exists/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Indexed$/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Unlink .*demo-only\.txt/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Grid" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Sample index metadata/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start learning" })).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Context inspector" })).not.toBeInTheDocument();
    expect(screen.getByText("Preview unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to Knowledge Base" })).toBeInTheDocument();
    expect(screen.getAllByText(/Browser Demo/i)).toHaveLength(1);
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("presents an empty live Knowledge Base as one first-source task", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse({ courses: [], tasks: [], mastery: [] });
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [] });
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/knowledge");

    expect(await screen.findByRole("heading", { name: "No sources yet" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Course libraries" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sources" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Search documents" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Import source" })).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Import source" }));
    expect(screen.getByRole("region", { name: "Import source" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close import" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "No sources yet" })).not.toBeInTheDocument();
  });

  it("hands one ready linked course from Knowledge Base to focused study", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.includes("/v1/learning-snapshot?")) return jsonResponse(learningSnapshot);
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/knowledge");

    await user.click(await screen.findByRole("button", { name: "Open source details: Live Notes.txt" }));
    expect(screen.queryByLabelText("Course for learning from Live Notes.txt")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start focused study" }));

    expect(await screen.findByRole("heading", { name: "Start a study session" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Learning source course")).toHaveValue("course-live"));
    expect(screen.getByLabelText("Learning source course")).toBeEnabled();
    expect(screen.queryByText(/indexed material available across this course/i)).not.toBeInTheDocument();
  });

  it("requires an explicit linked course when one indexed source belongs to several courses", async () => {
    const user = userEvent.setup();
    const multiCourseState = {
      ...demoState,
      courses: [...demoState.courses, { ...demoState.courses[0], id: "course-stats", title: "Statistics" }],
    };
    const multiCourseDocument = { ...documentRecord, courseIds: ["course-live", "course-stats"] };
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(multiCourseState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [multiCourseDocument] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.includes("/v1/learning-snapshot?")) return jsonResponse(learningSnapshot);
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/knowledge");

    await user.click(await screen.findByRole("button", { name: "Open source details: Live Notes.txt" }));
    const start = screen.getByRole("button", { name: "Start focused study" });
    const scope = screen.getByLabelText("Course for learning from Live Notes.txt");
    expect(scope).toHaveValue("");
    expect(start).toBeDisabled();
    await user.selectOptions(scope, "course-stats");
    await user.click(start);

    expect(await screen.findByRole("heading", { name: "Start a study session" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Learning source course")).toHaveValue("course-stats"));
  });

  it("does not offer Start learning for processing, failed, or unlinked sources", async () => {
    const user = userEvent.setup();
    const processing = { ...documentRecord, id: "doc-processing", name: "Processing.txt", status: "parsing", chunkCount: 0, indexState: null };
    const failed = { ...documentRecord, id: "doc-failed", name: "Failed.txt", status: "failed", chunkCount: 0, indexState: null };
    const unlinked = { ...documentRecord, id: "doc-unlinked", name: "Unlinked.txt", courseIds: [] };
    const runningJob = { ...queuedIndexJob, id: "job-processing", documentId: processing.id, status: "running", stage: "parsing", progress: 35, startedAt: "2026-07-15T12:00:01+00:00" };
    const failedJob = { ...completedIndexJob, id: "job-failed", documentId: failed.id, status: "failed", stage: "parsing", progress: 35, error: "Parsing failed" };
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/health")) return jsonResponse(health);
      if (url.pathname.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.pathname.endsWith("/v1/documents")) return jsonResponse({ documents: [processing, failed, unlinked] });
      if (url.pathname.endsWith("/v1/index-jobs")) {
        const documentId = url.searchParams.get("documentId");
        return jsonResponse({ jobs: documentId === processing.id ? [runningJob] : documentId === failed.id ? [failedJob] : [completedIndexJob] });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/knowledge");

    for (const name of [processing.name, failed.name, unlinked.name]) {
      await user.click(await screen.findByRole("button", { name: `Open source details: ${name}` }));
      expect(screen.queryByRole("button", { name: "Start learning" })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Back to Knowledge Base" }));
    }
  });

  it("keeps the collapsed Knowledge import controls out of the keyboard path", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn());
    const { container } = renderApp("/knowledge");
    const importButton = screen.getByRole("button", { name: "Add sample source" });
    const importPanel = container.querySelector("#knowledge-import-panel");
    expect(importButton).toHaveAttribute("aria-expanded", "false");
    expect(importPanel).toHaveClass("is-collapsed");
    importButton.focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Filter sources by Linear Algebra" })).toHaveFocus();

    await user.click(importButton);
    expect(importButton).toHaveAttribute("aria-expanded", "true");
    expect(importPanel).toHaveClass("is-open");
    expect(screen.getByLabelText("Course for imported document")).toBeVisible();
  });

  it("filters the source list from a course library card and restores all sources", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/knowledge");

    await user.click(screen.getByRole("button", { name: "Filter sources by Linear Algebra" }));
    expect(screen.getByRole("button", { name: "Show all sources instead of Linear Algebra" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Open source details: Linear Algebra — Chapter 5.pdf" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open source details: Cellular Respiration Notes.md" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show all sources instead of Linear Algebra" }));
    expect(screen.getByRole("button", { name: "Open source details: Cellular Respiration Notes.md" })).toBeInTheDocument();
  });

  it("shows unavailable in Tauri and never substitutes Demo tasks", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue({ available: false, port: null, baseUrl: null, token: null, status: "unavailable", phase: null, message: "The sidecar stopped after automatic recovery." });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/feed");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Learning queue unavailable");
    expect(alert).toHaveTextContent("Retry to reload your saved tasks.");
    expect(screen.queryByText("Review eigenvectors before Chapter 6")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["starting", "binding", "Restoring your learning queue"],
    ["starting", "migrating", "Restoring your learning queue"],
    ["starting", "recovering", "Restoring your learning queue"],
    ["starting", "starting_server", "Restoring your learning queue"],
    ["starting", "health_checking", "Restoring your learning queue"],
    ["restarting", null, "Restoring your learning queue"],
  ])("maps %s/%s sidecar state to startup UI", async (status, phase, expected) => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue({ available: false, port: null, baseUrl: null, token: null, status, phase, message: null });
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/feed");
    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("invokes one supervised restart when unavailable even after rapid repeated clicks", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    const unavailable = { available: false, port: null, baseUrl: null, token: null, status: "unavailable", phase: null, message: "The sidecar stopped after automatic recovery." };
    const binding = { ...unavailable, status: "starting", phase: "binding" };
    let resolveRestart!: (value: typeof binding) => void;
    const restartResponse = new Promise<typeof binding>((resolve) => { resolveRestart = resolve; });
    tauriMocks.invoke.mockImplementation(async (command: string) => command === "restart_sidecar" ? restartResponse : unavailable);
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/feed");

    const restart = await screen.findByRole("button", { name: "Retry" });
    fireEvent.click(restart);
    fireEvent.click(restart);
    expect(tauriMocks.invoke.mock.calls.filter(([command]) => command === "restart_sidecar")).toHaveLength(1);
    expect(tauriMocks.invoke).toHaveBeenCalledWith("restart_sidecar", { reason: "sidecar_unavailable" });

    resolveRestart(binding);
    await waitFor(() => expect(tauriMocks.invoke.mock.calls.filter(([command]) => command === "get_sidecar_connection").length).toBeGreaterThanOrEqual(2));
  });

  it("refetches ready-sidecar health without invoking a restart", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let healthAttempts = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        healthAttempts += 1;
        return healthAttempts <= 2 ? jsonResponse({ detail: "not ready" }, 503) : jsonResponse(health);
      }
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/feed");

    await user.click(await screen.findByRole("button", { name: "Retry" }, { timeout: 3_000 }));
    expect(await screen.findAllByText("Learning core ready")).toHaveLength(1);
    expect(healthAttempts).toBe(3);
    expect(tauriMocks.invoke).not.toHaveBeenCalledWith("restart_sidecar");
  });

  it("restarts after a repaired configuration and then rediscovers status", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    const configurationError = { available: false, port: null, baseUrl: null, token: null, status: "configuration_error", phase: null, message: "The configured learning-core runtime is unavailable." };
    const binding = { ...configurationError, status: "restarting", phase: "binding", message: null };
    let activeConnection: typeof configurationError | typeof binding = configurationError;
    tauriMocks.invoke.mockImplementation(async (command: string) => {
      if (command === "restart_sidecar") {
        activeConnection = binding;
        return binding;
      }
      return activeConnection;
    });
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/feed");

    expect(await screen.findByText("Learning queue needs attention")).toBeInTheDocument();
    expect(screen.getByText(/recovery guidance/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Restoring your learning queue")).toBeInTheDocument();
    await waitFor(() => expect(tauriMocks.invoke.mock.calls.filter(([command]) => command === "get_sidecar_connection").length).toBeGreaterThanOrEqual(2));
    expect(tauriMocks.invoke).toHaveBeenCalledWith("restart_sidecar", { reason: "configuration_recovered" });
  });

  it.each(["invoke", "schema"] as const)("surfaces a safe retry error when restart %s fails", async (failure) => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    const unavailable = { available: false, port: null, baseUrl: null, token: null, status: "unavailable", phase: null, message: "The local learning service is unavailable." };
    tauriMocks.invoke.mockImplementation(async (command: string) => {
      if (command !== "restart_sidecar") return unavailable;
      if (failure === "invoke") throw new Error("secret path: /Users/private/runtime");
      return { ...unavailable, phase: "not_a_real_phase" };
    });
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/feed");

    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/could not confirm the requested learning-core recovery/i)).toBeInTheDocument();
    expect(screen.queryByText(/Users\/private\/runtime/i)).not.toBeInTheDocument();
    expect(tauriMocks.invoke).toHaveBeenCalledWith("restart_sidecar", { reason: "sidecar_unavailable" });
    expect(tauriMocks.invoke.mock.calls.filter(([command]) => command === "get_sidecar_connection").length).toBeGreaterThanOrEqual(2);
  });

  it("refetches discovery errors without assuming that a restart is safe", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    const binding = { available: false, port: null, baseUrl: null, token: null, status: "starting", phase: "binding", message: null };
    let discoveryAttempts = 0;
    tauriMocks.invoke.mockImplementation(async (command: string) => {
      if (command === "restart_sidecar") throw new Error("Unexpected restart");
      discoveryAttempts += 1;
      if (discoveryAttempts === 1) throw new Error("Tauri IPC was temporarily unavailable");
      return binding;
    });
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/feed");

    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Restoring your learning queue")).toBeInTheDocument();
    expect(discoveryAttempts).toBe(2);
    expect(tauriMocks.invoke).not.toHaveBeenCalledWith("restart_sidecar");
  });

  it("renders authenticated live tasks and mastery instead of Demo state", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/learning-snapshot?")) return jsonResponse(learningSnapshot);
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/feed");
    expect(await within(screen.getByRole("region", { name: "Learning tasks" })).findByText("Live server task")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open task: Live server task" }));
    expect(screen.getByText("Returned by the authenticated learning core.")).toBeInTheDocument();
    expect(screen.queryByText("Revisit gradient descent")).not.toBeInTheDocument();
    expect(screen.getAllByText("Learning core ready")).toHaveLength(1);
  });

  it("routes the native new-conversation menu event to the source-first Home Ask entry", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/learning-snapshot?")) return jsonResponse(learningSnapshot);
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/settings");

    await waitFor(() => expect(tauriMocks.listen).toHaveBeenCalledWith("keen://menu", expect.any(Function)));
    const listenCalls = tauriMocks.listen.mock.calls as unknown as Array<[
      string,
      (event: { payload: string }) => void,
    ]>;
    const menuHandler = listenCalls.find(([event]) => event === "keen://menu")?.[1];
    expect(menuHandler).toBeDefined();
    act(() => menuHandler?.({ payload: "new-conversation" }));

    expect(await screen.findByRole("heading", { name: "What shall we explore?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask sources mode" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByLabelText("Question source scope")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter a question about your course…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask sources" })).toBeInTheDocument();
  });

  it("rediscovers rotated sidecar credentials after a supervised restart", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    const restartedConnection = {
      ...connection,
      token: "c".repeat(64),
    };
    const recoveredState = {
      ...demoState,
      tasks: [{ ...demoState.tasks[0], id: "task-recovered", title: "Recovered server task" }],
    };
    const recoveredSnapshot = { ...learningSnapshot, pending_tasks: [{ ...liveFeedTask, id: "task-recovered", title: "Recovered server task" }] };
    let activeConnection = connection;
    tauriMocks.invoke.mockImplementation(async () => activeConnection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) {
        const authorization = new Headers(init?.headers).get("Authorization");
        return jsonResponse(authorization === `Bearer ${restartedConnection.token}` ? recoveredState : demoState);
      }
      if (url.includes("/v1/learning-snapshot?")) {
        const authorization = new Headers(init?.headers).get("Authorization");
        return jsonResponse(authorization === `Bearer ${restartedConnection.token}` ? recoveredSnapshot : learningSnapshot);
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderApp("/feed");
    expect(await within(screen.getByRole("region", { name: "Learning tasks" })).findByText("Live server task")).toBeInTheDocument();

    activeConnection = restartedConnection;
    expect(await within(screen.getByRole("region", { name: "Learning tasks" })).findByText("Recovered server task", undefined, { timeout: 4_500 })).toBeInTheDocument();
    expect(tauriMocks.invoke.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("tests a saved provider only through the replacement sidecar client", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    const restartedConnection = {
      ...connection,
      port: 43124,
      baseUrl: "http://127.0.0.1:43124",
      token: "c".repeat(64),
    };
    const restartingConnection = {
      available: false,
      port: null,
      baseUrl: null,
      token: null,
      status: "restarting",
      phase: "binding",
      message: null,
    };
    let providerConfiguration = {
      configured: true,
      provider: "ollama",
      endpoint: "http://127.0.0.1:11434",
      model: "old-model",
      apiKeyConfigured: false,
    };
    let restartRequested = false;
    let postSaveDiscoveries = 0;
    tauriMocks.invoke.mockImplementation(async (command: string, arguments_: unknown) => {
      if (command === "get_provider_configuration") return providerConfiguration;
      if (command === "save_provider_configuration") {
        expect(arguments_).toEqual({
          configuration: {
            provider: "ollama",
            endpoint: "http://127.0.0.1:11434",
            model: "new-model",
          },
          apiKey: null,
        });
        providerConfiguration = { ...providerConfiguration, model: "new-model" };
        restartRequested = true;
        return restartingConnection;
      }
      if (command === "get_sidecar_connection") {
        if (!restartRequested) return connection;
        postSaveDiscoveries += 1;
        return postSaveDiscoveries === 1
          ? restartingConnection
          : restartedConnection;
      }
      throw new Error(`Unexpected Tauri command: ${command}`);
    });
    const testedAuthorizations: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const authorization = new Headers(init?.headers).get("Authorization");
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/provider/test")) {
        testedAuthorizations.push(authorization ?? "");
        return jsonResponse({
          status: "connected",
          provider: "ollama",
          model: "new-model",
          detail: "Connected",
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderApp("/settings");
    await user.click(screen.getByRole("button", { name: "Model" }));
    const modelInput = screen.getByRole("textbox", { name: "Model" });
    await waitFor(() => expect(modelInput).toHaveValue("old-model"));
    await user.clear(modelInput);
    await user.type(modelInput, "new-model");
    await user.click(screen.getByRole("button", { name: "Save and verify" }));

    await waitFor(
      () => expect(postSaveDiscoveries).toBeGreaterThanOrEqual(1),
      { timeout: 3_500 },
    );
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();
    expect(await screen.findByText(
      "Connected ollama · new-model",
      {},
      { timeout: 4_500 },
    )).toBeInTheDocument();
    expect(testedAuthorizations).toEqual([
      `Bearer ${restartedConnection.token}`,
    ]);
  }, 10_000);

  it("shows bounded import failure details and non-retryable recovery guidance", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.endsWith("/v1/documents/import")) {
        return new Response(JSON.stringify({
          detail: {
            message: "the PDF is encrypted",
            retryable: false,
            recovery: "Export an unencrypted copy before importing.",
          },
        }), {
          status: 422,
          headers: { "Content-Type": "application/json", "X-Request-ID": "import-request-1" },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    const { container } = renderApp("/knowledge");
    expect(await screen.findByText("Live Notes.txt")).toBeInTheDocument();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    fireEvent.change(input!, { target: { files: [new File(["pdf"], "locked.pdf", { type: "application/pdf" })] } });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("the PDF is encrypted");
    expect(alert).toHaveTextContent("Export an unencrypted copy before importing");
    expect(alert).toHaveTextContent("Do not retry the unchanged file");
    expect(alert).toHaveTextContent("import-request-1");
  });

  it("does not claim that retrying a rejected search is safe", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.endsWith("/v1/search")) {
        return new Response(JSON.stringify({ detail: {
          message: "search must contain a letter or number",
          retryable: false,
          recovery: "Enter at least one searchable term.",
        } }), {
          status: 422,
          headers: { "Content-Type": "application/json", "X-Request-ID": "search-request-1" },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderApp("/knowledge");
    await user.type(await screen.findByRole("textbox", { name: "Search documents" }), "???");
    const alert = await screen.findByRole("alert", undefined, { timeout: 3_000 });
    expect(alert).toHaveTextContent("search must contain a letter or number");
    expect(alert).toHaveTextContent("Enter at least one searchable term");
    expect(alert).toHaveTextContent("search-request-1");
    expect(alert).not.toHaveTextContent(/retrying is safe/i);
    expect(screen.queryByRole("button", { name: "Try search again" })).not.toBeInTheDocument();
  });

  it("searches live indexed text and refreshes documents after upload", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let documentLoads = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents") && !url.endsWith("/import")) { documentLoads += 1; return jsonResponse({ documents: [documentRecord] }); }
      if (url.endsWith("/v1/search")) return jsonResponse({ query: "eigen", mode: "lexical_only", warning: "Vector retrieval is unavailable; results use lexical search only. Reason: a local embedding provider is not configured", results: [{ chunkId: "chunk-1", chunkIds: ["chunk-1"], documentId: "doc-live", documentName: "Live Notes.txt", pageNumber: 1, pageEnd: 1, sectionPath: ["Vectors"], text: "An eigenvector preserves its direction.", score: 0.9 }] });
      if (url.endsWith("/v1/documents/import")) {
        expect((init?.body as FormData).get("course_id")).toBe("course-live");
        return jsonResponse({ document: { ...documentRecord, status: "queued" }, job: queuedIndexJob, duplicate: false, linked: true }, 202);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderApp("/knowledge");
    expect(await screen.findByText("Live Notes.txt")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Search documents" }), "eigen");
    expect(await screen.findByText("An eigenvector preserves its direction.")).toBeInTheDocument();
    expect(screen.getByText("Lexical-only indexed text results")).toBeInTheDocument();
    expect(screen.getByText(/local embedding provider is not configured/i)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Course for imported document"), "course-live");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input!, { target: { files: [new File(["note"], "upload.txt", { type: "text/plain" })] } });
    expect(await screen.findByText(/accepted as indexing job job-queued/i)).toBeInTheDocument();
    expect(screen.getByText(/selected course was linked/i)).toBeInTheDocument();
    await waitFor(() => expect(documentLoads).toBeGreaterThanOrEqual(2));
  });

  it("creates a local course and selects it as the next document-import course", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const createdCourse = { id: "course-created", title: "Calculus", description: "Limits", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null };
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/courses") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual(expect.objectContaining({ title: "Calculus", description: "Limits", idempotencyKey: expect.any(String) }));
        return jsonResponse({ course: createdCourse, replayed: false }, 201);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { queryClient } = renderApp("/knowledge");

    await screen.findByText("Live Notes.txt");
    await user.type(screen.getByLabelText("Course title"), "Calculus");
    await user.type(screen.getByLabelText("Course description"), "Limits");
    await user.click(screen.getByRole("button", { name: "Create course" }));
    expect(await screen.findByText(/Created “Calculus” and selected it for the next import/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Course for imported document")).toHaveValue("course-created");
    expect(screen.getAllByRole("option", { name: "Calculus" }).length).toBeGreaterThan(0);
    const courseState = queryClient.getQueryCache().findAll({ queryKey: ["learning-core", "demo-state"] })
      .map((query) => query.state.data as typeof demoState | undefined)
      .find((state) => state?.courses.some((course) => course.id === "course-created"));
    expect(courseState?.courses).toContainEqual(createdCourse);
  });

  it("aborts a course create when credentials rotate and ignores a late response from the old connection", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    const rotatedConnection = { ...connection, token: "c".repeat(64) };
    const rotatedState = {
      ...demoState,
      courses: [{ ...demoState.courses[0], id: "course-rotated", title: "Rotated Course" }],
    };
    const createdCourse = { id: "course-created", title: "Calculus", description: "Limits", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null };
    let activeConnection = connection;
    let resolveCreate!: (response: Response) => void;
    let createSignal: AbortSignal | undefined;
    tauriMocks.invoke.mockImplementation(async () => activeConnection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) {
        const authorization = new Headers(init?.headers).get("Authorization");
        return jsonResponse(authorization === `Bearer ${rotatedConnection.token}` ? rotatedState : demoState);
      }
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/courses") && init?.method === "POST") {
        createSignal = init.signal as AbortSignal | undefined;
        return new Promise<Response>((resolve) => { resolveCreate = resolve; });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    const { queryClient } = renderApp("/knowledge");

    await screen.findByText("Live Notes.txt");
    await user.type(screen.getByLabelText("Course title"), "Calculus");
    await user.click(screen.getByRole("button", { name: "Create course" }));
    await waitFor(() => expect(createSignal).toBeDefined());

    activeConnection = rotatedConnection;
    await waitFor(() => expect(createSignal?.aborted).toBe(true), { timeout: 4_500 });
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Rotated Course" }).length).toBeGreaterThan(0), { timeout: 4_500 });

    resolveCreate(jsonResponse({ course: createdCourse, replayed: false }, 201));
    await waitFor(() => expect(screen.queryByRole("option", { name: "Calculus" })).not.toBeInTheDocument());
    expect(screen.getByLabelText("Course for imported document")).toHaveValue("");
    const states = queryClient.getQueryCache().findAll({ queryKey: ["learning-core", "demo-state"] })
      .map((query) => query.state.data as typeof demoState | undefined);
    expect(states.some((state) => state?.courses.some((course) => course.id === "course-rotated"))).toBe(true);
    expect(states.some((state) => state?.courses.some((course) => course.id === createdCourse.id))).toBe(false);
  }, 10_000);

  it.each([
    [
      "provider missing",
      { indexState: "indexed-lexical", embeddingStatus: "provider-missing", embeddingModel: null, embeddingError: null, retrievalWarning: "Local embeddings are not configured. Existing lexical search remains available.", providerConfigured: false },
      "Text indexed",
      /Local embeddings are not configured/i,
    ],
    [
      "provider failure",
      { indexState: "indexed-lexical", embeddingStatus: "provider-failure", embeddingModel: "ollama: fixture@v1 (3 dimensions)", embeddingError: "local embedding provider is unavailable; lexical indexing completed", retrievalWarning: "Embedding failed for this source. Its lexical index remains available; retry indexing after the local provider recovers.", providerConfigured: true },
      "Text indexed",
      /local embedding provider is unavailable/i,
    ],
    [
      "model change",
      { indexState: "needs-reindex", embeddingStatus: "needs-reindex", embeddingModel: "ollama: fixture@v2 (3 dimensions)", embeddingError: null, retrievalWarning: "This source has no embeddings for the configured model. Lexical search remains available until it is reindexed.", providerConfigured: true },
      "Needs reindex",
      /no embeddings for the configured model/i,
    ],
  ] as const)("shows the real %s document capability state", async (_name, capability, label, warning) => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [{ ...documentRecord, ...capability }] });
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderApp("/knowledge");
    expect(await screen.findByText(label)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Open source details: Live Notes.txt" }));
    expect(screen.getAllByText(warning).length).toBeGreaterThan(0);
  });

  it("queues the real embedding-only reindex action while stating lexical availability", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const needsReindex = { ...documentRecord, indexState: "needs-reindex", embeddingStatus: "needs-reindex", embeddingModel: "ollama: fixture@v2 (3 dimensions)", retrievalWarning: "This source has no embeddings for the configured model. Lexical search remains available until it is reindexed.", providerConfigured: true };
    const reindexJob = { ...queuedIndexJob, operation: "embedding_reindex", stage: "embedding" };
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [needsReindex] });
      if (url.endsWith("/v1/documents/doc-live/embedding-reindex")) return jsonResponse({ document: needsReindex, job: reindexJob }, 202);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/knowledge");
    await user.click(await screen.findByRole("button", { name: "Open source details: Live Notes.txt" }));
    await user.click(screen.getByRole("button", { name: "Reindex embeddings" }));
    expect(await screen.findByText(/existing lexical index remains available/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reindex embeddings" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel indexing" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/v1/documents/doc-live/embedding-reindex"))).toBe(true);
  });

  it("does not offer a fake reindex call when the provider is missing", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderApp("/knowledge");
    await screen.findByText("Text indexed");
    expect(screen.queryByRole("button", { name: "Reindex embeddings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Provider required" })).not.toBeInTheDocument();
  });

  it("does not claim a reused document identity created no indexing job", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents") && !url.endsWith("/import")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents/import")) return jsonResponse({
        document: { ...documentRecord, status: "queued" },
        job: { ...queuedIndexJob, stage: "stored", progress: 10 },
        duplicate: true,
        linked: false,
      }, 202);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderApp("/knowledge");
    await screen.findByRole("button", { name: "Open source details: Live Notes.txt" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Import source" }));

    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    fireEvent.change(input!, { target: { files: [new File(["note"], "repair.txt", { type: "text/plain" })] } });

    expect(await screen.findByText(/reused its existing document record and content identity/i)).toBeInTheDocument();
    expect(screen.queryByText(/no duplicate file or indexing job was created/i)).not.toBeInTheDocument();
  });

  it("links one document to multiple courses, filters it, and unlinks without deleting it", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const courseState = {
      ...demoState,
      courses: [...demoState.courses, { id: "course-stats", title: "Statistics", description: "Second course", created_at: "2026-07-02T09:00:00+00:00", concept_count: 0, average_mastery: null }],
    };
    let currentDocument = documentRecord;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(courseState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [currentDocument] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents/doc-live/courses/course-stats") && init?.method === "POST") {
        currentDocument = { ...currentDocument, courseIds: ["course-live", "course-stats"] };
        return jsonResponse({ document: currentDocument, linked: true });
      }
      if (url.endsWith("/v1/documents/doc-live/courses/course-live") && init?.method === "DELETE") {
        currentDocument = { ...currentDocument, courseIds: ["course-stats"] };
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/knowledge");

    await user.click(await screen.findByRole("button", { name: "Open source details: Live Notes.txt" }));
    await user.click(screen.getByText("Source settings"));
    const linkSelect = screen.getByLabelText("Course to link to Live Notes.txt");
    await user.selectOptions(linkSelect, "course-stats");
    await user.click(screen.getByRole("button", { name: "Link course" }));
    expect(await screen.findByRole("button", { name: "Unlink Statistics from Live Notes.txt" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to Knowledge Base" }));
    await user.selectOptions(screen.getByLabelText("Filter documents by course"), "course-stats");
    expect(screen.getAllByText("Live Notes.txt").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Open source details: Live Notes.txt" }));
    await user.click(screen.getByRole("button", { name: "Unlink Live Course from Live Notes.txt" }));
    expect(await screen.findByText(/document and index were retained/i)).toBeInTheDocument();
    expect(screen.getAllByText("Live Notes.txt").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Back to Knowledge Base" }));
    await user.selectOptions(screen.getByLabelText("Filter documents by course"), "course-live");
    expect(await screen.findByText("No matching sources")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/v1/documents/doc-live") && (init as RequestInit | undefined)?.method === "DELETE")).toBe(false);
  });

  it("shows real persisted job stage/progress and requests cancellation at a server boundary", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const queuedStored = { ...completedIndexJob, status: "queued", stage: "stored", progress: 20, startedAt: null, finishedAt: null };
    const runningJob = { ...completedIndexJob, status: "running", stage: "lexical_indexing", progress: 64, finishedAt: null };
    const cancelRequested = { ...runningJob, status: "cancel_requested", cancelRequested: true };
    let jobLoads = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [{ ...documentRecord, status: "parsing" }] });
      if (url.includes("/v1/index-jobs?documentId=")) { jobLoads += 1; return jsonResponse({ jobs: [jobLoads === 1 ? queuedStored : runningJob] }); }
      if (url.endsWith("/v1/index-jobs/job-live/cancel") && init?.method === "POST") return jsonResponse(cancelRequested);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/knowledge");

    expect(await screen.findByText("Queued · Stored")).toBeInTheDocument();
    expect(screen.getByLabelText("Live Notes.txt indexing progress 20%")).toBeInTheDocument();
    expect(await screen.findByText("Indexing text", undefined, { timeout: 3_500 })).toBeInTheDocument();
    expect(screen.getByLabelText("Live Notes.txt indexing progress 64%")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open source details: Live Notes.txt" }));
    await user.click(screen.getByRole("button", { name: "Cancel indexing" }));
    expect(await screen.findByText(/worker will stop at a safe boundary/i)).toBeInTheDocument();
    expect((await screen.findAllByText("Cancel requested")).length).toBeGreaterThan(0);
    const cancelCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/v1/index-jobs/job-live/cancel"));
    expect((cancelCall?.[1] as RequestInit).method).toBe("POST");
  });

  it.each([
    {
      returnedJob: completedIndexJob,
      expected: /had already completed; no cancellation was applied/i,
      rejected: /worker will stop at a safe boundary|cancelled before it started/i,
    },
    {
      returnedJob: { ...completedIndexJob, status: "cancelled", error: "indexing was cancelled by the user" },
      expected: /stopped after the cancellation request reached a safe boundary/i,
      rejected: /cancelled before it started/i,
    },
  ])("reports the returned terminal cancel state without overstating cancellation", async ({ returnedJob, expected, rejected }) => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const runningJob = { ...completedIndexJob, status: "running", stage: "lexical_indexing", progress: 80, finishedAt: null };
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [{ ...documentRecord, status: "parsing" }] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [runningJob] });
      if (url.endsWith("/v1/index-jobs/job-live/cancel") && init?.method === "POST") return jsonResponse(returnedJob);
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/knowledge");

    await user.click(await screen.findByRole("button", { name: "Open source details: Live Notes.txt" }));
    await user.click(screen.getByRole("button", { name: "Cancel indexing" }));
    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(screen.queryByText(rejected)).not.toBeInTheDocument();
  });

  it("keeps document metadata visible when job polling fails and offers a separate retry", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ detail: "temporarily unavailable" }, 503);
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/knowledge");

    await screen.findByRole("button", { name: "Open source details: Live Notes.txt" });
    const alert = await screen.findByRole("alert", undefined, { timeout: 3_000 });
    expect(alert).toHaveTextContent(/progress and actions may be incomplete/i);
    expect(screen.getByRole("button", { name: "Retry job status" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel indexing" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry indexing" })).not.toBeInTheDocument();
  });

  it("retries interrupted jobs and confirms destructive document deletion", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const interruptedJob = { ...completedIndexJob, status: "interrupted", stage: "chunking", progress: 42, error: "The previous worker stopped.", finishedAt: null };
    const retriedDocument = { ...documentRecord, status: "queued", error: null };
    const retriedJob = { ...queuedIndexJob, id: "job-retry" };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents/doc-live/retry") && init?.method === "POST") return jsonResponse({ document: retriedDocument, job: retriedJob }, 202);
      if (url.endsWith("/v1/documents/doc-live") && init?.method === "DELETE") return new Response(null, { status: 204 });
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [interruptedJob] });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/knowledge");

    expect(await screen.findByText("Interrupted")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open source details: Live Notes.txt" }));
    expect(screen.queryByLabelText("Live Notes.txt indexing progress 42%")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry indexing" }));
    expect(await screen.findByText(/new indexing job was queued/i)).toBeInTheDocument();
    await user.click(screen.getByText("Source settings"));
    await user.click(screen.getByRole("button", { name: "Delete source" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringMatching(/cannot be undone/i));
    expect(await screen.findByText(/and its local indexing data were deleted/i)).toBeInTheDocument();
    expect(await screen.findByText("No sources yet")).toBeInTheDocument();
  });

  it("removes stale caches and reports incomplete cleanup after a partially successful delete", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let documentLoads = 0;
    let jobLoads = 0;
    let deleteCommitted = false;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents/doc-live") && init?.method === "DELETE") {
        deleteCommitted = true;
        return jsonResponse({
          detail: "document record was deleted, but quarantined source cleanup failed; restart Keen to retry maintenance",
        }, 500);
      }
      if (url.endsWith("/v1/documents")) { documentLoads += 1; return jsonResponse({ documents: deleteCommitted ? [] : [documentRecord] }); }
      if (url.includes("/v1/index-jobs?documentId=")) { jobLoads += 1; return jsonResponse({ jobs: [completedIndexJob] }); }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/knowledge");

    await user.click(await screen.findByRole("button", { name: "Open source details: Live Notes.txt" }));
    await user.click(screen.getByText("Source settings"));
    await user.click(screen.getByRole("button", { name: "Delete source" }));
    expect(await screen.findByText(/record and index data.*were deleted, but local source cleanup is incomplete/i)).toBeInTheDocument();
    expect(await screen.findByText("No sources yet")).toBeInTheDocument();
    await waitFor(() => {
      expect(documentLoads).toBeGreaterThanOrEqual(2);
      expect(jobLoads).toBeGreaterThanOrEqual(2);
    });
    expect(screen.queryByText(/Delete document failed/i)).not.toBeInTheDocument();
  });

  it("distinguishes stopping an upload request from cancelling an accepted server job", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents")) return jsonResponse({ documents: [documentRecord] });
      if (url.includes("/v1/index-jobs?documentId=")) return jsonResponse({ jobs: [completedIndexJob] });
      if (url.endsWith("/v1/documents/import")) return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderApp("/knowledge");
    await screen.findByRole("button", { name: "Open source details: Live Notes.txt" });
    await user.click(screen.getByRole("button", { name: "Import source" }));
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    fireEvent.change(input!, { target: { files: [new File(["note"], "slow.txt", { type: "text/plain" })] } });
    await user.click(await screen.findByRole("button", { name: "Stop waiting" }));

    expect(await screen.findByText(/did not send a server-side cancel request/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/cancel"))).toBe(false);
  });
});
