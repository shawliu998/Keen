import type { LearningCoreStatus as Status } from "../services/LearningCoreProvider";

const labels: Record<Status, string> = {
  demo: "Browser Demo · no service calls",
  starting: "Learning core starting…",
  binding: "Learning core binding…",
  migrating: "Learning core migrating…",
  recovering: "Learning core recovering…",
  starting_server: "Learning core starting server…",
  health_checking: "Learning core checking health…",
  restarting: "Learning core restarting…",
  healthy: "Learning core ready",
  unavailable: "Learning core unavailable",
  configuration_error: "Learning core configuration error",
  error: "Learning core error",
};

export function LearningCoreStatus({ status, compact = false }: { status: Status; compact?: boolean }) {
  return (
    <span className={`core-status core-status-${status}`} data-status={status} title={compact ? labels[status] : undefined}>
      <i aria-hidden />
      <span>{labels[status]}</span>
    </span>
  );
}
