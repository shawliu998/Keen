import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  AgentEventStreamDisconnectedError,
  LearningCoreResponseError,
  type AgentCancelResponse,
  type AgentMutationActionResponse,
  type AgentRun,
  type AgentRunCreateRequest,
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
};

function makeClient(overrides: Partial<{
  createAgentRun: (request: AgentRunCreateRequest, options?: RequestOptions) => Promise<AgentRun>;
  getAgentRun: (runId: string, options?: RequestOptions) => Promise<AgentRun>;
  cancelAgentRun: (runId: string, options?: RequestOptions) => Promise<AgentCancelResponse>;
  agentRunEvents: (runId: string, options?: AgentRunEventStreamOptions) => AsyncGenerator<AgentRunEvent>;
  undoAgentMutation: LearningCoreClient["undoAgentMutation"];
  redoAgentMutation: LearningCoreClient["redoAgentMutation"];
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
  const client = {
    createAgentRun,
    getAgentRun,
    cancelAgentRun,
    agentRunEvents,
    undoAgentMutation,
    redoAgentMutation,
  } as unknown as LearningCoreClient;
  return { client, createAgentRun, getAgentRun, cancelAgentRun, agentRunEvents, undoAgentMutation, redoAgentMutation };
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

function Harness() {
  const runtime = useAgentRuntime();
  return <>
    <button onClick={() => void runtime.startRun(startRequest)}>Start run</button>
    <button onClick={() => void runtime.cancelRun()}>Cancel run</button>
    <button onClick={() => void runtime.undoMutation("mutation-1")}>Undo mutation</button>
    <button onClick={() => void runtime.redoMutation("mutation-1")}>Redo mutation</button>
    <output data-testid="runtime">{JSON.stringify({
      phase: runtime.phase,
      status: runtime.activity.status,
      content: runtime.activity.content,
      mutationCount: runtime.activity.mutations.length,
      mutations: runtime.activity.mutations,
      issue: runtime.issue,
      mutationAction: runtime.mutationAction,
    })}</output>
  </>;
}

function Runtime({ strict = false }: { strict?: boolean }) {
  const content = <AgentRuntimeProvider><Harness /></AgentRuntimeProvider>;
  return strict ? <StrictMode>{content}</StrictMode> : content;
}

function setClient(mock: MockClient, generation = 1): void {
  learningCore.current = { status: "healthy", client: mock.client, connectionGeneration: generation };
}

function runtimeText(): string {
  return screen.getByTestId("runtime").textContent ?? "";
}

beforeEach(() => {
  learningCore.current = { status: "healthy", client: null, connectionGeneration: 1 };
});

describe("AgentRuntimeProvider", () => {
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
