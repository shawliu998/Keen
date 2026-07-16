import type { AgentRunEvent, AgentRunStatus } from "@keen/api-client";
import type {
  AgentActivityAction,
  AgentActivityState,
  AgentActivityStatus,
  AgentMutationActivity,
  AgentToolActivity,
} from "./agentActivityTypes";

const MAX_CONTENT_CHARACTERS = 2 * 1024 * 1024;
const MAX_TRACKED_EVENT_IDS = 4_096;
const MAX_ACTIVITY_ITEMS = 500;
const terminalStatuses = new Set<AgentRunStatus>(["completed", "failed", "cancelled", "interrupted"]);

export const initialAgentActivityState: AgentActivityState = {
  status: "idle",
  durableStatus: null,
  terminal: false,
  partial: false,
  content: "",
  contentTruncated: false,
  lastEventId: null,
  receivedEventIds: [],
  tools: [],
  mutations: [],
  warnings: [],
  error: null,
};

function isTerminal(status: AgentRunStatus): boolean {
  return terminalStatuses.has(status);
}

function boundedAppend<T>(items: readonly T[], item: T, limit = MAX_ACTIVITY_ITEMS): readonly T[] {
  const next = [...items, item];
  return next.length <= limit ? next : next.slice(next.length - limit);
}

function appendContent(state: AgentActivityState, delta: string): Pick<AgentActivityState, "content" | "contentTruncated"> {
  const available = MAX_CONTENT_CHARACTERS - state.content.length;
  if (available <= 0) return { content: state.content, contentTruncated: true };
  const accepted = delta.slice(0, available);
  return {
    content: state.content + accepted,
    contentTruncated: state.contentTruncated || accepted.length < delta.length,
  };
}

function updateToolStart(
  tools: readonly AgentToolActivity[],
  event: Extract<AgentRunEvent, { type: "tool_start" }>,
): readonly AgentToolActivity[] {
  if (tools.some((tool) => tool.invocationId === event.data.invocationId)) return tools;
  return boundedAppend(tools, {
    invocationId: event.data.invocationId,
    toolName: event.data.toolName,
    status: "running",
    replayed: event.data.replayCandidate,
  });
}

function updateToolResult(
  tools: readonly AgentToolActivity[],
  event: Extract<AgentRunEvent, { type: "tool_result" }>,
): readonly AgentToolActivity[] {
  const index = tools.findIndex((tool) => tool.invocationId === event.data.invocationId);
  if (index === -1) {
    return boundedAppend(tools, {
      invocationId: event.data.invocationId,
      toolName: event.data.toolName,
      status: "completed",
      replayed: event.data.replayed,
    });
  }
  return tools.map((tool, toolIndex) => toolIndex === index ? {
    ...tool,
    status: "completed" as const,
    replayed: event.data.replayed,
  } : tool);
}

function mutationFromEvent(event: Extract<AgentRunEvent, { type: "state_mutation" }>): AgentMutationActivity {
  if (!("entityType" in event.data)) {
    return {
      mutationId: event.data.mutationId,
      invocationId: event.data.invocationId,
      replayed: true,
      entityType: null,
      entityId: null,
      operation: null,
      action: null,
      targetMutationId: null,
    };
  }
  return {
    mutationId: event.data.mutationId,
    invocationId: event.data.invocationId,
    replayed: "replayed" in event.data ? event.data.replayed : false,
    entityType: event.data.entityType,
    entityId: event.data.entityId,
    operation: event.data.operation,
    action: "action" in event.data ? event.data.action : null,
    targetMutationId: "targetMutationId" in event.data ? event.data.targetMutationId : null,
  };
}

function statusFromEvent(event: AgentRunEvent): AgentRunStatus | null {
  if (event.type === "status") return event.data.status;
  if (event.type === "done") return "completed";
  if (event.type === "error") return event.data.status;
  return null;
}

export function agentActivityReducer(state: AgentActivityState, action: AgentActivityAction): AgentActivityState {
  if (action.type === "reset") return initialAgentActivityState;
  if (action.type === "run_status") {
    return {
      ...state,
      status: action.status,
      durableStatus: action.status,
      terminal: isTerminal(action.status),
      partial: false,
    };
  }
  if (action.type === "stream_disconnected") {
    if (state.terminal) return state;
    return { ...state, status: "partial", partial: true };
  }

  const event = action.event;
  if (state.receivedEventIds.includes(event.id)) return state;

  const durableStatus = statusFromEvent(event) ?? state.durableStatus;
  const terminal = durableStatus !== null && isTerminal(durableStatus);
  const status: AgentActivityStatus = durableStatus ?? (state.status === "idle" ? "running" : state.status);
  const next: AgentActivityState = {
    ...state,
    status,
    durableStatus,
    terminal,
    partial: false,
    lastEventId: event.id,
    receivedEventIds: boundedAppend(state.receivedEventIds, event.id, MAX_TRACKED_EVENT_IDS),
  };

  switch (event.type) {
    case "content_delta":
      return { ...next, ...appendContent(state, event.data.delta) };
    case "tool_start":
      return { ...next, tools: updateToolStart(state.tools, event) };
    case "tool_result":
      // Deliberately retain only lifecycle metadata. Tool results and provider reasoning
      // are not part of the user-visible activity model.
      return { ...next, tools: updateToolResult(state.tools, event) };
    case "state_mutation": {
      const mutation = mutationFromEvent(event);
      if (state.mutations.some((item) => item.mutationId === mutation.mutationId)) return next;
      return { ...next, mutations: boundedAppend(state.mutations, mutation) };
    }
    case "warning":
      return {
        ...next,
        warnings: boundedAppend(state.warnings, {
          eventId: event.id,
          code: event.data.code,
          message: event.data.message,
        }),
      };
    case "error":
      return {
        ...next,
        error: {
          code: event.data.code,
          message: event.data.message ?? null,
          retryable: event.data.retryable,
        },
      };
    case "metadata":
    case "status":
    case "checkpoint":
    case "done":
      return next;
  }
}
