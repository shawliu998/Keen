import {
  createLearningCoreClient,
  InvalidLearningCoreUrlError,
  LearningCoreResponseError,
  LearningCoreSchemaError,
  sidecarConnectionSchema,
} from "@keen/api-client";

const token = "a".repeat(64);
const health = { status: "ok", service: "keen-learning-core", version: "0.1.0" };

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
    expect(sidecarConnectionSchema.safeParse({ available: true, port: 8080, baseUrl: "http://127.0.0.1:8080", token: `${"a".repeat(32)}\n`, status: "ready" }).success).toBe(false);
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
      document: { id: "doc-1", name: "notes.txt", mimeType: "text/plain", sizeBytes: 5, contentHash: "c".repeat(64), status: "queued", pageCount: 0, chunkCount: 0, parser: "plain-text", createdAt: "2026-07-15T12:00:00+00:00", error: null },
      duplicate: false,
    };
    const fetchMock = vi.fn(async () => jsonResponse(imported, 201));
    const controller = new AbortController();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await client.uploadDocument(new File(["hello"], "notes.txt", { type: "text/plain" }), undefined, { signal: controller.signal });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8080/v1/documents/import");
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    expect(init.signal).toBe(controller.signal);
  });
});
