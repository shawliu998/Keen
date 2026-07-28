import type { LearningActionCandidate, LearningFeedTask, ReviewItem } from "@keen/api-client";
import {
  findDueReviewTask,
  findResumeSession,
  findTaskSession,
  selectDueReview,
  selectHomeNextTask,
  selectHomeResumeCandidate,
  studySessionAction,
} from "../src/features/home/homeContinuity";

const baseTask: LearningFeedTask = {
  id: "task-a",
  course_id: "course-a",
  concept_id: null,
  title: "Continue calculus",
  reason: "Saved work",
  due_at: "2026-07-23T09:00:00.000Z",
  estimated_minutes: 10,
  status: "upcoming",
  source_type: "study_session",
  source_id: "session-a",
  priority_score: 0.7,
  recommended_reason: "Resume the saved session.",
  scheduled_for: null,
  created_at: "2026-07-21T09:00:00.000Z",
  updated_at: "2026-07-21T09:00:00.000Z",
  completed_at: null,
};

describe("Home learning continuity", () => {
  it("selects the earliest due review with a stable identity tie-break", () => {
    const base: Omit<ReviewItem, "id" | "due_at"> = {
      course_id: "course-1", course_title: "Calculus", concept_id: "concept-1", concept_name: "Limits",
      item_type: "free_recall", prompt: "Explain limits", expected_answer: "", source_type: "study_session",
      source_id: "session-1", state: "learning", scheduler: "fsrs", scheduler_version: "1",
      revision: 0, repetitions: 0, lapses: 0,
    };
    expect(selectDueReview([
      { ...base, id: "review-b", due_at: "2026-07-22T09:00:00.000Z" },
      { ...base, id: "review-a", due_at: "2026-07-22T09:00:00.000Z" },
      { ...base, id: "review-later", due_at: "2026-07-22T10:00:00.000Z" },
    ])?.id).toBe("review-a");
  });

  it("finds one exact active review task and fails closed for ambiguous or mismatched evidence", () => {
    const review: ReviewItem = {
      id: "review-1", course_id: "course-a", course_title: "Calculus", concept_id: "concept-1",
      concept_name: "Limits", item_type: "free_recall", prompt: "Explain limits", expected_answer: "",
      source_type: "study_session", source_id: "session-1", due_at: "2026-07-22T09:00:00.000Z",
      state: "learning", scheduler: "fsrs", scheduler_version: "1", revision: 0, repetitions: 0, lapses: 0,
    };
    const exact = {
      ...baseTask,
      id: "task-review-1",
      concept_id: review.concept_id,
      source_type: "review",
      source_id: review.id,
    };
    expect(findDueReviewTask(review, [{ pending_tasks: [baseTask, exact] }])).toEqual(exact);
    expect(findDueReviewTask(review, [{ pending_tasks: [{ ...exact, concept_id: "concept-other" }] }])).toBeNull();
    expect(findDueReviewTask(review, [{ pending_tasks: [{ ...exact, source_id: "review-other" }] }])).toBeNull();
    expect(findDueReviewTask(review, [{ pending_tasks: [exact, { ...exact, id: "task-review-duplicate" }] }])).toBeNull();
  });
  it("selects the highest-priority real task across course snapshots", () => {
    const secondCourseTask = { ...baseTask, id: "task-b", course_id: "course-b", title: "Review eigenvectors", priority_score: 0.9 };
    expect(selectHomeNextTask([{ pending_tasks: [baseTask] }, { pending_tasks: [secondCourseTask] }])).toEqual(secondCourseTask);
  });

  it("uses due time and stable identity to break equal-priority ties", () => {
    const earlier = { ...baseTask, id: "task-z", course_id: "course-b", due_at: "2026-07-22T09:00:00.000Z" };
    const sameTimeEarlierId = { ...earlier, id: "task-b" };
    expect(selectHomeNextTask([{ pending_tasks: [baseTask, earlier, sameTimeEarlierId] }])?.id).toBe("task-b");
  });

  it("returns no invented next action for empty snapshots", () => {
    expect(selectHomeNextTask([{ pending_tasks: [] }])).toBeNull();
  });

  it("restores the exact session linked by its originating task", () => {
    const session = {
      id: "session-b", course_id: "course-a", originating_task_id: "task-a", title: "Limits",
      mode: "study", goal: "Explain limits without notes", estimated_minutes: 20, status: "practicing",
      progress: 0.5, revision: 3, created_at: "2026-07-21T09:00:00.000Z",
      updated_at: "2026-07-22T09:00:00.000Z", started_at: "2026-07-21T09:01:00.000Z",
    } as const;
    expect(findTaskSession(baseTask, [session])).toEqual(session);
    expect(studySessionAction(session.status)).toBe("Continue practice");
    expect(studySessionAction("summarizing")).toBe("Finish and schedule review");
    expect(findTaskSession({ ...baseTask, id: "other-task" }, [session])).toBeNull();
  });

  it("restores one exact incomplete session when no persisted task exists", () => {
    const candidate: LearningActionCandidate = {
      id: "session:session-b",
      action: "resume_study_session",
      target_type: "study_session",
      target_id: "session-b",
      concept_id: null,
      component: "study_sessions",
      priority_tier: 2,
      estimated_minutes: 20,
      fits_available_minutes: true,
      priority_score: 0.8,
      priority_unclamped_score: 0.8,
      priority_algorithm_version: "feed-priority-v1",
      priority_components: [],
      priority_explanation: [],
      why: "Study session is incomplete.",
    };
    const selected = selectHomeResumeCandidate([
      { course_id: "course-b", candidates: [{ ...candidate, target_id: "session-z", priority_score: 0.7 }] },
      { course_id: "course-a", candidates: [candidate] },
    ]);
    expect(selected).toEqual({ courseId: "course-a", candidate });

    const session = {
      id: "session-b", course_id: "course-a", originating_task_id: null, title: "Limits",
      mode: "study", goal: "Explain limits without notes", estimated_minutes: 20, status: "paused",
      resume_from_status: "practicing", progress: 0.5, revision: 3,
      created_at: "2026-07-21T09:00:00.000Z", updated_at: "2026-07-22T09:00:00.000Z",
      started_at: "2026-07-21T09:01:00.000Z",
    } as const;
    expect(findResumeSession(selected, [session])).toEqual(session);
    expect(findResumeSession(selected, [{ ...session, status: "completed", resume_from_status: null }])).toBeNull();
    expect(findResumeSession(selected, [{ ...session, course_id: "course-other" }])).toBeNull();
  });
});
