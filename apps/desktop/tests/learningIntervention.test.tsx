import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LearningCoreSchemaError } from "@keen/api-client";
import { LearningIntervention } from "../src/features/deep-learn/LearningIntervention";

const time = "2026-07-24T10:00:00+00:00";
const hash = "a".repeat(64);
const sourcePreview = {
  sourceHandle: "source-1",
  documentId: "document-1",
  documentName: "Limits notes.pdf",
  pageNumber: 7,
  sectionPath: ["Limits", "Formal definition"],
  metadata: {},
};
const actions = ["Explain differently", "Show a source example", "Test me instead"] as const;
const eligible = {
  status: "eligible" as const,
  courseId: "course-1",
  sessionId: "session-1",
  reason: null,
  actions: [...actions],
  run: null,
  artifact: {
    whyNow: "Your recall answer mixed up distance from the input with distance from the output.",
    sources: [sourcePreview],
    whatNext: { label: "Use the repaired distinction in one targeted check.", action: "continue_practice" as const },
  },
  practice: null,
  fallback: { action: "source_review" as const, label: "Return to source" },
};
const run = {
  id: "run-1",
  status: "queued" as const,
  provider: "local-openai-compatible",
  model: "local-model",
  createdAt: time,
  updatedAt: time,
  errorCode: null,
};
const queued = { ...eligible, status: "queued" as const, actions: [], run, artifact: null, fallback: null };
const readyArtifact = {
  kind: "learning_intervention_artifact" as const,
  schemaVersion: 1 as const,
  artifactId: "artifact-1",
  predecessor: null,
  profileId: "learning.intervention.source-grounded.v1" as const,
  profileDefinitionHash: hash,
  playbookSlug: "explain-differently",
  playbookVersion: 1,
  playbookDefinitionHash: hash,
  whyNow: eligible.artifact.whyNow,
  summary: "Separate the two distances",
  explanationMarkdown: "Treat **input distance at $g(x)$** and <img src=x onerror=alert(1)> output distance as plain text.\n\n1. Compare $g(x)$ with the input.\n2. Compare the output.\n\n$$y' = f'(g(x)) \\cdot g'(x)$$\n\n> Source: *quoted evidence*",
  sources: [{
    ...sourcePreview,
    chunkId: "chunk-1",
    documentVersionId: "version-1",
    chunkContentHash: hash,
    quote: "The input can approach a while the function value approaches L.",
    geometry: null,
  }],
  whatNext: {
    label: "Use the distinction in one targeted check.",
    action: "continue_practice" as const,
    practiceRunId: "practice-1",
    practicePrompt: "Which distance is controlled by delta?",
    sessionRevision: 5,
  },
};
const ready = {
  ...eligible,
  status: "ready" as const,
  run: { ...run, status: "completed" as const },
  artifact: readyArtifact,
  practice: readyArtifact.whatNext,
  fallback: null,
};

function props(client: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  return {
    client: client as never,
    sessionId: "session-1",
    courseId: "course-1",
    currentUnitId: "unit-1",
    sessionRevision: 4,
    stateScope: "recall-scope-1",
    paused: false,
    onGateChange: vi.fn(),
    onConfigureProvider: vi.fn(),
    onReturnToSource: vi.fn(),
    onStateChanged: vi.fn(),
    onAgentRunChanged: vi.fn(),
    ...overrides,
  };
}

