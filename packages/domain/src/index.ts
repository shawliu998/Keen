import { z } from "zod";

export const taskStatusSchema = z.enum(["today", "upcoming", "overdue", "completed"]);
export type TaskStatus = z.infer<typeof taskStatusSchema>;

export const learningTaskSchema = z.object({
  id: z.string(),
  title: z.string().min(1),
  course: z.string(),
  reason: z.string(),
  due: z.string(),
  durationMinutes: z.number().int().positive(),
  concepts: z.array(z.string()),
  mastery: z.number().min(0).max(100),
  status: taskStatusSchema,
});
export type LearningTask = z.infer<typeof learningTaskSchema>;

export const documentStatusSchema = z.enum([
  "queued", "parsing", "OCR", "chunking", "embedding", "indexed", "partial", "failed", "needs-reindex",
]);
export type DocumentStatus = z.infer<typeof documentStatusSchema>;

export const documentSchema = z.object({
  id: z.string(),
  name: z.string(),
  course: z.string(),
  type: z.enum(["PDF", "Markdown", "TXT", "Image"]),
  pages: z.number().int().nonnegative(),
  importedAt: z.string(),
  status: documentStatusSchema,
  parser: z.string(),
  embeddingModel: z.string(),
});
export type KnowledgeDocument = z.infer<typeof documentSchema>;

export type Citation = { document: string; page: number; excerpt: string };
export type AgentMode = "Teach" | "Solve" | "Review" | "Research";

export type MemoryItem = {
  id: string;
  statement: string;
  kind: "goal" | "preference" | "misconception" | "mastery" | "weakness" | "inference";
  evidence: string;
  enabled: boolean;
};
