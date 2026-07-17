import { useMemo, useState } from "react";
import {
  AlertCircle, CalendarClock, Check, ChevronRight, Clock3, Filter,
  Lightbulb, LoaderCircle, RotateCcw, ServerOff, Square, Sparkles,
} from "lucide-react";
import { Badge, Button, Card, EmptyState, Progress } from "@keen/ui";
import type { LearningActionCandidate, LearningFeedTask } from "@keen/api-client";
import type { LearningTask, TaskStatus } from "@keen/domain";
import { Page, Segmented } from "../../components/Page";
import { isLearningCoreStarting, useLearningCore, type LearningCoreErrorKind, type LearningCoreStatus } from "../../services/LearningCoreProvider";
import { useAppStore } from "../../state/appStore";
import { mapDemoStateTasks } from "./liveTasks";
import { useAutonomousLearningFeed } from "./useAutonomousLearningFeed";

const labels: Record<TaskStatus, string> = {
  today: "Today", upcoming: "Upcoming", overdue: "Overdue", completed: "Completed",
};

function FeedServiceState({ status, errorKind = null, serviceMessage, retryError, onRetry }: {
  status: LearningCoreStatus;
  errorKind?: LearningCoreErrorKind | null;
  serviceMessage?: string | null;
  retryError?: string | null;
  onRetry: () => void;
}) {
  const starting = isLearningCoreStarting(status);
  const titles: Partial<Record<LearningCoreStatus, string>> = {
    starting: "Learning core is starting",
    binding: "Learning core is binding its local port",
    migrating: "Learning core is migrating local data",
    recovering: "Learning core is recovering interrupted work",
    starting_server: "Learning core server is starting",
    health_checking: "Learning core is checking authenticated health",
    restarting: "Learning core is restarting",
    unavailable: "Learning core is unavailable",
    configuration_error: "Learning core has a configuration error",
  };
  const title = titles[status] ?? (errorKind === "health" ? "Learning core health check failed" : "Learning core connection status failed");
  const action = status === "unavailable"
    ? "Restart learning core"
    : status === "configuration_error"
      ? "Retry learning core"
      : status === "error" && errorKind !== "health" ? "Retry connection status" : "Retry health check";
  const fallback = starting
    ? "Keen is completing local startup and authenticated health checks. Live tasks and mastery will appear when it is ready; no demo records are being substituted."
    : status === "configuration_error"
      ? "The local learning service could not start. Live data is unavailable and stored learning records were not replaced. Follow the recovery guidance, then retry the learning core."
      : status === "unavailable"
        ? "The supervised local service is unavailable. Live data is unavailable and stored learning records were not replaced. Retry to request a new authenticated sidecar generation."
        : errorKind === "connection"
          ? "Keen could not read the supervised service status, so it did not assume that restarting was safe. Live data is unavailable and stored learning records were not replaced. Retry the status check."
          : "The ready local service failed an authenticated request. Live data is unavailable and stored learning records were not replaced. Retry the health check; restart Keen if the failure continues.";
  return (
    <Card className="service-state" role={starting ? "status" : "alert"}>
      {starting ? <LoaderCircle className="spin" size={23} /> : <ServerOff size={23} />}
      <div>
        <strong>{title}</strong>
        <p>{serviceMessage ?? fallback}</p>
        {retryError && <p className="service-retry-error" role="alert">{retryError}</p>}
      </div>
      {!starting && <Button onClick={onRetry}>{action}</Button>}
    </Card>
  );
}

function FeedDataError({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className="service-state" role="alert">
      <AlertCircle size={23} />
      <div>
        <strong>Live learning data could not be validated</strong>
        <p>The local service is healthy, but its tasks/mastery response failed or did not match the expected schema. The feed is affected; no records were modified and no demo data was substituted. Retry now, then restart Keen if it persists.</p>
      </div>
      <Button onClick={onRetry}>Retry data load</Button>
    </Card>
  );
}

function TaskCard({ task, isDemo, onUpdate, onInspect }: {
  task: LearningTask;
  isDemo: boolean;
  onUpdate: (status: TaskStatus) => void;
  onInspect: () => void;
}) {
  return (
    <Card className="task-card">
      <div className={`timeline-marker marker-${task.status}`}>
        {task.status === "completed" ? <Check size={14} /> : task.status === "overdue" ? <AlertCircle size={14} /> : <Clock3 size={14} />}
      </div>
      <div className="task-main">
        <div className="task-title-row"><div><Badge tone={task.status === "overdue" ? "danger" : task.status === "completed" ? "success" : "accent"}>{labels[task.status]}</Badge><h3>{task.title}</h3></div><span>{task.due}</span></div>
        <p className="reason"><Lightbulb size={14} />{task.reason}</p>
        <div className="task-meta"><span>{task.course}</span><span>{task.durationMinutes} min</span>{task.concepts.map((concept) => <Badge key={concept}>{concept}</Badge>)}</div>
        <div className="task-bottom">
          <div className="task-mastery"><span>Current mastery</span><Progress value={task.mastery} /><strong>{task.mastery}%</strong></div>
          <div className="task-actions">
            <button onClick={onInspect}>Why this?<ChevronRight size={13} /></button>
            {isDemo && task.status !== "completed" && <><Button onClick={() => onUpdate("upcoming")}><RotateCcw size={14} />Snooze</Button><Button className="primary" onClick={() => onUpdate("completed")}>{task.status === "today" ? "Start" : "Complete"}</Button></>}
            {!isDemo && <Badge>Live · read-only</Badge>}
          </div>
        </div>
      </div>
    </Card>
  );
}

