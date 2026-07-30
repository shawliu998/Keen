import { z, type ZodType } from "zod";
import {
  agentCancelResponseSchema,
  agentMutationActionRequestSchema,
  agentMutationActionResponseSchema,
  agentLevel2ApprovalRequestSchema,
  agentLevel2ApprovalResponseSchema,
  agentLevel2PendingActionsResponseSchema,
  agentRunCreateRequestSchema,
  agentRunActivityContextSchema,
  agentRunActivitySchema,
  agentRunEventSchema,
  agentRunSchema,
  type AgentCancelResponse,
  type AgentMutationActionRequest,
  type AgentMutationActionResponse,
  type AgentLevel2ApprovalRequest,
  type AgentLevel2ApprovalResponse,
  type AgentLevel2PendingActionsResponse,
  type AgentRun,
  type AgentRunActivity,
  type AgentRunActivityContext,
  type AgentRunCreateRequest,
  type AgentRunEvent,
} from "./agentSchemas";
import {
  learningInterventionCreateRequestSchema,
  learningInterventionEventSchema,
  learningInterventionResponseSchema,
  type LearningInterventionCreateRequest,
  type LearningInterventionEvent,
  type LearningInterventionResponse,
} from "./interventionSchemas";
import {
  studyPlanProposalCreateRequestSchema,
  studyPlanProposalDecisionRequestSchema,
  studyPlanProposalResponseSchema,
  studyPlanProposalUndoRequestSchema,
  type StudyPlanProposalCreateRequest,
  type StudyPlanProposalDecisionRequest,
  type StudyPlanProposalResponse,
  type StudyPlanProposalUndoRequest,
} from "./planProposalSchemas";
import {
  answerStreamEventSchema,
  conversationCancelRequestSchema,
  conversationCancelResponseSchema,
  conversationCreateRequestSchema,
  conversationCreateResponseSchema,
  conversationListResponseSchema,
  conversationSchema,
  durableAnswerStreamRequestSchema,
  durableConversationMessageSchema,
  durableConversationMessagesResponseSchema,
  autonomousRecommendationRequestSchema,
  autonomousRecommendationResponseSchema,
  autonomousStudySessionRequestSchema,
  autonomousStudySessionStartResponseSchema,
  focusedStudyRequestSchema,
  focusedStudyResponseSchema,
  activeRecallAnswerRequestSchema,
  activeRecallProgressionRequestSchema,
  activeRecallProgressionResponseSchema,
  activeRecallReadResponseSchema,
  adaptiveActionCompleteRequestSchema,
  adaptiveActionCompleteResponseSchema,
  adaptiveStateResponseSchema,
  targetedPracticeAnswerRequestSchema,
  targetedPracticeProgressionRequestSchema,
  targetedPracticeProgressionResponseSchema,
  targetedPracticeReadResponseSchema,
  studySummaryFinalizeResponseSchema,
  studySummaryReadResponseSchema,
  studySummaryRequestSchema,
  dueReviewListResponseSchema,
  reviewAttemptRequestSchema,
  reviewAttemptResponseSchema,
  courseCreateRequestSchema,
  courseCreateResponseSchema,
  diagnosticAnswerRequestSchema,
  diagnosticProgressionRequestSchema,
  diagnosticProgressionResponseSchema,
  diagnosticReadResponseSchema,
  demoStateSchema,
  documentCourseLinkResponseSchema,
  documentEmbeddingReindexResponseSchema,
  documentImportResponseSchema,
  documentListResponseSchema,
  documentRetryResponseSchema,
  groundedQueryResponseSchema,
  healthResponseSchema,
  providerConnectionTestResponseSchema,
  indexJobListResponseSchema,
  indexJobSchema,
  learningSnapshotSchema,
  studySessionControlRequestSchema,
  studySessionControlResponseSchema,
  studySessionReadResponseSchema,
  studySessionListResponseSchema,
  searchResponseSchema,
  type DemoState,
  type CourseCreateRequest,
  type CourseCreateResponse,
  type DiagnosticAnswerRequest,
  type DiagnosticProgressionRequest,
  type DiagnosticProgressionResponse,
  type DiagnosticReadResponse,
  type AnswerStreamEvent,
  type Conversation,
  type ConversationCancelRequest,
  type ConversationCancelResponse,
  type ConversationCreateRequest,
  type ConversationCreateResponse,
  type ConversationListResponse,
  type DurableAnswerStreamRequest,
  type DurableConversationMessage,
  type DurableConversationMessagesResponse,
  type AutonomousRecommendationRequest,
  type AutonomousRecommendationResponse,
  type AutonomousStudySessionRequest,
  type AutonomousStudySessionStartResponse,
  type FocusedStudyRequest,
  type FocusedStudyResponse,
  type ActiveRecallAnswerRequest,
  type ActiveRecallProgressionRequest,
  type ActiveRecallProgressionResponse,
  type ActiveRecallReadResponse,
  type AdaptiveActionCompleteRequest,
  type AdaptiveActionCompleteResponse,
  type AdaptiveStateResponse,
  type TargetedPracticeAnswerRequest,
  type TargetedPracticeProgressionRequest,
  type TargetedPracticeProgressionResponse,
  type TargetedPracticeReadResponse,
  type StudySummaryFinalizeResponse,
  type StudySummaryReadResponse,
  type StudySummaryRequest,
  type DueReviewListResponse,
  type ReviewAttemptRequest,
  type ReviewAttemptResponse,
  type DocumentImportResponse,
  type DocumentCourseLinkResponse,
  type GroundedQueryResponse,
  type HealthResponse,
  type ProviderConnectionTestResponse,
  type IndexJob,
  type IndexedDocument,
  type LearningSnapshot,
  type StudySessionControlRequest,
  type StudySessionControlResponse,
  type StudySessionReadResponse,
  type StudySessionListResponse,
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
export type LearningInterventionEventStreamOptions = AgentRunEventStreamOptions;
export type SearchRequest = { query: string; courseId?: string | null; limit?: number };
export type GroundedQueryRequest = SearchRequest;
export type LearningSnapshotRequest = { courseId: string; availableMinutes: number };
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
  code: LearningCoreResponseErrorCode | null;
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
  "approval_conflict",
  "approval_action_failed",
]);
export type AgentResponseErrorCode = z.infer<typeof agentResponseErrorCodeSchema>;

