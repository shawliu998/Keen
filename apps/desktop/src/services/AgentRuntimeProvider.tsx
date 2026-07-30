import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import {
  AgentEventStreamDisconnectedError,
  LearningCoreResponseError,
  type AgentRun,
  type AgentRunActivityEvent,
  type AgentRunEvent,
} from "@keen/api-client";
import { agentActivityReducer, initialAgentActivityState } from "../features/agent/agentActivityReducer";
import {
  AGENT_STREAM_RETRY_DELAY_MS,
  activityUnavailableIssue,
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
  type AgentActivityContext,
  type AgentRuntimeIssue,
  type AgentRuntimePhase,
  isSameAgentActivityContext,
} from "../features/agent/useAgentRunLifecycle";
import { useAgentApprovalActions } from "../features/agent/useAgentApprovalActions";
import { useLearningCore } from "./LearningCoreProvider";

export type { AgentMutationActionState, AgentApprovalActionState, AgentRunStartRequest,
  AgentRuntimeContextValue, AgentRuntimeIssue, AgentRuntimeIssueCode,
  AgentRuntimePhase } from "../features/agent/useAgentRunLifecycle";

const AgentRuntimeContext = createContext<AgentRuntimeContextValue | null>(null);

const initialMutationActionState: AgentMutationActionState = {
  target: null,
  pending: null,
  error: null,
  lastResult: null,
};

function getActivityContextKey(context: AgentActivityContext): string {
  if (context === null) return "null";
  if ("conversationId" in context) return `conversation:${context.conversationId}`;
  return `study:${context.studySessionId}`;
}