function LiveTaskCard({ task, candidate, onInspect }: {
  task: LearningFeedTask;
  candidate: LearningActionCandidate | null;
  onInspect: () => void;
}) {
  const overdue = task.status === "overdue";
  return <Card className="task-card">
    <div className={`timeline-marker marker-${overdue ? "overdue" : "today"}`}>
      {overdue ? <AlertCircle size={14} /> : <Clock3 size={14} />}
    </div>
    <div className="task-main">
      <div className="task-title-row"><div><Badge tone={overdue ? "danger" : "accent"}>{overdue ? "Overdue" : "Upcoming"}</Badge><h3>{task.title}</h3></div><span>{new Date(task.due_at).toLocaleString()}</span></div>
      <p className="reason"><Lightbulb size={14} />{task.reason}</p>
      <div className="task-meta"><span>{task.estimated_minutes} min</span><Badge>Priority {task.priority_score.toFixed(2)}</Badge></div>
      <div className="task-bottom"><div className="task-actions"><button onClick={onInspect}>Why this?<ChevronRight size={13} /></button><Badge>Persisted local task</Badge></div></div>
      {candidate ? <p className="feed-candidate-note">Current action: {candidate.action.replaceAll("_", " ")}.</p> : null}
    </div>
  </Card>;
}

function RecommendationNotice({ outcome }: { outcome: "empty" | "task_created" | "replay" | "covered_by_active_task" }) {
  const messages = {
    empty: "No eligible action was found. No task was created.",
    task_created: "Keen created one local study task from the current evidence.",
    replay: "The same local recommendation already exists or was completed today; no duplicate task was created.",
    covered_by_active_task: "An existing active local task already covers this action; no duplicate was created.",
  };
  return <Card className="service-state" role="status"><Sparkles size={23} /><div><strong>Recommendation checked</strong><p>{messages[outcome]}</p></div></Card>;
}