describe("LearningIntervention", () => {
  it("restores the durable state after the StrictMode effect replay", async () => {
    const client = {
      getCurrentLearningIntervention: vi.fn(async () => eligible),
    };
    const componentProps = props(client);

    render(
      <StrictMode>
        <LearningIntervention {...componentProps} />
      </StrictMode>,
    );

    expect(await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Checking the current learning intervention…")).not.toBeInTheDocument();
    await waitFor(() => expect(componentProps.onGateChange).toHaveBeenLastCalledWith("recall-scope-1", "blocked"));
  });

  it("runs a typed Agent action, restores the durable artifact, and renders model text inertly", async () => {
    const user = userEvent.setup();
    const getCurrentLearningIntervention = vi.fn()
      .mockResolvedValueOnce(eligible)
      .mockResolvedValueOnce(ready);
    const startLearningIntervention = vi.fn(async () => queued);
    const learningInterventionEvents = vi.fn(async function* () {
      yield { id: "event-1", event: "running", data: { status: "running" } };
      yield { id: "event-2", event: "searching_sources", data: { status: "searching_sources" } };
      yield { id: "event-3", event: "source_context_ready", data: { status: "source_context_ready" } };
      yield { id: "event-4", event: "artifact_ready", data: readyArtifact };
      yield { id: "event-5", event: "done", data: { status: "ready", artifactId: "artifact-1" } };
    });
    const client = {
      getCurrentLearningIntervention,
      startLearningIntervention,
      learningInterventionEvents,
      cancelLearningIntervention: vi.fn(),
    };
    const componentProps = props(client);
    const view = render(<LearningIntervention {...componentProps} />);

    expect(await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why now" })).toBeInTheDocument();
    expect(screen.getByText("Limits notes.pdf · p. 7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try another approach…" })).toHaveAttribute("aria-expanded", "false");
    expect(view.container.querySelector(".intervention-explanation img")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Explain differently" }));

    expect(await screen.findByRole("heading", { name: "Separate the two distances" })).toBeInTheDocument();
    await waitFor(() => expect(componentProps.onAgentRunChanged).toHaveBeenCalled());
    expect(view.container.querySelector(".intervention-explanation strong")).toHaveTextContent("input distance at g(x)");
    expect(view.container.querySelector(".intervention-explanation strong .math-inline")).toHaveTextContent("g(x)");
    expect(screen.getByText(/<img src=x onerror=alert\(1\)> output distance as plain text/)).toBeInTheDocument();
    expect(screen.getByRole("list")).toHaveTextContent("Compare g(x) with the input.");
    expect(view.container.querySelector(".intervention-display-math")).toHaveTextContent("y'=f'(g(x))·g'(x)");
    expect(screen.getByText(/Source:/).closest("blockquote")).toBeInTheDocument();
    expect(screen.getByText("quoted evidence").tagName).toBe("EM");
    expect(view.container.querySelector(".intervention-explanation img")).toBeNull();
    expect(screen.getByText(readyArtifact.sources[0].quote)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try another approach…" }));
    expect(screen.getByRole("button", { name: "Explain differently" })).not.toHaveClass("primary");
    expect(startLearningIntervention).toHaveBeenCalledWith("session-1", expect.objectContaining({
      courseId: "course-1",
      unitId: "unit-1",
      expectedSessionRevision: 4,
      intent: "explain_differently",
    }), expect.anything());
    expect(learningInterventionEvents).toHaveBeenCalledWith("session-1", "run-1", "course-1", expect.anything());
    expect(learningInterventionEvents).toHaveBeenCalledTimes(1);
    expect(componentProps.onAgentRunChanged).toHaveBeenLastCalledWith("run-1");
    await waitFor(() => expect(componentProps.onGateChange).toHaveBeenLastCalledWith("recall-scope-1", "ready"));
    expect(componentProps.onStateChanged).toHaveBeenCalled();
  });

  it("publishes the confirmed run and session state when a disconnected stream restores terminal success", async () => {
    const user = userEvent.setup();
    const getCurrentLearningIntervention = vi.fn()
      .mockResolvedValueOnce(eligible)
      .mockResolvedValueOnce(ready);
    const learningInterventionEvents = vi.fn(async function* () {
      yield await Promise.reject(new Error("stream disconnected"));
    });
    const componentProps = props({
      getCurrentLearningIntervention,
      startLearningIntervention: vi.fn(async () => queued),
      learningInterventionEvents,
      cancelLearningIntervention: vi.fn(),
    });
    render(<LearningIntervention {...componentProps} />);

    expect(await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Explain differently" }));

    expect(await screen.findByRole("heading", { name: "Separate the two distances" })).toBeInTheDocument();
    expect(componentProps.onAgentRunChanged).toHaveBeenLastCalledWith("run-1");
    expect(componentProps.onStateChanged).toHaveBeenCalledTimes(1);
    expect(learningInterventionEvents).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Live Agent updates disconnected/)).not.toBeInTheDocument();
  });

  it("hands off a practice-ready state once when a disconnected stream restores it", async () => {
    const user = userEvent.setup();
    const practiceReady = { ...ready, status: "practice_ready" as const, artifact: null, actions: [] };
    const getCurrentLearningIntervention = vi.fn()
      .mockResolvedValueOnce(eligible)
      .mockResolvedValueOnce(practiceReady);
    const componentProps = props({
      getCurrentLearningIntervention,
      startLearningIntervention: vi.fn(async () => queued),
      learningInterventionEvents: vi.fn(async function* () {
        yield await Promise.reject(new Error("stream disconnected"));
      }),
      cancelLearningIntervention: vi.fn(),
    });
    render(<LearningIntervention {...componentProps} />);

    expect(await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Explain differently" }));

    expect(await screen.findByRole("heading", { name: "Continue with a targeted check" })).toBeInTheDocument();
    await waitFor(() => expect(componentProps.onStateChanged).toHaveBeenCalledTimes(1));
  });

  it("returns to the saved source route without starting a provider-backed Agent action", async () => {
    const user = userEvent.setup();
    const startLearningIntervention = vi.fn();
    const componentProps = props({
      getCurrentLearningIntervention: vi.fn(async () => eligible),
      startLearningIntervention,
      learningInterventionEvents: vi.fn(),
      cancelLearningIntervention: vi.fn(),
    });
    render(<LearningIntervention {...componentProps} />);

    expect(await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to source" }));

    expect(componentProps.onReturnToSource).toHaveBeenCalledWith("recall-scope-1");
    expect(startLearningIntervention).not.toHaveBeenCalled();
  });

  it("keeps eligible alternatives quiet until requested, then starts the selected typed intent", async () => {
    const user = userEvent.setup();
    const startLearningIntervention = vi.fn(async () => queued);
    const componentProps = props({
      getCurrentLearningIntervention: vi.fn(async () => eligible),
      startLearningIntervention,
      learningInterventionEvents: vi.fn(async function* () {}),
      cancelLearningIntervention: vi.fn(),
    });
    const view = render(<LearningIntervention {...componentProps} />);

    await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" });
    expect(view.container.querySelectorAll(".intervention-actions button.primary")).toHaveLength(1);
    const providerDisclosure = screen.getByText(
      /Explain differently and Show a source example send your current answer/i,
    );
    expect(providerDisclosure).toHaveTextContent(
      "relevant cited excerpts to the configured model provider",
    );
    expect(providerDisclosure).not.toHaveTextContent("Test me instead");
    expect(screen.queryByRole("button", { name: "Show a source example" })).not.toBeInTheDocument();
    const disclosure = screen.getByRole("button", { name: "Try another approach…" });
    const disclosureGroup = document.getElementById(disclosure.getAttribute("aria-controls") ?? "");
    expect(disclosureGroup).toHaveAttribute("hidden");
    await user.click(disclosure);
    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    expect(disclosureGroup).not.toHaveAttribute("hidden");

    await user.click(screen.getByRole("button", { name: "Test me instead" }));
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    expect(startLearningIntervention).toHaveBeenCalledWith("session-1", expect.objectContaining({
      intent: "test_me_instead",
    }), expect.anything());
  });

  it("does not show a provider disclosure for deterministic local practice alone", async () => {
    const user = userEvent.setup();
    const startLearningIntervention = vi.fn(async () => ({
      ...ready,
      status: "practice_ready" as const,
      artifact: null,
      actions: [],
    }));
    render(<LearningIntervention {...props({
      getCurrentLearningIntervention: vi.fn(async () => ({
        ...eligible,
        actions: ["Test me instead"],
      })),
      startLearningIntervention,
      cancelLearningIntervention: vi.fn(),
    })} />);

    const localPractice = await screen.findByRole("button", { name: "Test me instead" });
    expect(screen.queryByText(/configured model provider/i)).not.toBeInTheDocument();
    await user.click(localPractice);
    expect(startLearningIntervention).toHaveBeenCalledWith(
      "session-1",
      expect.objectContaining({ intent: "test_me_instead" }),
      expect.anything(),
    );
  });

  it("binds a ready-state alternative and its uncertain retry to the visible artifact", async () => {
    const user = userEvent.setup();
    const startLearningIntervention = vi.fn()
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce({
        ...queued,
        run: { ...run, id: "run-2" },
      });
    const componentProps = props({
      getCurrentLearningIntervention: vi.fn(async () => ready),
      startLearningIntervention,
      learningInterventionEvents: vi.fn(async function* () {}),
      cancelLearningIntervention: vi.fn(),
    });
    render(<LearningIntervention {...componentProps} />);

    await screen.findByRole("heading", { name: "Separate the two distances" });
    await user.click(screen.getByRole("button", { name: "Try another approach…" }));
    await user.click(screen.getByRole("button", { name: "Show a source example" }));

    expect(await screen.findByRole("button", { name: "Retry show a source example" })).toBeInTheDocument();
    const firstRequest = startLearningIntervention.mock.calls[0]?.[1];
    expect(firstRequest).toMatchObject({
      intent: "show_source_example",
      predecessorRunId: "run-1",
      predecessorArtifactId: "artifact-1",
    });

    await user.click(screen.getByRole("button", { name: "Retry show a source example" }));
    expect(startLearningIntervention).toHaveBeenCalledTimes(2);
    expect(startLearningIntervention.mock.calls[1]?.[1]).toEqual(firstRequest);
  });

  it("shows only the frozen retry request after an uncertain write", async () => {
    const user = userEvent.setup();
    const startLearningIntervention = vi.fn()
      .mockRejectedValueOnce(new Error("network lost"));
    const componentProps = props({
      getCurrentLearningIntervention: vi.fn(async () => eligible),
      startLearningIntervention,
      learningInterventionEvents: vi.fn(),
      cancelLearningIntervention: vi.fn(),
    });
    render(<LearningIntervention {...componentProps} />);

    await screen.findByRole("heading", { name: "Choose how Keen should repair this gap" });
    await user.click(screen.getByRole("button", { name: "Explain differently" }));

    expect(await screen.findByRole("button", { name: "Retry explain differently" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try another approach…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Test me instead" })).not.toBeInTheDocument();
  });

  it("hands off a restored practice-ready state once", async () => {
    const componentProps = props({
      getCurrentLearningIntervention: vi.fn(async () => ({
        ...ready,
        status: "practice_ready" as const,
        artifact: null,
        actions: [],
      })),
    });
    render(<LearningIntervention {...componentProps} />);

    await screen.findByRole("heading", { name: "Continue with a targeted check" });
    await waitFor(() => expect(componentProps.onStateChanged).toHaveBeenCalledTimes(1));
  });

  it("prevents new intents while paused but keeps an active run cancellable", async () => {
    const user = userEvent.setup();
    const pausedEligible = props({
      getCurrentLearningIntervention: vi.fn(async () => eligible),
    }, { paused: true });
    const eligibleView = render(<LearningIntervention {...pausedEligible} />);
    expect(await screen.findByRole("button", { name: "Explain differently" })).toBeDisabled();
    eligibleView.unmount();

    const running = { ...queued, status: "running" as const, run: { ...run, status: "running" as const } };
    const cancelled = { ...eligible, status: "cancelled" as const, actions: [], artifact: null, practice: null, run: { ...run, status: "cancelled" as const }, fallback: null, reason: "cancelled" };
    const cancelLearningIntervention = vi.fn(async () => cancelled);
    const componentProps = props({
      getCurrentLearningIntervention: vi.fn(async () => running),
      cancelLearningIntervention,
      learningInterventionEvents: vi.fn(async function* () {}),
    }, { paused: true });
    render(<LearningIntervention {...componentProps} />);

    const cancel = await screen.findByRole("button", { name: "Cancel Agent run" });
    expect(cancel).toBeEnabled();
    await user.click(cancel);
    await waitFor(() => expect(cancelLearningIntervention).toHaveBeenCalledOnce());
  });

  it("offers one primary provider recovery and a secondary saved-source route", async () => {
    const user = userEvent.setup();
    const startLearningIntervention = vi.fn();
    const providerMissing = {
      ...eligible,
      status: "source_review" as const,
      reason: "provider_missing",
      run: { ...run, status: "failed" as const, errorCode: "provider_missing" },
      artifact: null,
      practice: null,
      fallback: { action: "source_review" as const, label: "Return to source", retryable: true },
    };
    const componentProps = props({
      getCurrentLearningIntervention: vi.fn(async () => providerMissing),
      startLearningIntervention,
      learningInterventionEvents: vi.fn(),
      cancelLearningIntervention: vi.fn(),
    });
    const view = render(<LearningIntervention {...componentProps} />);

    expect(await screen.findByRole("heading", { name: "Connect a provider to continue with the Agent" })).toBeInTheDocument();
    const configure = screen.getByRole("button", { name: "Configure learning provider" });
    const reviewSource = screen.getByRole("button", { name: "Review source instead" });
    expect(configure).toHaveClass("primary");
    expect(reviewSource).not.toHaveClass("primary");
    expect(view.container.querySelectorAll("button.primary")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Explain differently" })).not.toBeInTheDocument();

    await user.click(configure);
    expect(componentProps.onConfigureProvider).toHaveBeenCalledOnce();
    expect(startLearningIntervention).not.toHaveBeenCalled();

    await user.click(reviewSource);
    expect(componentProps.onReturnToSource).toHaveBeenCalledWith("recall-scope-1");
  });

  it("keeps a running intervention cancellable and moves to the truthful source-review fallback", async () => {
    const user = userEvent.setup();
    const running = { ...queued, status: "running" as const, run: { ...run, status: "running" as const } };
    const cancelled = {
      ...eligible,
      status: "cancelled" as const,
      run: { ...run, status: "cancelled" as const },
      artifact: null,
      practice: null,
      fallback: { action: "source_review" as const, label: "Return to source" },
      reason: "cancelled",
    };
    const learningInterventionEvents = vi.fn(async function* (
      _sessionId: string,
      _runId: string,
      _courseId: string,
      options: { signal?: AbortSignal },
    ) {
      yield { id: "event-running", event: "running", data: { status: "running" } };
      await new Promise<void>((resolve) => options.signal?.addEventListener("abort", () => resolve(), { once: true }));
    });
    const cancelLearningIntervention = vi.fn(async () => cancelled);
    const client = {
      getCurrentLearningIntervention: vi.fn(async () => running),
      startLearningIntervention: vi.fn(),
      learningInterventionEvents,
      cancelLearningIntervention,
    };
    const componentProps = props(client);
    render(<LearningIntervention {...componentProps} />);

    expect(await screen.findByRole("heading", { name: "Repairing this misconception" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel Agent run" }));

    expect(await screen.findByRole("heading", { name: "Agent run cancelled" })).toBeInTheDocument();
    expect(screen.getByText(/practice remains locked/i)).toBeInTheDocument();
    expect(cancelLearningIntervention).toHaveBeenCalledWith("session-1", "run-1", "course-1", expect.anything());
    await waitFor(() => expect(componentProps.onGateChange).toHaveBeenLastCalledWith("recall-scope-1", "fallback"));
  });

  it("falls back on an unverified restore and reports an ineligible state without inventing UI", async () => {
    const failedProps = props({
      getCurrentLearningIntervention: vi.fn(async () => {
        throw new LearningCoreSchemaError("/v1/study-sessions/session-1/interventions/current");
      }),
    });
    const failed = render(<LearningIntervention {...failedProps} />);
    expect(await screen.findByRole("heading", { name: "Agent status could not be restored" })).toBeInTheDocument();
    expect(screen.getByText(/could not verify/i)).toBeInTheDocument();
    await waitFor(() => expect(failedProps.onGateChange).toHaveBeenLastCalledWith("recall-scope-1", "fallback"));
    failed.unmount();

    const ineligibleProps = props({
      getCurrentLearningIntervention: vi.fn(async () => ({
        status: "ineligible",
        courseId: "course-1",
        sessionId: "session-1",
        reason: "recall_correct",
        actions: [],
        run: null,
        artifact: null,
        practice: null,
        fallback: null,
      })),
    });
    const ineligible = render(<LearningIntervention {...ineligibleProps} />);
    await waitFor(() => expect(ineligibleProps.onGateChange).toHaveBeenLastCalledWith("recall-scope-1", "ineligible"));
    expect(ineligible.container).toBeEmptyDOMElement();
  });

  it("does not render a late intervention response after the active Recall scope changes", async () => {
    let resolveOld!: (value: unknown) => void;
    const oldEligible = {
      ...eligible,
      artifact: {
        ...eligible.artifact,
        sources: [{ ...sourcePreview, documentName: "OLD SOURCE.pdf" }],
      },
    };
    const newEligible = {
      ...eligible,
      sessionId: "session-2",
      artifact: {
        ...eligible.artifact,
        sources: [{ ...sourcePreview, sourceHandle: "source-2", documentName: "CURRENT SOURCE.pdf" }],
      },
    };
    const client = {
      getCurrentLearningIntervention: vi.fn((sessionId: string) => sessionId === "session-1"
        ? new Promise((resolve) => { resolveOld = resolve; })
        : Promise.resolve(newEligible)),
    };
    const firstProps = props(client);
    const view = render(<LearningIntervention {...firstProps} />);
    await waitFor(() => expect(client.getCurrentLearningIntervention).toHaveBeenCalledWith("session-1", "course-1", expect.anything()));
    const secondProps = props(client, { sessionId: "session-2", stateScope: "recall-scope-2" });
    view.rerender(<LearningIntervention {...secondProps} />);

    expect(await screen.findByText("CURRENT SOURCE.pdf · p. 7")).toBeInTheDocument();
    resolveOld(oldEligible);
    await waitFor(() => expect(screen.queryByText("OLD SOURCE.pdf · p. 7")).not.toBeInTheDocument());
    expect(screen.getByText("CURRENT SOURCE.pdf · p. 7")).toBeInTheDocument();
    expect(secondProps.onGateChange).toHaveBeenLastCalledWith("recall-scope-2", "blocked");
  });
});
