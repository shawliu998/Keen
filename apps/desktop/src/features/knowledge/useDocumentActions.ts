import { useState, type Dispatch, type SetStateAction } from "react";
import type { QueryClient } from "@tanstack/react-query";
import { type IndexedDocument, type IndexJob, type LearningCoreClient } from "@keen/api-client";
import { cancellationNotice, type DisplayDocument } from "./documentJobs";
import { isConfirmedPartialDelete, operationError } from "./KnowledgeStates";

export type DocumentOperation = "cancelling" | "retrying" | "reindexing" | "deleting" | "linking" | "unlinking";
const operationLabels: Record<DocumentOperation, string> = {
  cancelling: "Cancel indexing", retrying: "Retry indexing", deleting: "Delete document",
  reindexing: "Reindex embeddings", linking: "Link course", unlinking: "Unlink course",
};

export function useDocumentActions({
  client,
  isDemo,
  courseTitles,
  documentsKey,
  jobsKeyPrefix,
  jobKey,
  queryClient,
  setDemoDocuments,
  setImportNotice,
}: {
  client: LearningCoreClient | null;
  isDemo: boolean;
  courseTitles: ReadonlyMap<string, string>;
  documentsKey: readonly unknown[];
  jobsKeyPrefix: readonly unknown[];
  jobKey: (documentId: string) => readonly unknown[];
  queryClient: QueryClient;
  setDemoDocuments: Dispatch<SetStateAction<DisplayDocument[]>>;
  setImportNotice: Dispatch<SetStateAction<string | null>>;
}) {
  const [operations, setOperations] = useState<Record<string, DocumentOperation | undefined>>({});
  const [documentOperationError, setDocumentOperationError] = useState<string | null>(null);
  const updateJob = (job: IndexJob) => queryClient.setQueryData<IndexJob[]>(jobKey(job.documentId), (jobs = []) => [job, ...jobs.filter((item) => item.id !== job.id)]);
  const updateDocument = (document: IndexedDocument) => queryClient.setQueryData<IndexedDocument[]>(documentsKey, (items = []) => items.map((item) => item.id === document.id ? document : item));
  const updateDemoCourses = (documentId: string, courseIds: string[]) => {
    const sortedIds = [...courseIds].sort();
    const names = sortedIds.map((courseId) => courseTitles.get(courseId) ?? `Unknown course (${courseId})`);
    setDemoDocuments((items) => items.map((document) => document.id === documentId
      ? { ...document, courseIds: sortedIds, courseNames: names, course: names.join(", ") || "No courses" }
      : document));
  };
  const run = async (document: DisplayDocument, operation: DocumentOperation, work: () => Promise<void>) => {
    setDocumentOperationError(null);
    setOperations((current) => ({ ...current, [document.id]: operation }));
    try { await work(); } catch (error) { setDocumentOperationError(operationError(operationLabels[operation], error)); }
    finally { setOperations((current) => ({ ...current, [document.id]: undefined })); }
  };
  const linkCourse = (document: DisplayDocument, courseId: string) => {
    const courseName = courseTitles.get(courseId) ?? courseId;
    if (isDemo) {
      updateDemoCourses(document.id, [...new Set([...document.courseIds, courseId])]);
      setImportNotice(`Demo only: ${courseName} was linked to ${document.name} in sample state.`);
      return;
    }
    if (!client) return;
    void run(document, "linking", async () => {
      const result = await client.linkDocumentCourse(document.id, courseId);
      updateDocument(result.document);
      setImportNotice(result.linked ? `${courseName} was linked to ${document.name}.` : `${document.name} was already linked to ${courseName}; no relationship changed.`);
    });
  };
  const unlinkCourse = (document: DisplayDocument, courseId: string) => {
    const courseName = courseTitles.get(courseId) ?? courseId;
    if (isDemo) {
      updateDemoCourses(document.id, document.courseIds.filter((id) => id !== courseId));
      setImportNotice(`Demo only: ${courseName} was unlinked from ${document.name}; the sample document was retained.`);
      return;
    }
    if (!client) return;
    void run(document, "unlinking", async () => {
      await client.unlinkDocumentCourse(document.id, courseId);
      queryClient.setQueryData<IndexedDocument[]>(documentsKey, (items = []) => items.map((item) => item.id === document.id
        ? { ...item, courseIds: item.courseIds.filter((id) => id !== courseId) } : item));
      setImportNotice(`${courseName} was unlinked from ${document.name}; the document and index were retained.`);
    });
  };
  const cancelJob = (document: DisplayDocument) => {
    if (!client || !document.job) return;
    void run(document, "cancelling", async () => {
      const job = await client.cancelIndexJob(document.job!.id);
      updateJob(job);
      setImportNotice(cancellationNotice(document.name, job));
    });
  };
  const retryDocument = (document: DisplayDocument) => {
    if (!client) return;
    void run(document, "retrying", async () => {
      const result = await client.retryDocument(document.id);
      updateJob(result.job);
      await queryClient.invalidateQueries({ queryKey: documentsKey });
      setImportNotice(`A new indexing job was queued for ${document.name}. Progress is ${result.job.progress}%.`);
    });
  };
  const reindexEmbeddings = (document: DisplayDocument) => {
    if (!client) return;
    void run(document, "reindexing", async () => {
      const result = await client.reindexDocumentEmbeddings(document.id);
      updateDocument(result.document);
      updateJob(result.job);
      setImportNotice(`Embedding reindex job ${result.job.id} was queued for ${document.name}. Its existing lexical index remains available while the local provider runs.`);
    });
  };
  const deleteDocument = (document: DisplayDocument) => {
    if (!client || !window.confirm(`Permanently delete “${document.name}”, its stored file, chunks, and indexing history? This cannot be undone.`)) return;
    setImportNotice(null);
    void run(document, "deleting", async () => {
      try { await client.deleteDocument(document.id); } catch (error) {
        const reconciliation = Promise.allSettled([queryClient.invalidateQueries({ queryKey: documentsKey }), queryClient.invalidateQueries({ queryKey: jobsKeyPrefix })]);
        if (isConfirmedPartialDelete(error)) {
          queryClient.setQueryData<IndexedDocument[]>(documentsKey, (items = []) => items.filter((item) => item.id !== document.id));
          queryClient.removeQueries({ queryKey: jobKey(document.id), exact: true });
          await reconciliation;
          const requestId = error.requestId ? ` Request ID: ${error.requestId}.` : "";
          const detail = error.detail?.message ?? error.message;
          setDocumentOperationError(`The document record and index data for ${document.name} were deleted, but local source cleanup is incomplete: ${detail}.${requestId}`);
          return;
        }
        await reconciliation;
        throw error;
      }
      queryClient.removeQueries({ queryKey: jobKey(document.id), exact: true });
      queryClient.setQueryData<IndexedDocument[]>(documentsKey, (items = []) => items.filter((item) => item.id !== document.id));
      setImportNotice(`${document.name} and its local indexing data were deleted.`);
    });
  };
  return { operations, documentOperationError, linkCourse, unlinkCourse, cancelJob, retryDocument, reindexEmbeddings, deleteDocument };
}
