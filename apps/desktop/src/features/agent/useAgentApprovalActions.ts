import { useCallback, useRef, useState, type Dispatch, type RefObject } from "react";
import {
  LearningCoreResponseError,
  type AgentRun,
  type LearningCoreClient,
} from "@keen/api-client";
import type { AgentActivityAction, AgentActivityState } from "./agentActivityTypes";
import {
  approvalIssue,
  createAgentIdempotencyKey,
  isAbortError,
  type AgentApprovalActionState,
} from "./useAgentRunLifecycle";

type ApprovalClient = Pick<LearningCoreClient, "confirmLevel2Action" | "rejectLevel2Action">;

export function useAgentApprovalActions({
  client,
  enabled,
  activity,
  activeRunRef,
  mountedRef,
  updateRun,
  dispatch,
  resumeAuthoritativeEvents,
}: {
  client: ApprovalClient | null;
  enabled: boolean;
  activity: AgentActivityState;
  activeRunRef: RefObject<AgentRun | null>;
  mountedRef: RefObject<boolean>;
  updateRun: (run: AgentRun | null) => void;
  dispatch: Dispatch<AgentActivityAction>;
  resumeAuthoritativeEvents: () => void;
}) {
  const [approvalAction, setApprovalAction] = useState<AgentApprovalActionState>({
    pending: null,
    error: null,
    lastResult: null,
  });
  const abortRef = useRef<AbortController | null>(null);
  const keysRef = useRef(new Map<string, string>());

  const abortApproval = useCallback(() => abortRef.current?.abort(), []);
  const resetApproval = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    keysRef.current.clear();
    setApprovalAction({ pending: null, error: null, lastResult: null });
  }, []);

  const resolveApproval = useCallback(async (
    action: "confirm" | "reject",
    approvalId: string,
  ): Promise<boolean> => {
    const activeRun = activeRunRef.current;
    const pendingApproval = activity.pendingApproval;
    if (!client || !enabled || !activeRun || !pendingApproval || pendingApproval.approvalId !== approvalId) {
      setApprovalAction((current) => ({
        ...current,
        error: approvalIssue(undefined, action),
      }));
      return false;
    }
    if (abortRef.current) return false;

    const controller = new AbortController();
    abortRef.current = controller;
    const idempotencyKey = keysRef.current.get(approvalId) ?? createAgentIdempotencyKey();
    keysRef.current.set(approvalId, idempotencyKey);
    setApprovalAction({ pending: { approvalId, action }, error: null, lastResult: null });
    try {
      const operation = action === "confirm" ? client.confirmLevel2Action : client.rejectLevel2Action;
      const result = await operation.call(client, activeRun.id, approvalId, { idempotencyKey }, { signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted) return false;
      updateRun(result.run);
      dispatch({ type: "run_status", status: result.run.status });
      setApprovalAction({
        pending: null,
        error: null,
        lastResult: {
          approvalId: result.approvalId,
          resolution: result.resolution,
          replayed: result.replayed,
        },
      });
      resumeAuthoritativeEvents();
      return result.resolution !== "expired";
    } catch (error) {
      if (!mountedRef.current || isAbortError(error)) return false;
      setApprovalAction({
        pending: null,
        error: approvalIssue(
          error instanceof LearningCoreResponseError ? error : undefined,
          action,
        ),
        lastResult: null,
      });
      return false;
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [activity.pendingApproval, activeRunRef, client, dispatch, enabled, mountedRef, resumeAuthoritativeEvents, updateRun]);

  const confirmApproval = useCallback(
    (approvalId: string) => resolveApproval("confirm", approvalId),
    [resolveApproval],
  );
  const rejectApproval = useCallback(
    (approvalId: string) => resolveApproval("reject", approvalId),
    [resolveApproval],
  );

  return {
    approvalAction,
    abortApproval,
    resetApproval,
    confirmApproval,
    rejectApproval,
  };
}
