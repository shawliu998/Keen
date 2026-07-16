import type { AgentActivityState, AgentActivityStatus, AgentMutationActivity } from "./agentActivityTypes";
import "./agentActivity.css";

export type AgentActivityViewState =
  | "ready"
  | "reconnecting"
  | "provider_missing"
  | "provider_unavailable"
  | "offline";

export type AgentMutationActionState = {
  undone: boolean;
  pendingAction: "undo" | "redo" | null;
  error: string | null;
};

export type AgentActivityPanelProps = {
  runId: string | null;
  state: AgentActivityState;
  viewState?: AgentActivityViewState;
  mutationActions?: Readonly<Record<string, AgentMutationActionState | undefined>>;
  cancelPending?: boolean;
  onCancel?: () => void;
  onUndo?: (mutationId: string) => void;
  onRedo?: (mutationId: string) => void;
};

const statusCopy: Record<AgentActivityStatus, { label: string; description: string }> = {
  idle: { label: "Ready", description: "Start an Agent run to see its verified activity here." },
  queued: { label: "Queued", description: "The run is waiting for the local learning service." },
  running: { label: "Running", description: "The Agent is working. Activity appears as it is recorded." },
  partial: { label: "Reconnecting", description: "The live connection was interrupted. Recorded partial output is preserved while Keen reconnects." },
  waiting_approval: { label: "Waiting for confirmation", description: "This run is paused. Confirmation is read-only here; no action can be approved from this panel." },
  completed: { label: "Completed", description: "The Agent run completed and its recorded output is shown below." },
  failed: { label: "Failed", description: "The Agent run stopped before completion. Existing partial output is preserved." },
  cancelled: { label: "Cancelled", description: "The Agent run was cancelled. Existing partial output is preserved." },
  interrupted: { label: "Interrupted", description: "The Agent run was interrupted and did not complete. Existing partial output is preserved." },
};

const viewStateCopy: Partial<Record<AgentActivityViewState, { label: string; description: string }>> = {
  reconnecting: { label: "Reconnecting", description: "Keen is reconnecting to the local service. Recorded partial output is preserved." },
  provider_missing: { label: "Provider not configured", description: "No Agent provider is configured. Add a provider before starting a real run." },
  provider_unavailable: { label: "Provider unavailable", description: "The configured Agent provider could not be reached. No completion is being claimed; retry when it is available." },
  offline: { label: "Learning service offline", description: "Keen cannot reach the local learning service. Recorded activity remains visible, but no new work is running." },
};

const activeStatuses = new Set<AgentActivityStatus>(["queued", "running", "partial", "waiting_approval"]);

function humanizeToolName(toolName: string): string {
  return toolName.replaceAll("_", " ").replace(/\b\w/gu, (character) => character.toUpperCase());
}

function mutationLabel(mutation: AgentMutationActivity): string {
  if (mutation.operation === "create") return "Study task created";
  if (mutation.operation === "delete") return "Study task deleted";
  return "Study task updated";
}

function MutationAction({
  mutation,
  actionState,
  actionsAvailable,
  onUndo,
  onRedo,
}: {
  mutation: AgentMutationActivity;
  actionState: AgentMutationActionState | undefined;
  actionsAvailable: boolean;
  onUndo: AgentActivityPanelProps["onUndo"];
  onRedo: AgentActivityPanelProps["onRedo"];
}) {
  const undone = actionState?.undone ?? false;
  const pendingAction = actionState?.pendingAction ?? null;
  const callback = undone ? onRedo : onUndo;
  const action = undone ? "Redo" : "Undo";
  const disabled = !actionsAvailable || pendingAction !== null || callback === undefined;

  return (
    <li className="agent-activity-mutation">
      <div>
        <strong>{mutationLabel(mutation)}</strong>
        <span>
          {!actionsAvailable
            ? "Undo becomes available after the run stops and the local service is connected."
            : undone
              ? "This recorded local change is currently undone."
              : "This recorded local change can be undone."}
        </span>
      </div>
      <button
        type="button"
        className="agent-activity-action"
        aria-label={`${action} ${mutationLabel(mutation).toLowerCase()}`}
        disabled={disabled}
        aria-busy={pendingAction !== null}
        onClick={() => callback?.(mutation.mutationId)}
      >
        {pendingAction === "undo" ? "Undoing…" : pendingAction === "redo" ? "Redoing…" : action}
      </button>
      {actionState?.error ? <p className="agent-activity-action-error" role="alert">{actionState.error}</p> : null}
    </li>
  );
}

