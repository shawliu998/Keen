import type { AgentRunEvent, AgentRunStatus } from "@keen/api-client";

export type AgentActivityStatus = AgentRunStatus | "idle" | "partial";

export type AgentToolActivity = {
  invocationId: string;
  toolName: string;
  status: "running" | "completed";
  replayed: boolean;
};

export type AgentMutationActivity = {
  mutationId: string;
  invocationId: string;
  replayed: boolean;
  entityType: string | null;
  entityId: string | null;
  operation: "create" | "update" | "delete" | null;
};

export type AgentWarningActivity = {
  eventId: string;
  code: string;
  message: string;
};

export type AgentActivityState = {
  status: AgentActivityStatus;
  durableStatus: AgentRunStatus | null;
  terminal: boolean;
  partial: boolean;
  content: string;
  contentTruncated: boolean;
  lastEventId: string | null;
  receivedEventIds: readonly string[];
  tools: readonly AgentToolActivity[];
  mutations: readonly AgentMutationActivity[];
  warnings: readonly AgentWarningActivity[];
  error: { code: string; message: string | null; retryable: boolean } | null;
};

export type AgentActivityAction =
  | { type: "reset" }
  | { type: "run_status"; status: AgentRunStatus }
  | { type: "event"; event: AgentRunEvent }
  | { type: "stream_disconnected" };
