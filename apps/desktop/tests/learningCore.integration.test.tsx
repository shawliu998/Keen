import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderApp(route: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
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
    expect(screen.getByText("Review eigenvectors before Chapter 6")).toBeInTheDocument();
    expect(screen.getByText(/No learning-core requests are made/i)).toBeInTheDocument();
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

    expect(await screen.findByText(/linked to Linear Algebra.*not uploaded or indexed/i)).toBeInTheDocument();
    expect(screen.getByText("demo-only.txt")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Unlink Linear Algebra from demo-only.txt" }));
    expect(await screen.findByText(/sample document was retained/i)).toBeInTheDocument();
    expect(screen.getByText("demo-only.txt")).toBeInTheDocument();
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows unavailable in Tauri and never substitutes Demo tasks", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue({ available: false, port: null, baseUrl: null, token: null, status: "unavailable", phase: null, message: "The sidecar stopped after automatic recovery." });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/feed");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Learning core is unavailable");
    expect(alert).toHaveTextContent("The sidecar stopped after automatic recovery.");
    expect(screen.queryByText("Review eigenvectors before Chapter 6")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["starting", "binding", "Learning core is binding its local port"],
    ["starting", "migrating", "Learning core is migrating local data"],
    ["starting", "recovering", "Learning core is recovering interrupted work"],
    ["starting", "starting_server", "Learning core server is starting"],
    ["starting", "health_checking", "Learning core is checking authenticated health"],
    ["restarting", null, "Learning core is restarting"],
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

    const restart = await screen.findByRole("button", { name: "Restart learning core" });
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

    await user.click(await screen.findByRole("button", { name: "Retry health check" }, { timeout: 3_000 }));
    expect((await screen.findAllByText("Learning core ready")).length).toBeGreaterThan(0);
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

    expect(await screen.findByText("Learning core has a configuration error")).toBeInTheDocument();
    expect(screen.getByText("The configured learning-core runtime is unavailable.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry learning core" }));
    expect(await screen.findByText("Learning core is restarting")).toBeInTheDocument();
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

    await user.click(await screen.findByRole("button", { name: "Restart learning core" }));
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

    await user.click(await screen.findByRole("button", { name: "Retry connection status" }));
    expect(await screen.findByText("Learning core is binding its local port")).toBeInTheDocument();
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
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/feed");
    await user.click(await screen.findByRole("button", { name: "overdue" }));
    expect(await screen.findByText("Live server task")).toBeInTheDocument();
    expect(screen.getByText("63%")).toBeInTheDocument();
    expect(screen.queryByText("Revisit gradient descent")).not.toBeInTheDocument();
    expect(screen.getAllByText("Learning core ready").length).toBeGreaterThan(0);
  });

  it("rediscovers rotated sidecar credentials after a supervised restart", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    const restartedConnection = {
      ...connection,
      token: "c".repeat(64),
    };
    const recoveredState = {
      ...demoState,
      tasks: [{ ...demoState.tasks[0], id: "task-recovered", title: "Recovered server task" }],
    };
    let activeConnection = connection;
    tauriMocks.invoke.mockImplementation(async () => activeConnection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) {
        const authorization = new Headers(init?.headers).get("Authorization");
        return jsonResponse(authorization === `Bearer ${restartedConnection.token}` ? recoveredState : demoState);
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderApp("/feed");
    await user.click(await screen.findByRole("button", { name: "overdue" }));
    expect(await screen.findByText("Live server task")).toBeInTheDocument();

    activeConnection = restartedConnection;
    expect(await screen.findByText("Recovered server task", undefined, { timeout: 4_500 })).toBeInTheDocument();
    expect(tauriMocks.invoke.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

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

  it.each([
    [
      "provider missing",
      { indexState: "indexed-lexical", embeddingStatus: "provider-missing", embeddingModel: null, embeddingError: null, retrievalWarning: "Local embeddings are not configured. Existing lexical search remains available.", providerConfigured: false },
      "Indexed · lexical only",
      /Local embeddings are not configured/i,
    ],
    [
      "provider failure",
      { indexState: "indexed-lexical", embeddingStatus: "provider-failure", embeddingModel: "ollama: fixture@v1 (3 dimensions)", embeddingError: "local embedding provider is unavailable; lexical indexing completed", retrievalWarning: "Embedding failed for this source. Its lexical index remains available; retry indexing after the local provider recovers.", providerConfigured: true },
      "Indexed · lexical only",
      /Embedding failed for this source/i,
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
    expect(screen.getByText(warning)).toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: "Reindex embeddings" }));
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
    const required = await screen.findByRole("button", { name: "Provider required" });
    expect(required).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Reindex embeddings" })).not.toBeInTheDocument();
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
    expect(await screen.findByText("Live Notes.txt")).toBeInTheDocument();

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

    const linkSelect = await screen.findByLabelText("Course to link to Live Notes.txt");
    await user.selectOptions(linkSelect, "course-stats");
    await user.click(screen.getByRole("button", { name: "Link" }));
    expect(await screen.findByRole("button", { name: "Unlink Statistics from Live Notes.txt" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Filter documents by course"), "course-stats");
    expect(screen.getByText("Live Notes.txt")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Unlink Live Course from Live Notes.txt" }));
    expect(await screen.findByText(/document and index were retained/i)).toBeInTheDocument();
    expect(screen.getByText("Live Notes.txt")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Filter documents by course"), "course-live");
    expect(await screen.findByText("No documents")).toBeInTheDocument();
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
    expect(await screen.findByText("Lexical indexing", undefined, { timeout: 2_000 })).toBeInTheDocument();
    expect(screen.getByLabelText("Live Notes.txt indexing progress 64%")).toBeInTheDocument();
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

    await user.click(await screen.findByRole("button", { name: "Cancel indexing" }));
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

    expect(await screen.findByText("Live Notes.txt")).toBeInTheDocument();
    const alert = await screen.findByRole("alert", undefined, { timeout: 3_000 });
    expect(alert).toHaveTextContent(/stage, progress, and job actions may be incomplete/i);
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
    expect(screen.getByLabelText("Live Notes.txt indexing progress 42%")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry indexing" }));
    expect(await screen.findByText(/new indexing job was queued/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringMatching(/cannot be undone/i));
    expect(await screen.findByText(/and its local indexing data were deleted/i)).toBeInTheDocument();
    expect(await screen.findByText("No documents")).toBeInTheDocument();
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

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByText(/record and index data.*were deleted, but local source cleanup is incomplete/i)).toBeInTheDocument();
    expect(await screen.findByText("No documents")).toBeInTheDocument();
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
    expect(await screen.findByText("Live Notes.txt")).toBeInTheDocument();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    fireEvent.change(input!, { target: { files: [new File(["note"], "slow.txt", { type: "text/plain" })] } });
    await user.click(await screen.findByRole("button", { name: "Stop waiting" }));

    expect(await screen.findByText(/did not send a server-side cancel request/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/cancel"))).toBe(false);
  });
});
