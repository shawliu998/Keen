import type { AgentActivityState, AgentActivityStatus, AgentLearningRecord, AgentMutationActivity } from "./agentActivityTypes";
import "./agentActivity.css";

export type AgentActivityViewState =
  | "ready"
  | "reconnecting"
  | "provider_missing"
  | "provider_unavailable"
  | "activity_unavailable"
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
  approvalAction?: { pending: { approvalId: string; action: "confirm" | "reject" } | null; error: string | null };
  onConfirmApproval?: (approvalId: string) => void;
  onRejectApproval?: (approvalId: string) => void;
};

const statusCopy: Record<AgentActivityStatus, { label: string; description: string }> = {
  idle: { label: "Ready", description: "Start an Agent run to see its verified activity here." },
  queued: { label: "Queued", description: "The run is waiting for the local learning service." },
  running: { label: "Running", description: "The Agent is working. Activity appears as it is recorded." },
  partial: { label: "Reconnecting", description: "The live connection was interrupted. Recorded partial output is preserved while Keen reconnects." },
  waiting_approval: { label: "Waiting for confirmation", description: "This run is paused until you confirm or reject the requested local task completion." },
  completed: { label: "Completed", description: "The Agent run completed and its recorded output is shown below." },
  failed: { label: "Failed", description: "The Agent run stopped before completion. Existing partial output is preserved." },
  cancelled: { label: "Cancelled", description: "The Agent run was cancelled. Existing partial output is preserved." },
  interrupted: { label: "Interrupted", description: "The Agent run was interrupted and did not complete. Existing partial output is preserved." },
};

const viewStateCopy: Partial<Record<AgentActivityViewState, { label: string; description: string }>> = {
  reconnecting: { label: "Reconnecting", description: "Keen is reconnecting to the local service. Recorded partial output is preserved." },
  provider_missing: { label: "Provider not configured", description: "No Agent provider is configured. Add a provider before starting a real run." },
  provider_unavailable: { label: "Provider unavailable", description: "The configured Agent provider could not be reached. No completion is being claimed; retry when it is available." },
  activity_unavailable: { label: "Activity not ready", description: "Keen confirmed a newer run, but its recorded activity is not readable yet. An older run is not shown as current." },
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

function sourceLabel(source: AgentLearningRecord["sources"][number]): string {
  const location = source.sectionPath.length > 0 ? ` · ${source.sectionPath.join(" › ")}` : "";
  return `${source.documentName} · p. ${source.pageNumber}${location}`;
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
  approvalAction,
  onConfirmApproval,
  onRejectApproval,
}: AgentActivityPanelProps) {
  const override = viewStateCopy[viewState];
  const status = override ?? statusCopy[state.status];
  const reversibleMutations = state.mutations.filter(
    (mutation) => mutation.entityType === "study_task" && mutation.action === null,
  );
  const canCancel = onCancel !== undefined
    && runId !== null
    && activeStatuses.has(state.status)
    && viewState !== "offline"
    && viewState !== "provider_missing";
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
            disabled={cancelPending}
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

      {state.status === "waiting_approval" ? (
        state.pendingApproval ? (() => {
          const pending = approvalAction?.pending?.approvalId === state.pendingApproval!.approvalId ? approvalAction.pending : null;
          const disabled = viewState === "offline" || pending !== null || onConfirmApproval === undefined || onRejectApproval === undefined;
          return <section className="agent-activity-section agent-approval" aria-labelledby="agent-approval-title">
            <h3 id="agent-approval-title">Confirm local change</h3>
            <p><strong>{state.pendingApproval!.summary.title}</strong></p>
            <dl><div><dt>Task</dt><dd>{state.pendingApproval!.summary.taskTitle}</dd></div><div><dt>Course</dt><dd>{state.pendingApproval!.summary.courseTitle}</dd></div><div><dt>Effect</dt><dd>{state.pendingApproval!.summary.effect}</dd></div></dl>
            {viewState === "offline" ? <p className="agent-activity-action-error" role="alert">The learning service is offline, so this request cannot be sent. No task completion has been confirmed.</p> : null}
            {approvalAction?.error ? <p className="agent-activity-action-error" role="alert">{approvalAction.error}</p> : null}
            <div className="agent-approval-actions" aria-busy={pending !== null}>
              <button type="button" className="agent-activity-action" disabled={disabled} aria-busy={pending?.action === "confirm"} onClick={() => onConfirmApproval?.(state.pendingApproval!.approvalId)}>{pending?.action === "confirm" ? "Confirming…" : "Confirm"}</button>
              <button type="button" className="agent-activity-action" disabled={disabled} aria-busy={pending?.action === "reject"} onClick={() => onRejectApproval?.(state.pendingApproval!.approvalId)}>{pending?.action === "reject" ? "Rejecting…" : "Reject"}</button>
            </div>
          </section>;
        })() : <section className="agent-activity-section" role="status"><h3>Confirmation details unavailable</h3><p className="agent-activity-empty">The run is waiting for confirmation, but its recorded request is unavailable. Refresh the local service state before taking action.</p></section>
      ) : null}

      {state.learningRecord ? (
        <section className="agent-activity-section agent-learning-record" aria-labelledby="agent-learning-record-title">
          <h3 id="agent-learning-record-title">Learning record</h3>
          <p>{state.learningRecord.summary}</p>
          <div className="agent-learning-record-detail">
            <strong>Sources</strong>
            <ul>
              {state.learningRecord.sources.map((source, index) => <li key={`${source.documentName}-${source.pageNumber}-${index}`}>{sourceLabel(source)}</li>)}
            </ul>
          </div>
          <div className="agent-learning-record-detail">
            <strong>What’s next</strong>
            <p>{state.learningRecord.whatNext}</p>
          </div>
        </section>
      ) : (
        <div className="agent-activity-content" aria-label="Agent response">
          {state.content ? <p>{state.content}</p> : <p className="agent-activity-empty">No Agent response has been recorded yet.</p>}
          {(state.partial || viewState === "reconnecting") && state.content ? <small>Partial response — reconnecting before more output can be shown.</small> : null}
          {state.contentTruncated ? <small>The displayed response reached Keen’s local display limit.</small> : null}
        </div>
      )}

      {state.tools.length > 0 ? (
        <section className="agent-activity-section" aria-labelledby="agent-tools-title">
          <h3 id="agent-tools-title">Tool activity</h3>
          <ul className="agent-activity-list">
            {state.tools.map((tool) => (
              <li key={tool.invocationId}>
                <span className={`agent-activity-tool-dot agent-activity-tool-${tool.status}`} aria-hidden="true" />
                <strong>{humanizeToolName(tool.toolName)}</strong>
                <span>{tool.status === "running"
                  ? "Running"
                  : tool.status === "failed"
                    ? "Failed safely; the Agent may try another approach"
                    : tool.status === "cancelled"
                      ? "Cancelled before completion"
                      : tool.status === "stopped"
                        ? "Stopped without a completed result"
                        : tool.replayed
                          ? "Completed from recorded result"
                          : "Completed"}</span>
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
