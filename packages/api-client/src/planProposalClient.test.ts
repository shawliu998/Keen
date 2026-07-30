import { describe, expect, it, vi } from "vitest";

import {
  createLearningCoreClient,
  LearningCoreRequestError,
  LearningCoreSchemaError,
} from "./client";
import { studyPlanProposalResponseSchema } from "./planProposalSchemas";

const token = "a".repeat(64);
const timestamp = "2026-07-26T10:00:00+00:00";
const run = {
  id: "run-plan-1",
  status: "completed",
  provider: "fixture",
  model: "bounded",
  createdAt: timestamp,
  updatedAt: timestamp,
  errorCode: null,
};
const artifact = {
  kind: "study_plan_proposal_artifact",
  schemaVersion: 1,
  artifactId: "plan-proposal-artifact-1",
  profileId: "learning.plan-proposal.source-grounded.v1",
  profileDefinitionHash: "b".repeat(64),
  baseSessionRevision: 7,
  basePlanId: "plan-1",
  basePlanVersion: 1,
  summary: "Add a prerequisite.",
  reason: "The cited source introduces an assumed concept.",
  currentPlan: {
    units: [
      {
        id: "unit-1",
        ordinal: 0,
        title: "Composition",
        objective: "Recall composition.",
        estimatedMinutes: 8,
        status: "active",
      },
      {
        id: "unit-2",
        ordinal: 1,
        title: "Chain rule",
        objective: "Differentiate a composition.",
        estimatedMinutes: 12,
        status: "locked",
      },
    ],
  },
  operation: {
    kind: "insert_prerequisite",
    beforeUnitId: "unit-2",
    title: "Composition refresher",
    objective: "Connect the inner and outer functions.",
    estimatedMinutes: 10,
    selectedSourceHandles: ["source-1"],
  },
  sources: [{
    sourceHandle: "source-1",
    chunkId: "chunk-1",
    documentId: "document-1",
    documentVersionId: "version-1",
    chunkContentHash: "c".repeat(64),
    documentName: "Calculus notes",
    pageNumber: 4,
    sectionPath: ["Chain rule"],
    quote: "A composition has an inner and outer function.",
    geometry: null,
    metadata: { contentTrust: "untrusted_course_data" },
  }],
  decision: { status: "pending", applyAvailable: true },
};
const ready = {
  status: "ready",
  courseId: "course-1",
  sessionId: "session-1",
  reason: null,
  run,
  artifact,
  receipt: null,
};
const response = (value: unknown, status = 200) => new Response(
  JSON.stringify(value),
  { status, headers: { "Content-Type": "application/json" } },
);

