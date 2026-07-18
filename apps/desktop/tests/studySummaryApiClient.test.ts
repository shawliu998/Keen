import { describe, expect, it, vi } from "vitest";
import { createLearningCoreClient, LearningCoreRequestError, LearningCoreSchemaError } from "@keen/api-client";

const token = "a".repeat(64); const time = "2026-07-18T10:00:00+00:00";
const base = {
  course_id: "course-1",
  session: { id: "session-1", course_id: "course-1", status: "summarizing" as const, revision: 5, progress: 0.8, estimated_minutes: 20, created_at: time, updated_at: time, started_at: time, finished_at: null },
  summary: { active_recall_correct: true, practice_correct: true, practice_score: 1, practice_max_score: 1, task_completed: false, remaining_units: 0 },
  review: null,
};
const ready = { outcome: "ready" as const, ...base };
const completed = {
  outcome: "applied" as const, ...base,
  session: { ...base.session, status: "completed" as const, revision: 6, progress: 1, finished_at: time },
  summary: { ...base.summary, task_completed: true },
  review: { due_at: time, scheduler: "fsrs", scheduler_version: "fsrs-6.3.1-keen-v1", state: "new" },
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("study-summary learning-core client", () => {
  it("uses canonical paths, exact statuses, and forwards abort signals", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(json(completed, 201));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await expect(client.getStudySessionSummary("session-1", "course-1", { signal: controller.signal })).resolves.toMatchObject({ outcome: "ready" });
    await expect(client.finalizeStudySessionSummary("session-1", { course_id: "course-1", expected_revision: 5, idempotency_key: "study-summary-finalize-001" })).resolves.toMatchObject({ outcome: "applied" });
    const [getUrl, getInit] = fetchMock.mock.calls[0] as [string, RequestInit]; const [postUrl] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(getUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/summary?course_id=course-1");
    expect(getInit.signal).toBe(controller.signal);
    expect(postUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/summary");
  });

  it("rejects malformed commands, wrong mutation status, and foreign summaries", async () => {
    const noFetch = vi.fn(); const invalid = createLearningCoreClient("http://127.0.0.1:8080", token, noFetch as unknown as typeof fetch);
    await expect(Promise.resolve().then(() => invalid.getStudySessionSummary("../../session", "course-1"))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => invalid.finalizeStudySessionSummary("session-1", { course_id: "course-1", expected_revision: 5, idempotency_key: "short" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    const badStatus = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => json(completed, 200)) as unknown as typeof fetch);
    await expect(badStatus.finalizeStudySessionSummary("session-1", { course_id: "course-1", expected_revision: 5, idempotency_key: "study-summary-finalize-001" })).rejects.toBeInstanceOf(LearningCoreSchemaError);
    const foreign = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => json({ ...ready, course_id: "course-2" })) as unknown as typeof fetch);
    await expect(foreign.getStudySessionSummary("session-1", "course-1")).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});
