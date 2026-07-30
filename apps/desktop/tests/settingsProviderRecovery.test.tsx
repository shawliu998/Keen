import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LearningCoreResponseError } from "@keen/api-client";
import { SettingsPage } from "../src/features/settings/SettingsPage";
import { buildProviderSettingsPath } from "../src/features/settings/providerRecoveryRouting";

const providerMocks = vi.hoisted(() => ({
  get: vi.fn(),
  save: vi.fn(),
}));
const core = vi.hoisted(() => ({ current: null as never }));

vi.mock("../src/features/settings/providerConfiguration", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/features/settings/providerConfiguration")>();
  return {
    ...actual,
    canConfigureProvider: () => true,
    getProviderConfiguration: providerMocks.get,
    saveProviderConfiguration: providerMocks.save,
  };
});
vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => core.current,
  isLearningCoreStarting: (status: string) => [
    "starting",
    "binding",
    "migrating",
    "recovering",
    "starting_server",
    "health_checking",
    "restarting",
  ].includes(status),
}));

const unconfigured = {
  configured: false,
  provider: null,
  endpoint: null,
  model: null,
  apiKeyConfigured: false,
};
const configured = {
  configured: true,
  provider: "ollama" as const,
  endpoint: "http://127.0.0.1:11434",
  model: "llama3.2",
  apiKeyConfigured: false,
};
const recoveryPath = buildProviderSettingsPath("session-1", "course-1");

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function coreState(
  status: "healthy" | "restarting" | "unavailable",
  testProvider: (() => Promise<unknown>) | null,
  connectionGeneration = 7,
) {
  return {
    status,
    client: testProvider ? { testProvider } : null,
    connectionGeneration,
    retry: vi.fn(),
    errorKind: null,
    serviceMessage: null,
    retryError: null,
    demoState: undefined,
    demoStatePending: false,
    demoStateError: null,
    visualFixture: false,
  } as never;
}

function ReturnProbe() {
  const location = useLocation();
  return <div>
    <h1>Returned to learning</h1>
    <span data-testid="return-location">{location.pathname}{location.search}</span>
  </div>;
}

function settingsTree(route = recoveryPath) {
  return <MemoryRouter initialEntries={[route]}>
    <Routes>
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/deep-learn/:id" element={<ReturnProbe />} />
    </Routes>
  </MemoryRouter>;
}

