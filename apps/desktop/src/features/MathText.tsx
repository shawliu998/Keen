import { Fragment, type ReactNode } from "react";

type MathToken =
  | { kind: "text"; value: string }
  | { kind: "matrix"; label: string | null; rows: string[][] }
  | { kind: "vector"; values: string[] }
  | { kind: "latex"; value: string };

const matrixPattern = /(?:\b([A-Za-z])\s*=\s*)?\[\[([^[\]]+)\],\s*\[([^[\]]+)\]\]/g;
const vectorPattern = /\[\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\]/g;
const inlineLatexPattern = /\\\((.+?)\\\)/gs;
const latexPartPattern = /\\[A-Za-z]+|[A-Za-z]+|\d+(?:\.\d+)?|[=+\-*/(),]|[^\s]/g;
const latexSymbols: Record<string, { value: string; spoken: string; operator?: boolean }> = {
  "\\alpha": { value: "α", spoken: "alpha" },
  "\\beta": { value: "β", spoken: "beta" },
  "\\gamma": { value: "γ", spoken: "gamma" },
  "\\delta": { value: "δ", spoken: "delta" },
  "\\epsilon": { value: "ε", spoken: "epsilon" },
  "\\lambda": { value: "λ", spoken: "lambda" },
  "\\mu": { value: "μ", spoken: "mu" },
  "\\pi": { value: "π", spoken: "pi" },
  "\\sigma": { value: "σ", spoken: "sigma" },
  "\\theta": { value: "θ", spoken: "theta" },
  "\\cdot": { value: "·", spoken: "times", operator: true },
  "\\times": { value: "×", spoken: "times", operator: true },
  "\\neq": { value: "≠", spoken: "does not equal", operator: true },
  "\\le": { value: "≤", spoken: "less than or equal to", operator: true },
  "\\ge": { value: "≥", spoken: "greater than or equal to", operator: true },
};

function values(value: string): string[] {
  return value.split(",").map((entry) => entry.trim()).filter(Boolean);
}

function tokenizeMathText(text: string): MathToken[] {
  const tokens: MathToken[] = [];
  let offset = 0;
  matrixPattern.lastIndex = 0;
  for (const match of text.matchAll(matrixPattern)) {
    const index = match.index ?? 0;
    if (index > offset) tokens.push({ kind: "text", value: text.slice(offset, index) });
    tokens.push({
      kind: "matrix",
      label: match[1] ?? null,
      rows: [values(match[2]), values(match[3])],
    });
    offset = index + match[0].length;
  }
  if (offset < text.length) tokens.push({ kind: "text", value: text.slice(offset) });

  const vectors = tokens.flatMap((token) => {
    if (token.kind !== "text") return token;
    const nested: MathToken[] = [];
    let nestedOffset = 0;
    vectorPattern.lastIndex = 0;
    for (const match of token.value.matchAll(vectorPattern)) {
      const index = match.index ?? 0;
      if (index > nestedOffset) nested.push({ kind: "text", value: token.value.slice(nestedOffset, index) });
      nested.push({ kind: "vector", values: [match[1], match[2]] });
      nestedOffset = index + match[0].length;
    }
    if (nestedOffset < token.value.length) nested.push({ kind: "text", value: token.value.slice(nestedOffset) });
    return nested;
  });
  return vectors.flatMap((token) => {
    if (token.kind !== "text") return token;
    const nested: MathToken[] = [];
    let nestedOffset = 0;
    inlineLatexPattern.lastIndex = 0;
    for (const match of token.value.matchAll(inlineLatexPattern)) {
      const index = match.index ?? 0;
      if (index > nestedOffset) nested.push({ kind: "text", value: token.value.slice(nestedOffset, index) });
      nested.push({ kind: "latex", value: match[1] });
      nestedOffset = index + match[0].length;
    }
    if (nestedOffset < token.value.length) nested.push({ kind: "text", value: token.value.slice(nestedOffset) });
    return nested;
  });
}

function matrixLabel(label: string | null, rows: string[][]): string {
  const contents = rows.map((row) => row.join(", ")).join("; ");
  return `${label ? `${label} equals ` : ""}matrix ${contents}`;
}

function MatrixMath({ label, rows }: { label: string | null; rows: string[][] }) {
  return <math className="math-notation math-matrix" aria-label={matrixLabel(label, rows)}>
    <mrow>
      {label ? <><mi>{label}</mi><mo>=</mo></> : null}
      <mo>[</mo>
      <mtable>
        {rows.map((row, rowIndex) => <mtr key={rowIndex}>
          {row.map((entry, columnIndex) => <mtd key={columnIndex}><mn>{entry}</mn></mtd>)}
        </mtr>)}
      </mtable>
      <mo>]</mo>
    </mrow>
  </math>;
}

function VectorMath({ values: entries }: { values: string[] }) {
  return <math className="math-notation math-vector" aria-label={`vector ${entries.join(", ")}`}>
    <mrow>
      <mo>[</mo>
      {entries.map((entry, index) => <Fragment key={index}>
        {index > 0 ? <mo>,</mo> : null}
        <mn>{entry}</mn>
      </Fragment>)}
      <mo>]</mo>
    </mrow>
  </math>;
}

function latexParts(value: string): string[] {
  return value.match(latexPartPattern) ?? [];
}

function latexLabel(value: string): string {
  return latexParts(value)
    .flatMap((part) => {
      const symbol = latexSymbols[part];
      if (symbol) return symbol.spoken;
      if (part === "=") return "equals";
      if (/^[A-Za-z]+$/.test(part)) return part.split("");
      if (part === "{" || part === "}") return [];
      return part;
    })
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

export function MathNotation({ value, display = false }: { value: string; display?: boolean }) {
  return <math
    className={`math-notation ${display ? "math-display" : "math-inline"}`}
    aria-label={latexLabel(value)}
  >
    <mrow>
      {latexParts(value).flatMap((part, index) => {
        const symbol = latexSymbols[part];
        if (symbol) {
          return symbol.operator
            ? <mo key={index}>{symbol.value}</mo>
            : <mi key={index}>{symbol.value}</mi>;
        }
        if (part === "{" || part === "}") return [];
        if (/^\d/.test(part)) return <mn key={index}>{part}</mn>;
        if (/^[A-Za-z]+$/.test(part)) {
          return part.split("").map((character, characterIndex) => <mi key={`${index}:${characterIndex}`}>{character}</mi>);
        }
        return <mo key={index}>{part}</mo>;
      })}
    </mrow>
  </math>;
}

/** Adds native MathML to bounded inline notation without changing persisted source text. */
export function FormattedMathText({ children }: { children: string }): ReactNode {
  return tokenizeMathText(children).map((token, index) => {
    if (token.kind === "matrix") return <MatrixMath key={index} label={token.label} rows={token.rows} />;
    if (token.kind === "vector") return <VectorMath key={index} values={token.values} />;
    if (token.kind === "latex") return <MathNotation key={index} value={token.value} />;
    return <Fragment key={index}>{token.value}</Fragment>;
  });
}
