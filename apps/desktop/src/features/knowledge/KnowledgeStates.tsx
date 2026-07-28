import { AlertCircle, LoaderCircle, ServerOff } from "lucide-react";
import { Button, Card } from "@keen/ui";
import { LearningCoreResponseError } from "@keen/api-client";

export function operationError(action: string, error: unknown): string {
  if (error instanceof LearningCoreResponseError) {
    const reason = error.detail?.message ?? error.message;
    const recovery = error.detail?.recovery ? ` Recovery: ${error.detail.recovery}` : "";
    const requestId = error.requestId ? ` Request ID: ${error.requestId}.` : "";
    return `${action} failed (HTTP ${error.status}): ${reason}.${recovery}${requestId}`;
  }
  return `${action} did not return a confirmed result. Refresh the document status before trying again.`;
}

export function isConfirmedPartialDelete(error: unknown): error is LearningCoreResponseError {
  return error instanceof LearningCoreResponseError
    && error.detail?.message.toLowerCase().includes("document record was deleted") === true;
}

export function KnowledgeState({ kind, serviceMessage, retryError, onRetry }: {
  kind: "unavailable" | "error";
  serviceMessage?: string | null;
  retryError?: string | null;
  onRetry: () => void;
}) {
  return <Card className="service-state knowledge-service-state" role="alert">
    {kind === "error" ? <AlertCircle size={23} /> : <ServerOff size={23} />}
    <div>
      <strong>{kind === "unavailable" ? "Sources are unavailable" : "Sources could not be loaded"}</strong>
      <p>{serviceMessage ?? "Your saved sources were not changed. Retry the affected source list."}</p>
      {retryError && <p className="service-retry-error" role="alert">{retryError}</p>}
    </div>
    <Button onClick={onRetry}>Retry</Button>
  </Card>;
}

export function KnowledgeRestoreSkeleton() {
  return <div className="knowledge-restore" role="status" aria-label="Restoring sources">
    <span className="visually-hidden">Restoring sources</span>
    <div className="knowledge-restore-scope" />
    <div className="knowledge-restore-heading" />
    <div className="knowledge-restore-tools"><i /><i /></div>
    <div className="knowledge-restore-list">{[0, 1, 2, 3].map((item) => <div key={item}><i /><span><i /><i /></span><i /><i /></div>)}</div>
  </div>;
}

export function SearchResults({ loading, error, results, mode, warning, onRetry }: {
  loading: boolean;
  error: Error | null;
  results: { chunkId: string; chunkIds: string[]; documentName: string; pageNumber: number; pageEnd: number; sectionPath: string[]; text: string }[];
  mode?: "hybrid" | "lexical_only";
  warning?: string | null;
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
  const modeLabel = mode === "hybrid" ? "Hybrid lexical + vector results" : "Lexical-only indexed text results";
  return <Card className="search-results"><strong>{modeLabel}</strong>{warning && <p className="search-mode-warning" role="status">{warning}</p>}{results.length === 0 ? <p>No matching indexed text was found.</p> : results.map((result) => <div className="search-result" key={result.chunkIds.join(":")}><span>{result.documentName} · {result.pageEnd === result.pageNumber ? `page ${result.pageNumber}` : `pages ${result.pageNumber}–${result.pageEnd}`}{result.sectionPath.length > 0 ? ` · ${result.sectionPath.join(" / ")}` : ""}</span><p>{result.text}</p></div>)}</Card>;
}