const reviewResponseErrorCodeSchema = z.enum([
  "review_queue_temporarily_unavailable",
  "review_task_not_found",
  "review_task_context_conflict",
  "review_item_not_found",
  "review_attempt_conflict",
  "review_attempt_idempotency_conflict",
  "review_attempt_temporarily_unavailable",
]);
export type ReviewResponseErrorCode = z.infer<typeof reviewResponseErrorCodeSchema>;
export type LearningCoreResponseErrorCode = AgentResponseErrorCode | ReviewResponseErrorCode;

function isAgentErrorCodeAllowedForStatus(status: number, code: AgentResponseErrorCode): boolean {
  if (status === 503) return code === "provider_missing" || code === "provider_unavailable";
  if (status === 403) return code === "mutation_action_forbidden";
  if (status === 404) return code === "mutation_not_found";
  if (status === 500) return code === "mutation_action_failed" || code === "approval_action_failed";
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
    "approval_conflict",
  ].includes(code);
}

function isReviewErrorCodeAllowedForStatus(status: number, code: ReviewResponseErrorCode): boolean {
  if (status === 404) return code === "review_task_not_found" || code === "review_item_not_found";
  if (status === 503) return code === "review_queue_temporarily_unavailable" || code === "review_attempt_temporarily_unavailable";
  if (status !== 409) return false;
  return [
    "review_task_context_conflict",
    "review_attempt_conflict",
    "review_attempt_idempotency_conflict",
  ].includes(code);
}

const learningCoreResponseErrorCodeSchema = z.union([
  agentResponseErrorCodeSchema,
  reviewResponseErrorCodeSchema,
]);

