import { describe, expect, it, vi } from "vitest";

import {
  createLearningCoreClient,
  LearningCoreRequestError,
  LearningCoreSchemaError,
} from "./client";
import {
  learningInterventionResponseSchema,
} from "./interventionSchemas";

const token = "a".repeat(64);
const timestamp = "2026-07-24T10:00:00+00:00";
const actions = [
  "Explain differently",
  "Show a source example",
  "Test me instead",
] as const;

const eligible = {
  status: "eligible",
  courseId: "course-1",
  sessionId: "session-1",
  reason: null,
  actions,
  run: null,
  artifact: {
    whyNow: "Your latest Recall did not meet the expected answer.",
    sources: [{
      sourceHandle: "source-1",
      documentId: "document-1",
      documentName: "Notes",
      pageNumber: 2,
      sectionPath: ["Limits"],
      metadata: { quoteTruncated: false },
    }],
    whatNext: {
      label: "Continue with a new Practice prompt.",
      action: "continue_practice",
    },
  },
  practice: null,
  fallback: { action: "source_review", label: "Return to source" },
};

const run = {
  id: "run-1",
  status: "completed",
  provider: "fixture",
  model: "bounded",
  createdAt: timestamp,
  updatedAt: timestamp,
  errorCode: null,
};

const readyArtifact = {
  kind: "learning_intervention_artifact",
  schemaVersion: 1,
  artifactId: "artifact-1",
  predecessor: null,
  profileId: "learning.intervention.source-grounded.v1",
  profileDefinitionHash: "a".repeat(64),
  playbookSlug: "source-grounded-rephrase",
  playbookVersion: 1,
  playbookDefinitionHash: "b".repeat(64),
  whyNow: "The persisted Recall was not correct.",
  summary: "A different formulation.",
  explanationMarkdown: "Use the cited source to connect the two changes.",
  sources: [{
    sourceHandle: "source-1",
    chunkId: "chunk-1",
    documentId: "document-1",
    documentVersionId: "version-1",
    chunkContentHash: "c".repeat(64),
    documentName: "Notes",
    pageNumber: 2,
    sectionPath: ["Limits"],
    quote: "A bounded source excerpt.",
    geometry: null,
    metadata: { contentTrust: "untrusted_course_data" },
  }],
  whatNext: {
    label: "Continue Practice.",
    action: "continue_practice",
    practiceRunId: "practice-1",
    practicePrompt: "Fill in a different missing term: [...]",
    sessionRevision: 8,
  },
};

const ready = {
  status: "ready",
  courseId: "course-1",
  sessionId: "session-1",
  reason: null,
  actions,
  run,
  artifact: readyArtifact,
  practice: readyArtifact.whatNext,
  fallback: null,
};

const response = (value: unknown, status = 200, contentType = "application/json") =>
  new Response(
    contentType === "application/json" ? JSON.stringify(value) : String(value),
    { status, headers: { "Content-Type": contentType } },
  );

describe("LearningCoreClient learning intervention contracts", () => {
  it("accepts only the closed action set and a durable source-linked artifact", () => {
    expect(learningInterventionResponseSchema.parse(eligible).status).toBe("eligible");
    expect(learningInterventionResponseSchema.parse(ready).status).toBe("ready");
    expect(
      learningInterventionResponseSchema.safeParse({
        ...ready,
        actions: [...actions, "Ask anything"],
      }).success,
    ).toBe(false);
    expect(
      learningInterventionResponseSchema.safeParse({
        ...ready,
        artifact: { ...readyArtifact, hiddenReasoning: "private trace" },
      }).success,
    ).toBe(false);
    expect(
      learningInterventionResponseSchema.safeParse({
        ...ready,
        artifact: {
          ...readyArtifact,
          sources: [{ ...readyArtifact.sources[0], chunkContentHash: "forged" }],
        },
      }).success,
    ).toBe(false);
  });

  it("uses canonical create/current/cancel paths and validates responses", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(eligible))
      .mockResolvedValueOnce(response({ ...eligible, status: "queued", run: { ...run, status: "queued" }, artifact: null, fallback: null }, 202))
      .mockResolvedValueOnce(response({ ...ready, status: "cancelled", artifact: null, practice: null, fallback: { action: "source_review", label: "Return to source" }, reason: "cancelled", run: { ...run, status: "cancelled" } }));
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      fetchMock as unknown as typeof fetch,
    );

    await expect(client.getCurrentLearningIntervention("session-1", "course-1")).resolves.toMatchObject({ status: "eligible" });
    await expect(client.startLearningIntervention("session-1", {
      courseId: "course-1",
      unitId: "unit-1",
      expectedSessionRevision: 7,
      intent: "explain_differently",
      idempotencyKey: "intervention-start-0001",
      predecessorRunId: "run-previous",
      predecessorArtifactId: "artifact-previous",
    })).resolves.toMatchObject({ status: "queued" });
    await expect(client.cancelLearningIntervention("session-1", "run-1", "course-1")).resolves.toMatchObject({ status: "cancelled" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8080/v1/study-sessions/session-1/interventions/current?courseId=course-1",
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "http://127.0.0.1:8080/v1/study-sessions/session-1/interventions",
    );
    expect(fetchMock.mock.calls[2]?.[0]).toBe(
      "http://127.0.0.1:8080/v1/study-sessions/session-1/interventions/run-1/cancel",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({
      predecessorRunId: "run-previous",
      predecessorArtifactId: "artifact-previous",
    });
  });

  it("rejects invalid identifiers, idempotency keys, and malformed success payloads", async () => {
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => response({ ok: true })) as unknown as typeof fetch,
    );
    await expect(Promise.resolve().then(() => client.getCurrentLearningIntervention("../../session", "course-1")))
      .rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.startLearningIntervention("session-1", {
      courseId: "course-1",
      unitId: "unit-1",
      expectedSessionRevision: 7,
      intent: "source_example" as never,
      idempotencyKey: "short",
    }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(Promise.resolve().then(() => client.startLearningIntervention("session-1", {
      courseId: "course-1",
      unitId: "unit-1",
      expectedSessionRevision: 7,
      intent: "explain_differently",
      idempotencyKey: "intervention-start-0002",
      predecessorRunId: "run-previous",
    }))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(client.getCurrentLearningIntervention("session-1", "course-1"))
      .rejects.toBeInstanceOf(LearningCoreSchemaError);
  });

  it("parses only typed public intervention events and supports Last-Event-ID replay", async () => {
    const eventBody = [
      "id: event-2",
      "event: artifact_ready",
      `data: ${JSON.stringify(readyArtifact)}`,
      "",
      "id: event-3",
      "event: done",
      'data: {"status":"ready","artifactId":"artifact-1"}',
      "",
    ].join("\n");
    const fetchMock = vi.fn(async () => response(eventBody, 200, "text/event-stream"));
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      fetchMock as unknown as typeof fetch,
    );
    const events = [];
    for await (const event of client.learningInterventionEvents(
      "session-1",
      "run-1",
      "course-1",
      { lastEventId: "event-1" },
    )) {
      events.push(event);
    }
    expect(events.map((event) => event.event)).toEqual(["artifact_ready", "done"]);
    const calls = fetchMock.mock.calls as unknown as [unknown, RequestInit][];
    const headers = new Headers(calls[0]?.[1].headers);
    expect(headers.get("Last-Event-ID")).toBe("event-1");
  });
});
