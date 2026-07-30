import {
  AlertCircle,
  Check,
  Clock3,
  LoaderCircle,
  ServerOff,
} from "lucide-react";
import { Badge, Button, Card } from "@keen/ui";
import type { LearningFeedTask } from "@keen/api-client";
import type { LearningTask, TaskStatus } from "@keen/domain";
import {
  isLearningCoreStarting,
  type LearningCoreErrorKind,
  type LearningCoreStatus,
} from "../../services/LearningCoreProvider";
import { displayLearningTitle } from "../learningPresentation";

export type FeedSection = Exclude<TaskStatus, "overdue">;
export const feedSections = ["today", "upcoming", "completed"] as const satisfies readonly FeedSection[];
export const taskStatusLabels: Record<TaskStatus, string> = {
  today: "Today",
  upcoming: "Upcoming",
  overdue: "Overdue",
  completed: "Completed",
};

export function FeedServiceState({
  status,
  errorKind = null,
  retryError,
  onRetry,
}: {
  status: LearningCoreStatus;
  errorKind?: LearningCoreErrorKind | null;
  retryError?: string | null;
  onRetry: () => void;
}) {
  const starting = isLearningCoreStarting(status);
  const titles: Partial<Record<LearningCoreStatus, string>> = {
    starting: "Restoring your tasks",
    binding: "Restoring your tasks",
    migrating: "Updating your tasks",
    recovering: "Recovering your tasks",
    starting_server: "Restoring your tasks",
    health_checking: "Checking your tasks",
    restarting: "Restarting the learning workspace",
    unavailable: "Learning queue unavailable",
    configuration_error: "Learning queue needs attention",
  };
  const title = titles[status]
    ?? (errorKind === "health" ? "Learning queue could not be checked" : "Learning queue unavailable");
  const fallback = starting
    ? "Your saved tasks will appear here when the workspace is ready."
    : status === "configuration_error"
      ? "Follow the recovery guidance, then retry your learning queue."
      : status === "unavailable"
        ? "Retry to reload your saved tasks."
        : errorKind === "connection"
          ? "Keen could not reach your learning queue. Retry now."
          : "Keen could not load your learning queue. Retry now.";
  return (
    <Card className={`service-state ${starting ? "is-loading" : ""}`} role={starting ? "status" : "alert"}>
      {starting ? <LoaderCircle className="spin" size={23} /> : <ServerOff size={23} />}
      <div>
        <strong>{title}</strong>
        <p>{fallback}</p>
        {retryError && <p className="service-retry-error" role="alert">{retryError}</p>}
      </div>
      {!starting && <Button onClick={onRetry}>Retry</Button>}
    </Card>
  );
}

export function FeedDataError({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className="service-state" role="alert">
      <AlertCircle size={23} />
      <div>
        <strong>Learning queue could not be loaded</strong>
        <p>Your saved tasks were not changed. Retry the queue now.</p>
      </div>
      <Button onClick={onRetry}>Retry data load</Button>
    </Card>
  );
}

export function TaskCard({
  task,
  onSelect,
  selected = false,
}: {
  task: LearningTask;
  onSelect: () => void;
  selected?: boolean;
}) {
  const title = displayLearningTitle(task.title);
  return (
    <button
      type="button"
      id={`feed-task-${task.id}`}
      data-task-detail-trigger
      className={`task-card feed-task-row ${selected ? "selected" : ""}`}
      aria-label={`Open task: ${title}`}
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <span className={`feed-task-status marker-${task.status}`} aria-hidden>
        {task.status === "completed"
          ? <Check size={14} />
          : task.status === "overdue"
            ? <AlertCircle size={14} />
            : <Clock3 size={14} />}
      </span>
      <span className="feed-task-copy">
        <strong>{title}</strong>
        <span>{task.course}</span>
        <small>{task.due} · {task.durationMinutes} min</small>
      </span>
      <Badge tone={task.status === "overdue" ? "danger" : task.status === "completed" ? "success" : "accent"}>
        {taskStatusLabels[task.status]}
      </Badge>
    </button>
  );
}

export function LiveTaskCard({
  task,
  courseTitle,
  onSelect,
  pending,
  selected = false,
  section,
}: {
  task: LearningFeedTask;
  courseTitle: string;
  onSelect: () => void;
  pending: boolean;
  selected?: boolean;
  section: FeedSection;
}) {
  const title = displayLearningTitle(task.title);
  const completed = task.status === "completed";
  const overdue = task.status === "overdue";
  const displayDate = completed ? task.completed_at : task.due_at;
  const due = new Intl.DateTimeFormat(document.documentElement.lang || "en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(displayDate ?? task.due_at));
  const statusLabel = pending
    ? "Starting"
    : completed
      ? "Completed"
      : overdue
        ? "Overdue"
        : section === "today"
          ? "Today"
          : "Upcoming";
  return (
    <button
      type="button"
      id={`feed-task-${task.id}`}
      data-task-detail-trigger
      className={`task-card feed-task-row ${selected ? "selected" : ""}`}
      aria-label={`Open task: ${title}`}
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <span className={`feed-task-status marker-${completed ? "completed" : overdue ? "overdue" : "today"}`} aria-hidden>
        {pending
          ? <LoaderCircle className="spin" size={14} />
          : completed
            ? <Check size={14} />
            : overdue
              ? <AlertCircle size={14} />
              : <Clock3 size={14} />}
      </span>
      <span className="feed-task-copy">
        <strong title={title}>{title}</strong>
        <span title={courseTitle}>{courseTitle}</span>
        <small title={`${completed ? "Completed" : "Due"} ${due} · ${task.estimated_minutes} min`}>{completed ? "Completed" : "Due"} {due} · {task.estimated_minutes} min</small>
      </span>
      <Badge tone={completed ? "success" : overdue ? "danger" : "accent"}>{statusLabel}</Badge>
    </button>
  );
}

export function FeedRestoreSkeleton() {
  return (
    <div className="feed-restore" role="status">
      <span className="visually-hidden">Restoring your learning queue</span>
      <div className="feed-restore-tabs" aria-hidden>
        {feedSections.map((section) => <i key={section} />)}
      </div>
      <i className="feed-restore-filter" aria-hidden />
      <div className="feed-restore-rows" aria-hidden>
        {Array.from({ length: 3 }, (_, index) => <div key={index}><i /><span><i /><i /><i /></span></div>)}
      </div>
    </div>
  );
}

export function RecommendationNotice({
  outcome,
}: {
  outcome: "empty" | "task_created" | "replay" | "covered_by_active_task";
}) {
  const messages = {
    empty: "No eligible action was found. No task was created.",
    task_created: "One local study task was created from the current evidence.",
    replay: "This task already exists or was completed today.",
    covered_by_active_task: "An active task already covers this action.",
  };
  return (
    <Card className="service-state" role="status">
      <Check size={23} />
      <div><strong>Learning queue updated</strong><p>{messages[outcome]}</p></div>
    </Card>
  );
}
