import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LearningCoreResponseError } from "@keen/api-client";
import { StudyPlanProposal } from "../src/features/deep-learn/StudyPlanProposal";

const time = "2026-07-26T10:00:00+00:00";
const run = {
  id: "run-plan-1",
  status: "completed" as const,
  provider: "fixture",
  model: "bounded",
  createdAt: time,
  updatedAt: time,
  errorCode: null,
};
const artifact = {
  kind: "study_plan_proposal_artifact" as const,
  schemaVersion: 1 as const,
  artifactId: "plan-proposal-artifact-1",
  profileId: "learning.plan-proposal.source-grounded.v1" as const,
  profileDefinitionHash: "a".repeat(64),
  baseSessionRevision: 7,
  basePlanId: "plan-1",
  basePlanVersion: 1,
  summary: "Add a short composition prerequisite.",
  reason: "The cited source introduces an idea the selected unit assumes.",
  currentPlan: {
    units: [
      {
        id: "unit-1",
        ordinal: 0,
        title: "Composition",
        objective: "Recall composition.",
        estimatedMinutes: 8,
        status: "active",
      },
      {
        id: "unit-2",
        ordinal: 1,
        title: "Chain rule",
        objective: "Differentiate a composition.",
        estimatedMinutes: 12,
        status: "locked",
      },
    ],
  },
  operation: {
    kind: "insert_prerequisite" as const,
    beforeUnitId: "unit-2",
    title: "Composition refresher",
    objective: "Connect the inner and outer functions before differentiating.",
    estimatedMinutes: 10,
    selectedSourceHandles: ["source-1"],
  },
  sources: [{
    sourceHandle: "source-1",
    chunkId: "chunk-1",
    documentId: "document-1",
    documentVersionId: "version-1",
    chunkContentHash: "b".repeat(64),
    documentName: "Calculus notes",
    pageNumber: 4,
    sectionPath: ["Chain rule"],
    quote: "A composition has an inner and an outer function.",
    geometry: null,
    metadata: {},
  }],
  decision: {
    status: "pending" as const,
    applyAvailable: true as const,
  },
};
const none = {
  status: "none" as const,
  courseId: "course-1",
  sessionId: "session-1",
  reason: null,
  run: null,
  artifact: null,
  receipt: null,
  trigger: null,
};
const ready = {
  ...none,
  status: "ready" as const,
  run,
  artifact,
};
const adaptiveTrigger = {
  origin: "adaptive_evidence" as const,
  reasonCode: "low_confidence_incorrect_recall_after_intervention" as const,
  evidenceIds: ["evidence-recall-1", "evidence-intervention-1"],
  whyNow: "A low-confidence recall remained incorrect after a source-grounded explanation.",
  learnerApprovalRequired: true as const,
};
const adaptiveNone = {
  ...none,
  trigger: adaptiveTrigger,
};
const adaptiveReady = {
  ...ready,
  trigger: adaptiveTrigger,
};

function props(client: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  return {
    client: client as never,
    sessionId: "session-1",
    courseId: "course-1",
    sessionRevision: 7,
    planVersion: 1,
    targetUnitId: "unit-2",
    targetUnitTitle: "Chain rule",
    paused: false,
    stateScope: "recall-scope-1",
    onConfigureProvider: vi.fn(),
    onAgentRunChanged: vi.fn(),
    onSessionChanged: vi.fn(),
    ...overrides,
  };
}

