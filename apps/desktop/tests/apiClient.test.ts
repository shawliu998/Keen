import {
  createLearningCoreClient,
  InvalidLearningCoreUrlError,
  LearningCoreResponseError,
  LearningCoreRequestError,
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

  it("binds fetch to the global object for Safari and WKWebView", async () => {
    const contextSensitiveFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError("fetch received an invalid receiver");
      return Promise.resolve(jsonResponse(health));
    });
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      contextSensitiveFetch as unknown as typeof fetch,
    );

    await expect(client.health()).resolves.toEqual(health);
    expect(contextSensitiveFetch).toHaveBeenCalledOnce();
  });

  it("posts provider tests with only the active sidecar client's credentials", async () => {
    const rotatedToken = "c".repeat(64);
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toBe("http://127.0.0.1:8081/v1/provider/test");
      expect(init?.method).toBe("POST");
      expect(new Headers(init?.headers).get("Authorization")).toBe(
        `Bearer ${rotatedToken}`,
      );
      return jsonResponse({
        status: "connected",
        provider: "ollama",
        model: "current-model",
        detail: "Connected",
      });
    });
    const client = createLearningCoreClient(
      "http://127.0.0.1:8081",
      rotatedToken,
      fetchMock as unknown as typeof fetch,
    );

    await expect(client.testProvider()).resolves.toEqual({
      status: "connected",
      provider: "ollama",
      model: "current-model",
      detail: "Connected",
    });
    expect(fetchMock).toHaveBeenCalledOnce();
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

  it("creates a course with a strict camelCase contract and distinguishes replay status", async () => {
    const course = { id: "course-created", title: "Calculus", description: "Limits", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null };
    const fetchMock = vi.fn(async () => jsonResponse({ course, replayed: false }, 201));
    const controller = new AbortController();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.createCourse({ title: "Calculus", description: "Limits", idempotencyKey: "course-0123456789abcdef" }, { signal: controller.signal })).resolves.toEqual({ course, replayed: false });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8080/v1/courses");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ title: "Calculus", description: "Limits", idempotencyKey: "course-0123456789abcdef" });
    expect(init.signal).toBe(controller.signal);
  });

  it("defaults an omitted course description before sending the validated request", async () => {
    const course = { id: "course-created", title: "Calculus", description: "", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null };
    const fetchMock = vi.fn(async () => jsonResponse({ course, replayed: false }, 201));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await client.createCourse({ title: "Calculus", idempotencyKey: "course-0123456789abcdef" });

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ title: "Calculus", description: "", idempotencyKey: "course-0123456789abcdef" });
  });

  it("rejects malformed course requests and mismatched creation status semantics", async () => {
    const course = { id: "course-created", title: "Calculus", description: "Limits", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null };
    const invalidFetch = vi.fn();
    const invalidClient = createLearningCoreClient("http://127.0.0.1:8080", token, invalidFetch as unknown as typeof fetch);
    await expect(Promise.resolve().then(() => invalidClient.createCourse({ title: "Calculus", description: "", idempotencyKey: "short" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => invalidClient.createCourse({ title: "Calculus", description: "", idempotencyKey: "course key with spaces" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => invalidClient.createCourse({ title: "Calculus", description: "", idempotencyKey: ".course-0123456789abcdef" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    expect(invalidFetch).not.toHaveBeenCalled();

    const semanticClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ course, replayed: false }, 200)) as unknown as typeof fetch);
    await expect(semanticClient.createCourse({ title: "Calculus", description: "Limits", idempotencyKey: "course-0123456789abcdef" })).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("uses strict persisted-learning snapshot and recommendation contracts", async () => {
    const candidate = {
      id: "concept:concept-1:study_very_weak_concept",
      action: "study_very_weak_concept",
      target_type: "concept",
      target_id: "concept-1",
      concept_id: "concept-1",
      component: "mastery",
      priority_tier: 3,
      estimated_minutes: 15,
      fits_available_minutes: true,
      priority_score: 0.8,
      priority_unclamped_score: 0.8,
      priority_algorithm_version: "keen-feed-priority/v1",
      priority_components: [{ name: "mastery", raw_value: 0.2, weight: 1, contribution: 0.8 }],
      priority_explanation: ["Weak mastery is prioritized."],
      why: "Mastery is 20%, at or below the very-weak threshold of 35%.",
    } as const;
    const task = {
      id: "recommendation-1",
      course_id: "course-1",
      concept_id: "concept-1",
      title: "Study very weak concept: Limits",
      reason: candidate.why,
      due_at: "2026-07-17T23:59:59+00:00",
      estimated_minutes: 15,
      status: "upcoming",
      source_type: "weak_concept",
      source_id: "concept-1",
      priority_score: 0.8,
      recommended_reason: candidate.why,
      scheduled_for: "2026-07-17T00:00:00+00:00",
      created_at: "2026-07-17T10:00:00+00:00",
      updated_at: "2026-07-17T10:00:00+00:00",
      completed_at: null,
    } as const;
    const snapshot = {
      course_id: "course-1",
      as_of: "2026-07-17T10:00:00+00:00",
      available_minutes: 20,
      due_review_count: 0,
      incomplete_session_count: 0,
      misconception_count: 0,
      pending_tasks: [task],
      completed_tasks: [],
      candidates: [candidate],
      mastery_gap_count: 0,
    } as const;
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(snapshot))
      .mockResolvedValueOnce(jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: null }, 201));
    const controller = new AbortController();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.learningSnapshot({ courseId: "course-1", availableMinutes: 20 }, { signal: controller.signal })).resolves.toEqual(snapshot);
    await expect(client.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20, time_zone: "Asia/Shanghai" })).resolves.toMatchObject({ outcome: "task_created", task, candidate });
    const [snapshotUrl, snapshotInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [recommendationUrl, recommendationInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(snapshotUrl).toBe("http://127.0.0.1:8080/v1/learning-snapshot?course_id=course-1&available_minutes=20");
    expect(snapshotInit.signal).toBe(controller.signal);
    expect(recommendationUrl).toBe("http://127.0.0.1:8080/v1/autonomous-recommendations");
    expect(JSON.parse(String(recommendationInit.body))).toEqual({ course_id: "course-1", available_minutes: 20, time_zone: "Asia/Shanghai" });

    const mismatchedStatus = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: null }, 200)) as unknown as typeof fetch);
    await expect(mismatchedStatus.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const completedTask = { ...task, status: "completed" as const, completed_at: "2026-07-17T11:00:00+00:00", updated_at: "2026-07-17T11:00:00+00:00" };
    const replaySnapshot = { ...snapshot, pending_tasks: [], completed_tasks: [completedTask] };
    const replayClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "replay", course_id: "course-1", snapshot: replaySnapshot, task: completedTask, candidate, bootstrap: null })) as unknown as typeof fetch);
    await expect(replayClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).resolves.toMatchObject({ outcome: "replay", task: completedTask, snapshot: replaySnapshot });

    const crossCourseSnapshot = { ...snapshot, pending_tasks: [{ ...task, course_id: "course-2" }] };
    const crossCourseSnapshotClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(crossCourseSnapshot)) as unknown as typeof fetch);
    await expect(crossCourseSnapshotClient.learningSnapshot({ courseId: "course-1", availableMinutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const crossCourseTaskClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task: { ...task, course_id: "course-2" }, candidate, bootstrap: null }, 201)) as unknown as typeof fetch);
    await expect(crossCourseTaskClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const wrongCandidateClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate: { ...candidate, why: "Mismatched rationale." }, bootstrap: null }, 201)) as unknown as typeof fetch);
    await expect(wrongCandidateClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const wrongTaskClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task: { ...task, source_id: "concept-2" }, candidate, bootstrap: null }, 201)) as unknown as typeof fetch);
    await expect(wrongTaskClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const manualTask = { ...task, source_type: "manual", source_id: null };
    const manualCoveredSnapshot = { ...snapshot, pending_tasks: [manualTask] };
    const manualCoveredClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "covered_by_active_task", course_id: "course-1", snapshot: manualCoveredSnapshot, task: manualTask, candidate, bootstrap: null })) as unknown as typeof fetch);
    await expect(manualCoveredClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).resolves.toMatchObject({ outcome: "covered_by_active_task", task: manualTask });

    const invalidCompletedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "covered_by_active_task", course_id: "course-1", snapshot: replaySnapshot, task: completedTask, candidate, bootstrap: null })) as unknown as typeof fetch);
    await expect(invalidCompletedClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const courseTwoTask = { ...task, course_id: "course-2" };
    const courseTwoSnapshot = { ...snapshot, course_id: "course-2", pending_tasks: [courseTwoTask] };
    const wrongGetCourseClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(courseTwoSnapshot)) as unknown as typeof fetch);
    await expect(wrongGetCourseClient.learningSnapshot({ courseId: "course-1", availableMinutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const thirtyMinuteSnapshot = { ...snapshot, available_minutes: 30 };
    const wrongGetMinutesClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(thirtyMinuteSnapshot)) as unknown as typeof fetch);
    await expect(wrongGetMinutesClient.learningSnapshot({ courseId: "course-1", availableMinutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const wrongPostCourseClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-2", snapshot: courseTwoSnapshot, task: courseTwoTask, candidate, bootstrap: null }, 201)) as unknown as typeof fetch);
    await expect(wrongPostCourseClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const wrongPostMinutesClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot: thirtyMinuteSnapshot, task, candidate, bootstrap: null }, 201)) as unknown as typeof fetch);
    await expect(wrongPostMinutesClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const emptyWithCandidateClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "empty", course_id: "course-1", snapshot: { ...snapshot, pending_tasks: [] }, task: null, candidate: null, bootstrap: null })) as unknown as typeof fetch);
    await expect(emptyWithCandidateClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const wrongActionCandidate = { ...candidate, action: "review_due" as const };
    const wrongActionClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ ...snapshot, candidates: [wrongActionCandidate] })) as unknown as typeof fetch);
    await expect(wrongActionClient.learningSnapshot({ courseId: "course-1", availableMinutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const misconceptionCandidate = {
      ...candidate,
      id: "misconception:misconception-1:address_repeated_misconception",
      action: "address_repeated_misconception" as const,
      target_type: "misconception" as const,
      target_id: "misconception-1",
      concept_id: "concept-1",
    };
    const wrongMisconceptionTask = { ...task, id: "misconception-task", concept_id: "concept-2", source_id: "concept-2" };
    const wrongMisconceptionSnapshot = { ...snapshot, pending_tasks: [wrongMisconceptionTask], candidates: [misconceptionCandidate] };
    const wrongMisconceptionClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot: wrongMisconceptionSnapshot, task: wrongMisconceptionTask, candidate: misconceptionCandidate, bootstrap: null }, 201)) as unknown as typeof fetch);
    await expect(wrongMisconceptionClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const bootstrap = {
      course_id: "course-1", document_id: "document-1", concept_id: "concept-1", concept_name: "Limits",
      mastery_probability: 0.2, mastery_attempts: 0, concept_created: true, mastery_initialized: true,
      mastery_initialization_algorithm: "bootstrap/v1", mastery_initialization_algorithm_version: "1.0.0",
    } as const;
    const bootstrapClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap }, 201)) as unknown as typeof fetch);
    await expect(bootstrapClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20, document_id: "document-1" })).resolves.toMatchObject({ bootstrap });

    const wrongBootstrapCourseClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: { ...bootstrap, course_id: "course-2" } }, 201)) as unknown as typeof fetch);
    await expect(wrongBootstrapCourseClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20, document_id: "document-1" })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const wrongBootstrapDocumentClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap }, 201)) as unknown as typeof fetch);
    await expect(wrongBootstrapDocumentClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20, document_id: "document-2" })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const unexpectedBootstrapClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap }, 201)) as unknown as typeof fetch);
    await expect(unexpectedBootstrapClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const missingBootstrapClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "task_created", course_id: "course-1", snapshot, task, candidate, bootstrap: null }, 201)) as unknown as typeof fetch);
    await expect(missingBootstrapClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20, document_id: "document-1" })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const emptyBootstrapClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "empty", course_id: "course-1", snapshot: { ...snapshot, pending_tasks: [], candidates: [] }, task: null, candidate: null, bootstrap }, 200)) as unknown as typeof fetch);
    await expect(emptyBootstrapClient.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20, document_id: "document-1" })).resolves.toMatchObject({ outcome: "empty", task: null, candidate: null, bootstrap });
  });

  it("rejects malformed autonomous-learning requests and responses before they affect the UI", async () => {
    const fetchMock = vi.fn();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await expect(Promise.resolve().then(() => client.learningSnapshot({ courseId: " ", availableMinutes: 20 }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.learningSnapshot({ courseId: " course-1 ", availableMinutes: 20 }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.learningSnapshot({ courseId: "course id", availableMinutes: 20 }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.learningSnapshot({ courseId: ".course-1", availableMinutes: 20 }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.learningSnapshot({ courseId: "course/1", availableMinutes: 20 }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 0 }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.createAutonomousRecommendation({ course_id: "course-1", available_minutes: 20, time_zone: "Not/A Zone" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    expect(fetchMock).not.toHaveBeenCalled();

    const invalid = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({
      course_id: "course-1", as_of: "2026-07-17T10:00:00+00:00", available_minutes: 20,
      due_review_count: 0, incomplete_session_count: 0, misconception_count: 0,
      pending_tasks: [], candidates: [], mastery_gap_count: 1, unexpected: true,
    })) as unknown as typeof fetch);
    await expect(invalid.learningSnapshot({ courseId: "course-1", availableMinutes: 20 })).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("validates autonomous study session start and persisted reader scope", async () => {
    const task = { id: "task-1", course_id: "course-1", concept_id: "concept-1", title: "Study limits", reason: "Weak mastery.", estimated_minutes: 20, status: "upcoming", source_type: "weak_concept", source_id: "concept-1" } as const;
    const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Study limits", mode: "study", goal: "Build a grounded understanding.", estimated_minutes: 20, status: "studying", progress: 0.25, revision: 1, created_at: "2026-07-17T10:00:00+00:00", updated_at: "2026-07-17T10:00:00+00:00", started_at: "2026-07-17T10:00:00+00:00" } as const;
    const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Indexed course evidence is available.", units: [
      { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"], title: "First source segment", objective: "Read the source.", content: "Untrusted source display text.", estimated_minutes: 10, status: "active" },
      { id: "unit-2", ordinal: 1, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-2"], title: "Second source segment", objective: "Connect the source.", content: "More display text.", estimated_minutes: 10, status: "ready" },
    ] } as const;
    const start = { outcome: "session_created" as const, course_id: "course-1", task, session, plan, blocked_reason: null, recovery_action: null };
    const read = { outcome: "ready" as const, course_id: "course-1", session, plan, current_unit_id: "unit-1", recovery_action: null };
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(start, 201)).mockResolvedValueOnce(jsonResponse(read));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await expect(client.startAutonomousStudySession({ course_id: "course-1", task_id: "task-1" })).resolves.toEqual(start);
    await expect(client.getStudySession("session-1", "course-1")).resolves.toEqual(read);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8080/v1/autonomous-study-sessions");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1?course_id=course-1");

    const history = { course_id: "course-1", sessions: [session] };
    const historyFetch = vi.fn(async () => jsonResponse(history));
    const historyClient = createLearningCoreClient("http://127.0.0.1:8080", token, historyFetch as unknown as typeof fetch);
    await expect(historyClient.listStudySessions("course-1")).resolves.toEqual(history);
    expect((historyFetch.mock.calls[0] as unknown as [string])[0]).toBe("http://127.0.0.1:8080/v1/study-sessions?course_id=course-1");
    const wrongHistory = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ course_id: "course-1", sessions: [{ ...session, course_id: "course-2" }] })) as unknown as typeof fetch);
    await expect(wrongHistory.listStudySessions("course-1")).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const pausedSession = { ...session, status: "paused" as const, resume_from_status: "studying" as const, revision: 2 };
    const resumedSession = { ...session, resume_from_status: null, revision: 3 };
    const controlFetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ outcome: "applied", command: "pause", course_id: "course-1", session: pausedSession }))
      .mockResolvedValueOnce(jsonResponse({ outcome: "applied", command: "resume", course_id: "course-1", session: resumedSession }));
    const controlClient = createLearningCoreClient("http://127.0.0.1:8080", token, controlFetch as unknown as typeof fetch);
    const pauseRequest = { course_id: "course-1", expected_revision: 1, idempotency_key: "pause-study-session-0001" };
    const resumeRequest = { course_id: "course-1", expected_revision: 2, idempotency_key: "resume-study-session-0001" };
    await expect(controlClient.pauseStudySession("session-1", pauseRequest)).resolves.toMatchObject({ command: "pause", session: { status: "paused", resume_from_status: "studying" } });
    await expect(controlClient.resumeStudySession("session-1", resumeRequest)).resolves.toMatchObject({ command: "resume", session: { status: "studying", resume_from_status: null } });
    expect((controlFetch.mock.calls[0] as unknown as [string])[0]).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/pause");
    expect(JSON.parse(String((controlFetch.mock.calls[0] as unknown as [string, RequestInit])[1].body))).toEqual(pauseRequest);
    expect((controlFetch.mock.calls[1] as unknown as [string])[0]).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/resume");

    const invalidPause = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ outcome: "applied", command: "pause", course_id: "course-1", session })) as unknown as typeof fetch);
    await expect(invalidPause.pauseStudySession("session-1", pauseRequest)).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const wrongStatus = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(start)) as unknown as typeof fetch);
    await expect(wrongStatus.startAutonomousStudySession({ course_id: "course-1", task_id: "task-1" })).rejects.toBeInstanceOf(LearningCoreSchemaError);
    const wrongRead = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ ...read, course_id: "course-2", session: { ...session, course_id: "course-2" } })) as unknown as typeof fetch);
    await expect(wrongRead.getStudySession("session-1", "course-1")).rejects.toBeInstanceOf(LearningCoreSchemaError);
    const unavailablePlan = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ ...read, outcome: "plan_unavailable", plan: null, current_unit_id: null, recovery_action: "Return to the feed." })) as unknown as typeof fetch);
    await expect(unavailablePlan.getStudySession("session-1", "course-1")).resolves.toMatchObject({ outcome: "plan_unavailable" });

    const resumed = { ...start, outcome: "resumed" as const, plan: null };
    const resumedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(resumed)) as unknown as typeof fetch);
    await expect(resumedClient.startAutonomousStudySession({ course_id: "course-1", task_id: "task-1" })).resolves.toEqual(resumed);
    const sourceTask = { ...task, source_type: "study_session", source_id: "session-1" };
    const sourceResumed = { ...resumed, task: sourceTask, session: { ...session, originating_task_id: null } };
    const sourceClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(sourceResumed)) as unknown as typeof fetch);
    await expect(sourceClient.startAutonomousStudySession({ course_id: "course-1", task_id: "task-1" })).resolves.toEqual(sourceResumed);
    const wrongSourceClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ ...sourceResumed, task: { ...sourceTask, source_id: "session-other" } })) as unknown as typeof fetch);
    await expect(wrongSourceClient.startAutonomousStudySession({ course_id: "course-1", task_id: "task-1" })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const visibleTaskReasons = ["task_not_actionable", "task_not_autonomous", "task_missing_concept", "source_session_unavailable", "originating_session_terminal", "no_indexed_source"] as const;
    for (const reason of visibleTaskReasons) {
      const blocked = { outcome: "blocked" as const, course_id: "course-1", task, session: null, plan: null, blocked_reason: reason, recovery_action: "Use the typed recovery." };
      const blockedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(blocked)) as unknown as typeof fetch);
      await expect(blockedClient.startAutonomousStudySession({ course_id: "course-1", task_id: "task-1" })).resolves.toEqual(blocked);
    }
    for (const reason of ["task_not_found", "task_outside_course"] as const) {
      const blocked = { outcome: "blocked" as const, course_id: "course-1", task: null, session: null, plan: null, blocked_reason: reason, recovery_action: "Use the typed recovery." };
      const blockedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(blocked)) as unknown as typeof fetch);
      await expect(blockedClient.startAutonomousStudySession({ course_id: "course-1", task_id: "task-1" })).resolves.toEqual(blocked);
    }
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

