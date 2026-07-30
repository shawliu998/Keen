import { useEffect, useRef, useState } from "react";
import { BookOpenText, LoaderCircle } from "lucide-react";
import { Button } from "@keen/ui";
import {
  LearningCoreResponseError,
  type AdaptiveAction,
  type AdaptiveStateResponse,
  type AutonomousStudySessionUnit,
  type LearningCoreClient,
} from "@keen/api-client";
import { FormattedMathText } from "../MathText";

type Intent = { actionId: string; revision: number; idempotencyKey: string };

function actionKey(): string {
  const id = globalThis.crypto?.randomUUID?.();
  return `adaptive-action-${id ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

export function AdaptiveSourceReview({
  client,
  sessionId,
  courseId,
  action,
  unit,
  paused,
  onReconciled,
  onCompleted,
}: {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  action: AdaptiveAction;
  unit: AutonomousStudySessionUnit;
  paused: boolean;
  onReconciled: (state: AdaptiveStateResponse) => void;
  onCompleted: () => Promise<void>;
}) {
  const [intent, setIntent] = useState<Intent | null>(null);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [freshAfterConflict, setFreshAfterConflict] = useState(false);
  const [waitingForResume, setWaitingForResume] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const wasPausedRef = useRef(paused);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (waitingForResume && wasPausedRef.current && !paused) {
      setWaitingForResume(false);
      setFreshAfterConflict(true);
    }
    wasPausedRef.current = paused;
  }, [paused, waitingForResume]);

  const reconcile = async (): Promise<AdaptiveStateResponse | null> => {
    try {
      const state = await client.getStudySessionAdaptiveState(sessionId, courseId);
      if (mountedRef.current) onReconciled(state);
      return state;
    } catch {
      return null;
    }
  };

  const complete = async () => {
    if (pending || paused) return;
    const frozen = intent ?? { actionId: action.id, revision: action.revision, idempotencyKey: actionKey() };
    setFreshAfterConflict(false);
    setWaitingForResume(false);
    setIntent(frozen);
    setPending(true);
    setNotice(null);
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      await client.completeStudySessionAdaptiveAction(sessionId, frozen.actionId, {
        course_id: courseId,
        expected_action_revision: frozen.revision,
        idempotency_key: frozen.idempotencyKey,
      }, { signal: controller.signal });
      if (!mountedRef.current) return;
      setIntent(null);
      await onCompleted();
    } catch (error) {
      if (!mountedRef.current) return;
      const restored = await reconcile();
      if (!mountedRef.current) return;
      const exactActionStillPending = restored?.action?.id === frozen.actionId
        && restored.action.revision === frozen.revision
        && restored.action.status === "pending"
        && restored.action.kind === "remediate";
      const rejectedWrite = error instanceof LearningCoreResponseError && error.status >= 400 && error.status < 500;
      if (!exactActionStillPending || rejectedWrite) setIntent(null);
      if (error instanceof LearningCoreResponseError && error.status === 409) {
        const restoredPaused = restored?.state === "paused";
        setWaitingForResume(exactActionStillPending && restoredPaused);
        setFreshAfterConflict(exactActionStillPending && !restoredPaused);
        setNotice(restored
          ? "This learning step changed before it could be completed. Keen restored the latest saved step."
          : "This learning step changed, but Keen could not restore it. Continue remains unavailable until the saved step can be read.");
      } else if (rejectedWrite) {
        setNotice(restored
          ? "The saved remediation action is not available to complete. Keen restored the latest learning step; no write was retried."
          : "The remediation action was rejected and could not be restored. No write was retried.");
      } else {
        setNotice(restored
          ? exactActionStillPending
            ? "Keen could not confirm whether the step was completed. Retry sends the same saved request."
            : "Keen restored the latest saved learning step after the result could not be confirmed."
          : "Keen could not confirm or restore this action. Continue remains unavailable until the saved step can be read.");
      }
    } finally {
      if (mountedRef.current) setPending(false);
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  };

  return <section className="checkpoint" aria-labelledby="adaptive-review-title">
    <div className="checkpoint-label">Source review</div>
    <h2 id="adaptive-review-title" tabIndex={-1}>Review source before practice</h2>
    <aside className="adaptive-decision-note" aria-label="Why Keen chose this step">
      <strong>Why this step</strong>
      <p>Your recall missed the required idea, so Keen selected a source review before targeted practice.</p>
      <span>Saved decision · {action.reason_code.replaceAll("_", " ")}</span>
    </aside>
    <p>{unit.title}</p>
    <p><FormattedMathText>{unit.objective}</FormattedMathText></p>
    <section className="lesson-source-block" aria-label="Source-grounded review material">
      <p><FormattedMathText>{unit.content}</FormattedMathText></p>
      <div className="lesson-note">
        <div className="lesson-note-label"><BookOpenText size={14} aria-hidden="true" /><strong>Source identities</strong></div>
        <p>{unit.source_chunk_ids.map((sourceId) => `Chunk ${sourceId}`).join(" · ")}</p>
      </div>
    </section>
    {notice ? <p className="diagnostic-notice error" role="alert">{notice}</p> : null}
    <div className="checkpoint-actions">
      <Button className="primary" disabled={paused || pending || (notice !== null && intent === null && !freshAfterConflict)} onClick={() => { void complete(); }}>
        {pending ? <LoaderCircle className="spin" size={14} /> : null}
        {pending ? "Continuing…" : intent ? "Retry same continuation" : "Continue to practice"}
      </Button>
    </div>
  </section>;
}
