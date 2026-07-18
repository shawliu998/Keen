import { render, screen, waitFor } from "@testing-library/react";
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

function renderSummary(client: Record<string, unknown>, changed = vi.fn()) {
  render(<SessionSummary client={client as never} sessionId="session-1" courseId="course-1" session={session} onSessionChanged={changed} />);
  return changed;
}

describe("local learning summary", () => {
  it("restores safe metrics and explicitly schedules one local review", async () => {
    const user = userEvent.setup();
    const client = { getStudySessionSummary: vi.fn(async () => ready), finalizeStudySessionSummary: vi.fn(async () => applied) };
    const changed = renderSummary(client);
    expect(await screen.findByText("Ready to finish this local session")).toBeInTheDocument();
    expect(screen.getByText("Active recall:")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish and schedule local review" }));
    expect(await screen.findByText("Session complete")).toBeInTheDocument();
    expect(client.finalizeStudySessionSummary).toHaveBeenCalledWith("session-1", expect.objectContaining({ course_id: "course-1", expected_revision: 5, idempotency_key: expect.any(String) }), expect.anything());
    expect(changed).toHaveBeenCalled();
  });

  it("reconciles a revision conflict instead of retrying a stale finalization", async () => {
    const user = userEvent.setup();
    const client = {
      getStudySessionSummary: vi.fn().mockResolvedValueOnce(ready).mockResolvedValueOnce({ ...ready, session: { ...base.session, revision: 9 } }),
      finalizeStudySessionSummary: vi.fn().mockRejectedValueOnce(new LearningCoreResponseError(409, null, null)),
    };
    renderSummary(client);
    await user.click(await screen.findByRole("button", { name: "Finish and schedule local review" }));
    expect(await screen.findByText(/This session changed before the summary completed/)).toBeInTheDocument();
    expect(client.finalizeStudySessionSummary).toHaveBeenCalledOnce();
  });

  it("retries an unknown finalization with the frozen intent", async () => {
    const user = userEvent.setup();
    const client = {
      getStudySessionSummary: vi.fn().mockResolvedValueOnce(ready).mockResolvedValueOnce(ready),
      finalizeStudySessionSummary: vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(applied),
    };
    renderSummary(client);
    await user.click(await screen.findByRole("button", { name: "Finish and schedule local review" }));
    await user.click(await screen.findByRole("button", { name: "Retry same local review" }));
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
    const view = render(<SessionSummary client={client as never} sessionId="session-1" courseId="course-1" session={session} onSessionChanged={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "Finish and schedule local review" }));
    await waitFor(() => expect(client.finalizeStudySessionSummary).toHaveBeenCalledOnce());
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
});
