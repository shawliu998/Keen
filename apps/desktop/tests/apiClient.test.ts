import {
  createLearningCoreClient,
  InvalidLearningCoreUrlError,
  LearningCoreResponseError,
  LearningCoreSchemaError,
  LearningCoreDocumentContentError,
  answerCitationSchema,
  indexedDocumentSchema,
  indexJobSchema,
  searchResponseSchema,
  sidecarConnectionSchema,
} from "@keen/api-client";

const token = "a".repeat(64);
const health = { status: "ok", service: "keen-learning-core", version: "0.1.0" };
const pendingCapability = { indexState: "pending", embeddingStatus: "not-applicable", embeddingModel: null, embeddingError: null, retrievalWarning: null, providerConfigured: false } as const;
const indexJob = {
  id: "job-1",
  documentId: "doc-1",
  status: "queued",
  stage: "queued",
  progress: 0,
  cancelRequested: false,
  error: null,
  createdAt: "2026-07-16T10:00:00+00:00",
  updatedAt: "2026-07-16T10:00:00+00:00",
  startedAt: null,
  finishedAt: null,
  operation: "full_index",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("LearningCoreClient security boundary", () => {
  it.each([
    "https://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:8080/health",
    "http://127.0.0.1:8080?redirect=evil.test",
    "http://127.0.0.1:0",
    "http://127.0.0.1:65536",
    "http://user@127.0.0.1:8080",
    "http://2130706433:8080",
  ])("rejects a non-canonical learning-core URL: %s", (baseUrl) => {
    expect(() => createLearningCoreClient(baseUrl, token)).toThrow(InvalidLearningCoreUrlError);
  });

  it("rejects short or header-injecting tokens at both boundaries", () => {
    expect(() => createLearningCoreClient("http://127.0.0.1:8080", "short")).toThrow(TypeError);
    expect(() => createLearningCoreClient("http://127.0.0.1:8080", `${"a".repeat(32)}\r\nInjected: yes`)).toThrow(TypeError);
    expect(sidecarConnectionSchema.safeParse({ available: true, port: 8080, baseUrl: "http://127.0.0.1:8080", token: `${"a".repeat(32)}\n`, status: "ready", phase: null, message: null }).success).toBe(false);
  });

  it.each(["binding", "migrating", "recovering", "starting_server", "health_checking"])("accepts the supervised startup phase: %s", (phase) => {
    expect(sidecarConnectionSchema.safeParse({
      available: false,
      port: null,
      baseUrl: null,
      token: null,
      status: "starting",
      phase,
      message: null,
    }).success).toBe(true);
  });

  it("accepts configuration errors without exposing connection credentials", () => {
    expect(sidecarConnectionSchema.safeParse({
      available: false,
      port: null,
      baseUrl: null,
      token: null,
      status: "configuration_error",
      phase: null,
      message: "The configured learning-core runtime is unavailable.",
    }).success).toBe(true);
  });

  it("rejects startup phases on ready connections", () => {
    expect(sidecarConnectionSchema.safeParse({
      available: true,
      port: 8080,
      baseUrl: "http://127.0.0.1:8080",
      token,
      status: "ready",
      phase: "health_checking",
      message: null,
    }).success).toBe(false);
  });

  it("rejects a response that does not match its Zod schema", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ status: "ok", service: "wrong", version: "0.1.0" }));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await expect(client.health()).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("preserves bounded recovery details and request IDs for non-success responses", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      detail: {
        message: "document contains no extractable text",
        retryable: true,
        recovery: "Retry with a text-extractable file.",
        documentId: "doc-failed",
      },
    }), { status: 422, headers: { "Content-Type": "application/json", "X-Request-ID": "request-123" } }));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    const error = await client.uploadDocument(
      new File(["empty"], "scan.pdf", { type: "application/pdf" }),
    ).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(LearningCoreResponseError);
    expect(error).toMatchObject({
      status: 422,
      requestId: "request-123",
      detail: {
        message: "document contains no extractable text",
        retryable: true,
        recovery: "Retry with a text-extractable file.",
        documentId: "doc-failed",
      },
    });
  });

  it("sends the bearer token and forwards AbortSignal", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(health));
    const controller = new AbortController();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await client.health({ signal: controller.signal });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(init.signal).toBe(controller.signal);
  });

  it("uploads a browser File as multipart without overriding its Content-Type", async () => {
    const imported = {
      document: { id: "doc-1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "queued", pageCount: 0, chunkCount: 0, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null, courseIds: ["course-a"], ...pendingCapability },
      job: indexJob,
      duplicate: false,
      linked: true,
    };
    const fetchMock = vi.fn(async () => jsonResponse(imported, 202));
    const controller = new AbortController();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await client.uploadDocument(new File(["hello"], "notes.txt", { type: "text/plain" }), "course-a", { signal: controller.signal });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8080/v1/documents/import");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("course_id")).toBe("course-a");
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    expect(init.signal).toBe(controller.signal);
  });

  it("rejects HTTP 200 imports that do not identify an existing document", async () => {
    const imported = {
      document: { id: "doc-1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "queued", pageCount: 0, chunkCount: 0, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null, courseIds: [], ...pendingCapability },
      job: indexJob,
      duplicate: false,
      linked: false,
    };
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse(imported, 200)) as unknown as typeof fetch,
    );

    await expect(client.uploadDocument(new File(["hello"], "notes.txt"))).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("accepts HTTP 202 when missing-source repair reuses a document identity", async () => {
    const imported = {
      document: { id: "doc-1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "queued", pageCount: 0, chunkCount: 0, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null, courseIds: [], ...pendingCapability },
      job: indexJob,
      duplicate: true,
      linked: false,
    };
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse(imported, 202)) as unknown as typeof fetch,
    );

    await expect(client.uploadDocument(new File(["hello"], "notes.txt"))).resolves.toMatchObject({ duplicate: true });
  });

  it("rejects unexpected success status codes for strict routes", async () => {
    const document = { id: "doc-1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "failed", pageCount: 0, chunkCount: 0, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: "interrupted", courseIds: [], ...pendingCapability };
    const getClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(indexJob, 202)) as unknown as typeof fetch);
    const retryClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ document, job: indexJob }, 200)) as unknown as typeof fetch);

    await expect(getClient.getIndexJob("job-1")).rejects.toMatchObject({ status: 202 });
    await expect(getClient.cancelIndexJob("job-1")).rejects.toMatchObject({ status: 202 });
    await expect(retryClient.retryDocument("doc-1")).rejects.toMatchObject({ status: 200 });
  });

  it("strictly validates persisted index jobs", () => {
    expect(indexJobSchema.safeParse(indexJob).success).toBe(true);
    expect(indexJobSchema.safeParse({ ...indexJob, progress: 101 }).success).toBe(false);
    expect(indexJobSchema.safeParse({ ...indexJob, status: "indexed" }).success).toBe(false);
    expect(indexJobSchema.safeParse({ ...indexJob, workerGeneration: 7 }).success).toBe(false);
  });

  it("requires unique, stably sorted courseIds on document records", () => {
    const document = { id: "doc-1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "queued", pageCount: 0, chunkCount: 0, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null, ...pendingCapability };
    expect(indexedDocumentSchema.safeParse({ ...document, courseIds: ["course-a", "course-b"] }).success).toBe(true);
    expect(indexedDocumentSchema.safeParse({ ...document, courseIds: ["course-b", "course-a"] }).success).toBe(false);
    expect(indexedDocumentSchema.safeParse({ ...document, courseIds: ["course-a", "course-a"] }).success).toBe(false);
  });

  it("requires truthful hybrid search mode, fallback warning, and merged chunk bounds", () => {
    const result = { chunkId: "chunk-1", chunkIds: ["chunk-1", "chunk-2"], documentId: "doc-1", documentName: "notes.txt", pageNumber: 2, pageEnd: 3, sectionPath: [], text: "grounded text", score: 0.1 };
    expect(searchResponseSchema.safeParse({ query: "text", mode: "hybrid", warning: null, results: [result] }).success).toBe(true);
    expect(searchResponseSchema.safeParse({ query: "text", mode: "lexical_only", warning: "Provider missing.", results: [result] }).success).toBe(true);
    expect(searchResponseSchema.safeParse({ query: "text", mode: "hybrid", warning: "Not really hybrid.", results: [result] }).success).toBe(false);
    expect(searchResponseSchema.safeParse({ query: "text", mode: "lexical_only", warning: null, results: [result] }).success).toBe(false);
    expect(searchResponseSchema.safeParse({ query: "text", mode: "hybrid", warning: null, results: [{ ...result, chunkIds: ["chunk-2"] }] }).success).toBe(false);
    expect(searchResponseSchema.safeParse({ query: "text", mode: "hybrid", warning: null, results: [{ ...result, pageEnd: 1 }] }).success).toBe(false);
  });

  it("polls and cancels encoded job identifiers", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/v1/index-jobs/job%2F1/cancel")) return jsonResponse({ ...indexJob, id: "job/1", status: "cancel_requested", cancelRequested: true });
      return jsonResponse({ ...indexJob, id: "job/1" });
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await client.getIndexJob("job/1");
    await client.cancelIndexJob("job/1");

    const [getUrl, getInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [cancelUrl, cancelInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(getUrl).toBe("http://127.0.0.1:8080/v1/index-jobs/job%2F1");
    expect(getInit.method).toBeUndefined();
    expect(cancelUrl).toBe("http://127.0.0.1:8080/v1/index-jobs/job%2F1/cancel");
    expect(cancelInit.method).toBe("POST");
  });

  it("lists jobs, retries documents, and accepts an empty 204 delete response", async () => {
    const document = { id: "doc/1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "failed", pageCount: 0, chunkCount: 0, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: "interrupted", courseIds: [], ...pendingCapability };
    const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.includes("/v1/index-jobs?")) return jsonResponse({ jobs: [{ ...indexJob, documentId: "doc/1" }] });
      if (url.endsWith("/retry")) return jsonResponse({ document, job: { ...indexJob, documentId: "doc/1" } }, 202);
      return new Response(null, { status: 204 });
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await client.listIndexJobs("doc/1");
    await client.retryDocument("doc/1");
    await client.deleteDocument("doc/1");

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:8080/v1/index-jobs?documentId=doc%2F1",
      "http://127.0.0.1:8080/v1/documents/doc%2F1/retry",
      "http://127.0.0.1:8080/v1/documents/doc%2F1",
    ]);
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).method).toBe("POST");
    expect((fetchMock.mock.calls[2]?.[1] as RequestInit).method).toBe("DELETE");
  });

  it("queues an encoded embedding-only reindex as an HTTP 202 operation", async () => {
    const document = { id: "doc/1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "indexed", pageCount: 1, chunkCount: 2, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null, courseIds: [], indexState: "needs-reindex", embeddingStatus: "needs-reindex", embeddingModel: "ollama: fixture@v2 (3 dimensions)", embeddingError: null, retrievalWarning: "Reindex required.", providerConfigured: true } as const;
    const reindexJob = { ...indexJob, documentId: "doc/1", operation: "embedding_reindex", stage: "embedding" } as const;
    const fetchMock = vi.fn(async () => jsonResponse({ document, job: reindexJob }, 202));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.reindexDocumentEmbeddings("doc/1")).resolves.toMatchObject({ job: { operation: "embedding_reindex" } });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8080/v1/documents/doc%2F1/embedding-reindex");
    expect(init.method).toBe("POST");
  });

  it("rejects DELETE responses that are not an empty HTTP 204", async () => {
    const wrongStatus = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => new Response(null, { status: 200 })) as unknown as typeof fetch,
    );
    const declaredBody = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => new Response(null, { status: 204, headers: { "Content-Length": "1" } })) as unknown as typeof fetch,
    );
    const streamedBody = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => {
        const response = new Response("unexpected", { status: 200, headers: { "Content-Length": "0" } });
        Object.defineProperty(response, "status", { value: 204 });
        Object.defineProperty(response, "ok", { value: true });
        return response;
      }) as unknown as typeof fetch,
    );

    await expect(wrongStatus.deleteDocument("doc-1")).rejects.toMatchObject({ status: 200 });
    await expect(declaredBody.deleteDocument("doc-1")).rejects.toBeInstanceOf(LearningCoreSchemaError);
    await expect(streamedBody.deleteDocument("doc-1")).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("links and unlinks an encoded document/course relationship without deleting the document", async () => {
    const document = { id: "doc/1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "indexed", pageCount: 1, chunkCount: 2, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null, courseIds: ["course-a", "course/b"], ...pendingCapability };
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => init?.method === "POST"
      ? jsonResponse({ document, linked: true })
      : new Response(null, { status: 204 }));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.linkDocumentCourse("doc/1", "course/b")).resolves.toMatchObject({ linked: true, document: { courseIds: ["course-a", "course/b"] } });
    await client.unlinkDocumentCourse("doc/1", "course/b");

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:8080/v1/documents/doc%2F1/courses/course%2Fb",
      "http://127.0.0.1:8080/v1/documents/doc%2F1/courses/course%2Fb",
    ]);
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).method).toBe("POST");
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).method).toBe("DELETE");
  });
});

