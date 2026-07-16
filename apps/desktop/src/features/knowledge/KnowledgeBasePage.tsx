import { useEffect, useMemo, useRef, useState } from "react";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus2, Filter, Grid2X2, List, Search, UploadCloud } from "lucide-react";
import { Badge, Button, Card } from "@keen/ui";
import { LearningCoreResponseError, type IndexedDocument, type IndexJob } from "@keen/api-client";
import { documents as seedDocuments } from "../../data/seed";
import { Page, Segmented } from "../../components/Page";
import { useAppStore } from "../../state/appStore";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { DocumentCollection } from "./DocumentCollection";
import { isConfirmedPartialDelete, KnowledgeState, operationError, SearchResults } from "./KnowledgeStates";
import {
  cancellationNotice, isActiveJob, latestJob, toDemoDocument, toDisplayDocument,
  type CourseOption, type DisplayDocument,
} from "./documentJobs";

type DocumentOperation = "cancelling" | "retrying" | "reindexing" | "deleting" | "linking" | "unlinking";
const operationLabels: Record<DocumentOperation, string> = {
  cancelling: "Cancel indexing", retrying: "Retry indexing", deleting: "Delete document",
  reindexing: "Reindex embeddings", linking: "Link course", unlinking: "Unlink course",
};

const demoCourses: CourseOption[] = Array.from(new Set(seedDocuments.map((document) => document.course)))
  .map((title, index) => ({ id: `demo-course-${index + 1}`, title }));
const demoCourseByTitle = new Map(demoCourses.map((course) => [course.title, course]));

