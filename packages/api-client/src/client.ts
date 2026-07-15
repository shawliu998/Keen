import { z, type ZodType } from "zod";
import {
  demoStateSchema,
  documentImportResponseSchema,
  documentListResponseSchema,
  groundedQueryResponseSchema,
  healthResponseSchema,
  searchResponseSchema,
  type DemoState,
  type DocumentImportResponse,
  type GroundedQueryResponse,
  type HealthResponse,
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

export type RequestOptions = { signal?: AbortSignal };
export type SearchRequest = { query: string; courseId?: string | null; limit?: number };
export type GroundedQueryRequest = SearchRequest;
export type LearningCoreErrorDetail = {
  message: string;
  retryable: boolean | null;
  recovery: string | null;
  documentId: string | null;
};

const errorEnvelopeSchema = z.object({
  detail: z.union([
    z.string().min(1).max(4_000),
    z.object({
      message: z.string().min(1).max(4_000),
      retryable: z.boolean().optional(),
      recovery: z.string().min(1).max(4_000).optional(),
      documentId: z.string().min(1).max(240).nullable().optional(),
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
    return { message: parsed.data.detail, retryable: null, recovery: null, documentId: null };
  }
  return {
    message: parsed.data.detail.message,
    retryable: parsed.data.detail.retryable ?? null,
    recovery: parsed.data.detail.recovery ?? null,
    documentId: parsed.data.detail.documentId ?? null,
  };
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
  ): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    headers.set("Authorization", `Bearer ${this.#token}`);
    const response = await this.#fetch(`${this.baseUrl}${path}`, { ...init, headers });
    if (!response.ok) {
      const requestId = response.headers.get("X-Request-ID")?.slice(0, 240) ?? null;
      throw new LearningCoreResponseError(
        response.status,
        await parseErrorResponse(response),
        requestId,
      );
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new LearningCoreSchemaError(path);
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) throw new LearningCoreSchemaError(path);
    return parsed.data;
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
    return this.#request("/v1/documents/import", documentImportResponseSchema, {
      method: "POST",
      body,
      signal: options.signal,
    });
  }

  listDocuments(options: RequestOptions = {}): Promise<IndexedDocument[]> {
    return this.#request("/v1/documents", documentListResponseSchema, options).then(({ documents }) => documents);
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
}

export function createLearningCoreClient(baseUrl: string, token: string, fetchImplementation?: typeof fetch) {
  return new LearningCoreClient(baseUrl, token, fetchImplementation);
}