const metadataEvent = {
  runId: "run-1",
  conversationId: "conversation-1",
  provider: { kind: "ollama", model: "fixture", version: "v1" },
  retrievalLimit: 8,
};
const retrievalChunk = {
  sourceIndex: 1,
  chunkIds: ["chunk-1"],
  documentId: "doc-1",
  documentName: "notes.txt",
  pageNumber: 2,
  pageEnd: 2,
  sectionPath: ["Vectors"],
  text: "方向 remains stable in this source.",
  courseIds: ["course-1"],
};
const answerCitation = {
  citationId: "citation-1",
  sourceIndex: 1,
  chunkId: "chunk-1",
  documentId: "doc-1",
  documentName: "notes.txt",
  pageNumber: 2,
  sectionPath: ["Vectors"],
  excerpt: "方向 remains stable",
  bbox: null,
};

function sseEvent(event: string, data: unknown, lineEnding = "\n") {
  return `event: ${event}${lineEnding}data: ${JSON.stringify(data)}${lineEnding}${lineEnding}`;
}

function sseResponse(parts: Uint8Array[] | string, contentType = "text/event-stream; charset=utf-8") {
  const encoded = typeof parts === "string" ? [new TextEncoder().encode(parts)] : parts;
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      encoded.forEach((part) => controller.enqueue(part));
      controller.close();
    },
  }), { status: 200, headers: { "Content-Type": contentType } });
}

