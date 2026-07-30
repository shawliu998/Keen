import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DeepLearnPage } from "../src/features/deep-learn/DeepLearnPage";
import { AgentRuntimeProvider } from "../src/services/AgentRuntimeProvider";
import { AppShell } from "../src/shell/AppShell";
import { useAppStore } from "../src/state/appStore";

const core = vi.hoisted(() => ({ current: null as never }));
vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => core.current,
  isLearningCoreStarting: () => false,
}));

const time = "2026-07-18T10:00:00+00:00";
const unit = { id: "unit-1", ordinal: 0, concept_id: "concept-1", concept_ids: ["concept-1"], source_chunk_ids: ["chunk-secret"], title: "SECRET UNIT TITLE", objective: "Secret objective.", content: "Secret source text.", estimated_minutes: 10, status: "active" as const };
const plan = { id: "plan-1", session_id: "session-1", version: 1, rationale: "Secret rationale.", units: [unit, { ...unit, id: "unit-2", ordinal: 1, status: "ready" as const }] };
const session = { id: "session-1", course_id: "course-1", originating_task_id: "task-1", title: "Secret session", mode: "study" as const, goal: "Secret goal.", estimated_minutes: 20, status: "active_recall" as const, progress: 0.2, revision: 3, created_at: time, updated_at: time, started_at: time };
const recallUnit = { id: "unit-1", ordinal: 0, estimated_minutes: 10, status: "active" as const, created_at: time, updated_at: time };
const pending = {
  outcome: "pending" as const,
  course_id: "course-1",
  session: { id: "session-1", course_id: "course-1", status: "active_recall" as const, revision: 3, progress: 0.2, estimated_minutes: 20, current_unit_id: "unit-1", created_at: time, updated_at: time, started_at: time, finished_at: null },
  plan: { id: "plan-1", session_id: "session-1", version: 1, units: [recallUnit, { ...recallUnit, id: "unit-2", ordinal: 1, status: "ready" as const }] },
  checkpoint: { id: "checkpoint-1", kind: "active_recall" as const, prompt: "Complete [...].", status: "pending" as const, created_at: time, answered_at: null },
  current_unit: recallUnit,
  run: { id: "run-1", status: "pending" as const, checkpoint_id: "checkpoint-1", generator_version: "source-cloze-v1", created_at: time, answered_at: null, cancelled_at: null, cancellation_reason: null },
  grade: null,
};

describe("Active Recall inspector protection", () => {
  it("closes an already-open source inspector before a pending prompt is shown", async () => {
    useAppStore.setState({
      inspectorOpen: true,
      inspector: { eyebrow: "Source citations", title: "SECRET INSPECTOR TITLE", body: "SECRET INSPECTOR BODY", meta: ["Chunk chunk-secret"] },
    });
    core.current = {
      status: "healthy",
      connectionGeneration: 1,
      retry: vi.fn(),
      client: {
        getStudySession: vi.fn(async () => ({ outcome: "ready" as const, course_id: "course-1", session, plan, current_unit_id: "unit-1", recovery_action: null })),
        getStudySessionActiveRecall: vi.fn(async () => pending),
        beginStudySessionActiveRecall: vi.fn(),
        answerStudySessionActiveRecall: vi.fn(),
        getLatestAgentRunActivity: vi.fn(async () => ({ run: null, events: [] })),
      },
    } as never;
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/deep-learn/session-1?course_id=course-1"]}>
          <AgentRuntimeProvider>
            <Routes><Route element={<AppShell />}><Route path="/deep-learn/:id" element={<DeepLearnPage />} /></Route></Routes>
          </AgentRuntimeProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Complete [...].")).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Context inspector" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close inspector" })).not.toBeInTheDocument();
    expect(screen.queryByText("SECRET INSPECTOR TITLE")).not.toBeInTheDocument();
    expect(screen.queryByText("SECRET INSPECTOR BODY")).not.toBeInTheDocument();
    expect(screen.queryByText("Chunk chunk-secret")).not.toBeInTheDocument();
    expect(screen.queryByText("Demo source labels")).not.toBeInTheDocument();
  });
});
