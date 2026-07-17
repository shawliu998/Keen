import { describe, expect, it, vi } from "vitest";
import {
  LearningCoreRequestError,
  LearningCoreSchemaError,
  createLearningCoreClient,
} from "@keen/api-client";
import { diagnosticProgressionResponseSchema, diagnosticReadResponseSchema } from "@keen/api-client";

const token = "a".repeat(64);
const timestamp = "2026-07-17T10:00:00+00:00";

const firstUnit = {
  id: "unit-1",
  ordinal: 0,
  concept_id: "concept-1",
  concept_ids: ["concept-1"],
  source_chunk_ids: ["chunk-1"],
  title: "Limits",
  objective: "Explain a limit.",
  content: "A limit describes approaching a value.",
  estimated_minutes: 10,
  status: "ready",
};
const secondUnit = {
  ...firstUnit,
  id: "unit-2",
  ordinal: 1,
  concept_id: "concept-2",
  concept_ids: ["concept-2"],
  source_chunk_ids: ["chunk-2"],
  title: "Continuity",
  status: "locked",
};
const plan = {
  id: "plan-1",
  session_id: "session-1",
  version: 1,
  rationale: "Start with limits.",
  units: [firstUnit, secondUnit],
};
const checkpoint = {
  id: "checkpoint-1",
  session_id: "session-1",
  unit_id: "unit-1",
  kind: "diagnostic",
  prompt: "What does a limit describe?",
  status: "pending",
};