export function AgentRuntimeProvider({ children }: { children: ReactNode }) {
  const { client, connectionGeneration, status: learningCoreStatus } = useLearningCore();
  const [activity, dispatch] = useReducer(agentActivityReducer, initialAgentActivityState);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [phase, setPhase] = useState<AgentRuntimePhase>("idle");
  const [issue, setIssue] = useState<AgentRuntimeIssue | null>(null);
  const [mutationAction, setMutationAction] = useState<AgentMutationActionState>(initialMutationActionState);
  const [streamRevision, setStreamRevision] = useState(0);
  const mountedRef = useRef(true);
  const creatingRef = useRef(false);
  const runRef = useRef<AgentRun | null>(null);
  const lastEventIdRef = useRef<string | null>(null);
  const terminalSeenRef = useRef(false);
  const streamCompleteRef = useRef(false);
  const activityRefreshRunIdRef = useRef<string | null>(null);
  const restoreRequestIdRef = useRef(0);
  const createAbortRef = useRef<AbortController | null>(null);
  const getAbortRef = useRef<AbortController | null>(null);
  const contextRestoreAbortRef = useRef<AbortController | null>(null);
  const abortContextRestore = useCallback(() => {
    contextRestoreAbortRef.current?.abort();
    contextRestoreAbortRef.current = null;
    restoreRequestIdRef.current += 1;
  }, []);
  const streamAbortRef = useRef<AbortController | null>(null);
  const cancelAbortRef = useRef<AbortController | null>(null);
  const mutationAbortRef = useRef<AbortController | null>(null);
  const mutationActionRef = useRef<AgentMutationActionState>(initialMutationActionState);
  const [activityContext, setActivityContextState] = useState<AgentActivityContext>(null);
  const [activityContextReady, setActivityContextReady] = useState(true);
  const [activityContextRevision, setActivityContextRevision] = useState(0);

  const updateMutationAction = useCallback((next: AgentMutationActionState) => {
    mutationActionRef.current = next;
    setMutationAction(next);
  }, []);

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

  const setActivityContext = useCallback((nextContext: AgentActivityContext) => {
    if (isSameAgentActivityContext(nextContext, activityContext)) return;
    abortContextRestore();
    abortLocalOperations();
    updateRun(null);
    dispatch({ type: "reset" });
    setIssue(null);
    updateMutationAction(initialMutationActionState);
    resetApproval();
    setPhase(nextContext === null ? "idle" : "recovering");
    streamCompleteRef.current = false;
    terminalSeenRef.current = false;
    lastEventIdRef.current = null;
    activityRefreshRunIdRef.current = null;
    creatingRef.current = false;
    setActivityContextReady(nextContext === null);
    setActivityContextState(nextContext);
  }, [activityContext, abortContextRestore, abortLocalOperations, resetApproval, updateMutationAction, updateRun]);

  // Learning interventions create Agent runs through their own typed endpoint.
  // Their route context remains stable, so invalidate this snapshot explicitly.
  const refreshActivityContext = useCallback((knownRunId?: string) => {
    if (activityContext === null) return;
    abortContextRestore();
    getAbortRef.current?.abort();
    streamAbortRef.current?.abort();
    activityRefreshRunIdRef.current = knownRunId ?? null;
    updateRun(null);
    dispatch({ type: "reset" });
    setIssue(null);
    updateMutationAction(initialMutationActionState);
    resetApproval();
    streamCompleteRef.current = false;
    terminalSeenRef.current = false;
    lastEventIdRef.current = null;
    setActivityContextReady(false);
    setPhase("recovering");
    setActivityContextRevision((revision) => revision + 1);
  }, [activityContext, abortContextRestore, resetApproval, updateMutationAction, updateRun]);

  useEffect(() => {
    if (activityContext === null) {
      return;
    }
    if (learningCoreStatus !== "healthy" || !client) {
      const unavailableUpdate = window.setTimeout(() => {
        if (!mountedRef.current) return;
        streamCompleteRef.current = true;
        setActivityContextReady(true);
        setPhase("idle");
        if (learningCoreStatus !== "demo") setIssue(unavailableIssue());
      }, 0);
      return () => window.clearTimeout(unavailableUpdate);
    }

    const restoreRequestId = ++restoreRequestIdRef.current;
    const localContext = activityContext;
    const localContextKey = getActivityContextKey(localContext);
    const restoreController = new AbortController();
    contextRestoreAbortRef.current = restoreController;
    streamAbortRef.current?.abort();

    const replaySortedEvents = (events: readonly AgentRunActivityEvent[]) => {
      const ordered = [...events].sort((left, right) => left.sequence - right.sequence);
      for (const event of ordered) {
        dispatch({ type: "event", event: event as AgentRunEvent });
        lastEventIdRef.current = event.id;
      }
    };

    const restore = async () => {
      await Promise.resolve();
      if (restoreController.signal.aborted || restoreRequestId !== restoreRequestIdRef.current) return;
      setActivityContextReady(false);
      setPhase("recovering");
      try {
        const expectedRunId = activityRefreshRunIdRef.current;
        let snapshot = await client.getLatestAgentRunActivity(localContext, { signal: restoreController.signal });
        // A newly-created intervention can be returned by its typed endpoint just
        // before it becomes visible to the workspace activity projection. Retry
        // that projection once, only when a confirmed run was supplied by it.
        if (expectedRunId !== null && snapshot.run?.id !== expectedRunId) {
          await delayWithAbort(AGENT_STREAM_RETRY_DELAY_MS, restoreController.signal);
          snapshot = await client.getLatestAgentRunActivity(localContext, { signal: restoreController.signal });
        }
        if (restoreController.signal.aborted || restoreRequestId !== restoreRequestIdRef.current || getActivityContextKey(activityContext) !== localContextKey) {
          return;
        }
        const { run: snapshotRun, events } = snapshot;
        dispatch({ type: "reset" });
        lastEventIdRef.current = null;
        terminalSeenRef.current = false;
        streamCompleteRef.current = false;
        if (expectedRunId !== null && snapshotRun?.id !== expectedRunId) {
          updateRun(null);
          activityRefreshRunIdRef.current = expectedRunId;
          setIssue(activityUnavailableIssue());
          streamCompleteRef.current = true;
          setPhase("idle");
          setActivityContextReady(true);
          return;
        }
        if (snapshotRun === null) {
          // A confirmed intervention run may reach the activity projection a
          // moment later; the single retry above is its only special handling.
          setIssue(null);
          streamCompleteRef.current = true;
          setPhase("idle");
          setActivityContextReady(true);
          return;
        }

        activityRefreshRunIdRef.current = null;
        updateRun(snapshotRun);
        dispatch({ type: "run_status", status: snapshotRun.status });
        replaySortedEvents(events);
        const terminal = isTerminalRun(snapshotRun);
        terminalSeenRef.current = terminal;
        setIssue(issueForTerminalRun(snapshotRun));
        if (terminal) {
          streamCompleteRef.current = true;
          setPhase("idle");
          setActivityContextReady(true);
          return;
        }
        if (snapshotRun.status === "running" || snapshotRun.status === "queued" || snapshotRun.status === "waiting_approval") {
          if (snapshotRun.status === "waiting_approval") {
            const pending = await client.getPendingLevel2Actions(snapshotRun.id, { signal: restoreController.signal });
            if (restoreController.signal.aborted || restoreRequestId !== restoreRequestIdRef.current || getActivityContextKey(activityContext) !== localContextKey) return;
            dispatch({ type: "pending_approval", approval: pending.approvals[0] ?? null });
          }
          setStreamRevision((revision) => revision + 1);
          setPhase("recovering");
          setActivityContextReady(true);
          return;
        }
        setPhase("idle");
        setActivityContextReady(true);
      } catch (error) {
        if (restoreController.signal.aborted || restoreRequestId !== restoreRequestIdRef.current) return;
        setIssue(error instanceof LearningCoreResponseError ? issueForResponse(error) : unavailableIssue());
        setPhase("idle");
        setActivityContextReady(true);
      }
    };

    void restore();
    return () => {
      restoreController.abort();
    };
  }, [activityContext, activityContextRevision, client, connectionGeneration, learningCoreStatus, resetApproval, setIssue, setPhase, setStreamRevision, updateRun]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortLocalOperations();
    };
  }, [abortLocalOperations]);

  const startRun = useCallback(async (request: AgentRunStartRequest): Promise<AgentRun | null> => {
    if (learningCoreStatus !== "healthy" || !client) {
      setIssue(unavailableIssue());
      return null;
    }
    const visibleRun = runRef.current;
    const shouldResumeVisibleRun = visibleRun !== null
      && !isTerminalRun(visibleRun)
      && phase === "idle"
      && !creatingRef.current;
    if (
      creatingRef.current
      || phase !== "idle"
      || mutationActionRef.current.pending !== null
      || (visibleRun !== null && !isTerminalRun(visibleRun))
    ) {
      setIssue({
        code: "agent_busy",
        message: "A local Agent operation is already in progress, so another run was not started.",
        retryable: true,
        recovery: "Wait for the current operation to settle, then start a new run.",
        automaticRecovery: false,
      });
      if (shouldResumeVisibleRun) {
        resumeAuthoritativeEvents();
        setPhase("recovering");
      }
      return null;
    }

    abortContextRestore();
    creatingRef.current = true;
    createAbortRef.current?.abort();
    getAbortRef.current?.abort();
    streamAbortRef.current?.abort();
    setPhase("creating");
    const controller = new AbortController();
    createAbortRef.current = controller;
    try {
      const created = await client.createAgentRun({
        ...request,
        idempotencyKey: createAgentIdempotencyKey(),
      }, { signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted) return null;
      streamCompleteRef.current = false;
      terminalSeenRef.current = false;
      lastEventIdRef.current = null;
      dispatch({ type: "reset" });
      setIssue(null);
      updateMutationAction(initialMutationActionState);
      resetApproval();
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
  }, [client, learningCoreStatus, phase, resetApproval, resumeAuthoritativeEvents, updateMutationAction, updateRun, abortContextRestore]);

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
    if (creatingRef.current || phase !== "idle") {
      setIssue({
        code: "agent_busy",
        message: "The Agent is still settling another operation, so this mutation request was not sent.",
        retryable: true,
        recovery: "Wait for the current Agent operation to settle, then try again.",
        automaticRecovery: false,
      });
      return false;
    }
    const activeRun = runRef.current;
    if (!client || learningCoreStatus !== "healthy" || !activeRun || !isTerminalRun(activeRun)) {
      updateMutationAction({
        target: { action, mutationId },
        pending: null,
        error: mutationIssue(undefined, action),
        lastResult: null,
      });
      return false;
    }
    if (mutationAbortRef.current || mutationActionRef.current.pending !== null) {
      setIssue({
        code: "agent_busy",
        message: "Another mutation action is still pending, so this request was not sent.",
        retryable: true,
        recovery: "Wait for the pending action to finish, then try again.",
        automaticRecovery: false,
      });
      return false;
    }
    const controller = new AbortController();
    mutationAbortRef.current = controller;
    const requestedTarget = { action, mutationId };
    updateMutationAction({
      target: requestedTarget,
      pending: requestedTarget,
      error: null,
      lastResult: null,
    });
    try {
      const operation = action === "undo" ? client.undoAgentMutation : client.redoAgentMutation;
      const result = await operation.call(client, activeRun.id, mutationId, {
        idempotencyKey: createAgentIdempotencyKey(),
      }, { signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted) return false;
      const authoritativeTarget = {
        action: result.action,
        mutationId: result.targetMutationId,
      };
      updateMutationAction({
        target: authoritativeTarget,
        pending: authoritativeTarget,
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
      updateMutationAction({
        target: requestedTarget,
        pending: null,
        error: mutationIssue(error instanceof LearningCoreResponseError ? error : undefined, action),
        lastResult: null,
      });
      return false;
    } finally {
      if (mutationAbortRef.current === controller) mutationAbortRef.current = null;
    }
  }, [client, learningCoreStatus, phase, updateMutationAction]);

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
            if (
              event.type === "state_mutation"
              && "action" in event.data
              && "targetMutationId" in event.data
              && mutationActionRef.current.pending?.action === event.data.action
              && mutationActionRef.current.pending.mutationId === event.data.targetMutationId
            ) {
              updateMutationAction({
                ...mutationActionRef.current,
                target: {
                  action: event.data.action,
                  mutationId: event.data.targetMutationId,
                },
                pending: null,
                error: null,
              });
            }
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
  }, [client, connectionGeneration, learningCoreStatus, runId, streamRevision, updateMutationAction, updateRun]);

  const value = useMemo<AgentRuntimeContextValue>(() => ({
    activity,
    run,
    activityContext,
    activityContextReady,
    phase,
    issue,
    mutationAction,
    approvalAction,
    learningCoreStatus,
    startRun,
    cancelRun,
    setActivityContext,
    refreshActivityContext,
    undoMutation,
    redoMutation,
    confirmApproval,
    rejectApproval,
  }), [activity, activityContext, activityContextReady, approvalAction, cancelRun, confirmApproval, issue, learningCoreStatus, mutationAction, phase, redoMutation, refreshActivityContext, rejectApproval, run, setActivityContext, startRun, undoMutation]);

  return <AgentRuntimeContext.Provider value={value}>{children}</AgentRuntimeContext.Provider>;
}

export function useAgentRuntime(): AgentRuntimeContextValue {
  const value = useOptionalAgentRuntime();
  if (!value) throw new Error("useAgentRuntime must be used inside AgentRuntimeProvider.");
  return value;
}

/** Supports focused page rendering outside the application shell. */
export function useOptionalAgentRuntime(): AgentRuntimeContextValue | null {
  return useContext(AgentRuntimeContext);
}
