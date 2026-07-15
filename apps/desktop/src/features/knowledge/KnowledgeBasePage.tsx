import { useMemo, useState } from "react";
import { File, FilePlus2, Grid2X2, List, MoreHorizontal, RefreshCw, Search, UploadCloud } from "lucide-react";
import { Badge, Button, Card, Progress } from "@keen/ui";
import type { DocumentStatus, KnowledgeDocument } from "@keen/domain";
import { documents as seedDocuments } from "../../data/seed";
import { Page, Segmented } from "../../components/Page";
import { useAppStore } from "../../state/appStore";

const tones: Partial<Record<DocumentStatus, "success" | "warning" | "danger" | "accent">> = { indexed: "success", failed: "danger", partial: "warning", "needs-reindex": "warning", embedding: "accent", parsing: "accent" };

export function KnowledgeBasePage() {
  const [documents, setDocuments] = useState(seedDocuments);
  const [view, setView] = useState<"List" | "Grid">("List");
  const [search, setSearch] = useState("");
  const [dragging, setDragging] = useState(false);
  const { setInspector } = useAppStore();
  const filtered = useMemo(() => documents.filter((doc) => doc.name.toLowerCase().includes(search.toLowerCase())), [documents, search]);
  const inspect = (doc: KnowledgeDocument) => setInspector({ eyebrow: "Document details", title: doc.name, body: `${doc.pages} pages imported ${doc.importedAt}.`, meta: [`Status: ${doc.status}`, `Parser: ${doc.parser}`, `Embedding: ${doc.embeddingModel}`] });
  const retry = (id: string) => setDocuments((items) => items.map((d) => d.id === id ? { ...d, status: "embedding" as const } : d));
  return (
    <Page title="Knowledge Base" description="Your private learning sources. Files are processed locally unless a model provider requires remote embeddings." actions={<Button className="primary"><FilePlus2 size={15} />Import files</Button>}>
      <Card className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); setDocuments((d) => [{ id: `d${d.length + 1}`, name: e.dataTransfer.files[0]?.name ?? "Dropped document.pdf", course: "Unassigned", type: "PDF", pages: 0, importedAt: "Just now", status: "queued", parser: "Pending", embeddingModel: "Pending" }, ...d]); }}><UploadCloud size={24} /><div><strong>Drop PDFs, notes, or images here</strong><span>PDF, Markdown, TXT, and images with OCR · 100 MB max</span></div><Button>Choose files</Button></Card>
      <div className="library-tools"><div className="search-box"><Search size={15} /><input aria-label="Search documents" placeholder="Search files…" value={search} onChange={(e) => setSearch(e.target.value)} /></div><select className="input" aria-label="Filter course"><option>All courses</option><option>Linear Algebra</option><option>Biology 101</option></select><span className="library-count">{filtered.length} sources</span><Segmented value={view} options={["List", "Grid"]} onChange={setView} /></div>
      {view === "List" ? <Card className="document-table"><div className="document-row document-head"><span>Name</span><span>Course</span><span>Status</span><span>Imported</span><span /></div>{filtered.map((doc) => <button className="document-row" key={doc.id} onClick={() => inspect(doc)}><span className="document-name"><File size={17} /><span><strong>{doc.name}</strong><small>{doc.type} · {doc.pages || "—"} pages</small></span></span><span>{doc.course}</span><span><Badge tone={tones[doc.status]}>{doc.status}</Badge>{["embedding", "parsing", "OCR", "chunking"].includes(doc.status) && <Progress value={63} />}</span><span>{doc.importedAt}</span><span>{doc.status === "failed" || doc.status === "needs-reindex" ? <i role="button" aria-label="Retry indexing" onClick={(e) => { e.stopPropagation(); retry(doc.id); }}><RefreshCw size={15} /></i> : <MoreHorizontal size={15} />}</span></button>)}</Card> : <div className="document-grid">{filtered.map((doc) => <Card key={doc.id} onClick={() => inspect(doc)}><File size={24} /><Badge tone={tones[doc.status]}>{doc.status}</Badge><h3>{doc.name}</h3><p>{doc.course}</p><small>{doc.pages || "—"} pages · {doc.importedAt}</small></Card>)}</div>}
      <div className="index-summary"><span><Grid2X2 size={14} />4,218 chunks</span><span><List size={14} />5 sources</span><span>Embedding: mixed models</span></div>
    </Page>
  );
}
