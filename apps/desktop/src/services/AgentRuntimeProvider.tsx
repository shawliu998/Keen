import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import {
  AgentEventStreamDisconnectedError,
  LearningCoreResponseError,
  type AgentRun,
} from "@keen/api-client";
import { agentActivityReducer, initialAgentActivityState } from "../features/agent/agentActivityReducer";
import {
  AGENT_STREAM_RETRY_DELAY_MS,
  createAgentIdempotencyKey,
  delayWithAbort,
  isAbortError,
  isTerminalRun,
  issueForResponse,
  issueForTerminalEvent,
  issueForTerminalRun,
  mutationIssue,
  unavailableIssue,
  type AgentMutationActionState,
  type AgentRunStartRequest,
  type AgentRuntimeContextValue,
  type AgentRuntimeIssue,
  type AgentRuntimePhase,
} from "../features/agent/useAgentRunLifecycle";
import { useAgentApprovalActions } from "../features/agent/useAgentApprovalActions";
import { useLearningCore } from "./LearningCoreProvider";

export type { AgentMutationActionState, AgentApprovalActionState, AgentRunStartRequest,
  AgentRuntimeContextValue, AgentRuntimeIssue, AgentRuntimeIssueCode,
  AgentRuntimePhase } from "../features/agent/useAgentRunLifecycle";

const AgentRuntimeContext = createContext<AgentRuntimeContextValue | null>(null);

