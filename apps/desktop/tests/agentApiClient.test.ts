import {
  AgentEventStreamDisconnectedError,
  LearningCoreRequestError,
  LearningCoreResponseError,
  LearningCoreSchemaError,
  agentMutationActionRequestSchema,
  agentMutationActionResponseSchema,
  agentLevel2PendingApprovalSchema,
  agentRunActivitySchema,
  agentRunCreateRequestSchema,
  agentRunEventSchema,
  agentRunSchema,
  createLearningCoreClient,
} from "@keen/api-client";

const token = "a".repeat(64);
const timestamp = "2026-07-16T10:00:00+00:00";
const queuedRun = {
  id: "run-1",
  kind: "conversation",
  mode: "teach",
  status: "queued",
  provider: "automation",
  model: "fixed-actions",
  errorCode: null,
  errorDetail: null,
  createdAt: timestamp,
  updatedAt: timestamp,
  startedAt: null,
  finishedAt: null,
} as const;

const createRequest = {
  kind: "conversation",
  userIntent: "Explain limits",
  mode: "teach",
  input: { question: "What is a limit?" },
  idempotencyKey: "agent-ui-1",
} as const;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function agentSseEvent(id: string, event: string, data: unknown, lineEnding = "\n"): string {
  return `id: ${id}${lineEnding}event: ${event}${lineEnding}data: ${JSON.stringify(data)}${lineEnding}${lineEnding}`;
}

function sseResponse(wire: string | Uint8Array[]): Response {
  const parts = typeof wire === "string" ? [new TextEncoder().encode(wire)] : wire;
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      parts.forEach((part) => controller.enqueue(part));
      controller.close();
    },
  }), { status: 200, headers: { "Content-Type": "text/event-stream; charset=utf-8" } });
}

