import { useState } from "react";
import { Calendar, Check, ChevronLeft, ChevronRight, Clock3, FileUp, GripVertical, WandSparkles } from "lucide-react";
import { Badge, Button, Card } from "@keen/ui";
import { Page } from "../../components/Page";

const days = ["Mon 13", "Tue 14", "Wed 15", "Thu 16", "Fri 17", "Sat 18", "Sun 19"];
const initial = [
  { id: 1, day: 2, time: "9:00 AM", title: "Eigenvectors review", course: "Linear Algebra", duration: 25, done: false },
  { id: 2, day: 2, time: "2:00 PM", title: "Cellular respiration recall", course: "Biology 101", duration: 15, done: false },
  { id: 3, day: 3, time: "10:30 AM", title: "Confidence interval practice", course: "Statistics", duration: 30, done: false },
  { id: 4, day: 4, time: "9:30 AM", title: "Optimization checkpoint", course: "Machine Learning", duration: 20, done: false },
];

export function PlannerPage() {
  const [tasks, setTasks] = useState(initial);
  const [confirmCalendar, setConfirmCalendar] = useState(false);
  const toggle = (id: number) => setTasks((items) => items.map((x) => x.id === id ? { ...x, done: !x.done } : x));
  return (
    <Page title="Study Planner" description="A deterministic demo schedule. Syllabus parsing and calendar writes are not connected." actions={<><Button disabled><FileUp size={14} />Import unavailable</Button><Button className="primary" onClick={() => setConfirmCalendar(true)}><Calendar size={14} />Preview calendar confirmation</Button></>}>
      <Card className="planner-summary"><div><WandSparkles size={18} /><span><strong>This week's plan</strong><small>4 h 10 min across 9 sessions</small></span></div><div><small>Exam countdown</small><strong>Linear Algebra · 4 days</strong></div><div><small>Available today</small><strong>1 h 20 min</strong></div></Card>
      <div className="calendar-toolbar"><Button disabled><ChevronLeft size={14} /></Button><strong>July 13–19, 2026</strong><Button disabled><ChevronRight size={14} /></Button><span /><Badge tone="warning">Deterministic demo plan</Badge></div>
      <div className="week-grid">{days.map((day, dayIndex) => <div className={`day-column ${dayIndex === 2 ? "today" : ""}`} key={day}><header><span>{day.split(" ")[0]}</span><strong>{day.split(" ")[1]}</strong>{dayIndex === 2 && <i>Sample today</i>}</header><div className="day-body">{tasks.filter((t) => t.day === dayIndex).map((task) => <Card className={`plan-task ${task.done ? "done" : ""}`} key={task.id}><div><GripVertical size={12} /><Badge>{task.course}</Badge></div><strong>{task.title}</strong><span><Clock3 size={11} />{task.time} · {task.duration}m</span><button onClick={() => toggle(task.id)} aria-label={task.done ? "Mark demo task incomplete" : "Mark demo task complete"}>{task.done ? <Check size={13} /> : "Demo done"}</button></Card>)}{!tasks.some((t) => t.day === dayIndex) && <button className="add-session" disabled>+ Add unavailable</button>}</div></div>)}</div>
      <div className="planner-note"><WandSparkles size={15} /><p><strong>Illustrative rationale:</strong> This fixed example places eigenvectors first; no planner, mastery model, or spaced-repetition scheduler produced it.</p><Button disabled>Rationale details unavailable</Button></div>
      {confirmCalendar && <div className="modal-backdrop" onMouseDown={() => setConfirmCalendar(false)}><Card className="confirm-dialog" onMouseDown={(e) => e.stopPropagation()}><Calendar size={24} /><h2>Calendar confirmation preview</h2><p>No event can be written in this build. When integration is available, this Level 3 action will require confirmation here.</p><div><Button onClick={() => setConfirmCalendar(false)}>Close</Button><Button className="primary" disabled>Calendar integration pending</Button></div></Card></div>}
    </Page>
  );
}
