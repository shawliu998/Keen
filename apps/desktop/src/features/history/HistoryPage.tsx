import { useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpenText, ChevronDown, Clock3, History, MessageSquareText } from "lucide-react";
import { Badge, Button } from "@keen/ui";
import type { AutonomousStudySession, ConversationSummary } from "@keen/api-client";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Page } from "../../components/Page";
import { CollectionEmptyState } from "../../components/CollectionEmptyState";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { CurrentMastery } from "./CurrentMastery";
import { displayLearningTitle, learningTitlesMatch } from "../learningPresentation";
import "./history-deeptutor.css";

type SessionStatus = AutonomousStudySession["status"];
type SessionPresentation = { label: string; action: string; current: string; next: string; terminalNote?: string };

const sessionPresentation: Record<SessionStatus, SessionPresentation> = {
  draft: { label: "Draft", action: "Start session", current: "Set the learning goal", next: "Confirm the session" },
  goal_confirmation: { label: "Ready to start", action: "Start session", current: "Confirm the learning goal", next: "Opening reflection" },
  diagnosing: { label: "Opening reflection", action: "Continue reflection", current: "Opening reflection", next: "Build the learning path" },
  planning: { label: "Preparing path", action: "Continue session", current: "Build the learning path", next: "Begin reading" },
  studying: { label: "Reading", action: "Continue reading", current: "Read the current unit", next: "Check recall" },
  checkpoint: { label: "Checkpoint", action: "Continue reading", current: "Complete the checkpoint", next: "Continue the learning path" },
  active_recall: { label: "Active recall", action: "Continue recall", current: "Answer the recall prompt", next: "Targeted practice" },
  practicing: { label: "Practice", action: "Continue practice", current: "Complete targeted practice", next: "Learning summary" },
  summarizing: { label: "Summary", action: "Finish and schedule review", current: "Learning summary", next: "Schedule review", terminalNote: "Recall and practice are saved. Finish the session to schedule review." },
  review_scheduling: { label: "Finishing", action: "Finish and schedule review", current: "Schedule review", next: "Session complete", terminalNote: "Your learning results are saved. Reopen the session to confirm the review." },
  paused: { label: "Paused", action: "Resume session", current: "Session paused", next: "Resume the saved step" },
  completed: { label: "Completed", action: "View record", current: "Session completed", next: "Review the saved result", terminalNote: "The learning session and its result are complete." },
  cancelled: { label: "Cancelled", action: "View record", current: "Session cancelled", next: "Review the saved record", terminalNote: "The session ended before completion." },
  failed: { label: "Needs attention", action: "View record", current: "Session stopped", next: "Review the recovery state", terminalNote: "The session stopped with a recoverable record." },
};

const questionPresentation: Record<NonNullable<ConversationSummary["answerStatus"]>, { label: string; action: string; note: string; tone?: "success" | "warning" | "danger" }> = {
  pending: { label: "Waiting", action: "Resume question", note: "The answer has not started yet.", tone: "warning" },
  streaming: { label: "In progress", action: "Resume question", note: "Open the question to see its current answer state.", tone: "warning" },
  completed: { label: "Answered", action: "Open record", note: "The saved answer is ready to read.", tone: "success" },
  failed: { label: "Needs attention", action: "Open record", note: "The answer stopped with a saved error state.", tone: "danger" },
  cancelled: { label: "Cancelled", action: "Open record", note: "The answer was cancelled and remains available as a record.", tone: "danger" },
  interrupted: { label: "Interrupted", action: "Open record", note: "The answer was interrupted; open the record for recovery options.", tone: "warning" },
};

function sessionTone(status: SessionStatus): "success" | "warning" | "danger" | undefined {
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "paused") return "warning";
  return undefined;
}

