import { useState } from "react";
import { ChevronDown, File, LoaderCircle } from "lucide-react";
import { Badge, Button, EmptyState, Progress, Select } from "@keen/ui";
import type { CourseOption, DocumentDisplayStatus, DisplayDocument } from "./documentJobs";
import { canCancelJob, canReindexEmbeddings, canRetryJob, isActiveJob } from "./documentJobs";

const tones: Partial<Record<DocumentDisplayStatus, "success" | "warning" | "danger" | "accent">> = {
  queued: "warning", validating: "accent", stored: "accent", parsing: "accent", chunking: "accent",
  lexical_indexing: "accent", embedding: "accent", finalizing: "accent", running: "accent",
  cancel_requested: "warning", cancelled: "warning", completed: "success", indexed: "success",
  "indexed-lexical": "warning", "indexed-hybrid": "success", failed: "danger", interrupted: "danger",
  partial: "warning", "needs-reindex": "warning",
};

const labels: Partial<Record<DocumentDisplayStatus, string>> = {
  queued: "Queued", validating: "Validating", stored: "Stored", parsing: "Parsing", chunking: "Chunking",
  lexical_indexing: "Indexing text", embedding: "Embedding", finalizing: "Finalizing",
  cancel_requested: "Cancel requested", cancelled: "Cancelled", completed: "Indexed", failed: "Failed",
  interrupted: "Interrupted", indexed: "Indexed", "indexed-lexical": "Text indexed",
  "indexed-hybrid": "Fully indexed", pending: "Pending", "needs-reindex": "Needs reindex",
};

type DocumentAction = "cancelling" | "retrying" | "reindexing" | "deleting" | "linking" | "unlinking";

type DocumentCollectionProps = {
  documents: DisplayDocument[];
  totalDocuments: number;
  demo: boolean;
  selectedId: string | null;
  operations: Record<string, DocumentAction | undefined>;
  onInspect: (document: DisplayDocument) => void;
  onImport: () => void;
  onClearFilters: () => void;
  onStartLearning: (courseId: string) => void;
  onCancel: (document: DisplayDocument) => void;
  onRetry: (document: DisplayDocument) => void;
  onReindex: (document: DisplayDocument) => void;
  onDelete: (document: DisplayDocument) => void;
  courses: CourseOption[];
  onLinkCourse: (document: DisplayDocument, courseId: string) => void;
  onUnlinkCourse: (document: DisplayDocument, courseId: string) => void;
};

export type DocumentDetailPanelProps = {
  document: DisplayDocument;
  demo: boolean;
  operation?: DocumentAction;
  courses: CourseOption[];
  onStartLearning: (courseId: string) => void;
  onCancel: () => void;
  onRetry: () => void;
  onReindex: () => void;
  onDelete: () => void;
  onLinkCourse: (courseId: string) => void;
  onUnlinkCourse: (courseId: string) => void;
};

