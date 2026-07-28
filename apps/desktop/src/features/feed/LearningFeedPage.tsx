import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle, BookOpenText, CalendarDays, Check, Filter, ListPlus, LoaderCircle, Square,
} from "lucide-react";
import { Button, Card, EmptyState } from "@keen/ui";
import type { AutonomousStudySession, LearningFeedTask } from "@keen/api-client";
import type { TaskStatus } from "@keen/domain";
import { Segmented } from "../../components/Page";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { useAppStore } from "../../state/appStore";
import { mapDemoStateTasks } from "./liveTasks";
import { useAutonomousLearningFeed } from "./useAutonomousLearningFeed";
import { LearningCalendar, type CalendarLearningItem } from "./LearningCalendar";
import { TaskDetailPanel, type TaskDetailSelection } from "./TaskDetailPanel";
import { FeedContextPanel } from "./FeedContextPanel";
import {
  FeedDataError,
  FeedRestoreSkeleton,
  FeedServiceState,
  LiveTaskCard,
  RecommendationNotice,
  TaskCard,
  feedSections,
  taskStatusLabels,
  type FeedSection,
} from "./FeedTaskList";
import { displayLearningTitle } from "../learningPresentation";

function sameLocalDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}

export function LearningFeedPage() {
  const { tasks: demoTasks, updateTask } = useAppStore();
  const core = useLearningCore();
  const [searchParams, setSearchParams] = useSearchParams();
  const isDemo = core.status === "demo";
  const visualTest = searchParams.get("visualTest") === "true" && (isDemo || core.visualFixture);
  const visualSelectedTaskId = visualTest ? searchParams.get("selectedTask") : null;
  const requestedTaskId = searchParams.get("task");
  const requestedCourseId = searchParams.get("course_id");
  const requestedStatus = searchParams.get("status");
  const [status, setStatus] = useState<FeedSection>(
    requestedStatus && feedSections.includes(requestedStatus as FeedSection)
      ? requestedStatus as FeedSection
      : "today",
  );
  const [course, setCourse] = useState("All courses");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(requestedTaskId ?? visualSelectedTaskId);
  const [detailDismissed, setDetailDismissed] = useState(false);
  const [contextView, setContextView] = useState<"tasks" | "calendar">("tasks");
  const [requestedLiveCourseId, setRequestedLiveCourseId] = useState<string | null>(null);
  const navigate = useNavigate();
  const startControllerRef = useRef<AbortController | null>(null);
  const calendarReturnTargetRef = useRef("feed-open-calendar-shortcut");
  const activeStartTaskRef = useRef<LearningFeedTask | null>(null);
  const startRequestRef = useRef(0);
  const [startingTaskId, setStartingTaskId] = useState<string | null>(null);
  const [startNotice, setStartNotice] = useState<{ tone: "blocked" | "unknown" | "cancelled" | "unavailable"; message: string } | null>(null);
  const [recoverableStartTask, setRecoverableStartTask] = useState<LearningFeedTask | null>(null);
  const [startScope, setStartScope] = useState<string | null>(null);
  const liveCourses = useMemo(() => core.demoState?.courses ?? [], [core.demoState?.courses]);
  const requestedCourseIsValid = requestedCourseId !== null && liveCourses.some((item) => item.id === requestedCourseId);
  const localCourseIsValid = requestedLiveCourseId !== null && liveCourses.some((item) => item.id === requestedLiveCourseId);
  const liveCourseId = requestedCourseId !== null
    ? requestedCourseIsValid ? requestedCourseId : null
    : localCourseIsValid ? requestedLiveCourseId : liveCourses[0]?.id ?? null;
  const requestedCourseIsUnavailable = requestedCourseId !== null && !requestedCourseIsValid;
  const liveFeed = useAutonomousLearningFeed({
    client: core.client,
    courseId: liveCourseId,
    enabled: !isDemo && core.status === "healthy" && !core.demoStateError && core.demoState !== undefined,
    connectionGeneration: core.connectionGeneration,
  });
  const startScopeKey = `${core.connectionGeneration}:${liveCourseId ?? ""}`;
  const currentStartScopeRef = useRef(startScopeKey);
  useLayoutEffect(() => {
    currentStartScopeRef.current = startScopeKey;
  }, [startScopeKey]);
  const visibleStartingTaskId = startScope === startScopeKey ? startingTaskId : null;
  const visibleStartNotice = startScope === startScopeKey ? startNotice : null;
  const visibleRecoverableStartTask = startScope === startScopeKey ? recoverableStartTask : null;
  useEffect(() => {
    return () => {
      startRequestRef.current += 1;
      startControllerRef.current?.abort();
      startControllerRef.current = null;
      activeStartTaskRef.current = null;
    };
  }, [core.client, core.connectionGeneration, liveCourseId]);
  const tasks = useMemo(() => isDemo ? demoTasks : core.demoState ? mapDemoStateTasks(core.demoState) : [], [core.demoState, demoTasks, isDemo]);
  const filtered = useMemo(() => tasks.filter((task) => {
    const matchesSection = status === "today"
      ? task.status === "today" || task.status === "overdue"
      : task.status === status;
    return matchesSection && (course === "All courses" || task.course === course);
  }), [course, status, tasks]);
  const courses = ["All courses", ...Array.from(new Set(tasks.map((task) => task.course)))];
  const liveCourseTitle = liveCourses.find((item) => item.id === liveCourseId)?.title ?? "Current course";
  const filteredLiveTasks = useMemo(() => {
    if (!liveFeed.snapshot) return [];
    if (status === "completed") return liveFeed.snapshot.completed_tasks;
    const asOf = new Date(liveFeed.snapshot.as_of);
    return liveFeed.snapshot.pending_tasks.filter((task) => {
      const due = new Date(task.due_at);
      if (Number.isNaN(due.getTime()) || Number.isNaN(asOf.getTime())) return false;
      if (status === "today") return task.status === "overdue" || sameLocalDay(due, asOf);
      return task.status !== "overdue" && !sameLocalDay(due, asOf);
    });
  }, [liveFeed.snapshot, status]);
  const showBaselineFeed = isDemo;
  const firstVisibleTaskId = showBaselineFeed ? filtered[0]?.id : filteredLiveTasks[0]?.id;
  const autoSelectionAllowed = contextView === "tasks"
    && !detailDismissed
    && !(visualTest && visualSelectedTaskId === null);
  const effectiveSelectedTaskId = selectedTaskId ?? (autoSelectionAllowed ? firstVisibleTaskId ?? null : null);
  const selectedLiveTaskForProgress = useMemo(() => {
    if (!effectiveSelectedTaskId) return null;
    return [
      ...(liveFeed.snapshot?.pending_tasks ?? []),
      ...(liveFeed.snapshot?.completed_tasks ?? []),
    ].find((task) => task.id === effectiveSelectedTaskId) ?? null;
  }, [
    effectiveSelectedTaskId,
    liveFeed.snapshot?.completed_tasks,
    liveFeed.snapshot?.pending_tasks,
  ]);
  const selectedSessionQuery = useQuery({
    queryKey: ["learning-core", "study-session-history", core.connectionGeneration, liveCourseId],
    queryFn: ({ signal }) => {
      if (!core.client || !liveCourseId) {
        throw new Error("A course is required before checking task progress.");
      }
      return core.client.listStudySessions(liveCourseId, { signal });
    },
    enabled: !isDemo
      && core.status === "healthy"
      && core.client !== null
      && liveCourseId !== null
      && selectedLiveTaskForProgress !== null
      && selectedLiveTaskForProgress.status !== "completed"
      && selectedLiveTaskForProgress.source_type !== "review",
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const selectedStudySession = useMemo<AutonomousStudySession | null>(() => {
    if (!selectedLiveTaskForProgress) return null;
    return [...(selectedSessionQuery.data?.sessions ?? [])]
      .filter((session) => session.originating_task_id === selectedLiveTaskForProgress.id)
      .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))[0] ?? null;
  }, [selectedLiveTaskForProgress, selectedSessionQuery.data?.sessions]);
  const retry = () => { void core.retry(); };

  const selectLiveCourse = (courseId: string) => {
    setRequestedLiveCourseId(courseId);
    setSelectedTaskId(null);
    setDetailDismissed(false);
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.set("course_id", courseId);
    setSearchParams(nextSearchParams, { replace: true });
  };

  const selectCalendarTask = (item: CalendarLearningItem) => {
    setContextView("tasks");
    setSelectedTaskId(item.id);
    setDetailDismissed(false);
    if (isDemo) {
      const task = tasks.find((candidate) => candidate.id === item.id);
      if (task) {
        setStatus(task.status === "overdue" ? "today" : task.status);
        if (course !== "All courses" && course !== task.course) setCourse("All courses");
      }
    }
  };

  useEffect(() => {
    if (!effectiveSelectedTaskId || effectiveSelectedTaskId === visualSelectedTaskId) return;
    const timeout = window.setTimeout(() => {
      const task = document.getElementById(`feed-task-${effectiveSelectedTaskId}`);
      const scroller = task?.closest<HTMLElement>(".feed-task-scroll");
      if (!task || !scroller) return;
      const taskRect = task.getBoundingClientRect();
      const scrollerRect = scroller.getBoundingClientRect();
      if (taskRect.top < scrollerRect.top) scroller.scrollBy({ top: taskRect.top - scrollerRect.top });
      else if (taskRect.bottom > scrollerRect.bottom) scroller.scrollBy({ top: taskRect.bottom - scrollerRect.bottom });
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [effectiveSelectedTaskId, filtered, liveFeed.snapshot?.completed_tasks, liveFeed.snapshot?.pending_tasks, visualSelectedTaskId]);

  const selectSection = (nextStatus: FeedSection) => {
    setStatus(nextStatus);
    setSelectedTaskId(null);
    setDetailDismissed(false);
  };
  const selectTask = (taskId: string) => {
    if (effectiveSelectedTaskId === taskId) {
      document.getElementById("task-detail-title")?.focus({ preventScroll: true });
    }
    setContextView("tasks");
    setSelectedTaskId(taskId);
    setDetailDismissed(false);
  };

  const cancelStart = () => {
    if (!startControllerRef.current) return;
    startControllerRef.current.abort();
    startControllerRef.current = null;
    startRequestRef.current += 1;
    setRecoverableStartTask(activeStartTaskRef.current);
    activeStartTaskRef.current = null;
    setStartingTaskId(null);
    setStartScope(startScopeKey);
    setStartNotice({ tone: "cancelled", message: "Start request cancelled, but the session may already be saved. Recover this same task before starting another one." });
  };
  const startTask = async (task: LearningFeedTask, recovery = false) => {
    if (!core.client || !liveCourseId || startControllerRef.current || (!recovery && visibleRecoverableStartTask !== null)) return;
    const controller = new AbortController();
    const request = startRequestRef.current + 1;
    startRequestRef.current = request;
    startControllerRef.current = controller;
    activeStartTaskRef.current = task;
    setStartingTaskId(task.id);
    setStartScope(startScopeKey);
    setStartNotice(null);
    setRecoverableStartTask(null);
    try {
      const result = await core.client.startAutonomousStudySession({ course_id: liveCourseId, task_id: task.id }, { signal: controller.signal });
      if (controller.signal.aborted || startRequestRef.current !== request) return;
      if (result.outcome === "blocked") {
        setRecoverableStartTask(null);
        setStartNotice({ tone: "blocked", message: result.recovery_action ?? "This local task cannot be started. Refresh the learning feed for a recovery action." });
        return;
      }
      if (!result.session) {
        setRecoverableStartTask(task);
        setStartNotice({ tone: "unknown", message: "Keen could not confirm the local study session. Recover this same task before starting another one." });
        return;
      }
      setRecoverableStartTask(null);
      navigate(`/deep-learn/${encodeURIComponent(result.session.id)}?course_id=${encodeURIComponent(liveCourseId)}`);
    } catch (error) {
      if (startRequestRef.current !== request || currentStartScopeRef.current !== startScopeKey) return;
      if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
        setRecoverableStartTask(task);
        setStartNotice({ tone: "cancelled", message: "Start request cancelled, but the session may already be saved. Recover this same task before starting another one." });
      } else if (error instanceof Error && "status" in error && error.status === 503) {
        setRecoverableStartTask(task);
        setStartNotice({ tone: "unavailable", message: "The local study service is unavailable and the session may already be saved. Restore it, then recover this same task." });
      } else {
        setRecoverableStartTask(task);
        setStartNotice({ tone: "unknown", message: "Keen could not confirm whether a local study session was saved. Recover this same task before starting another one." });
      }
    } finally {
      if (startControllerRef.current === controller) startControllerRef.current = null;
      if (activeStartTaskRef.current === task) activeStartTaskRef.current = null;
      if (startRequestRef.current === request) setStartingTaskId(null);
    }
  };
  const reconcileStart = async () => {
    const scope = startScopeKey;
    const request = startRequestRef.current;
    const refreshed = await liveFeed.refetchSnapshot();
    if (refreshed.isSuccess && currentStartScopeRef.current === scope && startRequestRef.current === request) {
      setStartScope(startScopeKey);
      setStartNotice(null);
    }
  };

  const calendarDate = useMemo(
    () => visualTest ? new Date(2026, 6, 19, 12) : new Date(),
    [visualTest],
  );
  const calendarItems = useMemo<CalendarLearningItem[]>(() => {
    if (isDemo) {
      const offsets: Record<TaskStatus, number> = { today: 0, upcoming: 1, overdue: -1, completed: -4 };
      return tasks.map((task, index) => {
        const offset = offsets[task.status] + (task.status === "today" ? index : 0);
        return {
          id: task.id,
          title: displayLearningTitle(task.title),
          date: new Date(calendarDate.getFullYear(), calendarDate.getMonth(), calendarDate.getDate() + offset),
          tone: task.status === "completed" ? "complete" : task.status === "overdue" ? "overdue" : "active",
        };
      });
    }
    return (liveFeed.snapshot?.pending_tasks ?? []).flatMap((task) => {
      const date = new Date(task.due_at);
      if (Number.isNaN(date.getTime())) return [];
      return [{ id: task.id, title: displayLearningTitle(task.title), date, tone: task.status === "overdue" ? "overdue" as const : "active" as const }];
    });
  }, [calendarDate, isDemo, liveFeed.snapshot?.pending_tasks, tasks]);

  const selectedDetail = useMemo<TaskDetailSelection | null>(() => {
    if (!effectiveSelectedTaskId) return null;
    const liveTask = [...(liveFeed.snapshot?.pending_tasks ?? []), ...(liveFeed.snapshot?.completed_tasks ?? [])].find((task) => task.id === effectiveSelectedTaskId);
    if (liveTask) {
      return {
        kind: "live",
        task: liveTask,
        candidate: liveTask.id === liveFeed.recommendation.result?.task?.id ? liveFeed.recommendation.result.candidate : null,
      };
    }
    if (!isDemo) return null;
    const baselineTask = tasks.find((task) => task.id === effectiveSelectedTaskId);
    if (!baselineTask) return null;
    return { kind: "demo", task: baselineTask };
  }, [effectiveSelectedTaskId, isDemo, liveFeed.recommendation.result, liveFeed.snapshot?.completed_tasks, liveFeed.snapshot?.pending_tasks, tasks]);
  const visibleSelectedDetail = !isDemo && liveFeed.snapshotPending ? null : selectedDetail;

  const feedActionContextAvailable = !isDemo
    && core.status === "healthy"
    && core.demoState !== undefined
    && !core.demoStateError
    && liveCourses.length > 0
    && liveFeed.snapshot != null;
  const feedAction = !feedActionContextAvailable
    ? null
    : liveFeed.recommendation.pending
      ? <Button onClick={liveFeed.cancelRecommendation}><Square size={15} />Cancel recommendation</Button>
      : <Button className="primary" disabled={liveCourseId === null || core.status !== "healthy" || liveFeed.snapshotPending || liveFeed.snapshotError !== null || liveFeed.recommendation.error !== null || liveFeed.recommendation.cancelled} onClick={() => { void liveFeed.createRecommendation(); }}><ListPlus size={15} />Find next task</Button>;
  const showCourseOnboarding = !isDemo
    && core.status === "healthy"
    && core.demoState !== undefined
    && !core.demoStatePending
    && !core.demoStateError
    && liveCourses.length === 0;

  const closeTaskDetail = () => {
    const taskId = effectiveSelectedTaskId;
    setSelectedTaskId(null);
    setDetailDismissed(true);
    setContextView("tasks");
    if (!taskId) return;
    window.requestAnimationFrame(() => {
      document.getElementById(`feed-task-${taskId}`)?.focus();
    });
  };
  const openCalendar = (returnTargetId: string) => {
    calendarReturnTargetRef.current = returnTargetId;
    setContextView("calendar");
  };
  const closeCalendar = () => {
    setContextView("tasks");
    window.requestAnimationFrame(() => {
      document.getElementById(calendarReturnTargetRef.current)?.focus();
    });
  };

  if (showCourseOnboarding) {
    return (
      <main className="feed-onboarding-page">
        <section className="feed-onboarding-empty" aria-labelledby="feed-onboarding-title">
          <span className="feed-onboarding-icon" aria-hidden="true"><BookOpenText size={22} /></span>
          <p className="eyebrow">Learning Feed</p>
          <h1 id="feed-onboarding-title">Build your first learning queue</h1>
          <p className="feed-onboarding-lead">Add course material, then start a learning request from Home. Study and Review work will return here as a clear task list.</p>
          <ol className="feed-onboarding-steps">
            <li><span>1</span><div><strong>Add a course</strong><small>Keep related sources and learning work in one scope.</small></div></li>
            <li><span>2</span><div><strong>Import a source</strong><small>Wait until local indexing confirms the material is ready.</small></div></li>
            <li><span>3</span><div><strong>Start learning</strong><small>Continue scheduled Study and Review tasks from this page.</small></div></li>
          </ol>
          <Button className="primary" onClick={() => navigate("/knowledge")}>Open Knowledge Base</Button>
        </section>
      </main>
    );
  }

  return (
    <div className={`learning-feed-workspace ${visibleSelectedDetail ? "has-detail" : contextView === "calendar" ? "has-calendar" : "has-context"}`}>
      <h1 className="visually-hidden">Learning Feed</h1>
      <section className="feed-task-pane" aria-label="Learning tasks">
        <div className="feed-pane-heading"><h2>Tasks</h2><div className="feed-pane-actions">{feedAction}<Button id="feed-open-calendar-shortcut" className="feed-calendar-shortcut" aria-label="Open calendar" onClick={() => openCalendar("feed-open-calendar-shortcut")}><CalendarDays size={14} aria-hidden="true" />Calendar</Button></div></div>
        <div className="feed-task-scroll">
      {!isDemo && isLearningCoreStarting(core.status) && <FeedRestoreSkeleton />}
      {!isDemo && !isLearningCoreStarting(core.status) && core.status !== "healthy" && <FeedServiceState status={core.status} errorKind={core.errorKind} retryError={core.retryError} onRetry={retry} />}
      {!isDemo && core.status === "healthy" && core.demoStatePending && <FeedRestoreSkeleton />}
      {!isDemo && core.status === "healthy" && core.demoStateError && <FeedDataError onRetry={retry} />}
      {!isDemo && core.status === "healthy" && core.demoState && !core.demoStateError && liveCourses.length > 0 && <>
        <div className="feed-controls"><Segmented value={status} options={feedSections} onChange={selectSection} /><label className="select-control"><Filter size={14} /><select aria-label="Select course for learning feed" value={liveCourseId ?? ""} onChange={(event) => selectLiveCourse(event.target.value)}>{requestedCourseIsUnavailable ? <option value="" disabled>Choose a course</option> : null}{liveCourses.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label></div>
        {requestedCourseIsUnavailable && <Card className="service-state feed-empty-state" role="status"><AlertCircle size={23} /><div><strong>Selected course is unavailable</strong><p>Choose an available course. Keen did not substitute tasks from another course.</p></div></Card>}
        {liveFeed.snapshotPending && <FeedRestoreSkeleton />}
        {liveFeed.snapshotError && <Card className="service-state" role="alert"><AlertCircle size={23} /><div><strong>Learning queue could not be loaded</strong><p>Retry to reload the tasks for this course.</p></div><Button onClick={() => { void liveFeed.refetchSnapshot(); }}>Retry queue</Button></Card>}
        {visibleStartingTaskId && <Card className="service-state" role="status"><LoaderCircle className="spin" size={23} /><div><strong>Preparing your study session</strong><p>You can cancel while Keen opens this task.</p></div><Button onClick={cancelStart}><Square size={14} />Cancel</Button></Card>}
        {visibleStartNotice && <Card className="service-state" role={visibleStartNotice.tone === "blocked" || visibleStartNotice.tone === "cancelled" ? "status" : "alert"}><AlertCircle size={23} /><div><strong>{visibleStartNotice.tone === "blocked" ? "Task cannot start yet" : visibleStartNotice.tone === "unavailable" ? "Local study service is unavailable" : visibleStartNotice.tone === "cancelled" ? "Start request cancelled" : "Study session could not be confirmed"}</strong><p>{visibleStartNotice.message}</p></div>{visibleRecoverableStartTask ? <Button disabled={core.status !== "healthy"} onClick={() => { void startTask(visibleRecoverableStartTask, true); }}>Recover start</Button> : <Button onClick={() => { void reconcileStart(); }}>Refresh feed</Button>}</Card>}
        {liveFeed.recommendation.cancelled && <Card className="service-state" role="status"><Square size={23} /><div><strong>Recommendation request cancelled</strong><p>Keen ignored the unfinished response. Refresh the feed before retrying if you need to confirm local tasks.</p></div><Button onClick={() => { void liveFeed.reconcileRecommendation(); }}>Refresh feed</Button></Card>}
        {liveFeed.recommendation.error && <Card className="service-state" role="alert"><AlertCircle size={23} /><div><strong>{liveFeed.recommendation.error === "service_unavailable" ? "Local recommendation service is unavailable" : "Recommendation could not be confirmed"}</strong><p>{liveFeed.recommendation.error === "service_unavailable" ? "Keen could not confirm whether a task was saved. Restore the local service and refresh the feed before retrying." : "Keen could not confirm whether a task was saved. Refresh the feed before retrying to avoid duplicates."}</p></div><Button onClick={() => { void liveFeed.reconcileRecommendation(); }}>Refresh feed</Button></Card>}
        {liveFeed.recommendation.result && <RecommendationNotice outcome={liveFeed.recommendation.result.outcome} />}
        {liveFeed.snapshot && !liveFeed.snapshotPending && <div className="timeline">
          {filteredLiveTasks.map((task) => <LiveTaskCard key={task.id} task={task} courseTitle={liveCourseTitle} onSelect={() => selectTask(task.id)} pending={visibleStartingTaskId === task.id} selected={effectiveSelectedTaskId === task.id} section={status} />)}
          {filteredLiveTasks.length === 0 && <Card className="feed-compact-empty"><EmptyState icon={<Check size={24} />} title={`No ${taskStatusLabels[status].toLowerCase()} tasks`} description={liveFeed.snapshot.candidates.length > 0 && status === "today" ? "Use Find next task to add the next available action." : "Choose another section or return when new work is due."} /></Card>}
        </div>}
      </>}
      {showBaselineFeed && <>
        <div className="feed-controls"><Segmented value={status} options={feedSections} onChange={selectSection} /><label className="select-control"><Filter size={14} /><select aria-label="Filter by course" value={course} onChange={(event) => { setCourse(event.target.value); setSelectedTaskId(null); setDetailDismissed(false); }}>{courses.map((item) => <option key={item}>{item}</option>)}</select></label></div>
        <div className="timeline">
          {filtered.map((task) => <TaskCard key={task.id} task={task} onSelect={() => selectTask(task.id)} selected={effectiveSelectedTaskId === task.id} />)}
          {filtered.length === 0 && <Card className="feed-compact-empty"><EmptyState icon={<Check size={24} />} title={`No ${taskStatusLabels[status].toLowerCase()} tasks`} description={course === "All courses" ? "Choose another section or return when new work is due." : `No tasks for ${course} in this section.`} action={course === "All courses" ? undefined : <Button onClick={() => setCourse("All courses")}>Clear filter</Button>} /></Card>}
        </div>
      </>}
        </div>
      </section>
      {visibleSelectedDetail ? <TaskDetailPanel
        selection={visibleSelectedDetail}
        courseTitle={visibleSelectedDetail.kind === "live" ? liveCourseTitle : visibleSelectedDetail.task.course}
        section={status}
        startPending={visibleSelectedDetail.kind === "live" && visibleStartingTaskId === visibleSelectedDetail.task.id}
        startUnavailable={visibleRecoverableStartTask !== null || visibleStartingTaskId !== null || core.status !== "healthy"}
        studySession={visibleSelectedDetail.kind === "live" ? selectedStudySession : null}
        studySessionPending={visibleSelectedDetail.kind === "live" && selectedSessionQuery.isPending}
        studySessionError={visibleSelectedDetail.kind === "live" && selectedSessionQuery.isError}
        onBack={closeTaskDetail}
        onDemoUpdate={(next) => { if (visibleSelectedDetail.kind === "demo") updateTask(visibleSelectedDetail.task.id, next); }}
        onReview={(task) => {
          if (!task.source_id) return;
          const params = new URLSearchParams({ course_id: task.course_id, review_item_id: task.source_id, task: task.id });
          navigate(`/review?${params.toString()}`);
        }}
        onStart={(task) => { void startTask(task); }}
        onViewHistory={() => { if (visibleSelectedDetail.kind === "live") navigate(`/history?course_id=${encodeURIComponent(visibleSelectedDetail.task.course_id)}`); }}
      /> : contextView === "calendar"
        ? <LearningCalendar items={calendarItems} initialDate={calendarDate} selectedItemId={selectedTaskId} onSelectItem={selectCalendarTask} onClose={closeCalendar} />
        : <FeedContextPanel />}
    </div>
  );
}
