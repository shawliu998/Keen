import { z } from "zod";

const identifier = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const isoDateTime = z.string().datetime({ offset: true });

export const learningInterventionIntentSchema = z.enum([
  "explain_differently",
  "show_source_example",
  "test_me_instead",
]);

export const learningInterventionActionSchema = z.enum([
  "Explain differently",
  "Show a source example",
  "Test me instead",
]);

export const learningInterventionCreateRequestSchema = z.object({
  courseId: identifier,
  unitId: identifier,
  expectedSessionRevision: z.number().int().nonnegative(),
  intent: learningInterventionIntentSchema,
  idempotencyKey: z.string().min(16).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/),
  predecessorRunId: identifier.optional(),
  predecessorArtifactId: identifier.optional(),
}).strict().superRefine((value, context) => {
  if ((value.predecessorRunId === undefined) !== (value.predecessorArtifactId === undefined)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["predecessorRunId"],
      message: "Intervention predecessor identity must include both run and artifact IDs.",
    });
  }
});

export const learningInterventionRunSchema = z.object({
  id: identifier,
  status: z.enum(["queued", "running", "waiting_approval", "completed", "failed", "cancelled", "interrupted"]),
  provider: z.string().min(1).max(128),
  model: z.string().min(1).max(256),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
  errorCode: z.string().min(1).max(128).nullable(),
}).strict();

const sourcePreviewSchema = z.object({
  sourceHandle: identifier,
  documentId: z.string().min(1).max(256),
  documentName: z.string().min(1).max(512),
  pageNumber: z.number().int().positive(),
  sectionPath: z.array(z.string()).max(16),
  metadata: z.record(z.unknown()),
}).strict();

const sourceSchema = sourcePreviewSchema.extend({
  chunkId: z.string().min(1).max(256),
  documentVersionId: z.string().min(1).max(256),
  chunkContentHash: sha256,
  quote: z.string().min(1).max(12_000),
  geometry: z.record(z.unknown()).nullable(),
}).strict();

const nextActionSchema = z.object({
  label: z.string().min(1).max(500),
  action: z.literal("continue_practice"),
  practiceRunId: identifier.nullable().optional(),
  practicePrompt: z.string().min(1).max(20_000).nullable().optional(),
  sessionRevision: z.number().int().nonnegative().nullable().optional(),
}).strict();

const eligibleArtifactSchema = z.object({
  whyNow: z.string().min(1).max(1_000),
  sources: z.array(sourcePreviewSchema).min(1).max(8),
  whatNext: nextActionSchema,
}).strict();

const artifactPredecessorSchema = z.object({
  runId: identifier,
  artifactId: identifier,
}).strict();

export const learningInterventionArtifactSchema = z.object({
  kind: z.literal("learning_intervention_artifact"),
  schemaVersion: z.literal(1),
  artifactId: identifier,
  predecessor: artifactPredecessorSchema.nullable().optional(),
  profileId: z.literal("learning.intervention.source-grounded.v1"),
  profileDefinitionHash: sha256,
  playbookSlug: z.string().min(1).max(128),
  playbookVersion: z.number().int().positive(),
  playbookDefinitionHash: sha256,
  whyNow: z.string().min(1).max(1_000),
  summary: z.string().min(1).max(1_000),
  explanationMarkdown: z.string().min(1).max(20_000),
  sources: z.array(sourceSchema).min(1).max(8),
  whatNext: nextActionSchema.extend({
    practiceRunId: identifier,
    practicePrompt: z.string().min(1).max(20_000),
    sessionRevision: z.number().int().nonnegative(),
  }).strict(),
}).strict();

const fallbackSchema = z.object({
  action: z.literal("source_review"),
  label: z.string().min(1).max(500),
  retryable: z.boolean().nullable().optional(),
}).strict();

export const learningInterventionResponseSchema = z.object({
  status: z.enum(["ineligible", "eligible", "queued", "running", "ready", "cancelled", "source_review", "practice_ready"]),
  courseId: identifier,
  sessionId: identifier,
  reason: z.string().min(1).max(256).nullable(),
  actions: z.array(learningInterventionActionSchema).max(3),
  run: learningInterventionRunSchema.nullable(),
  artifact: z.union([eligibleArtifactSchema, learningInterventionArtifactSchema]).nullable(),
  practice: nextActionSchema.nullable(),
  fallback: fallbackSchema.nullable(),
}).strict().superRefine((value, context) => {
  if (value.status === "eligible" && (value.artifact === null || "kind" in value.artifact)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["artifact"], message: "Eligible intervention requires its projected reason, sources, and next action." });
  }
  if (value.status === "ready" && (value.artifact === null || !("kind" in value.artifact))) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["artifact"], message: "Ready intervention requires a validated durable artifact." });
  }
  if (value.status === "ready" && value.practice === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["practice"], message: "Ready intervention requires the existing Practice handoff." });
  }
  if (value.status === "practice_ready" && value.practice === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["practice"], message: "Practice handoff is required." });
  }
  if (["queued", "running", "ready", "cancelled"].includes(value.status) && value.run === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["run"], message: "Run-backed intervention status requires a durable Agent run." });
  }
  if (value.status === "source_review" && value.fallback === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["fallback"], message: "Source review status requires a truthful fallback." });
  }
});

const publicEventBase = {
  id: identifier,
};

export const learningInterventionEventSchema = z.discriminatedUnion("event", [
  z.object({ ...publicEventBase, event: z.literal("started"), data: z.object({ runId: identifier }).strict() }).strict(),
  z.object({ ...publicEventBase, event: z.enum(["running", "searching_sources", "source_context_ready"]), data: z.object({ status: z.string().min(1).max(80) }).strict() }).strict(),
  z.object({ ...publicEventBase, event: z.literal("artifact_ready"), data: learningInterventionArtifactSchema }).strict(),
  z.object({ ...publicEventBase, event: z.literal("done"), data: z.object({ status: z.literal("ready"), artifactId: identifier }).strict() }).strict(),
  z.object({ ...publicEventBase, event: z.enum(["cancelled", "source_review"]), data: z.object({ status: z.string().min(1).max(80), reason: z.string().min(1).max(128) }).strict() }).strict(),
]);

export type LearningInterventionIntent = z.infer<typeof learningInterventionIntentSchema>;
export type LearningInterventionCreateRequest = z.infer<typeof learningInterventionCreateRequestSchema>;
export type LearningInterventionArtifact = z.infer<typeof learningInterventionArtifactSchema>;
export type LearningInterventionResponse = z.infer<typeof learningInterventionResponseSchema>;
export type LearningInterventionEvent = z.infer<typeof learningInterventionEventSchema>;
