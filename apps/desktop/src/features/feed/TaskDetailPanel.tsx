import { useEffect, useRef } from "react";
import { BookOpenText, CalendarClock, Check, Clock3, LoaderCircle, Repeat2, X } from "lucide-react";
import { Badge, Button } from "@keen/ui";
import type { AutonomousStudySession, LearningActionCandidate, LearningFeedTask } from "@keen/api-client";
import type { LearningTask, TaskStatus } from "@keen/domain";
import { displayLearningTitle } from "../learningPresentation";

export type TaskDetailSelection =
  | { kind: "demo"; task: LearningTask }
  | { kind: "read-only"; task: LearningTask }
  | { kind: "live"; task: LearningFeedTask; candidate: LearningActionCandidate | null };

const statusLabels: Record<TaskStatus, string> = {
  today: "Today",
  upcoming: "Upcoming",
  overdue: "Overdue",
  completed: "Completed",
};

function actionLabel(action: string) {
  return action.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function readableDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function readableReason(value: string) {
  const readable = value.replace(/\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b/gu, readableDate);
  const mastery = readable.match(/^Mastery is (\d+)%, (?:at or )?below the (?:very-weak|weak) threshold of \d+%\.$/i);
  if (mastery?.[1]) return `This is one of your weakest recorded concepts (${mastery[1]}% mastery), so it is a useful next place to study.`;
  if (/^Mastery is (?:below the weak threshold|weak)\.?$/i.test(readable)) {
    return "This concept is below your current mastery target, so it is a useful next place to study.";
  }
  return readable;
}

export function TaskDetailPanel({
  selection,
  courseTitle,
  section,
  startPending,
  startUnavailable,
  studySession,
  studySessionPending,
  studySessionError,
  onBack,
  onDemoUpdate,
  onReview,
  onStart,
  onViewHistory,
}: {
  selection: TaskDetailSelection;
  courseTitle: string;
  section: "today" | "upcoming" | "completed";
  startPending: boolean;
  startUnavailable: boolean;
  studySession: Pick<AutonomousStudySession, "progress"> | null;
  studySessionPending: boolean;
  studySessionError: boolean;
  onBack: () => void;
  onDemoUpdate: (status: TaskStatus) => void;
  onReview: (task: LearningFeedTask) => void;
  onStart: (task: LearningFeedTask) => void;
  onViewHistory: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const { task } = selection;
  const title = displayLearningTitle(task.title);
  const liveTask = selection.kind === "live" ? selection.task : null;
  const candidate = selection.kind === "live" ? selection.candidate : null;
  const localTask = selection.kind === "live" ? null : selection.task;
  const isLive = liveTask !== null;
  const isDemo = selection.kind === "demo";
  const completed = task.status === "completed";
  const isReview = liveTask?.source_type === "review";
  const status = liveTask
    ? completed
      ? "Completed"
      : liveTask.status === "overdue"
        ? "Overdue"
        : section === "today"
          ? "Today"
          : "Upcoming"
    : statusLabels[localTask!.status];
  const due = liveTask ? readableDate(liveTask.due_at) : localTask!.due;
  const estimate = liveTask ? liveTask.estimated_minutes : localTask!.durationMinutes;
  const progress = completed
    ? "Complete"
    : startPending
      ? "Opening session"
      : studySession
        ? `${Math.round(Math.min(1, Math.max(0, studySession.progress)) * 100)}% complete`
        : studySessionPending
          ? "Checking…"
          : studySessionError
            ? "Unavailable"
            : "Not started";

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, [task.id]);

  return (
    <section className="task-detail-panel" aria-labelledby="task-detail-title">
      <header className="task-detail-toolbar">
        <div><BookOpenText size={16} aria-hidden="true" /><span>{courseTitle}</span></div>
        <Button className="task-detail-close" aria-label="Close details" title="Close details" onClick={onBack}><X size={15} aria-hidden="true" /></Button>
      </header>
      <div className="task-detail-scroll">
        <div className="task-detail-content">
          <header className="task-detail-heading">
            <div className="task-detail-badges">
              <Badge tone={status === "Overdue" ? "danger" : completed ? "success" : "accent"}>{status}</Badge>
            </div>
            <h2 id="task-detail-title" ref={headingRef} tabIndex={-1} title={title}>{title}</h2>
            <dl className="task-detail-meta">
              <div><dt>Course</dt><dd>{courseTitle}</dd></div>
              <div><CalendarClock size={14} aria-hidden="true" /><dt>Due</dt><dd>{due}</dd></div>
              <div><Clock3 size={14} aria-hidden="true" /><dt>Estimate</dt><dd>{estimate} min</dd></div>
              <div><dt>Progress</dt><dd>{progress}</dd></div>
              {isLive && completed && liveTask.completed_at ? <div><dt>Completed</dt><dd>{readableDate(liveTask.completed_at)}</dd></div> : null}
            </dl>
          </header>

          <section className="task-detail-section task-detail-brief">
            <span className="task-detail-section-label">Learning goal</span>
            <p>{readableReason(task.reason)}</p>
          </section>

          {!(isLive && completed) ? <section className="task-detail-section task-detail-plan">
            <div className="task-detail-section-heading"><div><span className="visually-hidden">Expected steps</span><h3>Next step</h3></div></div>
            <ol className="task-flow task-action-list">
              {isLive && !completed ? <>
                <li className={startPending ? "loading" : "current"}><i>{startPending ? <LoaderCircle className="spin" size={13} /> : 1}</i><div><strong>{isReview ? "Open this due review" : "Open Deep Learn"}</strong><span>{isReview ? "Review the exact saved item that created this task." : candidate ? `Focus: ${actionLabel(candidate.action)}.` : "Continue at the next saved learning step."}</span></div></li>
                <li><i>2</i><div><strong>{isReview ? "Complete the review" : "Continue the session plan"}</strong><span>{isReview ? "Reveal the expected answer and record your recall rating." : "Your current and next step will appear in Deep Learn."}</span></div></li>
              </> : <>
                <li className={completed ? "done" : "current"}><i>{completed ? <Check size={13} /> : 1}</i><div><strong>{completed ? "Task completed" : isDemo ? "Review the key idea" : "Continue from an active task"}</strong><span>{isLive && completed && liveTask.completed_at ? `Completed ${readableDate(liveTask.completed_at)}.` : isDemo && completed ? "No learning progress was saved." : isDemo ? "Read a short explanation based on the sample course." : "Choose a task with an available study action."}</span></div></li>
                {isDemo && !completed ? <li><i>2</i><div><strong>Answer one recall question</strong><span>Check what you remember before moving on.</span></div></li> : null}
              </>}
            </ol>
          </section> : null}
        </div>
      </div>

      <footer className="task-detail-next">
        <div>
          <strong>{completed ? (isDemo ? "Demo finished" : "Completed") : isDemo ? "Demo task" : "Ready to continue"}</strong>
          <span>{isLive && completed ? "This saved task is read-only. Open History to review your learning record." : isDemo && completed ? "This preview did not change your learning history." : completed ? "This is only a visual preview; no learning data was written." : isReview ? "Open the exact due item in Review." : isLive ? "Open Deep Learn at the next saved step." : isDemo ? "Try the interaction. No learning progress will be saved." : "Choose an active task with an available study action."}</span>
        </div>
        {isDemo && !completed ? <Button className="primary" onClick={() => onDemoUpdate("completed")}><Check size={14} />Try demo task</Button> : null}
        {liveTask && completed ? <Button className="primary" onClick={onViewHistory}>View History</Button> : null}
        {liveTask && !completed && isReview ? <Button className="primary" disabled={!liveTask.source_id} onClick={() => onReview(liveTask)}><Repeat2 size={14} />Review</Button> : null}
        {liveTask && !completed && !isReview ? <Button className="primary" disabled={startPending || startUnavailable} onClick={() => onStart(liveTask)}>{startPending ? <LoaderCircle className="spin" size={14} /> : <Clock3 size={14} />}{startPending ? "Opening…" : "Open study"}</Button> : null}
      </footer>
    </section>
  );
}
