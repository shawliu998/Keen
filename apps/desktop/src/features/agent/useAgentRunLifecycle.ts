import {
  LearningCoreResponseError,
  type AgentMutationActionResponse,
  type AgentLevel2ApprovalResponse,
  type AgentRun,
  type AgentRunCreateRequest,
  type AgentRunEvent,
} from "@keen/api-client";
import type { LearningCoreStatus } from "../../services/LearningCoreProvider";
import type { AgentActivityState } from "./agentActivityTypes";

export type AgentRunStartRequest = Omit<AgentRunCreateRequest, "idempotencyKey">;
export type AgentRuntimePhase = "idle" | "creating" | "recovering" | "streaming" | "cancelling";
export type AgentRuntimeIssueCode =
  | "provider_missing"
  | "provider_unavailable"
  | "agent_busy"
  | "learning_core_unavailable"
  | "run_interrupted"
  | "run_failed";

export type AgentRuntimeIssue = {
  code: AgentRuntimeIssueCode;
  message: string;
  retryable: boolean;
  recovery: string;
  automaticRecovery: boolean;
};

export type AgentMutationActionState = {
  pending: { action: "undo" | "redo"; mutationId: string } | null;
  error: AgentRuntimeIssue | null;
  lastResult: Pick<AgentMutationActionResponse, "action" | "targetMutationId" | "replayed"> | null;
};

export type AgentApprovalActionState = {
  pending: { approvalId: string; action: "confirm" | "reject" } | null;
  error: AgentRuntimeIssue | null;
  lastResult: Pick<AgentLevel2ApprovalResponse, "approvalId" | "resolution" | "replayed"> | null;
};

export type AgentRuntimeContextValue = {
  activity: AgentActivityState;
  run: AgentRun | null;
  phase: AgentRuntimePhase;
  issue: AgentRuntimeIssue | null;
  mutationAction: AgentMutationActionState;
  approvalAction?: AgentApprovalActionState;
  learningCoreStatus: LearningCoreStatus;
  startRun: (request: AgentRunStartRequest) => Promise<AgentRun | null>;
  cancelRun: () => Promise<boolean>;
  undoMutation: (mutationId: string) => Promise<boolean>;
  redoMutation: (mutationId: string) => Promise<boolean>;
  confirmApproval?: (approvalId: string) => Promise<boolean>;
  rejectApproval?: (approvalId: string) => Promise<boolean>;
};

export const AGENT_STREAM_RETRY_DELAY_MS = 350;
let fallbackIdempotencyCounter = 0;