describe("LearningCoreClient review contract", () => {
  const reviewItem = {
    id: "review-1", course_id: "course-1", course_title: "Calculus I", concept_id: "concept-1", concept_name: "Chain rule",
    item_type: "free_recall", prompt: "Explain the chain rule.", expected_answer: { accepted_answers: ["Outer derivative times inner derivative."] },
    source_type: "manual", source_id: null, due_at: "2026-07-20T08:00:00+00:00", state: "new", scheduler: "fsrs",
    scheduler_version: "fsrs-6.3.1-keen-v1", revision: 0, repetitions: 0, lapses: 0,
  };

  it("lists validated due reviews and sends one revision-bound rating", async () => {
    const attempt = {
      outcome: "applied", review_item_id: "review-1", rating: "good", response: "My recall",
      reviewed_at: "2026-07-20T09:00:00+00:00",
      schedule: { due_at: "2026-07-22T09:00:00+00:00", last_reviewed_at: "2026-07-20T09:00:00+00:00", state: "learning", scheduler: "fsrs", scheduler_version: "fsrs-6.3.1-keen-v1", revision: 1, repetitions: 1, lapses: 0 },
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ as_of: "2026-07-20T09:00:00+00:00", items: [reviewItem] }))
      .mockResolvedValueOnce(jsonResponse(attempt, 201));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.listDueReviews({ courseId: "course-1", limit: 12 })).resolves.toMatchObject({ items: [{ id: "review-1" }] });
    await expect(client.recordReviewAttempt("review-1", {
      rating: "good",
      response: "My recall",
      expectedRevision: 0,
      taskContext: { taskId: "task-review-1", courseId: "course-1" },
      idempotencyKey: "review-attempt-key-1",
    })).resolves.toEqual(attempt);

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8080/v1/reviews/due?course_id=course-1&limit=12");
    const [, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      rating: "good",
      response: "My recall",
      expectedRevision: 0,
      taskContext: { taskId: "task-review-1", courseId: "course-1" },
      idempotencyKey: "review-attempt-key-1",
    });
  });

  it("rejects incomplete Review task context before sending a rating", async () => {
    const fetchMock = vi.fn();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    expect(() => client.recordReviewAttempt("review-1", {
      rating: "good",
      response: "",
      expectedRevision: 0,
      taskContext: { taskId: "task-review-1" } as never,
      idempotencyKey: "review-attempt-key-partial",
    })).toThrow(LearningCoreRequestError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["review_task_context_conflict", "This saved review task no longer matches the due item."],
    ["review_attempt_idempotency_conflict", "This rating does not match the saved review submission."],
  ] as const)("preserves non-retryable Review error code %s", async (code, message) => {
    const fetchMock = vi.fn(async () => jsonResponse({
      detail: {
        code,
        message,
        retryable: false,
        recoveryAction: "Return to the Learning Feed and open a current task.",
        automaticRecovery: false,
      },
    }, 409));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    const error = await client.recordReviewAttempt("review-1", {
      rating: "good",
      response: "",
      expectedRevision: 0,
      taskContext: { taskId: "task-review-1", courseId: "course-1" },
      idempotencyKey: "review-attempt-key-conflict",
    }).catch((caught: unknown) => caught);

    expect(error).toMatchObject({
      status: 409,
      detail: {
        code,
        message,
        retryable: false,
        recovery: "Return to the Learning Feed and open a current task.",
      },
    });
  });

  it("rejects future queue items and inconsistent write status", async () => {
    const futureQueue = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ as_of: "2026-07-20T09:00:00+00:00", items: [{ ...reviewItem, due_at: "2026-07-21T09:00:00+00:00" }] })) as unknown as typeof fetch);
    const replayAsCreated = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({
      outcome: "replayed", review_item_id: "review-1", rating: "good", response: "", reviewed_at: "2026-07-20T09:00:00+00:00",
      schedule: { due_at: "2026-07-22T09:00:00+00:00", last_reviewed_at: "2026-07-20T09:00:00+00:00", state: "learning", scheduler: "fsrs", scheduler_version: "fsrs-6.3.1-keen-v1", revision: 1, repetitions: 1, lapses: 0 },
    }, 201)) as unknown as typeof fetch);

    await expect(futureQueue.listDueReviews()).rejects.toBeInstanceOf(LearningCoreSchemaError);
    await expect(replayAsCreated.recordReviewAttempt("review-1", { rating: "good", response: "", expectedRevision: 0, idempotencyKey: "review-attempt-key-2" })).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});