describe("LearningCoreClient Agent run JSON contract", () => {
  it("loads the latest persisted Agent activity for one explicit learning context", async () => {
    const activity = {
      run: queuedRun,
      events: [
        {
          id: "event-1",
          sequence: 0,
          type: "metadata",
          data: {
            runId: "run-1",
            provider: "automation",
            model: "fixed-actions",
            providerVersion: "v1",
          },
          createdAt: timestamp,
        },
        {
          id: "event-2",
          sequence: 1,
          type: "status",
          data: { status: "running" },
          createdAt: timestamp,
        },
      ],
    } as const;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      void input;
      void init;
      return jsonResponse(activity);
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.getLatestAgentRunActivity({ conversationId: "conversation-1" })).resolves.toEqual(activity);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8080/v1/agent/runs/latest?conversationId=conversation-1");
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe(`Bearer ${token}`);

    await expect(client.getLatestAgentRunActivity({ studySessionId: "study-session-1" })).resolves.toEqual(activity);
    expect(fetchMock.mock.calls[1]?.[0]).toBe("http://127.0.0.1:8080/v1/agent/runs/latest?studySessionId=study-session-1");
    await expect(Promise.resolve().then(() => client.getLatestAgentRunActivity({
      conversationId: "conversation-1",
      studySessionId: "study-session-1",
    } as { conversationId: string }))).rejects.toBeInstanceOf(LearningCoreRequestError);
  });

  it("fails closed on unsafe, unordered, or fabricated Agent activity snapshots", () => {
    const safeEvent = {
      id: "event-1",
      sequence: 0,
      type: "status",
      data: { status: "running" },
      createdAt: timestamp,
    } as const;
    expect(agentRunActivitySchema.safeParse({ run: null, events: [safeEvent] }).success).toBe(false);
    expect(agentRunActivitySchema.safeParse({ run: queuedRun, events: [
      { ...safeEvent, sequence: 1 },
      { ...safeEvent, id: "event-2", sequence: 0 },
    ] }).success).toBe(false);
    expect(agentRunActivitySchema.safeParse({ run: queuedRun, events: [
      { ...safeEvent, sequence: 1 },
    ] }).success).toBe(false);
    expect(agentRunActivitySchema.safeParse({ run: queuedRun, events: [
      { ...safeEvent },
      { ...safeEvent, id: "event-2", sequence: 2 },
    ] }).success).toBe(false);
    expect(agentRunActivitySchema.safeParse({ run: queuedRun, events: [{
      id: "metadata-wrong-run",
      sequence: 0,
      type: "metadata",
      data: {
        runId: "run-other",
        provider: "automation",
        model: "fixed-actions",
        providerVersion: "v1",
      },
      createdAt: timestamp,
    }] }).success).toBe(false);
    expect(agentRunActivitySchema.safeParse({ run: queuedRun, events: [
      safeEvent,
      {
        id: "metadata-late",
        sequence: 1,
        type: "metadata",
        data: {
          runId: "run-1",
          provider: "automation",
          model: "fixed-actions",
          providerVersion: "v1",
        },
        createdAt: timestamp,
      },
    ] }).success).toBe(false);
    expect(agentRunActivitySchema.safeParse({ run: queuedRun, events: [{
      ...safeEvent,
      type: "checkpoint",
      data: { label: "unsafe", data: { reasoning: "private trace" } },
    }] }).success).toBe(false);
  });

  it("creates, gets, and cancels Agent runs through authenticated strict routes", async () => {
    const cancelledRun = {
      ...queuedRun,
      status: "cancelled",
      errorCode: "cancelled",
      errorDetail: "Agent run was cancelled before starting",
      finishedAt: timestamp,
    } as const;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/cancel")) return jsonResponse({ accepted: true, run: cancelledRun });
      if (init?.method === "POST") return jsonResponse(queuedRun, 202);
      return jsonResponse(queuedRun);
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.createAgentRun(createRequest)).resolves.toEqual(queuedRun);
    await expect(client.getAgentRun("run-1")).resolves.toEqual(queuedRun);
    await expect(client.cancelAgentRun("run-1")).resolves.toEqual({ accepted: true, run: cancelledRun });

    const [, createInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(createInit.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(new Headers(createInit.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(createInit.body))).toEqual(createRequest);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:8080/v1/agent/runs",
      "http://127.0.0.1:8080/v1/agent/runs/run-1",
      "http://127.0.0.1:8080/v1/agent/runs/run-1/cancel",
    ]);
  });

  it.each(["reasoning", "chainOfThought", "hidden-reasoning", "scratchpad"]) (
    "rejects hidden reasoning recursively before sending it: %s",
    async (hiddenKey) => {
      const fetchMock = vi.fn();
      const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
      const request = { ...createRequest, input: { nested: { [hiddenKey]: "private trace" } } };

      await expect(Promise.resolve().then(() => client.createAgentRun(request))).rejects.toBeInstanceOf(LearningCoreRequestError);
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("fails closed if a run response exposes input, intent, or any unknown field", async () => {
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse({ ...queuedRun, input: { question: "secret" }, userIntent: "secret" }, 202)) as unknown as typeof fetch,
    );

    await expect(client.createAgentRun(createRequest)).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it.each([
    ["provider_missing", 503, false],
    ["provider_unavailable", 503, true],
    ["agent_busy", 409, true],
  ] as const)("maps the allowlisted %s error without exposing unknown fields", async (code, status, retryable) => {
    const fetchMock = vi.fn(async () => jsonResponse({
      detail: {
        code,
        message: `Safe ${code} message`,
        retryable,
        recoveryAction: "Use the documented recovery action.",
        providerDebugTrace: "must-not-be-mapped",
      },
    }, status));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    const error = await client.createAgentRun(createRequest).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(LearningCoreResponseError);
    expect(error).toMatchObject({
      status,
      detail: {
        code,
        retryable,
        recovery: "Use the documented recovery action.",
      },
    });
    expect((error as LearningCoreResponseError).detail).not.toHaveProperty("providerDebugTrace");
  });

  it("validates interrupted and cancelled terminal run invariants", () => {
    expect(agentRunSchema.safeParse({
      ...queuedRun,
      status: "interrupted",
      errorCode: "process_restarted",
      errorDetail: "The learning core restarted.",
      finishedAt: timestamp,
    }).success).toBe(true);
    expect(agentRunSchema.safeParse({ ...queuedRun, status: "cancelled", finishedAt: timestamp }).success).toBe(false);
    expect(agentRunSchema.safeParse({ ...queuedRun, status: "completed", errorCode: "failed", finishedAt: timestamp }).success).toBe(false);
  });

  it("keeps request and event schemas strict and bounded", () => {
    expect(agentRunCreateRequestSchema.safeParse({ ...createRequest, unknown: true }).success).toBe(false);
    expect(agentRunCreateRequestSchema.safeParse({ ...createRequest, input: { value: Number.NaN } }).success).toBe(false);
    expect(agentRunEventSchema.safeParse({
      id: "event-1",
      type: "checkpoint",
      data: { label: "private", data: { internalReasoning: "trace" } },
    }).success).toBe(false);
  });

  it("accepts only strict Level 2 approval checkpoints", () => {
    const data = { approvalId: "approval-1", toolName: "complete_study_task", summary: { title: "Complete task", taskTitle: "Read chapter", courseTitle: "Physics", effect: "Marks the local task complete." } };
    expect(agentLevel2PendingApprovalSchema.safeParse(data).success).toBe(true);
    expect(agentRunEventSchema.safeParse({ id: "approval-event", type: "checkpoint", data: { label: "approval_requested", data } }).success).toBe(true);
    expect(agentRunEventSchema.safeParse({ id: "bad-approval", type: "checkpoint", data: { label: "approval_requested", data: { ...data, args: { taskId: "private" } } } }).success).toBe(false);
    expect(agentRunEventSchema.safeParse({ id: "bad-label", type: "checkpoint", data: { label: "approval_resolved", data: { approvalId: "approval-1", status: "approved", reasoning: "private" } } }).success).toBe(false);
    expect(agentRunEventSchema.safeParse({ id: "bad-resolution-error", type: "checkpoint", data: { label: "approval_resolved", data: { approvalId: "approval-1", status: "denied", error: { detail: "private database path" } } } }).success).toBe(false);
    expect(agentRunEventSchema.safeParse({ id: "bad-resolution-status", type: "checkpoint", data: { label: "approval_resolved", data: { approvalId: "approval-1", status: "completed" } } }).success).toBe(false);
  });

  it("accepts only the redacted failed tool-result contract", () => {
    const failedResult = {
      id: "event-tool-failed",
      type: "tool_result",
      data: {
        callId: "call-failed",
        invocationId: "invocation-failed",
        toolName: "search_course_knowledge",
        failed: true,
        code: "invalid_arguments",
        retryable: true,
        replayed: false,
      },
    };

    expect(agentRunEventSchema.safeParse(failedResult).success).toBe(true);
    expect(agentRunEventSchema.safeParse({
      ...failedResult,
      data: { ...failedResult.data, exception: "/private/course.sqlite" },
    }).success).toBe(false);
    expect(agentRunEventSchema.safeParse({
      ...failedResult,
      data: { ...failedResult.data, code: "permission_denied" },
    }).success).toBe(false);
    expect(agentRunEventSchema.safeParse({
      ...failedResult,
      data: { ...failedResult.data, retryable: false },
    }).success).toBe(false);
  });
});

