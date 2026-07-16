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
