import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Square } from "lucide-react";
import { Badge, Button, Card } from "@keen/ui";
import {
  LearningCoreResponseError,
  type AutonomousStudySession,
  type LearningCoreClient,
  type StudySummaryFinalizeResponse,
  type StudySummaryReadResponse,
} from "@keen/api-client";
import { LearningStepRestore } from "./LearningStepRestore";
import { invalidateLearningContinuityQueries } from "../learningContinuityQueries";

type SummaryState = StudySummaryReadResponse | StudySummaryFinalizeResponse;
type Notice = { tone: "error" | "unknown" | "cancelled"; text: string } | null;
type Intent = { key: string; revision: number };

function idempotencyKey(): string {
  const id = globalThis.crypto?.randomUUID?.();
  return id ? `study-summary-${id}` : `study-summary-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function isCompleted(value: SummaryState | null): boolean {
  return value?.outcome === "completed" || (value?.outcome === "applied" || value?.outcome === "replayed");
}

function formatReviewDue(value: string): string {
  const appLocale = document.documentElement.lang || "en";
  return new Intl.DateTimeFormat(appLocale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

const MAX_TIMEOUT_DELAY = 2_147_483_647;

function Metrics({ value }: { value: { active_recall_correct: boolean; practice_correct: boolean; practice_score: number; practice_max_score: number; task_completed: boolean } | null }) {
  if (!value) return null;
  return <dl className="learning-outcome-metrics">
    <div><dt>Active recall</dt><dd>{value.active_recall_correct ? "Correct" : "Needs review"}</dd></div>
    <div><dt>Targeted practice</dt><dd>{value.practice_correct ? "Correct" : "Needs review"} · {value.practice_score} / {value.practice_max_score}</dd></div>
  </dl>;
}

function CompletionMetrics({ value }: { value: { active_recall_correct: boolean; practice_correct: boolean; practice_score: number; practice_max_score: number } | null }) {
  if (!value) return null;
  return <dl className="session-complete-metrics"><div><dt>Active recall</dt><dd>{value.active_recall_correct ? "Correct" : "Incorrect"}</dd></div><div><dt>Targeted practice</dt><dd>{value.practice_correct ? "Correct" : "Incorrect"} · {value.practice_score} / {value.practice_max_score}</dd></div></dl>;
}

export function SessionSummary({
  client, sessionId, courseId, session, onSessionChanged, onOpenReview, onOpenFeed,
}: {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  session: AutonomousStudySession;
  onSessionChanged: () => void;
  onOpenReview: () => void;
  onOpenFeed: () => void;
}) {
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState<SummaryState | null>(null);
  const [loading, setLoading] = useState(true);
  const [writing, setWriting] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [retry, setRetry] = useState<Intent | null>(null);
  const [reviewClock, setReviewClock] = useState(() => Date.now());
  const mounted = useRef(true);
  const scope = `${sessionId}:${courseId}`;
  const scopeRef = useRef(scope);
  const restoreController = useRef<AbortController | null>(null);
  const writeController = useRef<AbortController | null>(null);
  const writingRef = useRef(false);

  useEffect(() => { scopeRef.current = scope; }, [scope]);
  useEffect(() => () => {
    mounted.current = false;
    restoreController.current?.abort();
    writeController.current?.abort();
  }, []);
  const current = (expected: string) => mounted.current && scopeRef.current === expected;
  const restore = useCallback(async (expected: string): Promise<StudySummaryReadResponse | null> => {
    const controller = new AbortController();
    restoreController.current?.abort();
    restoreController.current = controller;
    try {
      const result = await client.getStudySessionSummary(sessionId, courseId, { signal: controller.signal });
      if (!current(expected)) return null;
      setSummary(result); setLoading(false);
      return result;
    } catch (error) {
      if (!current(expected) || restoreController.current !== controller) return null;
      setLoading(false);
      setNotice(isAbort(error)
        ? { tone: "cancelled", text: "Summary restore was cancelled. No local review was scheduled." }
        : error instanceof LearningCoreResponseError && error.status === 404
          ? { tone: "error", text: "This local summary is unavailable for the current course." }
          : { tone: "error", text: "Keen could not restore this local summary. Retry after the learning core recovers." });
      return null;
    } finally {
      if (restoreController.current === controller) restoreController.current = null;
    }
  }, [client, courseId, sessionId]);

  useEffect(() => {
    mounted.current = true;
    const timer = window.setTimeout(() => { void restore(scope); }, 0);
    return () => window.clearTimeout(timer);
  }, [restore, scope]);

  const reviewDueAt = summary?.review ? Date.parse(summary.review.due_at) : Number.NaN;
  useEffect(() => {
    let timer: number | null = null;
    const update = () => {
      const now = Date.now();
      setReviewClock(now);
      if (Number.isFinite(reviewDueAt) && reviewDueAt > now) {
        timer = window.setTimeout(update, Math.min(MAX_TIMEOUT_DELAY, Math.max(1, reviewDueAt - now)));
      }
    };
    update();
    return () => { if (timer !== null) window.clearTimeout(timer); };
  }, [reviewDueAt]);

  const reconcile = async (expected: string) => {
    const restored = await restore(expected);
    if (restored) onSessionChanged();
    return restored;
  };
  const finalize = async () => {
    if (writingRef.current || session.status === "paused" || !current(scope) || !summary || summary.outcome !== "ready") return;
    const expected = scope;
    const intent = retry ?? { key: idempotencyKey(), revision: summary.session.revision };
    const controller = new AbortController();
    writeController.current = controller; writingRef.current = true; setWriting(true); setNotice(null);
    try {
      const result = await client.finalizeStudySessionSummary(
        sessionId,
        { course_id: courseId, expected_revision: intent.revision, idempotency_key: intent.key },
        { signal: controller.signal },
      );
      if (!current(expected)) return;
      setSummary(result); setRetry(null);
      await invalidateLearningContinuityQueries(queryClient);
      if (current(expected)) onSessionChanged();
    } catch (error) {
      if (!current(expected)) return;
      const restored = await reconcile(expected);
      if (isCompleted(restored)) {
        setRetry(null);
        await invalidateLearningContinuityQueries(queryClient);
      } else if (error instanceof LearningCoreResponseError && error.status === 409) {
        setRetry(null); if (!restored) setSummary(null);
        setNotice(restored
          ? { tone: "error", text: "This session changed before the summary completed. Keen restored the latest local state." }
          : { tone: "error", text: "This session changed, but Keen could not restore the latest summary. No local review was retried." });
      } else if (error instanceof LearningCoreResponseError && error.status >= 400 && error.status < 500) {
        setRetry(null); if (!restored) setSummary(null);
        setNotice(error.status === 404
          ? { tone: "error", text: "This local summary is unavailable for the current course. No local review was retried." }
          : { tone: "error", text: "The local summary action was rejected. No local review was retried; restore the current state before trying again." });
      } else {
        setRetry(intent);
        setNotice({ tone: "unknown", text: "Keen could not safely determine whether the local review was scheduled. Retry the same request; editing is locked until it is resolved." });
      }
    } finally {
      if (current(expected)) { writeController.current = null; writingRef.current = false; setWriting(false); }
    }
  };

  if (loading && session.status === "completed") return <div className="session-complete-loading" role="status"><span>Restoring session result…</span><i className="restore-line heading" aria-hidden="true" /><i className="restore-line medium" aria-hidden="true" /></div>;
  if (loading) return <LearningStepRestore label="Restoring learning summary…" />;
  if (notice && !summary) return <Card className="checkpoint" role="alert"><strong>Summary unavailable</strong><p>{notice.text}</p><Button onClick={() => { setLoading(true); setNotice(null); void restore(scope); }}>Retry summary restore</Button></Card>;
  if (!summary) return null;
  if (summary.outcome === "cancelled") return <Card className="checkpoint" role="status"><Badge tone="warning">Session ended</Badge><h3>Learning summary unavailable</h3><p>The local session ended before its summary was finalized. No review was scheduled from this step.</p></Card>;
  if (summary.session.status === "paused") return <Card className="checkpoint" role="status"><Badge tone="warning">Session paused</Badge><h3>Summary restored</h3><p>No local review action was sent while this session is paused. Resume the local session before finishing.</p></Card>;
  if (isCompleted(summary)) {
    const validReviewDue = summary.review !== null && Number.isFinite(reviewDueAt);
    const reviewDue = validReviewDue && reviewDueAt <= reviewClock;
    return <section className="session-complete-result" aria-labelledby="session-summary-title"><h2 id="session-summary-title">Session complete</h2><p className="session-complete-schedule">{validReviewDue && summary.review ? <>Review scheduled for <time dateTime={summary.review.due_at}>{formatReviewDue(summary.review.due_at)}</time></> : summary.review ? "The review schedule is unavailable. Return to the queue to refresh it." : "No review was scheduled."}</p><Button className="primary session-complete-review" loading={writing} loadingLabel="Refreshing saved work…" disabled={writing} onClick={reviewDue ? onOpenReview : onOpenFeed}>{reviewDue ? "Review now" : "Return to learning queue"}</Button><CompletionMetrics value={summary.summary} />{reviewDue ? <button type="button" className="session-complete-feed" disabled={writing} onClick={onOpenFeed}>View Learning Feed</button> : null}</section>;
  }
  return <Card className="checkpoint learning-outcome session-summary-ready" aria-labelledby="session-summary-title">
    <Badge tone="accent">Ready to finish</Badge>
    <h2 id="session-summary-title">Finish this study session</h2>
    <p className="learning-outcome-copy">Your recall and practice results are saved. Finish to add the next review to your queue.</p>
    <Metrics value={summary.summary} />
    {notice && <p className={`diagnostic-notice ${notice.tone}`} role="alert">{notice.text}</p>}
    <div className="checkpoint-actions"><Button className="primary" disabled={writing} onClick={() => { void finalize(); }}>{writing ? <LoaderCircle className="spin" size={14} /> : null}{writing ? "Scheduling review…" : retry ? "Retry same review" : "Finish and schedule review"}</Button>{writing && <Button onClick={() => writeController.current?.abort()}><Square size={14} />Cancel</Button>}</div>
  </Card>;
}
