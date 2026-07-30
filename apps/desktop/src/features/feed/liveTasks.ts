import type { DemoState, StudyTask } from "@keen/api-client";
import type { LearningTask, TaskStatus } from "@keen/domain";

function taskStatus(task: StudyTask, now: Date): TaskStatus {
  if (task.status === "completed" || task.status === "overdue") return task.status;
  const due = new Date(task.due_at);
  if (due.getTime() < now.getTime()) return "overdue";
  return due.getFullYear() === now.getFullYear()
    && due.getMonth() === now.getMonth()
    && due.getDate() === now.getDate()
    ? "today"
    : "upcoming";
}

function formatDue(dueAt: string, now: Date): string {
  const due = new Date(dueAt);
  const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(due);
  const todayOrdinal = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const dueOrdinal = Date.UTC(due.getFullYear(), due.getMonth(), due.getDate());
  const dayDifference = Math.round((dueOrdinal - todayOrdinal) / 86_400_000);
  if (dayDifference === 0) return `Today, ${time}`;
  if (dayDifference === 1) return `Tomorrow, ${time}`;
  if (dayDifference === -1) return `Yesterday, ${time}`;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(due);
}

export function mapDemoStateTasks(state: DemoState, now = new Date()): LearningTask[] {
  const courseTitles = new Map(state.courses.map((course) => [course.id, course.title]));
  const mastery = new Map(state.mastery.map((item) => [item.concept_id, item]));
  return state.tasks.map((task) => {
    const concept = task.concept_id ? mastery.get(task.concept_id) : undefined;
    return {
      id: task.id,
      title: task.title,
      course: task.course_title ?? courseTitles.get(task.course_id) ?? "Unknown course",
      reason: task.reason,
      due: formatDue(task.due_at, now),
      durationMinutes: task.estimated_minutes,
      concepts: concept ? [concept.concept_name] : [],
      mastery: Math.round((concept?.probability ?? 0) * 100),
      status: taskStatus(task, now),
    };
  });
}
