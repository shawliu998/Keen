import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle, File, FilePlus2, Grid2X2, List, LoaderCircle,
  MoreHorizontal, Search, ServerOff, UploadCloud,
} from "lucide-react";
import { Badge, Button, Card, EmptyState } from "@keen/ui";
import type { DocumentStatus, KnowledgeDocument } from "@keen/domain";
import { LearningCoreResponseError, type IndexedDocument } from "@keen/api-client";
import { documents as seedDocuments } from "../../data/seed";
import { Page, Segmented } from "../../components/Page";
import { useAppStore } from "../../state/appStore";
import { useLearningCore } from "../../services/LearningCoreProvider";

type DisplayDocument = KnowledgeDocument & { chunks?: number; error?: string | null };

const tones: Partial<Record<DocumentStatus, "success" | "warning" | "danger" | "accent">> = {
  indexed: "success", failed: "danger", partial: "warning", "needs-reindex": "warning",
  queued: "warning", parsing: "accent", chunking: "accent",
};

function toDisplayDocument(document: IndexedDocument): DisplayDocument {
  const type: KnowledgeDocument["type"] = document.mimeType === "application/pdf"
    ? "PDF"
    : document.mimeType.startsWith("image/") ? "Image" : document.name.endsWith(".md") ? "Markdown" : "TXT";
  return {
    id: document.id,
    name: document.name,
    course: "Unassigned",
    type,
    pages: document.pageCount,
    importedAt: new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(document.createdAt)),
    status: document.status,
    parser: document.parser,
    embeddingModel: "Local FTS index",
    chunks: document.chunkCount,
    error: document.error,
  };
}

function KnowledgeState({ kind, onRetry }: { kind: "loading" | "unavailable" | "error"; onRetry: () => void }) {
  const loading = kind === "loading";
  return (
    <Card className="service-state" role={loading ? "status" : "alert"}>
      {loading ? <LoaderCircle className="spin" size={23} /> : kind === "error" ? <AlertCircle size={23} /> : <ServerOff size={23} />}
      <div>
        <strong>{loading ? "Loading the local document index" : kind === "unavailable" ? "Learning core is unavailable" : "Document index request failed"}</strong>
        <p>{loading
          ? "Keen is waiting for an authenticated response. Demo documents are not being substituted."
          : "The document list and search are affected. Existing files were not changed, no sample records were substituted, and no automatic retry modified your data. Retry now; restart Keen if this continues."}</p>
      </div>
      {!loading && <Button onClick={onRetry}>Retry</Button>}
    </Card>
  );
}

export function KnowledgeBasePage() {
  const core = useLearningCore();
  const queryClient = useQueryClient();
  const { setInspector } = useAppStore();
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const [demoDocuments, setDemoDocuments] = useState<DisplayDocument[]>(seedDocuments);
  const [view, setView] = useState<"List" | "Grid">("List");
  const [search, setSearch] = useState("");
  const [serverSearch, setServerSearch] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const isDemo = core.status === "demo";
  const live = core.status === "healthy" && core.client !== null;
  const documentsKey = [
    "learning-core",
    "documents",
    core.client?.baseUrl ?? "none",
    core.connectionGeneration,
  ] as const;

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
    ],
    queryFn: ({ signal }) => {
      if (!core.client) throw new Error("Learning core connection is unavailable.");
      return core.client.search({ query: serverSearch, limit: 20 }, { signal });
    },
    enabled: live && serverSearch.length >= 2,
    retry: 1,
  });

  const documents = useMemo(() => isDemo
    ? demoDocuments
    : (documentsQuery.data ?? []).map(toDisplayDocument), [demoDocuments, documentsQuery.data, isDemo]);
  const filtered = useMemo(() => isDemo
    ? documents.filter((document) => document.name.toLowerCase().includes(search.toLowerCase()))
    : documents, [documents, isDemo, search]);

  const inspect = (document: DisplayDocument) => setInspector({
    eyebrow: "Document details", title: document.name,
    body: `${document.pages} pages imported ${document.importedAt}.`,
    meta: [`Status: ${document.status}`, `Parser: ${document.parser}`, `Index: ${document.embeddingModel}`, ...(document.error ? [`Error: ${document.error}`] : [])],
  });

  const addDemoFile = (file: File) => {
    setDemoDocuments((items) => [{
      id: `demo-${items.length + 1}`, name: file.name, course: "Unassigned",
      type: file.type === "application/pdf" ? "PDF" : file.name.endsWith(".md") ? "Markdown" : "TXT",
      pages: 0, importedAt: "Just now", status: "queued", parser: "Demo only", embeddingModel: "No index created",
    }, ...items]);
    setImportNotice("Demo only: the file name was added to sample state; the file was not uploaded or indexed.");
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
      const result = await core.client.uploadDocument(file, undefined, { signal: controller.signal });
      setImportNotice(result.duplicate
        ? `${result.document.name} was already indexed; no duplicate copy was created.`
        : `${result.document.name} was accepted by the local indexer; current status: ${result.document.status}.`);
      await queryClient.invalidateQueries({ queryKey: documentsKey });
    } catch (error) {
      await queryClient.invalidateQueries({ queryKey: documentsKey });
      if (controller.signal.aborted) return;
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

  const retry = () => {
    if (live) void documentsQuery.refetch();
    else void core.retry();
  };
  const totalChunks = documents.reduce((sum, document) => sum + (document.chunks ?? 0), 0);
  const showContent = isDemo || (live && documentsQuery.isSuccess);

  return (
    <Page title="Knowledge Base" description="Your private learning sources. Files stay local in this milestone; indexed text is treated as untrusted content." actions={<Button className="primary" disabled={uploading || (!isDemo && !live)} onClick={() => fileInput.current?.click()}><FilePlus2 size={15} />{uploading ? "Importing…" : "Import files"}</Button>}>
      <input ref={fileInput} hidden type="file" accept=".pdf,.md,.txt,application/pdf,text/markdown,text/plain" onChange={(event) => { void importFile(event.target.files?.[0]); event.currentTarget.value = ""; }} />
      {isDemo && <div className="demo-disclosure"><Badge tone="warning">Browser Demo</Badge><span>Sample documents only. Files are not uploaded, parsed, or indexed.</span></div>}
      {!isDemo && core.status !== "healthy" && <KnowledgeState kind={core.status === "starting" ? "loading" : core.status === "unavailable" ? "unavailable" : "error"} onRetry={retry} />}
      {!isDemo && live && documentsQuery.isPending && <KnowledgeState kind="loading" onRetry={retry} />}
      {!isDemo && live && documentsQuery.isError && <KnowledgeState kind="error" onRetry={retry} />}
      {showContent && <>
        <Card className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void importFile(event.dataTransfer.files[0]); }}><UploadCloud size={24} /><div><strong>Drop a PDF, Markdown, or text file here</strong><span>Only the selected browser File is sent to the authenticated local service; arbitrary paths are never accepted.</span></div><Button disabled={uploading} onClick={() => fileInput.current?.click()}>Choose file</Button></Card>
        {importNotice && <div className="operation-notice" role="status">{importNotice}</div>}
        {importError && <div className="operation-error" role="alert">{importError}</div>}
        <div className="library-tools"><div className="search-box"><Search size={15} /><input aria-label="Search documents" placeholder={isDemo ? "Filter sample files…" : "Search indexed content…"} value={search} onChange={(event) => setSearch(event.target.value)} /></div><span className="library-count">{filtered.length} sources</span><Segmented value={view} options={["List", "Grid"]} onChange={setView} /></div>
        {!isDemo && serverSearch.length >= 2 && <SearchResults loading={searchQuery.isPending} error={searchQuery.error} results={searchQuery.data?.results ?? []} onRetry={() => { void searchQuery.refetch(); }} />}
        <DocumentCollection documents={filtered} view={view} onInspect={inspect} />
        <div className="index-summary"><span><Grid2X2 size={14} />{isDemo ? "Sample index metadata" : `${totalChunks.toLocaleString()} chunks`}</span><span><List size={14} />{documents.length} {isDemo ? "sample sources" : "sources"}</span><span>{isDemo ? "No real index in browser Demo" : "Local FTS index"}</span></div>
      </>}
    </Page>
  );
}

