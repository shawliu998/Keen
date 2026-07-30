import { render, screen } from "@testing-library/react";
import { Badge, Button, IconButton, Progress } from "@keen/ui";

describe("shared UI components", () => {
  it("exposes button variant, size, active and loading state without losing its label", () => {
    const { rerender } = render(<Button variant="primary" size="small">Continue</Button>);
    const button = screen.getByRole("button", { name: "Continue" });
    expect(button).toHaveClass("ui-button-primary", "ui-button-small");
    expect(button).not.toBeDisabled();

    rerender(<Button variant="primary" loading loadingLabel="Saving response">Continue</Button>);
    const loadingButton = screen.getByRole("button", { name: "Saving response" });
    expect(loadingButton).toHaveAttribute("aria-busy", "true");
    expect(loadingButton).toBeDisabled();
    expect(loadingButton.querySelector(".ui-button-spinner")).not.toBeNull();
  });

  it("preserves a feature-owned busy state when shared loading is not active", () => {
    render(<Button aria-busy="true">Create course</Button>);
    expect(screen.getByRole("button", { name: "Create course" })).toHaveAttribute("aria-busy", "true");
  });

  it("keeps icon buttons named and non-submitting by default", () => {
    render(<form><IconButton label="Close panel"><span aria-hidden>×</span></IconButton></form>);
    const button = screen.getByRole("button", { name: "Close panel" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveAttribute("title", "Close panel");
  });

  it("accepts semantic badge attributes and bounds progress values", () => {
    render(<><Badge tone="warning" aria-label="Provider unavailable">Not configured</Badge><Progress value={140} label="Course progress" /></>);
    expect(screen.getByLabelText("Provider unavailable")).toHaveClass("badge-warning");
    expect(screen.getByRole("progressbar", { name: "Course progress" })).toHaveAttribute("aria-valuenow", "100");
  });
});
