import { z } from "zod";

const isoDateTimeSchema = z.string().datetime({ offset: true });

export const sidecarConnectionSchema = z.object({
  available: z.boolean(),
  port: z.number().int().min(1).max(65_535).nullable(),
  baseUrl: z.string().url().nullable(),
  token: z.string().min(32).regex(/^[^\r\n]+$/).nullable(),
  status: z.enum(["stopped", "starting", "restarting", "ready", "unavailable", "configuration_error"]),
  phase: z.enum(["binding", "migrating", "recovering", "starting_server", "health_checking"]).nullable(),
  message: z.string().min(1).max(1_000).nullable(),
}).strict().superRefine((connection, context) => {
  if (connection.available && (connection.port === null || connection.token === null)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: "An available sidecar must include both a port and a session token.",
    });
  }
  if (!connection.available && (connection.port !== null || connection.baseUrl !== null || connection.token !== null)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: "An unavailable sidecar must not expose connection credentials.",
    });
  }
  if (connection.available && connection.status !== "ready") {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "An available sidecar must be ready." });
  }
  if (connection.available && connection.baseUrl !== `http://127.0.0.1:${connection.port}`) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "The sidecar base URL must match its loopback port.", path: ["baseUrl"] });
  }
  if (!connection.available && connection.status === "ready") {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "A ready sidecar must expose a connection." });
  }
  if (connection.status === "ready" && connection.phase !== null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "A ready sidecar must not expose a startup phase.", path: ["phase"] });
  }
  if (connection.phase !== null && connection.status !== "starting" && connection.status !== "restarting") {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Only a starting sidecar may expose a startup phase.", path: ["phase"] });
  }
});

export const healthResponseSchema = z.object({
  status: z.literal("ok"),
  service: z.literal("keen-learning-core"),
  version: z.string().min(1),
}).strict();

export const courseSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string(),
  created_at: isoDateTimeSchema,
  concept_count: z.number().int().nonnegative(),
  average_mastery: z.number().min(0).max(1).nullable(),
}).strict();

export const courseCreateRequestSchema = z.object({
  title: z.string().trim().min(1).max(240),
  description: z.string().max(8_000).default(""),
  idempotencyKey: z.string().min(16).max(200).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/),
}).strict();

export const courseCreateResponseSchema = z.object({
  course: courseSchema,
  replayed: z.boolean(),
}).strict();

const finiteNumberSchema = z.number().finite();

export const learningPriorityComponentSchema = z.object({
  name: z.string().min(1).max(100),
  raw_value: finiteNumberSchema,
  weight: finiteNumberSchema,
  contribution: finiteNumberSchema,
}).strict();

export const learningActionCandidateSchema = z.object({
  id: z.string().min(1).max(256),
  action: z.enum([
    "review_due",
    "resume_study_session",
    "study_very_weak_concept",
    "address_repeated_misconception",
    "study_weak_concept",
  ]),
  target_type: z.enum(["review_item", "study_session", "concept", "misconception"]),
  target_id: z.string().min(1).max(128),
  concept_id: z.string().max(128).nullable(),
  component: z.string().min(1).max(100),
  priority_tier: z.number().int().min(1).max(10),
  estimated_minutes: z.number().int().min(1).max(1_440),
  fits_available_minutes: z.boolean(),
  priority_score: finiteNumberSchema.min(0).max(1),
  priority_unclamped_score: finiteNumberSchema,
  priority_algorithm_version: z.string().min(1).max(100),
  priority_components: z.array(learningPriorityComponentSchema).max(20),
  priority_explanation: z.array(z.string()).max(20),
  why: z.string().min(1).max(1_000),
}).strict().superRefine((candidate, context) => {
  const expectedTarget = candidate.action === "review_due"
    ? "review_item"
    : candidate.action === "resume_study_session"
      ? "study_session"
      : candidate.action === "address_repeated_misconception"
        ? "misconception"
        : "concept";
  if (candidate.target_type !== expectedTarget) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Candidate action must match its target type.", path: ["target_type"] });
  }
  const conceptMatches = candidate.target_type === "study_session"
    ? candidate.concept_id === null
    : candidate.target_type === "concept"
      ? candidate.concept_id === candidate.target_id
      : candidate.concept_id !== null;
  if (!conceptMatches) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Candidate concept must match its target semantics.", path: ["concept_id"] });
  }
});

