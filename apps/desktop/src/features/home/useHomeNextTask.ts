import { useQueries, useQuery } from "@tanstack/react-query";
import type { LearningCoreClient } from "@keen/api-client";
import { dueReviewsQueryKey } from "../learningContinuityQueries";
import {
  findDueReviewTask,
  findResumeSession,
  findTaskSession,
  selectDueReview,
  selectHomeNextTask,
  selectHomeResumeCandidate,
} from "./homeContinuity";

export function useHomeNextTask({
  client,
  courseIds,
  enabled,
  connectionGeneration,
}: {
  client: LearningCoreClient | null;
  courseIds: readonly string[];
  enabled: boolean;
  connectionGeneration: number;
}) {
  const queries = useQueries({
    queries: courseIds.map((courseId) => ({
      queryKey: ["learning-core", "learning-snapshot", connectionGeneration, courseId, 20] as const,
      queryFn: ({ signal }: { signal: AbortSignal }) => {
        if (!client) throw new Error("A connected learning core is required before loading saved work.");
        return client.learningSnapshot({ courseId, availableMinutes: 20 }, { signal });
      },
      enabled: enabled && client !== null,
      retry: 1,
      staleTime: 10_000,
      refetchOnWindowFocus: false,
    })),
  });
  const unavailable = !enabled || client === null;
  const pending = enabled && courseIds.length > 0 && queries.some((query) => query.isFetching);
  const error = enabled ? queries.find((query) => query.error)?.error ?? null : null;
  const reviewQuery = useQuery({
    queryKey: dueReviewsQueryKey(connectionGeneration),
    queryFn: ({ signal }) => {
      if (!client) throw new Error("A connected learning core is required before loading due reviews.");
      return client.listDueReviews({ limit: 50 }, { signal });
    },
    enabled: enabled && client !== null,
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const reviewUnavailable = unavailable || reviewQuery.isFetching || reviewQuery.error !== null;
  const snapshots = queries.flatMap((query) => query.data ? [query.data] : []);
  const nextReview = unavailable || reviewUnavailable ? null : selectDueReview(reviewQuery.data?.items ?? []);
  const nextTask = pending || error || reviewUnavailable
    ? null
    : selectHomeNextTask(snapshots);
  const nextReviewTask = pending || error || reviewUnavailable
    ? null
    : findDueReviewTask(nextReview, snapshots);
  const resumeCandidate = pending || error || reviewUnavailable || nextReview !== null || nextTask !== null
    ? null
    : selectHomeResumeCandidate(snapshots);
  const sessionCourseId = nextReview === null
    ? nextTask?.course_id ?? resumeCandidate?.courseId ?? null
    : null;
  const sessionQuery = useQuery({
    queryKey: ["learning-core", "study-session-history", connectionGeneration, sessionCourseId ?? "none"],
    queryFn: ({ signal }) => {
      if (!client || !sessionCourseId) throw new Error("A saved session scope is required before restoring study work.");
      return client.listStudySessions(sessionCourseId, { signal });
    },
    enabled: enabled && client !== null && sessionCourseId !== null,
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const nextSession = unavailable || reviewUnavailable
    ? null
    : findTaskSession(nextTask, sessionQuery.data?.sessions ?? [])
      ?? findResumeSession(resumeCandidate, sessionQuery.data?.sessions ?? []);
  const resumeSessionPending = resumeCandidate !== null && sessionQuery.isPending;
  const resumeSessionError = resumeCandidate !== null
    ? sessionQuery.error
      ?? (sessionQuery.data && nextSession === null
        ? new Error("The saved resume candidate did not resolve to one current incomplete session.")
        : null)
    : null;

  return {
    nextTask,
    nextSession,
    nextReview,
    nextReviewTask,
    pending: pending || (enabled && reviewQuery.isFetching) || resumeSessionPending,
    error: enabled ? error ?? reviewQuery.error ?? resumeSessionError : null,
    refetch: async () => {
      await Promise.all([...queries.map((query) => query.refetch()), reviewQuery.refetch()]);
      if (sessionQuery.isEnabled) await sessionQuery.refetch();
    },
  };
}
