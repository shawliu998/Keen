import { describe, expect, it, vi } from "vitest";
import { createLearningCoreClient, LearningCoreRequestError, LearningCoreSchemaError } from "@keen/api-client";

const token = "a".repeat(64); const timestamp = "2026-07-18T10:00:00+00:00";
const unit = { id: "unit-1", ordinal: 0, estimated_minutes: 10, status: "active" as const, created_at: timestamp, updated_at: timestamp };
const plan = { id: "plan-1", session_id: "session-1", version: 1, units: [unit, { ...unit, id: "unit-2", ordinal: 1, status: "locked" as const }] };
function session(status: string) { return { id: "session-1", course_id: "course-1", status, revision: 2, progress: 0.1, estimated_minutes: 20, current_unit_id: unit.id, created_at: timestamp, updated_at: timestamp, started_at: timestamp, finished_at: null }; }
const checkpoint = { id: "checkpoint-1", kind: "practice" as const, prompt: "The [...] rule follows the active-recall concept.", status: "pending" as const, created_at: timestamp, answered_at: null };
const run = { id: "run-1", status: "pending" as const, checkpoint_id: checkpoint.id, generator_version: "targeted-practice/1.0.0", created_at: timestamp, answered_at: null, cancelled_at: null, cancellation_reason: null };
function pending(outcome: "pending" | "applied" | "replayed") { return { outcome, course_id: "course-1", session: session("practicing"), plan, checkpoint, current_unit: unit, run, grade: null }; }
function answered(outcome: "applied" | "replayed" = "applied") { return { ...pending(outcome), session: session("summarizing"), checkpoint: { ...checkpoint, status: "answered" as const, answered_at: timestamp }, run: { ...run, status: "answered" as const, answered_at: timestamp }, grade: { correct: true, score: 1, max_score: 1, grader_version: "objective/1" } }; }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("Targeted Practice learning-core client", () => {
  it("uses canonical paths, exact mutation statuses, and forwards abort signals", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ ...pending("pending"), outcome: "pending" })).mockResolvedValueOnce(json(pending("applied"), 201)).mockResolvedValueOnce(json({ ...answered("replayed"), session: session("active_recall") }));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await expect(client.getStudySessionPractice("session-1", "course-1", { signal: controller.signal })).resolves.toMatchObject({ outcome: "pending" });
    await expect(client.beginStudySessionPractice("session-1", { course_id: "course-1", expected_revision: 2, idempotency_key: "practice-begin-0001" })).resolves.toMatchObject({ outcome: "applied" });
    await expect(client.answerStudySessionPractice("session-1", "run-1", { course_id: "course-1", expected_revision: 3, idempotency_key: "practice-answer-001", response: "chain rule" })).resolves.toMatchObject({ outcome: "replayed" });
    const [getUrl, getInit] = fetchMock.mock.calls[0] as [string, RequestInit]; const [beginUrl] = fetchMock.mock.calls[1] as [string, RequestInit]; const [answerUrl] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(getUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/practice?course_id=course-1"); expect(getInit.signal).toBe(controller.signal);
    expect(beginUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/practice"); expect(answerUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/practice/run-1/answer");
  });

  it("rejects bad requests, wrong HTTP status, foreign runs, and invalid action phases", async () => {
    const noFetch = vi.fn(); const invalid = createLearningCoreClient("http://127.0.0.1:8080", token, noFetch as unknown as typeof fetch);
    await expect(Promise.resolve().then(() => invalid.getStudySessionPractice("../../session", "course-1"))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => invalid.beginStudySessionPractice("session-1", { course_id: "course-1", expected_revision: 2, idempotency_key: "short" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    const badStatus = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => json(pending("applied"), 200)) as unknown as typeof fetch);
    await expect(badStatus.beginStudySessionPractice("session-1", { course_id: "course-1", expected_revision: 2, idempotency_key: "practice-begin-0001" })).rejects.toBeInstanceOf(LearningCoreSchemaError);
    const foreign = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => json({ ...answered(), run: { ...answered().run, id: "run-2" } })) as unknown as typeof fetch);
    await expect(foreign.answerStudySessionPractice("session-1", "run-1", { course_id: "course-1", expected_revision: 3, idempotency_key: "practice-answer-001", response: "chain rule" })).rejects.toBeInstanceOf(LearningCoreSchemaError);
    const wrongPhase = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => json({ ...answered(), session: session("review_scheduling") })) as unknown as typeof fetch);
    await expect(wrongPhase.answerStudySessionPractice("session-1", "run-1", { course_id: "course-1", expected_revision: 3, idempotency_key: "practice-answer-001", response: "chain rule" })).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});
