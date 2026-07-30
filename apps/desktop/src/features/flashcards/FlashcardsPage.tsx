import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type Ref } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Eye, EyeOff, LoaderCircle, RefreshCw, RotateCcw, ServerOff } from "lucide-react";
import { Button, EmptyState } from "@keen/ui";
import { LearningCoreResponseError, type ReviewAttemptResponse, type ReviewItem } from "@keen/api-client";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Page } from "../../components/Page";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { useAppStore } from "../../state/appStore";
import { dueReviewsQueryKey, invalidateLearningContinuityQueries } from "../learningContinuityQueries";
import { BlankStatement, isClozePrompt, readableClozePrompt } from "../clozePrompt";
import { FormattedMathText } from "../MathText";
import "./review-deeptutor.css";

const ratings = [
  { value: "again", label: "Again", key: "1", description: "I could not recall it" },
  { value: "hard", label: "Hard", key: "2", description: "I recalled it with effort" },
  { value: "good", label: "Good", key: "3", description: "I recalled it correctly" },
  { value: "easy", label: "Easy", key: "4", description: "It felt immediate" },
] as const;

type Rating = typeof ratings[number]["value"];
type Notice = { tone: "success" | "error" | "unknown"; text: string };
type ReviewIntent = {
  itemId: string;
  rating: Rating;
  response: string;
  expectedRevision: number;
  taskContext?: { taskId: string; courseId: string };
  idempotencyKey: string;
};

const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function isIdentifier(value: string | null): value is string {
  return value !== null && identifierPattern.test(value);
}

function newIdempotencyKey(): string {
  return `review-${crypto.randomUUID()}`;
}

function readableExpectedAnswer(value: unknown): string | null {
  if (typeof value === "string") return value.trim() || null;
  const strings = Array.isArray(value)
    ? value
    : value && typeof value === "object"
      ? (value as { accepted_answers?: unknown }).accepted_answers
      : null;
  if (!Array.isArray(strings) || strings.length === 0 || !strings.every((entry) => typeof entry === "string" && entry.trim().length > 0)) return null;
  return strings.map((entry) => entry.trim()).join("\n");
}

function provenanceLabel(item: ReviewItem): string {
  const labels: Record<ReviewItem["source_type"], string> = {
    assessment: "Created from assessment",
    mastery_evidence: "Created from learning evidence",
    misconception: "Created from a recorded misconception",
    study_session: "Created from a study session",
    manual: "Created manually",
    agent_recommendation: "Created from a learning recommendation",
  };
  return labels[item.source_type];
}

function reviewReason(item: ReviewItem): string {
  if (item.source_type === "misconception" || item.item_type === "error_replay") {
    return "A saved misconception is due for another retrieval attempt.";
  }
  if (item.lapses > 0 || item.state === "relearning") {
    return `The saved FSRS history scheduled this after ${item.lapses} ${item.lapses === 1 ? "lapse" : "lapses"}.`;
  }
  if (item.source_type === "assessment" || item.source_type === "mastery_evidence") {
    return "This concept is due from evidence recorded during your learning session.";
  }
  if (item.source_type === "agent_recommendation") {
    return "A saved learning recommendation placed this concept in the review queue.";
  }
  if (item.source_type === "study_session") {
    return "The completed learning session scheduled this concept for retrieval practice.";
  }
  return "This manually saved item is due under its local FSRS schedule.";
}

function formatDue(value: string): string {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function blocksGlobalShortcut(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest("input, textarea, select, button, a, [contenteditable='true'], [role='button'], [role='link'], [role='textbox'], nav, aside"));
}

function knownWriteFailure(error: unknown): Notice | null {
  if (!(error instanceof LearningCoreResponseError)) return null;
  if (error.status === 409) return { tone: "error", text: "The review schedule changed before this rating could be applied. Keen refreshed the current queue; reveal the current answer before rating again." };
  if (error.status === 404) return { tone: "error", text: "This review is no longer available. Keen refreshed the current Review state without submitting another rating." };
  if (error.status === 400 || error.status === 422) return { tone: "error", text: "This rating was rejected before it could be applied. Review the current item and try again." };
  return null;
}

function isUnavailableTaskHandoff(error: unknown): error is LearningCoreResponseError {
  return error instanceof LearningCoreResponseError
    && (error.status === 404 || (error.status === 409 && error.detail?.retryable === false));
}

function ReviewLoading() {
  return <div className="review-loading" role="status" aria-label="Loading due reviews"><span className="visually-hidden">Loading due reviews</span><div className="review-skeleton review-skeleton-meta" aria-hidden /><div className="review-skeleton review-skeleton-prompt" aria-hidden /><div className="review-skeleton review-skeleton-recall" aria-hidden /><div className="review-skeleton review-skeleton-actions" aria-hidden /></div>;
}

