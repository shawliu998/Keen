import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenText, Check, ChevronLeft, ChevronRight, Lightbulb, Lock, PanelLeftClose, PanelLeftOpen, Pause, Play } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, EmptyState, IconButton, Progress } from "@keen/ui";
import { LearningCoreResponseError, LearningCoreSchemaError, type AdaptiveAction } from "@keen/api-client";
import { useAppStore } from "../../state/appStore";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { useOptionalAgentRuntime } from "../../services/AgentRuntimeProvider";
import { OpeningDiagnostic } from "./OpeningDiagnostic";
import { ActiveRecall } from "./ActiveRecall";
import { TargetedPractice } from "./TargetedPractice";
import { SessionSummary } from "./SessionSummary";
import { DemoLearningEvidence } from "./DemoLearningEvidence";
import { SessionPauseControl } from "./SessionPauseControl";
import { AdaptiveSourceReview } from "./AdaptiveSourceReview";
import { LearningIntervention, type LearningInterventionGate } from "./LearningIntervention";
import { LearningPathPreview } from "./LearningPathPreview";
import { StudyPlanProposal } from "./StudyPlanProposal";
import { buildProviderSettingsPath } from "../settings/providerRecoveryRouting";
import { displayLearningTitle, learningTitlesMatch } from "../learningPresentation";
import { invalidateStudySessionContinuityQueries } from "../learningContinuityQueries";
import { FormattedMathText, MathNotation } from "../MathText";
// Loaded with the reader component so this bounded visual system follows every route state.
import "./deepLearn-deeptutor.css";
const demoUnits = ["Goal & baseline", "Geometric intuition", "The eigenvalue equation", "Eigenspaces", "Checkpoint", "Targeted practice", "Summary"];
const demoLessonCopy = [
  { label: "Sample objective", body: "Identify what you already know about linear transformations before beginning the lesson.", note: "This baseline is illustrative and is not recorded as learner evidence." },
  { label: "Key idea", body: "An eigenvector stays on the same line when a linear transformation is applied. Its magnitude may change, and a negative scale can reverse its orientation.", note: "Direction is preserved up to sign; the eigenvalue describes the scale." },
  { label: "Definition", body: "For a non-zero vector v, the equation Av = λv says that applying A has the same directional effect as multiplying v by a scalar λ.", note: "The vector must be non-zero. The scalar λ may be positive, negative, or zero." },
  { label: "Connection", body: "All eigenvectors associated with the same eigenvalue, together with the zero vector, form that eigenvalue’s eigenspace.", note: "An eigenspace is a subspace, not a single preferred vector." },
  { label: "Sample checkpoint", body: "Use the relationship between direction and scale to explain the transformation in your own words.", note: "This prompt is bundled with the browser demo and does not produce a persisted grade." },
  { label: "Sample practice", body: "Compare several transformed vectors and decide which ones remain on their original span.", note: "Live targeted practice requires a connected local learning session." },
  { label: "Sample review", body: "Review the distinction between invariant direction, scale, eigenvalues, and eigenspaces.", note: "Browser Demo does not schedule a review or update mastery." },
];

type DemoFeedback = {
  kind: "correct" | "hint" | "revise";
  title: string;
  body: string;
};

function repeatsGoal(title: string, goal: string): boolean {
  return learningTitlesMatch(title, goal);
}

function AdaptiveDecisionNote({ action }: { action: AdaptiveAction }) {
  const copy = action.reason_code === "active_recall_correct"
    ? "Your recall covered the required idea, so Keen moved directly to targeted practice."
    : action.reason_code === "remediation_completed"
      ? "You completed the source review, so Keen is checking whether the idea transfers to a new problem."
      : "Your recall missed the required idea, so Keen selected source review before targeted practice.";
  return <aside className="adaptive-decision-note" aria-label="Why Keen chose this step">
    <strong>Why this step</strong>
    <p>{copy}</p>
    <span>Saved decision · {action.reason_code.replaceAll("_", " ")}</span>
  </aside>;
}

function DeepLearnRestore({ message }: { message: string }) {
  return <div className="deep-learn-page deep-learn-restore" role="status" aria-label={message}>
    <header className="session-header deep-learn-restore-header" aria-hidden="true"><div><i className="restore-line short" /><i className="restore-line title" /><i className="restore-line medium" /></div></header>
    <div className="session-layout" aria-hidden="true">
      <aside className="unit-nav deep-learn-restore-rail"><i className="restore-line short" /><i className="restore-line medium" /><i className="restore-line long" /><i className="restore-line medium" /><div className="restore-divider" /><i className="restore-step" /><i className="restore-step" /><i className="restore-step" /><i className="restore-step" /></aside>
      <section className="lesson-content deep-learn-restore-content"><i className="restore-line short" /><i className="restore-line heading" /><i className="restore-line long" /><i className="restore-line medium" /><div className="restore-paragraph"><i /><i /><i /><i /></div><div className="restore-callout"><i /><i /></div><div className="restore-action"><i /><i /></div></section>
    </div>
    <span className="visually-hidden">{message}</span>
  </div>;
}

