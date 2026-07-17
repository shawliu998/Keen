import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AgentRun } from "@keen/api-client";
import type { AgentRuntimeContextValue } from "../src/services/AgentRuntimeProvider";
import { initialAgentActivityState } from "../src/features/agent/agentActivityReducer";
import { HomePage } from "../src/features/home/HomePage";

const runtimeState = vi.hoisted(() => ({ current: null as unknown as AgentRuntimeContextValue }));
const learningCoreState = vi.hoisted(() => ({ current: {
  status: "healthy", client: null, connectionGeneration: 0, demoState: undefined,
  demoStatePending: false, demoStateError: null,
} }));

vi.mock("../src/services/AgentRuntimeProvider", () => ({
  useAgentRuntime: () => runtimeState.current,
}));

vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => learningCoreState.current,
}));

vi.mock("../src/features/feed/useAutonomousLearningFeed", () => ({
  useAutonomousLearningFeed: () => ({
    snapshot: undefined, snapshotPending: false, snapshotError: null, refetchSnapshot: vi.fn(),
    createRecommendation: vi.fn(), cancelRecommendation: vi.fn(),
    recommendation: { pending: false, cancelled: false, error: null, result: null },
  }),
}));

const now = "2026-07-16T10:00:00.000Z";

function agentRun(status: AgentRun["status"]): AgentRun {
  const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(status);
  const unsuccessful = ["failed", "cancelled", "interrupted"].includes(status);
  return {
    id: "run-home-1",
    kind: "deep_learn",
    mode: "study",
    status,
    provider: "test-provider",
    model: "test-model",
    errorCode: unsuccessful ? "test_error" : null,
    errorDetail: unsuccessful ? "The test run ended." : null,
    createdAt: now,
    updatedAt: now,
    startedAt: status === "queued" ? null : now,
    finishedAt: terminal ? now : null,
  };
}

function runtime(overrides: Partial<AgentRuntimeContextValue> = {}): AgentRuntimeContextValue {
  return {
    activity: initialAgentActivityState,
    run: null,
    phase: "idle",
    issue: null,
    mutationAction: { pending: null, error: null, lastResult: null },
    learningCoreStatus: "healthy",
    startRun: vi.fn(async () => agentRun("queued")),
    cancelRun: vi.fn(async () => true),
    undoMutation: vi.fn(async () => true),
    redoMutation: vi.fn(async () => true),
    ...overrides,
  };
}

function renderHome() {
  return render(<MemoryRouter><HomePage /></MemoryRouter>);
}

beforeEach(() => {
  runtimeState.current = runtime();
});

describe("Agent Home", () => {
  it("starts the selected real Agent mode only from a user submission", async () => {
    const user = userEvent.setup();
    renderHome();
    expect(runtimeState.current.startRun).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /^Study$/u }));
    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Build a plan from my notes");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(runtimeState.current.startRun).toHaveBeenCalledWith({
      kind: "deep_learn",
      mode: "study",
      userIntent: "Build a plan from my notes",
      input: {},
    });
    expect(screen.getByText(/The feed below reads persisted learning evidence/i)).toBeInTheDocument();
    expect(screen.queryByText("78%")).not.toBeInTheDocument();
    expect(screen.queryByText("5 sources")).not.toBeInTheDocument();
    expect(screen.queryByText("18 insights")).not.toBeInTheDocument();
  });

  it("keeps Browser Demo request-free and records only the local conversation handoff", async () => {
    const user = userEvent.setup();
    runtimeState.current = runtime({ learningCoreStatus: "demo" });
    renderHome();

    await user.type(screen.getByRole("textbox", { name: "Message Keen" }), "Demo question");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(runtimeState.current.startRun).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("keen-new-message")).toBe("Demo question");
  });

  it("renders provider failure without claiming a run or completion", () => {
    runtimeState.current = runtime({
      issue: {
        code: "provider_missing",
        message: "No Agent provider is configured, so no run was created.",
        retryable: false,
        recovery: "Configure a provider before trying again.",
        automaticRecovery: false,
      },
    });
    renderHome();

    expect(screen.getByRole("heading", { name: "Provider not configured" })).toBeInTheDocument();
    expect(screen.getByText("No Agent provider is configured, so no run was created.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Completed" })).not.toBeInTheDocument();
  });

  it("sends cancellation only from the explicit active-run control", async () => {
    const user = userEvent.setup();
    runtimeState.current = runtime({
      run: agentRun("running"),
      phase: "streaming",
      activity: { ...initialAgentActivityState, status: "running", durableStatus: "running" },
    });
    renderHome();

    await user.click(screen.getByRole("button", { name: "Cancel Agent run" }));
    expect(runtimeState.current.cancelRun).toHaveBeenCalledOnce();
  });

  it("derives Redo from authoritative mutation-action audit metadata", async () => {
    const user = userEvent.setup();
    runtimeState.current = runtime({
      run: agentRun("completed"),
      activity: {
        ...initialAgentActivityState,
        status: "completed",
        durableStatus: "completed",
        terminal: true,
        mutations: [
          {
            mutationId: "mutation-original-1",
            invocationId: "invocation-original-1",
            replayed: false,
            entityType: "study_task",
            entityId: "task-1",
            operation: "update",
            action: null,
            targetMutationId: null,
          },
          {
            mutationId: "mutation-inverse-1",
            invocationId: "invocation-undo-1",
            replayed: false,
            entityType: "study_task",
            entityId: "task-1",
            operation: "update",
            action: "undo",
            targetMutationId: "mutation-original-1",
          },
        ],
      },
    });
    renderHome();

    await user.click(screen.getByRole("button", { name: "Redo study task updated" }));
    expect(runtimeState.current.redoMutation).toHaveBeenCalledWith("mutation-original-1");
    expect(runtimeState.current.undoMutation).not.toHaveBeenCalled();
  });
});