const metadataEvent = {
  runId: "run-1",
  conversationId: "11111111-1111-4111-8111-111111111111",
  provider: { kind: "ollama", model: "fixture", version: "v1" },
  retrievalLimit: 8,
};
const retrievalChunk = {
  sourceIndex: 1,
  chunkId: "chunk-1",
  chunkIds: ["chunk-1"],
  documentId: "doc-1",
  documentVersionId: "version-1",
  chunkContentHash: "c".repeat(64),
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
  documentVersionId: "version-1",
  chunkContentHash: "c".repeat(64),
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
    for await (const event of client.answerStream({ question: "Why?", courseId: "course-1", conversationId: "11111111-1111-4111-8111-111111111111", retrievalLimit: 8 })) events.push(event);

    expect(events.map((event) => event.type)).toEqual(["metadata", "retrieval", "warning", "delta", "citation", "done"]);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
    expect(JSON.parse(String(init.body))).toEqual({ question: "Why?", courseId: "course-1", conversationId: "11111111-1111-4111-8111-111111111111", retrievalLimit: 8 });
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
    ["missing chunkId", { ...retrievalChunk, chunkId: undefined }],
    ["chunkId that does not lead chunkIds", { ...retrievalChunk, chunkId: "chunk-other" }],
    ["an unexpected key", { ...retrievalChunk, unexpected: "reject-me" }],
  ])("rejects retrieval chunks with %s", async (_label, invalidChunk) => {
    const wire = sseEvent("metadata", metadataEvent)
      + sseEvent("retrieval", { mode: "hybrid", warning: null, chunks: [invalidChunk] })
      + sseEvent("done", { runId: "run-1", finishReason: "stop", grounded: false, citationCount: 0, citationValidation: "structural_only" });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(wire)) as unknown as typeof fetch);
    const read = async () => {
      for await (const _event of client.answerStream({ question: "Why?" })) void _event;
    };

    await expect(read()).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("keeps a slow stream alive after retrieval instead of pre-buffering or aborting it", async () => {
    const encoder = new TextEncoder();
    const streamState: { controller: ReadableStreamDefaultController<Uint8Array> | null } = { controller: null };
    let receivedSignal: AbortSignal | null = null;
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      receivedSignal = init?.signal as AbortSignal;
      return new Response(new ReadableStream<Uint8Array>({
        start(controller) {
          streamState.controller = controller;
          controller.enqueue(encoder.encode(
            sseEvent("metadata", metadataEvent)
            + sseEvent("retrieval", { mode: "hybrid", warning: null, chunks: [retrievalChunk] }),
          ));
        },
      }), { headers: { "Content-Type": "text/event-stream" } });
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    const requestController = new AbortController();
    const events = client.answerStream({ question: "Why?" }, { signal: requestController.signal });

    await expect(events.next()).resolves.toMatchObject({ value: { type: "metadata" }, done: false });
    await expect(events.next()).resolves.toMatchObject({ value: { type: "retrieval" }, done: false });
    expect(receivedSignal).toBe(requestController.signal);
    expect(requestController.signal.aborted).toBe(false);

    const nextEvent = events.next();
    const waitStartedAt = Date.now();
    await new Promise((resolve) => setTimeout(resolve, 130));
    expect(Date.now() - waitStartedAt).toBeGreaterThanOrEqual(120);
    expect(requestController.signal.aborted).toBe(false);
    streamState.controller?.enqueue(encoder.encode(
      sseEvent("delta", { text: "Arrived later." })
      + sseEvent("done", { runId: "run-1", finishReason: "stop", grounded: false, citationCount: 0, citationValidation: "structural_only" }),
    ));
    streamState.controller?.close();
    await expect(nextEvent).resolves.toMatchObject({ value: { type: "delta", data: { text: "Arrived later." } }, done: false });
    await expect(events.next()).resolves.toMatchObject({ value: { type: "done" }, done: false });
    await expect(events.next()).resolves.toEqual({ value: undefined, done: true });
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

describe("LearningCoreClient durable conversation contract", () => {
  const sourceScope = { kind: "course" as const, courseId: "course-1" };
  const conversation = {
    id: "11111111-1111-4111-8111-111111111111",
    courseId: "course-1",
    title: "Why does direction stay stable?",
    mode: "ask" as const,
    status: "active" as const,
    sourceScope,
    createdAt: "2026-07-21T08:00:00+00:00",
    updatedAt: "2026-07-21T08:00:01+00:00",
    archivedAt: null,
  };
  const userMessage = {
    id: "22222222-2222-4222-8222-222222222222", conversationId: "11111111-1111-4111-8111-111111111111", sequence: 0, role: "user" as const, status: "completed" as const,
    content: "Why?", replyToMessageId: null, sourceScope, retrievalLimit: null,
    modelProvider: null, modelName: null, promptVersion: null, errorCode: null, errorDetail: null,
    startedAt: "2026-07-21T08:00:00+00:00", finishedAt: "2026-07-21T08:00:00+00:00",
    createdAt: "2026-07-21T08:00:00+00:00", updatedAt: "2026-07-21T08:00:00+00:00", citations: [],
  };
  const assistantMessage = {
    id: "33333333-3333-4333-8333-333333333333", conversationId: "11111111-1111-4111-8111-111111111111", sequence: 1, role: "assistant" as const, status: "cancelled" as const,
    content: "Partial", replyToMessageId: "22222222-2222-4222-8222-222222222222", sourceScope, retrievalLimit: 8,
    modelProvider: "ollama", modelName: "fixture", promptVersion: "v1", errorCode: "cancelled_by_user", errorDetail: null,
    startedAt: "2026-07-21T08:00:00+00:00", finishedAt: "2026-07-21T08:00:01+00:00",
    createdAt: "2026-07-21T08:00:00+00:00", updatedAt: "2026-07-21T08:00:01+00:00", citations: [],
  };

  it("creates, reads, lists, reconciles, and cancels with encoded authenticated routes", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ conversation, replayed: false }, 201))
      .mockResolvedValueOnce(jsonResponse(conversation))
      .mockResolvedValueOnce(jsonResponse({ messages: [userMessage, assistantMessage] }))
      .mockResolvedValueOnce(jsonResponse(assistantMessage))
      .mockResolvedValueOnce(jsonResponse({ message: assistantMessage, replayed: false }));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.createConversation({ id: "11111111-1111-4111-8111-111111111111", question: "Why?", sourceScope })).resolves.toMatchObject({ replayed: false });
    await expect(client.getConversation("11111111-1111-4111-8111-111111111111")).resolves.toEqual(conversation);
    await expect(client.listConversationMessages("11111111-1111-4111-8111-111111111111")).resolves.toMatchObject({ messages: [{ id: "22222222-2222-4222-8222-222222222222" }, { id: "33333333-3333-4333-8333-333333333333" }] });
    await expect(client.getConversationMessage("11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333")).resolves.toMatchObject({ status: "cancelled" });
    await expect(client.cancelConversationAnswer("11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333", { idempotencyKey: "cancel-key-00001" })).resolves.toMatchObject({ replayed: false });

    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([
      "http://127.0.0.1:8080/v1/conversations",
      "http://127.0.0.1:8080/v1/conversations/11111111-1111-4111-8111-111111111111",
      "http://127.0.0.1:8080/v1/conversations/11111111-1111-4111-8111-111111111111/messages",
      "http://127.0.0.1:8080/v1/conversations/11111111-1111-4111-8111-111111111111/messages/33333333-3333-4333-8333-333333333333",
      "http://127.0.0.1:8080/v1/conversations/11111111-1111-4111-8111-111111111111/messages/33333333-3333-4333-8333-333333333333/cancel",
    ]);
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual({ id: "11111111-1111-4111-8111-111111111111", question: "Why?", sourceScope });
    expect(JSON.parse(String((fetchMock.mock.calls[4]?.[1] as RequestInit).body))).toEqual({ idempotencyKey: "cancel-key-00001" });
    fetchMock.mock.calls.forEach(([, init]) => expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe(`Bearer ${token}`));
  });

  it("lists bounded conversation summaries with cursor and exact course scope", async () => {
    const summary = {
      id: conversation.id,
      title: conversation.title,
      status: "active" as const,
      sourceScope,
      courseTitle: "Calculus",
      messageCount: 2,
      lastMessagePreview: "A saved answer preview.",
      answerStatus: "completed" as const,
      createdAt: conversation.createdAt,
      updatedAt: conversation.updatedAt,
    };
    const fetchMock = vi.fn(async (_input: string | URL | Request, _init?: RequestInit) => {
      void _input;
      void _init;
      return jsonResponse({ conversations: [summary], nextCursor: "opaque-next" });
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.listConversations({ limit: 25, cursor: "opaque-current", courseId: "course-1" })).resolves.toEqual({ conversations: [summary], nextCursor: "opaque-next" });
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8080/v1/conversations?limit=25&cursor=opaque-current&course_id=course-1");
    expect(new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).get("Authorization")).toBe(`Bearer ${token}`);
  });

  it("fails closed on malformed or scope-drifting conversation summaries", async () => {
    const allIndexedSummary = {
      id: conversation.id,
      title: conversation.title,
      status: "active",
      sourceScope: { kind: "all_indexed" },
      courseTitle: null,
      messageCount: 2,
      lastMessagePreview: null,
      answerStatus: "failed",
      createdAt: conversation.createdAt,
      updatedAt: conversation.updatedAt,
    };
    const scopedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ conversations: [allIndexedSummary], nextCursor: null })) as unknown as typeof fetch);
    await expect(scopedClient.listConversations({ courseId: "course-1" })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const leakingClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ conversations: [{ ...allIndexedSummary, content: "full answer" }], nextCursor: null })) as unknown as typeof fetch);
    await expect(leakingClient.listConversations()).rejects.toBeInstanceOf(LearningCoreSchemaError);
    expect(() => scopedClient.listConversations({ limit: 51 })).toThrow(LearningCoreRequestError);
  });

  it("binds durable stream metadata to requested message identities and fails closed on a mismatch", async () => {
    const durableMetadata = { ...metadataEvent, runId: "33333333-3333-4333-8333-333333333333", userMessageId: "22222222-2222-4222-8222-222222222222", assistantMessageId: "33333333-3333-4333-8333-333333333333" };
    const wire = sseEvent("metadata", durableMetadata)
      + sseEvent("retrieval", { mode: "hybrid", warning: null, chunks: [retrievalChunk] })
      + sseEvent("delta", { text: "Persisted answer" })
      + sseEvent("done", { runId: "33333333-3333-4333-8333-333333333333", finishReason: "stop", grounded: false, citationCount: 0, citationValidation: "structural_only" });
    const fetchMock = vi.fn(async (_input: string | URL | Request, _init?: RequestInit) => {
      void _input;
      void _init;
      return sseResponse(wire);
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    const request = { question: "Why?", idempotencyKey: "answer-key-00001", userMessageId: "22222222-2222-4222-8222-222222222222", assistantMessageId: "33333333-3333-4333-8333-333333333333", sourceScope, retrievalLimit: 8 };
    const events = [];
    for await (const event of client.streamConversationAnswer("11111111-1111-4111-8111-111111111111", request)) events.push(event);
    expect(events.map((event) => event.type)).toEqual(["metadata", "retrieval", "delta", "done"]);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8080/v1/conversations/11111111-1111-4111-8111-111111111111/answers/stream");
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual(request);

    const mismatched = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(wire.replaceAll("33333333-3333-4333-8333-333333333333", "assistant-other"))) as unknown as typeof fetch);
    const readMismatch = async () => {
      for await (const _event of mismatched.streamConversationAnswer("11111111-1111-4111-8111-111111111111", request)) void _event;
    };
    await expect(readMismatch()).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const missingSnapshotIdentityWire = wire.replace(`,"documentVersionId":"version-1","chunkContentHash":"${"c".repeat(64)}"`, "");
    const missingIdentity = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(missingSnapshotIdentityWire)) as unknown as typeof fetch);
    const readMissingIdentity = async () => {
      for await (const _event of missingIdentity.streamConversationAnswer("11111111-1111-4111-8111-111111111111", request)) void _event;
    };
    await expect(readMissingIdentity()).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("accepts a durable provider failure only after its retrieval snapshot", async () => {
    const durableMetadata = { ...metadataEvent, runId: "33333333-3333-4333-8333-333333333333", userMessageId: "22222222-2222-4222-8222-222222222222", assistantMessageId: "33333333-3333-4333-8333-333333333333" };
    const wire = sseEvent("metadata", durableMetadata)
      + sseEvent("retrieval", { mode: "hybrid", warning: null, chunks: [retrievalChunk] })
      + sseEvent("error", { runId: "33333333-3333-4333-8333-333333333333", code: "provider_missing", message: "Provider is not configured.", retryable: false });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(wire)) as unknown as typeof fetch);
    const events = [];
    for await (const event of client.streamConversationAnswer("11111111-1111-4111-8111-111111111111", {
      question: "Why?",
      idempotencyKey: "answer-key-00001",
      userMessageId: "22222222-2222-4222-8222-222222222222",
      assistantMessageId: "33333333-3333-4333-8333-333333333333",
      sourceScope,
      retrievalLimit: 8,
    })) events.push(event);
    expect(events.map((event) => event.type)).toEqual(["metadata", "retrieval", "error"]);
  });

  it("rejects inconsistent durable read identities and malformed evidence hashes", async () => {
    const wrongConversation = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ ...conversation, id: "conversation-other" })) as unknown as typeof fetch);
    await expect(wrongConversation.getConversation("11111111-1111-4111-8111-111111111111")).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const invalidCitation = { ...answerCitation, documentVersionId: "version-1", chunkContentHash: "not-a-hash" };
    const malformed = { ...assistantMessage, status: "completed", finishedAt: "2026-07-21T08:00:01+00:00", citations: [invalidCitation] };
    const wrongEvidence = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(malformed)) as unknown as typeof fetch);
    await expect(wrongEvidence.getConversationMessage("11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333")).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const noRequest = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn() as unknown as typeof fetch);
    expect(() => noRequest.createConversation({ id: "not-a-uuid", question: "Why?", sourceScope })).toThrow(LearningCoreRequestError);
    const invalidLimit = async () => {
      for await (const _event of noRequest.streamConversationAnswer("11111111-1111-4111-8111-111111111111", {
        question: "Why?",
        idempotencyKey: "answer-key-00001",
        userMessageId: "22222222-2222-4222-8222-222222222222",
        assistantMessageId: "33333333-3333-4333-8333-333333333333",
        sourceScope,
        retrievalLimit: 5,
      })) void _event;
    };
    await expect(invalidLimit()).rejects.toBeInstanceOf(LearningCoreRequestError);

    const emptyExcerpt = { ...answerCitation, documentVersionId: "version-1", chunkContentHash: "c".repeat(64), excerpt: "" };
    const emptyEvidence = { ...assistantMessage, status: "completed", finishedAt: "2026-07-21T08:00:01+00:00", citations: [emptyExcerpt] };
    const emptyEvidenceClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(emptyEvidence)) as unknown as typeof fetch);
    await expect(emptyEvidenceClient.getConversationMessage("11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333")).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("accepts a completed durable replay without inventing a retrieval snapshot", async () => {
    const request = { question: "Why?", idempotencyKey: "answer-key-00001", userMessageId: "22222222-2222-4222-8222-222222222222", assistantMessageId: "33333333-3333-4333-8333-333333333333", sourceScope, retrievalLimit: 8 };
    const replayWire = sseEvent("metadata", { ...metadataEvent, runId: "33333333-3333-4333-8333-333333333333", userMessageId: "22222222-2222-4222-8222-222222222222", assistantMessageId: "33333333-3333-4333-8333-333333333333", provider: null, replayed: true })
      + sseEvent("delta", { text: "Stored answer" })
      + sseEvent("citation", answerCitation)
      + sseEvent("done", { runId: "33333333-3333-4333-8333-333333333333", finishReason: "stop", grounded: true, citationCount: 1, citationValidation: "structural_only" });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => sseResponse(replayWire)) as unknown as typeof fetch);
    const events = [];
    for await (const event of client.streamConversationAnswer("11111111-1111-4111-8111-111111111111", request)) events.push(event);
    expect(events.map((event) => event.type)).toEqual(["metadata", "delta", "citation", "done"]);
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