function LearningPathRail({ label, children }: { label: string; children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  return <aside className={`unit-nav ${collapsed ? "is-collapsed" : ""}`} aria-label={label}>
    <div className="unit-nav-heading"><small>{label}</small><IconButton label={collapsed ? "Expand learning path" : "Collapse learning path"} onClick={() => setCollapsed((value) => !value)}>{collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}</IconButton></div>
    {children}
  </aside>;
}

function LearningStepRail({
  current,
  next,
  recallCompleted,
  updated,
}: {
  current: string;
  next: string;
  recallCompleted: boolean;
  updated: boolean;
}) {
  return <div className="unit-nav-now" aria-label="Current and next learning step">
    <ol className="unit-nav-flow">
      {recallCompleted ? <li className="is-complete"><i><Check size={11} aria-hidden="true" /></i><span>Recall</span></li> : null}
      <li className="is-current"><i aria-hidden="true" /><span><small>Current</small><strong>{current}</strong></span></li>
      <li><i aria-hidden="true" /><span><small>Next</small><strong>{next}</strong></span></li>
    </ol>
    {updated ? <p>Updated after recall.</p> : null}
  </div>;
}

function DemoDeepLearn() {
  const [unit, setUnit] = useState(1);
  const [paused, setPaused] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<DemoFeedback | null>(null);
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const lessonHeadingRef = useRef<HTMLHeadingElement>(null);
  const feedbackRef = useRef<HTMLParagraphElement>(null);
  const focusLessonAfterChangeRef = useRef(false);
  const { setInspector } = useAppStore();
  useLayoutEffect(() => {
    if (answering) answerRef.current?.focus({ preventScroll: true });
  }, [answering]);
  useLayoutEffect(() => {
    if (!focusLessonAfterChangeRef.current) return;
    focusLessonAfterChangeRef.current = false;
    lessonHeadingRef.current?.focus();
  }, [unit]);
  useLayoutEffect(() => {
    if (feedback && !answering) feedbackRef.current?.focus({ preventScroll: true });
  }, [answering, feedback]);
  const submit = () => {
    const separatesDirectionAndScale = answer.toLowerCase().includes("direction") || answer.toLowerCase().includes("scalar");
    setFeedback(separatesDirectionAndScale
      ? { kind: "correct", title: "Direction and scale separated", body: "Exactly. You separated direction from magnitude." }
      : { kind: "revise", title: "One idea is missing", body: "Good start. Add what changes—and what stays invariant." });
    setAnswering(false);
  };
  const openUnit = (index: number) => {
    focusLessonAfterChangeRef.current = true;
    setUnit(index);
    setAnswering(false);
    setAnswer("");
    setFeedback(null);
    if (index === unit) {
      focusLessonAfterChangeRef.current = false;
      lessonHeadingRef.current?.focus();
    }
  };
  const summary = unit === demoUnits.length - 1;
  const nextDemoStep = demoUnits[unit + 1] ?? "No review is scheduled in Browser Demo";
  const openDemoSource = () => setInspector({
    eyebrow: "Unverified demo citations",
    title: "Bundled demo source",
    body: "These page labels demonstrate citation placement only. No indexed document is connected, and the page references are not verified learner evidence.",
    meta: ["Direction and scale · p. 1 · demo", "Eigenvalue equation · p. 2 · demo"],
  });
  return <div className="deep-learn-page">
    <header className="session-header session-header-live"><div><span>Focused study</span><h1>Eigenvectors & eigenspaces</h1></div><div><Button className="session-demo-toggle" size="small" aria-label={paused ? "Resume demo" : "Pause demo"} onClick={() => setPaused(!paused)}>{paused ? <Play size={13} /> : <Pause size={13} />}{paused ? "Resume" : "Pause"}</Button></div></header>
    <div className="session-layout"><LearningPathRail label="Learning path"><div className="unit-nav-progress" aria-label="Demo progress"><span>Unit {unit + 1} of {demoUnits.length}</span><strong>{Math.round(((unit + 1) / demoUnits.length) * 100)}%</strong><Progress value={((unit + 1) / demoUnits.length) * 100} /></div><div className="unit-nav-now" aria-label="Current and next demo step"><span>Current</span><strong>{demoUnits[unit]}</strong><div><span>Next</span><p>{nextDemoStep}</p></div></div>{demoUnits.map((label, index) => <button type="button" key={label} className={unit === index ? "active" : index < unit ? "done" : ""} aria-current={unit === index ? "step" : undefined} disabled={paused || answering} onClick={() => openUnit(index)}><i>{index < unit ? <Check size={12} /> : index + 1}</i><span>{label}</span></button>)}</LearningPathRail>
      <section className="lesson-content" aria-label="Lesson content"><div className="lesson-kicker">Read, then recall · Unit {unit + 1} of {demoUnits.length}</div><h2 ref={lessonHeadingRef} tabIndex={-1}>{demoUnits[unit]}</h2><p className="lesson-lead">Build geometric intuition before moving to the eigenvalue equation.</p>
        {!summary && <section className="lesson-reading" aria-label="Bundled sample explanation"><p><FormattedMathText>{demoLessonCopy[unit].body}</FormattedMathText></p><div className="lesson-note"><div className="lesson-note-label"><BookOpenText size={14} aria-hidden="true" /><strong>{demoLessonCopy[unit].label}</strong></div><p><FormattedMathText>{demoLessonCopy[unit].note}</FormattedMathText></p></div></section>}
        {paused ? <div className="demo-pause-inline" role="status"><Pause size={14} aria-hidden="true" /><p><strong>Demo paused</strong><span>Resume to change units or answer the prompt.</span></p></div> : summary ? <DemoLearningEvidence onOpenSource={openDemoSource} /> : <Card className="checkpoint lesson-checkpoint demo-recall"><div className="demo-recall-heading"><span className="checkpoint-label">Recall · about 2 min</span><h3>What can change when a matrix acts on an eigenvector?</h3><p>Answer in plain language. If useful, type <MathNotation value={"A v = \\lambda v"} />; special formatting is optional.</p></div>{answering ? <div className="answer-box"><label className="demo-answer-label" htmlFor="demo-recall-answer">Your response</label><textarea id="demo-recall-answer" ref={answerRef} aria-label="Recall answer" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Describe what changes and what stays invariant…" /><div className="demo-answer-actions"><Button onClick={() => setAnswering(false)}>Cancel</Button><Button className="primary" disabled={!answer.trim()} onClick={submit}>Check answer</Button></div></div> : <><div className="checkpoint-actions"><Button className="primary" onClick={() => setAnswering(true)}>{feedback?.kind === "revise" ? "Revise answer" : feedback?.kind === "correct" ? "Edit answer" : "Answer now"}</Button><Button onClick={() => setFeedback({ kind: "hint", title: "A useful distinction", body: "Compare magnitude with direction." })}><Lightbulb size={14} />Give me a hint</Button></div>{feedback && <div className={`demo-recall-feedback is-${feedback.kind}`} role="status"><span aria-hidden="true">{feedback.kind === "correct" ? <Check size={15} /> : <Lightbulb size={15} />}</span><div><strong>{feedback.title}</strong><p ref={feedbackRef} className="feedback" tabIndex={-1}>{feedback.body}</p></div></div>}</>}</Card>}
        {!answering ? <div className="lesson-nav lesson-unit-nav"><div className="lesson-nav-secondary"><Button disabled={paused || unit === 0} onClick={() => openUnit(unit - 1)}><ChevronLeft size={14} />Previous</Button><Button onClick={openDemoSource}><BookOpenText size={14} aria-hidden="true" />Demo source</Button></div><Button className="primary" disabled={paused || unit === demoUnits.length - 1} onClick={() => openUnit(unit + 1)}>Next unit<ChevronRight size={14} /></Button></div> : null}
      </section>
    </div>
  </div>;
}

function RecallInspectorProtection() {
  const { setInspector } = useAppStore();
  useLayoutEffect(() => {
    setInspector(null);
  }, [setInspector]);
  return null;
}

function PracticeInspectorProtection() {
  const { setInspector } = useAppStore();
  useLayoutEffect(() => {
    setInspector(null);
  }, [setInspector]);
  return null;
}

function AdaptiveStateRecovery({ pending, error, onRetry }: { pending: boolean; error: unknown; onRetry: () => void }) {
  if (pending) return <section className="checkpoint" role="status" aria-label="Restoring saved next learning step"><h2>Restoring the saved next step…</h2><p>Practice stays unavailable until Keen verifies the persisted action after active recall.</p></section>;
  const serviceUnavailable = error instanceof LearningCoreResponseError && error.status === 503;
  const invalidResponse = error instanceof LearningCoreSchemaError;
  return <section className="checkpoint" role="alert" aria-labelledby="adaptive-state-recovery-title">
    <h2 id="adaptive-state-recovery-title">Next learning step unavailable</h2>
    <p>{serviceUnavailable
      ? "The local learning service could not restore the saved next step. No practice action was started; retry after the service recovers."
      : invalidResponse
        ? "The local learning service returned a next step Keen could not verify. No practice action was started; retry to reconcile the saved session and action."
        : "Keen could not confirm the saved next step. No practice action was started; retry to reconcile the session and action."}</p>
    <div className="checkpoint-actions"><Button className="primary" onClick={onRetry}>Retry next step</Button></div>
  </section>;
}

function SummaryInspectorProtection({ completed }: { completed: boolean }) {
  const { setInspector } = useAppStore();
  useLayoutEffect(() => {
    setInspector(null);
    return () => setInspector(null);
  }, [completed, setInspector]);
  return null;
}

function UnitChangeInspectorProtection({ scope }: { scope: string }) {
  const { setInspector } = useAppStore();
  useLayoutEffect(() => {
    setInspector(null);
  }, [scope, setInspector]);
  return null;
}

export function DeepLearnPage() {
  const runtime = useOptionalAgentRuntime();
  const refreshActivityContext = runtime?.refreshActivityContext;
  const { id: sessionId } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const courseId = search.get("course_id");
  const core = useLearningCore();
  const queryClient = useQueryClient();
  const { setInspector } = useAppStore();
  const query = useQuery({
    queryKey: ["learning-core", "study-session", core.connectionGeneration, courseId, sessionId],
    queryFn: ({ signal }) => {
      if (!core.client || !sessionId || !courseId) throw new Error("A session and its course are required.");
      return core.client.getStudySession(sessionId, courseId, { signal });
    },
    enabled: core.status === "healthy" && core.client !== null && Boolean(sessionId && courseId),
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const adaptiveSupported = core.client !== null && typeof core.client.getStudySessionAdaptiveState === "function" && typeof core.client.completeStudySessionAdaptiveAction === "function";
  const adaptiveQuery = useQuery({
    queryKey: ["learning-core", "study-session-adaptive-state", core.connectionGeneration, courseId, sessionId, query.data?.session.revision],
    queryFn: ({ signal }) => {
      if (!core.client || !sessionId || !courseId) throw new Error("A session and its course are required.");
      return core.client.getStudySessionAdaptiveState(sessionId, courseId, { signal });
    },
    enabled: core.status === "healthy" && adaptiveSupported && Boolean(sessionId && courseId && query.data?.outcome === "ready"),
    retry: 1,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
  const [selectedUnit, setSelectedUnit] = useState<{ scope: string; id: string } | null>(null);
  const [activeRecallState, setActiveRecallState] = useState<{ scope: string; outcome: "not_started" | "pending" | "answered" | "cancelled" | null } | null>(null);
  const [practiceState, setPracticeState] = useState<{ scope: string; outcome: "not_started" | "pending" | "answered" | "cancelled" | null } | null>(null);
  const [adaptiveOverride, setAdaptiveOverride] = useState<{ scope: string; value: Awaited<ReturnType<NonNullable<typeof core.client>["getStudySessionAdaptiveState"]>> } | null>(null);
  const [interventionState, setInterventionState] = useState<{ scope: string; gate: LearningInterventionGate } | null>(null);
  const [interventionPath, setInterventionPath] = useState<{ scope: string; path: "source_review" } | null>(null);
  const [focusPractice, setFocusPractice] = useState(false);
  const currentUnitId = query.data?.current_unit_id ?? null;
  const activeRecallScope = `${core.connectionGeneration}:${sessionId ?? ""}:${courseId ?? ""}:${currentUnitId ?? ""}`;
  const adaptiveScope = `${activeRecallScope}:${query.data?.session.revision ?? ""}`;
  const adaptiveState = adaptiveOverride?.scope === adaptiveScope ? adaptiveOverride.value : adaptiveQuery.data;
  const reconcileSessionContinuity = useCallback(() => {
    void invalidateStudySessionContinuityQueries(queryClient);
  }, [queryClient]);
  const onActiveRecallOutcome = useCallback((scope: string, outcome: "not_started" | "pending" | "answered" | "cancelled" | null) => setActiveRecallState({ scope, outcome }), []);
  const onPracticeOutcome = useCallback((scope: string, outcome: "not_started" | "pending" | "answered" | "cancelled" | null) => setPracticeState({ scope, outcome }), []);
  const onInterventionGateChange = useCallback((scope: string, gate: LearningInterventionGate) => setInterventionState({ scope, gate }), []);
  const onConfigureLearningProvider = useCallback(() => navigate(buildProviderSettingsPath(sessionId ?? "", courseId ?? "")), [courseId, navigate, sessionId]);
  const onInterventionReturnToSource = useCallback((scope: string) => setInterventionPath({ scope, path: "source_review" }), []);
  const onInterventionRunChanged = useCallback((runId: string) => {
    refreshActivityContext?.(runId);
  }, [refreshActivityContext]);
  const onInterventionStateChanged = useCallback(() => {
    setAdaptiveOverride(null);
    setFocusPractice(true);
    reconcileSessionContinuity();
  }, [reconcileSessionContinuity]);
  const activeUnits = query.data?.plan?.units.filter((item) => item.status === "active") ?? [];
  const pointedUnit = currentUnitId === null ? null : query.data?.plan?.units.find((item) => item.id === currentUnitId) ?? null;
  const currentUnit = pointedUnit?.status === "active" && activeUnits.length === 1 && activeUnits[0]?.id === pointedUnit.id ? pointedUnit : null;
  const selectedUnitId = selectedUnit?.scope === currentUnitId ? selectedUnit.id : null;
  const selectedPlanUnit = query.data?.plan?.units.find((item) => item.id === selectedUnitId);
  const unit = selectedPlanUnit && (selectedPlanUnit.status === "completed" || selectedPlanUnit.status === "skipped") ? selectedPlanUnit : currentUnit;
  if (!sessionId) return <DemoDeepLearn />;
  if (core.status === "demo") return <DemoDeepLearn />;
  if (!courseId) return <div className="deep-learn-page"><Card><EmptyState icon={<BookOpenText size={28} />} title="Study session needs a course" description="This link is missing its course scope. Return to the Learning Feed and start the task again." action={<Button onClick={() => navigate("/feed")}>Return to Learning Feed</Button>} /></Card></div>;
  if (core.status !== "healthy") return isLearningCoreStarting(core.status)
    ? <DeepLearnRestore message="Restoring the local study workspace…" />
    : <div className="deep-learn-page"><Card className="service-state" role="alert"><BookOpenText size={23} /><div><strong>Local study session is unavailable</strong><p>The local service cannot read this session right now. No sample lesson was substituted.</p></div><Button onClick={() => { void core.retry(); }}>Retry</Button></Card></div>;
  if (query.isPending) return <DeepLearnRestore message="Loading local study session" />;
  if (query.isError) {
    const missing = query.error instanceof LearningCoreResponseError && query.error.status === 404;
    return <div className="deep-learn-page"><Card className="service-state" role="alert"><BookOpenText size={23} /><div><strong>{missing ? "Study session was not found" : "Study session could not be read"}</strong><p>{missing ? "This local session is unavailable for the requested course. Return to the Learning Feed and start a current task." : "The session was not rendered because its local response could not be confirmed. Retry after the service recovers."}</p></div>{missing ? <Button onClick={() => navigate(`/feed?course_id=${encodeURIComponent(courseId)}`)}>Return to Learning Feed</Button> : <Button onClick={() => { void query.refetch(); }}>Retry</Button>}</Card></div>;
  }
  if (!query.data) return null;
  if (query.data.outcome === "plan_unavailable") {
    const unavailableSession = query.data.session;
    const resumeControl = core.client && unavailableSession.status === "paused"
      ? <SessionPauseControl key={`${unavailableSession.id}:${unavailableSession.status}:${unavailableSession.revision}`} client={core.client} sessionId={sessionId} courseId={courseId} session={unavailableSession} onSessionChanged={reconcileSessionContinuity} />
      : null;
    return <div className="deep-learn-page">
      <header className="session-header session-header-live"><div><span>Study session</span><h1>{displayLearningTitle(unavailableSession.title)}</h1><p>{unavailableSession.goal}</p></div>{resumeControl}</header>
      <Card><EmptyState icon={<BookOpenText size={28} />} title="Study plan unavailable" description={query.data.recovery_action ?? "Return to the Learning Feed and start a source-grounded task."} action={<Button onClick={() => navigate(`/feed?course_id=${encodeURIComponent(courseId)}`)}>Return to Learning Feed</Button>} /></Card>
    </div>;
  }
  const { session, plan } = query.data;
  const sessionTitle = displayLearningTitle(session.title);
  if (!plan) return <div className="deep-learn-page"><Card><EmptyState icon={<BookOpenText size={28} />} title="Study plan unavailable" description="Return to the Learning Feed and refresh the local recommendation." /></Card></div>;
  const activeRecallClientPresent = core.client !== null && typeof core.client.getStudySessionActiveRecall === "function";
  const practiceClientPresent = core.client !== null && typeof core.client.getStudySessionPractice === "function";
  const summaryClientPresent = core.client !== null && typeof core.client.getStudySessionSummary === "function" && typeof core.client.finalizeStudySessionSummary === "function";
  const interventionClientPresent = core.client !== null
    && typeof core.client.getCurrentLearningIntervention === "function"
    && typeof core.client.startLearningIntervention === "function"
    && typeof core.client.cancelLearningIntervention === "function"
    && typeof core.client.learningInterventionEvents === "function";
  const planProposalClientPresent = core.client !== null
    && typeof core.client.getCurrentStudyPlanProposal === "function"
    && typeof core.client.startStudyPlanProposal === "function";
  const activeRecallOutcome = activeRecallState?.scope === activeRecallScope ? activeRecallState.outcome : null;
  const isClosedBookRecall = activeRecallOutcome === "pending";
  const practiceOutcome = practiceState?.scope === activeRecallScope ? practiceState.outcome : null;
  const effectiveSessionStatus = session.status === "paused" ? session.resume_from_status : session.status;
  const summaryPhase = effectiveSessionStatus != null && ["summarizing", "review_scheduling", "completed", "cancelled", "failed"].includes(effectiveSessionStatus);
  const needsOpeningDiagnostic = effectiveSessionStatus === "goal_confirmation" || effectiveSessionStatus === "diagnosing";
  const needsPlanPreparation = effectiveSessionStatus === "draft" || effectiveSessionStatus === "planning";
  if ((!unit || !currentUnit) && !summaryPhase && !needsOpeningDiagnostic && !needsPlanPreparation) return <div className="deep-learn-page"><Card><EmptyState icon={<BookOpenText size={28} />} title="Study plan unavailable" description="The saved current learning unit is missing or inconsistent. Return to the Learning Feed and refresh the local recommendation." /></Card></div>;
  const activeRecallAvailable = activeRecallClientPresent && !summaryPhase && !needsPlanPreparation && effectiveSessionStatus !== "goal_confirmation" && effectiveSessionStatus !== "diagnosing";
  const adaptiveStateUnknownAfterRecall = adaptiveSupported && activeRecallOutcome === "answered" && (adaptiveQuery.isFetching || adaptiveQuery.isError);
  const confirmedAdaptiveState = adaptiveStateUnknownAfterRecall ? undefined : adaptiveState;
  const persistedRemediationAction = confirmedAdaptiveState?.action?.status === "pending" && confirmedAdaptiveState.action.kind === "remediate" && (confirmedAdaptiveState.state === "action_required" || confirmedAdaptiveState.state === "paused")
    ? confirmedAdaptiveState.action
    : null;
  const persistedPracticeAction = confirmedAdaptiveState?.action?.status === "pending" && confirmedAdaptiveState.action.kind === "practice" && (confirmedAdaptiveState.state === "action_required" || confirmedAdaptiveState.state === "paused")
    ? confirmedAdaptiveState.action
    : null;
  const canonicalPracticePhase = confirmedAdaptiveState?.state === "canonical"
    && effectiveSessionStatus === "practicing";
  const interventionProbe = interventionClientPresent && adaptiveSupported && activeRecallOutcome === "answered" && currentUnit !== null;
  const interventionGate = interventionState?.scope === activeRecallScope
    ? interventionState.gate
    : interventionProbe ? "checking" : "ineligible";
  const sourceReviewSelected = interventionPath?.scope === activeRecallScope && interventionPath.path === "source_review";
  const interventionAllowsPractice = interventionProbe && !sourceReviewSelected && interventionGate === "ready";
  const interventionClearsToAdaptivePath = sourceReviewSelected || !interventionProbe || interventionGate === "ineligible";
  const adaptiveAllowsPractice = !adaptiveSupported || confirmedAdaptiveState?.state === "legacy_canonical" || persistedPracticeAction !== null;
  const practiceAvailable = practiceClientPresent
    && !summaryPhase
    && activeRecallOutcome === "answered"
    && (
      persistedPracticeAction !== null
      || canonicalPracticePhase
      || practiceOutcome === "pending"
      || interventionAllowsPractice
      || (adaptiveAllowsPractice && interventionClearsToAdaptivePath)
    );
  // Before either protected read says there is no prompt, never place source-derived
  // lesson detail beside it. Answered/cancelled recall itself is not a permanent lock:
  // the following practice read owns the next protected phase.
  const recallLocksLesson = activeRecallAvailable && (activeRecallOutcome === null || activeRecallOutcome === "pending");
  const practiceLocksLesson = practiceAvailable && (practiceOutcome === null || practiceOutcome === "pending");
  const showAdaptiveRecovery = adaptiveStateUnknownAfterRecall && (sourceReviewSelected || !interventionProbe || interventionGate === "ineligible" || interventionGate === "fallback");
  const interventionLocksLesson = interventionProbe
    && persistedPracticeAction === null
    && !canonicalPracticePhase
    && practiceOutcome !== "pending"
    && !sourceReviewSelected
    && interventionGate !== "ineligible";
  const stepContext = showAdaptiveRecovery
      ? { current: "Active recall", next: "Restore saved next step" }
    : sourceReviewSelected && persistedRemediationAction
      ? { current: "Review source", next: "Targeted practice" }
    : persistedPracticeAction || canonicalPracticePhase || practiceOutcome === "pending"
      ? { current: "Targeted practice", next: "Learning summary" }
    : interventionProbe && (interventionGate === "checking" || interventionGate === "blocked")
      ? { current: "Learning Agent", next: "Targeted practice" }
    : interventionAllowsPractice
      ? { current: "Agent explanation", next: "Targeted practice" }
    : persistedRemediationAction
      ? { current: "Review source", next: "Targeted practice" }
    : session.status === "paused"
    ? { current: "Session paused", next: effectiveSessionStatus === "summarizing" || effectiveSessionStatus === "review_scheduling" ? "Resume the learning summary" : effectiveSessionStatus === "goal_confirmation" || effectiveSessionStatus === "diagnosing" ? "Resume the opening reflection" : "Resume the saved learning step" }
    : needsOpeningDiagnostic
      ? { current: "Opening reflection", next: "First source-grounded unit" }
      : needsPlanPreparation
        ? { current: "Preparing the learning plan", next: "Return to Learning Feed if the plan remains unavailable" }
    : summaryPhase
      ? session.status === "completed"
        ? { current: "Session complete", next: "Review the saved schedule below" }
        : ["cancelled", "failed"].includes(session.status)
          ? { current: "Session ended", next: "Return to Learning Feed" }
          : { current: "Learning summary", next: "Finish and schedule review" }
      : practiceLocksLesson
        ? { current: "Targeted practice", next: "Learning summary" }
        : recallLocksLesson
          ? { current: "Active recall", next: "Targeted practice" }
          : { current: currentUnit?.title ?? "Learning summary", next: activeRecallAvailable ? "Active recall" : "Continue this source-grounded plan" };
  const displayUnit = unit;
  const lesson = displayUnit ? <><div className="lesson-kicker">Explanation · Unit {displayUnit.ordinal + 1}</div><h2>{displayUnit.title}</h2><p className="lesson-lead"><FormattedMathText>{displayUnit.objective}</FormattedMathText></p><section className="lesson-source-block" aria-label="Source-grounded lesson material"><Badge tone="accent">Source-grounded material</Badge><p><FormattedMathText>{displayUnit.content || "This unit has no display text; use the cited source chunks in the inspector."}</FormattedMathText></p></section><div className="lesson-nav"><Button onClick={() => setInspector({ eyebrow: "Source citations", title: displayUnit.title, body: "The following persisted source chunk IDs ground this unit. Source text is displayed as data, not as instructions.", meta: displayUnit.source_chunk_ids.map((source) => `Chunk ${source}`) })}><BookOpenText size={14} />View source citations</Button></div></> : null;
  const reviewingCompletedUnit = currentUnit !== null && displayUnit !== null && displayUnit.id !== currentUnit.id;
  const adaptiveFallbackActive = sourceReviewSelected || !interventionProbe || interventionGate === "ineligible" || interventionGate === "fallback";
  const adaptiveReview = adaptiveFallbackActive && persistedRemediationAction && confirmedAdaptiveState?.current_unit && core.client
    ? <AdaptiveSourceReview
        key={`${persistedRemediationAction.id}:${persistedRemediationAction.revision}`}
        client={core.client}
        sessionId={sessionId}
        courseId={courseId}
        action={persistedRemediationAction}
        unit={confirmedAdaptiveState.current_unit}
        paused={session.status === "paused" || confirmedAdaptiveState.state === "paused"}
        onReconciled={(value) => {
          setAdaptiveOverride({ scope: adaptiveScope, value });
          reconcileSessionContinuity();
        }}
        onCompleted={async () => {
          setAdaptiveOverride(null);
          setFocusPractice(true);
          await invalidateStudySessionContinuityQueries(queryClient);
        }}
      />
    : null;
  const adaptiveRecovery = showAdaptiveRecovery
    ? <AdaptiveStateRecovery pending={adaptiveQuery.isFetching} error={adaptiveQuery.error} onRetry={() => { void Promise.all([query.refetch(), adaptiveQuery.refetch()]); }} />
    : null;
  const intervention = interventionProbe && core.client && currentUnit
    ? <LearningIntervention
        key={`intervention:${activeRecallScope}`}
        client={core.client}
        sessionId={sessionId}
        courseId={courseId}
        currentUnitId={currentUnit.id}
        sessionRevision={confirmedAdaptiveState?.session.revision ?? session.revision}
        stateScope={activeRecallScope}
        paused={session.status === "paused"}
        onGateChange={onInterventionGateChange}
        onConfigureProvider={onConfigureLearningProvider}
        onReturnToSource={onInterventionReturnToSource}
        onAgentRunChanged={onInterventionRunChanged}
        onStateChanged={onInterventionStateChanged}
      />
    : null;
  const proposalTarget = currentUnit === null
    ? null
    : plan.units.find((item) => (
        item.ordinal > currentUnit.ordinal
        && (item.status === "ready" || item.status === "locked")
      )) ?? null;
  const planProposal = planProposalClientPresent
    && core.client
    && proposalTarget
    && interventionGate === "ready"
    ? <StudyPlanProposal
        key={`plan-proposal:${activeRecallScope}:${plan.version}:${proposalTarget.id}`}
        client={core.client}
        sessionId={sessionId}
        courseId={courseId}
        sessionRevision={confirmedAdaptiveState?.session.revision ?? session.revision}
        planVersion={plan.version}
        targetUnitId={proposalTarget.id}
        targetUnitTitle={proposalTarget.title}
        paused={session.status === "paused"}
        stateScope={activeRecallScope}
        onConfigureProvider={onConfigureLearningProvider}
        onAgentRunChanged={onInterventionRunChanged}
        onSessionChanged={reconcileSessionContinuity}
      />
    : null;
  // A current Practice supersedes only a stale intervention fallback. Keep the
  // intervention mounted while it restores so a verified Agent artifact can
  // reappear beside its exact Practice after a cold restart.
  const showIntervention = intervention !== null
    && !sourceReviewSelected
    && interventionGate !== "ineligible"
    && (
      interventionGate === "ready"
      || (
        persistedPracticeAction === null
        && !canonicalPracticePhase
        && practiceOutcome !== "pending"
      )
    );
  const activeRecall = reviewingCompletedUnit
    ? <>{lesson}<div className="lesson-nav"><Button className="primary" onClick={() => setSelectedUnit(null)}>Return to current unit</Button></div></>
    : activeRecallAvailable && core.client && currentUnit ? <>{practiceLocksLesson || adaptiveReview || adaptiveRecovery || interventionLocksLesson ? <PracticeInspectorProtection /> : recallLocksLesson ? <RecallInspectorProtection /> : lesson}<section className={`learning-phase learning-phase-recall${isClosedBookRecall ? " is-closed-book-recall" : ""}`} aria-label={isClosedBookRecall ? "Closed-book recall step" : "Recall step"}><div className="learning-phase-label">{isClosedBookRecall ? "Closed-book recall" : "Recall"}</div><ActiveRecall key={`${core.connectionGeneration}:${courseId}:${sessionId}:${currentUnit.id}`} client={core.client} sessionId={sessionId} courseId={courseId} currentUnitId={currentUnit.id} stateScope={activeRecallScope} session={session} paused={session.status === "paused"} onSessionChanged={reconcileSessionContinuity} onOutcomeChange={onActiveRecallOutcome} /></section>{intervention ? <section className="learning-phase learning-phase-intervention" aria-label="Learning Agent step" hidden={!showIntervention}><div className="learning-phase-label">Learning Agent</div>{intervention}{planProposal}</section> : null}{adaptiveRecovery || adaptiveReview ? <section className="learning-phase learning-phase-intervention" aria-label="Learning Agent recovery step"><div className="learning-phase-label">Learning Agent</div>{adaptiveRecovery}{adaptiveReview}</section> : null}{practiceAvailable ? <section className="learning-phase learning-phase-practice" aria-label="Practice step"><div className="learning-phase-label">Practice</div>{persistedPracticeAction ? <AdaptiveDecisionNote action={persistedPracticeAction} /> : null}<TargetedPractice key={`practice:${core.connectionGeneration}:${courseId}:${sessionId}:${currentUnit.id}:${persistedPracticeAction?.id ?? "legacy"}`} client={core.client} sessionId={sessionId} courseId={courseId} currentUnitId={currentUnit.id} stateScope={activeRecallScope} session={session} paused={session.status === "paused"} focusOnMount={focusPractice} onFocusHandled={() => setFocusPractice(false)} onSessionChanged={reconcileSessionContinuity} onOutcomeChange={onPracticeOutcome} /></section> : null}</> : lesson;
  const summary = summaryPhase ? summaryClientPresent && core.client
    ? <><SummaryInspectorProtection completed={session.status === "completed"} /><SessionSummary key={`summary:${core.connectionGeneration}:${courseId}:${sessionId}`} client={core.client} sessionId={sessionId} courseId={courseId} session={session} onSessionChanged={reconcileSessionContinuity} onOpenReview={() => navigate("/review")} onOpenFeed={() => navigate(`/feed?course_id=${encodeURIComponent(courseId)}`)} /></>
    : <Card className="checkpoint" role="alert"><strong>Learning summary unavailable</strong><p>Keen cannot restore this local summary because the installed learning core does not provide the required summary contract. No review was scheduled.</p></Card>
    : activeRecall;
  const sessionControl = core.client && !["completed", "cancelled", "failed"].includes(session.status)
    ? <SessionPauseControl key={`${session.id}:${session.status}:${session.revision}`} client={core.client} sessionId={sessionId} courseId={courseId} session={session} onSessionChanged={reconcileSessionContinuity} />
    : null;
  const sessionGoal = repeatsGoal(session.title, session.goal) ? null : <p>{session.goal}</p>;
  if (session.status === "completed") return <div className="deep-learn-page is-completed">
    <header className="session-header session-header-completed"><div><span>Study session</span><h1>{sessionTitle}</h1>{sessionGoal}</div></header>
    <section className="session-complete-layout" aria-label="Completed learning session">{summary}</section>
  </div>;
  if (currentUnit === null) {
    if (needsOpeningDiagnostic && core.client) return <div className="deep-learn-page">
      <UnitChangeInspectorProtection scope={activeRecallScope} />
      <header className="session-header session-header-live"><div><span>Study session</span><h1>{sessionTitle}</h1>{sessionGoal}</div>{sessionControl}</header>
      <div className="session-layout"><LearningPathRail label="Source-grounded plan"><div className="unit-nav-progress" aria-label="Session progress"><span>Session progress</span><strong>{Math.round(session.progress * 100)}%</strong><Progress value={session.progress * 100} /><small>{plan.units.filter((item) => item.status === "completed" || item.status === "skipped").length} of {plan.units.length} planned units completed</small></div><div className="unit-nav-now" aria-label="Current and next learning step"><span>Current</span><strong>{stepContext.current}</strong><div><span>Next</span><p>{stepContext.next}</p></div></div>{plan.units.map((item) => <button type="button" key={item.id} className="locked" disabled aria-label={`${item.title} · planned, unavailable until opening reflection`}><i>{item.ordinal + 1}</i><span>{item.title}</span></button>)}<p className="diagnostic-nav-lock" role="status">{session.status === "paused" ? "Resume this session to continue." : "Complete this reflection to continue."}</p></LearningPathRail>
        <section className="lesson-content" aria-label="Learning session content"><LearningPathPreview plan={plan} /><OpeningDiagnostic key={`${core.connectionGeneration}:${courseId}:${sessionId}`} client={core.client} sessionId={sessionId} courseId={courseId} session={session} paused={session.status === "paused"} onSessionChanged={reconcileSessionContinuity}>{null}</OpeningDiagnostic></section>
      </div>
    </div>;
    if (session.status === "cancelled" || session.status === "failed") return <div className="deep-learn-page is-completed">
      <header className="session-header session-header-completed"><div><span>Study session</span><h1>{sessionTitle}</h1><p>{session.goal}</p></div></header>
      <section className="session-complete-layout" aria-label="Ended learning session">{summary}</section>
    </div>;
    if (needsPlanPreparation) return <div className="deep-learn-page">
      <header className="session-header session-header-live"><div><span>Study session</span><h1>{sessionTitle}</h1><p>{session.goal}</p></div>{sessionControl}</header>
      <Card><EmptyState icon={<BookOpenText size={28} />} title="Learning plan is not ready" description="This saved session has not reached its first source-grounded unit. Resume it if paused, or return to the Learning Feed to choose current work." action={<Button onClick={() => navigate(`/feed?course_id=${encodeURIComponent(courseId)}`)}>Return to Learning Feed</Button>} /></Card>
    </div>;
    return <div className="deep-learn-page"><Card><EmptyState icon={<BookOpenText size={28} />} title="Study plan unavailable" description="The saved current learning unit is missing or inconsistent. Return to the Learning Feed and refresh the local recommendation." /></Card></div>;
  }
  return <div className={`deep-learn-page${isClosedBookRecall ? " is-closed-book-recall" : ""}`}>
    <UnitChangeInspectorProtection scope={activeRecallScope} />
    <header className="session-header session-header-live"><div><span>Study session</span><h1>{sessionTitle}</h1>{sessionGoal}</div>{sessionControl}</header>
    <div className="session-layout"><LearningPathRail label="Learning path"><div className="unit-nav-progress is-unit-progress" aria-label="Unit progress"><span>Unit {currentUnit.ordinal + 1} of {plan.units.length}</span><Progress value={session.progress * 100} /><small>{plan.units.filter((item) => item.status === "completed" || item.status === "skipped").length} of {plan.units.length} units complete</small></div><LearningStepRail current={stepContext.current} next={stepContext.next} recallCompleted={activeRecallOutcome === "answered"} updated={Boolean(persistedRemediationAction || persistedPracticeAction)} />{needsOpeningDiagnostic ? <p className="diagnostic-nav-lock" role="status">{session.status === "paused" ? "Resume this session to continue." : "Complete this reflection to continue."}</p> : summaryPhase || practiceLocksLesson || recallLocksLesson || adaptiveReview || adaptiveRecovery || interventionLocksLesson ? null : plan.units.map((item) => {
      const isCurrent = item.id === currentUnit.id;
      const canReview = item.status === "completed" || item.status === "skipped";
      const unavailable = !isCurrent && !canReview;
      const stateLabel = isCurrent ? "current" : item.status === "completed" ? "completed" : item.status === "skipped" ? "skipped" : item.status === "locked" ? "locked" : "up next";
      return <button type="button" key={item.id} className={isCurrent ? "active" : canReview ? "done" : item.status === "locked" ? "locked" : "ready"} aria-current={isCurrent ? "step" : undefined} disabled={unavailable} aria-label={`${item.title} · ${stateLabel}`} onClick={() => { if (canReview) setSelectedUnit({ scope: currentUnitId ?? "", id: item.id }); else if (isCurrent) setSelectedUnit(null); }}><i>{canReview ? <Check size={12} /> : item.status === "locked" ? <Lock size={11} /> : item.ordinal + 1}</i><span>{item.title}</span></button>;
    })}</LearningPathRail>
      <section className="lesson-content" aria-label="Learning session content">{needsOpeningDiagnostic && core.client ? <OpeningDiagnostic key={`${core.connectionGeneration}:${courseId}:${sessionId}`} client={core.client} sessionId={sessionId} courseId={courseId} session={session} paused={session.status === "paused"} onSessionChanged={reconcileSessionContinuity}>{activeRecall}</OpeningDiagnostic> : summary}</section>
    </div>
  </div>;
}
