import { z, type ZodType } from "zod";
import {
  agentCancelResponseSchema,
  agentMutationActionRequestSchema,
  agentMutationActionResponseSchema,
  agentRunCreateRequestSchema,
  agentRunEventSchema,
  agentRunSchema,
  type AgentCancelResponse,
  type AgentMutationActionRequest,
  type AgentMutationActionResponse,
  type AgentRun,
  type AgentRunCreateRequest,
  type AgentRunEvent,
} from "./agentSchemas";
import {
  answerStreamEventSchema,
  demoStateSchema,
  documentCourseLinkResponseSchema,
  documentEmbeddingReindexResponseSchema,
  documentImportResponseSchema,
  documentListResponseSchema,
  documentRetryResponseSchema,
  groundedQueryResponseSchema,
  healthResponseSchema,
  indexJobListResponseSchema,
  indexJobSchema,
  searchResponseSchema,
  type DemoState,
  type AnswerStreamEvent,
  type DocumentImportResponse,
  type DocumentCourseLinkResponse,
  type GroundedQueryResponse,
  type HealthResponse,
  type IndexJob,
  type IndexedDocument,
  type SearchResponse,
} from "./schemas";

export class InvalidLearningCoreUrlError extends Error {
  constructor() {
    super("The learning-core URL must be an HTTP URL on 127.0.0.1 with an explicit port.");
    this.name = "InvalidLearningCoreUrlError";
  }
}

export class LearningCoreResponseError extends Error {
  readonly status: number;
  readonly detail: LearningCoreErrorDetail | null;
  readonly requestId: string | null;

  constructor(status: number, detail: LearningCoreErrorDetail | null, requestId: string | null) {
    super(detail?.message ?? `The learning core returned HTTP ${status}.`);
    this.name = "LearningCoreResponseError";
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }
}

export class LearningCoreSchemaError extends Error {
  readonly path: string;

  constructor(path: string) {
    super(`The learning core returned an invalid response for ${path}.`);
    this.name = "LearningCoreSchemaError";
    this.path = path;
  }
}

export class LearningCoreRequestError extends Error {
  readonly path: string;

  constructor(path: string) {
    super(`The request for ${path} does not match the learning-core contract.`);
    this.name = "LearningCoreRequestError";
    this.path = path;
  }
}

export class AgentEventStreamDisconnectedError extends Error {
  readonly runId: string;
  readonly lastEventId: string | null;
  readonly retryable = true;

  constructor(runId: string, lastEventId: string | null) {
    super("The Agent event stream disconnected before a terminal event. Reconnect using lastEventId.");
    this.name = "AgentEventStreamDisconnectedError";
    this.runId = runId;
    this.lastEventId = lastEventId;
  }
}

export class LearningCoreDocumentContentError extends Error {
  readonly reason: "non_pdf" | "too_large" | "invalid_body";

  constructor(reason: "non_pdf" | "too_large" | "invalid_body") {
    const messages = {
      non_pdf: "The requested document is not available as a PDF.",
      too_large: "The requested PDF exceeds Keen's viewer size limit.",
      invalid_body: "The learning core returned an invalid PDF response.",
    };
    super(messages[reason]);
    this.name = "LearningCoreDocumentContentError";
    this.reason = reason;
  }
}

export type RequestOptions = { signal?: AbortSignal };
export type AgentRunEventStreamOptions = RequestOptions & {
  lastEventId?: string;
  cursor?: string;
  terminalAlreadySeen?: boolean;
};
export type SearchRequest = { query: string; courseId?: string | null; limit?: number };
export type GroundedQueryRequest = SearchRequest;
export type AnswerStreamRequest = {
  question: string;
  courseId?: string | null;
  conversationId?: string | null;
  retrievalLimit?: number;
};
export type PdfDocumentContent = { data: ArrayBuffer; contentType: "application/pdf" };

function normalizeEvidenceWhitespace(value: string): string {
  return value.normalize("NFC").replace(/\s+/gu, " ").trim();
}
type ResponseContract<T> = {
  expectedStatuses: readonly number[];
  validate?: (status: number, data: T) => boolean;
};
export type LearningCoreErrorDetail = {
  message: string;
  retryable: boolean | null;
  recovery: string | null;
  documentId: string | null;
  code: AgentResponseErrorCode | null;
};