export function AgentRuntimeProvider({ children }: { children: ReactNode }) {
  const { client, connectionGeneration, status: learningCoreStatus } = useLearningCore();
  const [activity, dispatch] = useReducer(agentActivityReducer, initialAgentActivityState);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [phase, setPhase] = useState<AgentRuntimePhase>("idle");
  const [issue, setIssue] = useState<AgentRuntimeIssue | null>(null);
  const [mutationAction, setMutationAction] = useState<AgentMutationActionState>({
    pending: null,
    error: null,
    lastResult: null,
  });
  const [streamRevision, setStreamRevision] = useState(0);
  const mountedRef = useRef(true);
  const creatingRef = useRef(false);
  const runRef = useRef<AgentRun | null>(null);
  const lastEventIdRef = useRef<string | null>(null);
  const terminalSeenRef = useRef(false);
  const streamCompleteRef = useRef(false);
  const createAbortRef = useRef<AbortController | null>(null);
  const getAbortRef = useRef<AbortController | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const cancelAbortRef = useRef<AbortController | null>(null);
  const mutationAbortRef = useRef<AbortController | null>(null);

  const updateRun = useCallback((nextRun: AgentRun | null) => {
    runRef.current = nextRun;
    setRun(nextRun);
  }, []);

  const resumeAuthoritativeEvents = useCallback(() => {
    streamCompleteRef.current = false;
    setStreamRevision((revision) => revision + 1);
  }, []);
  const {
    approvalAction,
    abortApproval,
    resetApproval,
    confirmApproval,
    rejectApproval,
  } = useAgentApprovalActions({
    client,
    enabled: learningCoreStatus === "healthy",
    activity,
    activeRunRef: runRef,
    mountedRef,
    updateRun,
    dispatch,
    resumeAuthoritativeEvents,
  });

  const abortLocalOperations = useCallback(() => {
    createAbortRef.current?.abort();
    getAbortRef.current?.abort();
    streamAbortRef.current?.abort();
    cancelAbortRef.current?.abort();
    mutationAbortRef.current?.abort();
    abortApproval();
  }, [abortApproval]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortLocalOperations();
    };
  }, [abortLocalOperations]);

  const startRun = useCallback(async (request: AgentRunStartRequest): Promise<AgentRun | null> => {
    if (creatingRef.current || phase === "cancelling") {
      setIssue({
        code: "agent_busy",
        message: "A local Agent operation is already in progress, so another run was not started.",
        retryable: true,
        recovery: "Wait for the current operation to settle, then start a new run.",
        automaticRecovery: false,
      });
      return null;
    }
    if (learningCoreStatus !== "healthy" || !client) {
      setIssue(unavailableIssue());
      return null;
    }

    creatingRef.current = true;
    createAbortRef.current?.abort();
    getAbortRef.current?.abort();
    streamAbortRef.current?.abort();
    streamCompleteRef.current = false;
    terminalSeenRef.current = false;
    lastEventIdRef.current = null;
    updateRun(null);
    dispatch({ type: "reset" });
    setIssue(null);
    setMutationAction({ pending: null, error: null, lastResult: null });
    resetApproval();
    setPhase("creating");
    const controller = new AbortController();
    createAbortRef.current = controller;
    try {
      const created = await client.createAgentRun({
        ...request,
        idempotencyKey: createAgentIdempotencyKey(),
      }, { signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted) return null;
      updateRun(created);
      dispatch({ type: "run_status", status: created.status });
      setIssue(issueForTerminalRun(created));
      setPhase("recovering");
      return created;
    } catch (error) {
      if (!mountedRef.current || isAbortError(error)) return null;
      setIssue(error instanceof LearningCoreResponseError ? issueForResponse(error) : {
        code: "provider_unavailable",
        message: "Keen could not reach the Agent provider, so the run was not confirmed and no completion is shown.",
        retryable: true,
        recovery: "Check the local service and provider connection, then start a new run.",
        automaticRecovery: false,
      });
      setPhase("idle");
      return null;
    } finally {
      if (createAbortRef.current === controller) createAbortRef.current = null;
      creatingRef.current = false;
    }
  }, [client, learningCoreStatus, phase, resetApproval, updateRun]);

  const cancelRun = useCallback(async (): Promise<boolean> => {
    const activeRun = runRef.current;
    if (!client || !activeRun || isTerminalRun(activeRun)) return false;
    cancelAbortRef.current?.abort();
    const controller = new AbortController();
    cancelAbortRef.current = controller;
    setPhase("cancelling");
    try {
      const response = await client.cancelAgentRun(activeRun.id, { signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted) return false;
      updateRun(response.run);
      dispatch({ type: "run_status", status: response.run.status });
      // Do not detach the stream here: it still owns the final cancelled error event.
      setPhase("streaming");
      return response.accepted;
    } catch (error) {
      if (!mountedRef.current || isAbortError(error)) return false;
      setIssue(error instanceof LearningCoreResponseError ? issueForResponse(error) : unavailableIssue());
      setPhase("idle");
      return false;
    } finally {
      if (cancelAbortRef.current === controller) cancelAbortRef.current = null;
    }
  }, [client, updateRun]);

  const mutate = useCallback(async (action: "undo" | "redo", mutationId: string): Promise<boolean> => {
    const activeRun = runRef.current;
    if (!client || learningCoreStatus !== "healthy" || !activeRun || !isTerminalRun(activeRun)) {
      setMutationAction((current) => ({ ...current, error: mutationIssue() }));
      return false;
    }
    if (mutationAbortRef.current) {
      setMutationAction((current) => ({ ...current, error: {
        code: "agent_busy",
        message: "Another mutation action is still pending, so this request was not sent.",
        retryable: true,
        recovery: "Wait for the pending action to finish, then try again.",
        automaticRecovery: false,
      } }));
      return false;
    }
    const controller = new AbortController();
    mutationAbortRef.current = controller;
    setMutationAction({ pending: { action, mutationId }, error: null, lastResult: null });
    try {
      const operation = action === "undo" ? client.undoAgentMutation : client.redoAgentMutation;
      const result = await operation.call(client, activeRun.id, mutationId, {
        idempotencyKey: createAgentIdempotencyKey(),
      }, { signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted) return false;
      setMutationAction({
        pending: null,
        error: null,
        lastResult: { action: result.action, targetMutationId: result.targetMutationId, replayed: result.replayed },
      });
      // The backend appends authoritative tool/state_mutation audit events after terminal.
      // Resume from the last accepted event instead of synthesizing mutation activity here.
      streamCompleteRef.current = false;
      setStreamRevision((revision) => revision + 1);
      return true;
    } catch (error) {
      if (!mountedRef.current || isAbortError(error)) return false;
      setMutationAction({
        pending: null,
        error: mutationIssue(error instanceof LearningCoreResponseError ? error : undefined),
        lastResult: null,
      });
      return false;
    } finally {
      if (mutationAbortRef.current === controller) mutationAbortRef.current = null;
    }
  }, [client, learningCoreStatus]);

  const undoMutation = useCallback((mutationId: string) => mutate("undo", mutationId), [mutate]);
  const redoMutation = useCallback((mutationId: string) => mutate("redo", mutationId), [mutate]);

  const runId = run?.id ?? null;
  useEffect(() => {
    getAbortRef.current?.abort();
    streamAbortRef.current?.abort();
    if (!runId || streamCompleteRef.current) return;
    if (learningCoreStatus !== "healthy" || !client) {
      const offlineUpdate = window.setTimeout(() => {
        if (!mountedRef.current || runRef.current?.id !== runId) return;
        dispatch({ type: "stream_disconnected" });
        setIssue(unavailableIssue());
        setPhase("recovering");
      }, 0);
      return () => window.clearTimeout(offlineUpdate);
    }

    let disposed = false;
    const recoveryController = new AbortController();
    getAbortRef.current = recoveryController;

    const recoverAndStream = async () => {
      setIssue((current) => current?.code === "run_interrupted" || current?.code === "run_failed" ? current : null);
      setPhase("recovering");
      while (!disposed && !streamCompleteRef.current) {
        try {
          const recovered = await client.getAgentRun(runId, { signal: recoveryController.signal });
          if (disposed || recoveryController.signal.aborted) return;
          updateRun(recovered);
          dispatch({ type: "run_status", status: recovered.status });
          if (recovered.status === "waiting_approval") {
            const pending = await client.getPendingLevel2Actions(runId, { signal: recoveryController.signal });
            if (disposed || recoveryController.signal.aborted) return;
            dispatch({ type: "pending_approval", approval: pending.approvals[0] ?? null });
          }
          const terminalIssue = issueForTerminalRun(recovered);
          if (terminalIssue) setIssue(terminalIssue);

          const streamController = new AbortController();
          streamAbortRef.current = streamController;
          setPhase("streaming");
          const resumeFrom = lastEventIdRef.current;
          for await (const event of client.agentRunEvents(runId, {
            ...(resumeFrom ? { lastEventId: resumeFrom } : {}),
            ...(resumeFrom && terminalSeenRef.current ? { terminalAlreadySeen: true } : {}),
            signal: streamController.signal,
          })) {
            if (disposed || streamController.signal.aborted) return;
            lastEventIdRef.current = event.id;
            dispatch({ type: "event", event });
            if (event.type === "done" || event.type === "error") terminalSeenRef.current = true;
            if (event.type === "error") setIssue(issueForTerminalEvent(event));
          }
          // The API client validates that a normal EOF has included a terminal marker. It may
          // also include post-terminal Undo/Redo audit events, all of which must be consumed.
          const finalRun = await client.getAgentRun(runId, { signal: recoveryController.signal });
          if (disposed || recoveryController.signal.aborted) return;
          updateRun(finalRun);
          dispatch({ type: "run_status", status: finalRun.status });
          const finalIssue = issueForTerminalRun(finalRun);
          if (finalIssue) setIssue(finalIssue);
          streamCompleteRef.current = true;
          setPhase("idle");
          return;
        } catch (error) {
          if (disposed || isAbortError(error)) return;
          if (error instanceof AgentEventStreamDisconnectedError) {
            if (error.lastEventId) lastEventIdRef.current = error.lastEventId;
            dispatch({ type: "stream_disconnected" });
            setPhase("recovering");
            await delayWithAbort(AGENT_STREAM_RETRY_DELAY_MS, recoveryController.signal);
            continue;
          }
          setIssue(error instanceof LearningCoreResponseError ? issueForResponse(error) : unavailableIssue());
          dispatch({ type: "stream_disconnected" });
          setPhase("idle");
          return;
        }
      }
    };

    void recoverAndStream();
    return () => {
      disposed = true;
      recoveryController.abort();
      streamAbortRef.current?.abort();
    };
  }, [client, connectionGeneration, learningCoreStatus, runId, streamRevision, updateRun]);

  const value = useMemo<AgentRuntimeContextValue>(() => ({
    activity,
    run,
    phase,
    issue,
    mutationAction,
    approvalAction,
    learningCoreStatus,
    startRun,
    cancelRun,
    undoMutation,
    redoMutation,
    confirmApproval,
    rejectApproval,
  }), [activity, approvalAction, cancelRun, confirmApproval, issue, learningCoreStatus, mutationAction, phase, redoMutation, rejectApproval, run, startRun, undoMutation]);

  return <AgentRuntimeContext.Provider value={value}>{children}</AgentRuntimeContext.Provider>;
}

export function useAgentRuntime(): AgentRuntimeContextValue {
  const value = useContext(AgentRuntimeContext);
  if (!value) throw new Error("useAgentRuntime must be used inside AgentRuntimeProvider.");
  return value;
}
