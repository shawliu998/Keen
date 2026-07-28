import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { LearningCoreResponseError, type DueReviewListResponse, type ReviewAttemptResponse, type ReviewItem } from "@keen/api-client";
import { FlashcardsPage } from "../src/features/flashcards/FlashcardsPage";

const core = vi.hoisted(() => ({ current: null as never }));
const setInspector = vi.fn();

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => core.current,
  isLearningCoreStarting: (status: string) => status === "starting",
}));
vi.mock("../src/state/appStore", () => ({ useAppStore: () => ({ setInspector }) }));

const item: ReviewItem = {
  id: "review-1",
  course_id: "course-1",
  course_title: "Calculus I",
  concept_id: "concept-1",
  concept_name: "Chain rule",
  item_type: "free_recall",
  prompt: "Explain the chain rule.",
  expected_answer: { accepted_answers: ["Differentiate the outer function, then multiply by the derivative of the inner function."] },
  source_type: "assessment",
  source_id: null,
  due_at: "2026-07-20T08:00:00+00:00",
  state: "new",
  scheduler: "fsrs",
  scheduler_version: "fsrs-6.3.1-keen-v1",
  revision: 0,
  repetitions: 0,
  lapses: 0,
};
const queue: DueReviewListResponse = { as_of: "2026-07-20T09:00:00+00:00", items: [item] };
const emptyQueue: DueReviewListResponse = { ...queue, items: [] };
const completed: ReviewAttemptResponse = {
  outcome: "applied",
  review_item_id: item.id,
  rating: "good",
  response: "Outer derivative times inner derivative.",
  reviewed_at: "2026-07-20T09:01:00+00:00",
  schedule: { due_at: "2026-07-22T09:01:00+00:00", last_reviewed_at: "2026-07-20T09:01:00+00:00", state: "learning", scheduler: "fsrs", scheduler_version: "fsrs-6.3.1-keen-v1", revision: 1, repetitions: 1, lapses: 0 },
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current test route">{location.pathname}{location.search}</output>;
}

function renderPage(client: Record<string, unknown> | null, status = "healthy", connectionGeneration = 1, initialEntry = "/review") {
  core.current = { status, client, connectionGeneration, retry: vi.fn() } as never;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return Object.assign(
    render(<MemoryRouter initialEntries={[initialEntry]}><QueryClientProvider client={queryClient}><Routes><Route path="/review" element={<><FlashcardsPage /><LocationProbe /></>} /><Route path="/feed" element={<><div>Learning Feed destination</div><LocationProbe /></>} /><Route path="/history" element={<div>History destination</div>} /><Route path="/" element={<div>New learning destination</div>} /></Routes></QueryClientProvider></MemoryRouter>),
    { queryClient },
  );
}

async function revealAndRate(user: ReturnType<typeof userEvent.setup>, rating = "Good") {
  await user.click(await screen.findByRole("button", { name: /Reveal expected answer/i }));
  await user.click(screen.getByRole("button", { name: new RegExp(rating, "i") }));
}