const agentResponseErrorCodeSchema = z.enum([
  "provider_missing",
  "provider_unavailable",
  "agent_busy",
  "mutation_not_found",
  "mutation_action_forbidden",
  "run_not_terminal",
  "undo_in_progress",
  "undo_conflict",
  "idempotency_key_reused",
  "idempotency_key_terminal",
  "mutation_not_undone",
  "redo_unavailable",
  "mutation_already_undone",
  "idempotency_conflict",
  "mutation_action_failed",
]);
export type AgentResponseErrorCode = z.infer<typeof agentResponseErrorCodeSchema>;

function isAgentErrorCodeAllowedForStatus(status: number, code: AgentResponseErrorCode): boolean {
  if (status === 503) return code === "provider_missing" || code === "provider_unavailable";
  if (status === 403) return code === "mutation_action_forbidden";
  if (status === 404) return code === "mutation_not_found";
  if (status === 500) return code === "mutation_action_failed";
  if (status !== 409) return false;
  return [
    "agent_busy",
    "run_not_terminal",
    "undo_in_progress",
    "undo_conflict",
    "idempotency_key_reused",
    "idempotency_key_terminal",
    "mutation_not_undone",
    "redo_unavailable",
    "mutation_already_undone",
    "idempotency_conflict",
  ].includes(code);
}

const errorEnvelopeSchema = z.object({
  detail: z.union([
    z.string().min(1).max(4_000),
    z.object({
      message: z.string().min(1).max(4_000),
      retryable: z.boolean().optional(),
      recovery: z.string().min(1).max(4_000).optional(),
      recoveryAction: z.string().min(1).max(4_000).optional(),
      documentId: z.string().min(1).max(240).nullable().optional(),
      code: z.string().min(1).max(80).optional(),
    }).passthrough(),
  ]),
}).passthrough();

async function readBoundedText(response: Response, maximumBytes = 64 * 1024): Promise<string | null> {
  if (!response.body) return null;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let received = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > maximumBytes) {
        await reader.cancel();
        return null;
      }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } catch {
    return null;
  }
}

async function parseErrorResponse(response: Response): Promise<LearningCoreErrorDetail | null> {
  const text = await readBoundedText(response);
  if (!text) return null;
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  const parsed = errorEnvelopeSchema.safeParse(value);
  if (!parsed.success) return null;
  if (typeof parsed.data.detail === "string") {
    return { message: parsed.data.detail, retryable: null, recovery: null, documentId: null, code: null };
  }
  const code = agentResponseErrorCodeSchema.safeParse(parsed.data.detail.code);
  return {
    message: parsed.data.detail.message,
    retryable: parsed.data.detail.retryable ?? null,
    recovery: parsed.data.detail.recovery ?? parsed.data.detail.recoveryAction ?? null,
    documentId: parsed.data.detail.documentId ?? null,
    code: code.success && isAgentErrorCodeAllowedForStatus(response.status, code.data) ? code.data : null,
  };
}

async function assertExpectedStatus(
  response: Response,
  path: string,
  expectedStatuses: readonly number[],
): Promise<void> {
  if (response.ok && expectedStatuses.includes(response.status)) return;
  const requestId = response.headers.get("X-Request-ID")?.slice(0, 240) ?? null;
  const detail = response.ok
    ? {
        message: `The learning core returned unexpected HTTP ${response.status} for ${path}.`,
        retryable: null,
        recovery: null,
        documentId: null,
        code: null,
      }
    : await parseErrorResponse(response);
  throw new LearningCoreResponseError(response.status, detail, requestId);
}

async function hasEmptyBody(response: Response): Promise<boolean> {
  const contentLength = response.headers.get("Content-Length");
  if (contentLength !== null && contentLength.trim() !== "0") return false;
  if (!response.body) return true;
  const reader = response.body.getReader();
  try {
    for (let reads = 0; reads < 32; reads += 1) {
      const { done, value } = await reader.read();
      if (done) return true;
      if (value.byteLength > 0) {
        await reader.cancel();
        return false;
      }
    }
    await reader.cancel();
    return false;
  } catch {
    return false;
  }
}

function validateBaseUrl(baseUrl: string): string {
  const match = /^http:\/\/127\.0\.0\.1:(\d{1,5})\/?$/.exec(baseUrl);
  if (!match) throw new InvalidLearningCoreUrlError();
  const port = Number(match[1]);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new InvalidLearningCoreUrlError();
  }
  return `http://127.0.0.1:${port}`;
}

