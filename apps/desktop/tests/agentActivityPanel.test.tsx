import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgentActivityPanel, type AgentActivityPanelProps } from "../src/features/agent/AgentActivityPanel";
import type { AgentActivityState } from "../src/features/agent/agentActivityTypes";

function state(overrides: Partial<AgentActivityState> = {}): AgentActivityState {
  return {
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
    error: null,
    ...overrides,
  };
}

function renderPanel(props: Partial<AgentActivityPanelProps> = {}) {
  return render(<AgentActivityPanel runId={null} state={state()} {...props} />);
}

describe("AgentActivityPanel", () => {
  it("shows an honest empty state and provider/service failures", () => {
    const view = renderPanel();
    expect(screen.getByRole("heading", { name: "Ready" })).toBeInTheDocument();
    expect(screen.getByText("No Agent response has been recorded yet.")).toBeInTheDocument();

    view.rerender(<AgentActivityPanel runId={null} state={state()} viewState="provider_missing" />);
    expect(screen.getByRole("heading", { name: "Provider not configured" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("No Agent provider is configured");

    view.rerender(<AgentActivityPanel runId="run-1" state={state({ status: "running", durableStatus: "running" })} viewState="provider_unavailable" />);
    expect(screen.getByRole("alert")).toHaveTextContent("No completion is being claimed");

    view.rerender(<AgentActivityPanel runId="run-1" state={state({ status: "partial", partial: true, content: "Recorded so far" })} viewState="offline" />);
    expect(screen.getByRole("heading", { name: "Learning service offline" })).toBeInTheDocument();
    expect(screen.getByText("Recorded so far")).toBeInTheDocument();
  });

  it.each([
    ["queued", "Queued"],
    ["running", "Running"],
    ["completed", "Completed"],
    ["failed", "Failed"],
    ["cancelled", "Cancelled"],
    ["interrupted", "Interrupted"],
  ] as const)("renders the %s run state", (status, label) => {
    renderPanel({ runId: "run-1", state: state({ status, durableStatus: status }) });
    expect(screen.getByRole("heading", { name: label })).toBeInTheDocument();
  });

  it("renders waiting approval as read-only without an approval control", () => {
    renderPanel({ runId: "run-1", state: state({ status: "waiting_approval", durableStatus: "waiting_approval" }), onCancel: vi.fn() });
    expect(screen.getByRole("heading", { name: "Waiting for confirmation" })).toBeInTheDocument();
    expect(screen.getByText(/Confirmation is read-only here/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|confirm/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeEnabled();
  });

  it("preserves partial content and explains reconnecting and truncation", () => {
    renderPanel({
      runId: "run-1",
      viewState: "reconnecting",
      state: state({ status: "partial", partial: true, content: "A partial answer", contentTruncated: true }),
    });
    expect(screen.getByText("A partial answer")).toBeInTheDocument();
    expect(screen.getByText(/Partial response/)).toBeInTheDocument();
    expect(screen.getByText(/display limit/)).toBeInTheDocument();
  });

  it("shows only tool lifecycle metadata, content, warnings, and no raw internals", () => {
    const unsafeState = {
      ...state({
        status: "running",
        content: "Visible answer",
        tools: [{ invocationId: "call-1", toolName: "search_library", status: "completed", replayed: false }],
        warnings: [{ eventId: "event-1", code: "source_partial", message: "One source was unavailable." }],
      }),
      result: "SECRET TOOL RESULT",
      checkpoint: "SECRET CHECKPOINT",
      hiddenReasoning: "SECRET REASONING",
    } as AgentActivityState;

    renderPanel({ runId: "run-1", state: unsafeState });
    expect(screen.getByText("Visible answer")).toBeInTheDocument();
    expect(screen.getByText("Search Library")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("One source was unavailable.")).toBeInTheDocument();
    expect(screen.queryByText(/SECRET/)).not.toBeInTheDocument();
  });

  it("renders terminalized tool attempts without claiming they are still running", () => {
    renderPanel({
      runId: "run-1",
      state: state({
        status: "failed",
        durableStatus: "failed",
        terminal: true,
        tools: [
          { invocationId: "call-cancelled", toolName: "search_library", status: "cancelled", replayed: false },
          { invocationId: "call-stopped", toolName: "list_due_reviews", status: "stopped", replayed: false },
        ],
      }),
    });

    expect(screen.getByText("Cancelled before completion")).toBeInTheDocument();
    expect(screen.getByText("Stopped without a completed result")).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
  });

  it("offers Undo and Redo only for reversible study-task mutations", async () => {
    const user = userEvent.setup();
    const onUndo = vi.fn();
    const onRedo = vi.fn();
    const mutations = [
      { mutationId: "mutation-1", invocationId: "call-1", replayed: false, entityType: "study_task", entityId: "task-1", operation: "create" as const, action: null, targetMutationId: null },
      { mutationId: "mutation-2", invocationId: "call-2", replayed: false, entityType: "note", entityId: "note-1", operation: "create" as const, action: null, targetMutationId: null },
      { mutationId: "mutation-inverse-1", invocationId: "call-3", replayed: false, entityType: "study_task", entityId: "task-1", operation: "update" as const, action: "undo" as const, targetMutationId: "mutation-1" },
    ];
    const view = renderPanel({ runId: "run-1", state: state({ status: "completed", durableStatus: "completed", terminal: true, mutations }), onUndo, onRedo });

    await user.click(screen.getByRole("button", { name: "Undo study task created" }));
    expect(onUndo).toHaveBeenCalledWith("mutation-1");
    expect(screen.queryByText(/note/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /study task/i })).toHaveLength(1);

    view.rerender(
      <AgentActivityPanel
        runId="run-1"
        state={state({ status: "completed", durableStatus: "completed", terminal: true, mutations })}
        mutationActions={{ "mutation-1": { undone: true, pendingAction: null, error: null } }}
        onUndo={onUndo}
        onRedo={onRedo}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Redo study task created" }));
    expect(onRedo).toHaveBeenCalledWith("mutation-1");
  });

  it("keeps recorded mutations visible but disables Undo until the run is terminal", () => {
    renderPanel({
      runId: "run-1",
      state: state({
        status: "running",
        durableStatus: "running",
        terminal: false,
        mutations: [{ mutationId: "mutation-1", invocationId: "call-1", replayed: false, entityType: "study_task", entityId: "task-1", operation: "create", action: null, targetMutationId: null }],
      }),
      onUndo: vi.fn(),
    });

    expect(screen.getByText("Study task created")).toBeInTheDocument();
    expect(screen.getByText(/Undo becomes available after the run stops/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo study task created" })).toBeDisabled();
  });

  it("disables pending actions, exposes busy state, and announces action errors", () => {
    renderPanel({
      runId: "run-1",
      state: state({
        status: "completed",
        durableStatus: "completed",
        terminal: true,
        mutations: [{ mutationId: "mutation-1", invocationId: "call-1", replayed: false, entityType: "study_task", entityId: "task-1", operation: "update", action: null, targetMutationId: null }],
      }),
      mutationActions: { "mutation-1": { undone: false, pendingAction: "undo", error: "Undo could not be recorded. Retry is safe." } },
      onUndo: vi.fn(),
    });
    const changes = screen.getByRole("heading", { name: "Local changes" }).closest("section");
    expect(changes).not.toBeNull();
    const button = within(changes as HTMLElement).getByRole("button", { name: "Undo study task updated" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Undo could not be recorded");
  });

  it("allows cancellation only for active runs and disables unavailable callbacks", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const view = renderPanel({ runId: "run-1", state: state({ status: "running", durableStatus: "running" }), onCancel });
    await user.click(screen.getByRole("button", { name: "Cancel run" }));
    expect(onCancel).toHaveBeenCalledOnce();

    view.rerender(<AgentActivityPanel runId="run-1" state={state({ status: "running", durableStatus: "running" })} cancelPending />);
    expect(screen.getByRole("button", { name: "Cancelling…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelling…" })).toHaveAttribute("aria-busy", "true");

    view.rerender(<AgentActivityPanel runId="run-1" state={state({ status: "completed", durableStatus: "completed", terminal: true })} onCancel={onCancel} />);
    expect(screen.queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument();
  });
});
