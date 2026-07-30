import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LearningCoreResponseError } from "@keen/api-client";
import { SessionSummary } from "../src/features/deep-learn/SessionSummary";

const time = "2026-07-18T10:00:00+00:00";
const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Private session", mode: "study" as const, goal: "Private goal", estimated_minutes: 20, status: "summarizing" as const, progress: 0.8, revision: 5, created_at: time, updated_at: time, started_at: time };
const base = {
  course_id: "course-1",
  session: { id: "session-1", course_id: "course-1", status: "summarizing" as const, revision: 5, progress: 0.8, estimated_minutes: 20, created_at: time, updated_at: time, started_at: time, finished_at: null },
  summary: { active_recall_correct: true, practice_correct: false, practice_score: 0, practice_max_score: 1, task_completed: false, remaining_units: 0 },
  review: null,
};
const ready = { outcome: "ready" as const, ...base };
const applied = {
  outcome: "applied" as const, ...base,
  session: { ...base.session, status: "completed" as const, revision: 6, progress: 1, finished_at: time },
  summary: { ...base.summary, task_completed: true },
  review: { due_at: time, scheduler: "fsrs", scheduler_version: "fsrs-6.3.1-keen-v1", state: "new" },
};

function renderSummary(client: Record<string, unknown>, changed = vi.fn(), onOpenReview = vi.fn(), onOpenFeed = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><SessionSummary client={client as never} sessionId="session-1" courseId="course-1" session={session} onSessionChanged={changed} onOpenReview={onOpenReview} onOpenFeed={onOpenFeed} /></QueryClientProvider>);
  return { changed, onOpenReview, onOpenFeed, queryClient };
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((nextResolve) => { resolve = nextResolve; });
  return { promise, resolve };
}

