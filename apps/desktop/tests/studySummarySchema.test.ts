import { describe, expect, it } from "vitest";
import {
  studySummaryFinalizeResponseSchema,
  studySummaryReadResponseSchema,
  studySummaryRequestSchema,
} from "@keen/api-client";

const time = "2026-07-18T10:00:00+00:00";
const summarySession = {
  id: "session-1", course_id: "course-1", status: "summarizing" as const, revision: 5, progress: 0.8, estimated_minutes: 20,
  created_at: time, updated_at: time, started_at: time, finished_at: null,
};
const summary = { active_recall_correct: true, practice_correct: false, practice_score: 0, practice_max_score: 1, task_completed: false, remaining_units: 0 };
const ready = { outcome: "ready" as const, course_id: "course-1", session: summarySession, summary, review: null };
const completed = {
  ...ready,
  outcome: "completed" as const,
  session: { ...summarySession, status: "completed" as const, progress: 1, revision: 6, finished_at: time },
  summary: { ...summary, task_completed: true },
  review: { due_at: time, scheduler: "fsrs", scheduler_version: "fsrs-6.3.1-keen-v1", state: "new" },
};

describe("study-summary API schemas", () => {
  it("accepts bounded learner-safe summary states and exact finalize outcomes", () => {
    expect(studySummaryReadResponseSchema.safeParse(ready).success).toBe(true);
    expect(studySummaryReadResponseSchema.safeParse(completed).success).toBe(true);
    expect(studySummaryReadResponseSchema.safeParse({ ...ready, outcome: "cancelled", session: { ...summarySession, status: "cancelled" as const }, summary: null }).success).toBe(true);
    expect(studySummaryFinalizeResponseSchema.safeParse({ ...completed, outcome: "applied" }).success).toBe(true);
    expect(studySummaryFinalizeResponseSchema.safeParse({ ...completed, outcome: "replayed" }).success).toBe(true);
  });

  it("rejects hidden lineage, foreign scope, impossible review state, and malformed commands", () => {
    expect(studySummaryReadResponseSchema.safeParse({ ...ready, concept_id: "private" }).success).toBe(false);
    expect(studySummaryReadResponseSchema.safeParse({ ...ready, session: { ...summarySession, course_id: "course-2" } }).success).toBe(false);
    expect(studySummaryReadResponseSchema.safeParse({ ...completed, review: null }).success).toBe(false);
    expect(studySummaryReadResponseSchema.safeParse({ ...ready, summary: { ...summary, practice_correct: true } }).success).toBe(false);
    const request = { course_id: "course-1", expected_revision: 5, idempotency_key: "study-summary-finalize-001" };
    expect(studySummaryRequestSchema.safeParse(request).success).toBe(true);
    expect(studySummaryRequestSchema.safeParse({ ...request, review_id: "private" }).success).toBe(false);
  });
});
