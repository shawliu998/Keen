import { Activity } from "lucide-react";
import type { AgentActivityStatus } from "../agent/agentActivityTypes";
import type {
  AgentRuntimeContextValue,
  AgentRuntimeIssue,
  AgentRuntimePhase,
} from "../../services/AgentRuntimeProvider";
import type { LearningCoreStatus } from "../../services/LearningCoreProvider";

export type AgentShellStatus = "idle" | "running" | "completed" | "error";

type AgentStatusInput = {
  activityStatus: AgentActivityStatus;
  phase: AgentRuntimePhase;
  issue: AgentRuntimeIssue | null;
  learningCoreStatus: LearningCoreStatus;
  hasRun?: boolean;
};

const activeStatuses = new Set<AgentActivityStatus>([
  "queued",
  "running",
  "partial",
  "waiting_approval",
]);
const unavailableCoreStatuses = new Set<LearningCoreStatus>([
  "unavailable",
  "configuration_error",
  "error",
]);

export function getAgentShellStatus({
  activityStatus,
  phase,
  issue,
  learningCoreStatus,
  hasRun = false,
}: AgentStatusInput): AgentShellStatus {
  const hasRecordedActivity = hasRun || activityStatus !== "idle";
  if (
    activityStatus === "failed"
    || activityStatus === "interrupted"
  ) return "error";
  if (
    activityStatus === "completed"
    && (issue === null || issue.code === "learning_core_unavailable")
  ) return "completed";
  if (issue) return "error";
  if (unavailableCoreStatuses.has(learningCoreStatus)) {
    return hasRecordedActivity ? "error" : "idle";
  }
  if (phase !== "idle" || activeStatuses.has(activityStatus)) return "running";
  return "idle";
}

const statusLabels: Record<AgentShellStatus, string> = {
  idle: "Agent idle",
  running: "Agent running",
  completed: "Agent completed",
  error: "Agent error",
};

export function AgentStatusButton({
  runtime,
  pressed,
  onClick,
}: {
  runtime: AgentRuntimeContextValue;
  pressed: boolean;
  onClick: () => void;
}) {
  const status = getAgentShellStatus({
    activityStatus: runtime.activity.status,
    phase: runtime.phase,
    issue: runtime.issue,
    learningCoreStatus: runtime.learningCoreStatus,
    hasRun: runtime.run !== null,
  });
  const label = statusLabels[status];

  return (
    <button
      type="button"
      className={`agent-status-button is-${status}`}
      aria-label={`${label}. ${pressed ? "Close" : "Open"} activity drawer`}
      aria-pressed={pressed}
      title={label}
      onClick={onClick}
    >
      <span className="agent-status-glyph" aria-hidden="true">
        <Activity size={14} strokeWidth={1.8} />
        <i />
      </span>
      <span>{label.replace("Agent ", "")}</span>
    </button>
  );
}