export function AgentActivityPanel({
  runId,
  state,
  viewState = "ready",
  mutationActions = {},
  cancelPending = false,
  onCancel,
  onUndo,
  onRedo,
}: AgentActivityPanelProps) {
  const override = viewStateCopy[viewState];
  const status = override ?? statusCopy[state.status];
  const reversibleMutations = state.mutations.filter((mutation) => mutation.entityType === "study_task");
  const canCancel = runId !== null && activeStatuses.has(state.status) && viewState !== "offline" && viewState !== "provider_missing";
  const isErrorView = viewState === "provider_missing" || viewState === "provider_unavailable" || viewState === "offline" || state.status === "failed" || state.status === "interrupted";

  return (
    <section className="agent-activity-panel" aria-labelledby="agent-activity-title">
      <header className="agent-activity-header">
        <div>
          <p className="agent-activity-eyebrow">Agent activity</p>
          <h2 id="agent-activity-title">{status.label}</h2>
        </div>
        {canCancel ? (
          <button
            type="button"
            className="agent-activity-cancel"
            onClick={onCancel}
            disabled={cancelPending || onCancel === undefined}
            aria-busy={cancelPending}
          >
            {cancelPending ? "Cancelling…" : "Cancel run"}
          </button>
        ) : null}
      </header>

      <div className={`agent-activity-state agent-activity-state-${isErrorView ? "error" : state.status}`} role={isErrorView ? "alert" : "status"}>
        <span aria-hidden="true" />
        <p>{status.description}</p>
      </div>

      {state.error ? (
        <div className="agent-activity-error" role="alert">
          <strong>{state.error.code.replaceAll("_", " ")}</strong>
          <p>{state.error.message ?? "The Agent did not provide more error detail."}</p>
          <small>{state.error.retryable ? "This error may be retried." : "Retry is not currently available for this error."}</small>
        </div>
      ) : null}

      <div className="agent-activity-content" aria-label="Agent response">
        {state.content ? <p>{state.content}</p> : <p className="agent-activity-empty">No Agent response has been recorded yet.</p>}
        {(state.partial || viewState === "reconnecting") && state.content ? <small>Partial response — reconnecting before more output can be shown.</small> : null}
        {state.contentTruncated ? <small>The displayed response reached Keen’s local display limit.</small> : null}
      </div>

      {state.tools.length > 0 ? (
        <section className="agent-activity-section" aria-labelledby="agent-tools-title">
          <h3 id="agent-tools-title">Tool activity</h3>
          <ul className="agent-activity-list">
            {state.tools.map((tool) => (
              <li key={tool.invocationId}>
                <span className={`agent-activity-tool-dot agent-activity-tool-${tool.status}`} aria-hidden="true" />
                <strong>{humanizeToolName(tool.toolName)}</strong>
                <span>{tool.status === "running" ? "Running" : tool.replayed ? "Completed from recorded result" : "Completed"}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {state.warnings.length > 0 ? (
        <section className="agent-activity-section" aria-labelledby="agent-warnings-title">
          <h3 id="agent-warnings-title">Warnings</h3>
          <ul className="agent-activity-warnings">
            {state.warnings.map((warning) => <li key={warning.eventId}><strong>{warning.code.replaceAll("_", " ")}</strong><span>{warning.message}</span></li>)}
          </ul>
        </section>
      ) : null}

      {reversibleMutations.length > 0 ? (
        <section className="agent-activity-section" aria-labelledby="agent-changes-title">
          <h3 id="agent-changes-title">Local changes</h3>
          <ul className="agent-activity-mutations">
            {reversibleMutations.map((mutation) => (
              <MutationAction
                key={mutation.mutationId}
                mutation={mutation}
                actionState={mutationActions[mutation.mutationId]}
                actionsAvailable={state.terminal && runId !== null && viewState !== "offline"}
                onUndo={onUndo}
                onRedo={onRedo}
              />
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
