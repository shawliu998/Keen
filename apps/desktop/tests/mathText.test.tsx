import { render, screen } from "@testing-library/react";
import { FormattedMathText } from "../src/features/MathText";
import { BlankStatement } from "../src/features/clozePrompt";
import { LearningMarkdown } from "../src/features/deep-learn/LearningMarkdown";

describe("source math display", () => {
  it("renders unambiguous matrices and vectors with native MathML", () => {
    render(<p><FormattedMathText>A = [[3, 0], [0, -2]] maps [1, 0] and [0, 1].</FormattedMathText></p>);

    expect(screen.getByLabelText("A equals matrix 3, 0; 0, -2").tagName).toBe("math");
    expect(screen.getByLabelText("vector 1, 0").tagName).toBe("math");
    expect(screen.getByLabelText("vector 0, 1").tagName).toBe("math");
    expect(screen.queryByText(/\[\[3, 0\]/)).not.toBeInTheDocument();
  });

  it("keeps the cloze blank while formatting math around it", () => {
    const view = render(<p><BlankStatement>For A = [[3, 0], [0, -2]], the [...] preserves [1, 0].</BlankStatement></p>);

    expect(view.container.querySelector(".practice-blank")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("blank")).toHaveClass("visually-hidden");
    expect(view.container.contains(screen.getByLabelText("A equals matrix 3, 0; 0, -2"))).toBe(true);
    expect(view.container.contains(screen.getByLabelText("vector 1, 0"))).toBe(true);
  });

  it("renders persisted inline LaTeX delimiters as native MathML", () => {
    const view = render(<p><FormattedMathText>For \(A\), an eigenvector satisfies \(Av = \lambda v\).</FormattedMathText></p>);

    expect(screen.getByLabelText("A").tagName).toBe("math");
    expect(screen.getByLabelText("A v equals lambda v").tagName).toBe("math");
    expect(view.container).not.toHaveTextContent("\\(");
    expect(view.container).toHaveTextContent("Av=λv");
  });

  it("renders Agent Markdown inline and display delimiters as native MathML", () => {
    const view = render(<LearningMarkdown>{String.raw`For \(A\) and \(\lambda\), the equation is:

\[ A v = \lambda v \]`}</LearningMarkdown>);

    expect(screen.getByLabelText("A").tagName).toBe("math");
    expect(screen.getByLabelText("lambda").tagName).toBe("math");
    expect(screen.getByLabelText("A v equals lambda v").tagName).toBe("math");
    expect(screen.getByLabelText("A v equals lambda v").classList.contains("math-display")).toBe(true);
    expect(view.container).not.toHaveTextContent("\\(");
    expect(view.container).not.toHaveTextContent("\\[");
  });
});