export const learningFeedTaskSchema = z.object({
  id: z.string().min(1).max(128),
  course_id: z.string().min(1).max(128),
  concept_id: z.string().max(128).nullable(),
  title: z.string().min(1).max(500),
  reason: z.string().min(1).max(2_000),
  due_at: isoDateTimeSchema,
  estimated_minutes: z.number().int().min(1).max(1_440),
  status: z.enum(["upcoming", "overdue", "completed"]),
  source_type: z.string().min(1).max(100),
  source_id: z.string().max(128).nullable(),
  priority_score: finiteNumberSchema.min(0),
  recommended_reason: z.string().max(2_000),
  scheduled_for: isoDateTimeSchema.nullable(),
  created_at: isoDateTimeSchema,
  updated_at: isoDateTimeSchema,
}).strict();

function sameValidatedValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export const conceptBootstrapSchema = z.object({
  course_id: z.string().min(1).max(128),
  document_id: z.string().min(1).max(128),
  concept_id: z.string().min(1).max(128),
  concept_name: z.string().min(1).max(160),
  mastery_probability: finiteNumberSchema.min(0).max(1),
  mastery_attempts: z.number().int().nonnegative(),
  concept_created: z.boolean(),
  mastery_initialized: z.boolean(),
  mastery_initialization_algorithm: z.string().max(100).nullable(),
  mastery_initialization_algorithm_version: z.string().max(100).nullable(),
}).strict();

export const learningSnapshotSchema = z.object({
  course_id: z.string().min(1).max(128),
  as_of: isoDateTimeSchema,
  available_minutes: z.number().int().min(1).max(1_440),
  due_review_count: z.number().int().min(0).max(50),
  incomplete_session_count: z.number().int().min(0).max(50),
  misconception_count: z.number().int().min(0).max(50),
  pending_tasks: z.array(learningFeedTaskSchema).max(50),
  candidates: z.array(learningActionCandidateSchema).max(50),
  mastery_gap_count: z.number().int().nonnegative(),
}).strict().superRefine((snapshot, context) => {
  const taskIds = new Set<string>();
  snapshot.pending_tasks.forEach((task, index) => {
    if (task.course_id !== snapshot.course_id) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Every pending task must belong to the snapshot course.",
        path: ["pending_tasks", index, "course_id"],
      });
    }
    if (task.status === "completed") {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "Pending tasks cannot be completed.", path: ["pending_tasks", index, "status"] });
    }
    if (taskIds.has(task.id)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "Pending task IDs must be unique.", path: ["pending_tasks", index, "id"] });
    }
    taskIds.add(task.id);
  });
  const candidateIds = new Set<string>();
  snapshot.candidates.forEach((candidate, index) => {
    if (candidateIds.has(candidate.id)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "Candidate IDs must be unique.", path: ["candidates", index, "id"] });
    }
    candidateIds.add(candidate.id);
  });
});

export const autonomousRecommendationRequestSchema = z.object({
  course_id: z.string().min(1).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/),
  available_minutes: z.number().int().min(1).max(1_440),
  document_id: z.string().min(1).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/).optional(),
}).strict();