export function KnowledgeBasePage() {
  const core = useLearningCore();
  const queryClient = useQueryClient();
  const { setInspector } = useAppStore();
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const [demoDocuments, setDemoDocuments] = useState<DisplayDocument[]>(() => seedDocuments.map((document) => (
    toDemoDocument(document, demoCourseByTitle.get(document.course)!)
  )));
  const [view, setView] = useState<"List" | "Grid">("List");
  const [search, setSearch] = useState("");
  const [serverSearch, setServerSearch] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [documentOperationError, setDocumentOperationError] = useState<string | null>(null);
  const [operations, setOperations] = useState<Record<string, DocumentOperation | undefined>>({});
  const [courseFilter, setCourseFilter] = useState("all");
  const [importCourseId, setImportCourseId] = useState("");
  const isDemo = core.status === "demo";
  const live = core.status === "healthy" && core.client !== null;
  const courses = useMemo<CourseOption[]>(() => isDemo
    ? demoCourses
    : (core.demoState?.courses ?? []).map((course) => ({ id: course.id, title: course.title })), [core.demoState?.courses, isDemo]);
  const courseTitles = useMemo(() => new Map(courses.map((course) => [course.id, course.title])), [courses]);
  const selectedImportCourseId = courses.some((course) => course.id === importCourseId) ? importCourseId : "";
  const documentsKey = useMemo(() => [
    "learning-core",
    "documents",
    core.client?.baseUrl ?? "none",
    core.connectionGeneration,
  ] as const, [core.client?.baseUrl, core.connectionGeneration]);
  const jobsKeyPrefix = useMemo(() => [
    "learning-core",
    "index-jobs",
    core.client?.baseUrl ?? "none",
    core.connectionGeneration,
  ] as const, [core.client?.baseUrl, core.connectionGeneration]);
  const jobKey = (documentId: string) => [...jobsKeyPrefix, documentId] as const;

  useEffect(() => {
    const timeout = window.setTimeout(() => setServerSearch(search.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [search]);

  useEffect(() => () => uploadController.current?.abort(), []);

  const documentsQuery = useQuery({
    queryKey: documentsKey,
    queryFn: ({ signal }) => {
      if (!core.client) throw new Error("Learning core connection is unavailable.");
      return core.client.listDocuments({ signal });
    },
    enabled: live,
    retry: 1,
    staleTime: 5_000,
  });

  const searchQuery = useQuery({
    queryKey: [
      "learning-core",
      "document-search",
      core.client?.baseUrl ?? "none",
      core.connectionGeneration,
      serverSearch,
      courseFilter,
    ],
    queryFn: ({ signal }) => {
      if (!core.client) throw new Error("Learning core connection is unavailable.");
      return core.client.search({
        query: serverSearch,
        limit: 8,
        ...(courseFilter !== "all" && courseFilter !== "unlinked" ? { courseId: courseFilter } : {}),
      }, { signal });
    },
    enabled: live && serverSearch.length >= 2,
    retry: 1,
  });

  const documentRecords = useMemo(() => documentsQuery.data ?? [], [documentsQuery.data]);
  const jobQueries = useQueries({
    queries: documentRecords.map((document) => ({
      queryKey: jobKey(document.id),
      queryFn: ({ signal }: { signal: AbortSignal }) => {
        if (!core.client) throw new Error("Learning core connection is unavailable.");
        return core.client.listIndexJobs(document.id, { signal });
      },
      enabled: live,
      retry: 1,
      staleTime: 500,
      refetchInterval: (query: { state: { data?: IndexJob[] } }) => isActiveJob(latestJob(query.state.data)) ? 750 : false,
    })),
  });

  const liveDocuments = useMemo(() => documentRecords.map((document, index) => (
    toDisplayDocument(document, latestJob(jobQueries[index]?.data), courseTitles)
  )), [courseTitles, documentRecords, jobQueries]);
  const failedJobQueries = jobQueries.filter((query) => query.isError);

  const documents = useMemo(() => isDemo
    ? demoDocuments
    : liveDocuments, [demoDocuments, isDemo, liveDocuments]);
  const textFiltered = useMemo(() => isDemo
    ? documents.filter((document) => document.name.toLowerCase().includes(search.toLowerCase()))
    : documents, [documents, isDemo, search]);
  const filtered = useMemo(() => textFiltered.filter((document) => courseFilter === "all"
    || (courseFilter === "unlinked" ? document.courseIds.length === 0 : document.courseIds.includes(courseFilter))), [courseFilter, textFiltered]);

  const terminalJobSignature = useMemo(() => documents
    .flatMap((document) => document.job && !isActiveJob(document.job) ? [`${document.job.id}:${document.job.status}:${document.job.updatedAt}`] : [])
    .join("|"), [documents]);

  useEffect(() => {
    if (live && terminalJobSignature) void queryClient.invalidateQueries({ queryKey: documentsKey });
  }, [documentsKey, live, queryClient, terminalJobSignature]);

  const inspect = (document: DisplayDocument) => setInspector({
    eyebrow: "Document details", title: document.name,
    body: `${document.pages} pages imported ${document.importedAt}.`,
    meta: [`Status: ${document.status}`, `Courses: ${document.course}`, `Parser: ${document.parser}`, `Index: ${document.embeddingModel}`, ...(document.error ? [`Error: ${document.error}`] : [])],
  });

  const addDemoFile = (file: File) => {
    const selectedCourse = courses.find((course) => course.id === selectedImportCourseId);
    setDemoDocuments((items) => [{
      id: `demo-${items.length + 1}`, name: file.name, course: selectedCourse?.title ?? "No courses",
      type: file.type === "application/pdf" ? "PDF" : file.name.endsWith(".md") ? "Markdown" : "TXT",
      pages: 0, importedAt: "Just now", status: "queued", parser: "Demo only", embeddingModel: "No index created",
      job: null, courseIds: selectedCourse ? [selectedCourse.id] : [], courseNames: selectedCourse ? [selectedCourse.title] : [],
      retrievalWarning: null, embeddingStatus: null, providerConfigured: false,
    }, ...items]);
    setImportNotice(`Demo only: the file name was added to sample state${selectedCourse ? ` and linked to ${selectedCourse.title}` : " without a course"}; the file was not uploaded or indexed.`);
  };

  const importFile = async (file: File | undefined) => {
    if (!file) return;
    setImportError(null);
    setImportNotice(null);
    if (isDemo) { addDemoFile(file); return; }
    if (!live || !core.client) {
      setImportError("Import did not start because the learning core is unavailable. The file was not read or stored; retry after the service is healthy.");
      return;
    }
    uploadController.current?.abort();
    const controller = new AbortController();
    uploadController.current = controller;
    setUploading(true);
    try {
      const result = await core.client.uploadDocument(file, selectedImportCourseId || undefined, { signal: controller.signal });
      queryClient.setQueryData<IndexJob[]>(jobKey(result.document.id), [result.job]);
      const linkNotice = selectedImportCourseId
        ? result.linked ? " The selected course was linked." : " The selected course was already linked."
        : " No course link changed.";
      setImportNotice(result.duplicate
        ? `${result.document.name} reused its existing document record and content identity.${linkNotice} Current job status: ${result.job.status}, progress ${result.job.progress}%.`
        : `${result.document.name} was stored and accepted as indexing job ${result.job.id}.${linkNotice} Current status: ${result.job.status}, progress ${result.job.progress}%.`);
      await queryClient.invalidateQueries({ queryKey: documentsKey });
    } catch (error) {
      await queryClient.invalidateQueries({ queryKey: documentsKey });
      if (controller.signal.aborted) {
        setImportNotice("Stopped waiting for the upload response. This did not send a server-side cancel request; the file may already have an indexing job. The document list was refreshed—use Cancel indexing if a job appears.");
        return;
      }
      if (error instanceof LearningCoreResponseError) {
        const reason = error.detail?.message ?? error.message;
        const recovery = error.detail?.recovery ? ` Recovery: ${error.detail.recovery}` : "";
        const retry = error.detail?.retryable === false
          ? " Do not retry the unchanged file."
          : error.detail?.retryable === true
            ? " Retry after following the recovery guidance."
            : "";
        const requestId = error.requestId ? ` Request ID: ${error.requestId}.` : "";
        setImportError(`Import did not complete (HTTP ${error.status}): ${reason}. The document list was refreshed because a failed status record may be present.${recovery}${retry}${requestId}`);
      } else {
        setImportError("Import did not return a confirmed result. The document list was refreshed because the local service may have committed before the connection failed. Retrying the same file is safe because content hashes are deduplicated.");
      }
    } finally {
      if (uploadController.current === controller) {
        uploadController.current = null;
        setUploading(false);
      }
    }
  };

  const updateJob = (job: IndexJob) => {
    queryClient.setQueryData<IndexJob[]>(jobKey(job.documentId), (jobs = []) => [job, ...jobs.filter((item) => item.id !== job.id)]);
  };

  const updateDocument = (document: IndexedDocument) => {
    queryClient.setQueryData<IndexedDocument[]>(documentsKey, (items = []) => items.map((item) => item.id === document.id ? document : item));
  };

  const updateDemoCourses = (documentId: string, courseIds: string[]) => {
    const sortedIds = [...courseIds].sort();
    const names = sortedIds.map((courseId) => courseTitles.get(courseId) ?? `Unknown course (${courseId})`);
    setDemoDocuments((items) => items.map((document) => document.id === documentId
      ? { ...document, courseIds: sortedIds, courseNames: names, course: names.join(", ") || "No courses" }
      : document));
  };

  const runDocumentOperation = async (document: DisplayDocument, operation: DocumentOperation, work: () => Promise<void>) => {
    setDocumentOperationError(null);
    setOperations((current) => ({ ...current, [document.id]: operation }));
    try {
      await work();
    } catch (error) {
      setDocumentOperationError(operationError(operationLabels[operation], error));
    } finally {
      setOperations((current) => ({ ...current, [document.id]: undefined }));
    }
  };

  const linkCourse = (document: DisplayDocument, courseId: string) => {
    const courseName = courseTitles.get(courseId) ?? courseId;
    if (isDemo) {
      updateDemoCourses(document.id, [...new Set([...document.courseIds, courseId])]);
      setImportNotice(`Demo only: ${courseName} was linked to ${document.name} in sample state.`);
      return;
    }
    if (!core.client) return;
    void runDocumentOperation(document, "linking", async () => {
      const result = await core.client!.linkDocumentCourse(document.id, courseId);
      updateDocument(result.document);
      setImportNotice(result.linked
        ? `${courseName} was linked to ${document.name}.`
        : `${document.name} was already linked to ${courseName}; no relationship changed.`);
    });
  };

  const unlinkCourse = (document: DisplayDocument, courseId: string) => {
    const courseName = courseTitles.get(courseId) ?? courseId;
    if (isDemo) {
      updateDemoCourses(document.id, document.courseIds.filter((id) => id !== courseId));
      setImportNotice(`Demo only: ${courseName} was unlinked from ${document.name}; the sample document was retained.`);
      return;
    }
    if (!core.client) return;
    void runDocumentOperation(document, "unlinking", async () => {
      await core.client!.unlinkDocumentCourse(document.id, courseId);
      queryClient.setQueryData<IndexedDocument[]>(documentsKey, (items = []) => items.map((item) => item.id === document.id
        ? { ...item, courseIds: item.courseIds.filter((id) => id !== courseId) }
        : item));
      setImportNotice(`${courseName} was unlinked from ${document.name}; the document and index were retained.`);
    });
  };

  const cancelJob = (document: DisplayDocument) => {
    if (!core.client || !document.job) return;
    void runDocumentOperation(document, "cancelling", async () => {
      const job = await core.client!.cancelIndexJob(document.job!.id);
      updateJob(job);
      setImportNotice(cancellationNotice(document.name, job));
    });
  };

  const retryDocument = (document: DisplayDocument) => {
    if (!core.client) return;
    void runDocumentOperation(document, "retrying", async () => {
      const result = await core.client!.retryDocument(document.id);
      updateJob(result.job);
      await queryClient.invalidateQueries({ queryKey: documentsKey });
      setImportNotice(`A new indexing job was queued for ${document.name}. Progress is ${result.job.progress}%.`);
    });
  };

  const reindexEmbeddings = (document: DisplayDocument) => {
    if (!core.client) return;
    void runDocumentOperation(document, "reindexing", async () => {
      const result = await core.client!.reindexDocumentEmbeddings(document.id);
      updateDocument(result.document);
      updateJob(result.job);
      setImportNotice(`Embedding reindex job ${result.job.id} was queued for ${document.name}. Its existing lexical index remains available while the local provider runs.`);
    });
  };

  const deleteDocument = (document: DisplayDocument) => {
    if (!core.client) return;
    const confirmed = window.confirm(`Permanently delete “${document.name}”, its stored file, chunks, and indexing history? This cannot be undone.`);
    if (!confirmed) return;
    setImportNotice(null);
    void runDocumentOperation(document, "deleting", async () => {
      try {
        await core.client!.deleteDocument(document.id);
      } catch (error) {
        const reconciliation = Promise.allSettled([
          queryClient.invalidateQueries({ queryKey: documentsKey }),
          queryClient.invalidateQueries({ queryKey: jobsKeyPrefix }),
        ]);
        if (isConfirmedPartialDelete(error)) {
          queryClient.setQueryData<typeof documentRecords>(documentsKey, (items = []) => items.filter((item) => item.id !== document.id));
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
      queryClient.setQueryData<typeof documentRecords>(documentsKey, (items = []) => items.filter((item) => item.id !== document.id));
      setImportNotice(`${document.name} and its local indexing data were deleted.`);
    });
  };

  const retry = () => {
    if (live) void documentsQuery.refetch();
    else void core.retry();
  };
  const totalChunks = documents.reduce((sum, document) => sum + (document.chunks ?? 0), 0);
  const showContent = isDemo || (live && documentsQuery.isSuccess);

  return (
    <Page title="Knowledge Base" description="Your private learning sources can be linked to multiple courses without duplicating or deleting the document." actions={<><label className="select-control import-course"><span>Import course</span><select aria-label="Course for imported document" value={selectedImportCourseId} disabled={uploading} onChange={(event) => setImportCourseId(event.target.value)}><option value="">No course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label><Button className="primary" disabled={uploading || (!isDemo && !live)} onClick={() => fileInput.current?.click()}><FilePlus2 size={15} />{uploading ? "Uploading…" : "Import files"}</Button>{uploading && <Button onClick={() => uploadController.current?.abort()}>Stop waiting</Button>}</>}>
      <input ref={fileInput} hidden type="file" accept=".pdf,.md,.txt,application/pdf,text/markdown,text/plain" onChange={(event) => { void importFile(event.target.files?.[0]); event.currentTarget.value = ""; }} />
      {isDemo && <div className="demo-disclosure"><Badge tone="warning">Browser Demo</Badge><span>Sample documents only. Files are not uploaded, parsed, or indexed.</span></div>}
      {!isDemo && core.status !== "healthy" && <KnowledgeState kind={isLearningCoreStarting(core.status) ? "loading" : core.status === "unavailable" ? "unavailable" : "error"} serviceMessage={core.serviceMessage} retryError={core.retryError} onRetry={retry} />}
      {!isDemo && live && documentsQuery.isPending && <KnowledgeState kind="loading" onRetry={retry} />}
      {!isDemo && live && documentsQuery.isError && <KnowledgeState kind="error" onRetry={retry} />}
      {showContent && <>
        {!isDemo && core.demoStateError && <div className="operation-error job-status-error" role="alert"><span>Course names and course-link controls could not be loaded. Document IDs and indexing status remain available; no relationship was changed.</span><Button onClick={() => { void core.retry(); }}>Retry courses</Button></div>}
        <Card className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void importFile(event.dataTransfer.files[0]); }}><UploadCloud size={24} /><div><strong>Drop a PDF, Markdown, or text file here</strong><span>Only the selected browser File is sent to the authenticated local service; arbitrary paths are never accepted.</span></div><Button disabled={uploading} onClick={() => fileInput.current?.click()}>Choose file</Button></Card>
        {importNotice && <div className="operation-notice" role="status">{importNotice}</div>}
        {importError && <div className="operation-error" role="alert">{importError}</div>}
        {documentOperationError && <div className="operation-error" role="alert">{documentOperationError}</div>}
        {!isDemo && failedJobQueries.length > 0 && <div className="operation-error job-status-error" role="alert">
          <span>Indexing job status could not be loaded for {failedJobQueries.length} {failedJobQueries.length === 1 ? "document" : "documents"}. Document metadata remains visible, but stage, progress, and job actions may be incomplete. No job was changed.</span>
          <Button onClick={() => { void Promise.all(failedJobQueries.map((query) => query.refetch())); }}>Retry job status</Button>
        </div>}
        <div className="library-tools"><div className="search-box"><Search size={15} /><input aria-label="Search documents" placeholder={isDemo ? "Filter sample files…" : "Search indexed content…"} value={search} onChange={(event) => setSearch(event.target.value)} /></div><label className="select-control"><Filter size={14} /><select aria-label="Filter documents by course" value={courseFilter} onChange={(event) => setCourseFilter(event.target.value)}><option value="all">All courses</option><option value="unlinked">No courses</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label><span className="library-count">{filtered.length} sources</span><Segmented value={view} options={["List", "Grid"]} onChange={setView} /></div>
        {!isDemo && serverSearch.length >= 2 && <SearchResults loading={searchQuery.isPending} error={searchQuery.error} results={searchQuery.data?.results ?? []} mode={searchQuery.data?.mode} warning={searchQuery.data?.warning} onRetry={() => { void searchQuery.refetch(); }} />}
        <DocumentCollection documents={filtered} view={view} demo={isDemo} operations={operations} courses={courses} onInspect={inspect} onCancel={cancelJob} onRetry={retryDocument} onReindex={reindexEmbeddings} onDelete={deleteDocument} onLinkCourse={linkCourse} onUnlinkCourse={unlinkCourse} />
        <div className="index-summary"><span><Grid2X2 size={14} />{isDemo ? "Sample index metadata" : `${totalChunks.toLocaleString()} chunks`}</span><span><List size={14} />{documents.length} {isDemo ? "sample sources" : "sources"}</span><span>{isDemo ? "No real index in browser Demo" : `${documents.filter((document) => document.status === "indexed-hybrid").length} hybrid · ${documents.filter((document) => document.status === "indexed-lexical").length} lexical-only · ${documents.filter((document) => document.status === "needs-reindex").length} need reindex`}</span></div>
      </>}
    </Page>
  );
}
