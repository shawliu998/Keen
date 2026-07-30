import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { LoaderCircle, Square } from "lucide-react";
import { Badge, Button, Card } from "@keen/ui";
import {
  LearningCoreResponseError,
  type AutonomousStudySession,
  type LearningCoreClient,
  type TargetedPracticeProgressionResponse,
  type TargetedPracticeReadResponse,
} from "@keen/api-client";
import { LearningStepRestore } from "./LearningStepRestore";
import { BlankStatement, readableClozePrompt } from "../clozePrompt";

type PracticeState = TargetedPracticeReadResponse | TargetedPracticeProgressionResponse;
type Operation = "begin" | "answer";
type Intent = { kind: Operation; key: string; revision: number; runId?: string; response?: string };
type Notice = { tone: "error" | "unknown" | "cancelled"; text: string } | null;

function idempotencyKey(): string {
  const id = globalThis.crypto?.randomUUID?.();
  return id ? `targeted-practice-${id}` : `targeted-practice-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function practiceOutcome(value: PracticeState | null): "not_started" | "pending" | "answered" | "cancelled" | null {
  if (!value) return null;
  if (value.outcome === "applied" || value.outcome === "replayed") return value.run.status === "pending" ? "pending" : value.run.status === "answered" ? "answered" : "cancelled";
  return value.outcome;
}

export function TargetedPractice({
  client, sessionId, courseId, currentUnitId, stateScope, session, paused, focusOnMount = false, onFocusHandled, onSessionChanged, onOutcomeChange,
}: {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  currentUnitId: string;
  stateScope: string;
  session: AutonomousStudySession;
  paused: boolean;
  focusOnMount?: boolean;
  onFocusHandled?: () => void;
  onSessionChanged: () => void;
  onOutcomeChange: (scope: string, outcome: "not_started" | "pending" | "answered" | "cancelled" | null) => void;
}) {
  const [practice, setPractice] = useState<PracticeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [response, setResponse] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [retry, setRetry] = useState<Intent | null>(null);
  const mounted = useRef(true);
  const scope = `${sessionId}:${courseId}:${currentUnitId}`;
  const scopeRef = useRef(scope);
  const writeController = useRef<AbortController | null>(null);
  const restoreController = useRef<AbortController | null>(null);
  const operationRef = useRef<Operation | null>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const responseRef = useRef<HTMLInputElement | null>(null);

  useLayoutEffect(() => { scopeRef.current = scope; }, [scope]);
  useEffect(() => () => { mounted.current = false; writeController.current?.abort(); restoreController.current?.abort(); }, []);
  const current = (expected: string) => mounted.current && scopeRef.current === expected;
  const restore = useCallback(async (expected: string): Promise<TargetedPracticeReadResponse | null> => {
    const controller = new AbortController();
    restoreController.current?.abort();
    restoreController.current = controller;
    try {
      const result = await client.getStudySessionPractice(sessionId, courseId, { signal: controller.signal });
      if (!current(expected)) return null;
      setPractice(result); setLoading(false);
      return result;
    } catch (error) {
      if (!current(expected) || restoreController.current !== controller) return null;
      setLoading(false);
      setNotice(isAbort(error)
        ? { tone: "cancelled", text: "Practice restore was cancelled. No new write was sent." }
        : error instanceof LearningCoreResponseError && error.status === 404
          ? { tone: "error", text: "This practice step is unavailable for the current local course." }
          : { tone: "error", text: "Keen could not restore this local practice step. Retry after the learning core recovers." });
      return null;
    } finally { if (restoreController.current === controller) restoreController.current = null; }
  }, [client, courseId, sessionId]);
  useEffect(() => { mounted.current = true; const timer = window.setTimeout(() => { void restore(scope); }, 0); return () => window.clearTimeout(timer); }, [restore, scope]);

  const reconcile = async (expected: string) => {
    const restored = await restore(expected);
    if (restored) onSessionChanged();
    return restored;
  };
  const applied = (kind: Operation, value: TargetedPracticeReadResponse | null) => kind === "begin"
    ? value?.outcome === "pending" || value?.outcome === "answered" || value?.outcome === "cancelled"
    : value?.outcome === "answered" || value?.outcome === "cancelled";
  const run = async (kind: Operation) => {
    if (operationRef.current || paused || !current(scope)) return;
    const expected = scope;
    const outcome = practiceOutcome(practice);
    if (kind === "answer" && (outcome !== "pending" || !practice?.run || (!response.trim() && retry?.kind !== "answer"))) {
      setNotice({ tone: "error", text: "Write a response before submitting practice." }); return;
    }
    const intent = retry?.kind === kind ? retry : kind === "begin"
      ? { kind, key: idempotencyKey(), revision: practice?.session.revision ?? session.revision }
      : { kind, key: idempotencyKey(), revision: practice!.session.revision, runId: practice!.run!.id, response: response.trim() };
    const controller = new AbortController();
    writeController.current = controller; operationRef.current = kind; setOperation(kind); setNotice(null);
    try {
      const result = kind === "begin"
        ? await client.beginStudySessionPractice(sessionId, { course_id: courseId, expected_revision: intent.revision, idempotency_key: intent.key }, { signal: controller.signal })
        : await client.answerStudySessionPractice(sessionId, intent.runId!, { course_id: courseId, expected_revision: intent.revision, idempotency_key: intent.key, response: intent.response! }, { signal: controller.signal });
      if (!current(expected)) return;
      setPractice(result); setRetry(null); if (kind === "answer") setResponse("");
      if (kind !== "answer" || result.session.status !== "studying") onSessionChanged();
    } catch (error) {
      if (!current(expected)) return;
      const restored = await reconcile(expected);
      if (error instanceof LearningCoreResponseError && error.status === 409) {
        setRetry(null); if (!restored) setPractice(null);
        setNotice(restored ? { tone: "error", text: "This session changed before the action completed. Keen restored the latest local practice step." } : { tone: "error", text: "This session changed, but Keen could not restore the latest local practice step. No write was retried." });
      } else if (error instanceof LearningCoreResponseError && error.status >= 400 && error.status < 500) {
        setRetry(null); if (!restored) setPractice(null);
        setNotice(error.status === 404 ? { tone: "error", text: "This practice step is unavailable for the current local course. No write was retried." } : { tone: "error", text: "The local practice action was rejected. No write was retried; refresh the restored state before trying again." });
      } else if (applied(kind, restored)) {
        setRetry(null);
      } else {
        setRetry(intent);
        setNotice({ tone: "unknown", text: "Keen could not safely determine whether this local action was saved. Retry the same request; editing is locked until it is resolved." });
      }
    } finally {
      if (current(expected)) { writeController.current = null; operationRef.current = null; setOperation(null); }
    }
  };
  const outcome = practiceOutcome(practice);
  useLayoutEffect(() => { onOutcomeChange(stateScope, outcome); }, [onOutcomeChange, outcome, stateScope]);
  useLayoutEffect(() => {
    if (!loading && focusOnMount) {
      if (outcome === "pending" && !paused) responseRef.current?.focus({ preventScroll: true });
      else headingRef.current?.focus({ preventScroll: true });
      onFocusHandled?.();
    }
  }, [focusOnMount, loading, onFocusHandled, outcome, paused]);
  if (loading) return <LearningStepRestore label="Restoring targeted practice…" />;
  if (notice && !practice) return <Card className="checkpoint" role="alert"><strong>Practice unavailable</strong><p>{notice.text}</p><Button onClick={() => { setLoading(true); setNotice(null); void restore(scope); }}>Retry practice restore</Button></Card>;
  if (paused) return <Card className="checkpoint"><Badge tone="warning">Session paused</Badge><h2 id="targeted-practice-title" ref={headingRef} tabIndex={-1}>{practice?.run ? "Practice restored" : "Practice has not started"}</h2><p>{practice?.run ? "No practice action was sent while this session is paused. Resume this local session before continuing." : "This session paused before practice began. Resume the local session before starting practice."}</p></Card>;
  if (outcome === "answered" && practice?.grade) {
    const unitAdvanced = practice.session.status === "studying";
    return <Card className="checkpoint learning-outcome practice-result" aria-labelledby="targeted-practice-title">
      <Badge tone={practice.grade.correct ? "success" : "warning"}>Practice recorded</Badge>
      <h2 id="targeted-practice-title" ref={headingRef} tabIndex={-1}>{unitAdvanced ? "Unit complete" : practice.grade.correct ? "Practice complete" : "Review needed"}</h2>
      <p className="learning-outcome-copy">{unitAdvanced
        ? "This practice check is saved. Your next source-grounded unit is ready."
        : "This practice check is saved. Finish the session to add the next review to your queue."}</p>
      <dl className="learning-outcome-metrics">
        <div><dt>Score</dt><dd>{practice.grade.score} / {practice.grade.max_score}</dd></div>
        <div><dt>Next</dt><dd>{unitAdvanced ? "Continue learning" : "Finish session"}</dd></div>
      </dl>
      {unitAdvanced ? <div className="checkpoint-actions"><Button className="primary" onClick={onSessionChanged}>Continue to next unit</Button></div> : null}
    </Card>;
  }
  if (outcome === "cancelled") return <Card className="checkpoint" role="status"><Badge tone="warning">{practice?.run ? "Practice cancelled" : "Session ended before practice"}</Badge><p>{practice?.run ? "This practice run ended with the local session. No answer or mastery update was recorded." : "The local session ended before a practice run was created. No answer or mastery update was recorded."}</p></Card>;
  if (outcome === "pending" && practice?.checkpoint) {
    const prompt = readableClozePrompt(practice.checkpoint.prompt);
    return <Card className="checkpoint practice-checkpoint" aria-labelledby="targeted-practice-title"><h2 id="targeted-practice-title" ref={headingRef} tabIndex={-1}>Complete the missing term</h2><p className="practice-instruction">Type only the missing word or short phrase. You do not need to enter the formula.</p><div className="practice-question"><p><BlankStatement>{prompt.question}</BlankStatement></p>{prompt.equation ? <div className="practice-equation">{prompt.equation}</div> : null}</div><label className="diagnostic-response-label" htmlFor="targeted-practice-response">Missing term</label><input ref={responseRef} id="targeted-practice-response" type="text" maxLength={200} value={retry?.kind === "answer" ? retry.response : response} disabled={operation !== null || retry?.kind === "answer"} onChange={(event) => setResponse(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); void run("answer"); } }} placeholder="Type a word or short phrase" />{notice && <p className={`diagnostic-notice ${notice.tone}`} role="alert">{notice.text}</p>}<div className="checkpoint-actions"><Button className="primary" disabled={operation !== null || (!response.trim() && retry?.kind !== "answer")} onClick={() => { void run("answer"); }}>{operation === "answer" ? <LoaderCircle className="spin" size={14} /> : null}{operation === "answer" ? "Checking answer…" : retry?.kind === "answer" ? "Retry same answer" : "Check answer"}</Button>{operation && <Button onClick={() => writeController.current?.abort()}><Square size={14} />Cancel</Button>}</div></Card>;
  }
  return <Card className="checkpoint" aria-labelledby="targeted-practice-title"><h2 id="targeted-practice-title" ref={headingRef} tabIndex={-1}>Targeted practice</h2><p>Start one deterministic local practice prompt after active recall is complete.</p>{notice && <p className={`diagnostic-notice ${notice.tone}`} role="alert">{notice.text}</p>}<div className="checkpoint-actions"><Button className="primary" disabled={operation !== null} onClick={() => { void run("begin"); }}>{operation === "begin" ? <LoaderCircle className="spin" size={14} /> : null}{operation === "begin" ? "Preparing practice…" : retry?.kind === "begin" ? "Retry same practice" : "Begin practice"}</Button>{operation && <Button onClick={() => writeController.current?.abort()}><Square size={14} />Cancel</Button>}</div></Card>;
}
