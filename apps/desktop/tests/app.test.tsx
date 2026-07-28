import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";

function renderApp(route = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
}

function expectHomeAskEntry() {
  expect(screen.getByRole("heading", { name: "What shall we explore?" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Ask sources mode" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Ask a grounded question with the sample workspace.")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("Enter a question about your course…")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Ask sources" })).toBeInTheDocument();
}

describe("desktop workflow", () => {
  it("navigates from Home to the Knowledge Base", async () => {
    const user = userEvent.setup();
    renderApp();
    expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /knowledge base/i }));
    expect(screen.getByRole("heading", { name: "Knowledge Base" })).toBeInTheDocument();
    expect(screen.getByText("Linear Algebra — Chapter 5.pdf")).toBeInTheDocument();
  });

  it("keeps the sidebar recoverable after it is collapsed", async () => {
    const user = userEvent.setup();
    const { container } = renderApp();
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(container.querySelector(".app-shell")).toHaveClass("is-collapsed");
    expect(screen.getByText("Demo", { exact: true })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(container.querySelector(".app-shell")).not.toHaveClass("is-collapsed");
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
  });

  it("exposes the selected Home Agent mode to assistive technology", async () => {
    const user = userEvent.setup();
    renderApp("/?mode=ask");
    const ask = screen.getByRole("button", { name: "Ask sources mode" });
    expect(ask).toHaveAttribute("aria-pressed", "true");
    const study = screen.getByRole("button", { name: "Focused study mode" });
    await user.click(study);
    await waitFor(() => expect(screen.getByRole("button", { name: "Focused study mode" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "Ask sources mode" })).toHaveAttribute("aria-pressed", "false");
  });

  it("exposes one New learning entry and keeps Ask or Study inside Home", async () => {
    const user = userEvent.setup();
    renderApp("/feed");
    const sidebar = within(screen.getByRole("complementary", { name: "Primary navigation" }));
    expect(sidebar.queryByRole("button", { name: "New study session" })).not.toBeInTheDocument();
    await user.click(sidebar.getByRole("button", { name: "New learning" }));
    expectHomeAskEntry();
    await user.click(screen.getByRole("button", { name: "Focused study mode" }));
    expect(screen.getByRole("heading", { name: "Start a study session" })).toBeInTheDocument();
    expect(screen.getByText("Focused study needs your desktop workspace")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Message Keen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start focused study" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View sample sources" })).toBeInTheDocument();
  });

  it("opens the source-first Home Ask entry from the sidebar", async () => {
    const user = userEvent.setup();
    renderApp("/feed");
    await user.click(within(screen.getByRole("complementary", { name: "Primary navigation" })).getByRole("button", { name: "New learning" }));
    expectHomeAskEntry();
  });

  it("opens the source-first Home Ask entry with Command-N", async () => {
    const user = userEvent.setup();
    renderApp("/history");
    await user.keyboard("{Meta>}n{/Meta}");
    expectHomeAskEntry();
  });

  it("opens the source-first Home Ask entry from the command palette", async () => {
    const user = userEvent.setup();
    renderApp("/settings");
    await user.keyboard("{Meta>}k{/Meta}");
    const dialog = screen.getByRole("dialog", { name: "Command palette" });
    await user.click(within(dialog).getByRole("button", { name: /New learning/i }));
    expectHomeAskEntry();
  });

  it("keeps the command palette limited to available primary workflows", async () => {
    const user = userEvent.setup();
    renderApp();
    const trigger = screen.getByRole("button", { name: "Open command palette" });
    trigger.focus();
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Command palette" });
    expect(within(dialog).getByText("Actions")).toBeInTheDocument();
    expect(within(dialog).getByText("Pages")).toBeInTheDocument();
    expect(within(dialog).queryByText(/learner memory/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/quiz/i)).not.toBeInTheDocument();
    expect(within(dialog).getByText("Review")).toBeInTheDocument();
    expect(within(dialog).queryByText(/new study session/i)).not.toBeInTheDocument();

    const search = within(dialog).getByRole("textbox", { name: "Search commands" });
    await user.type(search, "memory");
    expect(within(dialog).getByText("No matching command")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("supports arrow-key selection in the command palette", async () => {
    const user = userEvent.setup();
    renderApp("/settings");
    await user.keyboard("{Meta>}k{/Meta}");
    const dialog = screen.getByRole("dialog", { name: "Command palette" });
    const search = within(dialog).getByRole("textbox", { name: "Search commands" });
    expect(search).toHaveFocus();
    await user.keyboard("{ArrowDown}{Enter}");
    expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
  });

  it("presents Visualize as one truthful bundled example", () => {
    renderApp("/visualize");
    expect(screen.getByRole("img", { name: /Eigenvector transformation diagram/i })).toBeInTheDocument();
    expect(screen.getByText(/does not read course files, call a model, or create an artifact/i)).toBeInTheDocument();
    expect(screen.getByText("UI demo")).toBeInTheDocument();
    expect(screen.getByText("Bundled local example")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/Load demo preview/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Export unavailable/i)).not.toBeInTheDocument();
  });

  it("keeps future planning visible without simulating a schedule", async () => {
    const user = userEvent.setup();
    renderApp("/planner");
    expect(screen.getByRole("heading", { name: "No study plan is connected" })).toBeInTheDocument();
    expect(screen.getByText(/These are implementation gates, not available setup steps/i)).toBeInTheDocument();
    expect(screen.getByText(/calendar writes remain Level 3 actions/i)).toBeInTheDocument();
    expect(screen.queryByText(/July 13–19, 2026/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Import unavailable/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open Learning Feed" }));
    expect(screen.getByRole("heading", { name: "Learning Feed" })).toBeInTheDocument();
  });

  it("completes a recommended Learning Feed task", async () => {
    const user = userEvent.setup();
    renderApp("/feed");
    const taskPane = within(screen.getByRole("region", { name: "Learning tasks" }));
    expect(taskPane.getByText("Review eigenvectors before Chapter 6")).toBeInTheDocument();
    const task = document.getElementById("feed-task-t1");
    expect(task).not.toBeNull();
    const detailTrigger = screen.getByRole("button", { name: "Open task: Review eigenvectors before Chapter 6" });
    await user.click(detailTrigger);
    const detail = screen.getByRole("region", { name: "Review eigenvectors before Chapter 6" });
    const detailHeading = within(detail).getByRole("heading", { name: "Review eigenvectors before Chapter 6" });
    expect(detailHeading).toBeInTheDocument();
    expect(detailHeading).toHaveFocus();
    expect(within(detail).getByText("Expected steps")).toBeInTheDocument();
    await user.click(within(detail).getByRole("button", { name: "Close details" }));
    await waitFor(() => expect(detailTrigger).toHaveFocus());
    await user.click(detailTrigger);
    await user.click(screen.getByRole("button", { name: "Try demo task" }));
    expect(taskPane.queryByText("Review eigenvectors before Chapter 6")).not.toBeInTheDocument();
    expect(screen.getByText("This preview did not change your learning history.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Completed" }));
    expect(taskPane.getByText("Review eigenvectors before Chapter 6")).toBeInTheDocument();
  });

  it("uses a calendar task to reveal and select the matching feed item", async () => {
    const user = userEvent.setup();
    renderApp("/feed");
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    await user.click(screen.getByRole("button", { name: "Show task: Revisit gradient descent" }));
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
    const task = document.getElementById("feed-task-t4");
    expect(task).toHaveAttribute("aria-current", "true");
    expect(task).toHaveTextContent("Revisit gradient descent");
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
    ["/", /^Sample tasks$/i],
    ["/quiz", /no assessment event or review task is persisted/i],
    ["/memory", /does not currently infer a learner profile/i],
  ])("labels the unconnected %s surface as demo content", (route, disclosure) => {
    renderApp(route);
    expect(screen.getByText(disclosure)).toBeInTheDocument();
    if (route === "/quiz") expect(screen.getByText("UI demo")).toBeInTheDocument();
  });

  it("uses the single global Browser Demo disclosure on Deep Learn", () => {
    renderApp("/deep-learn/1");
    expect(screen.getByLabelText("Browser Demo · no service calls")).toBeInTheDocument();
    expect(screen.queryByText(/focused study · sample · not saved/i)).not.toBeInTheDocument();
  });

  it("does not substitute sample flashcards when the desktop review service is absent", () => {
    renderApp("/review");
    expect(screen.getByRole("heading", { name: "No reviews are due" })).toBeInTheDocument();
    expect(screen.getAllByText(/Browser Demo/i)).toHaveLength(1);
    expect(screen.queryByText("What is an eigenvector?")).not.toBeInTheDocument();
    expect(screen.queryByText("UI demo")).not.toBeInTheDocument();
  });

  it("removes unavailable settings controls instead of presenting disabled actions", async () => {
    const user = userEvent.setup();
    renderApp("/settings");
    expect(screen.getByText(/bundled sample data is discarded when the browser preview ends/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Saving unavailable/i })).not.toBeInTheDocument();
    const statusSection = screen.getByRole("button", { name: "Status" });
    expect(statusSection).toHaveAttribute("aria-pressed", "true");
    statusSection.focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Model" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Model" }));
    expect(screen.getByText(/Browser Demo does not save providers or accept credentials/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Provider")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Endpoint")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Model" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "About" }));
    expect(screen.getByText(/Complete license notices are included with the app in THIRD_PARTY_NOTICES\.md/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Viewer unavailable" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Changes are stored on this Mac/i)).not.toBeInTheDocument();
  });

  it("does not advertise unavailable integrations or simulated success", async () => {
    const user = userEvent.setup();
    renderApp("/settings");
    await user.click(screen.getByRole("button", { name: "Model" }));
    expect(screen.queryByText("Calendar")).not.toBeInTheDocument();
    expect(screen.queryByText("Drive")).not.toBeInTheDocument();
    expect(screen.queryByText("Canvas")).not.toBeInTheDocument();
    expect(screen.queryByText("Not implemented")).not.toBeInTheDocument();
    expect(screen.queryByText("Sample connected")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Preview .* success/i })).not.toBeInTheDocument();
  });
});
