import { z } from "zod";

const identifier = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const isoDateTime = z.string().datetime({ offset: true });

export const studyPlanProposalCreateRequestSchema = z.object({
  courseId: identifier,
  expectedSessionRevision: z.number().int().nonnegative(),
  expectedPlanVersion: z.number().int().positive(),
  targetUnitId: identifier,
  request: z.literal("insert_source_grounded_prerequisite"),
  triggerOrigin: z.enum(["learner_request", "adaptive_evidence"]).default("learner_request"),
  idempotencyKey: z.string().min(16).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/),
}).strict();

export const studyPlanProposalDecisionRequestSchema = z.object({
  courseId: identifier,
  artifactId: identifier,
  expectedSessionRevision: z.number().int().nonnegative(),
  expectedPlanVersion: z.number().int().positive(),
  decision: z.enum(["accept", "keep"]),
  idempotencyKey: z.string().min(16).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/),
}).strict();

export const studyPlanProposalUndoRequestSchema = z.object({
  courseId: identifier,
  expectedSessionRevision: z.number().int().nonnegative(),
  idempotencyKey: z.string().min(16).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/),
}).strict();

const planProposalRunSchema = z.object({
  id: identifier,
  status: z.enum(["queued", "running", "waiting_approval", "completed", "failed", "cancelled", "interrupted"]),
  provider: z.string().min(1).max(128),
  model: z.string().min(1).max(256),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
  errorCode: z.string().min(1).max(128).nullable(),
}).strict();

const planProposalUnitSchema = z.object({
  id: identifier,
  ordinal: z.number().int().nonnegative(),
  title: z.string().min(1).max(500),
  objective: z.string().min(1).max(2_000),
  estimatedMinutes: z.number().int().positive(),
  status: z.string().min(1).max(80),
}).strict();

const planProposalSourceSchema = z.object({
  sourceHandle: identifier,
  chunkId: z.string().min(1).max(256),
  documentId: z.string().min(1).max(256),
  documentVersionId: z.string().min(1).max(256),
  chunkContentHash: sha256,
  documentName: z.string().min(1).max(512),
  pageNumber: z.number().int().positive(),
  sectionPath: z.array(z.string()).max(16),
  quote: z.string().min(1).max(12_000),
  geometry: z.record(z.unknown()).nullable(),
  metadata: z.record(z.unknown()),
}).strict();

export const studyPlanProposalArtifactSchema = z.object({
  kind: z.literal("study_plan_proposal_artifact"),
  schemaVersion: z.literal(1),
  artifactId: identifier,
  profileId: z.literal("learning.plan-proposal.source-grounded.v1"),
  profileDefinitionHash: sha256,
  baseSessionRevision: z.number().int().nonnegative(),
  basePlanId: identifier,
  basePlanVersion: z.number().int().positive(),
  summary: z.string().min(1).max(1_000),
  reason: z.string().min(1).max(1_000),
  currentPlan: z.object({
    units: z.array(planProposalUnitSchema).min(2).max(8),
  }).strict(),
  operation: z.object({
    kind: z.literal("insert_prerequisite"),
    beforeUnitId: identifier,
    title: z.string().min(1).max(120),
    objective: z.string().min(1).max(500),
    estimatedMinutes: z.number().int().min(5).max(30),
    selectedSourceHandles: z.array(identifier).min(1).max(8),
  }).strict(),
  sources: z.array(planProposalSourceSchema).min(1).max(8),
  decision: z.object({
    status: z.enum(["unapplied", "pending", "accepted", "rejected", "undone"]),
    applyAvailable: z.boolean(),
  }).strict(),
}).strict().superRefine((value, context) => {
  if (!value.currentPlan.units.some((unit) => unit.id === value.operation.beforeUnitId)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["operation", "beforeUnitId"],
      message: "Proposal target must exist in the frozen current plan.",
    });
  }
  const sourceHandles = new Set(value.sources.map((source) => source.sourceHandle));
  if (value.operation.selectedSourceHandles.some((handle) => !sourceHandles.has(handle))) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["operation", "selectedSourceHandles"],
      message: "Proposal source handles must resolve to durable source snapshots.",
    });
  }
});

