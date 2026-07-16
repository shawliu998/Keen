import { useState } from "react";
import { AlertCircle, File, LoaderCircle } from "lucide-react";
import { Badge, Button, Card, EmptyState, Progress } from "@keen/ui";
import type { CourseOption, DocumentDisplayStatus, DisplayDocument } from "./documentJobs";
import { canCancelJob, canReindexEmbeddings, canRetryJob } from "./documentJobs";

const tones: Partial<Record<DocumentDisplayStatus, "success" | "warning" | "danger" | "accent">> = {
  queued: "warning",
  validating: "accent",
  stored: "accent",
  parsing: "accent",
  chunking: "accent",
  lexical_indexing: "accent",
  embedding: "accent",
  finalizing: "accent",
  running: "accent",
  cancel_requested: "warning",
  cancelled: "warning",
  completed: "success",
  indexed: "success",
  "indexed-lexical": "warning",
  "indexed-hybrid": "success",
  failed: "danger",
  interrupted: "danger",
  partial: "warning",
  "needs-reindex": "warning",
};

const labels: Partial<Record<DocumentDisplayStatus, string>> = {
  queued: "Queued",
  validating: "Validating",
  stored: "Stored",
  parsing: "Parsing",
  chunking: "Chunking",
  lexical_indexing: "Lexical indexing",
  embedding: "Embedding",
  finalizing: "Finalizing",
  cancel_requested: "Cancel requested",
  cancelled: "Cancelled",
  completed: "Completed",
  failed: "Failed",
  interrupted: "Interrupted",
  indexed: "Indexed",
  "indexed-lexical": "Indexed · lexical only",
  "indexed-hybrid": "Indexed · hybrid",
  pending: "Pending",
  "needs-reindex": "Needs reindex",
};

type DocumentAction = "cancelling" | "retrying" | "reindexing" | "deleting" | "linking" | "unlinking";

type DocumentCollectionProps = {
  documents: DisplayDocument[];
  view: "List" | "Grid";
  demo: boolean;
  operations: Record<string, DocumentAction | undefined>;
  onInspect: (document: DisplayDocument) => void;
  onCancel: (document: DisplayDocument) => void;
  onRetry: (document: DisplayDocument) => void;
  onReindex: (document: DisplayDocument) => void;
  onDelete: (document: DisplayDocument) => void;
  courses: CourseOption[];
  onLinkCourse: (document: DisplayDocument, courseId: string) => void;
  onUnlinkCourse: (document: DisplayDocument, courseId: string) => void;
};

function Status({ document }: { document: DisplayDocument }) {
  const progress = document.job?.progress;
  const statusLabel = labels[document.status] ?? document.status;
  const badgeLabel = document.job?.status === "queued" && document.job.stage !== "queued"
    ? `${statusLabel} · ${labels[document.job.stage] ?? document.job.stage}`
    : statusLabel;
  return <span className="document-job-status">
    <Badge tone={tones[document.status]}>{badgeLabel}</Badge>
    {progress !== undefined && <><Progress value={progress} label={`${document.name} indexing progress ${progress}%`} /><small>{progress}%</small></>}
  </span>;
}

