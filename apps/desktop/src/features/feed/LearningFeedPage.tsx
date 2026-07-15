import { useMemo, useState } from "react";
import {
  AlertCircle, CalendarClock, Check, ChevronRight, Clock3, Filter,
  Lightbulb, LoaderCircle, RotateCcw, ServerOff,
} from "lucide-react";
import { Badge, Button, Card, EmptyState, Progress } from "@keen/ui";
import type { LearningTask, TaskStatus } from "@keen/domain";
import { Page, Segmented } from "../../components/Page";
import { useLearningCore, type LearningCoreStatus } from "../../services/LearningCoreProvider";
import { useAppStore } from "../../state/appStore";
import { mapDemoStateTasks } from "./liveTasks";

const labels: Record<TaskStatus, string> = {
  today: "Today", upcoming: "Upcoming", overdue: "Overdue", completed: "Completed",
};

function FeedServiceState({ status, onRetry }: { status: LearningCoreStatus; onRetry: () => void }) {
  const starting = status === "starting";
  return (
    <Card className="service-state" role={starting ? "status" : "alert"}>
      {starting ? <LoaderCircle className="spin" size={23} /> : <ServerOff size={23} />}
      <div>
        <strong>{starting ? "Learning core is starting" : status === "unavailable" ? "Learning core is unavailable" : "Learning core connection failed"}</strong>
        <p>{starting
          ? "Keen is completing an authenticated local health check. Live tasks and mastery will appear when it succeeds; no demo records are being substituted."
          : "Live tasks and mastery could not be loaded. Your stored data was not changed, and Keen did not substitute demo records. Retrying is safe; restart Keen if the problem continues."}</p>
      </div>
      {!starting && <Button onClick={onRetry}>Retry connection</Button>}
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

export function LearningFeedPage() {
  const { tasks: demoTasks, updateTask, setInspector } = useAppStore();
  const core = useLearningCore();
  const [status, setStatus] = useState<TaskStatus>("today");
  const [course, setCourse] = useState("All courses");
  const isDemo = core.status === "demo";
  const tasks = useMemo(() => isDemo ? demoTasks : core.demoState ? mapDemoStateTasks(core.demoState) : [], [core.demoState, demoTasks, isDemo]);
  const filtered = useMemo(() => tasks.filter((task) => task.status === status && (course === "All courses" || task.course === course)), [course, status, tasks]);
  const courses = ["All courses", ...Array.from(new Set(tasks.map((task) => task.course)))];
  const retry = () => { void core.retry(); };

  const inspect = (task: LearningTask) => setInspector({
    eyebrow: "Agent rationale", title: task.title, body: task.reason,
    meta: [`Due ${task.due}`, `${task.durationMinutes} minute estimate`, `Concepts: ${task.concepts.join(", ") || "None linked"}`],
  });

  return (
    <Page title="Learning Feed" description="Live local task/mastery readout when connected. Planning and task mutation are not connected in this milestone." actions={<Button disabled><CalendarClock size={15} />Planning unavailable</Button>}>
      {isDemo && <div className="demo-disclosure"><Badge tone="warning">Browser Demo</Badge><span>Showing local sample tasks. No learning-core requests are made in the browser.</span></div>}
      {!isDemo && core.status !== "healthy" && <FeedServiceState status={core.status} onRetry={retry} />}
      {!isDemo && core.status === "healthy" && core.demoStatePending && <FeedServiceState status="starting" onRetry={retry} />}
      {!isDemo && core.status === "healthy" && core.demoStateError && <FeedDataError onRetry={retry} />}
      {(isDemo || core.demoState) && !core.demoStateError && <>
        <div className="filter-bar"><Segmented value={status} options={["today", "upcoming", "overdue", "completed"]} onChange={setStatus} /><label className="select-control"><Filter size={14} /><select aria-label="Filter by course" value={course} onChange={(event) => setCourse(event.target.value)}>{courses.map((item) => <option key={item}>{item}</option>)}</select></label></div>
        <div className="timeline">
          {filtered.map((task) => <TaskCard key={task.id} task={task} isDemo={isDemo} onUpdate={(next) => updateTask(task.id, next)} onInspect={() => inspect(task)} />)}
          {filtered.length === 0 && <Card><EmptyState icon={<Check size={28} />} title={`No ${labels[status].toLowerCase()} tasks`} description={course === "All courses" ? "Your schedule is clear in this section." : `No tasks for ${course} in this section.`} action={<Button onClick={() => setCourse("All courses")}>Clear filter</Button>} /></Card>}
        </div>
      </>}
    </Page>
  );
}
