import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { App } from "../src/App";
import { storeConversationHandoff } from "../src/features/conversation/conversationHandoff";

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
const metadata = { runId: "run-1", conversationId: "11111111-1111-4111-8111-111111111111", provider: { kind: "ollama", model: "fixture", version: "v1" }, retrievalLimit: 8 };
const source = {
  sourceIndex: 1,
  chunkId: "chunk-1",
  chunkIds: ["chunk-1"],
  documentId: "doc-1",
  documentVersionId: "version-1",
  chunkContentHash: "c".repeat(64),
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
  documentVersionId: "version-1",
  chunkContentHash: "c".repeat(64),
  documentName: "Live Notes.pdf",
  pageNumber: 4,
  sectionPath: ["Eigenvectors"],
  excerpt: "direction is preserved",
  bbox: null,
};
const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function sseResponse(wire: string, init?: RequestInit): Response {
  const request = init?.body ? JSON.parse(String(init.body)) as { userMessageId?: string; assistantMessageId?: string } : {};
  const normalized = wire.replace(/event: (metadata|done|error)\ndata: ([^\n]+)\n\n/g, (_record, event: string, raw: string) => {
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (request.assistantMessageId) data.runId = request.assistantMessageId;
    if (event === "metadata" && request.userMessageId && request.assistantMessageId) {
      data.userMessageId = request.userMessageId;
      data.assistantMessageId = request.assistantMessageId;
    }
    return sse(event, data);
  });
  return new Response(normalized, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function savedConversation(id: string, selectedCourseId: string | null = null) {
  return {
    id,
    courseId: selectedCourseId,
    title: "Saved learning question",
    mode: "ask",
    status: "active",
    sourceScope: selectedCourseId ? { kind: "course", courseId: selectedCourseId } : { kind: "all_indexed" },
    createdAt: "2026-07-21T08:00:00+00:00",
    updatedAt: "2026-07-21T08:00:00+00:00",
    archivedAt: null,
  };
}

function durableMessage(
  id: string,
  role: "user" | "assistant",
  status: "pending" | "streaming" | "completed" | "failed" | "cancelled" | "interrupted",
  content: string,
  replyToMessageId: string | null = null,
  conversationId = "11111111-1111-4111-8111-111111111111",
) {
  return {
    id,
    conversationId,
    sequence: role === "user" ? 0 : 1,
    role,
    status,
    content,
    replyToMessageId: role === "assistant" ? replyToMessageId : null,
    sourceScope: { kind: "course", courseId: "course-live" },
    retrievalLimit: role === "assistant" ? 8 : null,
    modelProvider: role === "assistant" ? "ollama" : null,
    modelName: role === "assistant" ? "fixture" : null,
    promptVersion: role === "assistant" ? "v1" : null,
    errorCode: status === "cancelled" ? "cancelled_by_user" : null,
    errorDetail: null,
    startedAt: "2026-07-21T08:00:00+00:00",
    finishedAt: ["completed", "failed", "cancelled", "interrupted"].includes(status) ? "2026-07-21T08:00:01+00:00" : null,
    createdAt: "2026-07-21T08:00:00+00:00",
    updatedAt: "2026-07-21T08:00:01+00:00",
    citations: [],
  };
}

function conversationRead(url: string): Response | null {
  const match = url.match(/\/v1\/conversations\/([^/]+)(?:\/messages)?$/u);
  if (!match) return null;
  const id = decodeURIComponent(match[1]);
  return url.endsWith("/messages") ? jsonResponse({ messages: [] }) : jsonResponse(savedConversation(id, "course-live"));
}

function renderApp(route = "/conversation/new") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
}

function renderStrictApp(route: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(<StrictMode><QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider></StrictMode>);
}

function RouteSwitchControl() {
  const navigate = useNavigate();
  return <>
    <button onClick={() => navigate("/conversation/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")}>Switch conversation</button>
    <button onClick={() => navigate("/conversation/new")}>Switch to new conversation</button>
  </>;
}

function renderSwitchableApp(route = "/conversation/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><RouteSwitchControl /><App /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  tauriMocks.isTauri.mockReturnValue(false);
  tauriMocks.invoke.mockReset();
  tauriMocks.listen.mockClear();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  if (originalScrollIntoView) {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: originalScrollIntoView });
  } else {
    Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  }
});

