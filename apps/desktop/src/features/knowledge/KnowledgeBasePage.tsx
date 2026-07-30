import { useEffect, useMemo, useRef, useState } from "react";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, FilePlus2, Filter, FolderOpen, Search, UploadCloud, X } from "lucide-react";
import { Badge, Button } from "@keen/ui";
import { LearningCoreResponseError, type IndexJob } from "@keen/api-client";
import { useNavigate } from "react-router-dom";
import { documents as seedDocuments } from "../../data/seed";
import { Page } from "../../components/Page";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { DocumentCollection, DocumentDetailPanel } from "./DocumentCollection";
import { CourseCreateForm } from "./CourseCreateForm";
import { KnowledgeSourceWorkspace } from "./KnowledgeSourceWorkspace";
import { KnowledgeRestoreSkeleton, KnowledgeState, SearchResults } from "./KnowledgeStates";
import { isActiveJob, latestJob, toDemoDocument, toDisplayDocument, type DisplayDocument } from "./documentJobs";
import { demoCourseByTitle, useKnowledgeCourses } from "./useKnowledgeCourses";
import { useDocumentActions } from "./useDocumentActions";
import "./knowledgeCenter.css";

export function KnowledgeBasePage() {
  const core = useLearningCore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const [demoDocuments, setDemoDocuments] = useState<DisplayDocument[]>(() => seedDocuments.map((document) => (
    toDemoDocument(document, demoCourseByTitle.get(document.course)!)
  )));
  const [search, setSearch] = useState("");
  const [serverSearch, setServerSearch] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [courseFilter, setCourseFilter] = useState("all");
  const [importCourseId, setImportCourseId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const isDemo = core.status === "demo";
  const live = core.status === "healthy" && core.client !== null;
  const courseConnectionId = `${core.client?.baseUrl ?? "none"}:${core.connectionGeneration}`;
  const { courses, courseTitles, addCreatedCourse } = useKnowledgeCourses({
    isDemo,
    persistedCourses: core.demoState?.courses,
    connectionId: courseConnectionId,
  });
  const selectedImportCourseId = courses.some((course) => course.id === importCourseId) ? importCourseId : "";
  const documentsKey = useMemo(() => [
    "learning-core", "documents", core.client?.baseUrl ?? "none", core.connectionGeneration,
  ] as const, [core.client, core.connectionGeneration]);
  const jobsKeyPrefix = useMemo(() => [
    "learning-core", "index-jobs", core.client?.baseUrl ?? "none", core.connectionGeneration,
  ] as const, [core.client?.baseUrl, core.connectionGeneration]);
  const courseCacheKey = useMemo(() => [
    "learning-core", "demo-state", core.client ? Number(new URL(core.client.baseUrl).port) : "none", core.connectionGeneration,
  ] as const, [core.client, core.connectionGeneration]);
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
      "learning-core", "document-search", core.client?.baseUrl ?? "none", core.connectionGeneration, serverSearch, courseFilter,
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
  const documents = useMemo(() => isDemo ? demoDocuments : liveDocuments, [demoDocuments, isDemo, liveDocuments]);
  const textFiltered = useMemo(() => isDemo
    ? documents.filter((document) => document.name.toLowerCase().includes(search.toLowerCase()))
    : documents, [documents, isDemo, search]);
  const filtered = useMemo(() => textFiltered.filter((document) => courseFilter === "all"
    || (courseFilter === "unlinked" ? document.courseIds.length === 0 : document.courseIds.includes(courseFilter))), [courseFilter, textFiltered]);
  const courseLibraries = useMemo(() => courses.map((course) => {
    const linkedDocuments = documents.filter((document) => document.courseIds.includes(course.id));
    const readySources = linkedDocuments.filter((document) => document.chunks !== undefined
      && document.chunks > 0
      && !isActiveJob(document.job)
      && ["indexed", "indexed-lexical", "indexed-hybrid"].includes(document.status)).length;
    return { ...course, sourceCount: linkedDocuments.length, readySources };
  }), [courses, documents]);
  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId],
  );
  const workspaceCourseId = selectedDocument
    ? courseFilter !== "all" && courseFilter !== "unlinked" && selectedDocument.courseIds.includes(courseFilter)
      ? courseFilter
      : selectedDocument.courseIds[0] ?? null
    : null;
  const workspaceDocuments = useMemo(() => selectedDocument
    ? workspaceCourseId
      ? documents.filter((document) => document.courseIds.includes(workspaceCourseId))
      : documents.filter((document) => document.courseIds.length === 0)
    : [], [documents, selectedDocument, workspaceCourseId]);
  const workspaceTitle = workspaceCourseId
    ? courses.find((course) => course.id === workspaceCourseId)?.title ?? "Source workspace"
    : "Unlinked sources";
  const terminalJobSignature = useMemo(() => documents
    .flatMap((document) => document.job && !isActiveJob(document.job) ? [`${document.job.id}:${document.job.status}:${document.job.updatedAt}`] : [])
    .join("|"), [documents]);

  useEffect(() => {
    if (live && terminalJobSignature) void queryClient.invalidateQueries({ queryKey: documentsKey });
  }, [documentsKey, live, queryClient, terminalJobSignature]);

  const inspect = (document: DisplayDocument) => {
    setSelectedDocumentId(document.id);
  };

  const addDemoFile = (file: File) => {
    const selectedCourse = courses.find((course) => course.id === selectedImportCourseId);
    setDemoDocuments((items) => [{
      id: `demo-${items.length + 1}`, name: file.name, course: selectedCourse?.title ?? "No course",
      type: file.type === "application/pdf" ? "PDF" : file.name.endsWith(".md") ? "Markdown" : "TXT",
      pages: 0, importedAt: "Just now", status: "queued", parser: "Sample", embeddingModel: "Not applicable",
      job: null, courseIds: selectedCourse ? [selectedCourse.id] : [], courseNames: selectedCourse ? [selectedCourse.title] : [],
      retrievalWarning: null, embeddingStatus: null, providerConfigured: false,
    }, ...items]);
    setImportNotice(`Added ${file.name} to this sample list${selectedCourse ? ` under ${selectedCourse.title}` : " without a course"}. No file was uploaded or indexed.`);
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
        const retry = error.detail?.retryable === false ? " Do not retry the unchanged file." : error.detail?.retryable === true ? " Retry after following the recovery guidance." : "";
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

  const {
    operations, documentOperationError, linkCourse, unlinkCourse,
    cancelJob, retryDocument, reindexEmbeddings, deleteDocument,
  } = useDocumentActions({
    client: core.client, isDemo, courseTitles, documentsKey, jobsKeyPrefix, jobKey,
    queryClient, setDemoDocuments, setImportNotice,
  });
  const retry = () => { if (live) void documentsQuery.refetch(); else void core.retry(); };
  const showContent = isDemo || (live && documentsQuery.isSuccess);
  const showImportPanel = showContent && importOpen;
  const noSources = showContent && documents.length === 0;
  const clearSourceFilters = () => { setSearch(""); setServerSearch(""); setCourseFilter("all"); };

  return <Page
    className={`knowledge-page knowledge-center ${selectedDocument ? "knowledge-source-page" : ""}`}
    title={selectedDocument ? workspaceTitle : "Knowledge Base"}
    description={selectedDocument ? `${workspaceDocuments.length} ${workspaceDocuments.length === 1 ? "source" : "sources"} · Review local content, readiness, and learning actions.` : "Organize course libraries, import source material, and keep learning readiness visible."}
    actions={selectedDocument
      ? <Button aria-label="Back to Knowledge Base" onClick={() => setSelectedDocumentId(null)}><ArrowLeft size={15} />All libraries</Button>
      : noSources && !showImportPanel
        ? undefined
        : <><Button className="primary" aria-controls="knowledge-import-panel" aria-expanded={showImportPanel} disabled={uploading || (!isDemo && !live)} onClick={() => setImportOpen((open) => !open)}><FilePlus2 size={15} />{uploading ? "Importing…" : showImportPanel ? "Close import" : isDemo ? "Add sample source" : "Import source"}</Button>{uploading ? <Button onClick={() => uploadController.current?.abort()}>Stop waiting</Button> : null}</>}
  >
    <input ref={fileInput} hidden type="file" accept=".pdf,.md,.txt,application/pdf,text/markdown,text/plain" onChange={(event) => { void importFile(event.target.files?.[0]); event.currentTarget.value = ""; }} />
    {!isDemo && isLearningCoreStarting(core.status) ? <KnowledgeRestoreSkeleton /> : null}
    {!isDemo && !isLearningCoreStarting(core.status) && core.status !== "healthy" ? <KnowledgeState kind={core.status === "unavailable" ? "unavailable" : "error"} serviceMessage={core.serviceMessage} retryError={core.retryError} onRetry={retry} /> : null}
    {!isDemo && live && documentsQuery.isPending ? <KnowledgeRestoreSkeleton /> : null}
    {!isDemo && live && documentsQuery.isError ? <KnowledgeState kind="error" onRetry={retry} /> : null}
    {showContent && selectedDocument ? <>
      {!isDemo && core.demoStateError ? <div className="operation-error job-status-error" role="alert"><span>Course names and course-link controls could not be loaded. Document IDs and indexing status remain available; no relationship was changed.</span><Button onClick={() => { void core.retry(); }}>Retry courses</Button></div> : null}
      {importNotice ? <div className="operation-notice" role="status">{importNotice}</div> : null}
      {documentOperationError ? <div className="operation-error" role="alert">{documentOperationError}</div> : null}
      {!isDemo && failedJobQueries.length > 0 ? <div className="operation-error job-status-error" role="alert"><span>Indexing job status could not be loaded for {failedJobQueries.length} {failedJobQueries.length === 1 ? "source" : "sources"}. Source metadata remains visible, but progress and actions may be incomplete. No job was changed.</span><Button onClick={() => { void Promise.all(failedJobQueries.map((query) => query.refetch())); }}>Retry job status</Button></div> : null}
      <KnowledgeSourceWorkspace
        documents={workspaceDocuments}
        selected={selectedDocument}
        demo={isDemo}
        client={live ? core.client : null}
        onSelect={inspect}
        detailPanel={<DocumentDetailPanel
          document={selectedDocument}
          demo={isDemo}
          operation={operations[selectedDocument.id]}
          courses={courses}
          onStartLearning={(courseId) => navigate(`/?mode=study&course_id=${encodeURIComponent(courseId)}`)}
          onCancel={() => cancelJob(selectedDocument)}
          onRetry={() => retryDocument(selectedDocument)}
          onReindex={() => reindexEmbeddings(selectedDocument)}
          onDelete={() => deleteDocument(selectedDocument)}
          onLinkCourse={(courseId) => linkCourse(selectedDocument, courseId)}
          onUnlinkCourse={(courseId) => unlinkCourse(selectedDocument, courseId)}
        />}
      />
    </> : null}
    {showContent && !selectedDocument ? <>
      <section className={`knowledge-import-panel ${showImportPanel ? "is-open" : "is-collapsed"}`} id="knowledge-import-panel" hidden={!showImportPanel} aria-label={isDemo ? "Add sample source" : "Import source"}>
        <div className="knowledge-import-heading">
          <div><h2>{isDemo ? "Add a sample source" : "Import a local source"}</h2><p>{isDemo ? "Choose a file to add its name and type to this session-only sample list. Its contents are not read." : "PDF, Markdown, and plain text are accepted. A selected file is not presented as indexed until the local service confirms each stage."}</p></div>
          {documents.length > 0 ? <Button className="knowledge-import-close" aria-label="Close import panel" onClick={() => setImportOpen(false)}><X size={15} /></Button> : null}
        </div>
        <div className="knowledge-import-options">
          <label className="knowledge-import-course"><span>Course scope</span><select aria-label="Course for imported document" value={selectedImportCourseId} disabled={uploading} onChange={(event) => setImportCourseId(event.target.value)}><option value="">No course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label>
          <span>{isDemo ? "This changes sample organization only." : "Course links can be changed later without duplicating the source."}</span>
        </div>
        <div className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void importFile(event.dataTransfer.files[0]); }}><span className="dropzone-icon"><UploadCloud size={20} /></span><div><strong>{isDemo ? "Choose one sample file" : "Drop one file here"}</strong><span>{isDemo ? "Only its name and type are used in this browser session." : "The selected file is sent to Keen's authenticated local service; the resulting row shows stored and indexing states separately."}</span></div><Button disabled={uploading} onClick={() => fileInput.current?.click()}>{uploading ? "Waiting…" : isDemo ? "Choose sample file" : "Choose file"}</Button></div>
      </section>
      {!isDemo && core.demoStateError ? <div className="operation-error job-status-error" role="alert"><span>Course names and course-link controls could not be loaded. Document IDs and indexing status remain available; no relationship was changed.</span><Button onClick={() => { void core.retry(); }}>Retry courses</Button></div> : null}
      {importNotice ? <div className="operation-notice" role="status">{importNotice}</div> : null}
      {importError ? <div className="operation-error" role="alert">{importError}</div> : null}
      {documentOperationError ? <div className="operation-error" role="alert">{documentOperationError}</div> : null}
      {!isDemo && failedJobQueries.length > 0 ? <div className="operation-error job-status-error" role="alert"><span>Indexing job status could not be loaded for {failedJobQueries.length} {failedJobQueries.length === 1 ? "source" : "sources"}. Source metadata remains visible, but progress and actions may be incomplete. No job was changed.</span><Button onClick={() => { void Promise.all(failedJobQueries.map((query) => query.refetch())); }}>Retry job status</Button></div> : null}
      {noSources && !showImportPanel ? <section className="knowledge-first-source" aria-labelledby="knowledge-first-source-title">
        <div className="knowledge-first-source-main">
          <span className="knowledge-first-source-icon" aria-hidden="true"><FilePlus2 size={22} /></span>
          <h2 id="knowledge-first-source-title">No sources yet</h2>
          <p>Import a PDF, Markdown, or text file to begin. Keen will show storage and indexing progress before the source becomes available for learning.</p>
          <Button className="primary" aria-controls="knowledge-import-panel" aria-expanded="false" onClick={() => setImportOpen(true)}><FilePlus2 size={15} />{isDemo ? "Add sample source" : "Import source"}</Button>
        </div>
        {!isDemo ? <details className="knowledge-first-course">
          <summary><span><strong>{courses.length === 0 ? "Optional: create a course library" : `${courses.length} ${courses.length === 1 ? "course library is" : "course libraries are"} ready`}</strong><small>{courses.length === 0 ? "You can also organize this source after importing it." : "Create another library, or choose one during import."}</small></span><span className="knowledge-course-summary-action">{courses.length === 0 ? "Create course" : "Manage courses"} <ChevronDown size={14} /></span></summary>
          <CourseCreateForm
            key={courseConnectionId}
            client={live && core.demoState ? core.client : null}
            cacheKey={courseCacheKey}
            demo={false}
            onCreated={(course) => { addCreatedCourse(course); setImportCourseId(course.id); setImportOpen(true); }}
          />
        </details> : null}
      </section> : null}
      {!noSources ? <>
      <section className="knowledge-course-library" aria-labelledby="knowledge-course-library-title">
        <div className="knowledge-course-library-heading">
          <div><h2 id="knowledge-course-library-title">Course libraries</h2><p>Choose a library to narrow the source list below.</p></div>
          <Badge>{courses.length}</Badge>
        </div>
        {courseLibraries.length > 0 ? <div className="knowledge-course-grid">
          {courseLibraries.map((course) => {
            const selected = courseFilter === course.id;
            const state = isDemo ? "Sample" : course.sourceCount === 0 ? "Empty" : course.readySources === course.sourceCount ? "Ready" : course.readySources > 0 ? `${course.readySources} ready` : "Preparing";
            const tone = isDemo || course.sourceCount === 0 ? "neutral" : course.readySources === course.sourceCount ? "success" : "warning";
            return <button type="button" className={`knowledge-course-card ${selected ? "is-selected" : ""}`} key={course.id} aria-label={`${selected ? "Show all sources instead of" : "Filter sources by"} ${course.title}`} aria-pressed={selected} onClick={() => setCourseFilter(selected ? "all" : course.id)}>
              <span className="knowledge-course-card-top"><FolderOpen size={18} aria-hidden="true" /><strong title={course.title}>{course.title}</strong><Badge tone={tone}>{state}</Badge></span>
              <span className="knowledge-course-card-meta">{course.sourceCount} {course.sourceCount === 1 ? "source" : "sources"}{!isDemo && course.sourceCount > 0 ? ` · ${course.readySources} ready for learning` : ""}</span>
            </button>;
          })}
        </div> : <p className="knowledge-course-empty">No course library exists yet. Sources may remain unlinked until you create one.</p>}
      </section>
      {!isDemo ? <details className="knowledge-course-settings">
        <summary aria-label="Manage course scopes"><span><strong>Manage course libraries</strong><small>{courses.length === 0 ? "Create the first course, or keep sources unlinked" : `${courses.length} ${courses.length === 1 ? "course" : "courses"}`}</small></span><span className="knowledge-course-summary-action">Manage <ChevronDown size={14} /></span></summary>
        <CourseCreateForm
          key={courseConnectionId}
          client={live && core.demoState ? core.client : null}
          cacheKey={courseCacheKey}
          demo={false}
          onCreated={(course) => { addCreatedCourse(course); setImportCourseId(course.id); setImportOpen(true); }}
        />
      </details> : null}
      <div className="knowledge-library-heading"><div><h2>Sources</h2><p>Select a source to review availability and existing actions.</p></div><span>{filtered.length} of {documents.length}</span></div>
      <div className="library-tools"><div className="search-box"><Search size={15} /><input aria-label="Search documents" placeholder={isDemo ? "Filter sample source names…" : "Search indexed source text…"} value={search} onChange={(event) => setSearch(event.target.value)} /></div><label className="select-control"><Filter size={14} /><select aria-label="Filter documents by course" value={courseFilter} onChange={(event) => setCourseFilter(event.target.value)}><option value="all">All course scopes</option><option value="unlinked">No course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label></div>
      {!isDemo && serverSearch.length >= 2 ? <SearchResults loading={searchQuery.isPending} error={searchQuery.error} results={searchQuery.data?.results ?? []} mode={searchQuery.data?.mode} warning={searchQuery.data?.warning} onRetry={() => { void searchQuery.refetch(); }} /> : null}
      <DocumentCollection documents={filtered} totalDocuments={documents.length} demo={isDemo} selectedId={selectedDocumentId} operations={operations} courses={courses} onInspect={inspect} onImport={() => setImportOpen(true)} onClearFilters={clearSourceFilters} onStartLearning={(courseId) => navigate(`/?mode=study&course_id=${encodeURIComponent(courseId)}`)} onCancel={cancelJob} onRetry={retryDocument} onReindex={reindexEmbeddings} onDelete={deleteDocument} onLinkCourse={linkCourse} onUnlinkCourse={unlinkCourse} />
      </> : null}
    </> : null}
  </Page>;
}