export const autonomousRecommendationResponseSchema = z.object({
  outcome: z.enum(["empty", "task_created", "replay", "covered_by_active_task"]),
  course_id: z.string().min(1).max(128),
  snapshot: learningSnapshotSchema,
  task: learningFeedTaskSchema.nullable(),
  candidate: learningActionCandidateSchema.nullable(),
  bootstrap: conceptBootstrapSchema.nullable(),
}).strict().superRefine((result, context) => {
  if (result.course_id !== result.snapshot.course_id) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Recommendation course_id must match its snapshot.", path: ["course_id"] });
  }
  const shouldIncludeAction = result.outcome !== "empty";
  if (shouldIncludeAction !== (result.task !== null) || shouldIncludeAction !== (result.candidate !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Only a non-empty outcome may include a task and candidate." });
  }
  if (result.task !== null && result.task.course_id !== result.course_id) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Recommendation task must belong to the response course.", path: ["task", "course_id"] });
  }
  if (result.outcome === "empty" && result.snapshot.candidates.length !== 0) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "An empty outcome cannot include action candidates.", path: ["outcome"] });
  }
  if (result.bootstrap !== null && result.bootstrap.course_id !== result.course_id) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Bootstrap evidence must belong to the response course.", path: ["bootstrap", "course_id"] });
  }
  if (result.candidate !== null) {
    const snapshotCandidates = result.snapshot.candidates.filter((candidate) => candidate.id === result.candidate?.id);
    if (snapshotCandidates.length !== 1 || !sameValidatedValue(snapshotCandidates[0], result.candidate)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "Recommendation candidate must exactly match its snapshot candidate.", path: ["candidate"] });
    }
  }
  if (result.task !== null) {
    const pendingTasks = result.snapshot.pending_tasks.filter((task) => task.id === result.task?.id);
    if (result.task.status === "completed") {
      if (result.outcome !== "replay") {
        context.addIssue({ code: z.ZodIssueCode.custom, message: "Only a replay may return a completed task.", path: ["task", "status"] });
      }
      if (pendingTasks.length > 0) {
        context.addIssue({ code: z.ZodIssueCode.custom, message: "A completed task cannot appear in pending tasks.", path: ["task", "id"] });
      }
    } else if (pendingTasks.length !== 1 || !sameValidatedValue(pendingTasks[0], result.task)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "An active recommendation task must exactly match its pending snapshot task.", path: ["task"] });
    }
  }
  if (result.task !== null && result.candidate !== null) {
    const task = result.task;
    const candidate = result.candidate;
    const covered = result.outcome === "covered_by_active_task";
    const verifyGeneratedSource = !covered && task.status !== "completed";
    const sourceMatches = candidate.target_type === "review_item"
      ? task.source_type === "review" && task.source_id === candidate.target_id && task.concept_id === candidate.concept_id
      : candidate.target_type === "study_session"
        ? task.source_type === "study_session" && task.source_id === candidate.target_id && (!verifyGeneratedSource || task.concept_id === null)
        : candidate.target_type === "concept"
          ? task.concept_id === candidate.concept_id && (!verifyGeneratedSource || (task.source_type === "weak_concept" && task.source_id === candidate.concept_id))
          : task.concept_id === candidate.concept_id && (!verifyGeneratedSource || (task.source_type === "weak_concept" && task.source_id === candidate.concept_id));
    if (!sourceMatches) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "Recommendation task source must match the candidate target.", path: ["task", "source_type"] });
    }
  }
});

const learningIdentifierSchema = z.string().min(1).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);

export const autonomousStudySessionRequestSchema = z.object({
  course_id: learningIdentifierSchema,
  task_id: learningIdentifierSchema,
}).strict();

export const autonomousStudyTaskSchema = z.object({
  id: learningIdentifierSchema,
  course_id: learningIdentifierSchema,
  concept_id: learningIdentifierSchema.nullable(),
  title: z.string().min(1).max(500),
  reason: z.string().min(1).max(2_000),
  estimated_minutes: z.number().int().min(1).max(1_440),
  status: z.enum(["upcoming", "overdue", "completed"]),
  source_type: z.string().min(1).max(100),
  source_id: learningIdentifierSchema.nullable(),
}).strict();

export const autonomousStudySessionUnitSchema = z.object({
  id: z.string().min(1).max(256),
  ordinal: z.number().int().min(0).max(7),
  concept_id: learningIdentifierSchema.nullable(),
  concept_ids: z.array(learningIdentifierSchema).min(1).max(8),
  source_chunk_ids: z.array(learningIdentifierSchema).min(1).max(8),
  title: z.string().min(1).max(500),
  objective: z.string().min(1).max(5_000),
  // Source text is untrusted display data. It is deliberately data-only in this contract.
  content: z.string().max(1_200),
  estimated_minutes: z.number().int().min(1).max(1_440),
  status: z.enum(["locked", "ready", "active", "completed", "skipped"]),
}).strict();

export const autonomousStudyPlanSchema = z.object({
  id: learningIdentifierSchema,
  session_id: learningIdentifierSchema,
  version: z.number().int().min(1),
  rationale: z.string().min(1).max(2_000),
  units: z.array(autonomousStudySessionUnitSchema).min(2).max(8),
}).strict().superRefine((plan, context) => {
  const ids = new Set<string>();
  plan.units.forEach((unit, index) => {
    if (ids.has(unit.id)) context.addIssue({ code: z.ZodIssueCode.custom, message: "Study plan unit IDs must be unique.", path: ["units", index, "id"] });
    ids.add(unit.id);
    if (unit.ordinal !== index) context.addIssue({ code: z.ZodIssueCode.custom, message: "Study plan unit ordinals must be contiguous.", path: ["units", index, "ordinal"] });
    if (unit.concept_id !== null && !unit.concept_ids.includes(unit.concept_id)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "A unit concept_id must occur in concept_ids.", path: ["units", index, "concept_id"] });
    }
  });
});

