import { z } from "zod";

const isoDateTimeSchema = z.string().datetime({ offset: true });
const agentIdentifierSchema = z.string().min(1).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
const agentToolNameSchema = z.string().min(1).max(80).regex(/^[a-z][a-z0-9_]{0,79}$/);
const agentErrorCodeSchema = z.string().min(1).max(80).regex(/^[a-z][a-z0-9_]{0,79}$/);

const hiddenReasoningKeys = new Set([
  "chain_of_thought",
  "hidden_reasoning",
  "internal_reasoning",
  "reasoning",
  "reasoning_trace",
  "scratchpad",
  "thoughts",
]);
const hiddenReasoningCompactKeys = new Set([...hiddenReasoningKeys].map((key) => key.replaceAll("_", "")));

function canonicalizeAgentKey(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/gu, "$1_$2")
    .replace(/[^A-Za-z0-9]+/gu, "_")
    .replace(/^_+|_+$/gu, "")
    .toLowerCase();
}

function validateAgentJson(value: unknown): string | null {
  let nodes = 0;
  let textCharacters = 0;

  const visit = (candidate: unknown, depth: number): string | null => {
    nodes += 1;
    if (nodes > 2_048) return "Agent JSON exceeds the maximum item count.";
    if (depth > 16) return "Agent JSON exceeds the maximum nesting depth.";
    if (typeof candidate === "string") {
      if (candidate.length > 65_536) return "Agent JSON contains an oversized string.";
      textCharacters += candidate.length;
      return textCharacters > 131_072 ? "Agent JSON exceeds the total text limit." : null;
    }
    if (candidate === null || typeof candidate === "boolean") return null;
    if (typeof candidate === "number") return Number.isFinite(candidate) ? null : "Agent JSON numbers must be finite.";
    if (Array.isArray(candidate)) {
      for (const child of candidate) {
        const error = visit(child, depth + 1);
        if (error) return error;
      }
      return null;
    }
    if (typeof candidate === "object") {
      const prototype = Object.getPrototypeOf(candidate);
      if (prototype !== Object.prototype && prototype !== null) return "Agent JSON must contain only plain objects.";
      for (const [key, child] of Object.entries(candidate)) {
        const normalized = canonicalizeAgentKey(key);
        if (hiddenReasoningKeys.has(normalized) || hiddenReasoningCompactKeys.has(normalized.replaceAll("_", ""))) {
          return "Agent JSON must not contain hidden reasoning.";
        }
        textCharacters += key.length;
        if (textCharacters > 131_072) return "Agent JSON exceeds the total text limit.";
        const error = visit(child, depth + 1);
        if (error) return error;
      }
      return null;
    }
    return "Agent JSON contains an unsupported value.";
  };

  return visit(value, 0);
}

const agentJsonObjectSchema = z.record(z.unknown()).superRefine((value, context) => {
  const error = validateAgentJson(value);
  if (error) context.addIssue({ code: z.ZodIssueCode.custom, message: error });
});

export const agentRunKindSchema = z.enum(["conversation", "deep_learn", "assessment", "review"]);
export const agentRunModeSchema = z.enum(["ask", "teach", "study", "review", "plan"]);
export const agentRunStatusSchema = z.enum([
  "queued", "running", "waiting_approval", "completed", "failed", "cancelled", "interrupted",
]);

export const agentRunCreateRequestSchema = z.object({
  kind: agentRunKindSchema,
  userIntent: z.string().min(1).max(5_000),
  mode: agentRunModeSchema,
  input: agentJsonObjectSchema.default({}),
  idempotencyKey: z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/),
  conversationId: agentIdentifierSchema.nullable().optional(),
  studySessionId: agentIdentifierSchema.nullable().optional(),
}).strict();

export const agentRunSchema = z.object({
  id: agentIdentifierSchema,
  kind: agentRunKindSchema,
  mode: agentRunModeSchema,
  status: agentRunStatusSchema,
  provider: z.string().min(1).max(200),
  model: z.string().min(1).max(200),
  errorCode: agentErrorCodeSchema.nullable(),
  errorDetail: z.string().min(1).max(4_000).nullable(),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
  startedAt: isoDateTimeSchema.nullable(),
  finishedAt: isoDateTimeSchema.nullable(),
}).strict().superRefine((run, context) => {
  const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(run.status);
  if (terminal !== (run.finishedAt !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Only terminal Agent runs may have finishedAt.", path: ["finishedAt"] });
  }
  if (run.status === "completed" && (run.errorCode !== null || run.errorDetail !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Completed Agent runs must not expose errors.", path: ["errorCode"] });
  }
  if (["failed", "cancelled", "interrupted"].includes(run.status) && run.errorCode === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Unsuccessful terminal Agent runs require an error code.", path: ["errorCode"] });
  }
});

export const agentCancelResponseSchema = z.object({
  accepted: z.boolean(),
  run: agentRunSchema,
}).strict();

export const agentMutationActionRequestSchema = z.object({
  idempotencyKey: z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/),
}).strict();

export const agentMutationActionResponseSchema = z.object({
  action: z.enum(["undo", "redo"]),
  runId: agentIdentifierSchema,
  targetMutationId: agentIdentifierSchema,
  invocationId: agentIdentifierSchema,
  mutationId: agentIdentifierSchema,
  entityType: z.literal("study_task"),
  entityId: z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/),
  operation: z.literal("update"),
  replayed: z.boolean(),
}).strict();

const agentEventDataSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("metadata"),
    data: z.object({
      runId: agentIdentifierSchema,
      provider: z.string().min(1).max(200),
      model: z.string().min(1).max(200),
      providerVersion: z.string().min(1).max(200),
    }).strict(),
  }).strict(),
  z.object({ type: z.literal("status"), data: z.object({ status: agentRunStatusSchema }).strict() }).strict(),
  z.object({
    type: z.literal("tool_start"),
    data: z.object({
      invocationId: agentIdentifierSchema,
      toolName: agentToolNameSchema,
      replayCandidate: z.boolean(),
    }).strict(),
  }).strict(),
  z.object({
    type: z.literal("tool_result"),
    data: z.union([
      z.object({
        invocationId: agentIdentifierSchema,
        toolName: z.literal("undo_state_mutation"),
        action: z.enum(["undo", "redo"]),
        targetMutationId: agentIdentifierSchema,
        mutationId: agentIdentifierSchema,
        replayed: z.boolean(),
      }).strict(),
      z.object({
        callId: agentIdentifierSchema,
        invocationId: agentIdentifierSchema,
        toolName: agentToolNameSchema,
        result: agentJsonObjectSchema,
        replayed: z.literal(true),
      }).strict(),
      z.object({
        callId: agentIdentifierSchema,
        invocationId: agentIdentifierSchema,
        toolName: agentToolNameSchema,
        result: agentJsonObjectSchema,
        truncated: z.boolean(),
        replayed: z.literal(false),
      }).strict(),
    ]),
  }).strict(),
  z.object({ type: z.literal("content_delta"), data: z.object({ delta: z.string().min(1).max(16_384) }).strict() }).strict(),
  z.object({
    type: z.literal("checkpoint"),
    data: z.object({ label: z.string().min(1).max(200), data: agentJsonObjectSchema }).strict(),
  }).strict(),
  z.object({
    type: z.literal("state_mutation"),
    data: z.union([
      z.object({
        invocationId: agentIdentifierSchema,
        mutationId: agentIdentifierSchema,
        entityType: z.literal("study_task"),
        entityId: z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/),
        operation: z.literal("update"),
        reversible: z.literal(true),
        action: z.enum(["undo", "redo"]),
        targetMutationId: agentIdentifierSchema,
        replayed: z.boolean(),
      }).strict(),
      z.object({
        callId: agentIdentifierSchema,
        invocationId: agentIdentifierSchema,
        mutationId: agentIdentifierSchema,
        replayed: z.literal(true),
      }).strict(),
      z.object({
        callId: agentIdentifierSchema,
        invocationId: agentIdentifierSchema,
        mutationId: agentIdentifierSchema,
        entityType: z.string().min(1).max(80).regex(/^[a-z][a-z0-9_]*$/),
        entityId: z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/),
        operation: z.enum(["create", "update", "delete"]),
        reversible: z.literal(true),
      }).strict(),
    ]),
  }).strict(),
  z.object({
    type: z.literal("warning"),
    data: z.object({ code: agentErrorCodeSchema, message: z.string().min(1).max(1_000) }).strict(),
  }).strict(),
  z.object({ type: z.literal("done"), data: z.object({ status: z.literal("completed") }).strict() }).strict(),
  z.object({
    type: z.literal("error"),
    data: z.object({
      code: agentErrorCodeSchema,
      retryable: z.boolean(),
      status: z.enum(["failed", "cancelled", "interrupted"]),
      message: z.string().min(1).max(4_000).optional(),
    }).strict(),
  }).strict(),
]);

export const agentRunEventSchema = z.object({
  id: agentIdentifierSchema,
  type: z.enum(["metadata", "status", "tool_start", "tool_result", "content_delta", "checkpoint", "state_mutation", "warning", "done", "error"]),
  data: z.unknown(),
}).strict().transform((event, context) => {
  const parsed = agentEventDataSchema.safeParse({ type: event.type, data: event.data });
  if (!parsed.success) {
    parsed.error.issues.forEach((issue) => context.addIssue(issue));
    return z.NEVER;
  }
  return { id: event.id, ...parsed.data };
});

export type AgentRunKind = z.infer<typeof agentRunKindSchema>;
export type AgentRunMode = z.infer<typeof agentRunModeSchema>;
export type AgentRunStatus = z.infer<typeof agentRunStatusSchema>;
export type AgentRunCreateRequest = z.input<typeof agentRunCreateRequestSchema>;
export type AgentRun = z.infer<typeof agentRunSchema>;
export type AgentCancelResponse = z.infer<typeof agentCancelResponseSchema>;
export type AgentMutationActionRequest = z.infer<typeof agentMutationActionRequestSchema>;
export type AgentMutationActionResponse = z.infer<typeof agentMutationActionResponseSchema>;
export type AgentRunEvent = z.infer<typeof agentRunEventSchema>;
