import {
  createLearningCoreClient,
  LearningCoreRequestError,
  LearningCoreSchemaError,
} from "@keen/api-client";

const token = "a".repeat(64);
const now = "2026-07-22T08:00:00+00:00";
const request = {
  course_id: "course-1",
  goal: "Understand Bayesian updating",
  client_request_id: "11111111-1111-4111-8111-111111111111",
  idempotency_key: "focused-study-request-0001",
};
const task = {
  id: "task-focused-1", course_id: "course-1", concept_id: "concept-1", title: "Bayesian updating",
  reason: "Requested focused study goal.", estimated_minutes: 20, status: "upcoming" as const,
  source_type: "focused_study_request", source_id: request.client_request_id,
};
const session = {
  id: "session-focused-1", course_id: "course-1", originating_task_id: task.id, title: "Bayesian updating",
  mode: "study" as const, goal: request.goal, estimated_minutes: 20, status: "studying" as const,
  progress: 0, revision: 0, created_at: now, updated_at: now, started_at: now,
};
const plan = {
  id: "plan-focused-1", session_id: session.id, version: 1, rationale: "Follow the indexed source sequence.",
  units: [
    { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-1"], title: "Prior", objective: "Connect the prior to the evidence.", content: "Source excerpt.", estimated_minutes: 10, status: "active" as const },
    { id: "unit-2", ordinal: 1, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-2"], title: "Posterior", objective: "Explain the posterior update.", content: "Source excerpt.", estimated_minutes: 10, status: "ready" as const },
  ],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("focused study API client", () => {
  it("posts the stable goal-owned identity and accepts created and replayed results", async () => {
    const created = { outcome: "session_created" as const, course_id: "course-1", task, session, plan, blocked_reason: null, recovery_action: null };
    const replayed = { ...created, outcome: "replayed" as const };
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(created, 201)).mockResolvedValueOnce(jsonResponse(replayed));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.focusedStudyRequest(request)).resolves.toEqual(created);
    await expect(client.focusedStudyRequest(request)).resolves.toEqual(replayed);
    expect(fetchMock.mock.calls.map((call) => JSON.parse(String((call[1] as RequestInit).body)))).toEqual([request, request]);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8080/v1/focused-study-requests");
  });

  it("canonicalizes NFKC-compatible text and repeated whitespace before validation and response matching", async () => {
    const canonicalGoal = "Understand Bayesian updating";
    const rawRequest = { ...request, goal: "  Ｕｎｄｅｒｓｔａｎｄ   Bayesian   updating  " };
    const canonicalSession = { ...session, goal: canonicalGoal };
    const created = { outcome: "session_created" as const, course_id: "course-1", task, session: canonicalSession, plan, blocked_reason: null, recovery_action: null };
    const fetchMock = vi.fn(async () => jsonResponse(created, 201));
    const client = createLearningCoreClient("http://127.0.0.1:8080", token, fetchMock as unknown as typeof fetch);

    await expect(client.focusedStudyRequest(rawRequest)).resolves.toEqual(created);
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(JSON.parse(String(calls[0]?.[1].body))).toEqual({ ...request, goal: canonicalGoal });
  });

  it("accepts typed blocked recovery and rejects invalid request or goal drift", async () => {
    const blocked = { outcome: "blocked" as const, course_id: "course-1", task: null, session: null, plan: null, blocked_reason: "no_matching_indexed_source", recovery_action: "Index course material, then retry." };
    const blockedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(blocked)) as unknown as typeof fetch);
    await expect(blockedClient.focusedStudyRequest(request)).resolves.toEqual(blocked);

    const noFetch = vi.fn();
    const invalidClient = createLearningCoreClient("http://127.0.0.1:8080", token, noFetch as unknown as typeof fetch);
    await expect(Promise.resolve().then(() => invalidClient.focusedStudyRequest({ ...request, idempotency_key: "short" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => invalidClient.focusedStudyRequest({ ...request, goal: "x".repeat(1_001) }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => invalidClient.focusedStudyRequest({ ...request, goal: "Understand\u0000Bayes" }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    expect(noFetch).not.toHaveBeenCalled();

    const invalidBlockedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse({ ...blocked, blocked_reason: "no_indexed_source" })) as unknown as typeof fetch);
    await expect(invalidBlockedClient.focusedStudyRequest(request)).rejects.toBeInstanceOf(LearningCoreSchemaError);

    const drifted = { outcome: "replayed" as const, course_id: "course-1", task, session: { ...session, goal: "A different goal" }, plan, blocked_reason: null, recovery_action: null };
    const driftedClient = createLearningCoreClient("http://127.0.0.1:8080", token, vi.fn(async () => jsonResponse(drifted)) as unknown as typeof fetch);
    await expect(driftedClient.focusedStudyRequest(request)).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});