function SearchResults({ loading, error, results, onRetry }: {
  loading: boolean;
  error: Error | null;
  results: { chunkId: string; documentName: string; pageNumber: number; sectionPath: string[]; text: string }[];
  onRetry: () => void;
}) {
  if (loading) return <Card className="search-results" role="status"><LoaderCircle className="spin" size={17} />Searching the local index…</Card>;
  if (error) {
    const responseError = error instanceof LearningCoreResponseError ? error : null;
    const status = responseError ? ` (HTTP ${responseError.status})` : "";
    const reason = responseError?.detail?.message ?? error.message;
    const recovery = responseError?.detail?.recovery ? ` Recovery: ${responseError.detail.recovery}` : "";
    const requestId = responseError?.requestId ? ` Request ID: ${responseError.requestId}.` : "";
    const retryable = responseError?.detail?.retryable !== false;
    return <Card className="search-results operation-error" role="alert">Search failed{status}: {reason}. No results were changed.{recovery}{requestId}{retryable && <Button onClick={onRetry}>Try search again</Button>}</Card>;
  }
  return <Card className="search-results"><strong>Indexed text results</strong>{results.length === 0 ? <p>No matching indexed text was found.</p> : results.map((result) => <div className="search-result" key={result.chunkId}><span>{result.documentName} · page {result.pageNumber}{result.sectionPath.length > 0 ? ` · ${result.sectionPath.join(" / ")}` : ""}</span><p>{result.text}</p></div>)}</Card>;
}

function DocumentCollection({ documents, view, onInspect }: {
  documents: DisplayDocument[];
  view: "List" | "Grid";
  onInspect: (document: DisplayDocument) => void;
}) {
  if (documents.length === 0) return <Card><EmptyState icon={<File size={28} />} title="No documents" description="Import a supported file to create the first local index record." /></Card>;
  if (view === "Grid") return <div className="document-grid">{documents.map((document) => <Card key={document.id} onClick={() => onInspect(document)}><File size={24} /><Badge tone={tones[document.status]}>{document.status}</Badge><h3>{document.name}</h3><p>{document.course}</p><small>{document.pages || "—"} pages · {document.importedAt}</small></Card>)}</div>;
  return <Card className="document-table"><div className="document-row document-head"><span>Name</span><span>Course</span><span>Status</span><span>Imported</span><span /></div>{documents.map((document) => <button className="document-row" key={document.id} onClick={() => onInspect(document)}><span className="document-name"><File size={17} /><span><strong>{document.name}</strong><small>{document.type} · {document.pages || "—"} pages</small></span></span><span>{document.course}</span><span><Badge tone={tones[document.status]}>{document.status}</Badge></span><span>{document.importedAt}</span><span>{document.status === "failed" ? <AlertCircle aria-label="Indexing failed" size={15} /> : <MoreHorizontal size={15} />}</span></button>)}</Card>;
}
