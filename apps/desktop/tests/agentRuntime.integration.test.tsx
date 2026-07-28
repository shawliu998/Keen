import { StrictMode } from "react";
import { act } from "react-dom/test-utils";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  AgentEventStreamDisconnectedError,
  LearningCoreResponseError,
  type AgentCancelResponse,
  type AgentLevel2ApprovalResponse,
  type AgentLevel2PendingActionsResponse,
  type AgentMutationActionResponse,
  type AgentRun,
  type AgentRunCreateRequest,
  type AgentRunActivityContext,
  type AgentRunActivityEvent,
  type AgentRunEvent,
  type AgentRunEventStreamOptions,
  type LearningCoreClient,
  type RequestOptions,
} from "@keen/api-client";
import {
  AgentRuntimeProvider,
  useAgentRuntime,
} from "../src/services/AgentRuntimeProvider";

const learningCore = vi.hoisted(() => ({
  current: {
    status: "healthy",
    client: null as LearningCoreClient | null,
    connectionGeneration: 1,
  },
}));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => learningCore.current,
}));

const now = "2026-07-16T09:00:00.000Z";
const startRequest = {
  kind: "conversation" as const,
  userIntent: "Teach me eigenvectors",
  mode: "teach" as const,
  input: {},
};

function run(status: AgentRun["status"], id = "run-1"): AgentRun {
  const unsuccessful = status === "failed" || status === "cancelled" || status === "interrupted";
  const terminal = status === "completed" || unsuccessful;
  return {
    id,
    kind: "conversation",
    mode: "teach",
    status,
    provider: "test-provider",
    model: "test-model",
    errorCode: unsuccessful ? `${status}_for_test` : null,
    errorDetail: unsuccessful ? "The test run ended." : null,
    createdAt: now,
    updatedAt: now,
    startedAt: status === "queued" ? null : now,
    finishedAt: terminal ? now : null,
  };
}

async function* eventStream(events: readonly AgentRunEvent[]): AsyncGenerator<AgentRunEvent> {
  for (const event of events) yield event;
}

type MockClient = {
  client: LearningCoreClient;
  createAgentRun: ReturnType<typeof vi.fn>;
  getAgentRun: ReturnType<typeof vi.fn>;
  cancelAgentRun: ReturnType<typeof vi.fn>;
  agentRunEvents: ReturnType<typeof vi.fn>;
  undoAgentMutation: ReturnType<typeof vi.fn>;
  redoAgentMutation: ReturnType<typeof vi.fn>;
  getPendingLevel2Actions: ReturnType<typeof vi.fn>;
  confirmLevel2Action: ReturnType<typeof vi.fn>;
  rejectLevel2Action: ReturnType<typeof vi.fn>;
  getLatestAgentRunActivity: ReturnType<typeof vi.fn>;
};

function makeClient(overrides: Partial<{
  createAgentRun: (request: AgentRunCreateRequest, options?: RequestOptions) => Promise<AgentRun>;
  getAgentRun: (runId: string, options?: RequestOptions) => Promise<AgentRun>;
  cancelAgentRun: (runId: string, options?: RequestOptions) => Promise<AgentCancelResponse>;
  agentRunEvents: (runId: string, options?: AgentRunEventStreamOptions) => AsyncGenerator<AgentRunEvent>;
  undoAgentMutation: LearningCoreClient["undoAgentMutation"];
  redoAgentMutation: LearningCoreClient["redoAgentMutation"];
  getPendingLevel2Actions: (runId: string, options?: RequestOptions) => Promise<AgentLevel2PendingActionsResponse>;
  confirmLevel2Action: LearningCoreClient["confirmLevel2Action"];
  rejectLevel2Action: LearningCoreClient["rejectLevel2Action"];
  getLatestAgentRunActivity: (context: AgentRunActivityContext, options?: RequestOptions) => Promise<{
    run: AgentRun | null;
    events: readonly AgentRunActivityEvent[];
  }>;
}> = {}): MockClient {
  let getAttempt = 0;
  const createAgentRun = vi.fn(overrides.createAgentRun ?? (async () => run("queued")));
  const getAgentRun = vi.fn(overrides.getAgentRun ?? (async () => {
    getAttempt += 1;
    return run(getAttempt === 1 ? "running" : "completed");
  }));
  const cancelAgentRun = vi.fn(overrides.cancelAgentRun ?? (async () => ({ accepted: true, run: run("cancelled") })));
  const agentRunEvents = vi.fn(overrides.agentRunEvents ?? (() => eventStream([
    { id: "event-1", type: "status", data: { status: "running" } },
    { id: "event-2", type: "done", data: { status: "completed" } },
  ])));
  const undoAgentMutation = vi.fn(overrides.undoAgentMutation ?? (async (runId: string, mutationId: string) => mutationResult("undo", runId, mutationId, false)));
  const redoAgentMutation = vi.fn(overrides.redoAgentMutation ?? (async (runId: string, mutationId: string) => mutationResult("redo", runId, mutationId, false)));
  const getPendingLevel2Actions = vi.fn(overrides.getPendingLevel2Actions ?? (async () => ({ run: run("waiting_approval"), approvals: [] })));
  const confirmLevel2Action = vi.fn(overrides.confirmLevel2Action ?? (async (runId: string, approvalId: string) => approvalResult(runId, approvalId, "confirmed")));
  const rejectLevel2Action = vi.fn(overrides.rejectLevel2Action ?? (async (runId: string, approvalId: string) => approvalResult(runId, approvalId, "rejected")));
  const getLatestAgentRunActivity = vi.fn(overrides.getLatestAgentRunActivity ?? (async () => ({ run: null, events: [] })));
  const client = {
    createAgentRun,
    getAgentRun,
    cancelAgentRun,
    agentRunEvents,
    undoAgentMutation,
    redoAgentMutation,
    getPendingLevel2Actions,
    getLatestAgentRunActivity,
    confirmLevel2Action,
    rejectLevel2Action,
  } as unknown as LearningCoreClient;
  return {
    client,
    createAgentRun,
    getAgentRun,
    cancelAgentRun,
    agentRunEvents,
    undoAgentMutation,
    redoAgentMutation,
    getPendingLevel2Actions,
    getLatestAgentRunActivity,
    confirmLevel2Action,
    rejectLevel2Action,
  };
}

