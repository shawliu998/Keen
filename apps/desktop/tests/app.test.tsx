import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";

function renderApp(route = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
}

describe("desktop workflow", () => {
  it("navigates from Home to the Knowledge Base", async () => {
    const user = userEvent.setup();
    renderApp();
    expect(screen.getByRole("heading", { name: /what would you like to understand/i })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /knowledge base/i }));
    expect(screen.getByRole("heading", { name: "Knowledge Base" })).toBeInTheDocument();
    expect(screen.getByText("Linear Algebra — Chapter 5.pdf")).toBeInTheDocument();
  });

  it("completes a recommended Learning Feed task", async () => {
    const user = userEvent.setup();
    renderApp("/feed");
    expect(screen.getByText("Review eigenvectors before Chapter 6")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Start" })[0]);
    expect(screen.queryByText("Review eigenvectors before Chapter 6")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "completed" }));
    expect(screen.getByText("Review eigenvectors before Chapter 6")).toBeInTheDocument();
  });

  it("grades a quiz answer and advances", async () => {
    const user = userEvent.setup();
    renderApp("/quiz");
    await user.click(screen.getByRole("button", { name: /a vector whose direction is preserved/i }));
    await user.click(screen.getByRole("button", { name: /check answer/i }));
    expect(screen.getByText("Correct")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("If Av = −2v, what happens geometrically?")).toBeInTheDocument();
  });

  it.each([
    ["/", /No model runs, file is read, or learning record is changed/i],
    ["/deep-learn/1", /Answers, progress, and ratings are not persisted/i],
    ["/flashcards", /FSRS not connected/i],
    ["/quiz", /no assessment event or review task is persisted/i],
    ["/memory", /no Agent reads these items/i],
  ])("labels the unconnected %s surface as demo content", (route, disclosure) => {
    renderApp(route);
    expect(screen.getByText(disclosure)).toBeInTheDocument();
  });

  it("disables unimplemented settings actions and persistence claims", async () => {
    const user = userEvent.setup();
    renderApp("/settings");
    expect(screen.getByText(/Controls on this page are not applied or persisted/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open Source Notices" }));
    expect(screen.getAllByRole("button", { name: "Viewer unavailable" })[0]).toBeDisabled();
    expect(screen.queryByText(/Changes are stored on this Mac/i)).not.toBeInTheDocument();
  });
});
