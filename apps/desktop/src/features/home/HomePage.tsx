import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ArrowUp, ChevronDown, MessageCircleQuestion, NotebookPen } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge, Button } from "@keen/ui";
import { LearningCoreResponseError, type ConversationSourceScope, type IndexedDocument } from "@keen/api-client";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { useAppStore } from "../../state/appStore";
import { storeConversationHandoff } from "../conversation/conversationHandoff";
import { studySessionAction } from "./homeContinuity";
import { useHomeNextTask } from "./useHomeNextTask";

const studyTools = [
  ["ask", "Ask course materials", MessageCircleQuestion],
  ["study", "Start focused study", NotebookPen],
] as const;
type HomeMode = "ask" | "study";
type AskError = { message: string; retryable: boolean };
const modes: readonly HomeMode[] = ["ask", "study"];
const HOME_ASK_RESUME_KEY = "keen-durable-home-ask-resume";
const SESSION_GOAL_HELPER = "Your goal is saved with the source-grounded task and focused study session.";
const modeCopy: Record<HomeMode, { heading: string; description: string; placeholder: string }> = {
  ask: { heading: "Ask a course question", description: "Use the course materials already available to Keen.", placeholder: "Enter a question about your course…" },
  study: { heading: "Start a study session", description: SESSION_GOAL_HELPER, placeholder: "Describe what you want to understand or practice…" },
};
type PendingAsk = {
  conversationId: string;
  userMessageId: string;
  assistantMessageId: string;
  idempotencyKey: string;
  cancelIdempotencyKey: string;
  question: string;
  sourceScope: ConversationSourceScope;
  scopeLabel: string;
};

type PendingStudy = {
  courseId: string;
  goal: string;
  clientRequestId: string;
  idempotencyKey: string;
};

function questionTitle(question: string): string {
  const normalized = question.trim().replace(/\s+/gu, " ");
  return normalized.length <= 96 ? normalized : `${normalized.slice(0, 95).trimEnd()}…`;
}

function sameScope(left: ConversationSourceScope, right: ConversationSourceScope): boolean {
  return left.kind === right.kind && (left.kind !== "course" || (right.kind === "course" && left.courseId === right.courseId));
}

