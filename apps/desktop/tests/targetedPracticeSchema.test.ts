import { describe, expect, it } from "vitest";
import {
  targetedPracticeAnswerRequestSchema,
  targetedPracticeProgressionRequestSchema,
  targetedPracticeProgressionResponseSchema,
  targetedPracticeReadResponseSchema,
  studySessionReadResponseSchema,
} from "@keen/api-client";

const timestamp = "2026-07-18T10:00:00+00:00";
const unit = { id: "unit-1", ordinal: 0, estimated_minutes: 10, status: "active" as const, created_at: timestamp, updated_at: timestamp };
const plan = { id: "plan-1", session_id: "session-1", version: 1, units: [unit, { ...unit, id: "unit-2", ordinal: 1, status: "locked" as const }] };
const successor = { ...unit, id: "unit-2", ordinal: 1, status: "active" as const };
const advancedPlan = { ...plan, units: [{ ...unit, status: "completed" as const }, successor] };
function session(status: string, currentUnitId = unit.id) { return { id: "session-1", course_id: "course-1", status, revision: 2, progress: 0.1, estimated_minutes: 20, current_unit_id: currentUnitId, created_at: timestamp, updated_at: timestamp, started_at: timestamp, finished_at: null }; }
const checkpoint = { id: "checkpoint-1", kind: "practice" as const, prompt: "The [...] rule follows the active-recall concept.", status: "pending" as const, created_at: timestamp, answered_at: null };
const run = { id: "run-1", status: "pending" as const, checkpoint_id: checkpoint.id, generator_version: "targeted-practice/1.0.0", created_at: timestamp, answered_at: null, cancelled_at: null, cancellation_reason: null };
const notStarted = { outcome: "not_started" as const, course_id: "course-1", session: session("practicing"), plan, checkpoint: null, current_unit: unit, run: null, grade: null };
const pending = { ...notStarted, outcome: "pending" as const, checkpoint, run };
const answered = { ...pending, outcome: "answered" as const, session: session("summarizing"), checkpoint: { ...checkpoint, status: "answered" as const, answered_at: timestamp }, run: { ...run, status: "answered" as const, answered_at: timestamp }, grade: { correct: true, score: 1, max_score: 1, grader_version: "objective/1" } };
const advanced = { ...answered, session: session("studying", successor.id), plan: advancedPlan, current_unit: successor };
const finalAnswered = { ...answered, session: session("summarizing", successor.id), plan: advancedPlan, current_unit: successor };
const cancelled = { ...pending, outcome: "cancelled" as const, session: session("cancelled"), checkpoint: { ...checkpoint, status: "skipped" as const }, run: { ...run, status: "cancelled" as const, cancelled_at: timestamp, cancellation_reason: "session_cancelled" as const } };

