import {
  adaptiveActionCompleteRequestSchema,
  adaptiveActionCompleteResponseSchema,
  adaptiveStateResponseSchema,
} from "@keen/api-client";

const time = "2026-07-22T10:00:00+00:00";
const session = {
  id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Limits", mode: "study" as const,
  goal: "Understand limits.", estimated_minutes: 20, status: "practicing" as const, progress: 0.5, revision: 4,
  created_at: time, updated_at: time, started_at: time,
};
const unit = {
  id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"],
  title: "Definition", objective: "Read the definition.", content: "Existing source content.", estimated_minutes: 10, status: "active" as const,
};
const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Use the source.", units: [unit, { ...unit, id: "unit-2", ordinal: 1, source_chunk_ids: ["chunk-2"], status: "ready" as const }] };
const remediation = {
  id: "action-1", course_id: "course-1", session_id: "session-1", unit_id: "unit-1", kind: "remediate" as const,
  status: "pending" as const, reason_code: "active_recall_incorrect", policy_version: "adaptive-session-policy/1.0.0", revision: 0,
  created_at: time, started_at: null, completed_at: null, cancelled_at: null,
};

describe("adaptive study schemas", () => {
  it("accepts the strict action-required state and rejects foreign or invented relationships", () => {
    const value = { course_id: "course-1", session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: remediation };
    expect(adaptiveStateResponseSchema.parse(value).action?.reason_code).toBe("active_recall_incorrect");
    expect(adaptiveStateResponseSchema.safeParse({ ...value, extra: true }).success).toBe(false);
    expect(adaptiveStateResponseSchema.safeParse({ ...value, action: { ...remediation, course_id: "course-2" } }).success).toBe(false);
    expect(adaptiveStateResponseSchema.safeParse({ ...value, action: { ...remediation, status: "completed", completed_at: time } }).success).toBe(false);
    expect(adaptiveStateResponseSchema.safeParse({ ...value, current_unit: { ...unit, content: "Invented" } }).success).toBe(false);
  });

  it("requires a persisted pending practice action before adaptive practice", () => {
    const practice = { ...remediation, id: "action-2", kind: "practice" as const, reason_code: "active_recall_correct" as const };
    const required = { course_id: "course-1", session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required" as const, action: practice };
    expect(adaptiveStateResponseSchema.safeParse(required).success).toBe(true);
    expect(adaptiveStateResponseSchema.safeParse({ ...required, state: "canonical" }).success).toBe(false);
    expect(adaptiveStateResponseSchema.safeParse({ ...required, state: "legacy_canonical", action: null }).success).toBe(true);
  });

  it("validates action completion timestamps, next action, and request identity", () => {
    const completed = { ...remediation, status: "completed" as const, revision: 1, started_at: time, completed_at: time };
    const practice = { ...remediation, id: "action-2", kind: "practice" as const, reason_code: "remediation_completed" as const };
    const response = { outcome: "applied" as const, course_id: "course-1", session: { ...session, revision: 5 }, plan, completed_action: completed, current_action: practice };
    const parsedResponse = adaptiveActionCompleteResponseSchema.safeParse(response);
    if (!parsedResponse.success) throw new Error(JSON.stringify(parsedResponse.error.issues));
    expect(adaptiveActionCompleteResponseSchema.safeParse({ ...response, current_action: { ...practice, unit_id: "unit-2" } }).success).toBe(false);
    const consumedPractice = { ...practice, status: "completed" as const, revision: 1, started_at: time, completed_at: time };
    expect(adaptiveActionCompleteResponseSchema.safeParse({ ...response, outcome: "replayed", current_action: consumedPractice }).success).toBe(true);
    expect(adaptiveActionCompleteResponseSchema.safeParse({ ...response, current_action: consumedPractice }).success).toBe(false);
    expect(adaptiveActionCompleteResponseSchema.safeParse({ ...response, outcome: "replayed", current_action: { ...consumedPractice, kind: "remediate", reason_code: "active_recall_incorrect" } }).success).toBe(false);
    expect(adaptiveActionCompleteRequestSchema.safeParse({ course_id: "course-1", expected_action_revision: 0, idempotency_key: "adaptive-action-0001" }).success).toBe(true);
    expect(adaptiveActionCompleteRequestSchema.safeParse({ course_id: "course-1", expected_action_revision: 0, idempotency_key: "short" }).success).toBe(false);
  });
});
