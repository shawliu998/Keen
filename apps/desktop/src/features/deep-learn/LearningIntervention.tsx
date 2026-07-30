import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { BookOpenText, LoaderCircle, RefreshCw, Square, WandSparkles } from "lucide-react";
import { Badge, Button } from "@keen/ui";
import {
  LearningCoreResponseError,
  LearningCoreSchemaError,
  type LearningCoreClient,
  type LearningInterventionIntent,
  type LearningInterventionResponse,
} from "@keen/api-client";
import { LearningStepRestore } from "./LearningStepRestore";
import { LearningMarkdown } from "./LearningMarkdown";

export type LearningInterventionGate = "checking" | "ineligible" | "blocked" | "ready" | "fallback";

type Operation = LearningInterventionIntent | "cancel" | null;
type FrozenIntent = {
  intent: LearningInterventionIntent;
  idempotencyKey: string;
  sessionRevision: number;
  predecessorRunId?: string;
  predecessorArtifactId?: string;
};
type Notice = { tone: "error" | "warning"; text: string } | null;

const actions: Array<{
  label: LearningInterventionResponse["actions"][number];
  intent: LearningInterventionIntent;
}> = [
  { label: "Explain differently", intent: "explain_differently" },
  { label: "Show a source example", intent: "show_source_example" },
  { label: "Test me instead", intent: "test_me_instead" },
];

function usesConfiguredProvider(intent: LearningInterventionIntent): boolean {
  return intent === "explain_differently" || intent === "show_source_example";
}

function ProviderActionDisclosure() {
  return (
    <p className="intervention-provider-disclosure">
      Explain differently and Show a source example send your current answer and relevant cited excerpts to the configured model provider.
    </p>
  );
}