export function HomePage() {
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const core = useLearningCore();
  const [selectedMode, setSelectedMode] = useState<HomeMode>("ask");
  const requestedMode = search.get("mode");
  const requestedCourseId = search.get("course_id");
  const queryMode = requestedMode && modes.includes(requestedMode as HomeMode) ? requestedMode as HomeMode : null;
  const mode = queryMode ?? selectedMode;
  const selectMode = (nextMode: HomeMode) => {
    setSelectedMode(nextMode);
    setAskError(null);
    setStudyStartError(null);
    if (queryMode) {
      const nextSearch = new URLSearchParams(search);
      nextSearch.set("mode", nextMode);
      setSearch(nextSearch, { replace: true });
    }
  };
  const [message, setMessage] = useState("");
  const [sourceCourseId, setSourceCourseId] = useState<string>("");
  const [studyStartError, setStudyStartError] = useState<AskError | null>(null);
  const [startingStudy, setStartingStudy] = useState(false);
  const [askScopeValue, setAskScopeValue] = useState("");
  const [documents, setDocuments] = useState<IndexedDocument[] | null>(null);
  const [documentsError, setDocumentsError] = useState(false);
  const [documentsReload, setDocumentsReload] = useState(0);
  const [askError, setAskError] = useState<AskError | null>(null);
  const [startingAsk, setStartingAsk] = useState(false);
  const askInFlight = useRef(false);
  const studyInFlight = useRef(false);
  const pendingAsk = useRef<PendingAsk | null>(null);
  const pendingStudy = useRef<PendingStudy | null>(null);
  const createController = useRef<AbortController | null>(null);
  const studyController = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const demo = core.status === "demo";
  const demoNextTask = useAppStore((state) => state.tasks.find((task) => task.status !== "completed") ?? null);
  const coreStarting = !demo && isLearningCoreStarting(core.status);
  const canSend = demo ? mode === "ask" : core.status === "healthy";
  const sourceCourses = useMemo(() => core.demoState?.courses ?? [], [core.demoState?.courses]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; createController.current?.abort(); studyController.current?.abort(); };
  }, []);

  useEffect(() => {
    const conversationId = sessionStorage.getItem(HOME_ASK_RESUME_KEY);
    if (!conversationId) return;
    sessionStorage.removeItem(HOME_ASK_RESUME_KEY);
    navigate(`/conversation/${encodeURIComponent(conversationId)}`);
  }, [navigate]);

  useEffect(() => {
    if (demo || core.status !== "healthy" || !core.client) return;
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) { setDocuments(null); setDocumentsError(false); }
      return core.client?.listDocuments({ signal: controller.signal }) ?? [];
    })
      .then((next) => { if (!controller.signal.aborted) setDocuments(next); })
      .catch(() => { if (!controller.signal.aborted) { setDocuments([]); setDocumentsError(true); } });
    return () => controller.abort();
  }, [core.client, core.connectionGeneration, core.status, demo, documentsReload]);

  const indexedDocuments = useMemo(
    () => documents?.filter((document) => document.status === "indexed" && document.chunkCount > 0) ?? [],
    [documents],
  );
  const indexedCourses = useMemo(
    () => sourceCourses.filter((course) => indexedDocuments.some((document) => document.courseIds.includes(course.id))),
    [indexedDocuments, sourceCourses],
  );
  const requestedCourseIsIndexed = requestedCourseId !== null && indexedCourses.some((course) => course.id === requestedCourseId);
  const selectedSourceCourseId = requestedCourseId !== null
    ? requestedCourseIsIndexed ? requestedCourseId : null
    : indexedCourses.some((course) => course.id === sourceCourseId) ? sourceCourseId : null;
  const selectedAskScopeValue = requestedCourseId !== null
    ? requestedCourseIsIndexed ? `course:${requestedCourseId}` : ""
    : askScopeValue;

  const updateCourseSelection = (courseId: string | null) => {
    const nextSearch = new URLSearchParams(search);
    if (courseId) nextSearch.set("course_id", courseId);
    else nextSearch.delete("course_id");
    setSearch(nextSearch, { replace: true });
  };

  const selectedAskScope: { scope: ConversationSourceScope; label: string } | null = selectedAskScopeValue === "all_indexed" && indexedDocuments.length > 0
    ? { scope: { kind: "all_indexed" }, label: "All indexed courses" }
    : selectedAskScopeValue.startsWith("course:")
      ? (() => {
        const course = indexedCourses.find((candidate) => `course:${candidate.id}` === selectedAskScopeValue);
        return course ? { scope: { kind: "course", courseId: course.id }, label: course.title } : null;
      })()
      : null;
  const homeContinuity = useHomeNextTask({
    client: core.client,
    courseIds: sourceCourses.map((course) => course.id),
    enabled: !demo && core.status === "healthy" && !core.demoStateError && sourceCourses.length > 0,
    connectionGeneration: core.connectionGeneration,
  });
  const homeContinuityPending = sourceCourses.length > 0 && homeContinuity.pending;
  const homeContinuityError = sourceCourses.length > 0 ? homeContinuity.error : null;
  const queueHasTasks = demo
    ? demoNextTask !== null
    : homeContinuity.nextReview !== null
      || homeContinuity.nextTask !== null
      || homeContinuity.nextSession !== null;
  const queueResolvedEmpty = demo
    ? demoNextTask === null
    : core.status === "healthy"
      && !core.demoStatePending
      && !core.demoStateError
      && !homeContinuityPending
      && !homeContinuityError
      && homeContinuity.nextReview === null
      && homeContinuity.nextTask === null
      && homeContinuity.nextSession === null;
  const requestFirst = queryMode !== null || requestedCourseId !== null || queueResolvedEmpty;
  const queueIntroduction = demo
    ? "Explore sample tasks and the request handoff. No model or local service is contacted."
    : coreStarting || (core.status === "healthy" && (core.demoStatePending || homeContinuityPending))
      ? "Your saved next actions are loading."
      : core.status !== "healthy" || core.demoStateError || homeContinuityError
        ? "Reload the queue to continue saved work."
        : queueHasTasks
          ? "Continue the next saved task, or open the schedule for everything due."
          : "Nothing is queued right now. Start something new or review your schedule.";
  const submit = async () => {
    if (!message.trim()) return;
    if (demo && mode === "ask") {
      sessionStorage.setItem("keen-new-message", message.trim());
      navigate("/conversation/new");
      return;
    }
    if (demo) return;
    if (mode === "study") {
      if (!core.client || !selectedSourceCourseId) {
        setStudyStartError({ message: "Choose a course with indexed source material before starting a guided path.", retryable: false });
        return;
      }
      if (studyInFlight.current) return;
      const goal = message.trim();
      const existing = pendingStudy.current;
      const operation = existing && existing.courseId === selectedSourceCourseId && existing.goal === goal
        ? existing
        : { courseId: selectedSourceCourseId, goal, clientRequestId: crypto.randomUUID(), idempotencyKey: crypto.randomUUID() };
      pendingStudy.current = operation;
      studyInFlight.current = true;
      setStudyStartError(null);
      setStartingStudy(true);
      try {
        const controller = new AbortController();
        studyController.current = controller;
        const result = await core.client.focusedStudyRequest({
          course_id: operation.courseId,
          goal: operation.goal,
          client_request_id: operation.clientRequestId,
          idempotency_key: operation.idempotencyKey,
        }, { signal: controller.signal });
        if (!result.session) {
          pendingStudy.current = null;
          if (mounted.current) setStudyStartError({
            message: result.recovery_action ?? "Keen could not start a focused study session from this source. Your goal remains in the composer.",
            retryable: false,
          });
          return;
        }
        pendingStudy.current = null;
        setMessage("");
        navigate(`/deep-learn/${encodeURIComponent(result.session.id)}?course_id=${encodeURIComponent(operation.courseId)}`);
      } catch (error) {
        if (!mounted.current) return;
        if (error instanceof LearningCoreResponseError && error.status === 409) {
          setStudyStartError({ message: "This focused-study request ID already belongs to a different saved goal. Change the goal or source to start a new request.", retryable: false });
        } else {
          setStudyStartError({ message: "Keen could not confirm whether this focused study session was started. Retry to reconcile the same saved request.", retryable: true });
        }
      } finally {
        studyController.current = null;
        studyInFlight.current = false;
        if (mounted.current) setStartingStudy(false);
      }
      return;
    }
    if (!core.client || !selectedAskScope || askInFlight.current) return;
    const question = message.trim();
    const existing = pendingAsk.current;
    const operation = existing && existing.question === question && sameScope(existing.sourceScope, selectedAskScope.scope)
      ? existing
      : {
        conversationId: crypto.randomUUID(), userMessageId: crypto.randomUUID(), assistantMessageId: crypto.randomUUID(),
        idempotencyKey: crypto.randomUUID(), cancelIdempotencyKey: crypto.randomUUID(), question,
        sourceScope: selectedAskScope.scope, scopeLabel: selectedAskScope.label,
      };
    pendingAsk.current = operation;
    askInFlight.current = true;
    setStartingAsk(true);
    setAskError(null);
    const request = { id: operation.conversationId, question: operation.question, sourceScope: operation.sourceScope };
    const adopt = (saved: Awaited<ReturnType<typeof core.client.getConversation>>) => {
      storeConversationHandoff({ ...operation, conversation: saved });
      if (mounted.current) {
        sessionStorage.removeItem(HOME_ASK_RESUME_KEY);
        setMessage("");
        navigate(`/conversation/${encodeURIComponent(operation.conversationId)}`);
      } else {
        sessionStorage.setItem(HOME_ASK_RESUME_KEY, operation.conversationId);
      }
    };
    const matches = (saved: Awaited<ReturnType<typeof core.client.getConversation>>) => saved.id === operation.conversationId
      && saved.title === questionTitle(operation.question)
      && sameScope(saved.sourceScope, operation.sourceScope);
    try {
      const controller = new AbortController();
      createController.current = controller;
      const created = await core.client.createConversation(request, { signal: controller.signal });
      adopt(created.conversation);
    } catch (createError) {
      if (createError instanceof LearningCoreResponseError && createError.status === 409) {
        if (mounted.current) setAskError({ message: "This question ID already belongs to a different saved request. Change the question or scope to start a new request.", retryable: false });
        return;
      }
      try {
        const saved = await core.client.getConversation(operation.conversationId);
        if (!matches(saved)) throw new Error("conversation_conflict");
        adopt(saved);
      } catch (readError) {
        if (readError instanceof LearningCoreResponseError && readError.status === 404) {
          if (!mounted.current) return;
          try {
            const replay = await core.client.createConversation(request);
            adopt(replay.conversation);
          } catch {
            if (mounted.current) setAskError({ message: "Keen could not confirm whether this question was started. Retry to reconcile the same request.", retryable: true });
          }
        } else if (mounted.current) {
          setAskError(readError instanceof Error && readError.message === "conversation_conflict"
            ? { message: "This question ID already belongs to a different saved request. Change the question or scope to start a new request.", retryable: false }
            : { message: "Keen could not confirm whether this question was started. Retry to reconcile the same request.", retryable: true });
        }
      }
    } finally {
      createController.current = null;
      askInFlight.current = false;
      if (mounted.current) setStartingAsk(false);
    }
  };

  const nextLiveTask = homeContinuity.nextTask;
  const nextLiveSession = homeContinuity.nextSession;
  const nextLiveReview = homeContinuity.nextReview;
  const nextLiveReviewTask = homeContinuity.nextReviewTask;
  const nextLiveReviewDestination = nextLiveReview && nextLiveReviewTask
    ? `/review?${new URLSearchParams({
      course_id: nextLiveReview.course_id,
      review_item_id: nextLiveReview.id,
      task: nextLiveReviewTask.id,
    }).toString()}`
    : "/review";
  const openLiveTask = (taskId: string, courseId?: string) => {
    const params = new URLSearchParams({ task: taskId });
    if (courseId) params.set("course_id", courseId);
    navigate(`/feed?${params.toString()}`);
  };
  const learningQueue = <section className="home-section home-learning" aria-labelledby="home-learning-title">
    <div className="home-overview">
      <h1>Today</h1>
      <p>{queueIntroduction}</p>
    </div>
    <div className="home-section-head home-next-head"><div><h2 id="home-learning-title">Next up</h2>{demo ? <Badge tone="warning">Sample tasks</Badge> : null}</div>{demo || core.status === "healthy" ? <button onClick={() => navigate("/feed")}>View schedule <ArrowRight size={14} /></button> : null}</div>
    <div className="home-learning-list">
      {demo && demoNextTask ? <div className="home-next-task"><ArrowRight size={14} /><span><strong>{demoNextTask.title}</strong><small>{demoNextTask.course} · {demoNextTask.durationMinutes} min · sample</small></span></div> : null}
      {coreStarting ? <div className="home-learning-state" role="status"><strong>Restoring your learning queue</strong><span>Your next actions will appear here when the workspace is ready.</span></div> : null}
      {!demo && !coreStarting && core.status !== "healthy" ? <div className="home-learning-state" role="alert"><strong>Learning queue unavailable</strong><span>Retry to reload your saved tasks.</span><Button onClick={() => { void core.retry(); }}>Retry</Button>{core.retryError ? <small>{core.retryError}</small> : null}</div> : null}
      {!demo && core.status === "healthy" && (core.demoStatePending || homeContinuityPending) ? <div className="home-learning-state" role="status"><strong>Loading your learning queue</strong><span>Your next actions will appear here.</span></div> : null}
      {!demo && core.status === "healthy" && (core.demoStateError || homeContinuityError) ? <div className="home-learning-state" role="alert"><strong>Learning queue could not be loaded</strong><span>Retry to reload your saved tasks.</span><Button onClick={() => { void homeContinuity.refetch(); }}>Retry</Button></div> : null}
      {!demo && core.status === "healthy" && !core.demoStatePending && !core.demoStateError && sourceCourses.length === 0 ? <div className="home-learning-state"><strong>No course materials yet</strong><span>Add a course before starting focused study.</span><Button onClick={() => navigate("/knowledge")}>Open Knowledge Base</Button></div> : null}
      {!demo && core.status === "healthy" && nextLiveReview ? <div className="home-next-task"><ArrowRight size={14} /><span><small>{nextLiveReview.course_title}</small><strong>Review {nextLiveReview.concept_name}</strong><small>Due now · continue scheduled review</small></span></div> : null}
      {!demo && core.status === "healthy" && !nextLiveReview && nextLiveSession ? <div className="home-next-task"><ArrowRight size={14} /><span><small>{sourceCourses.find((course) => course.id === nextLiveSession.course_id)?.title ?? "Saved course"}</small><strong>{nextLiveSession.goal}</strong><small>{Math.round(nextLiveSession.progress * 100)}% complete · {studySessionAction(nextLiveSession.status)}</small></span></div> : null}
      {!demo && core.status === "healthy" && !nextLiveReview && !nextLiveSession && nextLiveTask ? <div className="home-next-task"><ArrowRight size={14} /><span><small>{sourceCourses.find((course) => course.id === nextLiveTask.course_id)?.title ?? "Saved course"}</small><strong>{nextLiveTask.title}</strong><small>{nextLiveTask.estimated_minutes} min · saved task</small></span></div> : null}
      {!demo && core.status === "healthy" && !core.demoStatePending && !homeContinuityPending && !core.demoStateError && !homeContinuityError && sourceCourses.length > 0 && nextLiveReview === null && nextLiveTask === null && nextLiveSession === null ? <div className="home-learning-state"><strong>Nothing queued</strong><span>Start a question or focused study session.</span></div> : null}
    </div>
    {((demo && demoNextTask) || (!demo && core.status === "healthy" && (nextLiveReview || nextLiveTask || nextLiveSession))) ? <div className="home-next-actions"><Button className="primary" onClick={() => demo && demoNextTask ? openLiveTask(demoNextTask.id) : !demo && nextLiveReview ? navigate(nextLiveReviewDestination) : !demo && nextLiveSession ? navigate(`/deep-learn/${encodeURIComponent(nextLiveSession.id)}?course_id=${encodeURIComponent(nextLiveSession.course_id)}`) : !demo && nextLiveTask ? openLiveTask(nextLiveTask.id, nextLiveTask.course_id) : undefined}>{!demo && nextLiveReview ? "Review now" : !demo && nextLiveSession ? studySessionAction(nextLiveSession.status) : "Continue task"}</Button></div> : null}
  </section>;
  const modeSwitcher = <div className="home-mode-chips" aria-label="Learning intent">{studyTools.map(([toolMode, , Icon]) => <button type="button" key={toolMode} aria-label={toolMode === "ask" ? "Ask sources mode" : "Focused study mode"} aria-pressed={mode === toolMode} disabled={startingStudy || startingAsk} onClick={() => selectMode(toolMode)}><Icon size={14} /><span>{toolMode === "ask" ? "Ask sources" : "Focused study"}</span></button>)}</div>;
  const sourceSelector = !demo ? mode === "study"
    ? <label className="home-source-scope"><span className="home-source-label">Source</span><span className="home-source-control"><select aria-label="Learning source course" value={selectedSourceCourseId ?? ""} disabled={startingStudy || documents === null || indexedCourses.length === 0} onChange={(event) => { const courseId = event.target.value; setSourceCourseId(courseId); setAskScopeValue(courseId ? `course:${courseId}` : ""); setStudyStartError(null); pendingStudy.current = null; pendingAsk.current = null; updateCourseSelection(courseId || null); }}><option value="">Choose a course</option>{indexedCourses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select><ChevronDown size={14} aria-hidden="true" /></span></label>
    : <label className="home-source-scope"><span className="home-source-label">Sources</span><span className="home-source-control"><select aria-label="Question source scope" value={selectedAskScopeValue} disabled={startingAsk || documents === null || indexedDocuments.length === 0} onChange={(event) => { const value = event.target.value; const courseId = value.startsWith("course:") ? value.slice("course:".length) : null; setAskScopeValue(value); setSourceCourseId(courseId ?? ""); setAskError(null); pendingAsk.current = null; updateCourseSelection(courseId); }}><option value="">Choose materials</option>{indexedDocuments.length > 0 ? <option value="all_indexed">All indexed courses</option> : null}{indexedCourses.map((course) => <option key={course.id} value={`course:${course.id}`}>{course.title}</option>)}</select><ChevronDown size={14} aria-hidden="true" /></span></label>
    : null;
  const requestWorkbench = <section className="home-hero home-chat-home" aria-labelledby="home-workbench-title">
    <div className="home-chat-stage">
      <header className="home-prompt-heading">
        <span className="home-prompt-mark" aria-hidden="true"><img src="/brand/keen-mark.svg" alt="" /></span>
        <h1 id="home-workbench-title">What shall we explore?</h1>
        <p className="visually-hidden" id="home-workbench-description">{demo ? mode === "ask" ? "Ask a grounded question with the sample workspace." : "Focused study uses an indexed course in the desktop workspace." : "Choose a learning mode and source, then tell Keen what you want to understand."}</p>
      </header>
      <section className="home-workbench" aria-label={modeCopy[mode].heading}>
        <h2 className="visually-hidden">{modeCopy[mode].heading}</h2>
        {demo && mode === "study" ? <div className="home-demo-study-state">
          <div className="home-demo-study-copy">{modeSwitcher}<div><strong>Focused study needs your desktop workspace</strong><span>Choose an indexed course there to create and save a guided learning path.</span></div></div>
          <Button onClick={() => navigate("/knowledge")}>View sample sources</Button>
        </div> : <div className="composer">
          <textarea className="home-message-input" aria-label="Message Keen" aria-describedby="home-workbench-description" placeholder={modeCopy[mode].placeholder} value={message} disabled={startingStudy || startingAsk} onChange={(event) => { setMessage(event.target.value); if (askError) setAskError(null); if (studyStartError) setStudyStartError(null); }} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!startingStudy && !startingAsk && canSend) void submit(); } }} />
          <div className="composer-bottom">
            <div className="home-composer-tools">
              {modeSwitcher}
              {sourceSelector}
            </div>
            <Button className="primary home-submit" aria-label={mode === "ask" ? "Ask sources" : "Start focused study"} loading={startingStudy || startingAsk} loadingLabel={startingStudy ? "Preparing session…" : startingAsk ? "Starting question…" : undefined} disabled={!message.trim() || !canSend || startingStudy || startingAsk || (mode === "study" && !demo && !selectedSourceCourseId) || (mode === "ask" && !demo && !selectedAskScope)} onClick={() => void submit()}><span>{mode === "ask" ? "Ask sources" : "Start study"}</span><ArrowUp size={16} aria-hidden="true" /></Button>
          </div>
        </div>}
        {!demo && mode === "study" ? <p className="home-mode-description">{modeCopy.study.description}</p> : null}
        {!demo && documents === null ? <p className="home-source-status" role="status">{mode === "study" ? "Checking available course material…" : "Checking available sources…"}</p> : null}
      {!demo && core.status !== "healthy" ? <p className="home-study-error home-service-recovery" role="alert">The learning service is not connected. Your draft remains here. <button type="button" onClick={() => { void core.retry(); }}>Retry connection</button></p> : null}
      {mode === "study" && studyStartError ? <p className="home-study-error" role="alert">{studyStartError.message}{studyStartError.retryable ? <> <button type="button" onClick={() => void submit()}>Retry</button></> : null}</p> : null}
      {mode === "ask" && askError ? <p className="home-study-error" role="alert">{askError.message}{askError.retryable ? <> <button type="button" onClick={() => void submit()}>Retry</button></> : null}</p> : null}
      {!demo && documents !== null && documentsError ? <p className="home-study-error" role="alert">Keen could not check which course materials are ready. <button type="button" onClick={() => setDocumentsReload((value) => value + 1)}>Retry</button></p> : null}
      {!demo && documents !== null && !documentsError && requestedCourseId !== null && !requestedCourseIsIndexed ? <p className="home-study-error" role="alert">The selected course no longer has indexed material available. Choose another indexed course or return to Knowledge Base.</p> : null}
      {mode === "ask" && !demo && documents !== null && !documentsError && indexedDocuments.length === 0 ? <p className="home-study-error">Add and index course material before asking. <button type="button" onClick={() => navigate("/knowledge")}>Open Knowledge Base</button></p> : null}
      </section>
    </div>
  </section>;

  return (
    <div className={`home-page ${requestFirst ? "is-request-first" : "has-learning-queue"}`}>
      {requestFirst ? requestWorkbench : learningQueue}
    </div>
  );
}