describe("targeted-practice API schemas", () => {
  it("accepts public lifecycle states, including cancellation before begin", () => {
    expect(targetedPracticeReadResponseSchema.safeParse(notStarted).success).toBe(true);
    expect(targetedPracticeReadResponseSchema.safeParse(pending).success).toBe(true);
    expect(targetedPracticeReadResponseSchema.safeParse(answered).success).toBe(true);
    expect(targetedPracticeReadResponseSchema.safeParse(cancelled).success).toBe(true);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...notStarted, outcome: "cancelled", session: session("failed") }).success).toBe(true);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...pending, session: session("paused") }).success).toBe(true);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...answered, session: session("paused") }).success).toBe(true);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...pending, outcome: "applied" }).success).toBe(true);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...answered, outcome: "replayed" }).success).toBe(true);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...answered, outcome: "replayed", session: session("active_recall") }).success).toBe(true);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...answered, outcome: "replayed", plan: { ...plan, units: [unit, { ...plan.units[1], status: "active" as const }] } }).success).toBe(false);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...answered, outcome: "applied", session: session("active_recall") }).success).toBe(false);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...advanced, outcome: "applied" }).success).toBe(true);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...finalAnswered, outcome: "applied" }).success).toBe(true);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...advanced, outcome: "applied", plan, current_unit: unit, session: session("studying") }).success).toBe(false);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...advanced, outcome: "applied", session: session("summarizing", successor.id) }).success).toBe(true);
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...advanced, outcome: "applied", session: session("summarizing", unit.id), current_unit: unit }).success).toBe(false);
    const third = { ...successor, id: "unit-3", ordinal: 2 };
    const nonAdjacent = { ...advanced, plan: { ...advancedPlan, units: [{ ...unit, status: "completed" as const }, { ...successor, status: "ready" as const }, third] }, current_unit: third, session: session("studying", third.id) };
    expect(targetedPracticeProgressionResponseSchema.safeParse({ ...nonAdjacent, outcome: "applied" }).success).toBe(false);
  });

  it("rejects private fields, forged scopes, invalid phases, and malformed relationships", () => {
    expect(targetedPracticeReadResponseSchema.safeParse({ ...pending, source: "private" }).success).toBe(false);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...pending, checkpoint: { ...checkpoint, response: "private" } }).success).toBe(false);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...pending, run: { ...run, answer_key: "private" } }).success).toBe(false);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...pending, session: { ...session("practicing"), course_id: "course-2" } }).success).toBe(false);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...pending, run: { ...run, checkpoint_id: "checkpoint-x" } }).success).toBe(false);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...pending, session: session("summarizing") }).success).toBe(false);
    expect(targetedPracticeReadResponseSchema.safeParse({ ...notStarted, outcome: "cancelled", session: session("paused") }).success).toBe(false);
  });

  it("accepts only bounded strict learner commands", () => {
    const begin = { course_id: "course-1", expected_revision: 2, idempotency_key: "practice-begin-0001" };
    expect(targetedPracticeProgressionRequestSchema.safeParse(begin).success).toBe(true);
    expect(targetedPracticeProgressionRequestSchema.safeParse({ ...begin, source: "private" }).success).toBe(false);
    expect(targetedPracticeAnswerRequestSchema.safeParse({ ...begin, response: "chain rule" }).success).toBe(true);
    expect(targetedPracticeAnswerRequestSchema.safeParse({ ...begin, response: "   " }).success).toBe(false);
    expect(targetedPracticeAnswerRequestSchema.safeParse({ ...begin, response: "chain rule", answer_key: "private" }).success).toBe(false);
  });

  it("fails closed on forged, missing, or non-unique current-unit pointers", () => {
    const publicUnits = [
      { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"], title: "First", objective: "Read first.", content: "First source.", estimated_minutes: 10, status: "completed" as const },
      { id: "unit-2", ordinal: 1, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-2"], title: "Second", objective: "Read second.", content: "Second source.", estimated_minutes: 10, status: "active" as const },
    ];
    const publicPlan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Use indexed sources.", units: publicUnits };
    const publicSession = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Study", mode: "study" as const, goal: "Learn.", estimated_minutes: 20, status: "studying" as const, progress: 0.5, revision: 3, created_at: timestamp, updated_at: timestamp, started_at: timestamp };
    const valid = { outcome: "ready" as const, course_id: "course-1", session: publicSession, plan: publicPlan, current_unit_id: "unit-2", recovery_action: null };
    expect(studySessionReadResponseSchema.safeParse(valid).success).toBe(true);
    expect(studySessionReadResponseSchema.safeParse({ ...valid, current_unit_id: "unit-1" }).success).toBe(false);
    expect(studySessionReadResponseSchema.safeParse({ ...valid, current_unit_id: null }).success).toBe(false);
    expect(studySessionReadResponseSchema.safeParse({ ...valid, plan: { ...publicPlan, units: [{ ...publicUnits[0], status: "active" as const }, publicUnits[1]] } }).success).toBe(false);
  });
});