describe("LearningCoreClient answer SSE contract", () => {
  it("parses CRLF records split across UTF-8 boundaries and validates citations", async () => {
    const wire = [
      sseEvent("metadata", metadataEvent, "\r\n"),
      sseEvent("retrieval", { mode: "lexical_only", warning: "Embeddings unavailable.", chunks: [retrievalChunk] }, "\r\n"),
      sseEvent("warning", { code: "lexical_only", message: "Embeddings unavailable.", retryable: false }, "\r\n"),
      sseEvent("delta", { text: "方向" }, "\r\n"),
      sseEvent("citation", answerCitation, "\r\n"),
      sseEvent("done", { runId: "run-1", finishReason: "stop", grounded: true, citationCount: 1, citationValidation: "structural_only" }, "\r\n"),
    ].join("");
    const bytes = new TextEncoder().encode(wire);
    const direction = new TextEncoder().encode("方向");
    const start = bytes.findIndex((_, index) => direction.every((byte, offset) => bytes[index + offset] === byte));
    const parts = [bytes.slice(0, start + 1), bytes.slice(start + 1, start + 4), bytes.slice(start + 4)];
    const fetchMock = vi.fn(async () => sseResponse(parts));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    const events = [];
    for await (const event of client.answerStream({ question: "Why?", courseId: "course-1", conversationId: "conversation-1", retrievalLimit: 8 })) events.push(event);

    expect(events.map((event) => event.type)).toEqual(["metadata", "retrieval", "warning", "delta", "citation", "done"]);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
    expect(JSON.parse(String(init.body))).toEqual({ question: "Why?", courseId: "course-1", conversationId: "conversation-1", retrievalLimit: 8 });
  });

  it("accepts a provider-missing terminal error after metadata", async () => {
    const wire = sseEvent("metadata", { ...metadataEvent, provider: null })
      + sseEvent("error", { runId: "run-1", code: "provider_missing", message: "No local generation provider is configured.", retryable: false });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(wire)) as unknown as typeof fetch);
    const events = [];
    for await (const event of client.answerStream({ question: "Why?" })) events.push(event);
    expect(events.at(-1)).toMatchObject({ type: "error", data: { code: "provider_missing", retryable: false } });
  });

  it.each([
    ["wrong media type", sseEvent("metadata", metadataEvent), "text/event-streaming"],
    ["event before metadata", sseEvent("delta", { text: "bad" }), "text/event-stream"],
    ["unknown event", sseEvent("metadata", metadataEvent) + sseEvent("tool", { name: "unsafe" }), "text/event-stream"],
    ["missing terminal", sseEvent("metadata", metadataEvent), "text/event-stream"],
    ["duplicate terminal", sseEvent("metadata", metadataEvent) + sseEvent("error", { runId: "run-1", code: "failed", message: "failed", retryable: true }) + sseEvent("error", { runId: "run-1", code: "failed", message: "failed", retryable: true }), "text/event-stream"],
  ])("fails closed on %s", async (_label, wire, contentType) => {
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(wire, contentType)) as unknown as typeof fetch);
    const read = async () => {
      for await (const _event of client.answerStream({ question: "Why?" })) void _event;
    };
    await expect(read()).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("rejects citation fields that do not map to the retrieved source", async () => {
    const wire = sseEvent("metadata", metadataEvent)
      + sseEvent("retrieval", { mode: "hybrid", warning: null, chunks: [retrievalChunk] })
      + sseEvent("citation", { ...answerCitation, documentId: "invented-document" })
      + sseEvent("done", { runId: "run-1", finishReason: "stop", grounded: true, citationCount: 1, citationValidation: "structural_only" });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(wire)) as unknown as typeof fetch);
    const read = async () => {
      for await (const _event of client.answerStream({ question: "Why?" })) void _event;
    };
    await expect(read()).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("forwards AbortSignal to the streaming transport", async () => {
    const controller = new AbortController();
    let receivedSignal: AbortSignal | null = null;
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      receivedSignal = init?.signal as AbortSignal;
      return await new Promise<Response>((_resolve, reject) => {
        receivedSignal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    const pending = client.answerStream({ question: "Why?" }, { signal: controller.signal }).next();
    await vi.waitFor(() => expect(receivedSignal).toBe(controller.signal));
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("accepts citation excerpts with equivalent Unicode whitespace", async () => {
    const whitespaceSource = { ...retrievalChunk, text: "方向\nremains\t stable in this source." };
    const whitespaceCitation = { ...answerCitation, excerpt: "方向 remains stable" };
    const wire = sseEvent("metadata", metadataEvent)
      + sseEvent("retrieval", { mode: "hybrid", warning: null, chunks: [whitespaceSource] })
      + sseEvent("citation", whitespaceCitation)
      + sseEvent("done", { runId: "run-1", finishReason: "stop", grounded: true, citationCount: 1, citationValidation: "structural_only" });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(wire)) as unknown as typeof fetch);
    const events = [];
    for await (const event of client.answerStream({ question: "Why?" })) events.push(event);
    expect(events.map((event) => event.type)).toEqual(["metadata", "retrieval", "citation", "done"]);
  });
});