function mutationResult(
  action: "undo" | "redo",
  runId: string,
  mutationId: string,
  replayed: boolean,
): AgentMutationActionResponse {
  return {
    action,
    runId,
    targetMutationId: mutationId,
    invocationId: `${action}-invocation`,
    mutationId: `${action}-mutation`,
    entityType: "study_task",
    entityId: "task-1",
    operation: "update",
    replayed,
  };
}

function approvalResult(
  runId: string,
  approvalId: string,
  resolution: "confirmed" | "rejected" | "expired",
  status: AgentRun["status"] = resolution === "confirmed"
    ? "completed"
    : resolution === "rejected"
      ? "cancelled"
      : "failed",
): AgentLevel2ApprovalResponse {
  return { run: run(status, runId), approvalId, resolution, replayed: false };
}

const pendingApproval = {
  approvalId: "approval-1",
  toolName: "complete_study_task" as const,
  summary: {
    title: "Complete local task",
    taskTitle: "Read chapter",
    courseTitle: "Physics",
    effect: "Marks the local task complete.",
  },
};

function Harness() {
  const runtime = useAgentRuntime();
  return <>
    <button onClick={() => void runtime.startRun(startRequest)}>Start run</button>
    <button onClick={() => void runtime.cancelRun()}>Cancel run</button>
    <button onClick={() => void runtime.undoMutation("mutation-1")}>Undo mutation</button>
    <button onClick={() => void runtime.redoMutation("mutation-1")}>Redo mutation</button>
    <button onClick={() => void runtime.confirmApproval?.("approval-1")}>Confirm approval</button>
    <button onClick={() => void runtime.rejectApproval?.("approval-1")}>Reject approval</button>
    <output data-testid="runtime">{JSON.stringify({
      phase: runtime.phase,
      status: runtime.activity.status,
      content: runtime.activity.content,
      mutationCount: runtime.activity.mutations.length,
      mutations: runtime.activity.mutations,
      issue: runtime.issue,
      mutationAction: runtime.mutationAction,
      run: runtime.run,
      pendingApproval: runtime.activity.pendingApproval,
      approvalAction: runtime.approvalAction,
    })}</output>
  </>;
}

function RestoreHarness() {
  const runtime = useAgentRuntime();
  return <>
    <button onClick={() => runtime.setActivityContext({ conversationId: "convo-empty" })}>Restore empty context</button>
    <button onClick={() => runtime.setActivityContext({ conversationId: "convo-terminal" })}>Restore terminal context</button>
    <button onClick={() => runtime.setActivityContext({ conversationId: "convo-stale" })}>Restore stale context</button>
    <button onClick={() => runtime.setActivityContext({ conversationId: "convo-fresh" })}>Restore fresh context</button>
    <button onClick={() => runtime.refreshActivityContext?.("new-run")}>Refresh known activity context</button>
    <button onClick={() => void runtime.startRun(startRequest)}>Start while restoring</button>
    <output data-testid="restore-run-id">{runtime.run?.id ?? "null"}</output>
    <output data-testid="restore-phase">{runtime.phase}</output>
    <output data-testid="restore-activity-status">{runtime.activity.status}</output>
    <output data-testid="restore-content">{runtime.activity.content}</output>
    <output data-testid="restore-issue">{runtime.issue?.code ?? "null"}</output>
    <output data-testid="restore-context">{JSON.stringify(runtime.activityContext)}</output>
  </>;
}

function Runtime({ strict = false }: { strict?: boolean }) {
  const content = <AgentRuntimeProvider><Harness /></AgentRuntimeProvider>;
  return strict ? <StrictMode>{content}</StrictMode> : content;
}

function RestoreRuntime() {
  return <AgentRuntimeProvider><RestoreHarness /></AgentRuntimeProvider>;
}

function setClient(mock: MockClient, generation = 1): void {
  learningCore.current = { status: "healthy", client: mock.client, connectionGeneration: generation };
}

function runtimeText(): string {
  return screen.getByTestId("runtime").textContent ?? "";
}