describe("LearningCoreClient Study Plan Proposal contracts", () => {
  it("accepts only a decision-ready, source-resolved proposal", () => {
    expect(studyPlanProposalResponseSchema.parse(ready).status).toBe("ready");
    expect(studyPlanProposalResponseSchema.safeParse({
      ...ready,
      artifact: {
        ...artifact,
        decision: { status: "unapplied", applyAvailable: false },
      },
    }).success).toBe(false);
    expect(studyPlanProposalResponseSchema.safeParse({
      ...ready,
      artifact: {
        ...artifact,
        operation: {
          ...artifact.operation,
          selectedSourceHandles: ["source-unissued"],
        },
      },
    }).success).toBe(false);
  });

  it("uses canonical current/create paths and strict request validation", async () => {
    const queued = {
      ...ready,
      status: "queued",
      run: { ...run, status: "queued" },
      artifact: null,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(ready))
      .mockResolvedValueOnce(response(queued, 202))
      .mockResolvedValueOnce(response(queued, 202));
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      fetchMock as unknown as typeof fetch,
    );
    await expect(
      client.getCurrentStudyPlanProposal("session-1", "course-1"),
    ).resolves.toMatchObject({ status: "ready" });
    await expect(client.startStudyPlanProposal("session-1", {
      courseId: "course-1",
      expectedSessionRevision: 7,
      expectedPlanVersion: 1,
      targetUnitId: "unit-2",
      request: "insert_source_grounded_prerequisite",
      idempotencyKey: "plan-proposal-start-0001",
    })).resolves.toMatchObject({ status: "queued" });
    await expect(client.startStudyPlanProposal("session-1", {
      courseId: "course-1",
      expectedSessionRevision: 7,
      expectedPlanVersion: 1,
      targetUnitId: "unit-2",
      request: "insert_source_grounded_prerequisite",
      triggerOrigin: "adaptive_evidence",
      idempotencyKey: "plan-proposal-start-0002",
    })).resolves.toMatchObject({ status: "queued" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8080/v1/study-sessions/session-1/plan-proposals/current?courseId=course-1",
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "http://127.0.0.1:8080/v1/study-sessions/session-1/plan-proposals",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({
      triggerOrigin: "learner_request",
    });
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({
      triggerOrigin: "adaptive_evidence",
    });
  });

  it("uses canonical decision and Undo paths with resolved receipts", async () => {
    const accepted = {
      ...ready,
      status: "accepted",
      artifact: {
        ...artifact,
        decision: { status: "accepted", applyAvailable: false },
      },
      receipt: {
        proposalId: "proposal-1",
        status: "accepted",
        planVersion: 2,
        effectiveAfterCurrentStep: true,
        undoAvailable: true,
        undoUntil: "2026-07-26T10:10:00+00:00",
        message: "The adjusted plan is saved.",
      },
    };
    const undone = {
      ...accepted,
      status: "undone",
      artifact: {
        ...artifact,
        decision: { status: "undone", applyAvailable: false },
      },
      receipt: {
        ...accepted.receipt,
        status: "undone",
        planVersion: 3,
        undoAvailable: false,
        message: "The adjustment was undone.",
      },
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(accepted))
      .mockResolvedValueOnce(response(undone));
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      fetchMock as unknown as typeof fetch,
    );

    await expect(client.decideStudyPlanProposal(
      "session-1",
      artifact.artifactId,
      {
        courseId: "course-1",
        artifactId: artifact.artifactId,
        expectedSessionRevision: 7,
        expectedPlanVersion: 1,
        decision: "accept",
        idempotencyKey: "plan-proposal-accept-0001",
      },
    )).resolves.toMatchObject({ status: "accepted" });
    await expect(client.undoStudyPlanProposal(
      "session-1",
      "proposal-1",
      {
        courseId: "course-1",
        expectedSessionRevision: 7,
        idempotencyKey: "plan-proposal-undo-0001",
      },
    )).resolves.toMatchObject({ status: "undone" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `http://127.0.0.1:8080/v1/study-sessions/session-1/plan-proposals/${artifact.artifactId}/decision`,
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "http://127.0.0.1:8080/v1/study-sessions/session-1/plan-proposals/proposal-1/undo",
    );
  });

  it("rejects impossible resolved decision receipts", () => {
    const accepted = {
      ...ready,
      status: "accepted",
      artifact: {
        ...artifact,
        decision: { status: "accepted", applyAvailable: false },
      },
      receipt: {
        proposalId: "proposal-1",
        status: "accepted",
        planVersion: 2,
        effectiveAfterCurrentStep: true,
        undoAvailable: true,
        undoUntil: "2026-07-26T10:10:00+00:00",
        message: "The adjusted plan is saved.",
      },
    };
    expect(studyPlanProposalResponseSchema.safeParse({
      ...accepted,
      receipt: { ...accepted.receipt, planVersion: null },
    }).success).toBe(false);
    expect(studyPlanProposalResponseSchema.safeParse({
      ...accepted,
      artifact: {
        ...accepted.artifact,
        decision: { status: "accepted", applyAvailable: true },
      },
    }).success).toBe(false);
    expect(studyPlanProposalResponseSchema.safeParse({
      ...accepted,
      status: "undone",
      artifact: {
        ...artifact,
        decision: { status: "undone", applyAvailable: false },
      },
      receipt: {
        ...accepted.receipt,
        status: "undone",
        planVersion: 3,
        undoAvailable: true,
      },
    }).success).toBe(false);
    expect(studyPlanProposalResponseSchema.safeParse({
      ...accepted,
      status: "rejected",
      artifact: {
        ...artifact,
        decision: { status: "rejected", applyAvailable: false },
      },
      receipt: {
        ...accepted.receipt,
        status: "rejected",
        planVersion: null,
        effectiveAfterCurrentStep: false,
        undoAvailable: false,
      },
    }).success).toBe(false);
  });

  it("rejects invalid requests and malformed success payloads", async () => {
    const client = createLearningCoreClient(
      "http://127.0.0.1:8080",
      token,
      vi.fn(async () => response({ ok: true })) as unknown as typeof fetch,
    );
    await expect(Promise.resolve().then(() => (
      client.startStudyPlanProposal("session-1", {
        courseId: "course-1",
        expectedSessionRevision: 7,
        expectedPlanVersion: 1,
        targetUnitId: "unit-2",
        request: "insert_source_grounded_prerequisite",
        idempotencyKey: "short",
      })
    ))).rejects.toBeInstanceOf(LearningCoreRequestError);
    await expect(
      client.getCurrentStudyPlanProposal("session-1", "course-1"),
    ).rejects.toBeInstanceOf(LearningCoreSchemaError);
  });
});
