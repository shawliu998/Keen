import type { DocumentStatus, KnowledgeDocument } from "@keen/domain";
import type { IndexedDocument, IndexJob, IndexJobStage, IndexJobStatus } from "@keen/api-client";

export type DocumentDisplayStatus = DocumentStatus | IndexJobStatus | IndexJobStage
  | "completed" | "pending" | "indexed-lexical" | "indexed-hybrid";

export type DisplayDocument = Omit<KnowledgeDocument, "status"> & {
  status: DocumentDisplayStatus;
  chunks?: number;
  error?: string | null;
  job: IndexJob | null;
  courseIds: string[];
  courseNames: string[];
  retrievalWarning: string | null;
  embeddingStatus: IndexedDocument["embeddingStatus"];
  providerConfigured: boolean | null;
};

export type CourseOption = { id: string; title: string };

export function latestJob(jobs: IndexJob[] | undefined): IndexJob | null {
  if (!jobs || jobs.length === 0) return null;
  return jobs.reduce((latest, job) => Date.parse(job.createdAt) > Date.parse(latest.createdAt) ? job : latest);
}

export function isActiveJob(job: IndexJob | null | undefined): boolean {
  return job?.status === "queued" || job?.status === "running" || job?.status === "cancel_requested";
}

export function canCancelJob(job: IndexJob | null | undefined): boolean {
  return job?.status === "queued" || job?.status === "running";
}

export function canRetryJob(job: IndexJob | null | undefined): boolean {
  return job?.operation === "full_index"
    && (job.status === "failed" || job.status === "cancelled" || job.status === "interrupted");
}

export function canReindexEmbeddings(document: DisplayDocument): boolean {
  if (document.providerConfigured !== true || isActiveJob(document.job)) return false;
  const terminalEmbeddingJob = document.job?.operation === "embedding_reindex"
    && (document.job.status === "failed" || document.job.status === "cancelled" || document.job.status === "interrupted");
  return document.status === "needs-reindex"
    || document.embeddingStatus === "provider-failure"
    || terminalEmbeddingJob;
}

export function cancellationNotice(documentName: string, job: IndexJob): string {
  switch (job.status) {
    case "cancel_requested":
      return `Cancellation was requested for ${documentName}; the worker will stop at a safe boundary.`;
    case "cancelled":
      return job.startedAt === null
        ? `Indexing for ${documentName} was cancelled before it started.`
        : `Indexing for ${documentName} stopped after the cancellation request reached a safe boundary.`;
    case "completed":
      return `Indexing for ${documentName} had already completed; no cancellation was applied.`;
    case "failed":
      return `Indexing for ${documentName} had already failed; no cancellation was applied.`;
    case "interrupted":
      return `Indexing for ${documentName} had already been interrupted; no cancellation was applied.`;
    case "queued":
      return `Cancellation was not confirmed for ${documentName}; the job remains queued.`;
    case "running":
      return `Cancellation was not confirmed for ${documentName}; the job remains running.`;
  }
}

export function displayJobStatus(job: IndexJob): DocumentDisplayStatus {
  if (job.status === "running") return job.stage;
  return job.status;
}

export function toDisplayDocument(
  document: IndexedDocument,
  job: IndexJob | null,
  courseTitles: ReadonlyMap<string, string>,
): DisplayDocument {
  const type: KnowledgeDocument["type"] = document.mimeType === "application/pdf"
    ? "PDF"
    : document.mimeType.startsWith("image/") ? "Image" : document.name.endsWith(".md") ? "Markdown" : "TXT";
  return {
    id: document.id,
    name: document.name,
    course: document.courseIds.length === 0
      ? "No courses"
      : document.courseIds.map((courseId) => courseTitles.get(courseId) ?? `Unknown course (${courseId})`).join(", "),
    type,
    pages: document.pageCount,
    importedAt: new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(document.createdAt)),
    status: job && job.status !== "completed"
      ? displayJobStatus(job)
      : document.indexState ?? (document.status === "indexed" ? "indexed-lexical" : document.status),
    parser: document.parser,
    embeddingModel: document.embeddingModel ?? "No configured local embedding model",
    chunks: document.chunkCount,
    error: job?.error ?? document.error ?? document.embeddingError,
    job,
    courseIds: document.courseIds,
    courseNames: document.courseIds.map((courseId) => courseTitles.get(courseId) ?? `Unknown course (${courseId})`),
    retrievalWarning: document.retrievalWarning,
    embeddingStatus: document.embeddingStatus,
    providerConfigured: document.providerConfigured,
  };
}

export function toDemoDocument(document: KnowledgeDocument, course: CourseOption): DisplayDocument {
  return { ...document, job: null, courseIds: [course.id], courseNames: [course.title], retrievalWarning: null, embeddingStatus: null, providerConfigured: false };
}