describe("LearningCoreClient Agent mutation action contract", () => {
  const mutationActionResponse = {
    action: "undo",
    runId: "run-1",
    targetMutationId: "mutation-1",
    invocationId: "invocation-undo-1",
    mutationId: "mutation-inverse-1",
    entityType: "study_task",
    entityId: "task-chain-rule",
    operation: "update",
    replayed: false,
  } as const;

  it("posts authenticated Undo and Redo requests with AbortSignal and preserves replay semantics", async () => {
    const controller = new AbortController();
    const responses = [
      mutationActionResponse,
      { ...mutationActionResponse, action: "redo", mutationId: "mutation-redo-1", replayed: true },
    ] as const;
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      const response = responses[fetchMock.mock.calls.length - 1];
      expect(init?.signal).toBe(controller.signal);
      return jsonResponse(response);
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.undoAgentMutation(
      "run-1",
      "mutation-1",
      { idempotencyKey: "undo-request-1" },
      { signal: controller.signal },
    )).resolves.toEqual(mutationActionResponse);
    await expect(client.redoAgentMutation(
      "run-1",
      "mutation-1",
      { idempotencyKey: "redo-request-1" },
      { signal: controller.signal },
    )).resolves.toEqual(responses[1]);

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:8080/v1/agent/runs/run-1/mutations/mutation-1/undo",
      "http://127.0.0.1:8080/v1/agent/runs/run-1/mutations/mutation-1/redo",
    ]);
    expect(fetchMock.mock.calls.map(([, init]) => ({
      authorization: new Headers(init?.headers).get("Authorization"),
      contentType: new Headers(init?.headers).get("Content-Type"),
      body: JSON.parse(String(init?.body)),
    }))).toEqual([
      { authorization: `Bearer ${token}`, contentType: "application/json", body: { idempotencyKey: "undo-request-1" } },
      { authorization: `Bearer ${token}`, contentType: "application/json", body: { idempotencyKey: "redo-request-1" } },
    ]);
  });

  it("rejects invalid IDs and non-strict request bodies before sending", async () => {
    const fetchMock = vi.fn();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    const invalidRequests = [
      () => client.undoAgentMutation("../run", "mutation-1", { idempotencyKey: "undo-1" }),
      () => client.undoAgentMutation("run-1", "mutation/1", { idempotencyKey: "undo-1" }),
      () => client.undoAgentMutation("run-1", "mutation-1", { idempotencyKey: "bad key" }),
      () => client.undoAgentMutation(
        "run-1",
        "mutation-1",
        { idempotencyKey: "undo-1", restore: true } as { idempotencyKey: string },
      ),
    ];

    for (const request of invalidRequests) {
      await expect(Promise.resolve().then(request)).rejects.toBeInstanceOf(LearningCoreRequestError);
    }
    expect(fetchMock).not.toHaveBeenCalled();
    expect(agentMutationActionRequestSchema.safeParse({ idempotencyKey: "undo-1", unknown: true }).success).toBe(false);
  });

  it("fails closed on unknown fields, invalid replay values, or response/request semantic mismatches", async () => {
    const invalidResponses = [
      { ...mutationActionResponse, privateState: "must-not-escape" },
      { ...mutationActionResponse, replayed: "false" },
      { ...mutationActionResponse, action: "redo" },
      { ...mutationActionResponse, runId: "run-other" },
      { ...mutationActionResponse, targetMutationId: "mutation-other" },
    ];

    for (const response of invalidResponses) {
      const client = createLearningCoreClient(
        "http://127.0.0.1:8080",
        token,
        vi.fn(async () => jsonResponse(response)) as unknown as typeof fetch,
      );
      await expect(client.undoAgentMutation(
        "run-1",
        "mutation-1",
        { idempotencyKey: "undo-1" },
      )).rejects.toBeInstanceOf(LearningCoreSchemaError);
    }
    expect(agentMutationActionResponseSchema.safeParse({ ...mutationActionResponse, unknown: true }).success).toBe(false);
  });

  it.each([
    [409, "undo_conflict", true],
    [403, "mutation_action_forbidden", false],
    [404, "mutation_not_found", false],
    [500, "mutation_action_failed", true],
  ] as const)("maps HTTP %i %s errors through the safe allowlist", async (status, code, retryable) => {
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse({
        detail: {
          code,
          message: `Safe ${code} message`,
          retryable,
          recoveryAction: "Refresh the Agent activity.",
          automaticRecovery: false,
          outcomeMayBeDurable: status === 500,
          databaseTrace: "private-debug-data",
        },
      }, status)) as unknown as typeof fetch,
    );

    const error = await client.undoAgentMutation(
      "run-1",
      "mutation-1",
      { idempotencyKey: "undo-error-1" },
    ).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(LearningCoreResponseError);
    expect(error).toMatchObject({
      status,
      detail: {
        code,
        retryable,
        recovery: "Refresh the Agent activity.",
      },
    });
    expect((error as LearningCoreResponseError).detail).not.toHaveProperty("databaseTrace");
    expect((error as LearningCoreResponseError).detail).not.toHaveProperty("outcomeMayBeDurable");
  });

  it("does not map an otherwise known mutation error code under the wrong HTTP status", async () => {
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse({
        detail: {
          code: "mutation_action_failed",
          message: "A mismatched status/code pair must not be trusted.",
        },
      }, 409)) as unknown as typeof fetch,
    );

    const error = await client.undoAgentMutation(
      "run-1",
      "mutation-1",
      { idempotencyKey: "undo-mismatch-1" },
    ).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(LearningCoreResponseError);
    expect(error).toMatchObject({ status: 409, detail: { code: null } });
  });
});

