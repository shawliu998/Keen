import type { QueryClient } from "@tanstack/react-query";

export function dueReviewsQueryKey(connectionGeneration: number) {
  return ["learning-core", "due-reviews", connectionGeneration, null, null] as const;
}

export async function invalidateLearningContinuityQueries(
  queryClient: QueryClient,
  refetchType: "active" | "all" | "none" = "all",
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["learning-core", "due-reviews"], refetchType }),
    queryClient.invalidateQueries({ queryKey: ["learning-core", "learning-snapshot"], refetchType }),
    queryClient.invalidateQueries({ queryKey: ["learning-core", "study-session-history"], refetchType }),
  ]);
}

export async function invalidateStudySessionContinuityQueries(
  queryClient: QueryClient,
  refetchType: "active" | "all" | "none" = "all",
): Promise<void> {
  await Promise.all([
    invalidateLearningContinuityQueries(queryClient, refetchType),
    queryClient.invalidateQueries({ queryKey: ["learning-core", "study-session"], refetchType }),
    queryClient.invalidateQueries({ queryKey: ["learning-core", "study-session-adaptive-state"], refetchType }),
  ]);
}
