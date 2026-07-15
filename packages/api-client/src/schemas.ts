import { z } from "zod";

const isoDateTimeSchema = z.string().datetime({ offset: true });

export const sidecarConnectionSchema = z.object({
  available: z.boolean(),
  port: z.number().int().min(1).max(65_535).nullable(),
  baseUrl: z.string().url().nullable(),
  token: z.string().min(32).regex(/^[^\r\n]+$/).nullable(),
  status: z.enum(["stopped", "starting", "restarting", "ready", "unavailable"]),
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
}).strict();

export const documentImportResponseSchema = z.object({
  document: indexedDocumentSchema,
  duplicate: z.boolean(),
}).strict();

export const documentListResponseSchema = z.object({
  documents: z.array(indexedDocumentSchema),
}).strict();

export const searchResultSchema = z.object({
  chunkId: z.string().min(1),
  documentId: z.string().min(1),
  documentName: z.string().min(1),
  pageNumber: z.number().int().positive(),
  sectionPath: z.array(z.string()),
  text: z.string(),
  score: z.number().finite().nonnegative(),
}).strict();

export const searchResponseSchema = z.object({
  query: z.string(),
  results: z.array(searchResultSchema),
}).strict();

export const citationSchema = z.object({
  chunkId: z.string().min(1),
  documentId: z.string().min(1),
  documentName: z.string().min(1),
  pageNumber: z.number().int().positive(),
  sectionPath: z.array(z.string()),
  excerpt: z.string(),
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

export type SidecarConnection = z.infer<typeof sidecarConnectionSchema>;
export type HealthResponse = z.infer<typeof healthResponseSchema>;
export type Course = z.infer<typeof courseSchema>;
export type StudyTask = z.infer<typeof studyTaskSchema>;
export type MasteryState = z.infer<typeof masteryStateSchema>;
export type DemoState = z.infer<typeof demoStateSchema>;
export type IndexedDocument = z.infer<typeof indexedDocumentSchema>;
export type DocumentImportResponse = z.infer<typeof documentImportResponseSchema>;
export type SearchResponse = z.infer<typeof searchResponseSchema>;
export type GroundedQueryResponse = z.infer<typeof groundedQueryResponseSchema>;