describe("StudyPlanProposal", () => {
  it("restores safely in StrictMode and offers one explicit read-only request", async () => {
    const componentProps = props({
      getCurrentStudyPlanProposal: vi.fn(async () => none),
      startStudyPlanProposal: vi.fn(),
    });
    render(
      <StrictMode>
        <StudyPlanProposal {...componentProps} />
      </StrictMode>,
    );

    expect(
      await screen.findByText("Need a bridge before Chain rule?"),
    ).toBeInTheDocument();
    expect(screen.getByText(/saved plan will not change/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suggest prerequisite" })).toBeEnabled();
  });

  it("auto-starts one adaptive suggestion in StrictMode with the persisted trigger origin", async () => {
    const startStudyPlanProposal = vi.fn(async () => adaptiveReady);
    render(
      <StrictMode>
        <StudyPlanProposal {...props({
          getCurrentStudyPlanProposal: vi.fn(async () => adaptiveNone),
          startStudyPlanProposal,
        })} />
      </StrictMode>,
    );

    await waitFor(() => expect(startStudyPlanProposal).toHaveBeenCalledTimes(1));
    expect(startStudyPlanProposal).toHaveBeenCalledWith(
      "session-1",
      expect.objectContaining({
        triggerOrigin: "adaptive_evidence",
        request: "insert_source_grounded_prerequisite",
      }),
      expect.anything(),
    );
    expect(await screen.findByText("Agent suggested · not applied")).toBeInTheDocument();
  });

  it("waits while paused, then starts the adaptive suggestion once", async () => {
    const startStudyPlanProposal = vi.fn(async () => adaptiveReady);
    const componentProps = props({
      getCurrentStudyPlanProposal: vi.fn(async () => adaptiveNone),
      startStudyPlanProposal,
    }, { paused: true });
    const view = render(<StudyPlanProposal {...componentProps} />);

    expect(await screen.findByText("Need a bridge before Chain rule?")).toBeInTheDocument();
    expect(startStudyPlanProposal).not.toHaveBeenCalled();

    view.rerender(<StudyPlanProposal {...componentProps} paused={false} />);
    await waitFor(() => expect(startStudyPlanProposal).toHaveBeenCalledTimes(1));
  });

  it("restores an adaptive proposal with a bounded reason and explicit learner control", async () => {
    render(<StudyPlanProposal {...props({
      getCurrentStudyPlanProposal: vi.fn(async () => adaptiveReady),
      startStudyPlanProposal: vi.fn(),
    })} />);

    expect(await screen.findByText("Agent suggested · not applied")).toBeInTheDocument();
    expect(screen.getByText("Why now")).toBeInTheDocument();
    expect(screen.getByText(adaptiveTrigger.whyNow)).toBeInTheDocument();
    expect(screen.getByText(/Based on 2 saved learning evidence items/i)).toBeInTheDocument();
    expect(screen.getByText(/will not change the plan until you accept or keep it/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept adjustment" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Keep current plan" })).toBeEnabled();
    expect(screen.queryByText(/mastered/i)).not.toBeInTheDocument();
    expect(screen.queryByText("evidence-recall-1")).not.toBeInTheDocument();
  });

  it("creates a bounded request and renders an unapplied source-linked diff", async () => {
    const user = userEvent.setup();
    const startStudyPlanProposal = vi.fn(async () => ready);
    const componentProps = props({
      getCurrentStudyPlanProposal: vi.fn(async () => none),
      startStudyPlanProposal,
    });
    const view = render(<StudyPlanProposal {...componentProps} />);

    await user.click(await screen.findByRole("button", { name: "Suggest prerequisite" }));

    expect(await screen.findByRole("heading", { name: "Composition refresher" })).toBeInTheDocument();
    expect(screen.getByText("Plan suggestion · not applied")).toBeInTheDocument();
    expect(screen.getByText("10 min · proposed")).toBeInTheDocument();
    expect(screen.getByText(/has not changed the saved plan/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept adjustment" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Keep current plan" })).toBeEnabled();
    expect(view.container.querySelectorAll(".plan-proposal-sequence .is-proposed")).toHaveLength(1);

    await user.click(screen.getByText("1 cited source"));
    expect(screen.getByText("Calculus notes · p. 4")).toBeInTheDocument();
    expect(screen.getByText(artifact.sources[0].quote)).toBeInTheDocument();
    expect(startStudyPlanProposal).toHaveBeenCalledWith(
      "session-1",
      expect.objectContaining({
        courseId: "course-1",
        expectedSessionRevision: 7,
        expectedPlanVersion: 1,
        targetUnitId: "unit-2",
        request: "insert_source_grounded_prerequisite",
      }),
      expect.anything(),
    );
    expect(componentProps.onAgentRunChanged).toHaveBeenCalledWith("run-plan-1");
  });

  it("accepts once, shows the effective boundary, and can Undo", async () => {
    const user = userEvent.setup();
    const accepted = {
      ...ready,
      status: "accepted" as const,
      artifact: {
        ...artifact,
        decision: { status: "accepted" as const, applyAvailable: false },
      },
      receipt: {
        proposalId: "proposal-1",
        status: "accepted" as const,
        planVersion: 2,
        effectiveAfterCurrentStep: true,
        undoAvailable: true,
        undoUntil: "2026-07-26T10:10:00+00:00",
        message: "The adjusted plan is saved. It will take effect after the current learning step finishes.",
      },
    };
    const undone = {
      ...accepted,
      status: "undone" as const,
      artifact: {
        ...artifact,
        decision: { status: "undone" as const, applyAvailable: false },
      },
      receipt: {
        ...accepted.receipt,
        status: "undone" as const,
        planVersion: 3,
        undoAvailable: false,
        message: "The adjustment was undone.",
      },
    };
    const decideStudyPlanProposal = vi.fn(async () => accepted);
    const undoStudyPlanProposal = vi.fn(async () => undone);
    render(<StudyPlanProposal {...props({
      getCurrentStudyPlanProposal: vi.fn(async () => ready),
      startStudyPlanProposal: vi.fn(),
      decideStudyPlanProposal,
      undoStudyPlanProposal,
    })} />);

    await user.click(await screen.findByRole("button", { name: "Accept adjustment" }));
    expect(await screen.findByText("Adjustment saved")).toBeInTheDocument();
    expect(screen.getByText("Plan version 2 · starts after the current step")).toBeInTheDocument();
    expect(decideStudyPlanProposal).toHaveBeenCalledWith(
      "session-1",
      artifact.artifactId,
      expect.objectContaining({
        decision: "accept",
        expectedSessionRevision: 7,
        expectedPlanVersion: 1,
      }),
      expect.anything(),
    );

    await user.click(screen.getByRole("button", { name: "Undo adjustment" }));
    expect(await screen.findByText("Adjustment undone")).toBeInTheDocument();
    expect(undoStudyPlanProposal).toHaveBeenCalledWith(
      "session-1",
      "proposal-1",
      expect.objectContaining({ expectedSessionRevision: 7 }),
      expect.anything(),
    );
  });

  it("keeps the current plan without presenting another primary decision", async () => {
    const user = userEvent.setup();
    const rejected = {
      ...ready,
      status: "rejected" as const,
      artifact: {
        ...artifact,
        decision: { status: "rejected" as const, applyAvailable: false },
      },
      receipt: {
        proposalId: "proposal-1",
        status: "rejected" as const,
        planVersion: null,
        effectiveAfterCurrentStep: false,
        undoAvailable: false,
        undoUntil: null,
        message: "The current learning plan was kept unchanged.",
      },
    };
    const decideStudyPlanProposal = vi.fn(async () => rejected);
    render(<StudyPlanProposal {...props({
      getCurrentStudyPlanProposal: vi.fn(async () => ready),
      startStudyPlanProposal: vi.fn(),
      decideStudyPlanProposal,
    })} />);

    await user.click(await screen.findByRole("button", { name: "Keep current plan" }));
    expect(await screen.findByText("Current plan kept")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept adjustment" })).not.toBeInTheDocument();
    expect(decideStudyPlanProposal).toHaveBeenCalledWith(
      "session-1",
      artifact.artifactId,
      expect.objectContaining({ decision: "keep" }),
      expect.anything(),
    );
  });

  it("retries an uncertain decision with the exact same frozen identity", async () => {
    const user = userEvent.setup();
    const accepted = {
      ...ready,
      status: "accepted" as const,
      artifact: {
        ...artifact,
        decision: { status: "accepted" as const, applyAvailable: false },
      },
      receipt: {
        proposalId: "proposal-1",
        status: "accepted" as const,
        planVersion: 2,
        effectiveAfterCurrentStep: true,
        undoAvailable: true,
        undoUntil: "2026-07-26T10:10:00+00:00",
        message: "The adjusted plan is saved.",
      },
    };
    const decideStudyPlanProposal = vi.fn()
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce(accepted);
    render(<StudyPlanProposal {...props({
      getCurrentStudyPlanProposal: vi.fn(async () => ready),
      startStudyPlanProposal: vi.fn(),
      decideStudyPlanProposal,
    })} />);

    await user.click(await screen.findByRole("button", { name: "Accept adjustment" }));
    expect(await screen.findByText("Plan decision not confirmed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry decision" }));

    expect(await screen.findByText("Adjustment saved")).toBeInTheDocument();
    expect(decideStudyPlanProposal).toHaveBeenCalledTimes(2);
    expect(decideStudyPlanProposal.mock.calls[1]).toEqual(
      decideStudyPlanProposal.mock.calls[0],
    );
  });

  it("keeps an uncertain write bound to one frozen idempotency request", async () => {
    const user = userEvent.setup();
    const startStudyPlanProposal = vi.fn()
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce(ready);
    const componentProps = props({
      getCurrentStudyPlanProposal: vi.fn(async () => none),
      startStudyPlanProposal,
    });
    render(<StudyPlanProposal {...componentProps} />);

    await user.click(await screen.findByRole("button", { name: "Suggest prerequisite" }));
    await user.click(await screen.findByRole("button", { name: "Retry request" }));

    expect(await screen.findByRole("heading", { name: "Composition refresher" })).toBeInTheDocument();
    expect(startStudyPlanProposal).toHaveBeenCalledTimes(2);
    expect(startStudyPlanProposal.mock.calls[1]?.[1]).toEqual(
      startStudyPlanProposal.mock.calls[0]?.[1],
    );
  });

  it("shows truthful provider recovery without presenting a proposal", async () => {
    const providerMissing = {
      ...none,
      status: "unavailable" as const,
      reason: "provider_missing",
      run: { ...run, status: "failed" as const, errorCode: "provider_missing" },
    };
    const componentProps = props({
      getCurrentStudyPlanProposal: vi.fn(async () => providerMissing),
      startStudyPlanProposal: vi.fn(),
    });
    const user = userEvent.setup();
    render(<StudyPlanProposal {...componentProps} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A learning provider is required",
    );
    await user.click(screen.getByRole("button", { name: "Configure provider" }));
    expect(componentProps.onConfigureProvider).toHaveBeenCalledOnce();
    expect(screen.queryByRole("heading", { name: "Composition refresher" })).not.toBeInTheDocument();
  });

  it("refreshes stale session truth instead of replaying a rejected request", async () => {
    const user = userEvent.setup();
    const startStudyPlanProposal = vi.fn().mockRejectedValue(
      new LearningCoreResponseError(409, null, null),
    );
    const componentProps = props({
      getCurrentStudyPlanProposal: vi.fn(async () => none),
      startStudyPlanProposal,
    });
    render(<StudyPlanProposal {...componentProps} />);

    await user.click(await screen.findByRole("button", { name: "Suggest prerequisite" }));
    expect(await screen.findByText(/session or plan changed/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh current plan" }));

    expect(componentProps.onSessionChanged).toHaveBeenCalledOnce();
    expect(startStudyPlanProposal).toHaveBeenCalledOnce();
  });

  it("marks a restored stale suggestion unusable and requests a fresh one separately", async () => {
    const stale = {
      ...ready,
      status: "stale" as const,
      reason: "base_plan_changed",
    };
    const getCurrentStudyPlanProposal = vi.fn(async () => stale);
    const componentProps = props({
      getCurrentStudyPlanProposal,
      startStudyPlanProposal: vi.fn(),
    });
    render(<StudyPlanProposal {...componentProps} />);

    expect(await screen.findByText("Suggestion out of date")).toBeInTheDocument();
    expect(screen.getByText(/cannot be used/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Request an updated suggestion" }),
    ).toBeEnabled();
    await waitFor(() => expect(getCurrentStudyPlanProposal).toHaveBeenCalled());
  });
});