export const autonomousStudySessionSchema = z.object({
  id: learningIdentifierSchema,
  course_id: learningIdentifierSchema,
  originating_task_id: learningIdentifierSchema.nullable(),
  title: z.string().min(1).max(500),
  mode: z.enum(["teach", "study", "review", "plan"]),
  goal: z.string().min(1).max(5_000),
  estimated_minutes: z.number().int().min(1).max(1_440),
  status: z.enum(["draft", "goal_confirmation", "diagnosing", "planning", "studying", "checkpoint", "active_recall", "practicing", "summarizing", "review_scheduling", "paused", "completed", "cancelled", "failed"]),
  progress: finiteNumberSchema.min(0).max(1),
  revision: z.number().int().nonnegative(),
  created_at: isoDateTimeSchema,
  updated_at: isoDateTimeSchema,
  started_at: isoDateTimeSchema.nullable(),
}).strict();

const blockedStudySessionReasonSchema = z.enum([
  "task_not_found", "task_outside_course", "task_not_actionable", "task_not_autonomous",
  "task_missing_concept", "source_session_unavailable", "originating_session_terminal", "no_indexed_source",
]);

export const autonomousStudySessionStartResponseSchema = z.object({
  outcome: z.enum(["session_created", "resumed", "blocked"]),
  course_id: learningIdentifierSchema,
  task: autonomousStudyTaskSchema.nullable(),
  session: autonomousStudySessionSchema.nullable(),
  plan: autonomousStudyPlanSchema.nullable(),
  blocked_reason: blockedStudySessionReasonSchema.nullable(),
  recovery_action: z.string().min(1).max(500).nullable(),
}).strict().superRefine((result, context) => {
  const blocked = result.outcome === "blocked";
  if (blocked) {
    if (result.session !== null || result.plan !== null || result.blocked_reason === null || result.recovery_action === null) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "Blocked starts must not carry a session or plan and must include typed recovery." });
    }
    if ((result.blocked_reason === "task_not_found" || result.blocked_reason === "task_outside_course") !== (result.task === null)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "Only absent or foreign tasks may be omitted from a blocked result.", path: ["task"] });
    }
    if (result.task !== null && result.task.course_id !== result.course_id) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "A visible blocked task must belong to the response course.", path: ["task", "course_id"] });
    }
    return;
  }
  if (result.task === null || result.session === null || result.blocked_reason !== null || result.recovery_action !== null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Successful starts must include a task and session without blocked recovery." });
    return;
  }
  if (result.task.course_id !== result.course_id || result.session.course_id !== result.course_id) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Study session start entities must share course scope." });
  }
  if (result.outcome === "session_created") {
    if (result.plan === null || result.session.originating_task_id !== result.task.id || result.plan?.session_id !== result.session.id || result.task.concept_id === null || !result.plan?.units.every((unit) => unit.concept_ids.includes(result.task!.concept_id!))) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "A created session must include its matching originating task and plan." });
    }
  } else if (result.plan !== null || (result.task.source_type === "study_session" ? result.task.source_id !== result.session.id : result.session.originating_task_id !== result.task.id)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "A resumed session must omit the plan and match its originating task when provable." });
  }
});

export const studySessionReadResponseSchema = z.object({
  outcome: z.enum(["ready", "plan_unavailable"]),
  course_id: learningIdentifierSchema,
  session: autonomousStudySessionSchema,
  plan: autonomousStudyPlanSchema.nullable(),
  current_unit_id: z.string().min(1).max(256).nullable(),
  recovery_action: z.string().min(1).max(500).nullable(),
}).strict().superRefine((result, context) => {
  if (result.session.course_id !== result.course_id) context.addIssue({ code: z.ZodIssueCode.custom, message: "Study session must belong to the response course.", path: ["session", "course_id"] });
  if (result.outcome === "ready") {
    if (result.plan === null || result.recovery_action !== null || result.plan?.session_id !== result.session.id || (result.current_unit_id !== null && !result.plan?.units.some((unit) => unit.id === result.current_unit_id))) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: "A ready study session must have its matching plan and an in-plan current unit." });
    }
  } else if (result.plan !== null || result.current_unit_id !== null || result.recovery_action === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "A plan-unavailable session must provide only recovery guidance." });
  }
});

