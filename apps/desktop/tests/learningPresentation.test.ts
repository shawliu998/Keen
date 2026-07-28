import { displayLearningTitle, learningTitlesMatch } from "../src/features/learningPresentation";

describe("learning presentation", () => {
  it.each([
    ["Study: Learn limits.", "Learn limits."],
    ["Study very weak concept: Eigenvectors", "Strengthen Eigenvectors"],
    ["Study weak concept: Limits", "Review Limits"],
    ["Address misconception: Slope equals height", "Resolve Slope equals height"],
    ["Resume study session: Study: Chain rule", "Chain rule"],
  ])("turns generated title %s into learner-facing copy", (input, expected) => {
    expect(displayLearningTitle(input)).toBe(expected);
  });

  it("matches a generated session title with its repeated goal", () => {
    expect(learningTitlesMatch("Study: Learn limits.", "Learn limits.")).toBe(true);
  });
});