describe("LearningCoreClient Level 2 approval actions", () => {
  it("uses strict pending, confirm, and reject routes with replay responses", async () => {
    const approval = { approvalId: "approval-1", toolName: "complete_study_task", summary: { title: "Complete task", taskTitle: "Read chapter", courseTitle: "Physics", effect: "Marks the local task complete." } } as const;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      void init;
      const url = String(input);
      if (url.endsWith("/pending")) return jsonResponse({ run: queuedRun, approvals: [approval] });
      return jsonResponse({ run: queuedRun, approvalId: "approval-1", resolution: url.endsWith("/confirm") ? "confirmed" : "rejected", replayed: true });
    });
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await expect(client.getPendingLevel2Actions("run-1")).resolves.toEqual({ run: queuedRun, approvals: [approval] });
    await expect(client.confirmLevel2Action("run-1", "approval-1", { idempotencyKey: "approval-key-1" })).resolves.toMatchObject({ resolution: "confirmed", replayed: true });
    await expect(client.rejectLevel2Action("run-1", "approval-1", { idempotencyKey: "approval-key-1" })).resolves.toMatchObject({ resolution: "rejected", replayed: true });
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:8080/v1/agent/runs/run-1/level2-actions/pending",
      "http://127.0.0.1:8080/v1/agent/runs/run-1/level2-actions/approval-1/confirm",
      "http://127.0.0.1:8080/v1/agent/runs/run-1/level2-actions/approval-1/reject",
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ idempotencyKey: "approval-key-1" });
  });

  it.each([
    ["approval_conflict", 409, false],
    ["approval_action_failed", 500, true],
  ] as const)("maps the allowlisted %s error for approval actions", async (code, status, retryable) => {
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse({
        detail: {
          code,
          message: "The approval outcome is safe to refresh.",
          retryable,
          recoveryAction: "Refresh and use the same request key if retrying.",
        },
      }, status)) as unknown as typeof fetch,
    );

    const error = await client.confirmLevel2Action(
      "run-1",
      "approval-1",
      { idempotencyKey: "approval-key-1" },
    ).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(LearningCoreResponseError);
    expect(error).toMatchObject({ status, detail: { code, retryable } });
  });

  it("accepts expired only as a confirmation outcome", async () => {
    const failedRun = {
      ...queuedRun,
      status: "failed",
      errorCode: "approval_action_expired",
      errorDetail: "The task changed before confirmation.",
      startedAt: timestamp,
      finishedAt: timestamp,
    } as const;
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse({
        run: failedRun,
        approvalId: "approval-1",
        resolution: "expired",
        replayed: false,
      })) as unknown as typeof fetch,
    );

    await expect(client.confirmLevel2Action(
      "run-1",
      "approval-1",
      { idempotencyKey: "approval-expired-1" },
    )).resolves.toMatchObject({ resolution: "expired", run: { status: "failed" } });
    await expect(client.rejectLevel2Action(
      "run-1",
      "approval-1",
      { idempotencyKey: "approval-expired-1" },
    )).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});