export const studyTaskSchema = z.object({
  id: z.string().min(1),
  course_id: z.string().min(1),
  course_title: z.string().min(1).nullable(),
  title: z.string().min(1),
  reason: z.string().min(1),
  due_at: isoDateTimeSchema,
  estimated_minutes: z.number().int().positive(),
  status: z.enum(["upcoming", "overdue", "completed"]),
  concept_id: z.string().min(1).nullable(),
  created_at: isoDateTimeSchema,
  updated_at: isoDateTimeSchema,
}).strict();

export const masteryStateSchema = z.object({
  concept_id: z.string().min(1),
  course_id: z.string().min(1),
  concept_name: z.string().min(1),
  probability: z.number().min(0).max(1),
  attempts: z.number().int().nonnegative(),
  updated_at: isoDateTimeSchema,
}).strict();

export const demoStateSchema = z.object({
  courses: z.array(courseSchema),
  tasks: z.array(studyTaskSchema),
  mastery: z.array(masteryStateSchema),
}).strict();

export const indexedDocumentSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  mimeType: z.string().min(1),
  sizeBytes: z.number().int().positive(),
  contentHash: z.string().regex(/^[a-f0-9]{64}$/),
  status: z.enum(["queued", "parsing", "chunking", "indexed", "failed"]),
  pageCount: z.number().int().nonnegative(),
  chunkCount: z.number().int().nonnegative(),
  parser: z.string().min(1),
  createdAt: isoDateTimeSchema,
  error: z.string().nullable(),
  courseIds: z.array(z.string().min(1)).superRefine((courseIds, context) => {
    for (let index = 1; index < courseIds.length; index += 1) {
      if (courseIds[index - 1] >= courseIds[index]) {
        context.addIssue({ code: z.ZodIssueCode.custom, message: "courseIds must be unique and sorted.", path: [index] });
      }
    }
  }),
  indexState: z.enum(["pending", "indexed-lexical", "indexed-hybrid", "needs-reindex"]).nullable(),
  embeddingStatus: z.enum([
    "not-applicable", "provider-missing", "pending", "embedding", "ready", "provider-failure", "needs-reindex",
  ]).nullable(),
  embeddingModel: z.string().min(1).nullable(),
  embeddingError: z.string().min(1).nullable(),
  retrievalWarning: z.string().min(1).nullable(),
  providerConfigured: z.boolean().nullable(),
}).strict();

export const indexJobStatusSchema = z.enum([
  "queued", "running", "cancel_requested", "cancelled", "completed", "failed", "interrupted",
]);

export const indexJobStageSchema = z.enum([
  "queued", "validating", "stored", "parsing", "chunking", "lexical_indexing", "embedding", "finalizing",
]);

export const indexJobSchema = z.object({
  id: z.string().min(1),
  documentId: z.string().min(1),
  status: indexJobStatusSchema,
  stage: indexJobStageSchema,
  progress: z.number().int().min(0).max(100),
  cancelRequested: z.boolean(),
  error: z.string().nullable(),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
  startedAt: isoDateTimeSchema.nullable(),
  finishedAt: isoDateTimeSchema.nullable(),
  operation: z.enum(["full_index", "embedding_reindex"]),
}).strict();

export const documentImportResponseSchema = z.object({
  document: indexedDocumentSchema,
  job: indexJobSchema,
  duplicate: z.boolean(),
  linked: z.boolean(),
}).strict();

export const documentCourseLinkResponseSchema = z.object({
  document: indexedDocumentSchema,
  linked: z.boolean(),
}).strict();

export const documentRetryResponseSchema = z.object({
  document: indexedDocumentSchema,
  job: indexJobSchema,
}).strict();

export const documentEmbeddingReindexResponseSchema = documentRetryResponseSchema;

export const indexJobListResponseSchema = z.object({
  jobs: z.array(indexJobSchema),
}).strict();

export const documentListResponseSchema = z.object({
  documents: z.array(indexedDocumentSchema),
}).strict();

