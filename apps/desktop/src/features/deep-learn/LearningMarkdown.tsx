import { Fragment, type ReactNode } from "react";
import { MathNotation } from "../MathText";

type Block =
  | { kind: "paragraph"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "ordered-list"; items: string[] }
  | { kind: "math"; text: string };

function inlineContent(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*|\\\([^\n]+?\\\)|\$[^$\n]+\$)/g)
    .filter(Boolean)
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={index}>{inlineContent(part.slice(2, -2))}</strong>;
      }
      if (part.startsWith("*") && part.endsWith("*")) {
        return <em key={index}>{inlineContent(part.slice(1, -1))}</em>;
      }
      if (part.startsWith("$") && part.endsWith("$")) {
        return <MathNotation key={index} value={part.slice(1, -1)} />;
      }
      if (part.startsWith("\\(") && part.endsWith("\\)")) {
        return <MathNotation key={index} value={part.slice(2, -2)} />;
      }
      return <Fragment key={index}>{part}</Fragment>;
    });
}

function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index]?.trim() ?? "";
    if (!line) {
      index += 1;
      continue;
    }
    if (line.startsWith("$$") && line.endsWith("$$") && line.length > 4) {
      blocks.push({ kind: "math", text: line.slice(2, -2).trim() });
      index += 1;
      continue;
    }
    if (line.startsWith("\\[") && line.endsWith("\\]") && line.length > 4) {
      blocks.push({ kind: "math", text: line.slice(2, -2).trim() });
      index += 1;
      continue;
    }
    if (line.startsWith(">")) {
      const quote: string[] = [];
      while (index < lines.length) {
        const next = lines[index]?.trim() ?? "";
        if (!next.startsWith(">")) break;
        quote.push(next.replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ kind: "quote", text: quote.join(" ") });
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = (lines[index]?.trim() ?? "").match(/^\d+\.\s+(.+)$/);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ kind: "ordered-list", items });
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (index < lines.length) {
      const next = lines[index]?.trim() ?? "";
      if (
        !next
        || /^\d+\.\s+/.test(next)
        || (next.startsWith("$$") && next.endsWith("$$"))
        || (next.startsWith("\\[") && next.endsWith("\\]"))
      ) break;
      paragraph.push(next);
      index += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
  }
  return blocks;
}

export function LearningMarkdown({ children }: { children: string }) {
  return <div className="intervention-explanation">
    {parseBlocks(children).map((block, index) => {
      if (block.kind === "math") {
        return <div className="intervention-display-math" key={index}><MathNotation value={block.text} display /></div>;
      }
      if (block.kind === "ordered-list") {
        return <ol key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{inlineContent(item)}</li>)}</ol>;
      }
      if (block.kind === "quote") {
        return <blockquote key={index}>{inlineContent(block.text)}</blockquote>;
      }
      return <p key={index}>{inlineContent(block.text)}</p>;
    })}
  </div>;
}
