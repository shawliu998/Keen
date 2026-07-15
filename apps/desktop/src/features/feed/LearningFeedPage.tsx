import { useMemo, useState } from "react";
import { AlertCircle, CalendarClock, Check, ChevronRight, Clock3, Filter, Lightbulb, RotateCcw } from "lucide-react";
import { Badge, Button, Card, EmptyState, Progress } from "@keen/ui";
import type { TaskStatus } from "@keen/domain";
import { Page, Segmented } from "../../components/Page";
import { useAppStore } from "../../state/appStore";

const labels: Record<TaskStatus, string> = { today: "Today", upcoming: "Upcoming", overdue: "Overdue", completed: "Completed" };

export function LearningFeedPage() {
  const { tasks, updateTask, setInspector } = useAppStore();
  const [status, setStatus] = useState<TaskStatus>("today");
  const [course, setCourse] = useState("All courses");
  const filtered = useMemo(() => tasks.filter((task) => task.status === status && (course === "All courses" || task.course === course)), [tasks, status, course]);
  const courses = ["All courses", ...Array.from(new Set(tasks.map((t) => t.course)))];
  return (
    <Page title="Learning Feed" description="A daily plan that adapts to what you know, what is due, and what unlocks your next step." actions={<Button><CalendarClock size={15} />Plan this week</Button>}>
      <div className="filter-bar"><Segmented value={status} options={["today", "upcoming", "overdue", "completed"]} onChange={setStatus} /><label className="select-control"><Filter size={14} /><select aria-label="Filter by course" value={course} onChange={(e) => setCourse(e.target.value)}>{courses.map((c) => <option key={c}>{c}</option>)}</select></label></div>
      <div className="timeline">{filtered.map((task) => <Card className="task-card" key={task.id}>
        <div className={`timeline-marker marker-${task.status}`}>{task.status === "completed" ? <Check size={14} /> : task.status === "overdue" ? <AlertCircle size={14} /> : <Clock3 size={14} />}</div>
        <div className="task-main"><div className="task-title-row"><div><Badge tone={task.status === "overdue" ? "danger" : task.status === "completed" ? "success" : "accent"}>{labels[task.status]}</Badge><h3>{task.title}</h3></div><span>{task.due}</span></div>
          <p className="reason"><Lightbulb size={14} />{task.reason}</p><div className="task-meta"><span>{task.course}</span><span>{task.durationMinutes} min</span>{task.concepts.map((c) => <Badge key={c}>{c}</Badge>)}</div>
          <div className="task-bottom"><div className="task-mastery"><span>Current mastery</span><Progress value={task.mastery} /><strong>{task.mastery}%</strong></div><div className="task-actions">
            <button onClick={() => setInspector({ eyebrow: "Agent rationale", title: task.title, body: task.reason, meta: [`Due ${task.due}`, `${task.durationMinutes} minute estimate`, `Concepts: ${task.concepts.join(", ")}`] })}>Why this?<ChevronRight size={13} /></button>
            {status !== "completed" && <><Button onClick={() => updateTask(task.id, "upcoming")}><RotateCcw size={14} />Snooze</Button><Button className="primary" onClick={() => updateTask(task.id, "completed")}>{status === "today" ? "Start" : "Complete"}</Button></>}
          </div></div>
        </div></Card>)}
        {filtered.length === 0 && <Card><EmptyState icon={<Check size={28} />} title={`No ${labels[status].toLowerCase()} tasks`} description={course === "All courses" ? "Your schedule is clear in this section." : `No tasks for ${course} in this section.`} action={<Button onClick={() => setCourse("All courses")}>Clear filter</Button>} /></Card>}
      </div>
    </Page>
  );
}