function restoreRuntimeText() {
  return {
    runId: screen.getByTestId("restore-run-id").textContent ?? "",
    phase: screen.getByTestId("restore-phase").textContent ?? "",
    content: screen.getByTestId("restore-content").textContent ?? "",
    status: screen.getByTestId("restore-activity-status").textContent ?? "",
    issue: screen.getByTestId("restore-issue").textContent ?? "",
    context: screen.getByTestId("restore-context").textContent ?? "",
  };
}

beforeEach(() => {
  learningCore.current = { status: "healthy", client: null, connectionGeneration: 1 };
});

describe("AgentRuntimeProvider", () => {
  it("fails closed while a context snapshot is restoring", async () => {
    let resolveRestore!: (value: { run: AgentRun | null; events: readonly AgentRunActivityEvent[] }) => void;
    const restoring = new Promise<{ run: AgentRun | null; events: readonly AgentRunActivityEvent[] }>((resolve) => {
      resolveRestore = resolve;
    });
    const mock = makeClient({ getLatestAgentRunActivity: () => restoring });
    setClient(mock);
    render(<RestoreRuntime />);

    fireEvent.click(screen.getByRole("button", { name: "Restore empty context" }));
    expect(screen.getByTestId("restore-phase")).toHaveTextContent("recovering");
    fireEvent.click(screen.getByRole("button", { name: "Start while restoring" }));
    expect(mock.createAgentRun).not.toHaveBeenCalled();

    resolveRestore({ run: null, events: [] });
    await waitFor(() => expect(screen.getByTestId("restore-phase")).toHaveTextContent("idle"));
  });

  it("preserves a displayed terminal run when the next create request fails", async () => {
    let createAttempt = 0;
    const createFailure = new LearningCoreResponseError(409, {
      message: "another run is active",
      retryable: true,
      recovery: "wait",
      documentId: null,
      code: "agent_busy",
    }, null);
    const mock = makeClient({
      createAgentRun: async () => {
        createAttempt += 1;
        if (createAttempt === 1) return run("queued", "visible-run");
        throw createFailure;
      },
      getAgentRun: async () => run("completed", "visible-run"),
      agentRunEvents: () => eventStream([
        { id: "visible-content", type: "content_delta", data: { delta: "Keep this terminal response" } },
        { id: "visible-done", type: "done", data: { status: "completed" } },
      ]),
    });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain("Keep this terminal response"));
    await waitFor(() => expect(runtimeText()).toContain('"phase":"idle"'));

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"code":"agent_busy"'));
    expect(runtimeText()).toContain('"id":"visible-run"');
    expect(runtimeText()).toContain("Keep this terminal response");
  });

  it("surfaces provider_missing safely without creating a run or starting a stream", async () => {
    const providerError = new LearningCoreResponseError(503, {
      message: "secret provider path /Users/private/key",
      retryable: false,
      recovery: "secret recovery",
      documentId: null,
      code: "provider_missing",
    }, "request-1");
    const mock = makeClient({ createAgentRun: async () => { throw providerError; } });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"code":"provider_missing"'));
    expect(runtimeText()).not.toContain("/Users/private/key");
    expect(mock.getAgentRun).not.toHaveBeenCalled();
    expect(mock.agentRunEvents).not.toHaveBeenCalled();
  });

  it("creates only from the user event under StrictMode and consumes content through normal EOF", async () => {
    const mock = makeClient({
      agentRunEvents: () => eventStream([
        { id: "event-1", type: "content_delta", data: { delta: "Visible answer" } },
        { id: "event-2", type: "done", data: { status: "completed" } },
      ]),
    });
    setClient(mock);
    render(<Runtime strict />);
    expect(mock.createAgentRun).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain("Visible answer"));
    await waitFor(() => expect(runtimeText()).toContain('"phase":"idle"'));
    expect(runtimeText()).toContain('"status":"completed"');
    expect(mock.createAgentRun).toHaveBeenCalledTimes(1);
    expect(mock.getAgentRun).toHaveBeenCalledTimes(2);
  });

  it("resumes after a stream disconnect and keeps consuming audit events after done", async () => {
    let attempt = 0;
    const stream = vi.fn((_runId: string, options?: AgentRunEventStreamOptions) => {
      attempt += 1;
      if (attempt === 1) {
        return (async function* () {
          yield { id: "event-1", type: "content_delta", data: { delta: "Part A" } } as AgentRunEvent;
          yield { id: "event-2", type: "done", data: { status: "completed" } } as AgentRunEvent;
          throw new AgentEventStreamDisconnectedError("run-1", "event-2");
        })();
      }
      expect(options?.lastEventId).toBe("event-2");
      expect(options?.terminalAlreadySeen).toBe(true);
      return eventStream([
        {
          id: "event-3",
          type: "state_mutation",
          data: {
            invocationId: "invocation-1",
            mutationId: "undo-mutation-1",
            entityType: "study_task",
            entityId: "task-1",
            operation: "update",
            reversible: true,
            action: "undo",
            targetMutationId: "mutation-1",
            replayed: false,
          },
        },
      ]);
    });
    const mock = makeClient({ agentRunEvents: stream });
    setClient(mock);
    render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(runtimeText()).toContain('"mutationCount":1'), { timeout: 2_000 });
    expect(runtimeText()).toContain('"status":"completed"');
    expect(runtimeText()).toContain('"action":"undo"');
    expect(runtimeText()).toContain('"targetMutationId":"mutation-1"');
    expect(stream).toHaveBeenCalledTimes(2);
    expect(mock.getAgentRun).toHaveBeenCalledTimes(3);
  });

  it("aborts the stale token stream and resumes from lastEventId after connection rotation", async () => {
    let staleSignal: AbortSignal | undefined;
    const first = makeClient({
      agentRunEvents: (_runId, options) => (async function* () {
        staleSignal = options?.signal;
        yield { id: "event-1", type: "content_delta", data: { delta: "Before rotation. " } } as AgentRunEvent;
        await new Promise<void>((_resolve, reject) => options?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true }));
      })(),
    });
    const second = makeClient({
      createAgentRun: first.createAgentRun,
      agentRunEvents: (_runId, options) => {
        expect(options?.lastEventId).toBe("event-1");
        return eventStream([
          { id: "event-2", type: "content_delta", data: { delta: "After rotation." } },
          { id: "event-3", type: "done", data: { status: "completed" } },
        ]);
      },
    });
    setClient(first, 1);
    const view = render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain("Before rotation"));

    setClient(second, 2);
    view.rerender(<Runtime />);
    await waitFor(() => expect(runtimeText()).toContain("After rotation"));
    expect(staleSignal?.aborted).toBe(true);
    expect(second.getAgentRun).toHaveBeenCalledWith("run-1", expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it("marks interrupted truthfully and generates a fresh create idempotency key for the next run", async () => {
    const mock = makeClient({
      createAgentRun: async () => run("queued"),
      getAgentRun: async () => run("interrupted"),
      agentRunEvents: () => eventStream([
        { id: "event-1", type: "error", data: { code: "provider_stopped", retryable: true, status: "interrupted" } },
      ]),
    });
    setClient(mock);
    render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"code":"run_interrupted"'));

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(mock.createAgentRun).toHaveBeenCalledTimes(2));
    const firstRequest = mock.createAgentRun.mock.calls[0]?.[0] as AgentRunCreateRequest;
    const secondRequest = mock.createAgentRun.mock.calls[1]?.[0] as AgentRunCreateRequest;
    expect(firstRequest.idempotencyKey).not.toBe(secondRequest.idempotencyKey);
  });

  it("sends explicit cancel once, continues to the final cancelled event, and disables cancel for terminal runs", async () => {
    let releaseStream!: () => void;
    let released = false;
    const streamReleased = new Promise<void>((resolve) => {
      releaseStream = () => {
        released = true;
        resolve();
      };
    });
    const mock = makeClient({
      getAgentRun: async () => released ? run("cancelled") : run("running"),
      agentRunEvents: () => (async function* () {
        await streamReleased;
        yield { id: "event-1", type: "error", data: { code: "cancelled_by_user", retryable: false, status: "cancelled" } } as AgentRunEvent;
      })(),
    });
    setClient(mock);
    render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(mock.agentRunEvents).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Cancel run" }));
    await waitFor(() => expect(mock.cancelAgentRun).toHaveBeenCalledTimes(1));
    releaseStream();
    await waitFor(() => expect(runtimeText()).toContain('"status":"cancelled"'));
    fireEvent.click(screen.getByRole("button", { name: "Cancel run" }));
    expect(mock.cancelAgentRun).toHaveBeenCalledTimes(1);
  });

  it("recovers a waiting approval through the pending endpoint without exposing proposal arguments", async () => {
    const mock = makeClient({
      getAgentRun: async () => run("waiting_approval"),
      getPendingLevel2Actions: async () => ({ run: run("waiting_approval"), approvals: [pendingApproval] }),
      agentRunEvents: () => eventStream([]),
    });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(mock.getPendingLevel2Actions).toHaveBeenCalledWith("run-1", expect.objectContaining({ signal: expect.any(AbortSignal) })));
    await waitFor(() => expect(runtimeText()).toContain('"pendingApproval":{"approvalId":"approval-1"'));
    expect(runtimeText()).toContain('"status":"waiting_approval"');
    expect(runtimeText()).not.toContain("expectedRevision");
    expect(runtimeText()).not.toContain("taskId");
  });

  it("uses one approval resolution flight, updates the authoritative run, and resumes SSE audit events", async () => {
    let firstStream = true;
    let completed = false;
    const mock = makeClient({
      getAgentRun: async () => run(completed ? "completed" : "waiting_approval"),
      getPendingLevel2Actions: async () => ({ run: run("waiting_approval"), approvals: [pendingApproval] }),
      confirmLevel2Action: async (runId, approvalId) => {
        completed = true;
        return approvalResult(runId, approvalId, "confirmed");
      },
      agentRunEvents: (_runId, options) => {
        if (firstStream) {
          firstStream = false;
          return (async function* () {
            yield { id: "approval-requested", type: "checkpoint", data: { label: "approval_requested", data: pendingApproval } } as AgentRunEvent;
            await new Promise<void>((_resolve, reject) => options?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true }));
          })();
        }
        expect(options?.lastEventId).toBe("approval-requested");
        return eventStream([
          { id: "approval-resolved", type: "checkpoint", data: { label: "approval_resolved", data: { approvalId: "approval-1", status: "approved", executionInvocationId: "invocation-1" } } },
          { id: "mutation-1", type: "state_mutation", data: { callId: "call-1", invocationId: "invocation-1", mutationId: "mutation-1", entityType: "study_task", entityId: "task-1", operation: "update", reversible: true } },
          { id: "done-1", type: "done", data: { status: "completed" } },
        ]);
      },
    });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"pendingApproval":{"approvalId":"approval-1"'));

    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    await waitFor(() => expect(mock.confirmLevel2Action).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(runtimeText()).toContain('"status":"completed"'));
    await waitFor(() => expect(runtimeText()).toContain('"mutationCount":1'));
    expect(mock.rejectLevel2Action).not.toHaveBeenCalled();
    expect(mock.agentRunEvents).toHaveBeenCalledTimes(2);
    expect(runtimeText()).toContain('"lastResult":{"approvalId":"approval-1","resolution":"confirmed","replayed":false}');
  });

  it("keeps one confirmation in flight even if confirm and reject are both pressed", async () => {
    let resolveConfirmation!: (result: AgentLevel2ApprovalResponse) => void;
    const confirmation = new Promise<AgentLevel2ApprovalResponse>((resolve) => { resolveConfirmation = resolve; });
    const mock = makeClient({
      getAgentRun: async () => run("waiting_approval"),
      getPendingLevel2Actions: async () => ({ run: run("waiting_approval"), approvals: [pendingApproval] }),
      confirmLevel2Action: () => confirmation,
      agentRunEvents: () => eventStream([]),
    });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"pendingApproval":{"approvalId":"approval-1"'));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject approval" }));
    await waitFor(() => expect(mock.confirmLevel2Action).toHaveBeenCalledTimes(1));
    expect(mock.rejectLevel2Action).not.toHaveBeenCalled();
    resolveConfirmation(approvalResult("run-1", "approval-1", "confirmed"));
    await waitFor(() => expect(runtimeText()).toContain('"resolution":"confirmed"'));
  });

  it("records an expired confirmation as a failed run rather than executed work", async () => {
    const mock = makeClient({
      getAgentRun: async () => run("waiting_approval"),
      getPendingLevel2Actions: async () => ({ run: run("waiting_approval"), approvals: [pendingApproval] }),
      confirmLevel2Action: async (runId, approvalId) => approvalResult(runId, approvalId, "expired"),
      agentRunEvents: () => eventStream([]),
    });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"pendingApproval":{"approvalId":"approval-1"'));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    await waitFor(() => expect(runtimeText()).toContain('"status":"failed"'));
    expect(runtimeText()).toContain('"resolution":"expired"');
    expect(runtimeText()).toContain('"mutationCount":0');
  });

  it("retries an unknown confirmation result with the same idempotency key", async () => {
    let attempt = 0;
    const mock = makeClient({
      getAgentRun: async () => run("waiting_approval"),
      getPendingLevel2Actions: async () => ({ run: run("waiting_approval"), approvals: [pendingApproval] }),
      confirmLevel2Action: async (runId, approvalId) => {
        attempt += 1;
        if (attempt === 1) throw new TypeError("network connection closed before a result was known");
        return approvalResult(runId, approvalId, "confirmed");
      },
      agentRunEvents: () => eventStream([]),
    });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"pendingApproval":{"approvalId":"approval-1"'));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    await waitFor(() => expect(runtimeText()).toContain("Keen could not confirm this approval request"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    await waitFor(() => expect(mock.confirmLevel2Action).toHaveBeenCalledTimes(2));
    const firstRequest = mock.confirmLevel2Action.mock.calls[0]?.[2] as { idempotencyKey: string };
    const secondRequest = mock.confirmLevel2Action.mock.calls[1]?.[2] as { idempotencyKey: string };
    expect(firstRequest.idempotencyKey).toBe(secondRequest.idempotencyKey);
  });

  it("reports an approval conflict as non-retryable without leaking backend detail", async () => {
    const conflict = new LearningCoreResponseError(409, {
      message: "private database detail /Users/private/keen.db",
      retryable: false,
      recovery: "Refresh the run.",
      documentId: null,
      code: "approval_conflict",
    }, null);
    const mock = makeClient({
      getAgentRun: async () => run("waiting_approval"),
      getPendingLevel2Actions: async () => ({ run: run("waiting_approval"), approvals: [pendingApproval] }),
      confirmLevel2Action: async () => { throw conflict; },
      agentRunEvents: () => eventStream([]),
    });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"pendingApproval":{"approvalId":"approval-1"'));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    await waitFor(() => expect(runtimeText()).toContain("resolved by a different request"));
    expect(runtimeText()).toContain('"retryable":false');
    expect(runtimeText()).toContain("Refresh the Agent activity");
    expect(runtimeText()).not.toContain("reuse the same approval request key");
    expect(runtimeText()).not.toContain("/Users/private/keen.db");
  });

  it("detaches and aborts local work on unmount without sending cancel", async () => {
    let streamSignal: AbortSignal | undefined;
    const mock = makeClient({
      agentRunEvents: (_runId, options) => (async function* () {
        streamSignal = options?.signal;
        await new Promise<void>((_resolve, reject) => options?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true }));
        yield { id: "unreachable", type: "done", data: { status: "completed" } } as AgentRunEvent;
      })(),
    });
    setClient(mock);
    const view = render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(mock.agentRunEvents).toHaveBeenCalledTimes(1));

    view.unmount();
    expect(streamSignal?.aborted).toBe(true);
    expect(mock.cancelAgentRun).not.toHaveBeenCalled();
  });

  it("uses fresh mutation idempotency keys and resumes authoritative first/replayed audit events", async () => {
    let streamAttempt = 0;
    const mock = makeClient({
      getAgentRun: async () => run("completed"),
      agentRunEvents: (_runId, options) => {
        streamAttempt += 1;
        if (streamAttempt === 1) {
          return eventStream([
            {
              id: "event-1", type: "state_mutation", data: {
                callId: "call-1", invocationId: "invocation-1", mutationId: "mutation-1",
                entityType: "study_task", entityId: "task-1", operation: "update", reversible: true,
              },
            },
            { id: "event-2", type: "done", data: { status: "completed" } },
          ]);
        }
        expect(options?.lastEventId).toBe(streamAttempt === 2 ? "event-2" : "event-3");
        expect(options?.terminalAlreadySeen).toBe(true);
        return eventStream([{
          id: streamAttempt === 2 ? "event-3" : "event-4",
          type: "state_mutation",
          data: {
            invocationId: `${streamAttempt === 2 ? "undo" : "redo"}-invocation`,
            mutationId: `${streamAttempt === 2 ? "undo" : "redo"}-mutation`,
            entityType: "study_task",
            entityId: "task-1",
            operation: "update",
            reversible: true,
            action: streamAttempt === 2 ? "undo" : "redo",
            targetMutationId: "mutation-1",
            replayed: streamAttempt === 3,
          },
        }]);
      },
      undoAgentMutation: async (runId, mutationId) => mutationResult("undo", runId, mutationId, false),
      redoAgentMutation: async (runId, mutationId) => mutationResult("redo", runId, mutationId, true),
    });
    setClient(mock);
    render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"mutationCount":1'));

    fireEvent.click(screen.getByRole("button", { name: "Undo mutation" }));
    await waitFor(() => expect(runtimeText()).toContain('"mutationCount":2'));
    expect(runtimeText()).toContain('"replayed":false');

    fireEvent.click(screen.getByRole("button", { name: "Redo mutation" }));
    await waitFor(() => expect(runtimeText()).toContain('"mutationCount":3'));
    expect(runtimeText()).toContain('"replayed":true');
    const undoRequest = mock.undoAgentMutation.mock.calls[0]?.[2] as { idempotencyKey: string };
    const redoRequest = mock.redoAgentMutation.mock.calls[0]?.[2] as { idempotencyKey: string };
    expect(undoRequest.idempotencyKey).not.toBe(redoRequest.idempotencyKey);
  });

  it("keeps a mutation locked until its authoritative event arrives", async () => {
    let releaseAudit!: () => void;
    const auditReady = new Promise<void>((resolve) => { releaseAudit = resolve; });
    let streamAttempt = 0;
    const mock = makeClient({
      getAgentRun: async () => run("completed"),
      agentRunEvents: (_runId, options) => {
        streamAttempt += 1;
        if (streamAttempt === 1) {
          return eventStream([
            {
              id: "event-1", type: "state_mutation", data: {
                callId: "call-1", invocationId: "invocation-1", mutationId: "mutation-1",
                entityType: "study_task", entityId: "task-1", operation: "update", reversible: true,
              },
            },
            { id: "event-2", type: "done", data: { status: "completed" } },
          ]);
        }
        expect(options?.lastEventId).toBe("event-2");
        return (async function* () {
          await auditReady;
          yield {
            id: "event-3",
            type: "state_mutation",
            data: {
              invocationId: "undo-invocation",
              mutationId: "undo-mutation",
              entityType: "study_task",
              entityId: "task-1",
              operation: "update",
              reversible: true,
              action: "undo",
              targetMutationId: "mutation-1",
              replayed: false,
            },
          } as AgentRunEvent;
        })();
      },
    });
    setClient(mock);
    render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"mutationCount":1'));

    fireEvent.click(screen.getByRole("button", { name: "Undo mutation" }));
    await waitFor(() => expect(mock.undoAgentMutation).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(runtimeText()).toContain('"pending":{"action":"undo","mutationId":"mutation-1"}'));

    fireEvent.click(screen.getByRole("button", { name: "Undo mutation" }));
    expect(mock.undoAgentMutation).toHaveBeenCalledTimes(1);

    releaseAudit();
    await waitFor(() => expect(runtimeText()).toContain('"mutationCount":2'));
    expect(runtimeText()).toContain('"pending":null');
  });

  it("keeps a failed mutation mapped to its requested target", async () => {
    const conflict = new LearningCoreResponseError(409, {
      message: "private database detail",
      retryable: false,
      recovery: null,
      documentId: null,
      code: "undo_conflict",
    }, null);
    const mock = makeClient({
      getAgentRun: async () => run("completed"),
      agentRunEvents: () => eventStream([
        { id: "event-1", type: "done", data: { status: "completed" } },
      ]),
      undoAgentMutation: async () => { throw conflict; },
    });
    setClient(mock);
    render(<Runtime />);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"status":"completed"'));

    fireEvent.click(screen.getByRole("button", { name: "Undo mutation" }));
    await waitFor(() => expect(runtimeText()).toContain('"target":{"action":"undo","mutationId":"mutation-1"}'));
    expect(runtimeText()).toContain("requested Undo action");
    expect(runtimeText()).toContain('"pending":null');
  });

  it("restores empty snapshots to honest idle state", async () => {
    const mock = makeClient({
      getLatestAgentRunActivity: async () => ({ run: null, events: [] }),
      getAgentRun: async () => run("completed"),
      agentRunEvents: vi.fn(() => eventStream([])),
    });
    setClient(mock);
    render(<RestoreRuntime />);

    fireEvent.click(screen.getByRole("button", { name: "Restore empty context" }));
    await waitFor(() => expect(mock.getLatestAgentRunActivity).toHaveBeenCalledWith(
      { conversationId: "convo-empty" },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(screen.getByTestId("restore-run-id")).toHaveTextContent("null"));
    await waitFor(() => expect(screen.getByTestId("restore-phase")).toHaveTextContent("idle"));
    expect(restoreRuntimeText().status).toBe("idle");
    expect(restoreRuntimeText().content).toBe("");
    expect(mock.agentRunEvents).not.toHaveBeenCalled();
    expect(mock.getAgentRun).not.toHaveBeenCalled();
  });

  it("replays terminal restore events in sequence order and does not resume streaming", async () => {
    const terminalEventSequence: AgentRunActivityEvent[] = [
      {
        id: "event-2",
        sequence: 1,
        type: "content_delta",
        data: { delta: "B" },
        createdAt: now,
      },
      {
        id: "event-1",
        sequence: 0,
        type: "content_delta",
        data: { delta: "A" },
        createdAt: now,
      },
    ];
    const mock = makeClient({
      getLatestAgentRunActivity: async (context: AgentRunActivityContext) => {
        if ("conversationId" in context && context.conversationId === "convo-terminal") {
          return { run: run("completed", "terminal-run"), events: terminalEventSequence };
        }
        return { run: null, events: [] };
      },
      getAgentRun: vi.fn(async () => run("completed", "terminal-run")),
      agentRunEvents: vi.fn(() => eventStream([])),
    });
    setClient(mock);
    render(<RestoreRuntime />);

    fireEvent.click(screen.getByRole("button", { name: "Restore terminal context" }));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("terminal-run"));
    await waitFor(() => expect(restoreRuntimeText().content).toBe("AB"));
    expect(restoreRuntimeText().phase).toBe("idle");
    expect(screen.getByTestId("restore-context").textContent).toBe("{\"conversationId\":\"convo-terminal\"}");
    expect(mock.agentRunEvents).not.toHaveBeenCalled();
    expect(mock.getAgentRun).not.toHaveBeenCalled();
  });

  it("retries one empty projection and restores the completed out-of-band run", async () => {
    let snapshotAttempt = 0;
    const mock = makeClient({
      getLatestAgentRunActivity: async (context) => {
        if (!("conversationId" in context) || context.conversationId !== "convo-terminal") {
          return { run: null, events: [] };
        }
        snapshotAttempt += 1;
        if (snapshotAttempt === 1) return { run: run("failed", "old-run"), events: [] };
        if (snapshotAttempt === 2) return { run: null, events: [] };
        return {
          run: run("completed", "new-run"),
          events: [{
            id: "new-content",
            sequence: 0,
            type: "content_delta",
            data: { delta: "Verified intervention artifact" },
            createdAt: now,
          }],
        };
      },
    });
    setClient(mock);
    render(<RestoreRuntime />);

    fireEvent.click(screen.getByRole("button", { name: "Restore terminal context" }));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("old-run"));

    fireEvent.click(screen.getByRole("button", { name: "Refresh known activity context" }));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("new-run"));
    await waitFor(() => expect(restoreRuntimeText().status).toBe("completed"));
    await waitFor(() => expect(restoreRuntimeText().content).toBe("Verified intervention artifact"));
    expect(restoreRuntimeText().issue).toBe("null");
    expect(mock.getLatestAgentRunActivity).toHaveBeenCalledTimes(3);
  });

  it("rejects an older non-empty projection before restoring the confirmed out-of-band run", async () => {
    let snapshotAttempt = 0;
    const mock = makeClient({
      getLatestAgentRunActivity: async (context) => {
        if (!("conversationId" in context) || context.conversationId !== "convo-terminal") {
          return { run: null, events: [] };
        }
        snapshotAttempt += 1;
        if (snapshotAttempt <= 2) {
          return {
            run: run("failed", "old-run"),
            events: [{
              id: `old-content-${snapshotAttempt}`,
              sequence: 0,
              type: "content_delta",
              data: { delta: "Stale provider error" },
              createdAt: now,
            }],
          };
        }
        return {
          run: run("completed", "new-run"),
          events: [{
            id: "new-content",
            sequence: 0,
            type: "content_delta",
            data: { delta: "Current intervention artifact" },
            createdAt: now,
          }],
        };
      },
    });
    setClient(mock);
    const view = render(<RestoreRuntime />);

    fireEvent.click(screen.getByRole("button", { name: "Restore terminal context" }));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("old-run"));

    fireEvent.click(screen.getByRole("button", { name: "Refresh known activity context" }));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("new-run"));
    expect(restoreRuntimeText().content).toBe("Current intervention artifact");
    expect(restoreRuntimeText().content).not.toContain("Stale provider error");
    expect(mock.getLatestAgentRunActivity).toHaveBeenCalledTimes(3);

    view.unmount();
    const persistentlyStale = makeClient({
      getLatestAgentRunActivity: async () => ({
        run: run("failed", "old-run"),
        events: [{
          id: "still-old",
          sequence: 0,
          type: "content_delta",
          data: { delta: "Still stale" },
          createdAt: now,
        }],
      }),
    });
    setClient(persistentlyStale);
    render(<RestoreRuntime />);

    fireEvent.click(screen.getByRole("button", { name: "Restore terminal context" }));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("old-run"));
    fireEvent.click(screen.getByRole("button", { name: "Refresh known activity context" }));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("null"));
    await waitFor(() => expect(restoreRuntimeText().issue).toBe("activity_unavailable"));
    expect(restoreRuntimeText().content).toBe("");
    expect(persistentlyStale.getLatestAgentRunActivity).toHaveBeenCalledTimes(3);
  });

  it("keeps stale non-terminal restore responses from replacing the active context and resumes from snapshot cursor", async () => {
    let resolveStale: (value: { run: AgentRun; events: readonly AgentRunActivityEvent[] }) => void = () => {};
    const staleSnapshot = new Promise<{ run: AgentRun; events: readonly AgentRunActivityEvent[] }>((resolve) => {
      resolveStale = resolve;
    });
    const events = (runId: string, options?: AgentRunEventStreamOptions) => {
      if (runId === "run-fresh") {
        expect(options?.lastEventId).toBe("fresh-1");
        return eventStream([{ id: "event-done", type: "done", data: { status: "completed" } }]);
      }
      return eventStream([]);
    };
    const mock = makeClient({
      getLatestAgentRunActivity: vi.fn(async (context) => {
        if ("conversationId" in context && context.conversationId === "convo-stale") {
          return staleSnapshot;
        }
        if ("conversationId" in context && context.conversationId === "convo-fresh") {
          return {
            run: run("running", "run-fresh"),
            events: [{ id: "fresh-1", sequence: 0, type: "content_delta" as const, data: { delta: "Fresh" }, createdAt: now }],
          };
        }
        return { run: null, events: [] };
      }),
      getAgentRun: vi.fn(async (runId) => run(runId === "run-fresh" ? "completed" : "running", runId)),
      agentRunEvents: vi.fn(events),
    });
    setClient(mock);
    render(<RestoreRuntime />);

    fireEvent.click(screen.getByRole("button", { name: "Restore stale context" }));
    await waitFor(() => expect(mock.getLatestAgentRunActivity).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Restore fresh context" }));
    await waitFor(() => expect(mock.getLatestAgentRunActivity).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(restoreRuntimeText().runId).toBe("run-fresh"));
    await waitFor(() => expect(restoreRuntimeText().content).toBe("Fresh"));
    expect(screen.getByTestId("restore-context").textContent).toBe("{\"conversationId\":\"convo-fresh\"}");
    expect(mock.agentRunEvents).toHaveBeenCalledWith("run-fresh", expect.objectContaining({ lastEventId: "fresh-1" }));

    await act(async () => {
      resolveStale({
        run: run("running", "run-stale"),
        events: [{ id: "stale-1", sequence: 0, type: "content_delta", data: { delta: "Stale" }, createdAt: now }],
      });
      await Promise.resolve();
    });
    await waitFor(() => expect(mock.agentRunEvents).not.toHaveBeenCalledWith("run-stale", expect.anything()));
    expect(restoreRuntimeText().content).not.toContain("Stale");
    expect(restoreRuntimeText().runId).toBe("run-fresh");
  });

  it("keeps mutation errors safe and refuses actions until the run is terminal", async () => {
    const conflict = new LearningCoreResponseError(409, {
      message: "private database detail /Users/private/keen.db",
      retryable: false,
      recovery: null,
      documentId: null,
      code: "undo_conflict",
    }, null);
    const mock = makeClient({ undoAgentMutation: async () => { throw conflict; } });
    setClient(mock);
    render(<Runtime />);

    fireEvent.click(screen.getByRole("button", { name: "Undo mutation" }));
    await waitFor(() => expect(runtimeText()).toContain('"mutationAction"'));
    expect(mock.undoAgentMutation).not.toHaveBeenCalled();
    expect(runtimeText()).not.toContain("/Users/private/keen.db");

    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(runtimeText()).toContain('"status":"completed"'));
    fireEvent.click(screen.getByRole("button", { name: "Undo mutation" }));
    await waitFor(() => expect(mock.undoAgentMutation).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(runtimeText()).toContain("Keen could not confirm"));
    expect(runtimeText()).not.toContain("/Users/private/keen.db");
  });
});
