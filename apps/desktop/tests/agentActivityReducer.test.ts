import type { AgentRunEvent, AgentRunStatus } from "@keen/api-client";
import { agentActivityReducer, initialAgentActivityState } from "../src/features/agent/agentActivityReducer";

function reduce(events: readonly AgentRunEvent[]) {
  return events.reduce(
    (state, event) => agentActivityReducer(state, { type: "event", event }),
    initialAgentActivityState,
  );
}

describe("Agent activity reducer", () => {
  it("deduplicates event IDs and retains content as partial across a disconnect", () => {
    const delta: AgentRunEvent = { id: "event-1", type: "content_delta", data: { delta: "Visible answer" } };
    const delivered = reduce([delta, delta]);

    expect(delivered.content).toBe("Visible answer");
    expect(delivered.receivedEventIds).toEqual(["event-1"]);
    expect(delivered.lastEventId).toBe("event-1");

    const partial = agentActivityReducer(delivered, { type: "stream_disconnected" });
    expect(partial).toMatchObject({ status: "partial", partial: true, terminal: false, content: "Visible answer" });

    const resumed = agentActivityReducer(partial, {
      type: "event",
      event: { id: "event-2", type: "status", data: { status: "running" } },
    });
    expect(resumed).toMatchObject({ status: "running", partial: false, durableStatus: "running" });
  });

  it.each<[AgentRunStatus, boolean]>([
    ["waiting_approval", false],
    ["interrupted", true],
    ["cancelled", true],
  ])("maps %s status without inventing completion", (status, terminal) => {
    const state = agentActivityReducer(initialAgentActivityState, {
      type: "event",
      event: { id: `status-${status}`, type: "status", data: { status } },
    });
    expect(state).toMatchObject({ status, durableStatus: status, terminal, partial: false });
  });

  it("marks done and error events terminal with their durable outcomes", () => {
    const completed = reduce([{ id: "done-1", type: "done", data: { status: "completed" } }]);
    expect(completed).toMatchObject({ status: "completed", durableStatus: "completed", terminal: true, error: null });

    const interrupted = reduce([{
      id: "error-1",
      type: "error",
      data: { code: "process_restarted", retryable: true, status: "interrupted", message: "Restarted safely." },
    }]);
    expect(interrupted).toMatchObject({
      status: "interrupted",
      terminal: true,
      error: { code: "process_restarted", retryable: true, message: "Restarted safely." },
    });
  });

  it("tracks tool lifecycle but never retains tool results or hidden reasoning", () => {
    const resultWithPrivatePayload = {
      id: "tool-result-1",
      type: "tool_result",
      data: {
        callId: "call-1",
        invocationId: "invocation-1",
        toolName: "search_notes",
        result: { hidden_reasoning: "must never appear", answer: "raw tool payload" },
        truncated: false,
        replayed: false,
      },
    } as AgentRunEvent;
    const state = reduce([
      {
        id: "tool-start-1",
        type: "tool_start",
        data: { invocationId: "invocation-1", toolName: "search_notes", replayCandidate: false },
      },
      resultWithPrivatePayload,
    ]);

    expect(state.tools).toEqual([{
      invocationId: "invocation-1",
      toolName: "search_notes",
      status: "completed",
      replayed: false,
    }]);
    expect(JSON.stringify(state)).not.toContain("must never appear");
    expect(JSON.stringify(state)).not.toContain("raw tool payload");
  });

  it("marks a durable redacted failed tool result as failed", () => {
    const state = reduce([
      {
        id: "tool-start-failed",
        type: "tool_start",
        data: { invocationId: "invocation-failed", toolName: "search_notes", replayCandidate: false },
      },
      {
        id: "tool-result-failed",
        type: "tool_result",
        data: {
          callId: "call-failed",
          invocationId: "invocation-failed",
          toolName: "search_notes",
          failed: true,
          code: "temporary_read_failure",
          retryable: true,
          replayed: false,
        },
      },
    ]);

    expect(state.tools).toEqual([{
      invocationId: "invocation-failed",
      toolName: "search_notes",
      status: "failed",
      replayed: false,
    }]);
  });

  it.each([
    ["cancelled", "cancelled"],
    ["failed", "stopped"],
    ["interrupted", "stopped"],
    ["completed", "stopped"],
  ] as const)("settles an unfinished tool when the run becomes %s", (runStatus, toolStatus) => {
    const running = reduce([{
      id: "tool-start-terminal",
      type: "tool_start",
      data: { invocationId: "invocation-terminal", toolName: "search_notes", replayCandidate: false },
    }]);
    const terminal = agentActivityReducer(running, {
      type: "run_status",
      status: runStatus,
    });

    expect(terminal.tools[0]?.status).toBe(toolStatus);
  });

  it("settles an unfinished tool from a terminal SSE event", () => {
    const state = reduce([
      {
        id: "tool-start-error",
        type: "tool_start",
        data: { invocationId: "invocation-error", toolName: "search_notes", replayCandidate: false },
      },
      {
        id: "run-error",
        type: "error",
        data: { code: "tool_contract_error", retryable: false, status: "failed" },
      },
    ]);

    expect(state.tools[0]?.status).toBe("stopped");
  });

  it("records mutation receipts and user-visible warnings without raw call payloads", () => {
    const state = reduce([
      {
        id: "mutation-1",
        type: "state_mutation",
        data: {
          callId: "call-2",
          invocationId: "invocation-2",
          mutationId: "mutation-local-1",
          entityType: "study_task",
          entityId: "task-1",
          operation: "update",
          reversible: true,
        },
      },
      {
        id: "warning-1",
        type: "warning",
        data: { code: "retrieval_partial", message: "One local source was unavailable." },
      },
    ]);

    expect(state.mutations).toEqual([{
      mutationId: "mutation-local-1",
      invocationId: "invocation-2",
      replayed: false,
      entityType: "study_task",
      entityId: "task-1",
      operation: "update",
      action: null,
      targetMutationId: null,
    }]);
    expect(state.warnings).toEqual([{
      eventId: "warning-1",
      code: "retrieval_partial",
      message: "One local source was unavailable.",
    }]);
  });

  it("retains bounded Undo audit metadata without exposing the raw tool result", () => {
    const state = reduce([{
      id: "mutation-undo-1",
      type: "state_mutation",
      data: {
        invocationId: "invocation-undo-1",
        mutationId: "mutation-inverse-1",
        entityType: "study_task",
        entityId: "task-1",
        operation: "update",
        reversible: true,
        action: "undo",
        targetMutationId: "mutation-original-1",
        replayed: true,
      },
    }]);

    expect(state.mutations).toEqual([{
      mutationId: "mutation-inverse-1",
      invocationId: "invocation-undo-1",
      replayed: true,
      entityType: "study_task",
      entityId: "task-1",
      operation: "update",
      action: "undo",
      targetMutationId: "mutation-original-1",
    }]);
  });
});