function assertToken(token: string): void {
  if (token.length < 32 || /[\r\n]/.test(token)) {
    throw new TypeError("A learning-core session token of at least 32 characters is required.");
  }
}

function assertAgentIdentifier(value: string, path: string): void {
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) {
    throw new LearningCoreRequestError(path);
  }
}

export class LearningCoreClient {
  readonly baseUrl: string;
  readonly #token: string;
  readonly #fetch: typeof fetch;

  constructor(baseUrl: string, token: string, fetchImplementation: typeof fetch = fetch) {
    this.baseUrl = validateBaseUrl(baseUrl);
    assertToken(token);
    this.#token = token;
    this.#fetch = fetchImplementation;
  }

  async #request<T>(
    path: string,
    schema: ZodType<T>,
    init: RequestInit & RequestOptions = {},
    contract: ResponseContract<T> = { expectedStatuses: [200] },
  ): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    headers.set("Authorization", `Bearer ${this.#token}`);
    const response = await this.#fetch(`${this.baseUrl}${path}`, { ...init, headers });
    await assertExpectedStatus(response, path, contract.expectedStatuses);
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new LearningCoreSchemaError(path);
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) throw new LearningCoreSchemaError(path);
    if (contract.validate && !contract.validate(response.status, parsed.data)) {
      throw new LearningCoreSchemaError(path);
    }
    return parsed.data;
  }

  async #requestVoid(
    path: string,
    init: RequestInit & RequestOptions = {},
    expectedStatuses: readonly number[] = [204],
  ): Promise<void> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    headers.set("Authorization", `Bearer ${this.#token}`);
    const response = await this.#fetch(`${this.baseUrl}${path}`, { ...init, headers });
    await assertExpectedStatus(response, path, expectedStatuses);
    if (!await hasEmptyBody(response)) throw new LearningCoreSchemaError(path);
  }

  health(options: RequestOptions = {}): Promise<HealthResponse> {
    return this.#request("/health", healthResponseSchema, options);
  }

  demoState(options: RequestOptions = {}): Promise<DemoState> {
    return this.#request("/v1/demo-state", demoStateSchema, options);
  }

  uploadDocument(file: File, courseId?: string, options: RequestOptions = {}): Promise<DocumentImportResponse> {
    const body = new FormData();
    body.set("file", file, file.name);
    if (courseId) body.set("course_id", courseId);
    return this.#request(
      "/v1/documents/import",
      documentImportResponseSchema,
      { method: "POST", body, signal: options.signal },
      {
        expectedStatuses: [200, 202],
        validate: (status, result) => (
          (status !== 200 || result.duplicate)
          && (courseId ? result.document.courseIds.includes(courseId) : !result.linked)
          && (result.duplicate || !courseId || result.linked)
        ),
      },
    );
  }

  listDocuments(options: RequestOptions = {}): Promise<IndexedDocument[]> {
    return this.#request("/v1/documents", documentListResponseSchema, options).then(({ documents }) => documents);
  }

  async getDocumentContent(documentId: string, options: RequestOptions = {}): Promise<PdfDocumentContent> {
    const response = await this.#fetch(`${this.baseUrl}/v1/documents/${encodeURIComponent(documentId)}/content`, {
      headers: {
        Accept: "application/pdf",
        Authorization: `Bearer ${this.#token}`,
      },
      signal: options.signal,
    });
    await assertExpectedStatus(response, "/v1/documents/{id}/content", [200]);
    const mediaType = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
    if (mediaType !== "application/pdf") {
      await response.body?.cancel();
      throw new LearningCoreDocumentContentError("non_pdf");
    }
    return {
      data: await readBoundedBytes(response, 32 * 1024 * 1024),
      contentType: "application/pdf",
    };
  }

  getIndexJob(jobId: string, options: RequestOptions = {}): Promise<IndexJob> {
    return this.#request(`/v1/index-jobs/${encodeURIComponent(jobId)}`, indexJobSchema, options);
  }

  listIndexJobs(documentId: string, options: RequestOptions = {}): Promise<IndexJob[]> {
    return this.#request(
      `/v1/index-jobs?documentId=${encodeURIComponent(documentId)}`,
      indexJobListResponseSchema,
      options,
    ).then(({ jobs }) => jobs);
  }

  cancelIndexJob(jobId: string, options: RequestOptions = {}): Promise<IndexJob> {
    return this.#request(`/v1/index-jobs/${encodeURIComponent(jobId)}/cancel`, indexJobSchema, {
      method: "POST",
      signal: options.signal,
    });
  }

  retryDocument(documentId: string, options: RequestOptions = {}) {
    return this.#request(`/v1/documents/${encodeURIComponent(documentId)}/retry`, documentRetryResponseSchema, {
      method: "POST",
      signal: options.signal,
    }, { expectedStatuses: [202] });
  }

  reindexDocumentEmbeddings(documentId: string, options: RequestOptions = {}) {
    return this.#request(
      `/v1/documents/${encodeURIComponent(documentId)}/embedding-reindex`,
      documentEmbeddingReindexResponseSchema,
      { method: "POST", signal: options.signal },
      { expectedStatuses: [202] },
    );
  }

  deleteDocument(documentId: string, options: RequestOptions = {}): Promise<void> {
    return this.#requestVoid(`/v1/documents/${encodeURIComponent(documentId)}`, {
      method: "DELETE",
      signal: options.signal,
    });
  }

  linkDocumentCourse(documentId: string, courseId: string, options: RequestOptions = {}): Promise<DocumentCourseLinkResponse> {
    return this.#request(
      `/v1/documents/${encodeURIComponent(documentId)}/courses/${encodeURIComponent(courseId)}`,
      documentCourseLinkResponseSchema,
      { method: "POST", signal: options.signal },
      { expectedStatuses: [200], validate: (_status, result) => result.document.courseIds.includes(courseId) },
    );
  }

  unlinkDocumentCourse(documentId: string, courseId: string, options: RequestOptions = {}): Promise<void> {
    return this.#requestVoid(
      `/v1/documents/${encodeURIComponent(documentId)}/courses/${encodeURIComponent(courseId)}`,
      { method: "DELETE", signal: options.signal },
    );
  }

  search(request: SearchRequest, options: RequestOptions = {}): Promise<SearchResponse> {
    return this.#request("/v1/search", searchResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: request.query,
        ...(request.courseId === undefined ? {} : { courseId: request.courseId }),
        ...(request.limit === undefined ? {} : { limit: request.limit }),
      }),
      signal: options.signal,
    });
  }

  query(request: GroundedQueryRequest, options: RequestOptions = {}): Promise<GroundedQueryResponse> {
    return this.#request("/v1/query", groundedQueryResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: request.query,
        ...(request.courseId === undefined ? {} : { courseId: request.courseId }),
        ...(request.limit === undefined ? {} : { limit: request.limit }),
      }),
      signal: options.signal,
    });
  }

  createAgentRun(request: AgentRunCreateRequest, options: RequestOptions = {}): Promise<AgentRun> {
    const parsed = agentRunCreateRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError("/v1/agent/runs");
    return this.#request("/v1/agent/runs", agentRunSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed.data),
      signal: options.signal,
    }, { expectedStatuses: [202] });
  }

  getAgentRun(runId: string, options: RequestOptions = {}): Promise<AgentRun> {
    assertAgentIdentifier(runId, "/v1/agent/runs/{id}");
    return this.#request(`/v1/agent/runs/${encodeURIComponent(runId)}`, agentRunSchema, options);
  }

  cancelAgentRun(runId: string, options: RequestOptions = {}): Promise<AgentCancelResponse> {
    assertAgentIdentifier(runId, "/v1/agent/runs/{id}/cancel");
    return this.#request(
      `/v1/agent/runs/${encodeURIComponent(runId)}/cancel`,
      agentCancelResponseSchema,
      { method: "POST", signal: options.signal },
    );
  }

  undoAgentMutation(
    runId: string,
    mutationId: string,
    request: AgentMutationActionRequest,
    options: RequestOptions = {},
  ): Promise<AgentMutationActionResponse> {
    return this.#agentMutationAction("undo", runId, mutationId, request, options);
  }

  redoAgentMutation(
    runId: string,
    mutationId: string,
    request: AgentMutationActionRequest,
    options: RequestOptions = {},
  ): Promise<AgentMutationActionResponse> {
    return this.#agentMutationAction("redo", runId, mutationId, request, options);
  }

  #agentMutationAction(
    action: "undo" | "redo",
    runId: string,
    mutationId: string,
    request: AgentMutationActionRequest,
    options: RequestOptions,
  ): Promise<AgentMutationActionResponse> {
    const contractPath = `/v1/agent/runs/{id}/mutations/{mutationId}/${action}`;
    assertAgentIdentifier(runId, contractPath);
    assertAgentIdentifier(mutationId, contractPath);
    const parsed = agentMutationActionRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(contractPath);
    return this.#request(
      `/v1/agent/runs/${encodeURIComponent(runId)}/mutations/${encodeURIComponent(mutationId)}/${action}`,
      agentMutationActionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.action === action
          && result.runId === runId
          && result.targetMutationId === mutationId
        ),
      },
    );
  }

  async *agentRunEvents(
    runId: string,
    options: AgentRunEventStreamOptions = {},
  ): AsyncGenerator<AgentRunEvent> {
    const path = "/v1/agent/runs/{id}/events";
    assertAgentIdentifier(runId, path);
    if (options.lastEventId !== undefined) assertAgentIdentifier(options.lastEventId, path);
    if (options.cursor !== undefined) assertAgentIdentifier(options.cursor, path);
    if (
      options.lastEventId !== undefined
      && options.cursor !== undefined
      && options.lastEventId !== options.cursor
    ) {
      throw new LearningCoreRequestError(path);
    }
    const query = options.cursor === undefined ? "" : `?cursor=${encodeURIComponent(options.cursor)}`;
    const headers = new Headers({
      Accept: "text/event-stream",
      Authorization: `Bearer ${this.#token}`,
    });
    if (options.lastEventId !== undefined) headers.set("Last-Event-ID", options.lastEventId);
    const response = await this.#fetch(
      `${this.baseUrl}/v1/agent/runs/${encodeURIComponent(runId)}/events${query}`,
      { headers, signal: options.signal },
    );
    await assertExpectedStatus(response, path, [200]);
    const mediaType = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
    if (mediaType !== "text/event-stream" || !response.body) throw new LearningCoreSchemaError(path);

    let terminalSeen = false;
    let lastEventId = options.lastEventId ?? options.cursor ?? null;
    const resumeAfterId = lastEventId;
    const receivedIds = new Set<string>();
    try {
      for await (const record of parseServerSentEvents(response.body, path)) {
        if (
          record.id === null
          || record.id === resumeAfterId
          || receivedIds.has(record.id)
        ) {
          throw new LearningCoreSchemaError(path);
        }
        let data: unknown;
        try {
          data = JSON.parse(record.data);
        } catch {
          throw new LearningCoreSchemaError(path);
        }
        const parsed = agentRunEventSchema.safeParse({ id: record.id, type: record.event, data });
        if (!parsed.success) throw new LearningCoreSchemaError(path);
        const event = parsed.data;
        if (event.type === "metadata" && event.data.runId !== runId) throw new LearningCoreSchemaError(path);
        if (event.type === "done" || event.type === "error") terminalSeen = true;
        receivedIds.add(event.id);
        lastEventId = event.id;
        yield event;
      }
    } catch (error) {
      if (
        error instanceof LearningCoreSchemaError
        || (error instanceof Error && error.name === "AbortError")
      ) {
        throw error;
      }
      throw new AgentEventStreamDisconnectedError(runId, lastEventId);
    }
    if (!terminalSeen && !options.terminalAlreadySeen) {
      throw new AgentEventStreamDisconnectedError(runId, lastEventId);
    }
  }

  async *answerStream(
    request: AnswerStreamRequest,
    options: RequestOptions = {},
  ): AsyncGenerator<AnswerStreamEvent> {
    const response = await this.#fetch(`${this.baseUrl}/v1/answer/stream`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        Authorization: `Bearer ${this.#token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: request.question,
        ...(request.courseId === undefined ? {} : { courseId: request.courseId }),
        ...(request.conversationId === undefined ? {} : { conversationId: request.conversationId }),
        ...(request.retrievalLimit === undefined ? {} : { retrievalLimit: request.retrievalLimit }),
      }),
      signal: options.signal,
    });
    await assertExpectedStatus(response, "/v1/answer/stream", [200]);
    const mediaType = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
    if (mediaType !== "text/event-stream" || !response.body) {
      throw new LearningCoreSchemaError("/v1/answer/stream");
    }

    let phase: "start" | "metadata" | "retrieval" | "terminal" = "start";
    let runId: string | null = null;
    const sources = new Map<number, Extract<AnswerStreamEvent, { type: "retrieval" }>["data"]["chunks"][number]>();
    const citationIds = new Set<string>();
    for await (const record of parseServerSentEvents(response.body, "/v1/answer/stream")) {
      let data: unknown;
      try {
        data = JSON.parse(record.data);
      } catch {
        throw new LearningCoreSchemaError("/v1/answer/stream");
      }
      const parsed = answerStreamEventSchema.safeParse({ type: record.event, data });
      if (!parsed.success || phase === "terminal") throw new LearningCoreSchemaError("/v1/answer/stream");
      const event = parsed.data;
      if (phase === "start") {
        if (event.type !== "metadata") throw new LearningCoreSchemaError("/v1/answer/stream");
        if (
          (request.conversationId != null && event.data.conversationId !== request.conversationId)
          || (request.retrievalLimit !== undefined && event.data.retrievalLimit !== request.retrievalLimit)
        ) {
          throw new LearningCoreSchemaError("/v1/answer/stream");
        }
        runId = event.data.runId;
        phase = "metadata";
      } else if (event.type === "metadata") {
        throw new LearningCoreSchemaError("/v1/answer/stream");
      } else if (event.type === "retrieval") {
        if (phase !== "metadata") throw new LearningCoreSchemaError("/v1/answer/stream");
        const seenChunkIds = new Set<string>();
        for (const [index, source] of event.data.chunks.entries()) {
          if (sources.has(source.sourceIndex) || source.chunkIds.some((chunkId) => seenChunkIds.has(chunkId))) {
            throw new LearningCoreSchemaError("/v1/answer/stream");
          }
          if (source.sourceIndex !== index + 1 || (request.courseId && !source.courseIds.includes(request.courseId))) {
            throw new LearningCoreSchemaError("/v1/answer/stream");
          }
          source.chunkIds.forEach((chunkId) => seenChunkIds.add(chunkId));
          sources.set(source.sourceIndex, source);
        }
        phase = "retrieval";
      } else if (event.type === "delta") {
        if (phase !== "retrieval") throw new LearningCoreSchemaError("/v1/answer/stream");
      } else if (event.type === "warning") {
        if (phase !== "retrieval") throw new LearningCoreSchemaError("/v1/answer/stream");
      } else if (event.type === "citation") {
        const source = sources.get(event.data.sourceIndex);
        if (
          phase !== "retrieval"
          || !source
          || citationIds.has(event.data.citationId)
          || !source.chunkIds.includes(event.data.chunkId)
          || source.documentId !== event.data.documentId
          || source.documentName !== event.data.documentName
          || event.data.pageNumber < source.pageNumber
          || event.data.pageNumber > source.pageEnd
          || source.sectionPath.join("\u0000") !== event.data.sectionPath.join("\u0000")
          || !normalizeEvidenceWhitespace(source.text).includes(normalizeEvidenceWhitespace(event.data.excerpt))
        ) {
          throw new LearningCoreSchemaError("/v1/answer/stream");
        }
        citationIds.add(event.data.citationId);
      } else if (event.type === "done") {
        if (
          phase !== "retrieval"
          || event.data.runId !== runId
          || event.data.citationCount !== citationIds.size
          || event.data.grounded !== (citationIds.size > 0)
        ) {
          throw new LearningCoreSchemaError("/v1/answer/stream");
        }
        phase = "terminal";
      } else if (event.type === "error") {
        if (event.data.runId !== runId) throw new LearningCoreSchemaError("/v1/answer/stream");
        phase = "terminal";
      }
      yield event;
    }
    if (phase !== "terminal") throw new LearningCoreSchemaError("/v1/answer/stream");
  }
}

