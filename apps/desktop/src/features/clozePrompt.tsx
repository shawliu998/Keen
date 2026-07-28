export type ReadableClozePrompt = {
  /** Source statement that still contains the "[...]" blank marker. */
  question: string;
  /** Normalized equation shown separately when the statement carries one. */
  equation: string | null;
};

/** True when a persisted prompt is a source-cloze item with a blank marker. */
export function isClozePrompt(prompt: string): boolean {
  return prompt.includes("[...]");
}

/**
 * Display-only parsing of a persisted source-cloze prompt: drops the stored
 * instruction paragraph, normalizes "y prime" to "y′" and "times" to "·",
 * and separates a trailing equation from the statement. Text only; the
 * persisted prompt and every write contract stay unchanged.
 */
export function readableClozePrompt(prompt: string): ReadableClozePrompt {
  const [instruction, ...questionParts] = prompt.split(/\n\s*\n/);
  const question = (questionParts.join("\n\n") || instruction)
    .replace(/\b([A-Za-z])\s+prime\b/g, "$1′")
    .replace(/\btimes\b/g, "·")
    .replace(/\s+/g, " ")
    .trim();
  const equationDivider = question.lastIndexOf(":");
  const possibleEquation = equationDivider >= 0 ? question.slice(equationDivider + 1).trim() : "";
  const hasEquation = possibleEquation.includes("=");
  return {
    question: hasEquation ? question.slice(0, equationDivider + 1).trim() : question,
    equation: hasEquation ? possibleEquation : null,
  };
}

/** Renders the "[...]" marker as a visible blank plus a screen-reader cue. */
export function BlankStatement({ children }: { children: string }) {
  const [before, ...after] = children.split("[...]");
  if (after.length === 0) return <FormattedMathText>{children}</FormattedMathText>;
  return <><FormattedMathText>{before}</FormattedMathText><span className="practice-blank" aria-hidden="true">________</span><span className="visually-hidden">blank</span><FormattedMathText>{after.join("[...]")}</FormattedMathText></>;
}
import { FormattedMathText } from "./MathText";