describe("Conversation local RAG integration", () => {
  it("keeps a new Browser Demo request empty and does not invent an answer", () => {
    renderApp("/conversation/new");

    expect(screen.getByRole("heading", { name: "New learning request" })).toBeInTheDocument();
    expect(screen.getByText("Start with a learning question")).toBeInTheDocument();
    expect(screen.queryByText("Why does multiplying by a matrix preserve an eigenvector's direction?")).not.toBeInTheDocument();
    expect(screen.queryByText(/This is fixed seed text/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open inspector" })).not.toBeInTheDocument();
  });

  it("keeps live course loading and empty source scope local to the affected region", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let resolveDemoState: (value: Response) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return new Promise<Response>((resolve) => { resolveDemoState = resolve; });
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp();

    expect(await screen.findByRole("status", { name: "Loading source scopes" })).toBeInTheDocument();
    resolveDemoState(jsonResponse({ courses: [], tasks: [], mastery: [] }));
    expect(await screen.findByText("Select a source scope first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Knowledge Base" })).toHaveAttribute("href", "/knowledge");
    expect(screen.getByLabelText("Reply")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ask question" })).toBeDisabled();
  });

  it("keeps Browser Demo explicit and makes no Tauri or network request", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    expect(screen.getByText("Sample answer")).toBeInTheDocument();
    expect(screen.getAllByText("Browser Demo · no service calls")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Copy answer unavailable" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Branch unavailable" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Attachment unavailable" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry answer" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reuse question" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Reply"), "A local demo note");
    await user.tab();
    expect(screen.getByRole("button", { name: "Add note" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Add note" }));

    expect(screen.getByText("A local demo note")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No answer request was sent");
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates /new durably, adopts the authoritative route, and streams with persisted identities", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let createdId = "";
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/v1/conversations") && init?.method === "POST") {
        const request = JSON.parse(String(init.body)) as { id: string; question: string; sourceScope: unknown };
        createdId = request.id;
        expect(request).toMatchObject({ question: "Create a durable explanation", sourceScope: { kind: "course", courseId: "course-live" } });
        return jsonResponse({ conversation: savedConversation(createdId, "course-live"), replayed: false }, 201);
      }
      if (url.endsWith("/answers/stream")) {
        expect(url).toContain(`/v1/conversations/${createdId}/answers/stream`);
        const wire = sse("metadata", { ...metadata, conversationId: createdId })
          + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] })
          + sse("delta", { text: "Durably saved answer." })
          + sse("done", { runId: "replaced", finishReason: "stop", grounded: false, citationCount: 0, citationValidation: "structural_only" });
        return sseResponse(wire, init);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/new");

    await user.selectOptions(await screen.findByLabelText("Conversation course scope"), "course-live");
    await user.type(screen.getByLabelText("Reply"), "Create a durable explanation");
    await user.click(screen.getByRole("button", { name: "Ask question" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/answers/stream"))).toBe(true));
    expect(await screen.findByText("Durably saved answer.")).toBeInTheDocument();
    expect(createdId).not.toBe("");
    const streamCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/answers/stream"));
    expect(JSON.parse(String((streamCall?.[1] as RequestInit).body))).toMatchObject({
      question: "Create a durable explanation",
      sourceScope: { kind: "course", courseId: "course-live" },
      retrievalLimit: 8,
    });
  });

  it("consumes a Home handoff once and streams on the authoritative route without creating again", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const conversationId = "22222222-2222-4222-8222-222222222222";
    const userMessageId = "33333333-3333-4333-8333-333333333333";
    const assistantMessageId = "44444444-4444-4444-8444-444444444444";
    const conversation = savedConversation(conversationId, "course-live");
    storeConversationHandoff({
      conversationId,
      question: "Explain the locked source",
      sourceScope: { kind: "course", courseId: "course-live" },
      scopeLabel: "Live Course",
      userMessageId,
      assistantMessageId,
      idempotencyKey: "home-question-key-0001",
      cancelIdempotencyKey: "home-cancel-key-00001",
      conversation: conversation as never,
    });
    const answerState: { signal: AbortSignal | null; activeBeforeCompletion: boolean } = {
      signal: null,
      activeBeforeCompletion: false,
    };
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) {
        const body = JSON.parse(String(init?.body));
        expect(body).toMatchObject({
          question: "Explain the locked source",
          sourceScope: { kind: "course", courseId: "course-live" },
          userMessageId,
          assistantMessageId,
          idempotencyKey: "home-question-key-0001",
        });
        answerState.signal = init?.signal as AbortSignal;
        const encoder = new TextEncoder();
        return new Response(new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(encoder.encode(
              sse("metadata", { ...metadata, conversationId, runId: assistantMessageId, userMessageId, assistantMessageId })
              + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] }),
            ));
            setTimeout(() => {
              answerState.activeBeforeCompletion = answerState.signal?.aborted === false;
              controller.enqueue(encoder.encode(
                sse("delta", { text: "Durable handoff answer." })
                + sse("done", { runId: assistantMessageId, finishReason: "stop", grounded: false, citationCount: 0, citationValidation: "structural_only" }),
              ));
              controller.close();
            }, 130);
          },
        }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderStrictApp(`/conversation/${conversationId}`);

    expect(await screen.findByText("Durable handoff answer.")).toBeInTheDocument();
    expect(answerState.activeBeforeCompletion).toBe(true);
    expect(answerState.signal?.aborted).toBe(false);
    expect(screen.getAllByText("Live Course").length).toBeGreaterThan(0);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/answers/stream"))).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/v1/conversations"))).toHaveLength(0);
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toHaveLength(1);
    expect(sessionStorage.length).toBe(0);
  });

  it("restores a persisted transcript and its locked source scope without a write", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const userMessage = durableMessage("22222222-2222-4222-8222-222222222222", "user", "completed", "What was saved?", null);
    const assistantMessage = durableMessage("33333333-3333-4333-8333-333333333333", "assistant", "completed", "This answer came from SQLite.", "22222222-2222-4222-8222-222222222222");
    const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/messages")) return jsonResponse({ messages: [userMessage, assistantMessage] });
      if (url.endsWith("/v1/conversations/11111111-1111-4111-8111-111111111111")) return jsonResponse(savedConversation("11111111-1111-4111-8111-111111111111", "course-live"));
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    expect(await screen.findByText("This answer came from SQLite.")).toBeInTheDocument();
    expect(screen.getByText("What was saved?")).toBeInTheDocument();
    expect(screen.getByLabelText("Conversation course scope")).toHaveTextContent("Live Course");
    expect(screen.getByLabelText("Conversation course scope").tagName).toBe("P");
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(false);
  });

  it("restores a completed answer without citations as explicitly unsupported", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const userMessage = durableMessage("22222222-2222-4222-8222-222222222222", "user", "completed", "What was saved?", null);
    const assistantMessage = durableMessage("33333333-3333-4333-8333-333333333333", "assistant", "completed", "", userMessage.id);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/messages")) return jsonResponse({ messages: [userMessage, assistantMessage] });
      if (url.endsWith("/v1/conversations/11111111-1111-4111-8111-111111111111")) return jsonResponse(savedConversation("11111111-1111-4111-8111-111111111111", "course-live"));
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    expect(await screen.findByText("There was not enough source support for this answer.")).toBeInTheDocument();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });

  it("polls a restored in-progress answer to its authoritative terminal state", async () => {
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const userMessage = durableMessage("22222222-2222-4222-8222-222222222222", "user", "completed", "Resume?", null);
    const pending = durableMessage("33333333-3333-4333-8333-333333333333", "assistant", "streaming", "Partial", userMessage.id);
    let reads = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/messages")) return jsonResponse({ messages: [userMessage, pending] });
      if (url.endsWith(`/messages/${pending.id}`)) {
        reads += 1;
        return jsonResponse(reads < 2 ? pending : durableMessage(pending.id, "assistant", "completed", "Recovered after refresh.", userMessage.id));
      }
      if (url.endsWith("/v1/conversations/11111111-1111-4111-8111-111111111111")) return jsonResponse(savedConversation("11111111-1111-4111-8111-111111111111", "course-live"));
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    expect(await screen.findByText("Recovered after refresh.")).toBeInTheDocument();
    expect(screen.queryByText("Answer in progress")).not.toBeInTheDocument();
    expect(reads).toBe(2);
  });

  it("reconciles a terminal persisted message after the SSE transport ends without a terminal event", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let requestIds: { userMessageId: string; assistantMessageId: string } | null = null;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) {
        requestIds = JSON.parse(String(init?.body)) as typeof requestIds;
        const wire = sse("metadata", { ...metadata, runId: requestIds!.assistantMessageId, userMessageId: requestIds!.userMessageId, assistantMessageId: requestIds!.assistantMessageId })
          + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] })
          + sse("delta", { text: "Unconfirmed partial" });
        return new Response(wire, { headers: { "Content-Type": "text/event-stream" } });
      }
      if (requestIds && url.endsWith(`/messages/${requestIds.assistantMessageId}`)) {
        return jsonResponse(durableMessage(requestIds.assistantMessageId, "assistant", "completed", "Recovered from the durable message.", requestIds.userMessageId));
      }
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Reconcile this answer");
    await user.click(screen.getByRole("button", { name: "Ask question" }));

    expect(await screen.findByText("Recovered from the durable message.")).toBeInTheDocument();
    expect(screen.queryByText("Unconfirmed partial")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask again" })).toBeInTheDocument();
  });

  it("streams a live answer, shows lexical-only limitations, and renders validated citations", async () => {
    const user = userEvent.setup();
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const answerWire = sse("metadata", metadata)
      + sse("retrieval", { mode: "lexical_only", warning: "Embeddings are unavailable; lexical evidence was used.", chunks: [source] })
      + sse("warning", { code: "lexical_only", message: "Embedding retrieval is unavailable.", retryable: false })
      + sse("delta", { text: "The direction " })
      + sse("delta", { text: "is preserved." })
      + sse("citation", citation)
      + sse("done", { runId: "run-1", finishReason: "stop", grounded: true, citationCount: 1, citationValidation: "structural_only" });
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) return sseResponse(answerWire, init);
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    const transcript = screen.getByRole("region", { name: "Conversation transcript" });
    Object.defineProperties(transcript, {
      scrollHeight: { configurable: true, value: 800 },
      clientHeight: { configurable: true, value: 320 },
    });
    await user.type(screen.getByLabelText("Reply"), "Why is direction preserved?");
    await user.click(screen.getByRole("button", { name: "Ask question" }));

    const answerText = await screen.findByText("The direction is preserved.");
    await waitFor(() => expect(answerText.closest("article")).toHaveFocus());
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "auto" });
    expect(screen.queryByText("Lexical-only retrieval")).not.toBeInTheDocument();
    expect(screen.getByText("Embeddings are unavailable; lexical evidence was used.")).toBeInTheDocument();
    const citationButton = screen.getByRole("button", { name: /Live Notes\.pdf · p\. 4/ });
    expect(citationButton).toBeInTheDocument();
    await user.click(citationButton);
    expect(screen.getByRole("dialog", { name: "Live Notes.pdf" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Context inspector")).not.toBeInTheDocument();
    const answerCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/answers/stream"));
    const init = answerCall?.[1] as RequestInit;
    expect(new Headers(init.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(JSON.parse(String(init.body))).toMatchObject({ question: "Why is direction preserved?", sourceScope: { kind: "course", courseId: "course-live" }, retrievalLimit: 8 });
    await user.click(screen.getByRole("link", { name: "Home" }));
    expect(screen.queryByLabelText("Context inspector")).not.toBeInTheDocument();
  });

  it("renders provider-missing as a real terminal error with no Demo answer", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const wire = sse("metadata", { ...metadata, provider: null })
      + sse("error", { runId: "run-1", code: "provider_missing", message: "No local generation provider is configured.", retryable: false });
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) return sseResponse(wire, init);
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Explain this");
    await user.click(screen.getByRole("button", { name: "Ask question" }));
    expect(await screen.findByRole("alert", { name: "" })).toHaveTextContent("No local generation provider is configured");
    expect(screen.getByRole("link", { name: "Open provider settings" })).toHaveAttribute("href", "/settings?section=capabilities");
    expect(screen.queryByText(/Offline demo response/i)).not.toBeInTheDocument();
  });

  it("clears a selected live citation when the durable run fails", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let streamController: ReadableStreamDefaultController<Uint8Array> | null = null;
    let runAssistantId = "";
    const encoder = new TextEncoder();
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/documents/doc-1/content")) return new Response(encoder.encode("%PDF-1.7 fixture"), { headers: { "Content-Type": "application/pdf", "Content-Length": "16" } });
      if (url.endsWith("/answers/stream")) {
        const request = JSON.parse(String(init?.body)) as { userMessageId: string; assistantMessageId: string };
        runAssistantId = request.assistantMessageId;
        return new Response(new ReadableStream<Uint8Array>({
          start(controller) {
            streamController = controller;
            controller.enqueue(encoder.encode(
              sse("metadata", { ...metadata, runId: request.assistantMessageId, userMessageId: request.userMessageId, assistantMessageId: request.assistantMessageId })
              + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] })
              + sse("delta", { text: "Partial grounded answer." })
              + sse("citation", citation),
            ));
          },
        }), { headers: { "Content-Type": "text/event-stream" } });
      }
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Fail after citing");
    await user.click(screen.getByRole("button", { name: "Ask question" }));
    await user.click(await screen.findByRole("button", { name: /Live Notes\.pdf · p\. 4/ }));
    expect(screen.getByRole("dialog", { name: "Live Notes.pdf" })).toBeInTheDocument();
    const activeController = streamController as ReadableStreamDefaultController<Uint8Array> | null;
    activeController?.enqueue(encoder.encode(sse("error", { runId: runAssistantId, code: "provider_unavailable", message: "Generation failed.", retryable: true })));
    activeController?.close();

    expect(await screen.findByText("Generation failed.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Live Notes.pdf" })).not.toBeInTheDocument();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });

  it("blocks new execution after an unknown outcome and reloads only authoritative state", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let assistantId = "";
    let userId = "";
    let messageReads = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) {
        const request = JSON.parse(String(init?.body)) as { userMessageId: string; assistantMessageId: string };
        userId = request.userMessageId;
        assistantId = request.assistantMessageId;
        return sseResponse(
          sse("metadata", { ...metadata, runId: assistantId, userMessageId: userId, assistantMessageId: assistantId })
          + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] })
          + sse("delta", { text: "Unconfirmed answer." })
          + sse("citation", citation),
          init,
        );
      }
      if (assistantId && url.endsWith(`/messages/${assistantId}`)) {
        messageReads += 1;
        if (messageReads === 1) return jsonResponse({ detail: "temporarily unavailable" }, 503);
        return jsonResponse(durableMessage(assistantId, "assistant", "completed", "Authoritative result.", userId));
      }
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Unknown outcome");
    await user.click(screen.getByRole("button", { name: "Ask question" }));
    expect(await screen.findByText(/could not confirm the saved answer status/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry answer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reuse question" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Reply")).toBeDisabled();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    const postsBeforeReload = fetchMock.mock.calls.filter(([, request]) => (request as RequestInit | undefined)?.method === "POST").length;
    await user.click(screen.getByRole("button", { name: "Reload saved answer" }));
    expect(await screen.findByText("Authoritative result.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, request]) => (request as RequestInit | undefined)?.method === "POST")).toHaveLength(postsBeforeReload);
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
      if (url.endsWith("/cancel")) {
        expect(answerSignal?.aborted).toBe(false);
        const assistantId = decodeURIComponent(url.split("/").at(-2) ?? "assistant");
        return jsonResponse({ message: durableMessage(assistantId, "assistant", "cancelled", "Partial answer", "44444444-4444-4444-8444-444444444444"), replayed: false });
      }
      const read = conversationRead(url);
      if (read) return read;
      answerSignal = init?.signal as AbortSignal;
      const request = JSON.parse(String(init?.body)) as { userMessageId: string; assistantMessageId: string };
      const encoder = new TextEncoder();
      return new Response(new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(sse("metadata", { ...metadata, runId: request.assistantMessageId, userMessageId: request.userMessageId, assistantMessageId: request.assistantMessageId }) + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] }) + sse("delta", { text: "Partial answer" })));
          answerSignal?.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")), { once: true });
        },
      }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Stream forever");
    await user.click(screen.getByRole("button", { name: "Ask question" }));
    expect(await screen.findByText("Partial answer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel answer" }));

    expect((answerSignal as AbortSignal | null)?.aborted).toBe(true);
    const stopped = await screen.findByText(/saved answer was cancelled/i);
    await waitFor(() => expect(stopped.closest("article")).toHaveFocus());
  });

  it("retries an uncommitted stream with the exact same durable identities and idempotency key", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const streamBodies: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        streamBodies.push(body);
        if (streamBodies.length === 1) return jsonResponse({ detail: { message: "Stream did not start", retryable: true } }, 503);
        const wire = sse("metadata", { ...metadata, runId: body.assistantMessageId, userMessageId: body.userMessageId, assistantMessageId: body.assistantMessageId })
          + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] })
          + sse("delta", { text: "Recovered with the same request." })
          + sse("done", { runId: body.assistantMessageId, finishReason: "stop", grounded: false, citationCount: 0, citationValidation: "structural_only" });
        return new Response(wire, { headers: { "Content-Type": "text/event-stream" } });
      }
      if (/\/messages\/[^/]+$/u.test(url)) return jsonResponse({ detail: "message not found" }, 404);
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Retry one durable request");
    await user.click(screen.getByRole("button", { name: "Ask question" }));

    expect(await screen.findByText("Recovered with the same request.")).toBeInTheDocument();
    expect(streamBodies).toHaveLength(2);
    expect(streamBodies[1]).toEqual(streamBodies[0]);
  });

  it("persists a new-request draft without inventing an editable sample answer", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const first = renderApp();
    await user.type(screen.getByLabelText("Reply"), "Persistent draft");
    first.unmount();

    renderApp();
    expect(screen.getByLabelText("Reply")).toHaveValue("Persistent draft");
    expect(screen.queryByRole("button", { name: "Reuse question" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("supports editing an explicit Demo transcript without sending automatically", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await user.click(screen.getByRole("button", { name: "Reuse question" }));
    expect(screen.getByLabelText("Reply")).toHaveValue("Why does multiplying by a matrix preserve an eigenvector's direction?");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("labels a completed ungrounded answer and does not invent sources", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const wire = sse("metadata", metadata)
      + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] })
      + sse("delta", { text: "This is a cautious answer." })
      + sse("done", { runId: "run-1", finishReason: "stop", grounded: false, citationCount: 0, citationValidation: "structural_only" });
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) return sseResponse(wire, init);
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp("/conversation/11111111-1111-4111-8111-111111111111");

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Explain this cautiously");
    await user.click(screen.getByRole("button", { name: "Ask question" }));

    expect(await screen.findByText("There was not enough source support for this answer.")).toBeInTheDocument();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reuse question" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry answer" })).not.toBeInTheDocument();
  });

  it("uses one PDF citation preview, restores focus on Escape, and clears it on route change", async () => {
    const user = userEvent.setup();
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    const wire = sse("metadata", { ...metadata, conversationId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" })
      + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] })
      + sse("delta", { text: "The direction is preserved." })
      + sse("citation", citation)
      + sse("done", { runId: "run-1", finishReason: "stop", grounded: true, citationCount: 1, citationValidation: "structural_only" });
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.endsWith("/answers/stream")) return sseResponse(wire, init);
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderSwitchableApp();

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Why is direction preserved?");
    await user.click(screen.getByRole("button", { name: "Ask question" }));
    const citationButton = await screen.findByRole("button", { name: /Live Notes\.pdf · p\. 4/ });
    await user.click(citationButton);
    expect(screen.getByRole("dialog", { name: "Live Notes.pdf" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Context inspector")).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Live Notes.pdf" })).not.toBeInTheDocument();
    expect(citationButton).toHaveFocus();

    await user.click(citationButton);
    await user.click(screen.getByRole("button", { name: "Switch conversation" }));
    expect(screen.queryByRole("dialog", { name: "Live Notes.pdf" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Context inspector")).not.toBeInTheDocument();
  });

  it("aborts a transient route run and loads only the next route's draft", async () => {
    const user = userEvent.setup();
    localStorage.setItem("keen-conversation-draft:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "Draft for B");
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    let answerSignal: AbortSignal | null = null;
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      if (url.includes("/v1/agent/runs/latest?")) return jsonResponse({ run: null, events: [] });
      const read = conversationRead(url);
      if (read) return read;
      if (url.endsWith("/answers/stream")) {
        answerSignal = init?.signal as AbortSignal;
        const request = JSON.parse(String(init?.body)) as { userMessageId: string; assistantMessageId: string };
        const encoder = new TextEncoder();
        return new Response(new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(encoder.encode(sse("metadata", { ...metadata, conversationId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", runId: request.assistantMessageId, userMessageId: request.userMessageId, assistantMessageId: request.assistantMessageId }) + sse("retrieval", { mode: "hybrid", warning: null, chunks: [source] }) + sse("delta", { text: "A route-local partial answer" })));
            answerSignal?.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")), { once: true });
          },
        }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderSwitchableApp();

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Question for A");
    await user.click(screen.getByRole("button", { name: "Ask question" }));
    expect(await screen.findByText("A route-local partial answer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Switch conversation" }));

    await waitFor(() => expect(answerSignal?.aborted).toBe(true));
    expect(screen.getByLabelText("Reply")).toHaveValue("Draft for B");
    expect(screen.queryByText("A route-local partial answer")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Context inspector")).not.toBeInTheDocument();
  });

  it("consumes a new-learning handoff on a route switch without showing the old transcript", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("keen-new-message", "Use this focused question");
    tauriMocks.isTauri.mockReturnValue(true);
    tauriMocks.invoke.mockResolvedValue(connection);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse(health);
      if (url.endsWith("/v1/demo-state")) return jsonResponse(demoState);
      const read = conversationRead(url);
      if (read) return read;
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderSwitchableApp();

    await screen.findByLabelText("Conversation course scope");
    await user.type(screen.getByLabelText("Reply"), "Question for A");
    await user.click(screen.getByRole("button", { name: "Switch to new conversation" }));

    await waitFor(() => expect(screen.getByLabelText("Reply")).toHaveValue("Use this focused question"));
    expect(screen.getByRole("heading", { name: "New learning request" })).toBeInTheDocument();
    expect(screen.queryByText("Question for A")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("keen-new-message")).toBeNull();
  });
});