describe("FlashcardsPage local review queue", () => {
  beforeEach(() => setInspector.mockClear());

  it("reveals a readable answer, records one rating, and focuses the completed state", async () => {
    const user = userEvent.setup();
    const listDueReviews = vi.fn().mockResolvedValueOnce(queue).mockResolvedValueOnce(emptyQueue);
    const recordReviewAttempt = vi.fn(async () => completed);
    const view = renderPage({ listDueReviews, recordReviewAttempt });
    const invalidate = vi.spyOn(view.queryClient, "invalidateQueries");

    expect(await screen.findByRole("heading", { name: item.prompt })).toBeInTheDocument();
    expect(screen.getByText("Created from assessment")).toBeInTheDocument();
    expect(screen.getByLabelText("Why this review is due")).toHaveTextContent("evidence recorded during your learning session");
    expect(screen.getByLabelText("Why this review is due")).toHaveTextContent("FSRS");
    expect(screen.queryByRole("button", { name: /source/i })).not.toBeInTheDocument();
    expect(screen.queryByText("New")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Good/i })).toBeDisabled();
    await user.type(screen.getByPlaceholderText(/Write what you recalled/i), completed.response);
    await revealAndRate(user);

    expect(recordReviewAttempt).toHaveBeenCalledTimes(1);
    expect(recordReviewAttempt).toHaveBeenCalledWith(item.id, expect.objectContaining({ rating: "good", response: completed.response, expectedRevision: 0, idempotencyKey: expect.stringMatching(/^review-/) }), expect.anything());
    const heading = await screen.findByRole("heading", { name: "Reviews complete" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByText(/Next due Jul 22, 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/FSRS|SQLite|Local review source/i)).not.toBeInTheDocument();
    expect(setInspector).toHaveBeenCalledWith(null);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learning-core", "due-reviews"], refetchType: "all" });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learning-core", "learning-snapshot"], refetchType: "all" });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learning-core", "study-session-history"], refetchType: "all" });
  });

  it("renders a persisted source-cloze prompt as a readable self-review card", async () => {
    const user = userEvent.setup();
    const clozeItem: ReviewItem = {
      ...item,
      prompt: "Fill in the missing term using the source context:\n\nFor a [...] y = f(g(x)), the chain rule gives: y prime = f prime(g(x)) times g prime(x).",
      expected_answer: { accepted_answers: ["composite"] },
    };
    const listDueReviews = vi.fn().mockResolvedValueOnce({ ...queue, items: [clozeItem] }).mockResolvedValueOnce(emptyQueue);
    const recordReviewAttempt = vi.fn(async () => completed);
    const view = renderPage({ listDueReviews, recordReviewAttempt });

    expect(await screen.findByRole("heading", { name: "Complete the missing term" })).toBeInTheDocument();
    expect(screen.getByText(/Recall the missing word or short phrase/)).toBeInTheDocument();
    const question = view.container.querySelector(".practice-question");
    expect(question).toHaveTextContent("For a");
    expect(question).toHaveTextContent("y = f(g(x)), the chain rule gives:");
    expect(question?.querySelector(".practice-blank")).toHaveAttribute("aria-hidden", "true");
    expect(within(question as HTMLElement).getByText("blank")).toHaveClass("visually-hidden");
    expect(screen.getByText("y′ = f′(g(x)) · g′(x).")).toHaveClass("practice-equation");
    expect(screen.queryByText(/\[\.\.\.\]|\bprime\b|\btimes\b/)).not.toBeInTheDocument();

    await revealAndRate(user);
    expect(recordReviewAttempt).toHaveBeenCalledWith(clozeItem.id, expect.objectContaining({ rating: "good", expectedRevision: 0, idempotencyKey: expect.stringMatching(/^review-/) }), expect.anything());
  });

  it("filters by course and prioritizes the exact review item from a Feed task", async () => {
    const otherItem = { ...item, id: "review-other", prompt: "Explain a different concept." };
    const listDueReviews = vi.fn(async () => ({ ...queue, items: [otherItem, item] }));
    renderPage(
      { listDueReviews, recordReviewAttempt: vi.fn() },
      "healthy",
      1,
      "/review?course_id=course-1&review_item_id=review-1&task=task-review-1",
    );

    expect(await screen.findByRole("heading", { name: item.prompt })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: otherItem.prompt })).not.toBeInTheDocument();
    expect(listDueReviews).toHaveBeenCalledWith({ courseId: "course-1", limit: 50 }, expect.anything());
  });

  it("does not substitute another due item and returns to the exact completed Feed task after rating", async () => {
    const user = userEvent.setup();
    const otherItem = { ...item, id: "review-other", prompt: "Explain a different concept." };
    const listDueReviews = vi.fn()
      .mockResolvedValueOnce(queue)
      .mockResolvedValueOnce({ ...queue, items: [otherItem] });
    const recordReviewAttempt = vi.fn(async () => completed);
    const view = renderPage(
      { listDueReviews, recordReviewAttempt },
      "healthy",
      1,
      "/review?course_id=course-1&review_item_id=review-1&task=task-review-1",
    );
    const feedQueryKey = ["learning-core", "learning-snapshot", 1, "course-1", 20] as const;
    view.queryClient.setQueryData(feedQueryKey, { stale: "pending review task" });

    await revealAndRate(user);
    expect(recordReviewAttempt).toHaveBeenCalledWith(item.id, expect.objectContaining({
      taskContext: { courseId: "course-1", taskId: "task-review-1" },
    }), expect.anything());
    expect(await screen.findByRole("heading", { name: "This task no longer needs review" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: otherItem.prompt })).not.toBeInTheDocument();
    expect(screen.getByText(/did not substitute another card or course/i)).toBeInTheDocument();
    expect(view.queryClient.getQueryState(feedQueryKey)?.isInvalidated).toBe(true);
    await user.click(screen.getByRole("button", { name: "Return to Learning Feed" }));
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/feed?status=completed&task=task-review-1&course_id=course-1");
  });

  it.each([
    "/review?course_id=course-1",
    "/review?course_id=course-1&review_item_id=review-1",
    "/review?course_id=course-1&task=task-review-1",
    "/review?review_item_id=review-1&task=task-review-1",
  ])("fails closed for an incomplete Review task handoff: %s", async (entry) => {
    const listDueReviews = vi.fn(async () => queue);
    const recordReviewAttempt = vi.fn();
    renderPage({ listDueReviews, recordReviewAttempt }, "healthy", 1, entry);

    expect(await screen.findByRole("heading", { name: "This review task link is incomplete" })).toBeInTheDocument();
    expect(screen.getByText(/No rating was saved/i)).toBeInTheDocument();
    expect(listDueReviews).not.toHaveBeenCalled();
    expect(recordReviewAttempt).not.toHaveBeenCalled();
  });

  it("keeps a bound Review task closed when the server cannot match its exact task", async () => {
    const user = userEvent.setup();
    const otherItem = { ...item, id: "review-other", prompt: "Explain a different concept." };
    const detail = {
      message: "This saved review task is no longer available.",
      retryable: false,
      recovery: "Return to the Learning Feed and open a current task.",
      documentId: null,
      code: null,
    };
    const recordReviewAttempt = vi.fn(async () => {
      throw new LearningCoreResponseError(404, detail, null);
    });
    renderPage(
      { listDueReviews: vi.fn(async () => ({ ...queue, items: [item, otherItem] })), recordReviewAttempt },
      "healthy",
      1,
      "/review?course_id=course-1&review_item_id=review-1&task=task-review-1",
    );

    await revealAndRate(user);
    expect(await screen.findByRole("heading", { name: "This task no longer needs review" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: otherItem.prompt })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/No rating was saved/i);
    expect(screen.queryByRole("button", { name: /Check this task again/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to Learning Feed" }));
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/feed");
  });

  it("keeps a bound Review task closed for a non-retryable task-context conflict", async () => {
    const user = userEvent.setup();
    const otherItem = { ...item, id: "review-other", prompt: "Explain a different concept." };
    const recordReviewAttempt = vi.fn(async () => {
      throw new LearningCoreResponseError(409, {
        message: "This saved review task no longer matches the due item.",
        retryable: false,
        recovery: "Return to the Learning Feed and open a current task.",
        documentId: null,
        code: "review_task_context_conflict",
      }, null);
    });
    renderPage(
      { listDueReviews: vi.fn(async () => ({ ...queue, items: [item, otherItem] })), recordReviewAttempt },
      "healthy",
      1,
      "/review?course_id=course-1&review_item_id=review-1&task=task-review-1",
    );

    await revealAndRate(user);
    expect(await screen.findByRole("heading", { name: "This task no longer needs review" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("This saved review task no longer matches the due item. No rating was saved.");
    expect(screen.queryByRole("heading", { name: otherItem.prompt })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Good/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Check this task again/i })).not.toBeInTheDocument();
    expect(recordReviewAttempt).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Return to Learning Feed" }));
    expect(screen.getByLabelText("Current test route")).toHaveTextContent("/feed?task=task-review-1&course_id=course-1");
  });

  it("shows the truthful task boundary when the requested item does not match the course", async () => {
    const wrongCourseItem = { ...item, course_id: "course-2", course_title: "Physics" };
    renderPage(
      { listDueReviews: vi.fn(async () => ({ ...queue, items: [wrongCourseItem] })), recordReviewAttempt: vi.fn() },
      "healthy",
      1,
      "/review?course_id=course-1&review_item_id=review-1&task=task-review-1",
    );

    expect(await screen.findByRole("heading", { name: "This task no longer needs review" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: wrongCourseItem.prompt })).not.toBeInTheDocument();
  });

  it("keeps Browser Demo request-free and shows no synthetic card", () => {
    const client = { listDueReviews: vi.fn(), recordReviewAttempt: vi.fn() };
    renderPage(client, "demo");
    expect(screen.getByRole("heading", { name: "No reviews are due" })).toBeInTheDocument();
    expect(screen.queryByText(item.prompt)).not.toBeInTheDocument();
    expect(client.listDueReviews).not.toHaveBeenCalled();
  });

  it("isolates global shortcuts from interactive targets, modifiers, repeats, and Sidebar focus", async () => {
    const user = userEvent.setup();
    const listDueReviews = vi.fn().mockResolvedValueOnce(queue).mockResolvedValueOnce(emptyQueue);
    const recordReviewAttempt = vi.fn(async () => ({ ...completed, response: "" }));
    renderPage({ listDueReviews, recordReviewAttempt });
    expect(await screen.findByRole("heading", { name: item.prompt })).toBeInTheDocument();

    fireEvent.keyDown(window, { code: "Space", key: " " });
    expect(screen.getByText(/Differentiate the outer function/i)).toBeInTheDocument();
    const textarea = screen.getByRole("textbox", { name: /Your recall/i });
    textarea.focus();
    fireEvent.keyDown(textarea, { key: "3", code: "Digit3" });
    fireEvent.keyDown(window, { key: "3", code: "Digit3", ctrlKey: true });
    fireEvent.keyDown(window, { key: "3", code: "Digit3", repeat: true });
    const sidebar = document.createElement("aside");
    sidebar.tabIndex = 0;
    document.body.append(sidebar);
    sidebar.focus();
    fireEvent.keyDown(sidebar, { key: "3", code: "Digit3" });
    expect(recordReviewAttempt).not.toHaveBeenCalled();
    sidebar.remove();

    const hide = screen.getByRole("button", { name: /Hide expected answer/i });
    hide.focus();
    await user.keyboard(" ");
    expect(screen.queryByText(/Differentiate the outer function/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Reveal expected answer/i }));
    const good = screen.getByRole("button", { name: /Good/i });
    good.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(recordReviewAttempt).toHaveBeenCalledOnce());
  });

  it("retries an unknown outcome with the identical submission after authoritative reconciliation", async () => {
    const user = userEvent.setup();
    const listDueReviews = vi.fn().mockResolvedValueOnce(queue).mockResolvedValueOnce(queue).mockResolvedValueOnce(emptyQueue);
    const recordReviewAttempt = vi.fn().mockRejectedValueOnce(new TypeError("connection lost")).mockResolvedValueOnce(completed);
    renderPage({ listDueReviews, recordReviewAttempt });
    await revealAndRate(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(/still due with the same schedule/i);
    await user.click(screen.getByRole("button", { name: "Retry same Good rating" }));
    await waitFor(() => expect(recordReviewAttempt).toHaveBeenCalledTimes(2));
    expect(recordReviewAttempt.mock.calls[1]?.[1]).toEqual(recordReviewAttempt.mock.calls[0]?.[1]);
    expect(await screen.findByRole("heading", { name: "Reviews complete" })).toBeInTheDocument();
  });

  it("does not claim success when an unknown outcome disappears from the current due window", async () => {
    const user = userEvent.setup();
    const listDueReviews = vi.fn().mockResolvedValueOnce(queue).mockResolvedValueOnce(emptyQueue);
    const recordReviewAttempt = vi.fn(async () => { throw new DOMException("Aborted", "AbortError"); });
    renderPage({ listDueReviews, recordReviewAttempt });
    await revealAndRate(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/may already have been saved/i);
    expect(screen.getByRole("heading", { name: "Nothing is due" })).toBeInTheDocument();
    expect(screen.queryByText(/Review recorded/i)).not.toBeInTheDocument();
  });

  it("treats a revision conflict as a known rejection and refreshes the current item", async () => {
    const user = userEvent.setup();
    const revisedItem = { ...item, revision: 1 };
    const listDueReviews = vi.fn().mockResolvedValueOnce(queue).mockResolvedValueOnce({ ...queue, items: [revisedItem] });
    const detail = { message: "Schedule changed", retryable: true, recovery: "Refresh", documentId: null, code: null };
    const recordReviewAttempt = vi.fn(async () => { throw new LearningCoreResponseError(409, detail, null); });
    renderPage({ listDueReviews, recordReviewAttempt });
    await revealAndRate(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed before this rating could be applied/i);
    expect(screen.queryByRole("button", { name: /Retry same/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reveal expected answer/i })).toBeEnabled();
  });

  it("fails closed when expected_answer is empty or unsupported", async () => {
    const unsupported = { ...item, expected_answer: { accepted_answers: [] } };
    renderPage({ listDueReviews: vi.fn(async () => ({ ...queue, items: [unsupported] })), recordReviewAttempt: vi.fn() });
    expect(await screen.findByText("This review cannot be rated")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reveal expected answer/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Good/i })).toBeDisabled();
    expect(screen.queryByText(/accepted_answers/)).not.toBeInTheDocument();
  });

  it("disables scoring while writing and reconciles a user cancellation", async () => {
    const user = userEvent.setup();
    const listDueReviews = vi.fn().mockResolvedValueOnce(queue).mockResolvedValueOnce(emptyQueue);
    const recordReviewAttempt = vi.fn((_itemId: string, _request: unknown, options: { signal: AbortSignal }) => new Promise<ReviewAttemptResponse>((_resolve, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })));
    renderPage({ listDueReviews, recordReviewAttempt });
    await revealAndRate(user);
    expect(screen.getByRole("button", { name: /Again/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Cancel and verify schedule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/may already have been saved/i);
    expect(screen.queryByText(/Review recorded/i)).not.toBeInTheDocument();
  });

  it("covers loading, read error, and unavailable recovery without inventing queue data", async () => {
    const pending = new Promise<DueReviewListResponse>(() => undefined);
    const view = renderPage({ listDueReviews: vi.fn(() => pending), recordReviewAttempt: vi.fn() });
    expect(screen.getByRole("status", { name: "Loading due reviews" })).toBeInTheDocument();
    view.unmount();

    renderPage({ listDueReviews: vi.fn(async () => { throw new Error("read failed"); }), recordReviewAttempt: vi.fn() });
    expect(await screen.findByRole("heading", { name: "Due reviews could not be loaded" }, { timeout: 3_000 })).toBeInTheDocument();
  });

  it("keeps an unavailable service recovery local to Review", () => {
    renderPage(null, "unavailable");
    expect(screen.getByRole("heading", { name: "Reviews are unavailable" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText(item.prompt)).not.toBeInTheDocument();
  });

  it("drops stale write feedback when the learning service generation changes", async () => {
    const user = userEvent.setup();
    let requestSignal: AbortSignal | undefined;
    const firstClient = { listDueReviews: vi.fn(async () => queue), recordReviewAttempt: vi.fn((_itemId: string, _request: unknown, options: { signal: AbortSignal }) => { requestSignal = options.signal; return new Promise<ReviewAttemptResponse>((_resolve, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })); }) };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    core.current = { status: "healthy", client: firstClient, connectionGeneration: 1, retry: vi.fn() } as never;
    const view = render(<MemoryRouter><QueryClientProvider client={queryClient}><FlashcardsPage /></QueryClientProvider></MemoryRouter>);
    await revealAndRate(user);
    await waitFor(() => expect(firstClient.recordReviewAttempt).toHaveBeenCalledOnce());
    core.current = { status: "healthy", client: { listDueReviews: vi.fn(async () => emptyQueue), recordReviewAttempt: vi.fn() }, connectionGeneration: 2, retry: vi.fn() } as never;
    view.rerender(<MemoryRouter><QueryClientProvider client={queryClient}><FlashcardsPage /></QueryClientProvider></MemoryRouter>);
    await waitFor(() => expect(requestSignal?.aborted).toBe(true));
    expect(screen.queryByText(/may have been saved|Review recorded/i)).not.toBeInTheDocument();
  });
});