export function createAgentIdempotencyKey(): string {
  try {
    const uuid = globalThis.crypto?.randomUUID?.();
    if (uuid) return `agent-${uuid}`;
  } catch {
    // Some embedded/test WebViews expose randomUUID but reject calls. The key is
    // process-local idempotency, not a credential, so the monotonic fallback is safe.
  }
  fallbackIdempotencyCounter += 1;
  return `agent-${Date.now().toString(36)}-${fallbackIdempotencyCounter.toString(36)}`;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export function delayWithAbort(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("The operation was aborted.", "AbortError"));
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("The operation was aborted.", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export function issueForResponse(error: LearningCoreResponseError): AgentRuntimeIssue {
  if (error.detail?.code === "provider_missing") {
    return {
      code: "provider_missing",
      message: "No Agent model provider is configured, so this run was not created and no learning data changed.",
      retryable: false,
      recovery: "Configure a supported provider, then start a new run.",
      automaticRecovery: false,
    };
  }
  if (error.detail?.code === "agent_busy") {
    return {
      code: "agent_busy",
      message: "The local Agent is already handling another run, so this request was not started.",
      retryable: true,
      recovery: "Wait for the active run to finish, then start a new run.",
      automaticRecovery: false,
    };
  }
  return {
    code: "provider_unavailable",
    message: "The Agent provider could not continue this run. Any events already shown remain available locally.",
    retryable: error.detail?.retryable ?? true,
    recovery: "Check the provider connection and credentials, then start a new run if recovery does not resume.",
    automaticRecovery: false,
  };
}

export function issueForTerminalEvent(event: Extract<AgentRunEvent, { type: "error" }>): AgentRuntimeIssue | null {
  if (event.data.status === "cancelled") return null;
  if (event.data.status === "interrupted") {
    return {
      code: "run_interrupted",
      message: "The Agent run was interrupted. Completed local mutations remain recorded and can be reviewed.",
      retryable: false,
      recovery: "Start a new run; Keen will generate a new idempotency key rather than reusing the interrupted request.",
      automaticRecovery: false,
    };
  }
  return {
    code: "run_failed",
    message: "The Agent run failed. Content and completed local mutations received before the failure remain visible.",
    retryable: event.data.retryable,
    recovery: event.data.retryable ? "Start a new run after checking the provider." : "Review the run error before starting a new run.",
    automaticRecovery: false,
  };
}

export function issueForTerminalRun(run: AgentRun): AgentRuntimeIssue | null {
  if (run.status === "interrupted") {
    return {
      code: "run_interrupted",
      message: "The Agent run was interrupted. Completed local mutations remain recorded and can be reviewed.",
      retryable: false,
      recovery: "Start a new run; Keen will use a new idempotency key.",
      automaticRecovery: false,
    };
  }
  if (run.status === "failed") {
    return {
      code: "run_failed",
      message: "The Agent run failed. Content and completed local mutations received before the failure remain visible.",
      retryable: false,
      recovery: "Review the final run event before starting a new run.",
      automaticRecovery: false,
    };
  }
  return null;
}

export function unavailableIssue(): AgentRuntimeIssue {
  return {
    code: "learning_core_unavailable",
    message: "The local learning core is unavailable. The current Agent view is partial; no server-side cancel was sent.",
    retryable: true,
    recovery: "Keen will try to resume this run after the authenticated local service is healthy again.",
    automaticRecovery: true,
  };
}

export function mutationIssue(error?: LearningCoreResponseError): AgentRuntimeIssue {
  const code = error?.detail?.code;
  if (code === "mutation_not_found") {
    return {
      code: "run_failed",
      message: "The selected mutation is no longer available, so no Undo or Redo change was made.",
      retryable: false,
      recovery: "Refresh the run activity and choose an available mutation.",
      automaticRecovery: false,
    };
  }
  if (code === "mutation_action_forbidden" || code === "run_not_terminal") {
    return {
      code: "agent_busy",
      message: "This mutation cannot be changed in the run's current state, so local learning data was left unchanged.",
      retryable: code === "run_not_terminal",
      recovery: "Wait for the run to reach a terminal state and review the mutation again.",
      automaticRecovery: false,
    };
  }
  return {
    code: "run_failed",
    message: "Keen could not confirm the requested mutation action, so no Undo or Redo result is shown.",
    retryable: error?.detail?.retryable ?? false,
    recovery: "Review the current run state before trying the action again.",
    automaticRecovery: false,
  };
}

export function approvalIssue(
  error?: LearningCoreResponseError,
  action: "confirm" | "reject" = "confirm",
): AgentRuntimeIssue {
  if (error?.detail?.code === "approval_conflict") {
    return {
      code: "run_failed",
      message: "This approval was resolved by a different request, so Keen did not submit another local change.",
      retryable: false,
      recovery: "Refresh the Agent activity to load the recorded approval result before taking another action.",
      automaticRecovery: false,
    };
  }
  return {
    code: error?.detail?.code === "agent_busy" ? "agent_busy" : "run_failed",
    message: action === "confirm"
      ? "Keen could not confirm this approval request. The requested study-task change was not confirmed as executed."
      : "Keen could not reject this approval request. The request may still be pending.",
    retryable: error?.detail?.retryable ?? true,
    recovery: "Check the local service and retry; Keen will reuse the same approval request key until its result is known.",
    automaticRecovery: false,
  };
}

export function isTerminalRun(run: AgentRun): boolean {
  return run.status === "completed"
    || run.status === "failed"
    || run.status === "cancelled"
    || run.status === "interrupted";
}
