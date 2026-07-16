import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
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

const token = "s".repeat(64);
const connection = { available: true, port: 43123, baseUrl: "http://127.0.0.1:43123", token, status: "ready", phase: null, message: null };
const health = { status: "ok", service: "keen-learning-core", version: "0.1.0" };
const demoState = {
  courses: [{ id: "course-live", title: "Live Course", description: "From SQLite", created_at: "2026-07-01T09:00:00+00:00", concept_count: 1, average_mastery: 0.63 }],
  tasks: [],
  mastery: [],
};
const metadata = { runId: "run-1", conversationId: "conversation-live", provider: { kind: "ollama", model: "fixture", version: "v1" }, retrievalLimit: 8 };
const source = {
  sourceIndex: 1,
  chunkIds: ["chunk-1"],
  documentId: "doc-1",
  documentName: "Live Notes.pdf",
  pageNumber: 4,
  pageEnd: 4,
  sectionPath: ["Eigenvectors"],
  text: "The direction is preserved by scalar multiplication.",
  courseIds: ["course-live"],
};
const citation = {
  citationId: "citation-1",
  sourceIndex: 1,
  chunkId: "chunk-1",
  documentId: "doc-1",
  documentName: "Live Notes.pdf",
  pageNumber: 4,
  sectionPath: ["Eigenvectors"],
  excerpt: "direction is preserved",
  bbox: null,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function sseResponse(wire: string): Response {
  return new Response(wire, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function renderApp(route = "/conversation/new") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  tauriMocks.isTauri.mockReturnValue(false);
  tauriMocks.invoke.mockReset();
  tauriMocks.listen.mockClear();
  vi.unstubAllGlobals();
});

describe("Conversation local RAG integration", () => {
  it("keeps Browser Demo explicit and makes no Tauri or network request", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/conversation-live");

    expect(screen.getByText("Demo transcript")).toBeInTheDocument();
    expect(screen.getByText("No model or retrieval request was made")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Reply"), "A local demo note");
    await user.click(screen.getByRole("button", { name: "Add to Demo transcript" }));

    expect(screen.getByText("A local demo note")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No model or retrieval request was made");
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("streams a live answer, shows lexical-only limitations, and renders validated citations", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const answerWire = sse("metadata", metadata)
      + sse("retrieval", { mode: "lexical_only", warning: "Embeddings are unavailable; lexical evidence was used.", chunks: [source] })
      + sse("warning", { code: "lexical_only", message: "Embedding retrieval is unavailable.", retryable: false })
      + sse("delta", { text: "The direction " })
      + sse("delta", { text: "is preserved." })
      + sse("citation", citation)
      + sse("done", { runId: "run-1", finishReason: "stop", grounded: true, citationCount: 1, citationValidation: "structural_only" });
    const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/answer/stream")) return sseResponse(answerWire);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/conversation-live");

    expect(await screen.findByText("Live local RAG")).toBeInTheDocument();
    await user.selectOptions(await screen.findByLabelText("Conversation course scope"), "course-live");
    await user.type(screen.getByLabelText("Reply"), "Why is direction preserved?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("The direction is preserved.")).toBeInTheDocument();
    expect(screen.getByText("Lexical-only retrieval")).toBeInTheDocument();
    expect(screen.getByText("Embeddings are unavailable; lexical evidence was used.")).toBeInTheDocument();
    const citationButton = screen.getByRole("button", { name: /Live Notes\.pdf · p\. 4/ });
    expect(citationButton).toBeInTheDocument();
    await user.click(citationButton);
    expect(screen.getByText("Validated retrieval citation")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Context inspector")).getByText("direction is preserved")).toBeInTheDocument();
    const answerCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/v1/answer/stream"));
    const init = answerCall?.[1] as RequestInit;
    expect(new Headers(init.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(JSON.parse(String(init.body))).toMatchObject({ question: "Why is direction preserved?", courseId: "course-live", conversationId: "conversation-live", retrievalLimit: 8 });
  });

  it("renders provider-missing as a real terminal error with no Demo answer", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const wire = sse("metadata", { ...metadata, provider: null })
      + sse("error", { runId: "run-1", code: "provider_missing", message: "No local generation provider is configured.", retryable: false });
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      return sseResponse(wire);
    }));
    renderApp("/conversation/conversation-live");

    await screen.findByText("Live local RAG");
    await user.type(screen.getByLabelText("Reply"), "Explain this");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("alert", { name: "" })).toHaveTextContent("No local generation provider is configured");
    expect(screen.queryByText(/Offline demo response/i)).not.toBeInTheDocument();
  });

  it("aborts Stop generation and labels the partial response as locally stopped", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let answerSignal: AbortSignal | null = null;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      answerSignal = init?.signal as AbortSignal;
      const encoder = new TextEncoder();
      return new Response(new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(sse("metadata", metadata) + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] }) + sse("delta", { text: "Partial answer" })));
          answerSignal?.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")), { once: true });
        },
      }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/conversation-live");

    await screen.findByText("Live local RAG");
    await user.type(screen.getByLabelText("Reply"), "Stream forever");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Partial answer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop generation" }));

    expect((answerSignal as AbortSignal | null)?.aborted).toBe(true);
    expect(await screen.findByText(/No server done event was received/)).toBeInTheDocument();
  });

  it("persists drafts and supports edit-and-resend without sending automatically", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const first = renderApp();
    await user.type(screen.getByLabelText("Reply"), "Persistent draft");
    first.unmount();

    renderApp();
    expect(screen.getByLabelText("Reply")).toHaveValue("Persistent draft");
    await user.click(screen.getByRole("button", { name: "Edit and resend" }));
    expect(screen.getByLabelText("Reply")).toHaveValue("Why does multiplying by a matrix preserve an eigenvector's direction?");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