function ReviewQueueState({ icon, title, description, actions, headingRef }: { icon: ReactNode; title: string; description: string; actions: ReactNode; headingRef?: Ref<HTMLHeadingElement> }) {
  return (
    <section className="review-queue-state" aria-labelledby="review-queue-state-title">
      <header><strong>Review queue</strong><span>0 due</span></header>
      <div className="review-queue-state-row">
        <span className="review-queue-state-icon" aria-hidden="true">{icon}</span>
        <div>
          <h2 ref={headingRef} tabIndex={headingRef ? -1 : undefined} id="review-queue-state-title">{title}</h2>
          <p>{description}</p>
        </div>
        <div className="review-queue-state-actions">{actions}</div>
      </div>
    </section>
  );
}

export function FlashcardsPage() {
  const core = useLearningCore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedCourseId = searchParams.get("course_id");
  const requestedItemId = searchParams.get("review_item_id");
  const originatingTaskId = searchParams.get("task");
  const hasTaskHandoff = [requestedCourseId, requestedItemId, originatingTaskId].some((value) => value !== null);
  const taskContext = useMemo(() => isIdentifier(requestedCourseId) && isIdentifier(requestedItemId) && isIdentifier(originatingTaskId)
    ? { courseId: requestedCourseId, taskId: originatingTaskId, reviewItemId: requestedItemId }
    : null, [originatingTaskId, requestedCourseId, requestedItemId]);
  const taskContextKey = taskContext ? `${taskContext.courseId}:${taskContext.reviewItemId}:${taskContext.taskId}` : null;
  const incompleteTaskHandoff = hasTaskHandoff && taskContext === null;
  const hasTaskContext = taskContext !== null;
  const { setInspector } = useAppStore();
  const [revealedItemId, setRevealedItemId] = useState<string | null>(null);
  const [responseDraft, setResponseDraft] = useState({ itemId: "", text: "" });
  const [reviewed, setReviewed] = useState(0);
  const [writing, setWriting] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [uncertainIntent, setUncertainIntent] = useState<ReviewIntent | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [unavailableTaskContextKey, setUnavailableTaskContextKey] = useState<string | null>(null);
  const [unavailableTaskContextRecovery, setUnavailableTaskContextRecovery] = useState<string | null>(null);
  const taskContextUnavailable = taskContextKey !== null && unavailableTaskContextKey === taskContextKey;
  const writeController = useRef<AbortController | null>(null);
  const promptRef = useRef<HTMLElement | null>(null);
  const completeRef = useRef<HTMLHeadingElement | null>(null);
  const focusAfterRefresh = useRef(false);
  const queryKey = useMemo(() => taskContext
    ? ["learning-core", "due-reviews", core.connectionGeneration, taskContext.courseId, taskContext.reviewItemId] as const
    : dueReviewsQueryKey(core.connectionGeneration), [core.connectionGeneration, taskContext]);
  const queue = useQuery({
    queryKey,
    queryFn: ({ signal }) => {
      if (!core.client) throw new Error("Learning core connection is not available.");
      return core.client.listDueReviews({ ...(taskContext ? { courseId: taskContext.courseId } : {}), limit: 50 }, { signal });
    },
    enabled: core.status === "healthy" && core.client !== null && !incompleteTaskHandoff,
    retry: 1,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
  const scopedItems = taskContext
    ? queue.data?.items.filter((candidate) => candidate.course_id === taskContext.courseId) ?? []
    : queue.data?.items ?? [];
  const item = taskContext
    ? scopedItems.find((candidate) => candidate.id === taskContext.reviewItemId) ?? null
    : scopedItems[0] ?? null;
  const revealed = item !== null && revealedItemId === item.id;
  const response = item !== null && responseDraft.itemId === item.id ? responseDraft.text : "";
  const answer = useMemo(() => item ? readableExpectedAnswer(item.expected_answer) : null, [item]);
  const cloze = useMemo(() => item && isClozePrompt(item.prompt) ? readableClozePrompt(item.prompt) : null, [item]);
  const remaining = scopedItems.length;
  const passTotal = reviewed + remaining;
  const completedFeedDestination = useMemo(() => {
    const params = new URLSearchParams();
    if (taskContext) {
      params.set("status", "completed");
      params.set("task", taskContext.taskId);
      params.set("course_id", taskContext.courseId);
    }
    const query = params.toString();
    return query ? `/feed?${query}` : "/feed";
  }, [taskContext]);
  const taskRecoveryDestination = useMemo(() => {
    if (!taskContext) return "/feed";
    const params = new URLSearchParams({ task: taskContext.taskId, course_id: taskContext.courseId });
    return `/feed?${params.toString()}`;
  }, [taskContext]);
  const taskBoundaryDestination = taskContextUnavailable
    ? unavailableTaskContextRecovery ?? "/feed"
    : reviewed > 0
      ? completedFeedDestination
      : taskRecoveryDestination;

  useEffect(() => {
    setInspector(null);
    return () => setInspector(null);
  }, [setInspector]);

  useEffect(() => () => writeController.current?.abort("connection_changed"), [core.connectionGeneration]);

  useEffect(() => {
    if (!focusAfterRefresh.current || writing) return;
    focusAfterRefresh.current = false;
    window.setTimeout(() => (item ? promptRef.current : completeRef.current)?.focus({ preventScroll: true }), 0);
  }, [item, reviewed, writing]);

  const submitIntent = useCallback(async (intent: ReviewIntent) => {
    if (!core.client || !item || item.id !== intent.itemId || writing || writeController.current) return;
    const controller = new AbortController();
    writeController.current = controller;
    setWriting(true);
    setNotice(null);
    setAnnouncement("Recording rating");
    try {
      const result: ReviewAttemptResponse = await core.client.recordReviewAttempt(intent.itemId, {
        rating: intent.rating,
        response: intent.response,
        expectedRevision: intent.expectedRevision,
        ...(intent.taskContext ? { taskContext: intent.taskContext } : {}),
        idempotencyKey: intent.idempotencyKey,
      }, { signal: controller.signal });
      if (controller.signal.aborted) throw new DOMException("The local request was cancelled before Keen confirmed the response.", "AbortError");
      setReviewed((value) => value + 1);
      setNotice({ tone: "success", text: `Review recorded. Next due ${formatDue(result.schedule.due_at)}.` });
      setAnnouncement("Review recorded. Moving to the next due item.");
      setUncertainIntent(null);
      setRevealedItemId(null);
      setResponseDraft({ itemId: "", text: "" });
      focusAfterRefresh.current = true;
      await invalidateLearningContinuityQueries(queryClient);
    } catch (error) {
      if (controller.signal.reason === "connection_changed") return;
      if (intent.taskContext && isUnavailableTaskHandoff(error)) {
        const message = `${error.detail?.message ?? "This saved review task is no longer available."} No rating was saved.`;
        setUnavailableTaskContextKey(`${intent.taskContext.courseId}:${intent.itemId}:${intent.taskContext.taskId}`);
        setUnavailableTaskContextRecovery(error.status === 409 ? `/feed?${new URLSearchParams({ task: intent.taskContext.taskId, course_id: intent.taskContext.courseId }).toString()}` : "/feed");
        setUncertainIntent(null);
        setRevealedItemId(null);
        setNotice({ tone: "error", text: message });
        setAnnouncement(message);
        await invalidateLearningContinuityQueries(queryClient);
        return;
      }
      const known = knownWriteFailure(error);
      const reconciliation = await queue.refetch();
      await invalidateLearningContinuityQueries(queryClient, "none");
      const reconciledItem = reconciliation.data?.items.find((candidate) => candidate.id === intent.itemId) ?? null;
      focusAfterRefresh.current = true;
      if (known) {
        setUncertainIntent(null);
        setRevealedItemId(null);
        setNotice(known);
        setAnnouncement(known.text);
      } else if (reconciliation.isError) {
        const text = "The rating may have been saved, but Keen could not verify the current schedule. Check the queue again before retrying; retrying this rating will reuse the same submission.";
        setUncertainIntent(intent);
        setNotice({ tone: "unknown", text });
        setAnnouncement(text);
      } else if (reconciledItem?.revision === intent.expectedRevision) {
        const text = "Keen could not confirm the result. This item is still due with the same schedule; retrying will reuse the same rating and submission.";
        setUncertainIntent(intent);
        setNotice({ tone: "unknown", text });
        setAnnouncement(text);
      } else {
        const text = "Keen could not confirm the response. The current schedule was refreshed and this item changed or left the due window, so the rating may already have been saved.";
        setUncertainIntent(null);
        setRevealedItemId(null);
        setNotice({ tone: "unknown", text });
        setAnnouncement(text);
      }
    } finally {
      if (writeController.current === controller) writeController.current = null;
      setWriting(false);
    }
  }, [core.client, item, queryClient, queue, writing]);

  const record = useCallback((rating: Rating) => {
    if (!item || !revealed || answer === null || writing || uncertainIntent) return;
    void submitIntent({
      itemId: item.id,
      rating,
      response,
      expectedRevision: item.revision,
      ...(taskContext ? { taskContext: { taskId: taskContext.taskId, courseId: taskContext.courseId } } : {}),
      idempotencyKey: newIdempotencyKey(),
    });
  }, [answer, item, response, revealed, submitIntent, taskContext, uncertainIntent, writing]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || blocksGlobalShortcut(event.target)) return;
      if (event.code === "Space" && item && answer !== null && !writing && !uncertainIntent) {
        event.preventDefault();
        setRevealedItemId((value) => value === item.id ? null : item.id);
        return;
      }
      const rating = ratings.find((candidate) => candidate.key === event.key);
      if (rating && revealed && !writing && !uncertainIntent) {
        event.preventDefault();
        record(rating.value);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [answer, item, record, revealed, uncertainIntent, writing]);

  return (
    <Page className="review-page" title="Review" description="Work through one question at a time. Recall, reveal, then choose how it felt.">
      <p className="visually-hidden" aria-live="polite">{announcement}</p>
      {core.status === "demo" ? (
        <ReviewQueueState
          icon={<RotateCcw size={20} />}
          title="No reviews are due"
          description="Complete focused study to create a scheduled review from the saved result."
          actions={<Button className="primary" onClick={() => navigate("/?mode=study")}>Start focused study</Button>}
        />
      ) : isLearningCoreStarting(core.status) ? (
        <ReviewLoading />
      ) : core.status !== "healthy" || !core.client ? (
        <EmptyState icon={<ServerOff size={22} aria-hidden />} title="Reviews are unavailable" description="Keen cannot read the due queue right now. No rating has been submitted from this screen." action={<Button onClick={() => void core.retry()}><RefreshCw size={14} />Retry</Button>} />
      ) : incompleteTaskHandoff ? (
        <div className="review-complete" role="status">
          <span className="review-complete-icon"><RotateCcw size={19} aria-hidden /></span>
          <h2 ref={completeRef} tabIndex={-1}>This review task link is incomplete</h2>
          <p>No rating was saved. Return to the Learning Feed and open the current review task again.</p>
          <div className="review-complete-actions"><Button className="primary" onClick={() => navigate("/feed")}>Return to Learning Feed</Button></div>
        </div>
      ) : queue.isPending ? (
        <ReviewLoading />
      ) : queue.isError ? (
        <EmptyState icon={<RotateCcw size={22} aria-hidden />} title="Due reviews could not be loaded" description="No rating was submitted. Retry the queue read to continue." action={<Button onClick={() => void queue.refetch()}><RefreshCw size={14} />Retry</Button>} />
      ) : (taskContextUnavailable || (!item && hasTaskContext)) ? (
        <div className="review-complete" role="status">
          <span className="review-complete-icon"><Check size={19} aria-hidden /></span>
          <h2 ref={completeRef} tabIndex={-1}>This task no longer needs review</h2>
          <p>{taskContextUnavailable ? "The saved task could not be matched to this review. Keen did not substitute another card or course." : "The saved review item is not due for this course. Keen did not substitute another card or course."}</p>
          {notice && <p className={`review-notice ${notice.tone}`} role={notice.tone === "success" ? "status" : "alert"}>{notice.text}</p>}
          <div className="review-complete-actions"><Button className="primary" onClick={() => navigate(taskBoundaryDestination)}>Return to Learning Feed</Button>{!taskContextUnavailable && <Button variant="secondary" onClick={() => void queue.refetch()}><RefreshCw size={14} />Check this task again</Button>}</div>
        </div>
      ) : !item ? (
        <>
          {notice && <p className={`review-notice ${notice.tone}`} role={notice.tone === "success" ? "status" : "alert"}>{notice.text}</p>}
          <ReviewQueueState
            icon={<Check size={19} />}
            title={reviewed ? "Reviews complete" : "Nothing is due"}
            description={reviewed ? `${reviewed} ${reviewed === 1 ? "review" : "reviews"} completed in this pass.` : "Return when a saved review becomes due, or continue learning now."}
            actions={<><Button className="primary" onClick={() => navigate(completedFeedDestination)}>Open Learning Feed</Button><Button onClick={() => navigate("/history")}>Open History</Button><Button variant="secondary" onClick={() => void queue.refetch()}><RefreshCw size={14} />Check again</Button></>}
            headingRef={completeRef}
          />
        </>
      ) : (
        <section className="review-workspace" aria-labelledby="review-prompt">
          <header className="review-session-header">
            <div>
              <span className="review-session-label">Review session</span>
              <strong title={item.course_title}>{item.course_title}</strong>
            </div>
            <div className="review-session-progress">
              <span>Question {reviewed + 1} of {passTotal}</span>
              <progress aria-label={`${reviewed} of ${passTotal} reviews completed`} max={Math.max(passTotal, 1)} value={reviewed} />
            </div>
          </header>
          {notice && <div className={`review-notice ${notice.tone}`} role={notice.tone === "success" ? "status" : "alert"}><p>{notice.text}</p>{uncertainIntent && uncertainIntent.itemId === item.id ? <Button onClick={() => void submitIntent(uncertainIntent)} disabled={writing}>Retry same {ratings.find((rating) => rating.value === uncertainIntent.rating)?.label} rating</Button> : null}</div>}

          <div className="review-context">
            <span title={item.concept_name}>{item.concept_name}</span>
            <time dateTime={item.due_at}>Due {formatDue(item.due_at)}</time>
          </div>
          <aside className="review-reason" aria-label="Why this review is due">
            <strong>Why this review</strong>
            <p>{reviewReason(item)}</p>
            <span>{item.scheduler.toUpperCase()} · {item.state} · {item.repetitions} prior {item.repetitions === 1 ? "review" : "reviews"}</span>
          </aside>
          <article ref={promptRef} tabIndex={-1} className={`review-prompt-surface ${revealed ? "is-revealed" : ""}`}>
            <div className="review-card-face">
              <div className="review-prompt-heading"><small>Quick check</small><span>{cloze === null ? "Free recall" : "Missing term"}</span></div>
              {cloze === null ? <><h2 id="review-prompt"><FormattedMathText>{item.prompt}</FormattedMathText></h2><p>Answer from memory before revealing the reference answer.</p></> : <><h2 id="review-prompt">Complete the missing term</h2><p>Recall the missing word or short phrase. You do not need to re-enter the formula.</p><div className="practice-question"><p><BlankStatement>{cloze.question}</BlankStatement></p>{cloze.equation ? <div className="practice-equation">{cloze.equation}</div> : null}</div></>}
            </div>
            <div className="review-response-panel">
              <label className="review-response">
                <span>Your answer <small>Optional self-check</small></span>
                <textarea aria-label="Your recall (optional self-check)" value={response} maxLength={8_000} rows={3} onChange={(event) => setResponseDraft({ itemId: item.id, text: event.target.value })} placeholder="Write what you recalled before revealing the answer…" disabled={writing || uncertainIntent !== null} />
              </label>
              <p className="review-input-hint">Plain text is fine. Write formulas the way you normally would.</p>
            </div>
            {answer === null ? <div className="review-answer-error" role="alert"><strong>This review cannot be rated</strong><p>The expected answer is missing or uses an unsupported display format. Refresh the queue; if it remains, open History to review the originating session.</p><div><Button className="primary" onClick={() => void queue.refetch()}><RefreshCw size={14} />Refresh queue</Button><Button onClick={() => navigate("/history")}>Open History</Button></div></div> : <div className="review-reveal-row"><Button className="review-reveal" variant={revealed ? "secondary" : "primary"} aria-keyshortcuts="Space" onClick={() => setRevealedItemId((value) => value === item.id ? null : item.id)} disabled={writing || uncertainIntent !== null}>{revealed ? <EyeOff size={15} aria-hidden /> : <Eye size={15} aria-hidden />}{revealed ? "Hide expected answer" : "Reveal expected answer"}<kbd>Space</kbd></Button></div>}
            {revealed && answer !== null ? <div className="review-answer" aria-live="polite"><small>Expected answer</small>{answer.split("\n").map((line, index) => <p key={`${index}:${line}`}><FormattedMathText>{line}</FormattedMathText></p>)}</div> : null}
            <footer className="review-card-source"><span>{provenanceLabel(item)}</span></footer>
          </article>

          <div className="review-rating-heading">
            <div><strong>How did this feel?</strong><span>Reveal the answer, then choose the closest match.</span></div>
          </div>
          <fieldset className="rating-row" disabled={!revealed || writing || uncertainIntent !== null || answer === null}>
            <legend>Rate your recall</legend>
            {ratings.map((rating) => <button type="button" className={rating.value} key={rating.value} aria-keyshortcuts={rating.key} onClick={() => record(rating.value)}>{writing ? <LoaderCircle className="spin" size={14} aria-hidden /> : null}<strong>{rating.label}</strong><span>{rating.description}</span><kbd>{rating.key}</kbd></button>)}
          </fieldset>
          {writing ? <Button className="review-cancel" onClick={() => writeController.current?.abort("user_cancelled")}>Cancel and verify schedule</Button> : null}
        </section>
      )}
    </Page>
  );
}