export const searchResultSchema = z.object({
  chunkId: z.string().min(1),
  chunkIds: z.array(z.string().min(1)).min(1),
  documentId: z.string().min(1),
  documentName: z.string().min(1),
  pageNumber: z.number().int().positive(),
  pageEnd: z.number().int().positive(),
  sectionPath: z.array(z.string()),
  text: z.string().min(1),
  score: z.number().finite().nonnegative(),
}).strict().superRefine((result, context) => {
  if (result.chunkIds[0] !== result.chunkId || new Set(result.chunkIds).size !== result.chunkIds.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "chunkIds must be unique and begin with chunkId.", path: ["chunkIds"] });
  }
  if (result.pageEnd < result.pageNumber) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "pageEnd must not precede pageNumber.", path: ["pageEnd"] });
  }
});

export const searchResponseSchema = z.object({
  query: z.string(),
  mode: z.enum(["hybrid", "lexical_only"]),
  warning: z.string().min(1).nullable(),
  results: z.array(searchResultSchema),
}).strict().superRefine((response, context) => {
  if (response.mode === "hybrid" && response.warning !== null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Hybrid search must not include a fallback warning.", path: ["warning"] });
  }
  if (response.mode === "lexical_only" && response.warning === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Lexical-only search must explain why vector retrieval was unavailable.", path: ["warning"] });
  }
});

export const citationSchema = z.object({
  chunkId: z.string().min(1),
  documentId: z.string().min(1),
  documentName: z.string().min(1),
  pageNumber: z.number().int().positive(),
  sectionPath: z.array(z.string()),
  excerpt: z.string().min(1),
}).strict();

export const groundedQueryResponseSchema = z.object({
  answer: z.string(),
  grounded: z.boolean(),
  citations: z.array(citationSchema),
  note: z.string(),
}).strict().superRefine((response, context) => {
  if (response.grounded && response.citations.length === 0) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: "A grounded answer must include at least one citation.",
      path: ["citations"],
    });
  }
});

export const answerRetrievalChunkSchema = z.object({
  sourceIndex: z.number().int().positive(),
  chunkIds: z.array(z.string().min(1)).min(1),
  documentId: z.string().min(1),
  documentName: z.string().min(1),
  pageNumber: z.number().int().positive(),
  pageEnd: z.number().int().positive(),
  sectionPath: z.array(z.string()),
  text: z.string(),
  courseIds: z.array(z.string().min(1)),
}).strict().superRefine((chunk, context) => {
  if (new Set(chunk.chunkIds).size !== chunk.chunkIds.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "chunkIds must be unique.", path: ["chunkIds"] });
  }
  if (chunk.pageEnd < chunk.pageNumber) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "pageEnd must not precede pageNumber.", path: ["pageEnd"] });
  }
});

export const answerCitationSchema = z.object({
  citationId: z.string().min(1),
  sourceIndex: z.number().int().positive(),
  chunkId: z.string().min(1),
  documentId: z.string().min(1),
  documentName: z.string().min(1),
  pageNumber: z.number().int().positive(),
  sectionPath: z.array(z.string()),
  excerpt: z.string(),
  bbox: z.object({
    x0: z.number().finite(),
    y0: z.number().finite(),
    x1: z.number().finite(),
    y1: z.number().finite(),
    pageWidth: z.number().finite().positive(),
    pageHeight: z.number().finite().positive(),
    coordinateSystem: z.literal("pdf_bottom_left"),
  }).strict().nullable(),
}).strict().superRefine((citation, context) => {
  const bbox = citation.bbox;
  if (!bbox) return;
  if (
    bbox.x0 < 0
    || bbox.y0 < 0
    || bbox.x1 <= bbox.x0
    || bbox.y1 <= bbox.y0
    || bbox.x1 > bbox.pageWidth
    || bbox.y1 > bbox.pageHeight
  ) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Citation bbox must be ordered within its PDF page bounds.", path: ["bbox"] });
  }
});