function LearningHandoff({ document, courses, onStart }: {
  document: DisplayDocument;
  courses: CourseOption[];
  onStart: (courseId: string) => void;
}) {
  const linkedCourses = courses.filter((course) => document.courseIds.includes(course.id));
  const [selection, setSelection] = useState("");
  const ready = document.chunks !== undefined
    && document.chunks > 0
    && !isActiveJob(document.job)
    && ["indexed", "indexed-lexical", "indexed-hybrid"].includes(document.status);
  if (!ready || linkedCourses.length === 0) return null;
  const selectedCourseId = linkedCourses.length === 1
    ? linkedCourses[0].id
    : linkedCourses.some((course) => course.id === selection) ? selection : "";
  const selectedCourse = linkedCourses.find((course) => course.id === selectedCourseId) ?? null;
  return <div className="document-learning-handoff">
    <span className="document-detail-label">Learning action</span>
    <p>{selectedCourse ? `Start focused study using the indexed material available across ${selectedCourse.title}.` : "Choose which linked course should provide the indexed material for focused study."}</p>
    <span className="course-link-control">
      {linkedCourses.length > 1 ? <Select controlSize="small" aria-label={`Course for learning from ${document.name}`} value={selectedCourseId} onChange={(event) => setSelection(event.target.value)}><option value="">Choose a course</option>{linkedCourses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</Select> : null}
      <Button className="primary" disabled={!selectedCourseId} onClick={() => onStart(selectedCourseId)}>Start focused study</Button>
    </span>
  </div>;
}

function Status({ document, demo }: { document: DisplayDocument; demo: boolean }) {
  if (demo) return <span className="document-job-status"><Badge>Sample</Badge></span>;
  const progress = document.job?.progress;
  const statusLabel = labels[document.status] ?? document.status;
  const badgeLabel = document.job?.status === "queued" && document.job.stage !== "queued"
    ? `${statusLabel} · ${labels[document.job.stage] ?? document.job.stage}`
    : statusLabel;
  return <span className="document-job-status">
    <Badge tone={tones[document.status]}>{badgeLabel}</Badge>
    {progress !== undefined && isActiveJob(document.job) ? <span className="document-progress"><Progress value={progress} label={`${document.name} indexing progress ${progress}%`} /><small>{progress}%</small></span> : null}
  </span>;
}

function capabilityCopy(document: DisplayDocument, demo: boolean) {
  if (demo) return "Sample source organization only; no file or index exists.";
  if (document.error) return document.error;
  if (document.retrievalWarning) return document.retrievalWarning;
  if (isActiveJob(document.job)) return "This source is still being prepared. Progress updates from the current indexing job appear above.";
  if (document.status === "indexed-hybrid") return "Available for indexed text and embedding retrieval.";
  if (document.status === "indexed-lexical" || document.status === "indexed") return "Available for indexed text search.";
  if (document.status === "failed" || document.status === "interrupted") return "Indexing needs attention before this source can be used reliably.";
  return "Review the current source status before using it for a learning request.";
}

function IndexActions({ document, operation, onCancel, onRetry, onReindex }: {
  document: DisplayDocument;
  operation?: DocumentAction;
  onCancel: () => void;
  onRetry: () => void;
  onReindex: () => void;
}) {
  const busy = operation !== undefined;
  const actionable = canCancelJob(document.job) || canRetryJob(document.job) || canReindexEmbeddings(document);
  if (!actionable) return null;
  return <div className="document-index-actions">
    <span className="document-detail-label">Indexing action</span>
    <span className="document-actions">
    {canCancelJob(document.job) ? <Button disabled={busy} onClick={onCancel}>{operation === "cancelling" ? <LoaderCircle className="spin" size={12} /> : null}Cancel indexing</Button> : null}
    {canRetryJob(document.job) ? <Button disabled={busy} onClick={onRetry}>{operation === "retrying" ? <LoaderCircle className="spin" size={12} /> : null}Retry indexing</Button> : null}
    {canReindexEmbeddings(document) ? <Button disabled={busy} onClick={onReindex}>{operation === "reindexing" ? <LoaderCircle className="spin" size={12} /> : null}Reindex embeddings</Button> : null}
    </span>
  </div>;
}

function CourseMembership({ document, courses, operation, onLink, onUnlink }: {
  document: DisplayDocument;
  courses: CourseOption[];
  operation?: DocumentAction;
  onLink: (courseId: string) => void;
  onUnlink: (courseId: string) => void;
}) {
  const available = courses.filter((course) => !document.courseIds.includes(course.id));
  const [selection, setSelection] = useState("");
  const selectedCourseId = available.some((course) => course.id === selection) ? selection : available[0]?.id ?? "";
  const busy = operation !== undefined;
  return <div className="document-course-editor">
    <span className="document-detail-label">Course scope</span>
    <span className="course-links">
      {document.courseIds.length === 0 ? <small>No course</small> : null}
      {document.courseIds.map((courseId, index) => <span className="course-chip" key={courseId}>
        <span title={document.courseNames[index]}>{document.courseNames[index]}</span>
        <button type="button" disabled={busy} aria-label={`Unlink ${document.courseNames[index]} from ${document.name}`} onClick={() => onUnlink(courseId)}>Remove</button>
      </span>)}
    </span>
    {available.length > 0 ? <span className="course-link-control">
      <Select controlSize="small" aria-label={`Course to link to ${document.name}`} value={selectedCourseId} disabled={busy} onChange={(event) => setSelection(event.target.value)}>
        {available.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
      </Select>
      <Button disabled={busy || !selectedCourseId} onClick={() => onLink(selectedCourseId)}>{operation === "linking" ? <LoaderCircle className="spin" size={12} /> : null}Link course</Button>
    </span> : null}
  </div>;
}

export function DocumentDetailPanel({
  document,
  demo,
  operation,
  courses,
  onStartLearning,
  onCancel,
  onRetry,
  onReindex,
  onDelete,
  onLinkCourse,
  onUnlinkCourse,
}: DocumentDetailPanelProps) {
  return <div className="document-row-detail">
    <div className="document-learning-overview">
      <div className="document-detail-copy"><span className="document-detail-label">Availability</span><p>{capabilityCopy(document, demo)}</p></div>
      {!demo ? <LearningHandoff document={document} courses={courses} onStart={onStartLearning} /> : null}
      {!demo ? <IndexActions document={document} operation={operation} onCancel={onCancel} onRetry={onRetry} onReindex={onReindex} /> : null}
    </div>
    {!demo ? <details className="document-source-settings">
      <summary><span><strong>Source settings</strong><small>Course links and deletion</small></span><ChevronDown size={15} aria-hidden="true" /></summary>
      <div className="document-source-settings-body">
        <CourseMembership document={document} courses={courses} operation={operation} onLink={onLinkCourse} onUnlink={onUnlinkCourse} />
        <div className="document-danger-action"><span className="document-detail-label">Delete source</span><p>Remove this local source and its indexing data from Keen.</p><Button className="danger" disabled={operation !== undefined} onClick={onDelete}>{operation === "deleting" ? <LoaderCircle className="spin" size={12} /> : null}Delete source</Button></div>
      </div>
    </details> : null}
  </div>;
}

export function DocumentCollection(props: DocumentCollectionProps) {
  const { documents, totalDocuments, demo, selectedId, operations, onInspect, onImport, onClearFilters, onStartLearning, onCancel, onRetry, onReindex, onDelete, courses, onLinkCourse, onUnlinkCourse } = props;
  if (documents.length === 0) {
    const filteredEmpty = totalDocuments > 0;
    return <div className="knowledge-empty"><EmptyState
      icon={<File size={24} />}
      title={filteredEmpty ? "No matching sources" : "No sources yet"}
      description={filteredEmpty ? "Clear the current search or course scope to see the full source list." : demo ? "Add a sample file name to preview source organization." : "Import a PDF, Markdown, or text file. Selection alone does not mean indexing is complete."}
      action={<Button onClick={filteredEmpty ? onClearFilters : onImport}>{filteredEmpty ? "Clear filters" : demo ? "Add sample source" : "Import source"}</Button>}
    /></div>;
  }
  return <div className="document-table" role="list" aria-label="Sources">
    <div className="document-row document-head" aria-hidden="true"><span>Source</span><span>Course scope</span><span>Status</span><span>Changed</span></div>
    {documents.map((document) => {
      const selected = selectedId === document.id;
      return <div className={`document-list-item ${selected ? "selected" : ""}`} role="listitem" key={document.id}>
        <button type="button" className="document-row" aria-label={`Open source details: ${document.name}`} aria-expanded={selected} onClick={() => onInspect(document)}>
          <span className="document-name"><File size={16} aria-hidden="true" /><span><strong title={document.name}>{document.name}</strong><small>{document.type} · {document.pages || "—"} {document.pages === 1 ? "page" : "pages"}</small></span></span>
          <span className="document-course-summary" title={document.courseNames.join(", ") || "No course"}>{document.courseNames.join(", ") || "No course"}</span>
          <Status document={document} demo={demo} />
          <span className="document-changed">{document.importedAt}</span>
        </button>
        {selected ? <DocumentDetailPanel
          document={document}
          demo={demo}
          operation={operations[document.id]}
          courses={courses}
          onStartLearning={onStartLearning}
          onCancel={() => onCancel(document)}
          onRetry={() => onRetry(document)}
          onReindex={() => onReindex(document)}
          onDelete={() => onDelete(document)}
          onLinkCourse={(courseId) => onLinkCourse(document, courseId)}
          onUnlinkCourse={(courseId) => onUnlinkCourse(document, courseId)}
        /> : null}
      </div>;
    })}
  </div>;
}
