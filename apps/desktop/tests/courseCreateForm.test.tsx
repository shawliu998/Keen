import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LearningCoreResponseError, LearningCoreSchemaError, type Course, type DemoState, type LearningCoreClient } from "@keen/api-client";
import { CourseCreateForm } from "../src/features/knowledge/CourseCreateForm";

const cacheKey = ["learning-core", "demo-state", "http://127.0.0.1:43123", 1] as const;
const course = { id: "course-created", title: "Calculus", description: "Limits", created_at: "2026-07-17T10:00:00+00:00", concept_count: 0, average_mastery: null };
const initialState: DemoState = { courses: [], tasks: [], mastery: [] };

function renderForm({
  createCourse = vi.fn(async () => ({ course, replayed: false })),
  demo = false,
  unavailable = false,
  onCreated = vi.fn(),
  strictMode = false,
}: {
  createCourse?: LearningCoreClient["createCourse"];
  demo?: boolean;
  unavailable?: boolean;
  onCreated?: (course: Course) => void;
  strictMode?: boolean;
} = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(cacheKey, initialState);
  const form = <QueryClientProvider client={queryClient}><CourseCreateForm
    client={unavailable ? null : { createCourse } as Pick<LearningCoreClient, "createCourse">}
    cacheKey={cacheKey}
    demo={demo}
    onCreated={onCreated}
  /></QueryClientProvider>;
  const view = render(strictMode ? <StrictMode>{form}</StrictMode> : form);
  return { ...view, createCourse, onCreated, queryClient };
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Course title"), "Calculus");
  await user.type(screen.getByLabelText("Course description"), "Limits");
  await user.click(screen.getByRole("button", { name: "Create course" }));
}

describe("CourseCreateForm", () => {
  it("creates a course after StrictMode setup, updates the course cache, and selects it for the next import", async () => {
    const user = userEvent.setup();
    const { createCourse, onCreated, queryClient } = renderForm({ strictMode: true });

    await fillAndSubmit(user);

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(course));
    expect(createCourse).toHaveBeenCalledWith(expect.objectContaining({ title: "Calculus", description: "Limits" }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(queryClient.getQueryData<DemoState>(cacheKey)?.courses).toEqual([course]);
    expect(screen.getByRole("status")).toHaveTextContent("Created “Calculus” and selected it for the next import.");
  });

  it("uses a single in-flight request and does not submit an empty title", async () => {
    const user = userEvent.setup();
    let resolve!: (value: { course: typeof course; replayed: boolean }) => void;
    const pending = new Promise<{ course: typeof course; replayed: boolean }>((done) => { resolve = done; });
    const createCourse = vi.fn(() => pending);
    renderForm({ createCourse });

    expect(screen.getByRole("button", { name: "Create course" })).toBeDisabled();
    await user.type(screen.getByLabelText("Course title"), "Calculus");
    const submit = screen.getByRole("button", { name: "Create course" });
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(createCourse).toHaveBeenCalledTimes(1);
    expect(submit).toHaveAttribute("aria-busy", "true");
    resolve({ course, replayed: false });
    await screen.findByText(/Created “Calculus”/);
  });

  it("uses a new key for known validation and conflict failures, without exposing server details", async () => {
    const user = userEvent.setup();
    const createCourse = vi.fn()
      .mockRejectedValueOnce(new LearningCoreResponseError(409, { message: "private sqlite detail", retryable: false, recovery: null, documentId: null, code: null }, null))
      .mockResolvedValueOnce({ course, replayed: false });
    renderForm({ createCourse });

    await fillAndSubmit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Course creation conflicted");
    expect(screen.queryByText(/private sqlite detail/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create course" }));
    await waitFor(() => expect(createCourse).toHaveBeenCalledTimes(2));
    expect(createCourse.mock.calls[1][0].idempotencyKey).not.toBe(createCourse.mock.calls[0][0].idempotencyKey);
  });

  it.each([
    new LearningCoreResponseError(500, { message: "private server trace", retryable: true, recovery: null, documentId: null, code: null }, null),
    new LearningCoreSchemaError("/v1/courses"),
    new TypeError("Network connection failed"),
  ])("keeps the key and gives the same truthful recovery for an unconfirmed creation result", async (failure) => {
    const user = userEvent.setup();
    const createCourse = vi.fn().mockRejectedValueOnce(failure).mockResolvedValueOnce({ course, replayed: false });
    const { onCreated, queryClient } = renderForm({ createCourse });

    await fillAndSubmit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("The current course display was not updated. The local service may have created the course. Refresh the course list first, then retry with the same request key to avoid creating a duplicate course.");
    expect(screen.queryByText(/private server trace|network connection failed/i)).not.toBeInTheDocument();
    expect(queryClient.getQueryData<DemoState>(cacheKey)?.courses).toEqual([]);
    expect(onCreated).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Create course" }));
    await waitFor(() => expect(createCourse).toHaveBeenCalledTimes(2));
    expect(createCourse.mock.calls[1][0].idempotencyKey).toBe(createCourse.mock.calls[0][0].idempotencyKey);
  });

  it("aborts an in-flight request when unmounted", async () => {
    const user = userEvent.setup();
    let signal: AbortSignal | undefined;
    const createCourse = vi.fn<LearningCoreClient["createCourse"]>((_request, options) => new Promise<never>(() => { signal = options?.signal; }));
    const { unmount } = renderForm({ createCourse });

    await fillAndSubmit(user);
    await waitFor(() => expect(signal).toBeDefined());
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("does not request course creation in Browser Demo or while the local service is unavailable", async () => {
    const user = userEvent.setup();
    const demo = renderForm({ demo: true });
    expect(screen.getByRole("status")).toHaveTextContent("no request will be sent");
    expect(screen.getByRole("button", { name: "Create course" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Create course" }));
    expect(demo.createCourse).not.toHaveBeenCalled();
  });

  it("labels local-service unavailability and sends no course request", () => {
    const unavailable = renderForm({ unavailable: true });
    expect(screen.getByRole("status")).toHaveTextContent("Course creation is unavailable until Keen confirms the local service and course list. No request was sent.");
    expect(screen.getByRole("button", { name: "Create course" })).toBeDisabled();
    expect(unavailable.createCourse).not.toHaveBeenCalled();
  });
});