describe("local learning summary", () => {
  it("restores safe metrics and explicitly schedules one review", async () => {
    const user = userEvent.setup();
    const client = { getStudySessionSummary: vi.fn(async () => ready), finalizeStudySessionSummary: vi.fn(async () => applied) };
    const { changed, onOpenReview, onOpenFeed, queryClient } = renderSummary(client);
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    expect(await screen.findByRole("heading", { name: "Finish this study session" })).toBeInTheDocument();
    expect(screen.getByText("Active recall")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish and schedule review" }));
    expect(await screen.findByText("Session complete")).toBeInTheDocument();
    const schedule = screen.getByText((_, element) => element?.classList.contains("session-complete-schedule") ?? false);
    expect(schedule).toHaveTextContent("Review scheduled for");
    expect(schedule).toHaveTextContent(/Review scheduled for [A-Z][a-z]{2} \d{1,2}, 2026/);
    expect(schedule).not.toHaveTextContent(/[\u5e74\u6708\u65e5]/);
    expect(schedule).not.toHaveTextContent(/:\d{2}:\d{2}/);
    expect(screen.queryByText(/fsrs/i)).not.toBeInTheDocument();
    const openReview = screen.getByRole("button", { name: "Review now" });
    const openFeed = screen.getByRole("button", { name: "View Learning Feed" });
    await user.tab();
    expect(openReview).toHaveFocus();
    await user.tab();
    expect(openFeed).toHaveFocus();
    await user.click(openReview);
    await user.click(openFeed);
    expect(onOpenReview).toHaveBeenCalledOnce();
    expect(onOpenFeed).toHaveBeenCalledOnce();
    expect(client.finalizeStudySessionSummary).toHaveBeenCalledWith("session-1", expect.objectContaining({ course_id: "course-1", expected_revision: 5, idempotency_key: expect.any(String) }), expect.anything());
    expect(changed).toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learning-core", "due-reviews"], refetchType: "all" });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learning-core", "learning-snapshot"], refetchType: "all" });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learning-core", "study-session-history"], refetchType: "all" });
  });

  it("returns to the learning queue instead of opening Review before its due time", async () => {
    const user = userEvent.setup();
    const onOpenReview = vi.fn();
    const onOpenFeed = vi.fn();
    const scheduled = { ...applied, outcome: "completed" as const, review: { ...applied.review, due_at: "2099-07-18T10:00:00+00:00" } };
    renderSummary({ getStudySessionSummary: vi.fn(async () => scheduled), finalizeStudySessionSummary: vi.fn() }, vi.fn(), onOpenReview, onOpenFeed);
    await user.click(await screen.findByRole("button", { name: "Return to learning queue" }));
    expect(onOpenFeed).toHaveBeenCalledOnce();
    expect(onOpenReview).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "View Learning Feed" })).not.toBeInTheDocument();
  });

  it("updates the completed CTA when the review becomes due while the page stays open", async () => {
    vi.useFakeTimers();
    vi.setSystemTime("2026-07-18T10:00:00.000Z");
    try {
      const scheduled = { ...applied, outcome: "completed" as const, review: { ...applied.review, due_at: "2026-07-18T10:00:01.000Z" } };
      renderSummary({ getStudySessionSummary: vi.fn(async () => scheduled), finalizeStudySessionSummary: vi.fn() });
      await act(async () => { vi.advanceTimersByTime(0); await Promise.resolve(); });
      expect(screen.getByRole("button", { name: "Return to learning queue" })).toBeInTheDocument();
      await act(async () => { vi.advanceTimersByTime(1_000); await Promise.resolve(); });
      expect(screen.getByRole("button", { name: "Review now" })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("fails an invalid review date closed without throwing or scheduling Review", async () => {
    const scheduled = { ...applied, outcome: "completed" as const, review: { ...applied.review, due_at: "not-a-date" } };
    renderSummary({ getStudySessionSummary: vi.fn(async () => scheduled), finalizeStudySessionSummary: vi.fn() });
    expect(await screen.findByText(/review schedule is unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to learning queue" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review now" })).not.toBeInTheDocument();
  });

  it("reconciles a revision conflict instead of retrying a stale finalization", async () => {
    const user = userEvent.setup();
    const client = {
      getStudySessionSummary: vi.fn().mockResolvedValueOnce(ready).mockResolvedValueOnce({ ...ready, session: { ...base.session, revision: 9 } }),
      finalizeStudySessionSummary: vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null)),
    };
    renderSummary(client);
    await user.click(await screen.findByRole("button", { name: "Finish and schedule review" }));
    expect(await screen.findByText(/This session changed before the summary completed/)).toBeInTheDocument();
    expect(client.finalizeStudySessionSummary).toHaveBeenCalledOnce();
  });

  it("invalidates continuity when a conflict restore confirms the summary already completed", async () => {
    const user = userEvent.setup();
    const client = {
      getStudySessionSummary: vi.fn().mockResolvedValueOnce(ready).mockResolvedValueOnce(applied),
      finalizeStudySessionSummary: vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null)),
    };
    const { queryClient } = renderSummary(client);
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await user.click(await screen.findByRole("button", { name: "Finish and schedule review" }));
    expect(await screen.findByText("Session complete")).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learning-core", "learning-snapshot"], refetchType: "all" });
  });

  it("keeps completion navigation locked until continuity refresh settles", async () => {
    const user = userEvent.setup();
    const refresh = deferred();
    const client = { getStudySessionSummary: vi.fn(async () => ready), finalizeStudySessionSummary: vi.fn(async () => applied) };
    const { queryClient, onOpenReview, onOpenFeed } = renderSummary(client);
    vi.spyOn(queryClient, "invalidateQueries").mockImplementation(() => refresh.promise);
    await user.click(await screen.findByRole("button", { name: "Finish and schedule review" }));
    const refreshing = await screen.findByRole("button", { name: "Refreshing saved work…" });
    expect(refreshing).toBeDisabled();
    expect(screen.getByRole("button", { name: "View Learning Feed" })).toBeDisabled();
    expect(onOpenReview).not.toHaveBeenCalled();
    expect(onOpenFeed).not.toHaveBeenCalled();
    await act(async () => { refresh.resolve(); await refresh.promise; });
    expect(await screen.findByRole("button", { name: "Review now" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "View Learning Feed" })).toBeEnabled();
  });

  it("retries an unknown finalization with the frozen intent", async () => {
    const user = userEvent.setup();
    const client = {
      getStudySessionSummary: vi.fn().mockResolvedValueOnce(ready).mockResolvedValueOnce(ready),
      finalizeStudySessionSummary: vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(applied),
    };
    renderSummary(client);
    await user.click(await screen.findByRole("button", { name: "Finish and schedule review" }));
    await user.click(await screen.findByRole("button", { name: "Retry same review" }));
    await screen.findByText("Session complete");
    const calls = client.finalizeStudySessionSummary.mock.calls as unknown[][];
    expect(calls[1]?.[1]).toEqual(calls[0]?.[1]);
  });

  it("aborts a summary write on unmount", async () => {
    const user = userEvent.setup();
    let signal: AbortSignal | undefined;
    const client = {
      getStudySessionSummary: vi.fn(async () => ready),
      finalizeStudySessionSummary: vi.fn((_: string, __: unknown, options: { signal?: AbortSignal }) => new Promise(() => { signal = options.signal; })),
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><SessionSummary client={client as never} sessionId="session-1" courseId="course-1" session={session} onSessionChanged={vi.fn()} onOpenReview={vi.fn()} onOpenFeed={vi.fn()} /></QueryClientProvider>);
    await user.click(await screen.findByRole("button", { name: "Finish and schedule review" }));
    await waitFor(() => expect(client.finalizeStudySessionSummary).toHaveBeenCalledOnce());
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
});
