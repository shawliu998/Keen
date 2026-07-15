import type { LearningCoreStatus as Status } from "../services/LearningCoreProvider";

const labels: Record<Status, string> = {
  demo: "Browser Demo · no service calls",
  starting: "Learning core starting…",
  healthy: "Learning core healthy",
  unavailable: "Learning core unavailable",
  error: "Learning core error",
};

export function LearningCoreStatus({ status, compact = false }: { status: Status; compact?: boolean }) {
  return (
    <span className={`core-status core-status-${status}`} data-status={status}>
      <i aria-hidden />
      <span>{compact && status === "demo" ? "Demo" : labels[status]}</span>
    </span>
  );
}
