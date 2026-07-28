import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  LearningCoreResponseError,
  type Course,
  type DemoState,
  type LearningCoreClient,
} from "@keen/api-client";

type CourseCreateClient = Pick<LearningCoreClient, "createCourse">;
type CourseCacheKey = readonly ["learning-core", "demo-state", string | number, number];

type CourseCreateState = {
  creating: boolean;
  error: string | null;
  notice: string | null;
};

const unconfirmedCreationMessage = "Course creation is unconfirmed. The current course display was not updated. The local service may have created the course. Refresh the course list first, then retry with the same request key to avoid creating a duplicate course.";

function createIdempotencyKey(): string {
  if (typeof globalThis.crypto.randomUUID === "function") {
    return `course-${globalThis.crypto.randomUUID().replaceAll("-", "")}`;
  }
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return `course-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

function mergeCourse(state: DemoState | undefined, course: Course): DemoState | undefined {
  if (!state) return state;
  const courses = state.courses.some((item) => item.id === course.id)
    ? state.courses.map((item) => item.id === course.id ? course : item)
    : [...state.courses, course];
  return { ...state, courses };
}

function knownFailureMessage(error: LearningCoreResponseError): string | null {
  if (error.status === 409) {
    return "Course creation conflicted with an existing local request. No course was selected; review the course list and submit again.";
  }
  if (error.status === 400 || error.status === 422) {
    return "Course creation was rejected before a course was created. Update the title or description and submit again.";
  }
  return null;
}

export function useCourseCreate({
  client,
  cacheKey,
  onCreated,
}: {
  client: CourseCreateClient | null;
  cacheKey: CourseCacheKey;
  onCreated: (course: Course) => void;
}) {
  const queryClient = useQueryClient();
  const controller = useRef<AbortController | null>(null);
  const key = useRef(createIdempotencyKey());
  const [state, setState] = useState<CourseCreateState>({ creating: false, error: null, notice: null });

  useEffect(() => {
    return () => {
      controller.current?.abort();
      controller.current = null;
    };
  }, [cacheKey, client]);

  const createCourse = useCallback(async (title: string, description: string) => {
    if (!client || controller.current) return;
    const requestKey = key.current;
    const requestController = new AbortController();
    controller.current = requestController;
    setState({ creating: true, error: null, notice: null });
    try {
      const result = await client.createCourse({ title, description, idempotencyKey: requestKey }, { signal: requestController.signal });
      if (requestController.signal.aborted || controller.current !== requestController) return;
      queryClient.setQueryData<DemoState>(cacheKey, (current) => mergeCourse(current, result.course));
      onCreated(result.course);
      key.current = createIdempotencyKey();
      setState({
        creating: false,
        error: null,
        notice: result.replayed
          ? `The existing course “${result.course.title}” was selected for the next import.`
          : `Created “${result.course.title}” and selected it for the next import.`,
      });
    } catch (error) {
      if (controller.current !== requestController) return;
      if (requestController.signal.aborted) {
        setState({ creating: false, error: "Course creation was cancelled before a confirmed result. No course was selected; submit again when ready.", notice: null });
      } else if (error instanceof LearningCoreResponseError) {
        const message = knownFailureMessage(error);
        if (message) {
          key.current = createIdempotencyKey();
          setState({ creating: false, error: message, notice: null });
        } else {
          setState({ creating: false, error: unconfirmedCreationMessage, notice: null });
        }
      } else {
        setState({ creating: false, error: unconfirmedCreationMessage, notice: null });
      }
    } finally {
      if (controller.current === requestController) controller.current = null;
    }
  }, [cacheKey, client, onCreated, queryClient]);

  return { ...state, createCourse };
}
