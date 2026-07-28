import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "../src/App";
import { parseActivityContext } from "../src/shell/AppShell";
import { getAgentShellStatus } from "../src/features/agent-activity/AgentStatusButton";
import { useAppStore } from "../src/state/appStore";
import { initialAgentActivityState } from "../src/features/agent/agentActivityReducer";
import type { AgentActivityState } from "../src/features/agent/agentActivityTypes";
import type { AgentActivityContext } from "../src/features/agent/useAgentRunLifecycle";
import type { AgentRuntimeContextValue } from "../src/services/AgentRuntimeProvider";

const runtimeContext = vi.hoisted(() => ({
  activity: {
    status: "idle",
    durableStatus: null,
    terminal: false,
    partial: false,
    content: "",
    contentTruncated: false,
    lastEventId: null,
    receivedEventIds: [],
    tools: [],
    mutations: [],
    warnings: [],
    learningRecord: null,
    pendingApproval: null,
    error: null,
  } as AgentActivityState,
  run: null,
  activityContext: null as AgentActivityContext,
  activityContextReady: true,
  phase: "idle" as const,
  issue: null,
  mutationAction: {
    target: null,
    pending: null,
    error: null,
    lastResult: null,
  },
  learningCoreStatus: "healthy",
  startRun: vi.fn(),
  cancelRun: vi.fn(),
  undoMutation: vi.fn(),
  redoMutation: vi.fn(),
  setActivityContext: vi.fn(),
}));

vi.mock("../src/services/AgentRuntimeProvider", async () => {
  const actual = await vi.importActual<typeof import("../src/services/AgentRuntimeProvider")>("../src/services/AgentRuntimeProvider");
  return {
    ...actual,
    useAgentRuntime: () => runtimeContext,
  };
});

function renderApp(route = "/feed") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useAppStore.setState({
    sidebarCollapsed: false,
    inspectorOpen: false,
    drawerView: "activity",
    commandOpen: false,
    inspector: null,
  });
  runtimeContext.setActivityContext.mockClear();
  runtimeContext.startRun.mockClear();
  runtimeContext.cancelRun.mockClear();
  runtimeContext.activity = initialAgentActivityState;
  runtimeContext.run = null;
  runtimeContext.activityContext = null;
  runtimeContext.activityContextReady = true;
  runtimeContext.phase = "idle";
  runtimeContext.issue = null;
  runtimeContext.learningCoreStatus = "healthy";
  runtimeContext.mutationAction = {
    target: null,
    pending: null,
    error: null,
    lastResult: null,
  };
});

