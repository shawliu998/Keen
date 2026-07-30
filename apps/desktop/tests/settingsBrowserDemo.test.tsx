import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { SettingsPage } from "../src/features/settings/SettingsPage";

const tauri = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: tauri.invoke,
  isTauri: () => false,
}));
vi.mock("../src/services/LearningCoreProvider", () => ({
  useLearningCore: () => ({
    status: "demo",
    client: null,
    connectionGeneration: 0,
    retry: vi.fn(),
  }),
  isLearningCoreStarting: () => false,
}));

describe("Settings browser demo", () => {
  it("does not render provider fields or invoke desktop configuration commands", () => {
    render(<MemoryRouter initialEntries={["/settings?section=capabilities"]}><SettingsPage /></MemoryRouter>);

    expect(screen.getByRole("heading", { level: 1, name: "Model" })).toBeInTheDocument();
    expect(screen.getByText(/Browser Demo does not save providers or accept credentials/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Provider")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Endpoint")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Model" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();
    expect(tauri.invoke).not.toHaveBeenCalled();
  });
});
