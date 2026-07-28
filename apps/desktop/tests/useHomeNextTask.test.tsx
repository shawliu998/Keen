import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { useHomeNextTask } from "../src/features/home/useHomeNextTask";

const task = {
  id: "task-1", course_id: "course-1", concept_id: null, title: "Lower-priority saved task",
  reason: "Saved work", due_at: "2026-07-23T09:00:00.000Z", estimated_minutes: 10,
  status: "upcoming", source_type: "study_session", source_id: "session-1", priority_score: 0.5,
  recommended_reason: "Resume the saved session.", scheduled_for: null,
  created_at: "2026-07-21T09:00:00.000Z", updated_at: "2026-07-21T09:00:00.000Z", completed_at: null,
} as const;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => { resolve = nextResolve; reject = nextReject; });
  return { promise, resolve, reject };
}

function wrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useHomeNextTask", () => {
  it("does not expose cached actions while continuity reads are disabled", () => {
    const client = { learningSnapshot: vi.fn(), listDueReviews: vi.fn(), listStudySessions: vi.fn() };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData(["learning-core", "learning-snapshot", 1, "course-1", 20], { pending_tasks: [task] });
    queryClient.setQueryData(["learning-core", "due-reviews", 1, null, null], { items: [{
      id: "review-1", course_id: "course-1", course_title: "Course", concept_id: "concept-1",
      concept_name: "Cached concept", prompt: "Prompt", answer: "Answer", source_context: null,
      state: "review", due_at: "2026-07-22T09:00:00.000Z", created_at: "2026-07-21T09:00:00.000Z",
    }] });
    const { result } = renderHook(() => useHomeNextTask({
      client: client as never, courseIds: ["course-1"], enabled: false, connectionGeneration: 1,
    }), { wrapper: wrapper(queryClient) });

    expect(result.current.nextTask).toBeNull();
    expect(result.current.nextReview).toBeNull();
    expect(result.current.nextSession).toBeNull();
    expect(result.current.error).toBeNull();
    expect(client.learningSnapshot).not.toHaveBeenCalled();
    expect(client.listDueReviews).not.toHaveBeenCalled();
  });

  it("does not expose a saved task or session while the due-review query is pending", async () => {
    const reviews = deferred<{ items: never[] }>();
    const client = {
      learningSnapshot: vi.fn(async () => ({ pending_tasks: [task] })),
      listDueReviews: vi.fn(() => reviews.promise),
      listStudySessions: vi.fn(async () => ({ sessions: [{ id: "session-1", course_id: "course-1", originating_task_id: "task-1" }] })),
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useHomeNextTask({
      client: client as never, courseIds: ["course-1"], enabled: true, connectionGeneration: 1,
    }), { wrapper: wrapper(queryClient) });

    await waitFor(() => expect(client.learningSnapshot).toHaveBeenCalledOnce());
    expect(result.current.pending).toBe(true);
    expect(result.current.nextTask).toBeNull();
    expect(result.current.nextSession).toBeNull();
    expect(client.listStudySessions).not.toHaveBeenCalled();

    await act(async () => { reviews.resolve({ items: [] }); await reviews.promise; });
    await waitFor(() => expect(result.current.nextTask?.id).toBe("task-1"));
    await waitFor(() => expect(client.listStudySessions).toHaveBeenCalledOnce());
  });

  it("fails closed when the due-review query errors after its retry", async () => {
    const client = {
      learningSnapshot: vi.fn(async () => ({ pending_tasks: [task] })),
      listDueReviews: vi.fn(async () => { throw new Error("review read failed"); }),
      listStudySessions: vi.fn(),
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
    const { result } = renderHook(() => useHomeNextTask({
      client: client as never, courseIds: ["course-1"], enabled: true, connectionGeneration: 1,
    }), { wrapper: wrapper(queryClient) });

    await waitFor(() => expect(result.current.error).toEqual(expect.objectContaining({ message: "review read failed" })));
    expect(client.listDueReviews).toHaveBeenCalledTimes(2);
    expect(result.current.nextTask).toBeNull();
    expect(result.current.nextSession).toBeNull();
    expect(client.listStudySessions).not.toHaveBeenCalled();
  });
});