describe("Agent-native app shell", () => {
  it("keeps one creation entry and only the release navigation in the sidebar", () => {
    renderApp("/");

    const navigation = screen.getByRole("navigation");
    expect(within(navigation).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Home",
      "Knowledge Base",
      "Learning Feed",
      "History",
      "Review",
    ]);
    const sidebar = screen.getByRole("complementary", { name: "Primary navigation" });
    expect(within(sidebar).getAllByRole("button", { name: "New learning" })).toHaveLength(1);
    expect([
      ...screen.queryAllByRole("button", { name: "New learning" }),
      ...screen.queryAllByRole("link", { name: "New learning" }),
    ]).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /quiz|planner|memory|visualize/iu })).not.toBeInTheDocument();
  });

  it("keeps the drawer closed by default and exposes honest Activity, Sources, and Outline states", async () => {
    const user = userEvent.setup();
    runtimeContext.learningCoreStatus = "demo";
    renderApp();

    expect(screen.queryByRole("complementary", { name: "Context and activity drawer" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Agent idle. Open activity drawer" });
    expect(trigger).toHaveAttribute("aria-pressed", "false");

    await user.click(trigger);
    const drawer = screen.getByRole("complementary", { name: "Context and activity drawer" });
    expect(trigger).toHaveAttribute("aria-pressed", "true");
    expect(within(drawer).getByRole("tab", { name: "Activity" })).toHaveAttribute("aria-selected", "true");
    expect(within(drawer).getByRole("heading", { name: "No Agent activity in Browser Demo" })).toBeInTheDocument();

    await user.click(within(drawer).getByRole("tab", { name: "Sources" }));
    expect(within(drawer).getByRole("heading", { name: "No source context selected" })).toBeInTheDocument();

    const outlineTab = within(drawer).getByRole("tab", { name: "Outline" });
    await user.click(outlineTab);
    expect(within(drawer).getByRole("heading", { name: "No outline connected" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", { name: "Context and activity drawer" })).not.toBeInTheDocument();
  });

  it("supports arrow-key tab navigation and renders only connected context", async () => {
    const user = userEvent.setup();
    useAppStore.getState().setInspector({
      title: "Unit sources",
      eyebrow: "Source citations",
      body: "These persisted chunk identifiers ground the current unit.",
      meta: ["Chunk source-1", "Chunk source-2"],
    });
    renderApp();

    const drawer = screen.getByRole("complementary", { name: "Context and activity drawer" });
    expect(within(drawer).getByRole("heading", { name: "Unit sources" })).toBeInTheDocument();
    expect(within(drawer).getByText("Chunk source-1")).toBeInTheDocument();

    const sourcesTab = within(drawer).getByRole("tab", { name: "Sources" });
    sourcesTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(within(drawer).getByRole("tab", { name: "Outline" })).toHaveFocus();
    expect(within(drawer).getByRole("heading", { name: "No outline connected" })).toBeInTheDocument();

    await user.keyboard("{ArrowLeft}");
    expect(sourcesTab).toHaveFocus();
    expect(within(drawer).getByRole("heading", { name: "Unit sources" })).toBeInTheDocument();
  });

  it("derives the four low-noise toolbar states from authoritative runtime state", () => {
    const base = {
      activityStatus: "idle" as const,
      phase: "idle" as const,
      issue: null,
      learningCoreStatus: "healthy" as const,
    };
    expect(getAgentShellStatus(base)).toBe("idle");
    expect(getAgentShellStatus({ ...base, activityStatus: "running", phase: "streaming" })).toBe("running");
    expect(getAgentShellStatus({ ...base, activityStatus: "completed" })).toBe("completed");
    expect(getAgentShellStatus({ ...base, activityStatus: "failed" })).toBe("error");
    expect(getAgentShellStatus({ ...base, learningCoreStatus: "unavailable" })).toBe("idle");
    expect(getAgentShellStatus({ ...base, learningCoreStatus: "unavailable", hasRun: true })).toBe("error");
    expect(getAgentShellStatus({
      ...base,
      activityStatus: "completed",
      learningCoreStatus: "unavailable",
      hasRun: true,
    })).toBe("completed");
  });

  it("maps deep learn routes to study session activity context", async () => {
    renderApp("/deep-learn/session-77");
    await waitFor(() => expect(runtimeContext.setActivityContext).toHaveBeenCalledWith({ studySessionId: "session-77" }));
  });

  it("maps conversation routes to conversation activity context", async () => {
    renderApp("/conversation/convo-21");
    await waitFor(() => expect(runtimeContext.setActivityContext).toHaveBeenCalledWith({ conversationId: "convo-21" }));
  });

  it("gates old Agent activity while the route context is being restored", () => {
    runtimeContext.activityContext = { conversationId: "old-conversation" };
    runtimeContext.activity = {
      ...initialAgentActivityState,
      status: "waiting_approval",
      durableStatus: "waiting_approval",
      content: "Old workspace output",
      pendingApproval: {
        approvalId: "old-approval",
        toolName: "complete_study_task",
        summary: {
          title: "Old approval",
          taskTitle: "Old task",
          courseTitle: "Old course",
          effect: "Old effect",
        },
      },
    };
    useAppStore.setState({ inspectorOpen: true, drawerView: "activity" });

    renderApp("/conversation/new-conversation");

    const drawer = screen.getByRole("complementary", { name: "Context and activity drawer" });
    expect(within(drawer).getByRole("heading", { name: "Restoring Agent activity" })).toBeInTheDocument();
    expect(within(drawer).queryByText("Old workspace output")).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: /Cancel run/u })).not.toBeInTheDocument();
    expect(runtimeContext.setActivityContext).toHaveBeenCalledWith({ conversationId: "new-conversation" });
  });

  it("renders a failed mutation action only on its recorded target", () => {
    const mutableRuntime = runtimeContext as unknown as AgentRuntimeContextValue;
    mutableRuntime.activity = {
      ...initialAgentActivityState,
      status: "completed",
      durableStatus: "completed",
      terminal: true,
      mutations: [
        {
          mutationId: "mutation-created",
          invocationId: "invocation-created",
          replayed: false,
          entityType: "study_task",
          entityId: "task-created",
          operation: "create",
          action: null,
          targetMutationId: null,
        },
        {
          mutationId: "mutation-deleted",
          invocationId: "invocation-deleted",
          replayed: false,
          entityType: "study_task",
          entityId: "task-deleted",
          operation: "delete",
          action: null,
          targetMutationId: null,
        },
      ],
    };
    mutableRuntime.mutationAction = {
      target: { action: "undo", mutationId: "mutation-deleted" },
      pending: null,
      error: {
        code: "run_failed",
        message: "Undo for the deleted task was not confirmed.",
        retryable: false,
        recovery: "Review the run.",
        automaticRecovery: false,
      },
      lastResult: null,
    };
    useAppStore.setState({ inspectorOpen: true, drawerView: "activity" });

    renderApp("/feed");

    const drawer = screen.getByRole("complementary", { name: "Context and activity drawer" });
    const error = within(drawer).getByText("Undo for the deleted task was not confirmed.");
    expect(error.closest("li")).toHaveTextContent("Study task deleted");
    expect(error.closest("li")).not.toHaveTextContent("Study task created");
  });

  it("maps non-context routes (including /conversation/new) to null context", async () => {
    renderApp("/conversation/new");
    await waitFor(() => expect(runtimeContext.setActivityContext).toHaveBeenCalledWith(null));
    expect(runtimeContext.setActivityContext).toHaveBeenLastCalledWith(null);
    runtimeContext.setActivityContext.mockClear();

    renderApp("/feed");
    await waitFor(() => expect(runtimeContext.setActivityContext).toHaveBeenCalledWith(null));
  });

  it("parses strict route identifiers and rejects invalid contexts", () => {
    expect(parseActivityContext("/conversation/valid-123")).toEqual({ conversationId: "valid-123" });
    expect(parseActivityContext("/conversation/percent%3Aencoded")).toEqual({ conversationId: "percent:encoded" });
    expect(parseActivityContext("/deep-learn/session%3Aid")).toEqual({ studySessionId: "session:id" });
    expect(parseActivityContext("/conversation/new")).toBeNull();
    expect(parseActivityContext("/conversation/-bad")).toBeNull();
    expect(parseActivityContext("/deep-learn/%25")).toBeNull();
    expect(parseActivityContext("/conversation/%")).toBeNull();
  });
});
