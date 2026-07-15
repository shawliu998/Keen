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
const connection = { available: true, port: 43123, baseUrl: "http://127.0.0.1:43123", token, status: "ready" };
const health = { status: "ok", service: "keen-learning-core", version: "0.1.0" };
const demoState = {
  courses: [{ id: "course-live", title: "Live Course", description: "From SQLite", created_at: "2026-07-01T09:00:00+00:00", concept_count: 1, average_mastery: 0.63 }],
  tasks: [{ id: "task-live", course_id: "course-live", course_title: "Live Course", title: "Live server task", reason: "Returned by the authenticated learning core.", due_at: "2026-07-14T09:00:00+00:00", estimated_minutes: 20, status: "overdue", concept_id: "concept-live", created_at: "2026-07-01T09:00:00+00:00", updated_at: "2026-07-14T09:00:00+00:00" }],
  mastery: [{ concept_id: "concept-live", course_id: "course-live", concept_name: "Live concept", probability: 0.63, attempts: 3, updated_at: "2026-07-14T09:00:00+00:00" }],
};
const documentRecord = { id: "doc-live", name: "Live Notes.txt", mimeType: "text/plain", sizeBytes: 42, contentHash: "d".repeat(64), status: "indexed", pageCount: 1, chunkCount: 2, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null };

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

  it("shows unavailable in Tauri and never substitutes Demo tasks", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue({ available: false, port: null, baseUrl: null, token: null, status: "unavailable" });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/feed");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Learning core is unavailable");
    expect(screen.queryByText("Review eigenvectors before Chapter 6")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("maps starting/restarting sidecar state to starting UI", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue({ available: false, port: null, baseUrl: null, token: null, status: "restarting" });
    vi.stubGlobal("fetch", vi.fn());
    renderApp("/feed");
    expect(await screen.findByText("Learning core is starting")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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
    expect(screen.getAllByText("Learning core healthy").length).toBeGreaterThan(0);
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
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/documents") && !url.endsWith("/import")) { documentLoads += 1; return jsonResponse({ documents: [documentRecord] }); }
      if (url.endsWith("/v1/search")) return jsonResponse({ query: "eigen", results: [{ chunkId: "chunk-1", documentId: "doc-live", documentName: "Live Notes.txt", pageNumber: 1, sectionPath: ["Vectors"], text: "An eigenvector preserves its direction.", score: 0.9 }] });
      if (url.endsWith("/v1/documents/import")) return jsonResponse({ document: { ...documentRecord, status: "queued" }, duplicate: false }, 201);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderApp("/knowledge");
    expect(await screen.findByText("Live Notes.txt")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Search documents" }), "eigen");
    expect(await screen.findByText("An eigenvector preserves its direction.")).toBeInTheDocument();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input!, { target: { files: [new File(["note"], "upload.txt", { type: "text/plain" })] } });
    expect(await screen.findByText(/current status: queued/i)).toBeInTheDocument();
    await waitFor(() => expect(documentLoads).toBeGreaterThanOrEqual(2));
  });
});
