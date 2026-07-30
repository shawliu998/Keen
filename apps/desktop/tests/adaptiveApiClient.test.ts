import { LearningCoreClient, LearningCoreRequestError, LearningCoreSchemaError } from "@keen/api-client";

const time = "2026-07-22T10:00:00+00:00";
const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Limits", mode: "study", goal: "Understand limits.", estimated_minutes: 20, status: "practicing", progress: 0.5, revision: 4, created_at: time, updated_at: time, started_at: time };
const unit = { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"], title: "Definition", objective: "Read the definition.", content: "Existing source content.", estimated_minutes: 10, status: "active" };
const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Use the source.", units: [unit, { ...unit, id: "unit-2", ordinal: 1, status: "ready", source_chunk_ids: ["chunk-2"] }] };
const action = { id: "action-1", course_id: "course-1", session_id: "session-1", unit_id: "unit-1", kind: "remediate", status: "pending", reason_code: "active_recall_incorrect", policy_version: "adaptive-session-policy/1.0.0", revision: 0, created_at: time, started_at: null, completed_at: null, cancelled_at: null };

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("adaptive learning-core client", () => {
  it("uses course-scoped GET and revision/idempotency checked completion", async () => {
    const completed = { ...action, status: "completed", revision: 1, started_at: time, completed_at: time };
    const practice = { ...action, id: "action-2", kind: "practice", reason_code: "remediation_completed" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ course_id: "course-1", session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required", action }))
      .mockResolvedValueOnce(response({ outcome: "applied", course_id: "course-1", session: { ...session, revision: 5 }, plan, completed_action: completed, current_action: practice }));
    const client = new LearningCoreClient("http://127.0.0.1:8080", "x".repeat(32), fetchMock);
    await expect(client.getStudySessionAdaptiveState("session-1", "course-1")).resolves.toMatchObject({ state: "action_required" });
    await expect(client.completeStudySessionAdaptiveAction("session-1", "action-1", { course_id: "course-1", expected_action_revision: 0, idempotency_key: "adaptive-action-0001" })).resolves.toMatchObject({ outcome: "applied" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/adaptive-state?course_id=course-1");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("http://127.0.0.1:8080/v1/study-sessions/session-1/adaptive-actions/action-1/complete");
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({ course_id: "course-1", expected_action_revision: 0, idempotency_key: "adaptive-action-0001" });
  });

  it("rejects invalid requests and cross-scope responses", async () => {
    const client = new LearningCoreClient("http://127.0.0.1:8080", "x".repeat(32), vi.fn(async () => response({ course_id: "course-1", session, plan, current_unit: unit, current_unit_id: "unit-1", state: "action_required", action: { ...action, session_id: "foreign" } })));
    await expect(client.getStudySessionAdaptiveState("session-1", "course-1")).rejects.toBeInstanceOf(LearningCoreSchemaError);
    expect(() => client.completeStudySessionAdaptiveAction("session-1", "action-1", { course_id: "course-1", expected_action_revision: 0, idempotency_key: "short" })).toThrow(LearningCoreRequestError);
  });

  it("accepts only the truthful completed-practice projection on late replay", async () => {
    const completed = { ...action, status: "completed", revision: 1, started_at: time, completed_at: time };
    const consumedPractice = { ...action, id: "action-2", kind: "practice", status: "completed", reason_code: "remediation_completed", revision: 1, started_at: time, completed_at: time };
    const fetchMock = vi.fn(async () => response({ outcome: "replayed", course_id: "course-1", session: { ...session, revision: 6 }, plan, completed_action: completed, current_action: consumedPractice }));
    const client = new LearningCoreClient("http://127.0.0.1:8080", "x".repeat(32), fetchMock);
    await expect(client.completeStudySessionAdaptiveAction("session-1", "action-1", { course_id: "course-1", expected_action_revision: 0, idempotency_key: "adaptive-action-0001" })).resolves.toMatchObject({ outcome: "replayed", current_action: { status: "completed", kind: "practice" } });
  });
});