function interventionKey(): string {
  const id = globalThis.crypto?.randomUUID?.();
  return `learning-intervention-${id ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function gateFor(
  loading: boolean,
  error: unknown,
  response: LearningInterventionResponse | null,
): LearningInterventionGate {
  if (loading) return "checking";
  if (error || !response) return "fallback";
  if (response.status === "ineligible") return "ineligible";
  if (response.status === "ready" || response.status === "practice_ready") return "ready";
  if (response.status === "source_review" || response.status === "cancelled") return "fallback";
  return "blocked";
}

function restoreErrorMessage(error: unknown): string {
  if (error instanceof LearningCoreResponseError && error.status === 503) {
    return "The local learning service could not restore Agent status. No practice was started. Continue with the saved source review below, or retry after the service recovers.";
  }
  if (error instanceof LearningCoreSchemaError) {
    return "The local learning service returned Agent state Keen could not verify. No practice was started. Continue with the saved source review below, or retry the status check.";
  }
  return "Keen could not confirm the current Agent state. No practice was started. The saved source review remains available below.";
}

function fallbackMessage(response: LearningInterventionResponse): string {
  if (response.status === "cancelled") {
    return "The Agent run was cancelled. No intervention artifact was accepted and practice remains locked. Continue with the saved source review below, or choose another action.";
  }
  switch (response.reason) {
    case "provider_missing":
      return "No learning provider is configured, so the Agent could not create a verified explanation. No practice was started; the saved source review remains available below.";
    case "provider_unavailable":
    case "provider_failed":
      return "The learning provider could not complete this intervention. No practice was started; continue with the saved source review below or retry.";
    case "invalid_output":
      return "The Agent response did not satisfy Keen’s verified learning-artifact contract. It was not shown, and no practice was started.";
    case "source_unavailable":
      return "The current source evidence is unavailable, so Keen did not ask the Agent to invent an explanation. Continue with the saved source review below.";
    default:
      return "The Agent could not produce a verified intervention. No practice was started; continue with the saved source review below or retry.";
  }
}

export function LearningIntervention({
  client,
  sessionId,
  courseId,
  currentUnitId,
  sessionRevision,
  stateScope,
  paused,
  onGateChange,
  onConfigureProvider,
  onReturnToSource,
  onStateChanged,
  onAgentRunChanged,
}: {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  currentUnitId: string;
  sessionRevision: number;
  stateScope: string;
  paused: boolean;
  onGateChange: (scope: string, gate: LearningInterventionGate) => void;
  onConfigureProvider: () => void;
  onReturnToSource: (scope: string) => void;
  onStateChanged: () => void;
  onAgentRunChanged?: (runId: string) => void;
}) {
  const scope = `${stateScope}:${sessionId}:${courseId}:${currentUnitId}`;
  const [storedResponse, setResponse] = useState<LearningInterventionResponse | null>(null);
  const [storedLoading, setLoading] = useState(true);
  const [storedRestoreError, setRestoreError] = useState<unknown>(null);
  const [loadedScope, setLoadedScope] = useState(scope);
  const [notice, setNotice] = useState<Notice>(null);
  const [operation, setOperation] = useState<Operation>(null);
  const [retryIntent, setRetryIntent] = useState<FrozenIntent | null>(null);
  const [stage, setStage] = useState("Preparing a source-grounded intervention…");
  const scopeRef = useRef(scope);
  const mountedRef = useRef(true);
  const restoreControllerRef = useRef<AbortController | null>(null);
  const writeControllerRef = useRef<AbortController | null>(null);
  const streamControllerRef = useRef<AbortController | null>(null);
  const operationRef = useRef<Operation>(null);
  const practiceReadyHandoffScopeRef = useRef<string | null>(null);
  const stateMatchesScope = loadedScope === scope;
  const response = stateMatchesScope ? storedResponse : null;
  const loading = stateMatchesScope ? storedLoading : true;
  const restoreError = stateMatchesScope ? storedRestoreError : null;

  useLayoutEffect(() => {
    scopeRef.current = scope;
  }, [scope]);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      restoreControllerRef.current?.abort();
      writeControllerRef.current?.abort();
      streamControllerRef.current?.abort();
    };
  }, []);
  const isCurrent = useCallback(
    (expected: string) => mountedRef.current && scopeRef.current === expected,
    [],
  );
  const restore = useCallback(async (expected: string): Promise<LearningInterventionResponse | null> => {
    const controller = new AbortController();
    restoreControllerRef.current?.abort();
    restoreControllerRef.current = controller;
    try {
      const value = await client.getCurrentLearningIntervention(sessionId, courseId, {
        signal: controller.signal,
      });
      if (!isCurrent(expected) || restoreControllerRef.current !== controller) return null;
      setResponse(value);
      setRestoreError(null);
      setLoading(false);
      return value;
    } catch (error) {
      if (
        !isCurrent(expected)
        || restoreControllerRef.current !== controller
        || isAbort(error)
      ) return null;
      setRestoreError(error);
      setLoading(false);
      return null;
    } finally {
      if (restoreControllerRef.current === controller) restoreControllerRef.current = null;
    }
  }, [client, courseId, isCurrent, sessionId]);

  useEffect(() => {
    restoreControllerRef.current?.abort();
    writeControllerRef.current?.abort();
    streamControllerRef.current?.abort();
    operationRef.current = null;
    const timer = window.setTimeout(() => {
      setLoadedScope(scope);
      setResponse(null);
      setRestoreError(null);
      setNotice(null);
      setOperation(null);
      setRetryIntent(null);
      setStage("Preparing a source-grounded intervention…");
      setLoading(true);
      void restore(scope);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [restore, scope]);

  const runId = response?.status === "queued" || response?.status === "running"
    ? response.run?.id ?? null
    : null;
  useEffect(() => {
    if (!runId) return;
    const expected = scope;
    const controller = new AbortController();
    streamControllerRef.current?.abort();
    streamControllerRef.current = controller;
    void (async () => {
      try {
        for await (const event of client.learningInterventionEvents(
          sessionId,
          runId,
          courseId,
          { signal: controller.signal },
        )) {
          if (!isCurrent(expected)) return;
          if (event.event === "searching_sources") setStage("Checking the frozen source evidence…");
          if (event.event === "source_context_ready") setStage("Writing a bounded explanation from those sources…");
          if (event.event === "artifact_ready") setStage("Validating the learning artifact and practice handoff…");
          if (event.event === "cancelled" || event.event === "source_review" || event.event === "done") break;
        }
        if (controller.signal.aborted) return;
        const restored = await restore(expected);
        if (!isCurrent(expected)) return;
        if (restored) {
          setNotice(null);
          if (restored.run) onAgentRunChanged?.(restored.run.id);
          if (restored.status === "ready" || restored.status === "source_review" || restored.status === "cancelled") {
            onStateChanged();
          }
        }
      } catch (error) {
        if (!isCurrent(expected) || isAbort(error)) return;
        const restored = await restore(expected);
        if (!isCurrent(expected)) return;
        if (restored?.run) onAgentRunChanged?.(restored.run.id);
        if (
          restored?.status === "ready"
          || restored?.status === "source_review"
          || restored?.status === "cancelled"
        ) {
          setNotice(null);
          onStateChanged();
          return;
        }
        if (restored?.status === "practice_ready") {
          setNotice(null);
          return;
        }
        if (restored?.status === "queued" || restored?.status === "running") {
          setNotice({
            tone: "warning",
            text: "Live Agent updates disconnected, but the durable run is still active. Practice remains locked; refresh status or cancel the run.",
          });
        }
      }
    })();
    return () => {
      controller.abort();
      if (streamControllerRef.current === controller) streamControllerRef.current = null;
    };
  }, [client, courseId, isCurrent, onAgentRunChanged, onStateChanged, restore, runId, scope, sessionId]);

  const runAction = async (intent: LearningInterventionIntent) => {
    if (operationRef.current || paused || !isCurrent(scope)) return;
    const expected = scope;
    const readyArtifact = response?.status === "ready"
      && response.run
      && response.artifact
      && "kind" in response.artifact
      ? { runId: response.run.id, artifactId: response.artifact.artifactId }
      : null;
    const frozen = retryIntent?.intent === intent
      ? retryIntent
      : {
          intent,
          idempotencyKey: interventionKey(),
          sessionRevision,
          ...(readyArtifact
            ? {
                predecessorRunId: readyArtifact.runId,
                predecessorArtifactId: readyArtifact.artifactId,
              }
            : {}),
        };
    const controller = new AbortController();
    writeControllerRef.current = controller;
    operationRef.current = intent;
    setOperation(intent);
    setNotice(null);
    try {
      const value = await client.startLearningIntervention(sessionId, {
        courseId,
        unitId: currentUnitId,
        expectedSessionRevision: frozen.sessionRevision,
        intent,
        idempotencyKey: frozen.idempotencyKey,
        ...(frozen.predecessorRunId && frozen.predecessorArtifactId
          ? {
              predecessorRunId: frozen.predecessorRunId,
              predecessorArtifactId: frozen.predecessorArtifactId,
            }
          : {}),
      }, { signal: controller.signal });
      if (!isCurrent(expected)) return;
      setResponse(value);
      setRestoreError(null);
      setRetryIntent(null);
      if (value.run) onAgentRunChanged?.(value.run.id);
      setStage(value.status === "queued" ? "The intervention is queued…" : "Preparing a source-grounded intervention…");
      if (value.status === "ready" || value.status === "source_review") {
        onStateChanged();
      }
    } catch (error) {
      if (!isCurrent(expected)) return;
      const restored = await restore(expected);
      if (!isCurrent(expected)) return;
      const rejected = error instanceof LearningCoreResponseError && error.status >= 400 && error.status < 500;
      const restoredAtFrozenHead = restored?.status === "ready"
        && frozen.predecessorRunId === restored.run?.id
        && restored.artifact !== null
        && "kind" in restored.artifact
        && frozen.predecessorArtifactId === restored.artifact.artifactId;
      if (rejected || (restored && restored.status !== "eligible" && !restoredAtFrozenHead)) {
        setRetryIntent(null);
      }
      else setRetryIntent(frozen);
      if (error instanceof LearningCoreResponseError && error.status === 409) {
        setNotice({
          tone: "error",
          text: restored
            ? "This learning step changed before the Agent action started. Keen restored the current state; retry after the session refreshes."
            : "This learning step changed, but Keen could not restore the current Agent state. No write was retried.",
        });
        onStateChanged();
      } else if (rejected) {
        setNotice({
          tone: "error",
          text: "The Agent action was rejected. Keen restored the current state and did not retry the write.",
        });
      } else if (!restored || restored.status === "eligible" || restoredAtFrozenHead) {
        setNotice({
          tone: "warning",
          text: "Keen could not confirm whether the Agent action started. Retry sends the same saved request; practice remains locked.",
        });
      }
    } finally {
      if (isCurrent(expected)) {
        writeControllerRef.current = null;
        operationRef.current = null;
        setOperation(null);
      }
    }
  };

  const cancel = async () => {
    // Pausing study prevents new intervention writes, but must not trap an active provider run.
    if (operationRef.current || !response?.run || !isCurrent(scope)) return;
    const expected = scope;
    const runToCancel = response.run.id;
    const controller = new AbortController();
    writeControllerRef.current = controller;
    operationRef.current = "cancel";
    setOperation("cancel");
    setNotice(null);
    try {
      const value = await client.cancelLearningIntervention(
        sessionId,
        runToCancel,
        courseId,
        { signal: controller.signal },
      );
      if (!isCurrent(expected)) return;
      setResponse(value);
      setRestoreError(null);
      onStateChanged();
    } catch {
      if (!isCurrent(expected)) return;
      const restored = await restore(expected);
      if (!isCurrent(expected)) return;
      setNotice({
        tone: "warning",
        text: restored?.status === "cancelled"
          ? "The Agent run was cancelled and the durable state was restored."
          : "Keen could not confirm cancellation. The run may still be active; practice remains locked until its state is restored.",
      });
    } finally {
      if (isCurrent(expected)) {
        writeControllerRef.current = null;
        operationRef.current = null;
        setOperation(null);
      }
    }
  };

  const gate = gateFor(loading, restoreError, response);
  useLayoutEffect(() => {
    onGateChange(stateScope, gate);
  }, [gate, onGateChange, stateScope]);
  useEffect(() => {
    if (response?.status !== "practice_ready" || practiceReadyHandoffScopeRef.current === scope) return;
    practiceReadyHandoffScopeRef.current = scope;
    onStateChanged();
  }, [onStateChanged, response?.status, scope]);

  if (loading) return <LearningStepRestore label="Checking the current learning intervention…" />;
  if (
    restoreError instanceof LearningCoreResponseError
    && restoreError.detail?.code === "provider_missing"
  ) {
    return <ProviderRecovery
      onConfigure={onConfigureProvider}
      onReviewSource={() => onReturnToSource(stateScope)}
    />;
  }
  if (restoreError || !response) {
    return <section className="checkpoint learning-intervention" role="alert" aria-labelledby="learning-intervention-error-title">
      <Badge tone="warning">Learning Agent unavailable</Badge>
      <h2 id="learning-intervention-error-title">Agent status could not be restored</h2>
      <p>{restoreErrorMessage(restoreError)}</p>
      <div className="checkpoint-actions">
        <Button onClick={() => {
          setLoading(true);
          setRestoreError(null);
          void restore(scope);
        }}><RefreshCw size={14} />Retry Agent status</Button>
      </div>
    </section>;
  }
  if (response.status === "ineligible") return null;
  if (response.status === "queued" || response.status === "running") {
    return <section className="checkpoint learning-intervention" aria-labelledby="learning-intervention-running-title">
      <Badge tone="accent"><WandSparkles size={12} />Learning Agent</Badge>
      <div className="intervention-running-line">
        <LoaderCircle className="spin" size={17} aria-hidden="true" />
        <div><h2 id="learning-intervention-running-title">Repairing this misconception</h2><p role="status">{stage}</p></div>
      </div>
      <p className="intervention-run-meta">{response.run?.provider} · {response.run?.model}</p>
      {notice ? <p className={`diagnostic-notice ${notice.tone}`} role="alert">{notice.text}</p> : null}
      <div className="checkpoint-actions">
        {notice ? <Button onClick={() => { setNotice(null); void restore(scope); }}><RefreshCw size={14} />Refresh Agent status</Button> : null}
        <Button disabled={operation === "cancel"} onClick={() => { void cancel(); }}>
          {operation === "cancel" ? <LoaderCircle className="spin" size={14} /> : <Square size={13} />}
          {operation === "cancel" ? "Cancelling…" : "Cancel Agent run"}
        </Button>
      </div>
    </section>;
  }
  if (response.status === "source_review" || response.status === "cancelled") {
    if (response.status === "source_review" && response.reason === "provider_missing") {
      return <ProviderRecovery
        onConfigure={onConfigureProvider}
        onReviewSource={() => onReturnToSource(stateScope)}
      />;
    }
    const canRetry = response.status === "cancelled" || response.fallback?.retryable !== false;
    return <section className="checkpoint learning-intervention" role="status" aria-labelledby="learning-intervention-fallback-title">
      <Badge tone="warning">Source review fallback</Badge>
      <h2 id="learning-intervention-fallback-title">{response.status === "cancelled" ? "Agent run cancelled" : "Verified intervention unavailable"}</h2>
      <p>{fallbackMessage(response)}</p>
      {notice ? <p className={`diagnostic-notice ${notice.tone}`} role="alert">{notice.text}</p> : null}
      {canRetry ? <InterventionActions response={response} operation={operation} paused={paused} retryIntent={retryIntent} onAction={runAction} /> : null}
    </section>;
  }
  if (response.status === "practice_ready") {
    return <section className="checkpoint learning-intervention" aria-labelledby="learning-intervention-practice-title">
      <Badge tone="success">Practice ready</Badge>
      <h2 id="learning-intervention-practice-title">Continue with a targeted check</h2>
      <section className="intervention-fact">
        <h3>What next</h3>
        <p>{response.practice?.label}</p>
      </section>
    </section>;
  }

  const artifact = response.artifact;
  const readyArtifact = artifact && "kind" in artifact ? artifact : null;
  if (!artifact) return null;
  return <section className="checkpoint learning-intervention" aria-labelledby="learning-intervention-title">
    <Badge tone={readyArtifact ? "success" : "accent"}><WandSparkles size={12} />{readyArtifact ? "Agent explanation ready" : "Learning Agent"}</Badge>
    <h2 id="learning-intervention-title">{readyArtifact?.summary ?? "Choose how Keen should repair this gap"}</h2>
    {readyArtifact ? <LearningMarkdown>{readyArtifact.explanationMarkdown}</LearningMarkdown> : null}
    <div className="intervention-facts">
      <section className="intervention-fact">
        <h3>Why now</h3>
        <p>{artifact.whyNow}</p>
      </section>
      <section className="intervention-fact">
        <h3>Sources</h3>
        <div className="intervention-sources">
          {artifact.sources.map((source) => <details className="intervention-source" key={source.sourceHandle}>
            <summary><BookOpenText size={14} aria-hidden="true" /><span>{source.documentName} · p. {source.pageNumber}</span></summary>
            {"quote" in source ? <blockquote>{source.quote}</blockquote> : <p>{source.sectionPath.join(" › ") || "Page-level source context"}</p>}
          </details>)}
        </div>
      </section>
      <section className="intervention-fact">
        <h3>What next</h3>
        <p>{artifact.whatNext.label}</p>
      </section>
    </div>
    {notice ? <p className={`diagnostic-notice ${notice.tone}`} role="alert">{notice.text}</p> : null}
    <InterventionActions
      response={response}
      operation={operation}
      paused={paused}
      retryIntent={retryIntent}
      promoteFirst={!readyArtifact}
      fallbackAction={!readyArtifact && response.fallback?.action === "source_review"
        ? {
            label: response.fallback.label,
            onSelect: () => onReturnToSource(stateScope),
          }
        : null}
      onAction={runAction}
    />
  </section>;
}

function ProviderRecovery({
  onConfigure,
  onReviewSource,
}: {
  onConfigure: () => void;
  onReviewSource: () => void;
}) {
  return <section className="checkpoint learning-intervention" role="alert" aria-labelledby="learning-provider-recovery-title">
    <Badge tone="warning">Provider setup needed</Badge>
    <h2 id="learning-provider-recovery-title">Connect a provider to continue with the Agent</h2>
    <p>No learning provider is configured. Your Recall result and source review remain saved, and no practice was started.</p>
    <div className="checkpoint-actions intervention-actions" aria-label="Provider recovery actions">
      <Button className="primary" onClick={onConfigure}>Configure learning provider</Button>
      <Button onClick={onReviewSource}>Review source instead</Button>
    </div>
  </section>;
}

function InterventionActions({
  response,
  operation,
  paused,
  retryIntent,
  promoteFirst = true,
  fallbackAction = null,
  onAction,
}: {
  response: LearningInterventionResponse;
  operation: Operation;
  paused: boolean;
  retryIntent: FrozenIntent | null;
  promoteFirst?: boolean;
  fallbackAction?: { label: string; onSelect: () => void } | null;
  onAction: (intent: LearningInterventionIntent) => Promise<void>;
}) {
  const available = actions.filter((item) => response.actions.includes(item.label));
  const [expanded, setExpanded] = useState(false);
  const disclosureId = useId();
  const disabled = paused || operation !== null;
  const start = (intent: LearningInterventionIntent) => {
    setExpanded(false);
    void onAction(intent);
  };
  const retryAction = retryIntent ? actions.find((item) => item.intent === retryIntent.intent) : null;

  if (retryAction) return <div className="intervention-action-block">
    <div className="checkpoint-actions intervention-actions" aria-label="Learning Agent actions">
      <Button
        className="primary"
        disabled={disabled}
        onClick={() => start(retryAction.intent)}
      >
        {operation === retryAction.intent ? <LoaderCircle className="spin" size={14} /> : null}
        {operation === retryAction.intent ? "Retrying Agent…" : `Retry ${retryAction.label.toLowerCase()}`}
      </Button>
      {fallbackAction ? <Button disabled={operation !== null} onClick={fallbackAction.onSelect}>{fallbackAction.label}</Button> : null}
    </div>
    {usesConfiguredProvider(retryAction.intent) ? <ProviderActionDisclosure /> : null}
  </div>;
  if (available.length === 0 && !fallbackAction) return null;

  const [primaryAction, ...alternativeActions] = available;
  const showPrimary = promoteFirst && primaryAction;
  const showDisclosure = !promoteFirst ? available : alternativeActions;
  const hasProviderAction = available.some((item) => usesConfiguredProvider(item.intent));
  return <div className="intervention-action-block">
    <div className="checkpoint-actions intervention-actions" aria-label="Learning Agent actions">
      {showPrimary ? <Button
        className="primary"
        disabled={disabled}
        onClick={() => start(showPrimary.intent)}
      >
        {operation === showPrimary.intent ? <LoaderCircle className="spin" size={14} /> : null}
        {operation === showPrimary.intent
          ? showPrimary.intent === "test_me_instead" ? "Preparing practice…" : "Starting Agent…"
          : showPrimary.label}
      </Button> : null}
      {fallbackAction ? <Button disabled={operation !== null} onClick={fallbackAction.onSelect}>{fallbackAction.label}</Button> : null}
      {showDisclosure.length > 0 ? <div className="intervention-alternatives">
        <button
          aria-controls={disclosureId}
          aria-expanded={expanded}
          className="intervention-alternatives-trigger"
          disabled={disabled}
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >Try another approach…</button>
        <div className="intervention-alternatives-group" hidden={!expanded} id={disclosureId}>
          {showDisclosure.map((item) => <Button
            disabled={disabled}
            key={item.intent}
            onClick={() => start(item.intent)}
          >
            {operation === item.intent ? <LoaderCircle className="spin" size={14} /> : null}
            {operation === item.intent
              ? item.intent === "test_me_instead" ? "Preparing practice…" : "Starting Agent…"
              : item.label}
          </Button>)}
        </div>
      </div> : null}
    </div>
    {hasProviderAction ? <ProviderActionDisclosure /> : null}
  </div>;
}
