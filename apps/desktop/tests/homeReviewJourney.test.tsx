import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import type {
  AutonomousStudySession,
  LearningActionCandidate,
  LearningFeedTask,
  LearningSnapshot,
  ReviewAttemptResponse,
  ReviewItem,
} from "@keen/api-client";
import { HomePage } from "../src/features/home/HomePage";
import { LearningFeedPage } from "../src/features/feed/LearningFeedPage";
import { FlashcardsPage } from "../src/features/flashcards/FlashcardsPage";

const core = vi.hoisted(() => ({ current: null as never }));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => core.current,
  isLearningCoreStarting: (status: string) => status === "starting",
}));

const time = "2026-07-24T08:00:00+00:00";
const review: ReviewItem = {
  id: "review-1",
  course_id: "course-1",
  course_title: "Calculus",
  concept_id: "concept-1",
  concept_name: "Limits",
  item_type: "free_recall",
  prompt: "Explain the formal definition of a limit.",
  expected_answer: "For every epsilon there is a delta.",
  source_type: "study_session",
  source_id: "session-1",
  due_at: time,
  state: "learning",
  scheduler: "fsrs",
  scheduler_version: "fsrs-6.3.1-keen-v1",
  revision: 0,
  repetitions: 0,
  lapses: 0,
};
const reviewTask: LearningFeedTask = {
  id: "task-review-1",
  course_id: review.course_id,
  concept_id: review.concept_id,
  title: "Review limits",
  reason: "A scheduled review is due.",
  due_at: time,
  estimated_minutes: 5,
  status: "upcoming",
  source_type: "review",
  source_id: review.id,
  priority_score: 1,
  recommended_reason: "Complete the exact due review.",
  scheduled_for: time,
  created_at: time,
  updated_at: time,
  completed_at: null,
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current test route">{location.pathname}{location.search}</output>;
}

