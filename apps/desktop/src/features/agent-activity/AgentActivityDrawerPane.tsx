import { Activity } from "lucide-react";
import { AgentActivityPanel, type AgentActivityViewState } from "../agent/AgentActivityPanel";
import type { AgentMutationActivity } from "../agent/agentActivityTypes";
import { useAgentRuntime } from "../../services/AgentRuntimeProvider";

const startingCoreStatuses = new Set([
  "starting",
  "binding",
  "migrating",
  "recovering",
  "starting_server",
  "health_checking",
  "restarting",
]);

function lastMutationAction(
  mutations: readonly AgentMutationActivity[],
  mutationId: string,
): AgentMutationActivity["action"] {
  return [...mutations]
    .reverse()
    .find((mutation) => mutation.targetMutationId === mutationId && mutation.action !== null)
    ?.action ?? null;
}

export function AgentActivityDrawerPane({ contextReady = true }: { contextReady?: boolean }) {
  const runtime = useAgentRuntime();
  const { activity, issue, learningCoreStatus, mutationAction, approvalAction } = runtime;

  if (!contextReady) {
    return (
      <div className="context-drawer-empty" role="status" aria-live="polite">
        <Activity size={18} aria-hidden="true" />
        <h2>Restoring Agent activity</h2>
        <p>Keen is switching to this workspace. Actions remain unavailable until its recorded Agent state is loaded.</p>
      </div>
    );
  }

  if (learningCoreStatus === "demo" && runtime.run === null) {
    return (
      <div className="context-drawer-empty" role="status">
        <Activity size={18} aria-hidden="true" />
        <h2>No Agent activity in Browser Demo</h2>
        <p>A real Agent run has not started. Open the packaged app with a connected local service to record activity here.</p>
      </div>
    );
  }

  if (runtime.run === null && startingCoreStatuses.has(learningCoreStatus)) {
    return (
      <div className="context-drawer-empty" role="status">
        <Activity size={18} aria-hidden="true" />
        <h2>Preparing the local Agent</h2>
        <p>No run is active. Activity will remain empty until the local learning service is ready and a run starts.</p>
      </div>
    );
  }

  const viewState: AgentActivityViewState = (() => {
    if (issue?.code === "provider_missing") return "provider_missing";
    if (issue?.code === "provider_unavailable") return "provider_unavailable";
    if (issue?.code === "activity_unavailable") return "activity_unavailable";
    if (runtime.phase === "recovering" && activity.partial) return "reconnecting";
    if (
      learningCoreStatus !== "healthy"
      && !startingCoreStatuses.has(learningCoreStatus)
    ) return "offline";
    return "ready";
  })();

  const mutationActions = Object.fromEntries(activity.mutations
    .filter((mutation) => mutation.entityType === "study_task" && mutation.action === null)
    .map((mutation) => {
      const pending = mutationAction.pending?.mutationId === mutation.mutationId
        ? mutationAction.pending.action
        : null;
      const error = mutationAction.target?.mutationId === mutation.mutationId
        ? mutationAction.error?.message ?? null
        : null;
      return [mutation.mutationId, {
        undone: lastMutationAction(activity.mutations, mutation.mutationId) === "undo",
        pendingAction: pending,
        error,
      }];
    }));
  const mutationActionsLocked = mutationAction.pending !== null || runtime.phase !== "idle";

  return (
    <AgentActivityPanel
      runId={runtime.run?.id ?? null}
      state={activity}
      viewState={viewState}
      mutationActions={mutationActions}
      cancelPending={runtime.phase === "cancelling"}
      onCancel={() => { void runtime.cancelRun(); }}
      onUndo={mutationActionsLocked ? undefined : (mutationId) => { void runtime.undoMutation(mutationId); }}
      onRedo={mutationActionsLocked ? undefined : (mutationId) => { void runtime.redoMutation(mutationId); }}
      approvalAction={approvalAction ? {
        pending: approvalAction.pending,
        error: approvalAction.error?.message ?? null,
      } : undefined}
      onConfirmApproval={runtime.confirmApproval
        ? (approvalId) => { void runtime.confirmApproval?.(approvalId); }
        : undefined}
      onRejectApproval={runtime.rejectApproval
        ? (approvalId) => { void runtime.rejectApproval?.(approvalId); }
        : undefined}
    />
  );
}
