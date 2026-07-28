import type { DemoState, StudyTask } from "@keen/api-client";
import { mapDemoStateTasks } from "../src/features/feed/liveTasks";

const course = {
  id: "course-1",
  title: "Course",
  description: "",
  created_at: "2026-07-01T00:00:00+00:00",
  concept_count: 0,
  average_mastery: null,
};

function stateWith(task: StudyTask): DemoState {
  return { courses: [course], tasks: [task], mastery: [] };
}

function task(dueAt: Date): StudyTask {
  return {
    id: "task-1",
    course_id: course.id,
    course_title: course.title,
    title: "Review",
    reason: "Due-date mapping test",
    due_at: dueAt.toISOString(),
    estimated_minutes: 10,
    status: "upcoming",
    concept_id: null,
    created_at: "2026-07-01T00:00:00+00:00",
    updated_at: "2026-07-01T00:00:00+00:00",
  };
}

describe("live task scheduling state", () => {
  it("derives overdue when an upcoming task is already past due", () => {
    const now = new Date(2026, 6, 16, 12, 0);
    const mapped = mapDemoStateTasks(stateWith(task(new Date(2026, 6, 16, 11, 59))), now);
    expect(mapped[0].status).toBe("overdue");
  });

  it("maps a later task on the same local date to today", () => {
    const now = new Date(2026, 6, 16, 12, 0);
    const mapped = mapDemoStateTasks(stateWith(task(new Date(2026, 6, 16, 17, 0))), now);
    expect(mapped[0].status).toBe("today");
    expect(mapped[0].due).toMatch(/^Today,/);
  });

  it("uses calendar-day arithmetic across daylight-saving transitions", () => {
    const now = new Date(2026, 2, 7, 23, 30);
    const mapped = mapDemoStateTasks(stateWith(task(new Date(2026, 2, 8, 23, 30))), now);
    expect(mapped[0].due).toMatch(/^Tomorrow,/);
  });
});
