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
  kind: "loading" | "unavailable" | "error";
  serviceMessage?: string | null;
  retryError?: string | null;
  onRetry: () => void;
}) {
  const loading = kind === "loading";
  return <Card className="service-state" role={loading ? "status" : "alert"}>
    {loading ? <LoaderCircle className="spin" size={23} /> : kind === "error" ? <AlertCircle size={23} /> : <ServerOff size={23} />}
    <div>
      <strong>{loading ? "Loading the local document index" : kind === "unavailable" ? "Learning core is unavailable" : "Document index request failed"}</strong>
      <p>{serviceMessage ?? (loading
        ? "Keen is waiting for an authenticated response. Demo documents are not being substituted."
        : "The document list and search are affected. Existing files were not replaced, and no sample records were substituted. Follow the current recovery guidance, then retry.")}</p>
      {retryError && <p className="service-retry-error" role="alert">{retryError}</p>}
    </div>
    {!loading && <Button onClick={onRetry}>Retry</Button>}
  </Card>;
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