describe("Settings provider recovery", () => {
  beforeEach(() => {
    providerMocks.get.mockReset();
    providerMocks.save.mockReset();
  });

  it("opens Model from learning, gates return through save, restart, and connection validation", async () => {
    const user = userEvent.setup();
    const save = deferred<unknown>();
    const test = deferred<unknown>();
    const testProvider = vi.fn(() => test.promise);
    providerMocks.get
      .mockResolvedValueOnce(unconfigured)
      .mockResolvedValueOnce(configured);
    providerMocks.save.mockImplementation(() => save.promise);
    core.current = coreState("healthy", testProvider);
    const view = render(settingsTree());

    expect(screen.getByRole("heading", { level: 1, name: "Model" })).toBeInTheDocument();
    expect(screen.getByText("Provider needed for this learning step")).toBeInTheDocument();
    const model = await screen.findByRole("textbox", { name: "Model" });
    await user.type(model, "llama3.2");
    await user.click(screen.getByRole("button", { name: "Save and verify" }));

    expect(screen.getByRole("button", { name: "Saving provider settings" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("Provider")).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Model" })).toBeDisabled();
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Return to learning" })).not.toBeInTheDocument();

    await act(async () => save.resolve({}));

    expect(await screen.findByText(/Keen is restarting the learning service/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restarting learning service" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return to learning" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Model" })).toBeDisabled();

    core.current = coreState("restarting", null, 7);
    view.rerender(settingsTree());
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();

    core.current = coreState("healthy", testProvider, 8);
    view.rerender(settingsTree());

    await waitFor(() => expect(testProvider).toHaveBeenCalledOnce());
    expect(screen.getByRole("button", { name: "Verifying model access" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Testing provider connection" })).toHaveAttribute("aria-busy", "true");
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Return to learning" })).not.toBeInTheDocument();

    await act(async () => test.resolve({
      detail: "Connection verified.",
      provider: "ollama",
      model: "llama3.2",
    }));

    const returnButton = await screen.findByRole("button", { name: "Return to learning" });
    expect(returnButton).toHaveClass("ui-button-primary");
    expect(screen.getByRole("button", { name: "Save and verify" })).not.toHaveClass("ui-button-primary");
    expect(screen.getByRole("button", { name: "Test again" })).not.toHaveClass("ui-button-primary");
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);

    await user.click(returnButton);
    expect(await screen.findByRole("heading", { name: "Returned to learning" })).toBeInTheDocument();
    expect(screen.getByTestId("return-location")).toHaveTextContent("/deep-learn/session-1?course_id=course-1");
  });

  it("keeps the learning return locked and does not expose a save failure detail", async () => {
    const user = userEvent.setup();
    providerMocks.get.mockResolvedValue(unconfigured);
    providerMocks.save.mockRejectedValue(new Error("secret token sk-provider-private"));
    core.current = coreState("healthy", vi.fn());
    const view = render(settingsTree());

    await user.type(await screen.findByRole("textbox", { name: "Model" }), "llama3.2");
    await user.click(screen.getByRole("button", { name: "Save and verify" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Keen could not confirm that the provider settings were saved");
    expect(screen.queryByText(/sk-provider-private/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return to learning" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save and verify" })).toBeEnabled();
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
  });

  it("unlocks a retry when the supervised restart reaches an explicit terminal failure", async () => {
    const user = userEvent.setup();
    providerMocks.get
      .mockResolvedValueOnce(unconfigured)
      .mockResolvedValueOnce(configured);
    providerMocks.save.mockResolvedValue({});
    core.current = coreState("healthy", vi.fn(), 7);
    const view = render(settingsTree());

    await user.type(await screen.findByRole("textbox", { name: "Model" }), "llama3.2");
    await user.click(screen.getByRole("button", { name: "Save and verify" }));
    expect(await screen.findByRole("button", { name: "Restarting learning service" })).toBeDisabled();

    core.current = coreState("restarting", null, 7);
    view.rerender(settingsTree());
    expect(screen.getByRole("button", { name: "Restarting learning service" })).toBeDisabled();

    core.current = coreState("unavailable", null, 7);
    view.rerender(settingsTree());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Provider settings were saved, but Keen could not confirm the restarted learning service");
    expect(screen.getByRole("button", { name: "Retry save and verify" })).toBeEnabled();
    expect(screen.getByRole("textbox", { name: "Model" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
  });

  it("does not test an unsaved draft against the previously configured runtime", async () => {
    const user = userEvent.setup();
    const testProvider = vi.fn();
    providerMocks.get.mockResolvedValue(configured);
    core.current = coreState("healthy", testProvider);
    const view = render(settingsTree());

    const testButton = await screen.findByRole("button", { name: "Test connection" });
    expect(testButton).toHaveClass("ui-button-primary");
    const model = screen.getByRole("textbox", { name: "Model" });
    await user.clear(model);
    await user.type(model, "different-model");

    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save and verify" })).toHaveClass("ui-button-primary");
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
    expect(testProvider).not.toHaveBeenCalled();
  });

  it("keeps Test connection primary after a failed validation without exposing provider details", async () => {
    const user = userEvent.setup();
    const testProvider = vi.fn().mockRejectedValue(new LearningCoreResponseError(503, {
      message: "Keen could not confirm the provider model.",
      retryable: true,
      recovery: "Check the provider endpoint, model access, and API key, then retry.",
      documentId: null,
      code: null,
    }, "request-1"));
    providerMocks.get.mockResolvedValue(configured);
    core.current = coreState("healthy", testProvider);
    const view = render(settingsTree());

    expect(await screen.findByRole("heading", { level: 1, name: "Model" })).toBeInTheDocument();
    expect(screen.getByText("Provider needed for this learning step")).toBeInTheDocument();
    const testButton = await screen.findByRole("button", { name: "Test connection" });
    expect(testButton).toHaveClass("ui-button-primary");
    await user.click(testButton);

    await waitFor(() => expect(testProvider).toHaveBeenCalledOnce());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Keen could not confirm the provider model");
    expect(alert).toHaveTextContent("Check the provider endpoint, model access, and API key, then retry");
    expect(screen.queryByRole("button", { name: "Return to learning" })).not.toBeInTheDocument();
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Test connection" })).toHaveClass("ui-button-primary");
  });

  it("ignores an external return target instead of creating a navigation action", async () => {
    providerMocks.get.mockResolvedValue(configured);
    core.current = coreState("healthy", vi.fn());
    const unsafeRoute = "/settings?section=capabilities&return_to=https%3A%2F%2Fevil.example";
    const view = render(settingsTree(unsafeRoute));

    expect(await screen.findByRole("heading", { level: 1, name: "Model" })).toBeInTheDocument();
    expect(screen.queryByText("Provider needed for this learning step")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return to learning" })).not.toBeInTheDocument();
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Save and verify" })).toHaveClass("ui-button-primary");
  });

  it("requires a fresh connection test after Settings is reopened", async () => {
    providerMocks.get.mockResolvedValue(configured);
    core.current = coreState("healthy", vi.fn(), 8);
    const view = render(settingsTree());

    const testButton = await screen.findByRole("button", { name: "Test connection" });
    expect(testButton).toHaveClass("ui-button-primary");
    expect(screen.queryByRole("button", { name: "Return to learning" })).not.toBeInTheDocument();
    expect(view.container.querySelectorAll("button.ui-button-primary")).toHaveLength(1);
  });

  it("prefills known provider API bases while keeping custom bases editable", async () => {
    const user = userEvent.setup();
    providerMocks.get.mockResolvedValue(unconfigured);
    core.current = coreState("healthy", vi.fn(), 8);
    render(settingsTree("/settings?section=capabilities"));

    const providerSelect = await screen.findByRole("combobox", { name: "Provider" });
    await user.selectOptions(providerSelect, "deepseek");

    expect(screen.getByRole("textbox", { name: "Model" })).toHaveValue("deepseek-v4-flash");
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
    expect(screen.getByText("Compatible preset")).toBeInTheDocument();
    expect(screen.getByText(/availability still depends on your key, model, and provider/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Advanced connection" }));
    expect(screen.getByRole("textbox", { name: "API base URL" })).toHaveValue("https://api.deepseek.com");
    expect(screen.getByRole("textbox", { name: "API base URL" })).toBeDisabled();

    await user.selectOptions(providerSelect, "custom");
    expect(screen.getByRole("textbox", { name: "API base URL" })).toBeEnabled();
    expect(screen.getByRole("textbox", { name: "API base URL" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "Model" })).toHaveValue("");
    expect(screen.getByText(/not the final \/chat\/completions URL/i)).toBeInTheDocument();
  });
});
