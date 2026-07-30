import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  LearningCoreResponseError,
  type AutonomousRecommendationResponse,
  type LearningCoreClient,
  type LearningSnapshot,
} from "@keen/api-client";

export function resolvedBrowserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

type RecommendationState = {
  pending: boolean;
  cancelled: boolean;
  error: "service_unavailable" | "request_failed" | null;
  result: AutonomousRecommendationResponse | null;
  scope: {
    client: LearningCoreClient | null;
    connectionGeneration: number;
    courseId: string | null;
    availableMinutes: number;
  } | null;
};

const initialRecommendationState: RecommendationState = {
  pending: false,
  cancelled: false,
  error: null,
  result: null,
  scope: null,
};

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function recommendationError(error: unknown): RecommendationState["error"] {
  return error instanceof LearningCoreResponseError && error.status === 503
    ? "service_unavailable"
    : "request_failed";
}

export function useAutonomousLearningFeed({
  client,
  courseId,
  availableMinutes = 20,
  enabled,
  connectionGeneration,
}: {
  client: LearningCoreClient | null;
  courseId: string | null;
  availableMinutes?: number;
  enabled: boolean;
  connectionGeneration: number;
}) {
  const queryClient = useQueryClient();
  const controllerRef = useRef<AbortController | null>(null);
  const requestRef = useRef(0);
  const [recommendation, setRecommendation] = useState<RecommendationState>(initialRecommendationState);
  const cacheKey = useMemo(
    () => ["learning-core", "learning-snapshot", connectionGeneration, courseId, availableMinutes] as const,
    [availableMinutes, connectionGeneration, courseId],
  );
  const snapshotQuery = useQuery({
    queryKey: cacheKey,
    queryFn: ({ signal }) => {
      if (!client || !courseId) throw new Error("A confirmed local course is required before loading the learning feed.");
      return client.learningSnapshot({ courseId, availableMinutes }, { signal });
    },
    enabled: enabled && client !== null && courseId !== null,
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    return () => {
      requestRef.current += 1;
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [availableMinutes, client, connectionGeneration, courseId]);

  const cancelRecommendation = useCallback(() => {
    const active = controllerRef.current;
    if (!active) return;
    active.abort();
    controllerRef.current = null;
    requestRef.current += 1;
    setRecommendation((current) => ({ ...current, pending: false, cancelled: true }));
  }, []);

  const createRecommendation = useCallback(async () => {
    if (!client || !courseId || controllerRef.current) return;
    const controller = new AbortController();
    const request = requestRef.current + 1;
    requestRef.current = request;
    controllerRef.current = controller;
    const scope = { client, connectionGeneration, courseId, availableMinutes };
    setRecommendation({ pending: true, cancelled: false, error: null, result: null, scope });
    try {
      const result = await client.createAutonomousRecommendation(
        { course_id: courseId, available_minutes: availableMinutes, time_zone: resolvedBrowserTimeZone() },
        { signal: controller.signal },
      );
      if (controller.signal.aborted || requestRef.current !== request) return;
      queryClient.setQueryData<LearningSnapshot>(cacheKey, result.snapshot);
      setRecommendation({ pending: false, cancelled: false, error: null, result, scope });
    } catch (error) {
      if (requestRef.current !== request) return;
      if (controller.signal.aborted || isAbort(error)) {
        setRecommendation({ pending: false, cancelled: true, error: null, result: null, scope });
      } else {
        setRecommendation({ pending: false, cancelled: false, error: recommendationError(error), result: null, scope });
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }, [availableMinutes, cacheKey, client, connectionGeneration, courseId, queryClient]);

  const reconcileRecommendation = useCallback(async () => {
    const scope = recommendation.scope;
    if (scope === null) return false;
    const refreshed = await snapshotQuery.refetch();
    if (!refreshed.isSuccess) return false;
    setRecommendation((current) => current.scope === scope ? initialRecommendationState : current);
    return true;
  }, [recommendation.scope, snapshotQuery]);

  const visibleRecommendation = recommendation.scope !== null && (
    recommendation.scope.client !== client
    || recommendation.scope.connectionGeneration !== connectionGeneration
    || recommendation.scope.courseId !== courseId
    || recommendation.scope.availableMinutes !== availableMinutes
  )
    ? initialRecommendationState
    : recommendation;

  return {
    snapshot: snapshotQuery.data,
    snapshotPending: snapshotQuery.isFetching,
    snapshotError: snapshotQuery.error,
    refetchSnapshot: snapshotQuery.refetch,
    createRecommendation,
    cancelRecommendation,
    reconcileRecommendation,
    recommendation: visibleRecommendation,
  };
}