function updatedLabel(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function HistoryLoading({ label }: { label: string }) {
  return <section className="history-loading" role="status" aria-label={label}><span /><span /><span /></section>;
}

export function HistoryPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const core = useLearningCore();
  const courses = useMemo(() => core.demoState?.courses ?? [], [core.demoState?.courses]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const requestedCourseId = searchParams.get("course_id");
  const requestedCourseIsValid = requestedCourseId !== null && courses.some((course) => course.id === requestedCourseId);
  const localCourseIsValid = courses.some((course) => course.id === selectedCourseId);
  const courseId = requestedCourseId !== null
    ? requestedCourseIsValid ? requestedCourseId : ""
    : localCourseIsValid ? selectedCourseId : courses[0]?.id ?? "";
  const requestedCourseIsUnavailable = requestedCourseId !== null && !requestedCourseIsValid;
  const selectedCourse = courses.find((course) => course.id === courseId) ?? null;

  const selectCourse = (nextCourseId: string) => {
    setSelectedCourseId(nextCourseId);
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.set("course_id", nextCourseId);
    setSearchParams(nextSearchParams, { replace: true });
  };

  const questionsQuery = useInfiniteQuery({
    queryKey: ["learning-core", "conversation-history", core.connectionGeneration],
    queryFn: ({ signal, pageParam }) => {
      if (!core.client) throw new Error("The learning service is required before loading questions.");
      return core.client.listConversations({ limit: 25, cursor: pageParam }, { signal });
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: core.status === "healthy" && core.client !== null,
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const questions = useMemo(() => questionsQuery.data?.pages.flatMap((page) => page.conversations) ?? [], [questionsQuery.data]);

  const sessionsQuery = useQuery({
    queryKey: ["learning-core", "study-session-history", core.connectionGeneration, courseId],
    queryFn: ({ signal }) => {
      if (!core.client || !courseId) throw new Error("A course is required before loading study history.");
      return core.client.listStudySessions(courseId, { signal });
    },
    enabled: core.status === "healthy" && core.client !== null && courseId !== "" && !core.demoStateError,
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const sessions = useMemo(() => [...(sessionsQuery.data?.sessions ?? [])].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)), [sessionsQuery.data?.sessions]);
  const hasRecordedMastery = useMemo(() => (
    core.demoState?.mastery.some((row) => row.course_id === courseId && row.attempts > 0) ?? false
  ), [core.demoState?.mastery, courseId]);
  const starting = isLearningCoreStarting(core.status);
  const noSavedStudySessions = courses.length === 0 || (
    courseId !== ""
    && sessionsQuery.isSuccess
    && sessions.length === 0
  );
  const bothEmpty = core.status === "healthy"
    && !core.demoStatePending
    && !core.demoStateError
    && questionsQuery.isSuccess
    && questions.length === 0
    && noSavedStudySessions
    && !hasRecordedMastery;
  const serviceUnavailable = !starting
    && core.status !== "healthy"
    && core.status !== "demo";

  return (
    <Page
      title="Learning history"
      description="Resume a saved study session or reopen an answered question."
      className="history-page"
      actions={courses.length > 1 || (courses.length > 0 && requestedCourseIsUnavailable) ? <label className="history-course"><span>Study course</span><span className="history-course-control"><select aria-label="Study session course" value={courseId} onChange={(event) => selectCourse(event.target.value)}>{requestedCourseIsUnavailable ? <option value="" disabled>Choose a course</option> : null}{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select><ChevronDown size={14} aria-hidden="true" /></span></label> : undefined}
    >
      {core.status === "demo" ? <CollectionEmptyState
        icon={<History size={20} />}
        label="Recent learning"
        count="0 saved"
        title="Your learning history starts here"
        description="Ask a question or begin focused study to save your first learning record."
        action={<Button className="primary" onClick={() => navigate("/")}>Start new learning</Button>}
      /> : null}

      {serviceUnavailable ? <CollectionEmptyState
        icon={<History size={20} />}
        label="Learning history"
        count="Unavailable"
        title="Learning history is unavailable"
        description="Keen cannot reach the local learning service right now. Your saved questions and sessions were not changed."
        action={<Button className="primary" onClick={() => { void core.retry(); }}>Retry</Button>}
      /> : null}

      {bothEmpty ? <section className="history-start-state" aria-labelledby="history-start-title">
        <span className="history-start-icon" aria-hidden="true"><History size={20} /></span>
        <div>
          <h2 id="history-start-title">{courses.length === 0 ? "Add material to begin" : "No saved history yet"}</h2>
          <p>{courses.length === 0
            ? "Create a course and add source material before starting a source-grounded learning session."
            : "Ask a question or start focused study from New learning; saved questions and sessions will appear here."}</p>
        </div>
        {courses.length === 0
          ? <Button type="button" className="primary" onClick={() => navigate("/knowledge")}>Open Knowledge Base</Button>
          : <Button type="button" className="primary" onClick={() => navigate("/?mode=ask")}>New learning</Button>}
      </section> : null}

      {core.status !== "demo" && !bothEmpty && !serviceUnavailable ? <div className="history-browser">
      <section className="history-section history-questions" aria-labelledby="questions-title">
        <div className="history-list-head"><div><h2 id="questions-title">Questions</h2><span>Source-scoped answers saved from Ask</span></div>{questions.length > 0 ? <small>{questions.length} saved{questionsQuery.hasNextPage ? " · more available" : ""}</small> : null}</div>
        {starting ? <HistoryLoading label="Loading saved questions" /> : null}
        {core.status === "healthy" && questionsQuery.isPending ? <HistoryLoading label="Loading saved questions" /> : null}
        {core.status === "healthy" && questionsQuery.isError ? <section className="history-state history-state-compact" role="alert"><MessageSquareText size={19} aria-hidden="true" /><div><strong>Questions could not be loaded</strong><p>Study sessions below are still available. Retry this read-only request.</p><Button onClick={() => { void questionsQuery.refetch(); }}>Retry questions</Button></div></section> : null}
        {core.status === "healthy" && questionsQuery.isSuccess && questions.length === 0 ? <section className="history-state history-state-compact"><MessageSquareText size={19} aria-hidden="true" /><div><strong>No saved questions yet</strong><p>Ask a question with an indexed source scope and it will appear here.</p><Button className="primary" onClick={() => navigate("/?mode=ask")}>New learning</Button></div></section> : null}
        {core.status === "healthy" && questions.length > 0 ? <div className="history-list">
          {questions.map((conversation) => {
            const presentation = conversation.answerStatus ? questionPresentation[conversation.answerStatus] : { label: "Ready", action: "Open record", note: "Open this saved question to continue." };
            const scopeLabel = conversation.sourceScope.kind === "all_indexed" ? "All indexed sources" : conversation.courseTitle ?? "Course unavailable";
            return <article className="history-row" key={conversation.id}>
              <button type="button" className="history-row-main" onClick={() => navigate(`/conversation/${encodeURIComponent(conversation.id)}`)} aria-label={`${presentation.action}: ${conversation.title}`}>
                <div className="history-row-title"><strong title={conversation.title}>{conversation.title}</strong><Badge tone={presentation.tone}>{presentation.label}</Badge></div>
                {conversation.lastMessagePreview ? <p title={conversation.lastMessagePreview}>{conversation.lastMessagePreview}</p> : null}
                {conversation.answerStatus !== "completed" ? <p className="history-row-result">{presentation.note}</p> : null}
                <div className="history-row-footer"><div className="history-row-meta"><span title={scopeLabel}>{scopeLabel}</span><time dateTime={conversation.updatedAt}><Clock3 size={13} aria-hidden="true" />Updated {updatedLabel(conversation.updatedAt)}</time><span>{conversation.messageCount} {conversation.messageCount === 1 ? "message" : "messages"}</span></div><span className="history-row-action">{presentation.action}<ArrowRight size={14} aria-hidden="true" /></span></div>
              </button>
            </article>;
          })}
          {questionsQuery.hasNextPage ? <div className="history-more"><Button variant="secondary" disabled={questionsQuery.isFetchingNextPage} onClick={() => { void questionsQuery.fetchNextPage(); }}>{questionsQuery.isFetchingNextPage ? "Loading…" : "Load more questions"}</Button></div> : null}
        </div> : null}
      </section>

      <section className="history-section history-sessions" aria-labelledby="study-sessions-title">
        <div className="history-list-head"><div><h2 id="study-sessions-title">Study sessions</h2><span>{selectedCourse?.title ?? "Guided learning by course"}</span></div>{sessions.length > 0 ? <small>{sessions.length} saved</small> : null}</div>
        {starting || (core.status === "healthy" && core.demoStatePending) ? <HistoryLoading label="Loading study sessions" /> : null}
        {core.status === "healthy" && core.demoStateError ? <section className="history-state history-state-compact" role="alert"><History size={19} aria-hidden="true" /><div><strong>Study courses could not be loaded</strong><p>Saved questions above are still available. Retry the course read.</p><Button onClick={() => { void core.retry(); }}>Retry courses</Button></div></section> : null}
        {core.status === "healthy" && !core.demoStatePending && !core.demoStateError && courses.length === 0 ? <section className="history-state history-state-compact"><BookOpenText size={19} aria-hidden="true" /><div><strong>No course to show yet</strong><p>Add learning material to a course before starting a guided session.</p><Button onClick={() => navigate("/knowledge")}>Open Knowledge Base</Button></div></section> : null}
        {core.status === "healthy" && !core.demoStatePending && !core.demoStateError && courses.length > 0 && requestedCourseIsUnavailable ? <section className="history-state history-state-compact" role="status"><History size={19} aria-hidden="true" /><div><strong>Selected course is unavailable</strong><p>Choose an available course. Keen did not substitute sessions from another course.</p></div></section> : null}
        {core.status === "healthy" && courseId && sessionsQuery.isPending ? <HistoryLoading label="Loading study sessions" /> : null}
        {core.status === "healthy" && sessionsQuery.isError ? <section className="history-state history-state-compact" role="alert"><History size={19} aria-hidden="true" /><div><strong>Study sessions could not be loaded</strong><p>Saved questions above are still available. Retry this read-only request.</p><Button onClick={() => { void sessionsQuery.refetch(); }}>Retry sessions</Button></div></section> : null}
        {core.status === "healthy" && sessionsQuery.isSuccess && sessions.length === 0 ? <section className="history-state history-state-compact"><History size={19} aria-hidden="true" /><div><strong>No study sessions yet</strong><p>Start focused study with {selectedCourse?.title ?? "this course"}; the saved session will appear here.</p><Button onClick={() => navigate(`/?mode=study&course_id=${encodeURIComponent(courseId)}`)}>Start study</Button></div></section> : null}
        {core.status === "healthy" && sessions.length > 0 ? <div className="history-list">{sessions.map((session) => {
          const presentation = sessionPresentation[session.status];
          const title = displayLearningTitle(session.title);
          const goalRepeatsTitle = learningTitlesMatch(session.title, session.goal);
          return <article className="history-row" key={session.id}><button type="button" className="history-row-main" onClick={() => navigate(`/deep-learn/${encodeURIComponent(session.id)}?course_id=${encodeURIComponent(session.course_id)}`)} aria-label={`${presentation.action}: ${title}`}>
            <div className="history-row-title"><strong title={title}>{title}</strong><Badge tone={sessionTone(session.status)}>{presentation.label}</Badge></div>
            {!goalRepeatsTitle ? <p title={session.goal}>{session.goal}</p> : null}
            <div className="history-row-steps"><span><small>Current</small>{presentation.current}</span><span><small>Next</small>{presentation.next}</span></div>
            {presentation.terminalNote ? <p className="history-row-result">{presentation.terminalNote}</p> : null}
            <div className="history-row-footer"><div className="history-row-meta"><span>{selectedCourse?.title ?? "Course unavailable"}</span><time dateTime={session.updated_at}><Clock3 size={13} aria-hidden="true" />{updatedLabel(session.updated_at)}</time><span>{session.estimated_minutes} min</span>{presentation.terminalNote ? null : <span className="history-progress-value">{Math.round(session.progress * 100)}%</span>}</div><span className="history-row-action">{presentation.action}<ArrowRight size={14} aria-hidden="true" /></span></div>
          </button></article>;
        })}</div> : null}
      </section>
      </div> : null}

      {core.status === "healthy" && courseId ? <CurrentMastery courseId={courseId} /> : null}
    </Page>
  );
}