type SseRecord = { id: string | null; event: string; data: string };
const MAX_SSE_BUFFER_BYTES = 1024 * 1024;
const MAX_SSE_STREAM_BYTES = 8 * 1024 * 1024;

async function* parseServerSentEvents(
  body: ReadableStream<Uint8Array>,
  path: string,
): AsyncGenerator<SseRecord> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "";
  let totalBytes = 0;
  let eventBytes = 0;
  let eventId: string | null = null;
  let eventName: string | null = null;
  let dataLines: string[] = [];
  let finishedReading = false;

  const consumeLine = (lineWithPossibleCr: string): SseRecord | null => {
    const line = lineWithPossibleCr.endsWith("\r") ? lineWithPossibleCr.slice(0, -1) : lineWithPossibleCr;
    eventBytes += new TextEncoder().encode(line).byteLength + 1;
    if (eventBytes > MAX_SSE_BUFFER_BYTES) throw new LearningCoreSchemaError(path);
    if (line === "") {
      if (eventName === null && dataLines.length === 0) {
        eventBytes = 0;
        return null;
      }
      if (eventName === null || dataLines.length === 0) throw new LearningCoreSchemaError(path);
      const record = { id: eventId, event: eventName, data: dataLines.join("\n") };
      eventId = null;
      eventName = null;
      dataLines = [];
      eventBytes = 0;
      return record;
    }
    if (line.startsWith(":")) return null;
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id" && eventId === null && value) {
      eventId = value;
      return null;
    }
    if (field === "event" && eventName === null && value) {
      eventName = value;
      return null;
    }
    if (field === "data") {
      dataLines.push(value);
      return null;
    }
    throw new LearningCoreSchemaError(path);
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        finishedReading = true;
        break;
      }
      totalBytes += value.byteLength;
      if (totalBytes > MAX_SSE_STREAM_BYTES) throw new LearningCoreSchemaError(path);
      try {
        buffer += decoder.decode(value, { stream: true });
      } catch {
        throw new LearningCoreSchemaError(path);
      }
      let lineEnd = buffer.indexOf("\n");
      while (lineEnd >= 0) {
        const line = buffer.slice(0, lineEnd);
        buffer = buffer.slice(lineEnd + 1);
        if (new TextEncoder().encode(buffer).byteLength > MAX_SSE_BUFFER_BYTES) {
          throw new LearningCoreSchemaError(path);
        }
        const record = consumeLine(line);
        if (record) yield record;
        lineEnd = buffer.indexOf("\n");
      }
    }
    try {
      buffer += decoder.decode();
    } catch {
      throw new LearningCoreSchemaError(path);
    }
    if (buffer !== "") {
      const record = consumeLine(buffer);
      if (record) yield record;
    }
    const finalRecord = consumeLine("");
    if (finalRecord) yield finalRecord;
  } finally {
    if (!finishedReading) {
      try {
        await reader.cancel();
      } catch {
        // The transport may already be aborted or disconnected.
      }
    }
    reader.releaseLock();
  }
}

