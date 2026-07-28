import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpenText,
  Check,
  Clock3,
  GitCompareArrows,
  LoaderCircle,
  Plus,
  Undo2,
} from "lucide-react";
import {
  type LearningCoreClient,
  LearningCoreResponseError,
  LearningCoreSchemaError,
  type StudyPlanProposalResponse,
} from "@keen/api-client";
import { Badge, Button } from "@keen/ui";
import { FormattedMathText } from "../MathText";

type FrozenRequest = {
  idempotencyKey: string;
  sessionRevision: number;
  planVersion: number;
  targetUnitId: string;
  triggerOrigin: "learner_request" | "adaptive_evidence";
};

type FrozenDecision = {
  artifactId: string;
  decision: "accept" | "keep";
  idempotencyKey: string;
  sessionRevision: number;
  planVersion: number;
};

type FrozenUndo = {
  proposalId: string;
  idempotencyKey: string;
  sessionRevision: number;
};

function proposalKey(): string {
  const id = globalThis.crypto?.randomUUID?.();
  return `plan-proposal-${id ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function restoreMessage(error: unknown): string {
  if (error instanceof LearningCoreResponseError && error.status === 503) {
    return "The local learning service could not restore this suggestion. Your saved plan was not changed.";
  }
  if (error instanceof LearningCoreSchemaError) {
    return "Keen received a plan suggestion it could not verify. It was not shown, and your saved plan was not changed.";
  }
  return "Keen could not confirm the saved plan suggestion. Your current plan remains in place.";
}

function unavailableMessage(reason: string | null): string {
  if (reason === "provider_missing") {
    return "A learning provider is required to create this source-grounded suggestion. Your current plan remains available.";
  }
  if (reason === "provider_unavailable") {
    return "The learning provider is unavailable. No suggestion was accepted and your current plan was not changed.";
  }
  return "The proposed unit did not pass Keen’s plan and source checks. It was discarded without changing your plan.";
}

function writeErrorMessage(error: unknown): string {
  if (error instanceof LearningCoreResponseError && error.status === 409) {
    return "The learning session or plan changed before Keen could confirm this action. Refresh the current plan before trying again.";
  }
  return "Keen could not confirm whether this action reached the local service. Retry reuses the same identity, so it cannot duplicate the change.";
}

export function StudyPlanProposal({
  client,
  sessionId,
  courseId,
  sessionRevision,
  planVersion,
  targetUnitId,
  targetUnitTitle,
  paused,
  stateScope,
  onConfigureProvider,
  onAgentRunChanged,
  onSessionChanged,
}: {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  sessionRevision: number;
  planVersion: number;
  targetUnitId: string;
  targetUnitTitle: string;
  paused: boolean;
  stateScope: string;
  onConfigureProvider: () => void;
  onAgentRunChanged?: (runId: string) => void;
  onSessionChanged: () => void;
}) {
  const scope = `${stateScope}:${sessionId}:${courseId}:${sessionRevision}:${planVersion}:${targetUnitId}`;
  const [loadedScope, setLoadedScope] = useState(scope);
  const [storedResponse, setStoredResponse] = useState<StudyPlanProposalResponse | null>(null);
  const [storedError, setStoredError] = useState<unknown>(null);
  const [storedLoading, setStoredLoading] = useState(true);
  const [frozenRequest, setFrozenRequest] = useState<FrozenRequest | null>(null);
  const [frozenDecision, setFrozenDecision] = useState<FrozenDecision | null>(null);
  const [frozenUndo, setFrozenUndo] = useState<FrozenUndo | null>(null);
  const [requestPending, setRequestPending] = useState(false);
  const [mutationPending, setMutationPending] = useState(false);
  const mountedRef = useRef(true);
  const scopeRef = useRef(scope);
  const restoreControllerRef = useRef<AbortController | null>(null);
  const writeControllerRef = useRef<AbortController | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const adaptiveStartRef = useRef<string | null>(null);
  const stateMatchesScope = loadedScope === scope;
  const response = stateMatchesScope ? storedResponse : null;
  const error = stateMatchesScope ? storedError : null;
  const loading = stateMatchesScope ? storedLoading : true;

  useEffect(() => {
    scopeRef.current = scope;
  }, [scope]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      restoreControllerRef.current?.abort();
      writeControllerRef.current?.abort();
      if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
    };
  }, []);

  const isCurrent = useCallback(
    (expected: string) => mountedRef.current && scopeRef.current === expected,
    [],
  );

  const restore = useCallback(async (expected: string) => {
    const controller = new AbortController();
    restoreControllerRef.current?.abort();
    restoreControllerRef.current = controller;
    try {
      const value = await client.getCurrentStudyPlanProposal(sessionId, courseId, {
        signal: controller.signal,
      });
      if (!isCurrent(expected) || restoreControllerRef.current !== controller) return null;
      setStoredResponse(value);
      setStoredError(null);
      setStoredLoading(false);
      if (value.run) onAgentRunChanged?.(value.run.id);
      return value;
    } catch (nextError) {
      if (
        !isCurrent(expected)
        || restoreControllerRef.current !== controller
        || isAbort(nextError)
      ) return null;
      setStoredError(nextError);
      setStoredLoading(false);
      return null;
    } finally {
      if (restoreControllerRef.current === controller) {
        restoreControllerRef.current = null;
      }
    }
  }, [client, courseId, isCurrent, onAgentRunChanged, sessionId]);

  useEffect(() => {
    restoreControllerRef.current?.abort();
    writeControllerRef.current?.abort();
    if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
    const timer = window.setTimeout(() => {
      setLoadedScope(scope);
      setStoredResponse(null);
      setStoredError(null);
      setStoredLoading(true);
      setFrozenRequest(null);
      setFrozenDecision(null);
      setFrozenUndo(null);
      setRequestPending(false);
      setMutationPending(false);
      void restore(scope);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [restore, scope]);

  useEffect(() => {
    if (response?.status !== "queued" && response?.status !== "running") return;
    const expected = scope;
    pollTimerRef.current = window.setTimeout(() => {
      pollTimerRef.current = null;
      void restore(expected);
    }, 700);
    return () => {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [response, restore, scope]);

  const start = useCallback(async (
    triggerOrigin: "learner_request" | "adaptive_evidence" = "learner_request",
  ) => {
    if (requestPending || paused) return;
    const expected = scope;
    const request = frozenRequest ?? {
      idempotencyKey: proposalKey(),
      sessionRevision,
      planVersion,
      targetUnitId,
      triggerOrigin,
    };
    const controller = new AbortController();
    writeControllerRef.current?.abort();
    writeControllerRef.current = controller;
    setFrozenRequest(request);
    setRequestPending(true);
    setStoredError(null);
    try {
      const value = await client.startStudyPlanProposal(sessionId, {
        courseId,
        expectedSessionRevision: request.sessionRevision,
        expectedPlanVersion: request.planVersion,
        targetUnitId: request.targetUnitId,
        request: "insert_source_grounded_prerequisite",
        triggerOrigin: request.triggerOrigin,
        idempotencyKey: request.idempotencyKey,
      }, { signal: controller.signal });
      if (!isCurrent(expected) || writeControllerRef.current !== controller) return;
      setStoredResponse(value);
      setFrozenRequest(null);
      if (value.run) onAgentRunChanged?.(value.run.id);
    } catch (nextError) {
      if (
        !isCurrent(expected)
        || writeControllerRef.current !== controller
        || isAbort(nextError)
      ) return;
      setStoredError(nextError);
    } finally {
      if (isCurrent(expected) && writeControllerRef.current === controller) {
        setRequestPending(false);
        writeControllerRef.current = null;
      }
    }
  }, [
    client,
    courseId,
    frozenRequest,
    isCurrent,
    onAgentRunChanged,
    paused,
    planVersion,
    requestPending,
    scope,
    sessionId,
    sessionRevision,
    targetUnitId,
  ]);

  useEffect(() => {
    const trigger = response?.status === "none" ? response.trigger : null;
    if (
      loading
      || paused
      || requestPending
      || trigger?.origin !== "adaptive_evidence"
    ) return;
    const adaptiveStartKey = [
      scope,
      trigger.reasonCode,
      ...trigger.evidenceIds,
    ].join(":");
    if (adaptiveStartRef.current === adaptiveStartKey) return;
    adaptiveStartRef.current = adaptiveStartKey;
    void start("adaptive_evidence");
  }, [loading, paused, requestPending, response, scope, start]);

  const decide = useCallback(async (decision: "accept" | "keep") => {
    if (mutationPending || paused || !response?.artifact) return;
    const expected = scope;
    const request = frozenDecision ?? {
      artifactId: response.artifact.artifactId,
      decision,
      idempotencyKey: proposalKey(),
      sessionRevision: response.artifact.baseSessionRevision,
      planVersion: response.artifact.basePlanVersion,
    };
    const controller = new AbortController();
    writeControllerRef.current?.abort();
    writeControllerRef.current = controller;
    setFrozenDecision(request);
    setFrozenUndo(null);
    setMutationPending(true);
    setStoredError(null);
    try {
      const value = await client.decideStudyPlanProposal(
        sessionId,
        request.artifactId,
        {
          courseId,
          artifactId: request.artifactId,
          expectedSessionRevision: request.sessionRevision,
          expectedPlanVersion: request.planVersion,
          decision: request.decision,
          idempotencyKey: request.idempotencyKey,
        },
        { signal: controller.signal },
      );
      if (!isCurrent(expected) || writeControllerRef.current !== controller) return;
      setStoredResponse(value);
      setFrozenDecision(null);
    } catch (nextError) {
      if (
        !isCurrent(expected)
        || writeControllerRef.current !== controller
        || isAbort(nextError)
      ) return;
      setStoredError(nextError);
    } finally {
      if (isCurrent(expected) && writeControllerRef.current === controller) {
        setMutationPending(false);
        writeControllerRef.current = null;
      }
    }
  }, [
    client,
    courseId,
    frozenDecision,
    isCurrent,
    mutationPending,
    paused,
    response,
    scope,
    sessionId,
  ]);

  const undo = useCallback(async () => {
    if (mutationPending || paused || !response?.receipt) return;
    const expected = scope;
    const request = frozenUndo ?? {
      proposalId: response.receipt.proposalId,
      idempotencyKey: proposalKey(),
      sessionRevision,
    };
    const controller = new AbortController();
    writeControllerRef.current?.abort();
    writeControllerRef.current = controller;
    setFrozenUndo(request);
    setFrozenDecision(null);
    setMutationPending(true);
    setStoredError(null);
    try {
      const value = await client.undoStudyPlanProposal(
        sessionId,
        request.proposalId,
        {
          courseId,
          expectedSessionRevision: request.sessionRevision,
          idempotencyKey: request.idempotencyKey,
        },
        { signal: controller.signal },
      );
      if (!isCurrent(expected) || writeControllerRef.current !== controller) return;
      setStoredResponse(value);
      setFrozenUndo(null);
    } catch (nextError) {
      if (
        !isCurrent(expected)
        || writeControllerRef.current !== controller
        || isAbort(nextError)
      ) return;
      setStoredError(nextError);
    } finally {
      if (isCurrent(expected) && writeControllerRef.current === controller) {
        setMutationPending(false);
        writeControllerRef.current = null;
      }
    }
  }, [
    client,
    courseId,
    frozenUndo,
    isCurrent,
    mutationPending,
    paused,
    response,
    scope,
    sessionId,
    sessionRevision,
  ]);

  const resetForFreshSuggestion = () => {
    setFrozenRequest(null);
    setFrozenDecision(null);
    setFrozenUndo(null);
    setStoredResponse({
      status: "none",
      courseId,
      sessionId,
      reason: null,
      run: null,
      artifact: null,
      receipt: null,
      trigger: null,
    });
    setStoredError(null);
  };

  if (loading) {
    return (
      <section className="plan-proposal plan-proposal-restoring" role="status">
        <LoaderCircle size={15} aria-hidden="true" />
        <span>Checking for a saved plan suggestion…</span>
      </section>
    );
  }

  if (error) {
    const hasFrozenWrite = frozenRequest !== null
      || frozenDecision !== null
      || frozenUndo !== null;
    const writeConflict = hasFrozenWrite
      && error instanceof LearningCoreResponseError
      && error.status === 409;
    return (
      <section className="plan-proposal plan-proposal-message" role="alert">
        <div>
          <strong>
            {frozenDecision || frozenUndo
              ? "Plan decision not confirmed"
              : "Plan suggestion unavailable"}
          </strong>
          <p>{hasFrozenWrite ? writeErrorMessage(error) : restoreMessage(error)}</p>
        </div>
        <Button
          disabled={paused || requestPending || mutationPending}
          onClick={() => {
            if (writeConflict) onSessionChanged();
            else if (frozenUndo) void undo();
            else if (frozenDecision) void decide(frozenDecision.decision);
            else if (frozenRequest) void start();
            else void restore(scope);
          }}
        >
          {writeConflict
            ? "Refresh current plan"
            : frozenUndo
              ? "Retry Undo"
              : frozenDecision
                ? "Retry decision"
                : frozenRequest
                  ? "Retry request"
                  : "Try again"}
        </Button>
      </section>
    );
  }

  if (!response || response.status === "none") {
    const adaptiveTrigger = response?.trigger?.origin === "adaptive_evidence"
      ? response.trigger
      : null;
    if (adaptiveTrigger && requestPending) {
      return (
        <section className="plan-proposal plan-proposal-running" role="status">
          <LoaderCircle size={16} aria-hidden="true" />
          <div>
            <strong>Preparing an Agent suggestion…</strong>
            <p>Keen is checking the saved learning evidence. Your current plan remains unchanged.</p>
          </div>
        </section>
      );
    }
    return (
      <section className="plan-proposal plan-proposal-invitation" aria-labelledby="plan-proposal-invitation-title">
        <div>
          <strong id="plan-proposal-invitation-title">
            Need a bridge before {targetUnitTitle}?
          </strong>
          <p>Keen can suggest one short, source-grounded prerequisite. Your saved plan will not change.</p>
        </div>
        <Button disabled={paused || requestPending} onClick={() => void start("learner_request")}>
          <Plus size={14} aria-hidden="true" />
          {requestPending ? "Requesting…" : "Suggest prerequisite"}
        </Button>
      </section>
    );
  }

  if (response.status === "queued" || response.status === "running") {
    return (
      <section className="plan-proposal plan-proposal-running" role="status">
        <LoaderCircle size={16} aria-hidden="true" />
        <div>
          <strong>Building one bounded suggestion…</strong>
          <p>Keen is checking the frozen source scope. Your current plan remains usable.</p>
        </div>
      </section>
    );
  }

  if (response.status === "unavailable") {
    const providerMissing = response.reason === "provider_missing";
    return (
      <section className="plan-proposal plan-proposal-message" role="alert">
        <div>
          <strong>Plan suggestion unavailable</strong>
          <p>{unavailableMessage(response.reason)}</p>
        </div>
        {providerMissing
          ? <Button onClick={onConfigureProvider}>Configure provider</Button>
          : <Button disabled={paused} onClick={resetForFreshSuggestion}>Try a fresh suggestion</Button>}
      </section>
    );
  }

  const artifact = response.artifact;
  if (!artifact) return null;
  const stale = response.status === "stale";
  const accepted = response.status === "accepted";
  const rejected = response.status === "rejected";
  const undone = response.status === "undone";
  const resolved = accepted || rejected || undone;
  const operation = artifact.operation;
  const adaptiveTrigger = response.trigger?.origin === "adaptive_evidence"
    ? response.trigger
    : null;
  const proposedSequence = artifact.currentPlan.units.flatMap((unit) => (
    unit.id === operation.beforeUnitId
      ? [
          {
            id: artifact.artifactId,
            title: operation.title,
            minutes: operation.estimatedMinutes,
            proposed: true,
          },
          {
            id: unit.id,
            title: unit.title,
            minutes: unit.estimatedMinutes,
            proposed: false,
          },
        ]
      : [{
          id: unit.id,
          title: unit.title,
          minutes: unit.estimatedMinutes,
          proposed: false,
        }]
  ));

  return (
    <section
      className={`plan-proposal plan-proposal-ready${stale ? " is-stale" : ""}`}
      aria-labelledby="plan-proposal-title"
    >
      <div className="plan-proposal-heading">
        <div>
          <Badge tone={stale ? "warning" : "accent"}>
            {stale
              ? "Suggestion out of date"
              : accepted
                ? "Adjustment saved"
                : rejected
                  ? "Current plan kept"
                  : undone
                    ? "Adjustment undone"
                    : adaptiveTrigger
                      ? "Agent suggested · not applied"
                      : "Plan suggestion · not applied"}
          </Badge>
          <h3 id="plan-proposal-title">{operation.title}</h3>
          <p>{artifact.reason}</p>
        </div>
        <GitCompareArrows size={18} aria-hidden="true" />
      </div>

      {adaptiveTrigger
        ? (
            <div className="plan-proposal-why">
              <strong>Why now</strong>
              <p>{adaptiveTrigger.whyNow}</p>
              <small>
                Based on {adaptiveTrigger.evidenceIds.length} saved learning evidence
                {adaptiveTrigger.evidenceIds.length === 1 ? " item" : " items"}.
                {" "}Keen will not change the plan until you accept or keep it.
              </small>
            </div>
          )
        : null}

      <div className="plan-proposal-objective">
        <strong>What this unit adds</strong>
        <p><FormattedMathText>{operation.objective}</FormattedMathText></p>
      </div>

      <div className="plan-proposal-sequence">
        <strong>Proposed sequence</strong>
        <ol>
          {proposedSequence.map((unit) => (
            <li key={unit.id} className={unit.proposed ? "is-proposed" : undefined}>
              <span className="plan-proposal-index">
                {unit.proposed ? <Plus size={12} aria-hidden="true" /> : <Check size={11} aria-hidden="true" />}
              </span>
              <span>
                <strong>{unit.title}</strong>
                <small>
                  <Clock3 size={11} aria-hidden="true" />
                  {unit.minutes} min{unit.proposed ? " · proposed" : ""}
                </small>
              </span>
            </li>
          ))}
        </ol>
      </div>

      <details className="plan-proposal-sources">
        <summary>
          <BookOpenText size={14} aria-hidden="true" />
          {artifact.sources.length} cited source{artifact.sources.length === 1 ? "" : "s"}
        </summary>
        {artifact.sources.map((source) => (
          <div key={source.sourceHandle}>
            <strong>{source.documentName} · p. {source.pageNumber}</strong>
            <blockquote>{source.quote}</blockquote>
          </div>
        ))}
      </details>

      <div className="plan-proposal-foot">
        <p>
          {stale
            ? "The session or plan changed after this was created. This suggestion cannot be used."
            : resolved && response.receipt
              ? response.receipt.message
              : "Preview only. Keen has not changed the saved plan or scheduled this unit."}
        </p>
        {response.receipt?.planVersion
          ? (
              <small>
                Plan version {response.receipt.planVersion}
                {response.receipt.effectiveAfterCurrentStep ? " · starts after the current step" : ""}
              </small>
            )
          : null}
        {stale
          ? <Button disabled={paused} onClick={resetForFreshSuggestion}>Request an updated suggestion</Button>
          : response.status === "ready"
            ? (
                <div className="plan-proposal-actions">
                  <Button
                    disabled={paused || mutationPending}
                    onClick={() => void decide("accept")}
                  >
                    {mutationPending && frozenDecision?.decision === "accept"
                      ? "Saving…"
                      : "Accept adjustment"}
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={paused || mutationPending}
                    onClick={() => void decide("keep")}
                  >
                    {mutationPending && frozenDecision?.decision === "keep"
                      ? "Keeping…"
                      : "Keep current plan"}
                  </Button>
                </div>
              )
            : accepted && response.receipt?.undoAvailable
              ? (
                  <Button
                    variant="secondary"
                    disabled={paused || mutationPending}
                    onClick={() => void undo()}
                  >
                    <Undo2 size={14} aria-hidden="true" />
                    {mutationPending ? "Undoing…" : "Undo adjustment"}
                  </Button>
                )
              : null}
      </div>
    </section>
  );
}
