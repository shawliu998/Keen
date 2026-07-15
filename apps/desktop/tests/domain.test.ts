import { documentSchema, learningTaskSchema } from "@keen/domain";

describe("domain validation", () => {
  it("rejects impossible mastery values", () => {
    const result = learningTaskSchema.safeParse({ id: "x", title: "Review", course: "Math", reason: "Due", due: "Today", durationMinutes: 10, concepts: [], mastery: 120, status: "today" });
    expect(result.success).toBe(false);
  });

  it("accepts an indexed PDF document", () => {
    const result = documentSchema.safeParse({ id: "d", name: "notes.pdf", course: "Math", type: "PDF", pages: 10, importedAt: "Today", status: "indexed", parser: "PyMuPDF", embeddingModel: "local" });
    expect(result.success).toBe(true);
  });
});