async function readBoundedBytes(response: Response, maximumBytes: number): Promise<ArrayBuffer> {
  const declaredLength = response.headers.get("Content-Length");
  if (declaredLength !== null) {
    const parsedLength = Number(declaredLength);
    if (!Number.isSafeInteger(parsedLength) || parsedLength <= 0) {
      await response.body?.cancel();
      throw new LearningCoreDocumentContentError("invalid_body");
    }
    if (parsedLength > maximumBytes) {
      await response.body?.cancel();
      throw new LearningCoreDocumentContentError("too_large");
    }
  }
  if (!response.body) throw new LearningCoreDocumentContentError("invalid_body");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > maximumBytes) {
        await reader.cancel();
        throw new LearningCoreDocumentContentError("too_large");
      }
      chunks.push(value);
    }
  } catch (error) {
    if (error instanceof LearningCoreDocumentContentError) throw error;
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new LearningCoreDocumentContentError("invalid_body");
  } finally {
    reader.releaseLock();
  }
  if (received === 0 || (declaredLength !== null && received !== Number(declaredLength))) {
    throw new LearningCoreDocumentContentError("invalid_body");
  }
  const output = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  if (output.byteLength < 5 || output[0] !== 0x25 || output[1] !== 0x50 || output[2] !== 0x44 || output[3] !== 0x46 || output[4] !== 0x2d) {
    throw new LearningCoreDocumentContentError("invalid_body");
  }
  return output.buffer;
}

export function createLearningCoreClient(baseUrl: string, token: string, fetchImplementation?: typeof fetch) {
  return new LearningCoreClient(baseUrl, token, fetchImplementation);
}
