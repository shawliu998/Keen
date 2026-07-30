import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { LoaderCircle, Square } from "lucide-react";
import { Badge, Button, Card } from "@keen/ui";
import {
  LearningCoreResponseError,
  type AutonomousStudySession,
  type DiagnosticProgressionResponse,
  type DiagnosticReadResponse,
  type LearningCoreClient,
} from "@keen/api-client";
import { LearningStepRestore } from "./LearningStepRestore";

type SelfAssessment = "not_yet" | "partial" | "confident";

type Notice = { tone: "error" | "unknown" | "cancelled"; text: string } | null;
type Operation = "begin" | "answer";
type WriteIntent = {
  kind: Operation;
  key: string;
  expectedRevision: number;
  checkpointId?: string;
  response?: string;
  assessment?: SelfAssessment;
};

function newIdempotencyKey(): string {
  const random = globalThis.crypto?.randomUUID?.();
  return random ? `diagnostic-${random}` : `diagnostic-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function abortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function isScopeCurrent(current: string, expected: string, mounted: boolean): boolean {
  return mounted && current === expected;
}

export function OpeningDiagnostic({
  client,
  sessionId,
  courseId,
  session,
  onSessionChanged,
  children,
  paused,
}: {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  session: AutonomousStudySession;
  onSessionChanged: () => void;
  children: ReactNode;
  paused: boolean;
}) {
  const [diagnostic, setDiagnostic] = useState<DiagnosticReadResponse | DiagnosticProgressionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [response, setResponse] = useState("");
  const [assessment, setAssessment] = useState<SelfAssessment>("partial");
  const [notice, setNotice] = useState<Notice>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const restoreControllerRef = useRef<AbortController | null>(null);
  const operationRef = useRef<Operation | null>(null);
  const [retryIntent, setRetryIntent] = useState<WriteIntent | null>(null);
  const mountedRef = useRef(true);
  const scope = `${sessionId}:${courseId}`;
  const scopeRef = useRef(scope);

  useLayoutEffect(() => { scopeRef.current = scope; }, [scope]);
  useEffect(() => () => {
    mountedRef.current = false;
    controllerRef.current?.abort();
    restoreControllerRef.current?.abort();
  }, []);

  const restore = useCallback(async (expectedScope: string): Promise<DiagnosticReadResponse | null> => {
    const controller = new AbortController();
    restoreControllerRef.current?.abort();
    restoreControllerRef.current = controller;
    try {
      const restored = await client.getStudySessionDiagnostic(sessionId, courseId, { signal: controller.signal });
      if (!isScopeCurrent(scopeRef.current, expectedScope, mountedRef.current)) return null;
      setDiagnostic(restored);
      setLoading(false);
      return restored;
    } catch (error) {
      if (restoreControllerRef.current !== controller) return null;
      if (!isScopeCurrent(scopeRef.current, expectedScope, mountedRef.current)) return null;
      setLoading(false);
      if (abortError(error)) setNotice({ tone: "cancelled", text: "Opening reflection restore was cancelled. No new write was sent." });
      else setNotice({ tone: "error", text: "Keen could not restore this local opening reflection. Retry after the learning core recovers." });
      return null;
    } finally {
      if (restoreControllerRef.current === controller) restoreControllerRef.current = null;
    }
  }, [client, courseId, sessionId]);

  useEffect(() => {
    mountedRef.current = true;
    const timer = window.setTimeout(() => { void restore(scope); }, 0);
    return () => window.clearTimeout(timer);
  }, [restore, scope]);

  const reconcile = async (expectedScope: string): Promise<DiagnosticReadResponse | null> => {
    const restored = await restore(expectedScope);
    if (!restored) return null;
    onSessionChanged();
    return restored;
  };

  const wasApplied = (action: Operation, restored: DiagnosticReadResponse | null): boolean => action === "begin"
    ? restored?.outcome === "pending" || restored?.outcome === "answered"
    : restored?.outcome === "answered";

  const run = async (kind: Operation) => {
    if (operationRef.current || !isScopeCurrent(scopeRef.current, scope, mountedRef.current)) return;
    const expectedScope = scope;
    if (paused) return;
    const checkpoint = diagnostic?.checkpoint;
    if (kind === "answer" && (!checkpoint || checkpoint.status !== "pending" || !response.trim()) && retryIntent?.kind !== "answer") {
      setNotice({ tone: "error", text: "Write a short response before recording your self-assessment." });
      return;
    }
    const intent = retryIntent?.kind === kind
      ? retryIntent
      : kind === "begin"
        ? { kind, key: newIdempotencyKey(), expectedRevision: diagnostic?.session.revision ?? session.revision }
        : { kind, key: newIdempotencyKey(), expectedRevision: diagnostic!.session.revision, checkpointId: checkpoint!.id, response: response.trim(), assessment };
    const controller = new AbortController();
    controllerRef.current = controller;
    operationRef.current = kind;
    setOperation(kind);
    setNotice(null);
    try {
      const result = kind === "begin"
        ? await client.beginStudySessionDiagnostic(sessionId, { course_id: courseId, expected_revision: intent.expectedRevision, idempotency_key: intent.key }, { signal: controller.signal })
        : await client.answerStudySessionDiagnostic(sessionId, intent.checkpointId!, { course_id: courseId, expected_revision: intent.expectedRevision, idempotency_key: intent.key, response: intent.response!, self_assessment: intent.assessment! }, { signal: controller.signal });
      if (!isScopeCurrent(scopeRef.current, expectedScope, mountedRef.current)) return;
      setDiagnostic(result);
      setRetryIntent(null);
      if (kind === "answer") setResponse("");
      onSessionChanged();
    } catch (error) {
      if (!isScopeCurrent(scopeRef.current, expectedScope, mountedRef.current)) return;
      if (abortError(error)) {
        setNotice({ tone: "cancelled", text: "Request cancelled. Keen will restore the local opening reflection before another write." });
        const restored = await reconcile(expectedScope);
        if (wasApplied(kind, restored)) setRetryIntent(null);
        else {
          setRetryIntent(intent);
          setNotice({ tone: "unknown", text: "Keen could not safely determine whether this local action was saved. Retry the same request; editing is locked until it is resolved." });
        }
      } else if (error instanceof LearningCoreResponseError && error.status === 409) {
        const restored = await reconcile(expectedScope);
        setRetryIntent(null);
        if (restored) {
          setNotice({ tone: "error", text: "This session changed before the action completed. Keen restored the latest local opening reflection." });
        } else {
          setDiagnostic(null);
          setNotice({ tone: "error", text: "This session changed before the action completed, but Keen could not restore the latest local opening reflection. Retry after the learning core recovers; no write was retried." });
        }
      } else {
        const restored = await reconcile(expectedScope);
        if (wasApplied(kind, restored)) setRetryIntent(null);
        else {
          setRetryIntent(intent);
          setNotice({ tone: "unknown", text: "Keen could not safely determine whether this local action was saved. Retry the same request; editing is locked until it is resolved." });
        }
      }
    } finally {
      if (isScopeCurrent(scopeRef.current, expectedScope, mountedRef.current)) {
        controllerRef.current = null;
        operationRef.current = null;
        setOperation(null);
      }
    }
  };

  const cancel = () => controllerRef.current?.abort();
  const outcome = diagnostic?.outcome;
  const pending = outcome === "pending" || diagnostic !== null && (outcome === "applied" || outcome === "replayed") && diagnostic.checkpoint.status === "pending";
  const answered = outcome === "answered" || diagnostic !== null && (outcome === "applied" || outcome === "replayed") && diagnostic.checkpoint.status === "answered";
  const retryingAnswer = retryIntent?.kind === "answer";
  const retryingBegin = retryIntent?.kind === "begin";

  if (loading) return <LearningStepRestore label="Restoring your local opening reflection…" />;
  if (notice && !diagnostic) return <Card className="checkpoint" role="alert"><strong>Opening reflection unavailable</strong><p>{notice.text}</p><Button onClick={() => { setLoading(true); setNotice(null); void restore(scope); }}>Retry reflection restore</Button></Card>;
  // A completed diagnostic must not block restoration of a later, paused learning state.
  if (paused && answered) return <>{children}</>;
  if (paused) return <Card className="checkpoint" role="status"><Badge tone="warning">Session paused</Badge><h3>Opening reflection restored</h3><p>No reflection action was sent while this session is paused. Resume this local session before starting or answering the opening reflection.</p></Card>;
  if (answered) return <>{children}</>;
  if (pending && diagnostic?.checkpoint) return <Card className="checkpoint" aria-labelledby="opening-diagnostic-title">
    <h3 id="opening-diagnostic-title">{diagnostic.checkpoint.prompt}</h3>
    <p className="diagnostic-disclosure">This is your self-report, not a scored assessment. It does not change mastery or schedule review.</p>
    <label className="diagnostic-response-label" htmlFor="diagnostic-response">Your response</label>
    <textarea id="diagnostic-response" maxLength={8000} value={retryingAnswer ? retryIntent.response : response} disabled={operation !== null || retryingAnswer} onChange={(event) => setResponse(event.target.value)} placeholder="Explain what you already know in your own words." />
    <fieldset className="diagnostic-assessment" disabled={operation !== null || retryingAnswer}>
      <legend>How confident do you feel?</legend>
      <label><input type="radio" name="self-assessment" checked={(retryingAnswer ? retryIntent.assessment : assessment) === "not_yet"} onChange={() => setAssessment("not_yet")} /> Not yet</label>
      <label><input type="radio" name="self-assessment" checked={(retryingAnswer ? retryIntent.assessment : assessment) === "partial"} onChange={() => setAssessment("partial")} /> Partly</label>
      <label><input type="radio" name="self-assessment" checked={(retryingAnswer ? retryIntent.assessment : assessment) === "confident"} onChange={() => setAssessment("confident")} /> Confident</label>
    </fieldset>
    {notice && <p className={`diagnostic-notice ${notice.tone}`} role={notice.tone === "cancelled" ? "status" : "alert"}>{notice.text}</p>}
    <div className="checkpoint-actions"><Button className="primary" disabled={operation !== null || !response.trim() && !retryingAnswer} onClick={() => { void run("answer"); }}>{operation === "answer" ? <LoaderCircle className="spin" size={14} /> : null}{operation === "answer" ? "Saving local response…" : retryingAnswer ? "Retry same response" : "Continue to first unit"}</Button>{operation && <Button onClick={cancel}><Square size={14} />Cancel</Button>}</div>
  </Card>;
  return <Card className="checkpoint" aria-labelledby="opening-diagnostic-title">
    <h3 id="opening-diagnostic-title">Start with a brief self-reflection</h3>
    <p>Before the first source-grounded unit, Keen can record what you say you already know. This is not scored and does not change mastery.</p>
    {notice && <p className={`diagnostic-notice ${notice.tone}`} role={notice.tone === "cancelled" ? "status" : "alert"}>{notice.text}</p>}
    <div className="checkpoint-actions"><Button className="primary" disabled={operation !== null} onClick={() => { void run("begin"); }}>{operation === "begin" ? <LoaderCircle className="spin" size={14} /> : null}{operation === "begin" ? "Preparing reflection…" : retryingBegin ? "Retry same reflection" : "Start opening reflection"}</Button>{operation && <Button onClick={cancel}><Square size={14} />Cancel</Button>}</div>
  </Card>;
}
