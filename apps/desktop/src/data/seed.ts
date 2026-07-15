import type { KnowledgeDocument, LearningTask, MemoryItem } from "@keen/domain";

export const learningTasks: LearningTask[] = [
  { id: "t1", title: "Review eigenvectors before Chapter 6", course: "Linear Algebra", reason: "You missed this concept twice yesterday. It unlocks Chapter 6 and the exam begins in 4 days.", due: "Today, 10:30 AM", durationMinutes: 18, concepts: ["Eigenvectors", "Basis"], mastery: 42, status: "today" },
  { id: "t2", title: "Active recall: cellular respiration", course: "Biology 101", reason: "This review is due under your spaced repetition schedule.", due: "Today, 2:00 PM", durationMinutes: 12, concepts: ["ATP", "Krebs cycle"], mastery: 68, status: "today" },
  { id: "t3", title: "Practice confidence intervals", course: "Statistics", reason: "Your quiz confidence was high, but accuracy remained below your target.", due: "Tomorrow", durationMinutes: 25, concepts: ["Sampling", "Z-score"], mastery: 57, status: "upcoming" },
  { id: "t4", title: "Revisit gradient descent", course: "Machine Learning", reason: "This task was not completed and is a prerequisite for optimization methods.", due: "Yesterday", durationMinutes: 15, concepts: ["Gradients"], mastery: 35, status: "overdue" },
  { id: "t5", title: "Chapter 3 retrieval practice", course: "Biology 101", reason: "Completed after two successful recall rounds.", due: "Jul 13", durationMinutes: 20, concepts: ["Cell membrane"], mastery: 81, status: "completed" },
];

export const documents: KnowledgeDocument[] = [
  { id: "d1", name: "Linear Algebra — Chapter 5.pdf", course: "Linear Algebra", type: "PDF", pages: 48, importedAt: "Today, 9:42 AM", status: "indexed", parser: "PyMuPDF4LLM", embeddingModel: "text-embedding-3-small" },
  { id: "d2", name: "Cellular Respiration Notes.md", course: "Biology 101", type: "Markdown", pages: 7, importedAt: "Yesterday", status: "indexed", parser: "Markdown", embeddingModel: "text-embedding-3-small" },
  { id: "d3", name: "Statistics Formula Sheet.pdf", course: "Statistics", type: "PDF", pages: 12, importedAt: "Jul 12", status: "embedding", parser: "PyMuPDF4LLM", embeddingModel: "nomic-embed-text" },
  { id: "d4", name: "Lecture Scan 06.png", course: "Linear Algebra", type: "Image", pages: 1, importedAt: "Jul 11", status: "failed", parser: "OCR", embeddingModel: "text-embedding-3-small" },
  { id: "d5", name: "Optimization notes.txt", course: "Machine Learning", type: "TXT", pages: 4, importedAt: "Jul 8", status: "needs-reindex", parser: "Plain text", embeddingModel: "nomic-embed-text" },
];

export const memories: MemoryItem[] = [
  { id: "m1", kind: "goal", statement: "Build a confident foundation in linear algebra before the August exam.", evidence: "Set by you on Jul 3", enabled: true },
  { id: "m2", kind: "preference", statement: "Prefers a worked example before formal notation.", evidence: "Observed in 6 learning sessions", enabled: true },
  { id: "m3", kind: "misconception", statement: "Sometimes treats eigenvectors as unique instead of directionally equivalent.", evidence: "Quiz 14 · Questions 2 and 5", enabled: true },
  { id: "m4", kind: "mastery", statement: "Strong recall of matrix multiplication and row reduction.", evidence: "92% across 23 recent answers", enabled: true },
  { id: "m5", kind: "weakness", statement: "Needs more practice connecting geometric and algebraic interpretations.", evidence: "Deep Learn session · Jul 12", enabled: true },
  { id: "m6", kind: "inference", statement: "Focus is strongest during 20–30 minute sessions in the morning.", evidence: "Inferred from 18 sessions", enabled: false },
];

export const recentConversations = ["Why eigenvectors keep their direction", "Build a review plan for Biology", "Confidence intervals, step by step"];
export const recentSessions = ["Eigenvectors & eigenspaces", "Cellular respiration"];