describe("LearningCoreClient authenticated document content", () => {
  it("fetches encoded document content with bearer authentication and a bounded PDF body", async () => {
    const bytes = new TextEncoder().encode("%PDF-1.7 fixture");
    const fetchMock = vi.fn(async () => new Response(bytes, {
      status: 200,
      headers: { "Content-Type": "application/pdf", "Content-Length": String(bytes.byteLength) },
    }));
    const controller = new AbortController();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    const content = await client.getDocumentContent("doc/one", { signal: controller.signal });

    expect(new TextDecoder().decode(content.data)).toBe("%PDF-1.7 fixture");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8080/v1/documents/doc%2Fone/content");
    expect(new Headers(init.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(new Headers(init.headers).get("Accept")).toBe("application/pdf");
    expect(init.signal).toBe(controller.signal);
  });

  it("rejects non-PDF and oversized content before exposing it to the viewer", async () => {
    const nonPdf = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => new Response("text", { headers: { "Content-Type": "text/plain" } })) as unknown as typeof fetch);
    const oversized = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => new Response("%PDF", { headers: { "Content-Type": "application/pdf", "Content-Length": String(33 * 1024 * 1024) } })) as unknown as typeof fetch);

    await expect(nonPdf.getDocumentContent("doc-1")).rejects.toMatchObject({ reason: "non_pdf" });
    await expect(oversized.getDocumentContent("doc-1")).rejects.toMatchObject({ reason: "too_large" });
    await expect(nonPdf.getDocumentContent("doc-1")).rejects.toBeInstanceOf(LearningCoreDocumentContentError);
  });

  it("rejects an application/pdf response without the PDF magic header", async () => {
    const corrupted = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => new Response("not a PDF", { headers: { "Content-Type": "application/pdf" } })) as unknown as typeof fetch);
    await expect(corrupted.getDocumentContent("doc-1")).rejects.toMatchObject({ reason: "invalid_body" });
  });

  it("strictly validates PDF bottom-left citation geometry", () => {
    const bbox = { x0: 10, y0: 20, x1: 110, y1: 70, pageWidth: 600, pageHeight: 800, coordinateSystem: "pdf_bottom_left" };
    expect(answerCitationSchema.safeParse({ ...answerCitation, bbox }).success).toBe(true);
    expect(answerCitationSchema.safeParse({ ...answerCitation, bbox: { ...bbox, y1: 900 } }).success).toBe(false);
    expect(answerCitationSchema.safeParse({ ...answerCitation, bbox: { ...bbox, coordinateSystem: "css_top_left" } }).success).toBe(false);
  });
});