function Actions({ document, demo, operation, onCancel, onRetry, onReindex, onDelete }: {
  document: DisplayDocument;
  demo: boolean;
  operation?: DocumentAction;
  onCancel: () => void;
  onRetry: () => void;
  onReindex: () => void;
  onDelete: () => void;
}) {
  if (demo) return null;
  const busy = operation !== undefined;
  return <span className="document-actions">
    {canCancelJob(document.job) && <Button disabled={busy} onClick={onCancel}>{operation === "cancelling" ? <LoaderCircle className="spin" size={12} /> : null}Cancel indexing</Button>}
    {document.job?.status === "cancel_requested" && <Button disabled>Cancel requested</Button>}
    {canRetryJob(document.job) && <Button disabled={busy} onClick={onRetry}>{operation === "retrying" ? <LoaderCircle className="spin" size={12} /> : null}Retry indexing</Button>}
    {canReindexEmbeddings(document) && <Button disabled={busy} onClick={onReindex}>{operation === "reindexing" ? <LoaderCircle className="spin" size={12} /> : null}Reindex embeddings</Button>}
    {document.embeddingStatus === "provider-missing" && <Button disabled title="Configure a supported loopback embedding provider and restart the learning core first.">Provider required</Button>}
    <Button className="danger" disabled={busy} onClick={onDelete}>{operation === "deleting" ? <LoaderCircle className="spin" size={12} /> : null}Delete</Button>
  </span>;
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
  return <span className="document-courses">
    <span className="course-links">
      {document.courseIds.length === 0 && <small>No courses</small>}
      {document.courseIds.map((courseId, index) => <span className="course-chip" key={courseId}>
        {document.courseNames[index]}
        <button type="button" disabled={busy} aria-label={`Unlink ${document.courseNames[index]} from ${document.name}`} onClick={() => onUnlink(courseId)}>×</button>
      </span>)}
    </span>
    <span className="course-link-control">
      <select aria-label={`Course to link to ${document.name}`} value={selectedCourseId} disabled={busy || available.length === 0} onChange={(event) => setSelection(event.target.value)}>
        {available.length === 0 ? <option value="">No courses available</option> : available.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
      </select>
      <Button disabled={busy || !selectedCourseId} onClick={() => onLink(selectedCourseId)}>{operation === "linking" ? <LoaderCircle className="spin" size={12} /> : null}Link</Button>
    </span>
  </span>;
}

export function DocumentCollection(props: DocumentCollectionProps) {
  const { documents, view, demo, operations, onInspect, onCancel, onRetry, onReindex, onDelete, courses, onLinkCourse, onUnlinkCourse } = props;
  if (documents.length === 0) return <Card><EmptyState icon={<File size={28} />} title="No documents" description="Import a supported file to create the first local index record." /></Card>;
  if (view === "Grid") return <div className="document-grid">{documents.map((document) => <Card key={document.id}>
    <button className="document-grid-open" onClick={() => onInspect(document)}><File size={24} /><h3>{document.name}</h3><small>{document.pages || "—"} pages · {document.importedAt}</small></button>
    <CourseMembership document={document} courses={courses} operation={operations[document.id]} onLink={(courseId) => onLinkCourse(document, courseId)} onUnlink={(courseId) => onUnlinkCourse(document, courseId)} />
    <Status document={document} />
    {document.error && <span className="document-error"><AlertCircle size={13} />{document.error}</span>}
    {document.retrievalWarning && <span className="document-index-warning"><AlertCircle size={13} />{document.retrievalWarning}</span>}
    <Actions document={document} demo={demo} operation={operations[document.id]} onCancel={() => onCancel(document)} onRetry={() => onRetry(document)} onReindex={() => onReindex(document)} onDelete={() => onDelete(document)} />
  </Card>)}</div>;
  return <Card className="document-table">
    <div className="document-row document-head"><span>Name</span><span>Course</span><span>Status & progress</span><span>Imported</span><span>Actions</span></div>
    {documents.map((document) => <div className="document-row" key={document.id}>
      <button className="document-name" onClick={() => onInspect(document)}><File size={17} /><span><strong>{document.name}</strong><small>{document.type} · {document.pages || "—"} pages</small></span></button>
      <CourseMembership document={document} courses={courses} operation={operations[document.id]} onLink={(courseId) => onLinkCourse(document, courseId)} onUnlink={(courseId) => onUnlinkCourse(document, courseId)} />
      <span><Status document={document} />{document.error && <small className="document-error"><AlertCircle size={12} />{document.error}</small>}{document.retrievalWarning && <small className="document-index-warning"><AlertCircle size={12} />{document.retrievalWarning}</small>}</span>
      <span>{document.importedAt}</span>
      <Actions document={document} demo={demo} operation={operations[document.id]} onCancel={() => onCancel(document)} onRetry={() => onRetry(document)} onReindex={() => onReindex(document)} onDelete={() => onDelete(document)} />
    </div>)}
  </Card>;
}
