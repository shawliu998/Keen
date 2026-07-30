import type { AgentLevel2PendingApproval, AgentRunEvent, AgentRunStatus } from "@keen/api-client";

export type AgentActivityStatus = AgentRunStatus | "idle" | "partial";

export type AgentToolActivity = {
  invocationId: string;
  toolName: string;
  status: "running" | "completed" | "failed" | "cancelled" | "stopped";
  replayed: boolean;
};

export type AgentMutationActivity = {
  mutationId: string;
  invocationId: string;
  replayed: boolean;
  entityType: string | null;
  entityId: string | null;
  operation: "create" | "update" | "delete" | null;
  action: "undo" | "redo" | null;
  targetMutationId: string | null;
};

export type AgentWarningActivity = {
  eventId: string;
  code: string;
  message: string;
};

/**
 * Deliberately small learner-facing projection of a completed intervention.
 * The durable artifact contains source handles, quoted content, hashes, and
 * provider-oriented details that do not belong in the global Activity drawer.
 */
export type AgentLearningRecord = {
  summary: string;
  sources: readonly {
    documentName: string;
    pageNumber: number;
    sectionPath: readonly string[];
  }[];
  whatNext: string;
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
  learningRecord: AgentLearningRecord | null;
  pendingApproval?: AgentLevel2PendingApproval | null;
  error: { code: string; message: string | null; retryable: boolean } | null;
};

export type AgentActivityAction =
  | { type: "reset" }
  | { type: "run_status"; status: AgentRunStatus }
  | { type: "pending_approval"; approval: AgentLevel2PendingApproval | null }
  | { type: "event"; event: AgentRunEvent }
  | { type: "stream_disconnected" };