function isLearningCoreErrorCodeAllowedForStatus(status: number, code: LearningCoreResponseErrorCode): boolean {
  return agentResponseErrorCodeSchema.safeParse(code).success
    ? isAgentErrorCodeAllowedForStatus(status, code as AgentResponseErrorCode)
    : isReviewErrorCodeAllowedForStatus(status, code as ReviewResponseErrorCode);
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
  const code = learningCoreResponseErrorCodeSchema.safeParse(parsed.data.detail.code);
  return {
    message: parsed.data.detail.message,
    retryable: parsed.data.detail.retryable ?? null,
    recovery: parsed.data.detail.recovery ?? parsed.data.detail.recoveryAction ?? null,
    documentId: parsed.data.detail.documentId ?? null,
    code: code.success && isLearningCoreErrorCodeAllowedForStatus(response.status, code.data) ? code.data : null,
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
    this.#fetch = fetchImplementation.bind(globalThis);
  }

  async #request<Schema extends ZodType>(
    path: string,
    schema: Schema,
    init: RequestInit & RequestOptions = {},
    contract: ResponseContract<z.output<Schema>> = { expectedStatuses: [200] },
  ): Promise<z.output<Schema>> {
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

  testProvider(options: RequestOptions = {}): Promise<ProviderConnectionTestResponse> {
    return this.#request("/v1/provider/test", providerConnectionTestResponseSchema, { method: "POST", signal: options.signal });
  }

  demoState(options: RequestOptions = {}): Promise<DemoState> {
    return this.#request("/v1/demo-state", demoStateSchema, options);
  }

  createCourse(request: CourseCreateRequest, options: RequestOptions = {}): Promise<CourseCreateResponse> {
    const parsed = courseCreateRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError("/v1/courses");
    return this.#request("/v1/courses", courseCreateResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed.data),
      signal: options.signal,
    }, {
      expectedStatuses: [200, 201],
      validate: (status, result) => (status === 200) === result.replayed,
    });
  }

  learningSnapshot(request: LearningSnapshotRequest, options: RequestOptions = {}): Promise<LearningSnapshot> {
    const courseId = request.courseId;
    if (!Number.isInteger(request.availableMinutes) || request.availableMinutes < 1 || request.availableMinutes > 1_440) {
      throw new LearningCoreRequestError("/v1/learning-snapshot");
    }
    assertAgentIdentifier(courseId, "/v1/learning-snapshot");
    const params = new URLSearchParams({ course_id: courseId, available_minutes: String(request.availableMinutes) });
    return this.#request(`/v1/learning-snapshot?${params.toString()}`, learningSnapshotSchema, options, {
      expectedStatuses: [200],
      validate: (_status, result) => result.course_id === courseId && result.available_minutes === request.availableMinutes,
    });
  }

  createAutonomousRecommendation(
    request: AutonomousRecommendationRequest,
    options: RequestOptions = {},
  ): Promise<AutonomousRecommendationResponse> {
    const parsed = autonomousRecommendationRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError("/v1/autonomous-recommendations");
    return this.#request("/v1/autonomous-recommendations", autonomousRecommendationResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed.data),
      signal: options.signal,
    }, {
      expectedStatuses: [200, 201],
      validate: (status, result) => (
        (status === 201) === (result.outcome === "task_created")
        && result.course_id === parsed.data.course_id
        && result.snapshot.available_minutes === parsed.data.available_minutes
        && (parsed.data.document_id === undefined
          ? result.bootstrap === null
          : result.bootstrap !== null
            && result.bootstrap.course_id === parsed.data.course_id
            && result.bootstrap.document_id === parsed.data.document_id)
      ),
    });
  }

  startAutonomousStudySession(
    request: AutonomousStudySessionRequest,
    options: RequestOptions = {},
  ): Promise<AutonomousStudySessionStartResponse> {
    const parsed = autonomousStudySessionRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError("/v1/autonomous-study-sessions");
    return this.#request("/v1/autonomous-study-sessions", autonomousStudySessionStartResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed.data),
      signal: options.signal,
    }, {
      expectedStatuses: [200, 201],
      validate: (status, result) => (
        (status === 201) === (result.outcome === "session_created")
        && result.course_id === parsed.data.course_id
        && (result.task === null || result.task.id === parsed.data.task_id)
      ),
    });
  }

  focusedStudyRequest(
    request: FocusedStudyRequest,
    options: RequestOptions = {},
  ): Promise<FocusedStudyResponse> {
    const parsed = focusedStudyRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError("/v1/focused-study-requests");
    return this.#request("/v1/focused-study-requests", focusedStudyResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed.data),
      signal: options.signal,
    }, {
      expectedStatuses: [200, 201],
      validate: (status, result) => (
        (status === 201) === (result.outcome === "session_created")
        && result.course_id === parsed.data.course_id
        && (result.session === null || result.session.goal === parsed.data.goal)
      ),
    });
  }

  getStudySession(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<StudySessionReadResponse> {
    const path = "/v1/study-sessions/{session_id}";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(courseId, path);
    const params = new URLSearchParams({ course_id: courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}?${params.toString()}`,
      studySessionReadResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.course_id === courseId && result.session.id === sessionId },
    );
  }

  getStudySessionAdaptiveState(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<AdaptiveStateResponse> {
    const path = "/v1/study-sessions/{session_id}/adaptive-state";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(courseId, path);
    const params = new URLSearchParams({ course_id: courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/adaptive-state?${params.toString()}`,
      adaptiveStateResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.course_id === courseId && result.session.id === sessionId },
    );
  }

  completeStudySessionAdaptiveAction(
    sessionId: string,
    actionId: string,
    request: AdaptiveActionCompleteRequest,
    options: RequestOptions = {},
  ): Promise<AdaptiveActionCompleteResponse> {
    const path = "/v1/study-sessions/{session_id}/adaptive-actions/{action_id}/complete";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(actionId, path);
    const parsed = adaptiveActionCompleteRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/adaptive-actions/${encodeURIComponent(actionId)}/complete`,
      adaptiveActionCompleteResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.course_id === parsed.data.course_id
          && result.session.id === sessionId
          && result.completed_action.id === actionId
        ),
      },
    );
  }

  pauseStudySession(
    sessionId: string,
    request: StudySessionControlRequest,
    options: RequestOptions = {},
  ): Promise<StudySessionControlResponse> {
    return this.#controlStudySession("pause", sessionId, request, options);
  }

  resumeStudySession(
    sessionId: string,
    request: StudySessionControlRequest,
    options: RequestOptions = {},
  ): Promise<StudySessionControlResponse> {
    return this.#controlStudySession("resume", sessionId, request, options);
  }

  #controlStudySession(
    command: "pause" | "resume",
    sessionId: string,
    request: StudySessionControlRequest,
    options: RequestOptions,
  ): Promise<StudySessionControlResponse> {
    const path = `/v1/study-sessions/{session_id}/${command}`;
    assertAgentIdentifier(sessionId, path);
    const parsed = studySessionControlRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/${command}`,
      studySessionControlResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.command === command
          && result.course_id === parsed.data.course_id
          && result.session.id === sessionId
        ),
      },
    );
  }

  listStudySessions(
    courseId: string,
    options: RequestOptions = {},
  ): Promise<StudySessionListResponse> {
    const path = "/v1/study-sessions";
    assertAgentIdentifier(courseId, path);
    const params = new URLSearchParams({ course_id: courseId });
    return this.#request(
      `${path}?${params.toString()}`,
      studySessionListResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.course_id === courseId },
    );
  }

  getStudySessionDiagnostic(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<DiagnosticReadResponse> {
    const path = "/v1/study-sessions/{session_id}/diagnostic";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(courseId, path);
    const params = new URLSearchParams({ course_id: courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/diagnostic?${params.toString()}`,
      diagnosticReadResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.course_id === courseId && result.session.id === sessionId },
    );
  }

  beginStudySessionDiagnostic(
    sessionId: string,
    request: DiagnosticProgressionRequest,
    options: RequestOptions = {},
  ): Promise<DiagnosticProgressionResponse> {
    const path = "/v1/study-sessions/{session_id}/diagnostic";
    assertAgentIdentifier(sessionId, path);
    const parsed = diagnosticProgressionRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/diagnostic`,
      diagnosticProgressionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 201],
        validate: (status, result) => (
          (status === 201) === (result.outcome === "applied")
          && result.course_id === parsed.data.course_id
          && result.session.id === sessionId
        ),
      },
    );
  }

  answerStudySessionDiagnostic(
    sessionId: string,
    checkpointId: string,
    request: DiagnosticAnswerRequest,
    options: RequestOptions = {},
  ): Promise<DiagnosticProgressionResponse> {
    const path = "/v1/study-sessions/{session_id}/diagnostic/{checkpoint_id}/answer";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(checkpointId, path);
    const parsed = diagnosticAnswerRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/diagnostic/${encodeURIComponent(checkpointId)}/answer`,
      diagnosticProgressionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 201],
        validate: (status, result) => (
          (status === 201) === (result.outcome === "applied")
          && result.course_id === parsed.data.course_id
          && result.session.id === sessionId
          && result.checkpoint.id === checkpointId
        ),
      },
    );
  }

  getStudySessionActiveRecall(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<ActiveRecallReadResponse> {
    const path = "/v1/study-sessions/{session_id}/active-recall";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(courseId, path);
    const params = new URLSearchParams({ course_id: courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/active-recall?${params.toString()}`,
      activeRecallReadResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.course_id === courseId && result.session.id === sessionId },
    );
  }

  beginStudySessionActiveRecall(
    sessionId: string,
    request: ActiveRecallProgressionRequest,
    options: RequestOptions = {},
  ): Promise<ActiveRecallProgressionResponse> {
    const path = "/v1/study-sessions/{session_id}/active-recall";
    assertAgentIdentifier(sessionId, path);
    const parsed = activeRecallProgressionRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/active-recall`,
      activeRecallProgressionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 201],
        validate: (status, result) => (
          (status === 201) === (result.outcome === "applied")
          && result.course_id === parsed.data.course_id
          && result.session.id === sessionId
          && (result.outcome !== "applied" || (
            result.run.status === "pending"
            && result.session.status === "active_recall"
          ))
        ),
      },
    );
  }

  answerStudySessionActiveRecall(
    sessionId: string,
    runId: string,
    request: ActiveRecallAnswerRequest,
    options: RequestOptions = {},
  ): Promise<ActiveRecallProgressionResponse> {
    const path = "/v1/study-sessions/{session_id}/active-recall/{run_id}/answer";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(runId, path);
    const parsed = activeRecallAnswerRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/active-recall/${encodeURIComponent(runId)}/answer`,
      activeRecallProgressionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.course_id === parsed.data.course_id
          && result.session.id === sessionId
          && result.run.id === runId
          && result.run.status === "answered"
          && (result.outcome !== "applied" || result.session.status === "practicing")
        ),
      },
    );
  }

  getStudySessionPractice(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<TargetedPracticeReadResponse> {
    const path = "/v1/study-sessions/{session_id}/practice";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(courseId, path);
    const params = new URLSearchParams({ course_id: courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/practice?${params.toString()}`,
      targetedPracticeReadResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.course_id === courseId && result.session.id === sessionId },
    );
  }

  beginStudySessionPractice(
    sessionId: string,
    request: TargetedPracticeProgressionRequest,
    options: RequestOptions = {},
  ): Promise<TargetedPracticeProgressionResponse> {
    const path = "/v1/study-sessions/{session_id}/practice";
    assertAgentIdentifier(sessionId, path);
    const parsed = targetedPracticeProgressionRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/practice`,
      targetedPracticeProgressionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 201],
        validate: (status, result) => (
          (status === 201) === (result.outcome === "applied")
          && result.course_id === parsed.data.course_id
          && result.session.id === sessionId
          && (result.outcome !== "applied" || (
            result.run.status === "pending"
            && result.session.status === "practicing"
          ))
        ),
      },
    );
  }

  answerStudySessionPractice(
    sessionId: string,
    runId: string,
    request: TargetedPracticeAnswerRequest,
    options: RequestOptions = {},
  ): Promise<TargetedPracticeProgressionResponse> {
    const path = "/v1/study-sessions/{session_id}/practice/{run_id}/answer";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(runId, path);
    const parsed = targetedPracticeAnswerRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/practice/${encodeURIComponent(runId)}/answer`,
      targetedPracticeProgressionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.course_id === parsed.data.course_id
          && result.session.id === sessionId
          && result.run.id === runId
          && result.run.status === "answered"
          && (result.outcome !== "applied" || result.session.status === "studying" || result.session.status === "summarizing")
        ),
      },
    );
  }

  getStudySessionSummary(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<StudySummaryReadResponse> {
    const path = "/v1/study-sessions/{session_id}/summary";
    assertAgentIdentifier(sessionId, path);
    assertAgentIdentifier(courseId, path);
    const params = new URLSearchParams({ course_id: courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/summary?${params.toString()}`,
      studySummaryReadResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.course_id === courseId && result.session.id === sessionId },
    );
  }

  finalizeStudySessionSummary(
    sessionId: string,
    request: StudySummaryRequest,
    options: RequestOptions = {},
  ): Promise<StudySummaryFinalizeResponse> {
    const path = "/v1/study-sessions/{session_id}/summary";
    assertAgentIdentifier(sessionId, path);
    const parsed = studySummaryRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/summary`,
      studySummaryFinalizeResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 201],
        validate: (status, result) => (
          (status === 201) === (result.outcome === "applied")
          && result.course_id === parsed.data.course_id
          && result.session.id === sessionId
          && result.session.status === "completed"
        ),
      },
    );
  }

  listDueReviews(
    request: { courseId?: string; limit?: number } = {},
    options: RequestOptions = {},
  ): Promise<DueReviewListResponse> {
    const params = new URLSearchParams();
    if (request.courseId !== undefined) {
      assertAgentIdentifier(request.courseId, "/v1/reviews/due");
      params.set("course_id", request.courseId);
    }
    const limit = request.limit ?? 50;
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
      throw new LearningCoreRequestError("/v1/reviews/due");
    }
    params.set("limit", String(limit));
    return this.#request(`/v1/reviews/due?${params.toString()}`, dueReviewListResponseSchema, options);
  }

  recordReviewAttempt(
    itemId: string,
    request: ReviewAttemptRequest,
    options: RequestOptions = {},
  ): Promise<ReviewAttemptResponse> {
    const path = "/v1/reviews/{item_id}/attempts";
    assertAgentIdentifier(itemId, path);
    const parsed = reviewAttemptRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/reviews/${encodeURIComponent(itemId)}/attempts`,
      reviewAttemptResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 201],
        validate: (status, result) => (
          (status === 201) === (result.outcome === "applied")
          && result.review_item_id === itemId
          && result.rating === parsed.data.rating
          && result.response === parsed.data.response
          && result.schedule.revision === parsed.data.expectedRevision + 1
        ),
      },
    );
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

  getCurrentLearningIntervention(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<LearningInterventionResponse> {
    const contractPath = "/v1/study-sessions/{sessionId}/interventions/current";
    assertAgentIdentifier(sessionId, contractPath);
    assertAgentIdentifier(courseId, contractPath);
    const query = new URLSearchParams({ courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/interventions/current?${query.toString()}`,
      learningInterventionResponseSchema,
      { signal: options.signal },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.courseId === courseId && result.sessionId === sessionId
        ),
      },
    );
  }

  startLearningIntervention(
    sessionId: string,
    request: LearningInterventionCreateRequest,
    options: RequestOptions = {},
  ): Promise<LearningInterventionResponse> {
    const contractPath = "/v1/study-sessions/{sessionId}/interventions";
    assertAgentIdentifier(sessionId, contractPath);
    const parsed = learningInterventionCreateRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(contractPath);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/interventions`,
      learningInterventionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 201, 202],
        validate: (status, result) => (
          result.courseId === parsed.data.courseId
          && result.sessionId === sessionId
          && (status !== 201 || result.status === "practice_ready")
          && (status !== 202 || result.status === "queued" || result.status === "running")
        ),
      },
    );
  }

  getCurrentStudyPlanProposal(
    sessionId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<StudyPlanProposalResponse> {
    const contractPath = "/v1/study-sessions/{sessionId}/plan-proposals/current";
    assertAgentIdentifier(sessionId, contractPath);
    assertAgentIdentifier(courseId, contractPath);
    const query = new URLSearchParams({ courseId });
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/plan-proposals/current?${query.toString()}`,
      studyPlanProposalResponseSchema,
      { signal: options.signal },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.courseId === courseId && result.sessionId === sessionId
        ),
      },
    );
  }

  startStudyPlanProposal(
    sessionId: string,
    request: StudyPlanProposalCreateRequest,
    options: RequestOptions = {},
  ): Promise<StudyPlanProposalResponse> {
    const contractPath = "/v1/study-sessions/{sessionId}/plan-proposals";
    assertAgentIdentifier(sessionId, contractPath);
    const parsed = studyPlanProposalCreateRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(contractPath);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/plan-proposals`,
      studyPlanProposalResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200, 202],
        validate: (status, result) => (
          result.courseId === parsed.data.courseId
          && result.sessionId === sessionId
          && (
            status !== 202
            || result.status === "queued"
            || result.status === "running"
          )
        ),
      },
    );
  }

  decideStudyPlanProposal(
    sessionId: string,
    artifactId: string,
    request: StudyPlanProposalDecisionRequest,
    options: RequestOptions = {},
  ): Promise<StudyPlanProposalResponse> {
    const contractPath = "/v1/study-sessions/{sessionId}/plan-proposals/{artifactId}/decision";
    assertAgentIdentifier(sessionId, contractPath);
    assertAgentIdentifier(artifactId, contractPath);
    const parsed = studyPlanProposalDecisionRequestSchema.safeParse(request);
    if (!parsed.success || parsed.data.artifactId !== artifactId) {
      throw new LearningCoreRequestError(contractPath);
    }
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/plan-proposals/${encodeURIComponent(artifactId)}/decision`,
      studyPlanProposalResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.courseId === parsed.data.courseId
          && result.sessionId === sessionId
          && (
            parsed.data.decision === "accept"
              ? result.status === "accepted" || result.status === "undone"
              : result.status === "rejected"
          )
        ),
      },
    );
  }

  undoStudyPlanProposal(
    sessionId: string,
    proposalId: string,
    request: StudyPlanProposalUndoRequest,
    options: RequestOptions = {},
  ): Promise<StudyPlanProposalResponse> {
    const contractPath = "/v1/study-sessions/{sessionId}/plan-proposals/{proposalId}/undo";
    assertAgentIdentifier(sessionId, contractPath);
    assertAgentIdentifier(proposalId, contractPath);
    const parsed = studyPlanProposalUndoRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(contractPath);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/plan-proposals/${encodeURIComponent(proposalId)}/undo`,
      studyPlanProposalResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.courseId === parsed.data.courseId
          && result.sessionId === sessionId
          && result.status === "undone"
          && result.receipt?.proposalId === proposalId
        ),
      },
    );
  }

  cancelLearningIntervention(
    sessionId: string,
    runId: string,
    courseId: string,
    options: RequestOptions = {},
  ): Promise<LearningInterventionResponse> {
    const contractPath = "/v1/study-sessions/{sessionId}/interventions/{runId}/cancel";
    assertAgentIdentifier(sessionId, contractPath);
    assertAgentIdentifier(runId, contractPath);
    assertAgentIdentifier(courseId, contractPath);
    return this.#request(
      `/v1/study-sessions/${encodeURIComponent(sessionId)}/interventions/${encodeURIComponent(runId)}/cancel`,
      learningInterventionResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ courseId }),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, result) => (
          result.courseId === courseId
          && result.sessionId === sessionId
          && result.run?.id === runId
        ),
      },
    );
  }

  async *learningInterventionEvents(
    sessionId: string,
    runId: string,
    courseId: string,
    options: LearningInterventionEventStreamOptions = {},
  ): AsyncGenerator<LearningInterventionEvent> {
    const contractPath = "/v1/study-sessions/{sessionId}/interventions/{runId}/events";
    assertAgentIdentifier(sessionId, contractPath);
    assertAgentIdentifier(runId, contractPath);
    assertAgentIdentifier(courseId, contractPath);
    if (options.lastEventId !== undefined) {
      assertAgentIdentifier(options.lastEventId, contractPath);
    }
    if (options.cursor !== undefined) assertAgentIdentifier(options.cursor, contractPath);
    if (
      options.lastEventId !== undefined
      && options.cursor !== undefined
      && options.lastEventId !== options.cursor
    ) {
      throw new LearningCoreRequestError(contractPath);
    }

    const query = new URLSearchParams({ courseId });
    if (options.cursor !== undefined) query.set("cursor", options.cursor);
    const headers = new Headers({
      Accept: "text/event-stream",
      Authorization: `Bearer ${this.#token}`,
    });
    if (options.lastEventId !== undefined) headers.set("Last-Event-ID", options.lastEventId);
    const response = await this.#fetch(
      `${this.baseUrl}/v1/study-sessions/${encodeURIComponent(sessionId)}/interventions/${encodeURIComponent(runId)}/events?${query.toString()}`,
      { headers, signal: options.signal },
    );
    await assertExpectedStatus(response, contractPath, [200]);
    const mediaType = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
    if (mediaType !== "text/event-stream" || !response.body) {
      throw new LearningCoreSchemaError(contractPath);
    }

    let terminalSeen = false;
    let lastEventId = options.lastEventId ?? options.cursor ?? null;
    const resumeAfterId = lastEventId;
    const receivedIds = new Set<string>();
    try {
      for await (const record of parseServerSentEvents(response.body, contractPath)) {
        if (
          record.id === null
          || record.id === resumeAfterId
          || receivedIds.has(record.id)
        ) {
          throw new LearningCoreSchemaError(contractPath);
        }
        let data: unknown;
        try {
          data = JSON.parse(record.data);
        } catch {
          throw new LearningCoreSchemaError(contractPath);
        }
        const parsed = learningInterventionEventSchema.safeParse({
          id: record.id,
          event: record.event,
          data,
        });
        if (!parsed.success) throw new LearningCoreSchemaError(contractPath);
        const event = parsed.data;
        if (event.event === "started" && event.data.runId !== runId) {
          throw new LearningCoreSchemaError(contractPath);
        }
        if (
          event.event === "done"
          || event.event === "cancelled"
          || event.event === "source_review"
        ) {
          terminalSeen = true;
        }
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

  getLatestAgentRunActivity(
    context: AgentRunActivityContext,
    options: RequestOptions = {},
  ): Promise<AgentRunActivity> {
    const path = "/v1/agent/runs/latest";
    const parsed = agentRunActivityContextSchema.safeParse(context);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    const [name, value] = "conversationId" in parsed.data
      ? ["conversationId", parsed.data.conversationId]
      : ["studySessionId", parsed.data.studySessionId];
    const params = new URLSearchParams({ [name]: value });
    return this.#request(
      `${path}?${params.toString()}`,
      agentRunActivitySchema,
      options,
      { expectedStatuses: [200] },
    );
  }

  cancelAgentRun(runId: string, options: RequestOptions = {}): Promise<AgentCancelResponse> {
    assertAgentIdentifier(runId, "/v1/agent/runs/{id}/cancel");
    return this.#request(
      `/v1/agent/runs/${encodeURIComponent(runId)}/cancel`,
      agentCancelResponseSchema,
      { method: "POST", signal: options.signal },
    );
  }

  getPendingLevel2Actions(runId: string, options: RequestOptions = {}): Promise<AgentLevel2PendingActionsResponse> {
    const path = "/v1/agent/runs/{id}/level2-actions/pending";
    assertAgentIdentifier(runId, path);
    return this.#request(
      `/v1/agent/runs/${encodeURIComponent(runId)}/level2-actions/pending`,
      agentLevel2PendingActionsResponseSchema,
      options,
      { expectedStatuses: [200], validate: (_status, result) => result.run.id === runId },
    );
  }

  confirmLevel2Action(runId: string, approvalId: string, request: AgentLevel2ApprovalRequest, options: RequestOptions = {}): Promise<AgentLevel2ApprovalResponse> {
    return this.#level2Action("confirm", runId, approvalId, request, options);
  }

  rejectLevel2Action(runId: string, approvalId: string, request: AgentLevel2ApprovalRequest, options: RequestOptions = {}): Promise<AgentLevel2ApprovalResponse> {
    return this.#level2Action("reject", runId, approvalId, request, options);
  }

  #level2Action(action: "confirm" | "reject", runId: string, approvalId: string, request: AgentLevel2ApprovalRequest, options: RequestOptions): Promise<AgentLevel2ApprovalResponse> {
    const path = `/v1/agent/runs/{id}/level2-actions/{approvalId}/${action}`;
    assertAgentIdentifier(runId, path);
    assertAgentIdentifier(approvalId, path);
    const parsed = agentLevel2ApprovalRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(`/v1/agent/runs/${encodeURIComponent(runId)}/level2-actions/${encodeURIComponent(approvalId)}/${action}`, agentLevel2ApprovalResponseSchema, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(parsed.data), signal: options.signal,
    }, {
      expectedStatuses: [200],
      validate: (_status, result) => result.run.id === runId
        && result.approvalId === approvalId
        && (action === "confirm"
          ? result.resolution === "confirmed" || result.resolution === "expired"
          : result.resolution === "rejected"),
    });
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

  createConversation(
    request: ConversationCreateRequest,
    options: RequestOptions = {},
  ): Promise<ConversationCreateResponse> {
    const path = "/v1/conversations";
    const parsed = conversationCreateRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    assertAgentIdentifier(parsed.data.id, path);
    if (parsed.data.sourceScope.kind === "course") assertAgentIdentifier(parsed.data.sourceScope.courseId, path);
    return this.#request(path, conversationCreateResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed.data),
      signal: options.signal,
    }, {
      expectedStatuses: [200, 201],
      validate: (status, response) => (
        response.conversation.id === parsed.data.id
        && response.conversation.sourceScope.kind === parsed.data.sourceScope.kind
        && (response.conversation.sourceScope.kind !== "course"
          || parsed.data.sourceScope.kind !== "course"
          || response.conversation.sourceScope.courseId === parsed.data.sourceScope.courseId)
        && (status === 200) === response.replayed
      ),
    });
  }

  getConversation(conversationId: string, options: RequestOptions = {}): Promise<Conversation> {
    const path = "/v1/conversations/{conversation_id}";
    assertAgentIdentifier(conversationId, path);
    return this.#request(`/v1/conversations/${encodeURIComponent(conversationId)}`, conversationSchema, options, {
      expectedStatuses: [200],
      validate: (_status, conversation) => conversation.id === conversationId,
    });
  }

  listConversations(
    request: { cursor?: string; limit?: number; courseId?: string } = {},
    options: RequestOptions = {},
  ): Promise<ConversationListResponse> {
    const path = "/v1/conversations";
    const limit = request.limit ?? 25;
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) throw new LearningCoreRequestError(path);
    const params = new URLSearchParams({ limit: String(limit) });
    if (request.cursor !== undefined) {
      if (request.cursor.length < 1 || request.cursor.length > 1024) throw new LearningCoreRequestError(path);
      params.set("cursor", request.cursor);
    }
    if (request.courseId !== undefined) {
      assertAgentIdentifier(request.courseId, path);
      params.set("course_id", request.courseId);
    }
    return this.#request(`${path}?${params.toString()}`, conversationListResponseSchema, options, {
      expectedStatuses: [200],
      validate: (_status, response) => request.courseId === undefined || response.conversations.every(
        (conversation) => conversation.sourceScope.kind === "course" && conversation.sourceScope.courseId === request.courseId,
      ),
    });
  }

  listConversationMessages(
    conversationId: string,
    options: RequestOptions = {},
  ): Promise<DurableConversationMessagesResponse> {
    const path = "/v1/conversations/{conversation_id}/messages";
    assertAgentIdentifier(conversationId, path);
    return this.#request(
      `/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
      durableConversationMessagesResponseSchema,
      options,
      {
        expectedStatuses: [200],
        validate: (_status, response) => response.messages.every((message) => message.conversationId === conversationId),
      },
    );
  }

  getConversationMessage(
    conversationId: string,
    messageId: string,
    options: RequestOptions = {},
  ): Promise<DurableConversationMessage> {
    const path = "/v1/conversations/{conversation_id}/messages/{message_id}";
    assertAgentIdentifier(conversationId, path);
    assertAgentIdentifier(messageId, path);
    return this.#request(
      `/v1/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
      durableConversationMessageSchema,
      options,
      {
        expectedStatuses: [200],
        validate: (_status, message) => message.conversationId === conversationId && message.id === messageId,
      },
    );
  }

  cancelConversationAnswer(
    conversationId: string,
    assistantMessageId: string,
    request: ConversationCancelRequest,
    options: RequestOptions = {},
  ): Promise<ConversationCancelResponse> {
    const path = "/v1/conversations/{conversation_id}/messages/{message_id}/cancel";
    assertAgentIdentifier(conversationId, path);
    assertAgentIdentifier(assistantMessageId, path);
    const parsed = conversationCancelRequestSchema.safeParse(request);
    if (!parsed.success) throw new LearningCoreRequestError(path);
    return this.#request(
      `/v1/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(assistantMessageId)}/cancel`,
      conversationCancelResponseSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
        signal: options.signal,
      },
      {
        expectedStatuses: [200],
        validate: (_status, response) => (
          response.message.conversationId === conversationId
          && response.message.id === assistantMessageId
          && ["completed", "failed", "cancelled", "interrupted"].includes(response.message.status)
        ),
      },
    );
  }

  async *streamConversationAnswer(
    conversationId: string,
    request: DurableAnswerStreamRequest,
    options: RequestOptions = {},
  ): AsyncGenerator<AnswerStreamEvent> {
    const path = "/v1/conversations/{conversation_id}/answers/stream";
    assertAgentIdentifier(conversationId, path);
    const parsedRequest = durableAnswerStreamRequestSchema.safeParse(request);
    if (!parsedRequest.success) throw new LearningCoreRequestError(path);
    const requestBody = parsedRequest.data;
    assertAgentIdentifier(requestBody.userMessageId, path);
    assertAgentIdentifier(requestBody.assistantMessageId, path);
    if (requestBody.sourceScope.kind === "course") assertAgentIdentifier(requestBody.sourceScope.courseId, path);
    const response = await this.#fetch(`${this.baseUrl}/v1/conversations/${encodeURIComponent(conversationId)}/answers/stream`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        Authorization: `Bearer ${this.#token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
      signal: options.signal,
    });
    await assertExpectedStatus(response, path, [200]);
    const mediaType = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
    if (mediaType !== "text/event-stream" || !response.body) throw new LearningCoreSchemaError(path);

    let phase: "start" | "metadata" | "retrieval" | "replay" | "terminal" = "start";
    const sources = new Map<number, Extract<AnswerStreamEvent, { type: "retrieval" }>["data"]["chunks"][number]>();
    const citationIds = new Set<string>();
    const replaySourceIndexes = new Set<number>();
    for await (const record of parseServerSentEvents(response.body, path)) {
      let data: unknown;
      try {
        data = JSON.parse(record.data);
      } catch {
        throw new LearningCoreSchemaError(path);
      }
      const parsed = answerStreamEventSchema.safeParse({ type: record.event, data });
      if (!parsed.success || phase === "terminal") throw new LearningCoreSchemaError(path);
      const event = parsed.data;
      if (phase === "start") {
        if (
          event.type !== "metadata"
          || event.data.conversationId !== conversationId
          || event.data.runId !== requestBody.assistantMessageId
          || event.data.userMessageId !== requestBody.userMessageId
          || event.data.assistantMessageId !== requestBody.assistantMessageId
          || event.data.retrievalLimit !== requestBody.retrievalLimit
        ) throw new LearningCoreSchemaError(path);
        phase = event.data.replayed === true ? "replay" : "metadata";
      } else if (event.type === "metadata") {
        throw new LearningCoreSchemaError(path);
      } else if (event.type === "retrieval") {
        if (phase !== "metadata") throw new LearningCoreSchemaError(path);
        const seenChunkIds = new Set<string>();
        for (const [index, source] of event.data.chunks.entries()) {
          if (sources.has(source.sourceIndex) || source.chunkIds.some((chunkId) => seenChunkIds.has(chunkId))) throw new LearningCoreSchemaError(path);
          if (
            source.sourceIndex !== index + 1
            || source.documentVersionId === undefined
            || source.chunkContentHash === undefined
            || (requestBody.sourceScope.kind === "course" && !source.courseIds.includes(requestBody.sourceScope.courseId))
          ) throw new LearningCoreSchemaError(path);
          source.chunkIds.forEach((chunkId) => seenChunkIds.add(chunkId));
          sources.set(source.sourceIndex, source);
        }
        phase = "retrieval";
      } else if (event.type === "delta" || event.type === "warning") {
        if (phase !== "retrieval" && !(phase === "replay" && event.type === "delta")) throw new LearningCoreSchemaError(path);
      } else if (event.type === "citation") {
        const source = sources.get(event.data.sourceIndex);
        if (phase === "replay") {
          if (
            event.data.documentVersionId === undefined
            || event.data.chunkContentHash === undefined
            || citationIds.has(event.data.citationId)
            || replaySourceIndexes.has(event.data.sourceIndex)
          ) throw new LearningCoreSchemaError(path);
          citationIds.add(event.data.citationId);
          replaySourceIndexes.add(event.data.sourceIndex);
          yield event;
          continue;
        }
        if (
          phase !== "retrieval"
          || !source
          || event.data.documentVersionId === undefined
          || event.data.chunkContentHash === undefined
          || citationIds.has(event.data.citationId)
          || !source.chunkIds.includes(event.data.chunkId)
          || source.documentId !== event.data.documentId
          || source.documentVersionId !== event.data.documentVersionId
          || source.chunkContentHash !== event.data.chunkContentHash
          || source.documentName !== event.data.documentName
          || event.data.pageNumber < source.pageNumber
          || event.data.pageNumber > source.pageEnd
          || source.sectionPath.join("\u0000") !== event.data.sectionPath.join("\u0000")
          || !normalizeEvidenceWhitespace(source.text).includes(normalizeEvidenceWhitespace(event.data.excerpt))
        ) throw new LearningCoreSchemaError(path);
        citationIds.add(event.data.citationId);
      } else if (event.type === "done") {
        if (
          (phase !== "retrieval" && phase !== "replay")
          || event.data.runId !== requestBody.assistantMessageId
          || event.data.citationCount !== citationIds.size
          || event.data.grounded !== (citationIds.size > 0)
        ) throw new LearningCoreSchemaError(path);
        phase = "terminal";
      } else if (event.type === "error") {
        if ((phase !== "metadata" && phase !== "retrieval" && phase !== "replay") || event.data.runId !== requestBody.assistantMessageId) throw new LearningCoreSchemaError(path);
        phase = "terminal";
      }
      yield event;
    }
    if (phase !== "terminal") throw new LearningCoreSchemaError(path);
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