describe("Home due Review continuity", () => {
  it("passes exact task context and restores the task only under Completed after rating", async () => {
    const user = userEvent.setup();
    let reviewCompleted = false;
    const completedTask: LearningFeedTask = {
      ...reviewTask,
      status: "completed",
      updated_at: "2026-07-24T08:05:00+00:00",
      completed_at: "2026-07-24T08:05:00+00:00",
    };
    const snapshot = (): LearningSnapshot => ({
      course_id: "course-1",
      as_of: time,
      available_minutes: 20,
      due_review_count: reviewCompleted ? 0 : 1,
      incomplete_session_count: 0,
      mastery_gap_count: 0,
      misconception_count: 0,
      pending_tasks: reviewCompleted ? [] : [reviewTask],
      completed_tasks: reviewCompleted ? [completedTask] : [],
      candidates: [],
    });
    const listDueReviews = vi.fn(async () => ({ as_of: time, items: reviewCompleted ? [] : [review] }));
    const learningSnapshot = vi.fn(async () => snapshot());
    const attempt: ReviewAttemptResponse = {
      outcome: "applied",
      review_item_id: review.id,
      rating: "good",
      response: "",
      reviewed_at: "2026-07-24T08:05:00+00:00",
      schedule: {
        due_at: "2026-07-26T08:05:00+00:00",
        last_reviewed_at: "2026-07-24T08:05:00+00:00",
        state: "learning",
        scheduler: "fsrs",
        scheduler_version: "fsrs-6.3.1-keen-v1",
        revision: 1,
        repetitions: 1,
        lapses: 0,
      },
    };
    const recordReviewAttempt = vi.fn(async () => {
      reviewCompleted = true;
      return attempt;
    });
    const client = {
      listDocuments: vi.fn(async () => []),
      learningSnapshot,
      listDueReviews,
      listStudySessions: vi.fn(async () => ({ course_id: "course-1", sessions: [] })),
      recordReviewAttempt,
      createAutonomousRecommendation: vi.fn(),
    };
    core.current = {
      status: "healthy",
      client,
      connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }], tasks: [], mastery: [] },
      demoStatePending: false,
      demoStateError: null,
      retryError: null,
      retry: vi.fn(),
    } as never;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <QueryClientProvider client={queryClient}>
          <Routes>
            <Route path="/" element={<><HomePage /><LocationProbe /></>} />
            <Route path="/review" element={<><FlashcardsPage /><LocationProbe /></>} />
            <Route path="/feed" element={<><LearningFeedPage /><LocationProbe /></>} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: "Review now" }));
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/review?course_id=course-1&review_item_id=review-1&task=task-review-1");
    await user.click(await screen.findByRole("button", { name: /Reveal expected answer/i }));
    await user.click(screen.getByRole("button", { name: /Good/i }));

    expect(recordReviewAttempt).toHaveBeenCalledWith(review.id, expect.objectContaining({
      taskContext: { courseId: "course-1", taskId: "task-review-1" },
    }), expect.anything());
    expect(await screen.findByRole("heading", { name: "This task no longer needs review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to Learning Feed" }));

    expect(await screen.findByRole("button", { name: "Completed" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("heading", { name: reviewTask.title })).toBeInTheDocument();
    expect(screen.getByText(/saved task is read-only/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Upcoming" }));
    expect(await screen.findByText("No upcoming tasks")).toBeInTheDocument();
    await waitFor(() => expect(learningSnapshot).toHaveBeenLastCalledWith(
      { courseId: "course-1", availableMinutes: 20 },
      expect.anything(),
    ));
  });

  it("resumes an incomplete saved session even when it has no task", async () => {
    const user = userEvent.setup();
    const candidate: LearningActionCandidate = {
      id: "session:session-orphan",
      action: "resume_study_session",
      target_type: "study_session",
      target_id: "session-orphan",
      concept_id: null,
      component: "study_sessions",
      priority_tier: 2,
      estimated_minutes: 20,
      fits_available_minutes: true,
      priority_score: 0.9,
      priority_unclamped_score: 0.9,
      priority_algorithm_version: "feed-priority-v1",
      priority_components: [],
      priority_explanation: [],
      why: "Study session is incomplete.",
    };
    const snapshot: LearningSnapshot = {
      course_id: "course-1",
      as_of: time,
      available_minutes: 20,
      due_review_count: 0,
      incomplete_session_count: 1,
      mastery_gap_count: 0,
      misconception_count: 0,
      pending_tasks: [],
      completed_tasks: [],
      candidates: [candidate],
    };
    const session: AutonomousStudySession = {
      id: "session-orphan",
      course_id: "course-1",
      originating_task_id: null,
      title: "Limits",
      mode: "study",
      goal: "Explain limits without notes",
      estimated_minutes: 20,
      status: "paused",
      resume_from_status: "practicing",
      progress: 0.5,
      revision: 3,
      created_at: time,
      updated_at: time,
      started_at: time,
    };
    let savedSession = session;
    const client = {
      listDocuments: vi.fn(async () => []),
      learningSnapshot: vi.fn(async () => snapshot),
      listDueReviews: vi.fn(async () => ({ as_of: time, items: [] })),
      listStudySessions: vi.fn(async () => ({ course_id: "course-1", sessions: [savedSession] })),
      createAutonomousRecommendation: vi.fn(),
    };
    core.current = {
      status: "healthy",
      client,
      connectionGeneration: 1,
      demoState: { courses: [{ id: "course-1", title: "Calculus" }], tasks: [], mastery: [] },
      demoStatePending: false,
      demoStateError: null,
      retryError: null,
      retry: vi.fn(),
    } as never;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const firstView = render(
      <MemoryRouter initialEntries={["/"]}>
        <QueryClientProvider client={queryClient}>
          <Routes>
            <Route path="/" element={<><HomePage /><LocationProbe /></>} />
            <Route path="/deep-learn/:sessionId" element={<LocationProbe />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Explain limits without notes")).toBeInTheDocument();
    expect(screen.getByText("50% complete · Resume session")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume session" }));
    expect(screen.getByLabelText("Current test route")).toHaveTextContent(
      "/deep-learn/session-orphan?course_id=course-1",
    );
    expect(client.createAutonomousRecommendation).not.toHaveBeenCalled();

    firstView.unmount();
    savedSession = {
      ...session,
      status: "studying",
      resume_from_status: null,
      progress: 0.75,
      revision: 4,
      updated_at: "2026-07-24T08:10:00+00:00",
    };
    const restartedQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <QueryClientProvider client={restartedQueryClient}>
          <Routes>
            <Route path="/" element={<HomePage />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("75% complete · Continue reading")).toBeInTheDocument();
    expect(client.listStudySessions).toHaveBeenCalledTimes(2);
  });
});