export function LearningFeedPage() {
  const { tasks: demoTasks, updateTask, setInspector } = useAppStore();
  const core = useLearningCore();
  const [status, setStatus] = useState<TaskStatus>("today");
  const [course, setCourse] = useState("All courses");
  const [requestedLiveCourseId, setRequestedLiveCourseId] = useState<string | null>(null);
  const isDemo = core.status === "demo";
  const liveCourses = useMemo(() => core.demoState?.courses ?? [], [core.demoState?.courses]);
  const liveCourseId = liveCourses.some((item) => item.id === requestedLiveCourseId)
    ? requestedLiveCourseId
    : liveCourses[0]?.id ?? null;
  const liveFeed = useAutonomousLearningFeed({
    client: core.client,
    courseId: liveCourseId,
    enabled: !isDemo && core.status === "healthy" && !core.demoStateError && core.demoState !== undefined,
    connectionGeneration: core.connectionGeneration,
  });
  const tasks = useMemo(() => isDemo ? demoTasks : core.demoState ? mapDemoStateTasks(core.demoState) : [], [core.demoState, demoTasks, isDemo]);
  const filtered = useMemo(() => tasks.filter((task) => task.status === status && (course === "All courses" || task.course === course)), [course, status, tasks]);
  const courses = ["All courses", ...Array.from(new Set(tasks.map((task) => task.course)))];
  const showBaselineFeed = isDemo || (!isDemo && core.demoState !== undefined && (liveFeed.snapshotPending || liveFeed.snapshotError));
  const retry = () => { void core.retry(); };

  const inspect = (task: LearningTask) => setInspector({
    eyebrow: "Agent rationale", title: task.title, body: task.reason,
    meta: [`Due ${task.due}`, `${task.durationMinutes} minute estimate`, `Concepts: ${task.concepts.join(", ") || "None linked"}`],
  });

  const inspectLive = (task: LearningFeedTask) => setInspector({
    eyebrow: "Persisted learning rationale", title: task.title, body: task.reason,
    meta: [`Due ${new Date(task.due_at).toLocaleString()}`, `${task.estimated_minutes} minute estimate`, `Priority ${task.priority_score.toFixed(2)}`],
  });

  return (
    <Page title="Learning Feed" description="Local tasks and deterministic next actions, based only on stored learning evidence." actions={isDemo ? <Button disabled><CalendarClock size={15} />Planning unavailable</Button> : liveFeed.recommendation.pending ? <Button onClick={liveFeed.cancelRecommendation}><Square size={15} />Cancel recommendation</Button> : <Button className="primary" disabled={liveCourseId === null || core.status !== "healthy" || liveFeed.recommendation.error !== null || liveFeed.recommendation.cancelled} onClick={() => { void liveFeed.createRecommendation(); }}><Sparkles size={15} />Plan next local action</Button>}>
      {isDemo && <div className="demo-disclosure"><Badge tone="warning">Browser Demo</Badge><span>Showing local sample tasks. No learning-core requests are made in the browser.</span></div>}
      {!isDemo && core.status !== "healthy" && <FeedServiceState status={core.status} errorKind={core.errorKind} serviceMessage={core.serviceMessage} retryError={core.retryError} onRetry={retry} />}
      {!isDemo && core.status === "healthy" && core.demoStatePending && <FeedServiceState status="health_checking" onRetry={retry} />}
      {!isDemo && core.status === "healthy" && core.demoStateError && <FeedDataError onRetry={retry} />}
      {!isDemo && core.status === "healthy" && core.demoState && !core.demoStateError && liveCourses.length === 0 && <Card><EmptyState icon={<Check size={28} />} title="No local courses yet" description="Create a course and add an indexed source before Keen can inspect learning evidence. No recommendation request was sent." /></Card>}
      {!isDemo && core.status === "healthy" && core.demoState && !core.demoStateError && liveCourses.length > 0 && <>
        <div className="filter-bar"><label className="select-control"><Filter size={14} /><select aria-label="Select course for local learning feed" value={liveCourseId ?? ""} onChange={(event) => setRequestedLiveCourseId(event.target.value)}>{liveCourses.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label></div>
        {liveFeed.snapshotPending && <Card className="service-state" role="status"><LoaderCircle className="spin" size={23} /><div><strong>Loading local learning evidence</strong><p>Keen is reading persisted tasks, reviews, sessions, and mastery state. No recommendation is being created.</p></div></Card>}
        {liveFeed.snapshotError && <Card className="service-state" role="alert"><AlertCircle size={23} /><div><strong>Learning feed could not be validated</strong><p>The local service did not return a valid learning snapshot. No recommendation or task was created. Retry the feed after the service recovers.</p></div><Button onClick={() => { void liveFeed.refetchSnapshot(); }}>Retry feed</Button></Card>}
        {liveFeed.recommendation.cancelled && <Card className="service-state" role="status"><Square size={23} /><div><strong>Recommendation request cancelled</strong><p>Keen ignored the unfinished response. Refresh the feed before retrying if you need to confirm local tasks.</p></div><Button onClick={() => { void liveFeed.reconcileRecommendation(); }}>Refresh feed</Button></Card>}
        {liveFeed.recommendation.error && <Card className="service-state" role="alert"><AlertCircle size={23} /><div><strong>{liveFeed.recommendation.error === "service_unavailable" ? "Local recommendation service is unavailable" : "Recommendation could not be confirmed"}</strong><p>{liveFeed.recommendation.error === "service_unavailable" ? "Keen could not confirm whether a task was saved. Restore the local service and refresh the feed before retrying." : "Keen could not confirm whether a task was saved. Refresh the feed before retrying to avoid duplicates."}</p></div><Button onClick={() => { void liveFeed.reconcileRecommendation(); }}>Refresh feed</Button></Card>}
        {liveFeed.recommendation.result && <RecommendationNotice outcome={liveFeed.recommendation.result.outcome} />}
        {liveFeed.snapshot && <div className="timeline">
          {liveFeed.snapshot.pending_tasks.map((task) => <LiveTaskCard key={task.id} task={task} candidate={task.id === liveFeed.recommendation.result?.task?.id ? liveFeed.recommendation.result.candidate : null} onInspect={() => inspectLive(task)} />)}
          {liveFeed.snapshot.pending_tasks.length === 0 && <Card><EmptyState icon={<Check size={28} />} title="No active local tasks" description={liveFeed.snapshot.candidates.length > 0 ? "Keen found an eligible next action, but no task has been created. Use “Plan next local action” to create one local task." : "Keen found no eligible action in the persisted learning evidence."} /></Card>}
        </div>}
      </>}
      {showBaselineFeed && <>
        {!isDemo && <p className="feed-candidate-note">Showing the existing authenticated task readout while the new local recommendation snapshot is unavailable.</p>}
        <div className="filter-bar"><Segmented value={status} options={["today", "upcoming", "overdue", "completed"]} onChange={setStatus} /><label className="select-control"><Filter size={14} /><select aria-label="Filter by course" value={course} onChange={(event) => setCourse(event.target.value)}>{courses.map((item) => <option key={item}>{item}</option>)}</select></label></div>
        <div className="timeline">
          {filtered.map((task) => <TaskCard key={task.id} task={task} isDemo={isDemo} onUpdate={(next) => updateTask(task.id, next)} onInspect={() => inspect(task)} />)}
          {filtered.length === 0 && <Card><EmptyState icon={<Check size={28} />} title={`No ${labels[status].toLowerCase()} tasks`} description={course === "All courses" ? "Your schedule is clear in this section." : `No tasks for ${course} in this section.`} action={<Button onClick={() => setCourse("All courses")}>Clear filter</Button>} /></Card>}
        </div>
      </>}
    </Page>
  );
}