export const answerStreamEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("metadata"),
    data: z.object({
      runId: z.string().min(1),
      conversationId: z.string().min(1),
      provider: z.object({
        kind: z.string().min(1),
        model: z.string().min(1),
        version: z.string().min(1),
      }).strict().nullable(),
      retrievalLimit: z.number().int().min(1).max(30),
    }).strict(),
  }).strict(),
  z.object({
    type: z.literal("retrieval"),
    data: z.object({
      mode: z.enum(["hybrid", "lexical_only"]),
      warning: z.string().min(1).nullable(),
      chunks: z.array(answerRetrievalChunkSchema),
    }).strict().superRefine((retrieval, context) => {
      if (retrieval.mode === "hybrid" && retrieval.warning !== null) {
        context.addIssue({ code: z.ZodIssueCode.custom, message: "Hybrid retrieval cannot include a fallback warning.", path: ["warning"] });
      }
      if (retrieval.mode === "lexical_only" && retrieval.warning === null) {
        context.addIssue({ code: z.ZodIssueCode.custom, message: "Lexical-only retrieval must include its limitation.", path: ["warning"] });
      }
    }),
  }).strict(),
  z.object({
    type: z.literal("delta"),
    data: z.object({ text: z.string().min(1) }).strict(),
  }).strict(),
  z.object({
    type: z.literal("citation"),
    data: answerCitationSchema,
  }).strict(),
  z.object({
    type: z.literal("warning"),
    data: z.object({
      code: z.string().min(1),
      message: z.string().min(1),
      retryable: z.boolean(),
    }).strict(),
  }).strict(),
  z.object({
    type: z.literal("done"),
    data: z.object({
      runId: z.string().min(1),
      finishReason: z.string().min(1),
      grounded: z.boolean(),
      citationCount: z.number().int().nonnegative(),
      citationValidation: z.literal("structural_only"),
    }).strict(),
  }).strict(),
  z.object({
    type: z.literal("error"),
    data: z.object({
      runId: z.string().min(1),
      code: z.string().min(1),
      message: z.string().min(1),
      retryable: z.boolean(),
    }).strict(),
  }).strict(),
]);

export type SidecarConnection = z.infer<typeof sidecarConnectionSchema>;
export type HealthResponse = z.infer<typeof healthResponseSchema>;
export type Course = z.infer<typeof courseSchema>;
export type CourseCreateRequest = z.input<typeof courseCreateRequestSchema>;
export type CourseCreateResponse = z.infer<typeof courseCreateResponseSchema>;
export type LearningPriorityComponent = z.infer<typeof learningPriorityComponentSchema>;
export type LearningActionCandidate = z.infer<typeof learningActionCandidateSchema>;
export type LearningFeedTask = z.infer<typeof learningFeedTaskSchema>;
export type ConceptBootstrap = z.infer<typeof conceptBootstrapSchema>;
export type LearningSnapshot = z.infer<typeof learningSnapshotSchema>;
export type AutonomousRecommendationRequest = z.input<typeof autonomousRecommendationRequestSchema>;
export type AutonomousRecommendationResponse = z.infer<typeof autonomousRecommendationResponseSchema>;
export type AutonomousStudySessionRequest = z.input<typeof autonomousStudySessionRequestSchema>;
export type AutonomousStudyTask = z.infer<typeof autonomousStudyTaskSchema>;
export type AutonomousStudySessionUnit = z.infer<typeof autonomousStudySessionUnitSchema>;
export type AutonomousStudyPlan = z.infer<typeof autonomousStudyPlanSchema>;
export type AutonomousStudySession = z.infer<typeof autonomousStudySessionSchema>;
export type AutonomousStudySessionStartResponse = z.infer<typeof autonomousStudySessionStartResponseSchema>;
export type StudySessionReadResponse = z.infer<typeof studySessionReadResponseSchema>;
export type StudyTask = z.infer<typeof studyTaskSchema>;
export type MasteryState = z.infer<typeof masteryStateSchema>;
export type DemoState = z.infer<typeof demoStateSchema>;
export type IndexedDocument = z.infer<typeof indexedDocumentSchema>;
export type IndexJobStatus = z.infer<typeof indexJobStatusSchema>;
export type IndexJobStage = z.infer<typeof indexJobStageSchema>;
export type IndexJob = z.infer<typeof indexJobSchema>;
export type DocumentImportResponse = z.infer<typeof documentImportResponseSchema>;
export type DocumentCourseLinkResponse = z.infer<typeof documentCourseLinkResponseSchema>;
export type DocumentRetryResponse = z.infer<typeof documentRetryResponseSchema>;
export type DocumentEmbeddingReindexResponse = z.infer<typeof documentEmbeddingReindexResponseSchema>;
export type SearchResponse = z.infer<typeof searchResponseSchema>;
export type GroundedQueryResponse = z.infer<typeof groundedQueryResponseSchema>;
export type AnswerRetrievalChunk = z.infer<typeof answerRetrievalChunkSchema>;
export type AnswerCitation = z.infer<typeof answerCitationSchema>;
export type AnswerStreamEvent = z.infer<typeof answerStreamEventSchema>;
