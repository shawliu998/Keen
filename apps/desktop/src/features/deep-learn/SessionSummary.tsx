import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Square } from "lucide-react";
import { Badge, Button, Card } from "@keen/ui";
import {
  LearningCoreResponseError,
  type AutonomousStudySession,
  type LearningCoreClient,
  type StudySummaryFinalizeResponse,
  type StudySummaryReadResponse,
} from "@keen/api-client";

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

function Metrics({ value }: { value: { active_recall_correct: boolean; practice_correct: boolean; practice_score: number; practice_max_score: number; task_completed: boolean } | null }) {
  if (!value) return null;
  return <><p><strong>Active recall:</strong> {value.active_recall_correct ? "correct" : "incorrect"}</p><p><strong>Targeted practice:</strong> {value.practice_correct ? "correct" : "incorrect"} · {value.practice_score} / {value.practice_max_score}</p></>;
}

export function SessionSummary({
  client, sessionId, courseId, session, onSessionChanged,
}: {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  session: AutonomousStudySession;
  onSessionChanged: () => void;
}) {
  const [summary, setSummary] = useState<SummaryState | null>(null);
  const [loading, setLoading] = useState(true);
  const [writing, setWriting] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [retry, setRetry] = useState<Intent | null>(null);
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
      setSummary(result); setRetry(null); onSessionChanged();
    } catch (error) {
      if (!current(expected)) return;
      const restored = await reconcile(expected);
      if (error instanceof LearningCoreResponseError && error.status === 409) {
        setRetry(null); if (!restored) setSummary(null);
        setNotice(restored
          ? { tone: "error", text: "This session changed before the summary completed. Keen restored the latest local state." }
          : { tone: "error", text: "This session changed, but Keen could not restore the latest summary. No local review was retried." });
      } else if (error instanceof LearningCoreResponseError && error.status >= 400 && error.status < 500) {
        setRetry(null); if (!restored) setSummary(null);
        setNotice(error.status === 404
          ? { tone: "error", text: "This local summary is unavailable for the current course. No local review was retried." }
          : { tone: "error", text: "The local summary action was rejected. No local review was retried; restore the current state before trying again." });
      } else if (isCompleted(restored)) {
        setRetry(null);
      } else {
        setRetry(intent);
        setNotice({ tone: "unknown", text: "Keen could not safely determine whether the local review was scheduled. Retry the same request; editing is locked until it is resolved." });
      }
    } finally {
      if (current(expected)) { writeController.current = null; writingRef.current = false; setWriting(false); }
    }
  };

  if (loading) return <Card className="checkpoint" role="status"><LoaderCircle className="spin" size={18} /><p>Restoring your local learning summary…</p></Card>;
  if (notice && !summary) return <Card className="checkpoint" role="alert"><strong>Summary unavailable</strong><p>{notice.text}</p><Button onClick={() => { setLoading(true); setNotice(null); void restore(scope); }}>Retry summary restore</Button></Card>;
  if (!summary) return null;
  if (summary.outcome === "cancelled") return <Card className="checkpoint" role="status"><Badge tone="warning">Session ended</Badge><h3>Learning summary unavailable</h3><p>The local session ended before its summary was finalized. No review was scheduled from this step.</p></Card>;
  if (summary.session.status === "paused") return <Card className="checkpoint" role="status"><Badge tone="warning">Session paused</Badge><h3>Summary restored</h3><p>No local review action was sent while this session is paused. Resume the local session before finishing.</p></Card>;
  if (isCompleted(summary)) return <Card className="checkpoint" aria-labelledby="session-summary-title"><Badge tone="success">Local review scheduled</Badge><h3 id="session-summary-title">Session complete</h3><Metrics value={summary.summary} /><p>{summary.review ? `One local review is due ${new Date(summary.review.due_at).toLocaleString()} (${summary.review.scheduler} · ${summary.review.scheduler_version}).` : "No local review schedule was returned."}</p></Card>;
  return <Card className="checkpoint" aria-labelledby="session-summary-title"><Badge tone="accent">Learning summary</Badge><h3 id="session-summary-title">Ready to finish this local session</h3><Metrics value={summary.summary} /><p>Finishing schedules one local FSRS review. It does not add another mastery observation.</p>{notice && <p className={`diagnostic-notice ${notice.tone}`} role="alert">{notice.text}</p>}<div className="checkpoint-actions"><Button className="primary" disabled={writing} onClick={() => { void finalize(); }}>{writing ? <LoaderCircle className="spin" size={14} /> : null}{writing ? "Scheduling local review…" : retry ? "Retry same local review" : "Finish and schedule local review"}</Button>{writing && <Button onClick={() => writeController.current?.abort()}><Square size={14} />Cancel</Button>}</div></Card>;
}
