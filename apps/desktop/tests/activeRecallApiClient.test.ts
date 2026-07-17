import { describe, expect, it, vi } from "vitest";
import {
  createLearningCoreClient,
  LearningCoreRequestError,
  LearningCoreSchemaError,
} from "@keen/api-client";

const token = "a".repeat(64);
const timestamp = "2026-07-18T10:00:00+00:00";

const unit = {
  id: "unit-1", ordinal: 0, estimated_minutes: 10, status: "active" as const,
  created_at: timestamp, updated_at: timestamp,
};
const plan = {
  id: "plan-1", session_id: "session-1", version: 1,
  units: [unit, { ...unit, id: "unit-2", ordinal: 1, status: "locked" as const }],
};
const checkpoint = {
  id: "checkpoint-1", kind: "active_recall" as const,
  prompt: "The [...] differentiates composite functions.", status: "pending" as const,
  created_at: timestamp, answered_at: null,
};
const pendingRun = {
  id: "run-1", status: "pending" as const, checkpoint_id: checkpoint.id,
  generator_version: "source-cloze/1.0.0", created_at: timestamp,
  answered_at: null, cancelled_at: null, cancellation_reason: null,
};

function session(status: string) {
  return {
    id: "session-1", course_id: "course-1", status, revision: 2, progress: 0.1,
    estimated_minutes: 20, current_unit_id: unit.id, created_at: timestamp,
    updated_at: timestamp, started_at: timestamp, finished_at: null,
  };
}

function pendingResponse(outcome: "pending" | "applied" | "replayed") {
  return {
    outcome,
    course_id: "course-1",
    session: session("active_recall"),
    plan,
    checkpoint,
    current_unit: unit,
    run: pendingRun,
    grade: null,
  };
}

function answeredResponse(outcome: "applied" | "replayed" = "applied") {
  return {
    ...pendingResponse(outcome),
    session: session("practicing"),
    checkpoint: { ...checkpoint, status: "answered" as const, answered_at: timestamp },
    run: { ...pendingRun, status: "answered" as const, answered_at: timestamp },
    grade: { correct: true, score: 1, max_score: 1, grader_version: "objective/1" },
  };
}

function cancelledResponse(outcome: "applied" | "replayed" = "replayed") {
  return {
    ...pendingResponse(outcome),
    session: session("cancelled"),
    checkpoint: { ...checkpoint, status: "skipped" as const },
    run: {
      ...pendingRun,
      status: "cancelled" as const,
      cancelled_at: timestamp,
      cancellation_reason: "session_cancelled" as const,
    },
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Active Recall learning-core client", () => {
  it("uses canonical paths, status semantics, and abort signals", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ ...pendingResponse("pending"), outcome: "pending" }))
      .mockResolvedValueOnce(jsonResponse(pendingResponse("applied"), 201))
      .mockResolvedValueOnce(jsonResponse(answeredResponse("replayed")));
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch,
    );

    await expect(client.getStudySessionActiveRecall("session-1", "course-1", { signal: controller.signal }))
      .resolves.toMatchObject({ outcome: "pending" });
    await expect(client.beginStudySessionActiveRecall("session-1", {
      course_id: "course-1", expected_revision: 2, idempotency_key: "active-recall-begin-01",
    })).resolves.toMatchObject({ outcome: "applied", run: { status: "pending" } });
    await expect(client.answerStudySessionActiveRecall("session-1", "run-1", {
      course_id: "course-1", expected_revision: 4, idempotency_key: "active-recall-answer-01",
      response: "chain rule",
    })).resolves.toMatchObject({ outcome: "replayed", run: { status: "answered" } });

    const [getUrl, getInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [beginUrl, beginInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    const [answerUrl, answerInit] = fetchMock.mock.calls[2] as unknown as [string, RequestInit];
    expect(getUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/active-recall?course_id=course-1");
    expect(getInit.signal).toBe(controller.signal);
    expect(beginUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/active-recall");
    expect(JSON.parse(String(beginInit.body))).toEqual({
      course_id: "course-1", expected_revision: 2, idempotency_key: "active-recall-begin-01",
    });
    expect(answerUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/active-recall/run-1/answer");
    expect(JSON.parse(String(answerInit.body))).toEqual({
      course_id: "course-1", expected_revision: 4, idempotency_key: "active-recall-answer-01", response: "chain rule",
    });
  });

  it("rejects invalid identifiers, request bodies, status semantics, and foreign results", async () => {
    const noFetch = vi.fn();
    const invalid = createLearningCoreClient("http://127.0.0.1:8080", token, noFetch as unknown as typeof fetch);
    await expect(Promise.resolve().then(() => invalid.getStudySessionActiveRecall("../../session", "course-1")))
      .rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => invalid.beginStudySessionActiveRecall("session-1", {
      course_id: "course-1", expected_revision: 0, idempotency_key: "short",
    }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    expect(noFetch).not.toHaveBeenCalled();

    const badBegin = createLearningCoreClient(
      "http://127.0.0.1:8080", token,
      vi.fn(async () => jsonResponse(pendingResponse("applied"), 200)) as unknown as typeof fetch,
    );
    await expect(badBegin.beginStudySessionActiveRecall("session-1", {
      course_id: "course-1", expected_revision: 2, idempotency_key: "active-recall-begin-01",
    })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const appliedAnsweredBegin = createLearningCoreClient(
      "http://127.0.0.1:8080", token,
      vi.fn(async () => jsonResponse({ ...answeredResponse(), session: session("completed") }, 201)) as unknown as typeof fetch,
    );
    await expect(appliedAnsweredBegin.beginStudySessionActiveRecall("session-1", {
      course_id: "course-1", expected_revision: 2, idempotency_key: "active-recall-begin-01",
    })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const foreignAnswer = createLearningCoreClient(
      "http://127.0.0.1:8080", token,
      vi.fn(async () => jsonResponse({ ...answeredResponse(), run: { ...answeredResponse().run, id: "run-2" } })) as unknown as typeof fetch,
    );
    await expect(foreignAnswer.answerStudySessionActiveRecall("session-1", "run-1", {
      course_id: "course-1", expected_revision: 4, idempotency_key: "active-recall-answer-01", response: "chain rule",
    })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const replayCancelledAnswer = createLearningCoreClient(
      "http://127.0.0.1:8080", token,
      vi.fn(async () => jsonResponse(cancelledResponse())) as unknown as typeof fetch,
    );
    await expect(replayCancelledAnswer.answerStudySessionActiveRecall("session-1", "run-1", {
      course_id: "course-1", expected_revision: 4, idempotency_key: "active-recall-answer-01", response: "chain rule",
    })).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const appliedNonPracticingAnswer = createLearningCoreClient(
      "http://127.0.0.1:8080", token,
      vi.fn(async () => jsonResponse({ ...answeredResponse(), session: session("summarizing") })) as unknown as typeof fetch,
    );
    await expect(appliedNonPracticingAnswer.answerStudySessionActiveRecall("session-1", "run-1", {
      course_id: "course-1", expected_revision: 4, idempotency_key: "active-recall-answer-01", response: "chain rule",
    })).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});
