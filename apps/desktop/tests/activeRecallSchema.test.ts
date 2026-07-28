import { describe, expect, it } from "vitest";
import {
  activeRecallAnswerRequestSchema,
  activeRecallProgressionRequestSchema,
  activeRecallProgressionResponseSchema,
  activeRecallReadResponseSchema,
} from "@keen/api-client";

const timestamp = "2026-07-18T10:00:00+00:00";

const unit = {
  id: "unit-1",
  ordinal: 0,
  estimated_minutes: 10,
  status: "active" as const,
  created_at: timestamp,
  updated_at: timestamp,
};

const plan = {
  id: "plan-1",
  session_id: "session-1",
  version: 1,
  units: [unit, { ...unit, id: "unit-2", ordinal: 1, status: "locked" as const }],
};

function session(status: string) {
  return {
    id: "session-1",
    course_id: "course-1",
    status,
    revision: 2,
    progress: 0.1,
    estimated_minutes: 20,
    current_unit_id: "unit-1",
    created_at: timestamp,
    updated_at: timestamp,
    started_at: timestamp,
    finished_at: null,
  };
}

const checkpoint = {
  id: "checkpoint-1",
  kind: "active_recall" as const,
  prompt: "The [...] differentiates composite functions.",
  status: "pending" as const,
  created_at: timestamp,
  answered_at: null,
};

const pendingRun = {
  id: "run-1",
  status: "pending" as const,
  checkpoint_id: "checkpoint-1",
  generator_version: "source-cloze/1.0.0",
  created_at: timestamp,
  answered_at: null,
  cancelled_at: null,
  cancellation_reason: null,
};

describe("active-recall API schemas", () => {
  it("accepts the public read states and applied/replayed mutations", () => {
    const notStarted = {
      outcome: "not_started" as const,
      course_id: "course-1",
      session: session("studying"),
      plan,
      checkpoint: null,
      current_unit: unit,
      run: null,
      grade: null,
    };
    const pending = {
      ...notStarted,
      outcome: "pending" as const,
      session: session("active_recall"),
      checkpoint,
      run: pendingRun,
    };
    const answered = {
      ...pending,
      outcome: "answered" as const,
      session: session("practicing"),
      checkpoint: { ...checkpoint, status: "answered" as const, answered_at: timestamp },
      run: { ...pendingRun, status: "answered" as const, answered_at: timestamp },
      grade: { correct: true, score: 1, max_score: 1, grader_version: "objective/1" },
    };
    const cancelled = {
      ...pending,
      outcome: "cancelled" as const,
      session: session("cancelled"),
      checkpoint: { ...checkpoint, status: "skipped" as const },
      run: {
        ...pendingRun,
        status: "cancelled" as const,
        cancelled_at: timestamp,
        cancellation_reason: "session_cancelled" as const,
      },
    };

    expect(activeRecallReadResponseSchema.safeParse(notStarted).success).toBe(true);
    expect(activeRecallReadResponseSchema.safeParse({
      ...notStarted,
      session: { ...session("studying"), current_unit_id: null },
      current_unit: null,
    }).success).toBe(true);
    expect(activeRecallReadResponseSchema.safeParse(pending).success).toBe(true);
    expect(activeRecallReadResponseSchema.safeParse(answered).success).toBe(true);
    expect(activeRecallReadResponseSchema.safeParse(cancelled).success).toBe(true);
    expect(activeRecallProgressionResponseSchema.safeParse({ ...pending, outcome: "applied" }).success).toBe(true);
    expect(activeRecallProgressionResponseSchema.safeParse({ ...answered, outcome: "replayed" }).success).toBe(true);
  });

  it("rejects forged phases, relationships, terminal metadata, and private fields", () => {
    const pending = {
      outcome: "pending" as const,
      course_id: "course-1",
      session: session("active_recall"),
      plan,
      checkpoint,
      current_unit: unit,
      run: pendingRun,
      grade: null,
    };

    expect(activeRecallReadResponseSchema.safeParse({ ...pending, session: session("practicing") }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({
      ...pending,
      outcome: "cancelled",
      session: session("paused"),
      checkpoint: { ...checkpoint, status: "skipped" },
      run: {
        ...pendingRun,
        status: "cancelled",
        cancelled_at: timestamp,
        cancellation_reason: "session_cancelled",
      },
    }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, session: { ...session("active_recall"), course_id: "course-2" } }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, current_unit: { ...unit, id: "unit-x" } }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, run: { ...pendingRun, checkpoint_id: "checkpoint-x" } }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, run: { ...pendingRun, answered_at: timestamp } }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, checkpoint: { ...checkpoint, response: "raw learner response" } }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, run: { ...pendingRun, answer_idempotency_key: "private" } }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, grade: { correct: true, score: 1, max_score: 1, grader_version: "v1", raw_score: 1 } }).success).toBe(false);
    expect(activeRecallReadResponseSchema.safeParse({ ...pending, source_chunk_ids: ["source-1"] }).success).toBe(false);
  });

  it("accepts only strict, bounded learner requests", () => {
    const begin = {
      course_id: "course-1",
      expected_revision: 0,
      idempotency_key: "active-recall-begin-01",
    };
    expect(activeRecallProgressionRequestSchema.safeParse(begin).success).toBe(true);
    expect(activeRecallProgressionRequestSchema.safeParse({ ...begin, source: "private" }).success).toBe(false);
    expect(activeRecallProgressionRequestSchema.safeParse({ ...begin, idempotency_key: "short" }).success).toBe(false);
    expect(activeRecallAnswerRequestSchema.safeParse({ ...begin, response: "chain rule" }).success).toBe(true);
    expect(activeRecallAnswerRequestSchema.safeParse({ ...begin, response: "  " }).success).toBe(false);
    expect(activeRecallAnswerRequestSchema.safeParse({ ...begin, response: "chain rule", answer_key: "private" }).success).toBe(false);
  });
});
