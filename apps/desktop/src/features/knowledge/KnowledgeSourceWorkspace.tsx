import { File, Files, FolderOpen } from "lucide-react";
import type { LearningCoreClient } from "@keen/api-client";
import { Badge } from "@keen/ui";
import type { DisplayDocument } from "./documentJobs";
import { KnowledgeSourcePreview } from "./KnowledgeSourcePreview";

function statusLabel(document: DisplayDocument, demo: boolean): string {
  if (demo) return "Sample";
  const label = document.status.replaceAll("_", " ").replaceAll("-", " ");
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}`;
}

export function KnowledgeSourceWorkspace({
  documents,
  selected,
  demo,
  client,
  detailPanel,
  onSelect,
}: {
  documents: DisplayDocument[];
  selected: DisplayDocument;
  demo: boolean;
  client: LearningCoreClient | null;
  detailPanel: React.ReactNode;
  onSelect: (document: DisplayDocument) => void;
}) {
  return <section className="knowledge-source-workspace" aria-label="Source workspace">
    <aside className="knowledge-source-rail" aria-label="Sources in this course library">
      <header><span><FolderOpen size={17} aria-hidden="true" /><strong>Sources</strong></span><Badge>{documents.length}</Badge></header>
      <div className="knowledge-source-rail-list" role="list">
        {documents.map((document) => <button
          type="button"
          role="listitem"
          key={document.id}
          className={document.id === selected.id ? "is-selected" : ""}
          aria-current={document.id === selected.id ? "true" : undefined}
          aria-label={`Open source workspace: ${document.name}`}
          onClick={() => onSelect(document)}
        >
          <File size={16} aria-hidden="true" />
          <span><strong title={document.name}>{document.name}</strong><small>{document.type} · {document.pages || "—"} {document.pages === 1 ? "page" : "pages"}</small></span>
        </button>)}
      </div>
    </aside>
    <div className="knowledge-source-content">
      <header className="knowledge-source-header">
        <div className="knowledge-source-title"><Files size={19} aria-hidden="true" /><span><strong title={selected.name}>{selected.name}</strong><small>{selected.courseNames.join(", ") || "No course"} · {selected.type} · {selected.pages || "—"} {selected.pages === 1 ? "page" : "pages"}</small></span></div>
        <Badge>{statusLabel(selected, demo)}</Badge>
      </header>
      <KnowledgeSourcePreview key={selected.id} document={selected} demo={demo} client={client} />
      <div className="knowledge-source-details">{detailPanel}</div>
    </div>
  </section>;
}
