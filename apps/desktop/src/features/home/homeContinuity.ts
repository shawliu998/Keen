import type {
  AutonomousStudySession,
  LearningActionCandidate,
  LearningFeedTask,
  LearningSnapshot,
  ReviewItem,
} from "@keen/api-client";

export type HomeResumeCandidate = {
  courseId: string;
  candidate: LearningActionCandidate;
};

export function selectHomeNextTask(
  snapshots: readonly Pick<LearningSnapshot, "pending_tasks">[],
): LearningFeedTask | null {
  return snapshots
    .flatMap((snapshot) => snapshot.pending_tasks)
    .sort((left, right) => (
      right.priority_score - left.priority_score
      || Date.parse(left.due_at) - Date.parse(right.due_at)
      || left.id.localeCompare(right.id)
    ))[0] ?? null;
}

export function selectDueReview(items: readonly ReviewItem[]): ReviewItem | null {
  return [...items].sort((left, right) => (
    Date.parse(left.due_at) - Date.parse(right.due_at)
    || left.id.localeCompare(right.id)
  ))[0] ?? null;
}

export function selectHomeResumeCandidate(
  snapshots: readonly Pick<LearningSnapshot, "course_id" | "candidates">[],
): HomeResumeCandidate | null {
  return snapshots
    .flatMap((snapshot) => snapshot.candidates
      .filter((candidate) => (
        candidate.action === "resume_study_session"
        && candidate.target_type === "study_session"
      ))
      .map((candidate) => ({ courseId: snapshot.course_id, candidate })))
    .sort((left, right) => (
      left.candidate.priority_tier - right.candidate.priority_tier
      || right.candidate.priority_score - left.candidate.priority_score
      || left.courseId.localeCompare(right.courseId)
      || left.candidate.target_id.localeCompare(right.candidate.target_id)
    ))[0] ?? null;
}

export function findDueReviewTask(
  review: ReviewItem | null,
  snapshots: readonly Pick<LearningSnapshot, "pending_tasks">[],
): LearningFeedTask | null {
  if (review === null) return null;
  const matches = snapshots
    .flatMap((snapshot) => snapshot.pending_tasks)
    .filter((task) => (
      task.status !== "completed"
      && task.completed_at === null
      && task.course_id === review.course_id
      && task.concept_id === review.concept_id
      && task.source_type === "review"
      && task.source_id === review.id
    ));
  return matches.length === 1 ? matches[0] ?? null : null;
}

export function findTaskSession(
  task: LearningFeedTask | null,
  sessions: readonly AutonomousStudySession[],
): AutonomousStudySession | null {
  if (task === null) return null;
  return sessions.find((session) => (
    session.originating_task_id === task.id
    || (task.source_type === "study_session" && task.source_id === session.id)
  )) ?? null;
}

export function findResumeSession(
  value: HomeResumeCandidate | null,
  sessions: readonly AutonomousStudySession[],
): AutonomousStudySession | null {
  if (
    value === null
    || value.candidate.action !== "resume_study_session"
    || value.candidate.target_type !== "study_session"
  ) return null;
  const matches = sessions.filter((session) => (
    session.id === value.candidate.target_id
    && session.course_id === value.courseId
    && !["completed", "cancelled", "failed"].includes(session.status)
  ));
  return matches.length === 1 ? matches[0] ?? null : null;
}

export function studySessionAction(status: AutonomousStudySession["status"]): string {
  const actions: Record<AutonomousStudySession["status"], string> = {
    draft: "Start session", goal_confirmation: "Start session", diagnosing: "Continue reflection",
    planning: "Continue session", studying: "Continue reading", checkpoint: "Continue checkpoint",
    active_recall: "Continue recall", practicing: "Continue practice", summarizing: "Finish and schedule review",
    review_scheduling: "Finish and schedule review", paused: "Resume session", completed: "View record",
    cancelled: "View record", failed: "Review session",
  };
  return actions[status];
}