export const studyPlanProposalResponseSchema = z.object({
  status: z.enum(["none", "queued", "running", "ready", "stale", "unavailable", "accepted", "rejected", "undone"]),
  courseId: identifier,
  sessionId: identifier,
  reason: z.string().min(1).max(256).nullable(),
  run: planProposalRunSchema.nullable(),
  artifact: studyPlanProposalArtifactSchema.nullable(),
  receipt: z.object({
    proposalId: identifier,
    status: z.enum(["accepted", "rejected", "undone"]),
    planVersion: z.number().int().positive().nullable(),
    effectiveAfterCurrentStep: z.boolean(),
    undoAvailable: z.boolean(),
    undoUntil: isoDateTime.nullable(),
    message: z.string().min(1).max(1_000),
  }).strict().nullable(),
  trigger: z.object({
    origin: z.enum(["learner_request", "adaptive_evidence"]),
    reasonCode: z.enum([
      "learner_requested_prerequisite",
      "low_confidence_incorrect_recall_after_intervention",
    ]),
    evidenceIds: z.array(identifier).max(3),
    whyNow: z.string().min(1).max(1_000),
    learnerApprovalRequired: z.literal(true),
  }).strict().nullable().default(null),
}).strict().superRefine((value, context) => {
  if (["queued", "running", "ready", "stale", "unavailable", "accepted", "rejected", "undone"].includes(value.status) && value.run === null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["run"],
      message: "Run-backed Plan Proposal state requires its durable run.",
    });
  }
  if (["ready", "stale", "accepted", "rejected", "undone"].includes(value.status) && value.artifact === null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["artifact"],
      message: "Ready or stale Plan Proposal state requires its durable artifact.",
    });
  }
  if (["accepted", "rejected", "undone"].includes(value.status) && value.receipt === null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["receipt"],
      message: "Resolved Plan Proposal state requires its operation receipt.",
    });
  }
  if (!["accepted", "rejected", "undone"].includes(value.status) && value.receipt !== null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["receipt"],
      message: "Unresolved Plan Proposal state cannot expose a receipt.",
    });
  }
  if (value.status === "ready" && value.artifact?.decision.applyAvailable !== true) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["artifact", "decision", "applyAvailable"],
      message: "Current Plan Proposal must explicitly allow a learner decision.",
    });
  }
  if (
    value.artifact !== null
    && value.status !== "ready"
    && value.artifact.decision.applyAvailable !== false
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["artifact", "decision", "applyAvailable"],
      message: "Only a current ready Plan Proposal can allow a learner decision.",
    });
  }
  const resolvedStatuses = ["accepted", "rejected", "undone"] as const;
  if (
    resolvedStatuses.includes(value.status as (typeof resolvedStatuses)[number])
    && (
      value.artifact?.decision.status !== value.status
      || value.receipt?.status !== value.status
    )
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["status"],
      message: "Resolved Plan Proposal state, artifact, and receipt must agree.",
    });
  }
  if (
    value.status === "accepted"
    && (
      value.receipt?.planVersion === null
      || value.receipt?.effectiveAfterCurrentStep !== true
      || value.receipt?.undoUntil === null
    )
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["receipt"],
      message: "An accepted adjustment requires a deferred plan version and bounded Undo window.",
    });
  }
  if (
    value.status === "rejected"
    && (
      value.receipt?.planVersion !== null
      || value.receipt?.effectiveAfterCurrentStep !== false
      || value.receipt?.undoAvailable !== false
      || value.receipt?.undoUntil !== null
    )
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["receipt"],
      message: "Keeping the current plan cannot create a plan version or Undo state.",
    });
  }
  if (
    value.status === "undone"
    && (
      value.receipt?.planVersion === null
      || value.receipt?.effectiveAfterCurrentStep !== true
      || value.receipt?.undoAvailable !== false
      || value.receipt?.undoUntil === null
    )
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["receipt"],
      message: "An undone adjustment requires a restore version and cannot remain undoable.",
    });
  }
});

export type StudyPlanProposalCreateRequest = z.input<typeof studyPlanProposalCreateRequestSchema>;
export type StudyPlanProposalDecisionRequest = z.infer<typeof studyPlanProposalDecisionRequestSchema>;
export type StudyPlanProposalUndoRequest = z.infer<typeof studyPlanProposalUndoRequestSchema>;
export type StudyPlanProposalArtifact = z.infer<typeof studyPlanProposalArtifactSchema>;
export type StudyPlanProposalResponse = z.infer<typeof studyPlanProposalResponseSchema>;