describe("LearningCoreClient durable Agent SSE contract", () => {
  it("parses durable IDs across UTF-8/CRLF boundaries and reaches done", async () => {
    const wire = [
      agentSseEvent("event-1", "metadata", {
        runId: "run-1",
        provider: "automation",
        model: "fixed-actions",
        providerVersion: "v1",
      }, "\r\n"),
      agentSseEvent("event-2", "status", { status: "running" }, "\r\n"),
      agentSseEvent("event-3", "content_delta", { delta: "方向" }, "\r\n"),
      agentSseEvent("event-4", "status", { status: "completed" }, "\r\n"),
      agentSseEvent("event-5", "done", { status: "completed" }, "\r\n"),
    ].join("");
    const bytes = new TextEncoder().encode(wire);
    const direction = new TextEncoder().encode("方向");
    const start = bytes.findIndex((_, index) => direction.every((byte, offset) => bytes[index + offset] === byte));
    const fetchMock = vi.fn(async () => sseResponse([
      bytes.slice(0, start + 1),
      bytes.slice(start + 1, start + 4),
      bytes.slice(start + 4),
    ]));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    const events = [];
    for await (const event of client.agentRunEvents("run-1")) events.push(event);

    expect(events.map((event) => [event.id, event.type])).toEqual([
      ["event-1", "metadata"],
      ["event-2", "status"],
      ["event-3", "content_delta"],
      ["event-4", "status"],
      ["event-5", "done"],
    ]);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
  });

  it("sends Last-Event-ID or cursor and accepts interrupted/cancelled replay terminals", async () => {
    const responses = [
      sseResponse(
        agentSseEvent("event-3", "status", { status: "interrupted" })
        + agentSseEvent("event-4", "error", {
          code: "process_restarted",
          retryable: false,
          status: "interrupted",
          message: "The learning core restarted.",
        }),
      ),
      sseResponse(
        agentSseEvent("event-8", "status", { status: "cancelled" })
        + agentSseEvent("event-9", "error", { code: "cancelled", retryable: false, status: "cancelled" }),
      ),
    ];
    const fetchMock = vi.fn(async () => responses.shift() ?? sseResponse(""));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    const interrupted = [];
    for await (const event of client.agentRunEvents("run-1", { lastEventId: "event-2" })) interrupted.push(event);
    const cancelled = [];
    for await (const event of client.agentRunEvents("run-1", { cursor: "event-7" })) cancelled.push(event);

    expect(interrupted.at(-1)).toMatchObject({ type: "error", data: { status: "interrupted" } });
    expect(cancelled.at(-1)).toMatchObject({ type: "error", data: { status: "cancelled" } });
    const [firstUrl, firstInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [secondUrl, secondInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(firstUrl).not.toContain("cursor=");
    expect(new Headers(firstInit.headers).get("Last-Event-ID")).toBe("event-2");
    expect(secondUrl.endsWith("/events?cursor=event-7")).toBe(true);
    expect(new Headers(secondInit.headers).has("Last-Event-ID")).toBe(false);
  });

  it("returns a safe reconnect signal with the latest durable event ID on early EOF", async () => {
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => sseResponse(agentSseEvent("event-11", "content_delta", { delta: "partial" }))) as unknown as typeof fetch,
    );
    const read = async () => {
      for await (const _event of client.agentRunEvents("run-1", { lastEventId: "event-10" })) void _event;
    };

    const error = await read().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AgentEventStreamDisconnectedError);
    expect(error).toMatchObject({ runId: "run-1", lastEventId: "event-11", retryable: true });
  });

  it("accepts durable Undo audit events appended after the original terminal event", async () => {
    const wire = [
      agentSseEvent("event-done", "done", { status: "completed" }),
      agentSseEvent("event-tool-start", "tool_start", {
        invocationId: "invocation-undo-1",
        toolName: "undo_state_mutation",
        replayCandidate: false,
      }),
      agentSseEvent("event-tool-result", "tool_result", {
        invocationId: "invocation-undo-1",
        toolName: "undo_state_mutation",
        action: "undo",
        targetMutationId: "mutation-original-1",
        mutationId: "mutation-inverse-1",
        replayed: false,
      }),
      agentSseEvent("event-mutation", "state_mutation", {
        invocationId: "invocation-undo-1",
        mutationId: "mutation-inverse-1",
        entityType: "study_task",
        entityId: "task-1",
        operation: "update",
        reversible: true,
        action: "undo",
        targetMutationId: "mutation-original-1",
        replayed: false,
      }),
    ].join("");
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => sseResponse(wire)) as unknown as typeof fetch,
    );

    const events = [];
    for await (const event of client.agentRunEvents("run-1")) events.push(event);

    expect(events.map((event) => event.type)).toEqual([
      "done",
      "tool_start",
      "tool_result",
      "state_mutation",
    ]);
  });

  it("accepts a post-terminal resume batch only with explicit terminal history", async () => {
    const auditOnly = agentSseEvent("event-audit-1", "state_mutation", {
      invocationId: "invocation-undo-1",
      mutationId: "mutation-inverse-1",
      entityType: "study_task",
      entityId: "task-1",
      operation: "update",
      reversible: true,
      action: "undo",
      targetMutationId: "mutation-original-1",
      replayed: false,
    });
    const makeClient = () => createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => sseResponse(auditOnly)) as unknown as typeof fetch,
    );
    const withoutHistory = async () => {
      for await (const _event of makeClient().agentRunEvents("run-1", { lastEventId: "event-done" })) void _event;
    };
    await expect(withoutHistory()).rejects.toBeInstanceOf(AgentEventStreamDisconnectedError);

    const events = [];
    for await (const event of makeClient().agentRunEvents("run-1", {
      lastEventId: "event-done",
      terminalAlreadySeen: true,
    })) events.push(event);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ type: "state_mutation", data: { action: "undo" } });
  });

  it("maps a transport read failure to the same safe reconnect signal", async () => {
    let sent = false;
    const response = new Response(new ReadableStream<Uint8Array>({
      pull(controller) {
        if (!sent) {
          sent = true;
          controller.enqueue(new TextEncoder().encode(agentSseEvent("event-12", "status", { status: "running" })));
          return;
        }
        controller.error(new TypeError("transport internals must not escape"));
      },
    }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => response) as unknown as typeof fetch,
    );
    const read = async () => {
      for await (const _event of client.agentRunEvents("run-1", { lastEventId: "event-10" })) void _event;
    };

    const error = await read().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AgentEventStreamDisconnectedError);
    expect(error).toMatchObject({ runId: "run-1", lastEventId: "event-12", retryable: true });
    expect((error as Error).message).not.toContain("transport internals");
  });

  it("rejects conflicting cursors, missing IDs, duplicate IDs, and hidden fields", async () => {
    const fetchMock = vi.fn();
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    const conflict = async () => {
      for await (const _event of client.agentRunEvents("run-1", { lastEventId: "event-1", cursor: "event-2" })) void _event;
    };
    await expect(conflict()).rejects.toBeInstanceOf(LearningCoreRequestError);
    expect(fetchMock).not.toHaveBeenCalled();

    const invalidWires = [
      "event: done\ndata: {\"status\":\"completed\"}\n\n",
      agentSseEvent("event-1", "status", { status: "running" }) + agentSseEvent("event-1", "done", { status: "completed" }),
      agentSseEvent("event-1", "checkpoint", { label: "bad", data: { thoughts: "private" } }),
    ];
    for (const wire of invalidWires) {
      const invalidClient = createLearningCoreClient(
        "http://127.0.0.1:8080",
        token,
        vi.fn(async () => sseResponse(wire)) as unknown as typeof fetch,
      );
      const read = async () => {
        for await (const _event of invalidClient.agentRunEvents("run-1")) void _event;
      };
      await expect(read()).rejects.toBeInstanceOf(LearningCoreSchemaError);
    }

    const duplicateCursorClient = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => sseResponse(agentSseEvent("event-7", "done", { status: "completed" }))) as unknown as typeof fetch,
    );
    const duplicateCursorRead = async () => {
      for await (const _event of duplicateCursorClient.agentRunEvents("run-1", { lastEventId: "event-7" })) void _event;
    };
    await expect(duplicateCursorRead()).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});