function session(status: string, revision = 0) {
  return {
    id: "session-1",
    course_id: "course-1",
    originating_task_id: "task-1",
    title: "Study limits",
    mode: "study",
    goal: "Learn limits.",
    estimated_minutes: 20,
    status,
    progress: 0,
    revision,
    created_at: timestamp,
    updated_at: timestamp,
    started_at: timestamp,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("diagnostic learning-core contract", () => {
  it("accepts the three discriminated read states", () => {
    const notStarted = {
      outcome: "not_started",
      course_id: "course-1",
      session: session("goal_confirmation"),
      plan,
      checkpoint: null,
      current_unit: null,
      current_unit_id: null,
    };
    const pending = {
      ...notStarted,
      outcome: "pending",
      session: session("diagnosing", 1),
      checkpoint,
    };
    const activeUnit = { ...firstUnit, status: "active" };
    const answered = {
      ...pending,
      outcome: "answered",
      session: session("studying", 2),
      checkpoint: { ...checkpoint, status: "answered" },
      plan: { ...plan, units: [activeUnit, secondUnit] },
      current_unit: activeUnit,
      current_unit_id: activeUnit.id,
    };

    expect(diagnosticReadResponseSchema.safeParse(notStarted).success).toBe(true);
    expect(diagnosticReadResponseSchema.safeParse(pending).success).toBe(true);
    expect(diagnosticReadResponseSchema.safeParse(answered).success).toBe(true);
  });

  it("rejects malformed, extra, and cross-linked diagnostic read data", () => {
    const pending = {
      outcome: "pending",
      course_id: "course-1",
      session: session("diagnosing", 1),
      plan,
      checkpoint,
      current_unit: null,
      current_unit_id: null,
    };
    expect(diagnosticReadResponseSchema.safeParse({ ...pending, unexpected: true }).success).toBe(false);
    expect(diagnosticReadResponseSchema.safeParse({ ...pending, checkpoint: { ...checkpoint, unit_id: "unit-2" } }).success).toBe(false);
    expect(diagnosticReadResponseSchema.safeParse({ ...pending, current_unit_id: "unit-1" }).success).toBe(false);
    expect(diagnosticReadResponseSchema.safeParse({
      outcome: "not_started",
      course_id: "course-1",
      session: session("goal_confirmation"),
      plan: { ...plan, units: [{ ...firstUnit, status: "locked" }, secondUnit] },
      checkpoint: null,
      current_unit: null,
      current_unit_id: null,
    }).success).toBe(false);
  });

  it("rejects forged diagnostic state/status pairs, except paused recovery states", () => {
    const notStarted = {
      outcome: "not_started",
      course_id: "course-1",
      session: session("goal_confirmation"),
      plan,
      checkpoint: null,
      current_unit: null,
      current_unit_id: null,
    };
    const pending = {
      outcome: "pending",
      course_id: "course-1",
      session: session("diagnosing", 1),
      plan,
      checkpoint,
      current_unit: null,
      current_unit_id: null,
    };
    const activeUnit = { ...firstUnit, status: "active" };
    const answered = {
      outcome: "answered",
      course_id: "course-1",
      session: session("studying", 2),
      plan: { ...plan, units: [activeUnit, secondUnit] },
      checkpoint: { ...checkpoint, status: "answered" },
      current_unit: activeUnit,
      current_unit_id: activeUnit.id,
    };

    expect(diagnosticReadResponseSchema.safeParse({ ...notStarted, session: session("diagnosing") }).success).toBe(false);
    expect(diagnosticReadResponseSchema.safeParse({ ...pending, session: session("studying", 1) }).success).toBe(false);
    expect(diagnosticReadResponseSchema.safeParse({ ...answered, session: session("diagnosing", 2) }).success).toBe(false);
    expect(diagnosticReadResponseSchema.safeParse({ ...notStarted, session: session("paused") }).success).toBe(true);
    expect(diagnosticReadResponseSchema.safeParse({ ...pending, session: session("paused", 1) }).success).toBe(true);
    expect(diagnosticReadResponseSchema.safeParse({ ...answered, session: session("paused", 2) }).success).toBe(true);
  });

  it("rejects a forged answered current unit and inconsistent progression status", () => {
    const activeFirst = { ...firstUnit, status: "active" };
    const activeSecond = { ...secondUnit, status: "active" };
    const answered = {
      outcome: "answered",
      course_id: "course-1",
      session: session("studying", 2),
      plan: { ...plan, units: [activeFirst, activeSecond] },
      checkpoint: { ...checkpoint, status: "answered" },
      current_unit: activeSecond,
      current_unit_id: activeSecond.id,
    };
    expect(diagnosticReadResponseSchema.safeParse(answered).success).toBe(false);
    expect(diagnosticReadResponseSchema.safeParse({
      ...answered,
      current_unit: activeFirst,
      current_unit_id: activeFirst.id,
    }).success).toBe(false);

    const pendingProgression = {
      outcome: "applied",
      course_id: "course-1",
      session: session("studying", 1),
      plan,
      checkpoint,
      current_unit: null,
      current_unit_id: null,
      mastery_changed: false,
      scoring: "not_performed",
    };
    expect(diagnosticProgressionResponseSchema.safeParse(pendingProgression).success).toBe(false);
    const answeredProgression = {
      ...pendingProgression,
      session: session("studying", 2),
      plan: { ...plan, units: [activeFirst, activeSecond] },
      checkpoint: { ...checkpoint, status: "answered" },
      current_unit: activeSecond,
      current_unit_id: activeSecond.id,
    };
    expect(diagnosticProgressionResponseSchema.safeParse(answeredProgression).success).toBe(false);
  });

  it("uses snake_case paths, bodies, status semantics, and abort signals", async () => {
    const controller = new AbortController();
    const pending = {
      outcome: "pending",
      course_id: "course-1",
      session: session("diagnosing", 1),
      plan,
      checkpoint,
      current_unit: null,
      current_unit_id: null,
    };
    const activeUnit = { ...firstUnit, status: "active" };
    const answered = {
      outcome: "applied",
      course_id: "course-1",
      session: session("studying", 2),
      plan: { ...plan, units: [activeUnit, secondUnit] },
      checkpoint: { ...checkpoint, status: "answered" },
      current_unit: activeUnit,
      current_unit_id: "unit-1",
      mastery_changed: false,
      scoring: "not_performed",
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(pending))
      .mockResolvedValueOnce(jsonResponse({ ...pending, outcome: "applied", mastery_changed: false, scoring: "not_performed" }, 201))
      .mockResolvedValueOnce(jsonResponse(answered, 201));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.getStudySessionDiagnostic("session-1", "course-1", { signal: controller.signal })).resolves.toMatchObject({ outcome: "pending" });
    await expect(client.beginStudySessionDiagnostic("session-1", {
      course_id: "course-1",
      expected_revision: 0,
      idempotency_key: "begin-0123456789ab",
    })).resolves.toMatchObject({ outcome: "applied", checkpoint: { status: "pending" } });
    await expect(client.answerStudySessionDiagnostic("session-1", "checkpoint-1", {
      course_id: "course-1",
      expected_revision: 1,
      idempotency_key: "answer-0123456789a",
      response: "It describes getting closer to a value.",
      self_assessment: "partial",
    })).resolves.toMatchObject({ outcome: "applied", checkpoint: { status: "answered" } });

    const [getUrl, getInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [beginUrl, beginInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    const [answerUrl, answerInit] = fetchMock.mock.calls[2] as unknown as [string, RequestInit];
    expect(getUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/diagnostic?course_id=course-1");
    expect(getInit.signal).toBe(controller.signal);
    expect(beginUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/diagnostic");
    expect(JSON.parse(String(beginInit.body))).toEqual({ course_id: "course-1", expected_revision: 0, idempotency_key: "begin-0123456789ab" });
    expect(answerUrl).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/diagnostic/checkpoint-1/answer");
    expect(JSON.parse(String(answerInit.body))).toEqual({
      course_id: "course-1",
      expected_revision: 1,
      idempotency_key: "answer-0123456789a",
      response: "It describes getting closer to a value.",
      self_assessment: "partial",
    });
  });

  it("rejects extra request fields and malformed response envelopes before trusting them", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);
    await expect(Promise.resolve().then(() => client.beginStudySessionDiagnostic("session-1", {
      course_id: "course-1",
      expected_revision: 0,
      idempotency_key: "begin-0123456789ab",
      unexpected: true,
    } as unknown as { course_id: string; expected_revision: number; idempotency_key: string }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    expect(fetchMock).not.toHaveBeenCalled();

    const malformed = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => jsonResponse({
        outcome: "pending",
        course_id: "course-1",
        session: session("diagnosing", 1),
        plan,
        checkpoint,
        current_unit: null,
        current_unit_id: null,
        extra: "not allowed",
      })) as unknown as typeof fetch,
    );
    await expect(malformed.getStudySessionDiagnostic("session-1", "course-1")).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("accepts a 200 replay and rejects a contradictory 201 replay", async () => {
    const replay = {
      outcome: "replayed",
      course_id: "course-1",
      session: session("diagnosing", 1),
      plan,
      checkpoint,
      current_unit: null,
      current_unit_id: null,
      mastery_changed: false,
      scoring: "not_performed",
    };
    const replayClient = createLearningCoreClient(
      "http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(replay)) as unknown as typeof fetch,
    );
    await expect(replayClient.beginStudySessionDiagnostic("session-1", {
      course_id: "course-1", expected_revision: 0, idempotency_key: "begin-0123456789ab",
    })).resolves.toMatchObject({ outcome: "replayed" });

    const contradictoryClient = createLearningCoreClient(
      "http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(replay, 201)) as unknown as typeof fetch,
    );
    await expect(contradictoryClient.beginStudySessionDiagnostic("session-1", {
      course_id: "course-1", expected_revision: 0, idempotency_key: "begin-0123456789ab",
    })).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});
