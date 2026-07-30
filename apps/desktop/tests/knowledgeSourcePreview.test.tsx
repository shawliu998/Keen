import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { LearningCoreClient } from "@keen/api-client";
import type { DisplayDocument } from "../src/features/knowledge/documentJobs";
import { KnowledgeSourcePreview } from "../src/features/knowledge/KnowledgeSourcePreview";

const pdfMocks = vi.hoisted(() => ({ loadRuntime: vi.fn() }));

vi.mock("../src/features/conversation/pdfRuntimeLoader", () => ({ loadPdfRuntime: pdfMocks.loadRuntime }));

const source: DisplayDocument = {
  id: "doc-pdf",
  name: "Linear Algebra.pdf",
  course: "Linear Algebra",
  type: "PDF",
  pages: 2,
  importedAt: "Today",
  status: "indexed",
  parser: "pdf",
  embeddingModel: "fixture",
  chunks: 4,
  job: null,
  courseIds: ["course-linear"],
  courseNames: ["Linear Algebra"],
  retrievalWarning: null,
  embeddingStatus: "ready",
  providerConfigured: true,
};

beforeEach(() => {
  pdfMocks.loadRuntime.mockReset();
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(760);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D);
});

afterEach(() => {
  vi.restoreAllMocks();
});

it("keeps Browser Demo source rows metadata-only", () => {
  const getDocumentContent = vi.fn();
  render(<KnowledgeSourcePreview document={source} demo client={{ getDocumentContent } as unknown as LearningCoreClient} />);

  expect(screen.getByText("Preview unavailable")).toBeInTheDocument();
  expect(screen.getByText(/did not read or store a file/i)).toBeInTheDocument();
  expect(getDocumentContent).not.toHaveBeenCalled();
});

it("loads an authenticated PDF and renders requested pages", async () => {
  const user = userEvent.setup();
  const renderTask = { promise: Promise.resolve(), cancel: vi.fn() };
  const page = {
    getViewport: vi.fn(({ scale }: { scale: number }) => ({ width: 612 * scale, height: 792 * scale })),
    render: vi.fn(() => renderTask),
    cleanup: vi.fn(),
  };
  const pdf = { numPages: 2, getPage: vi.fn(async () => page), destroy: vi.fn(async () => undefined) };
  const loadingTask = { promise: Promise.resolve(pdf), destroy: vi.fn(async () => undefined) };
  pdfMocks.loadRuntime.mockResolvedValue({ createPdfLoadingTask: vi.fn(() => loadingTask) });
  const getDocumentContent = vi.fn(async () => ({ data: new ArrayBuffer(8), contentType: "application/pdf" as const }));

  render(<KnowledgeSourcePreview document={source} demo={false} client={{ getDocumentContent } as unknown as LearningCoreClient} />);

  await waitFor(() => expect(screen.getByLabelText("PDF page 1").parentElement).toHaveClass("is-ready"));
  expect(getDocumentContent).toHaveBeenCalledWith("doc-pdf", expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(pdf.getPage).toHaveBeenCalledWith(1);

  await user.click(screen.getByRole("button", { name: "Next PDF page" }));
  await waitFor(() => expect(pdf.getPage).toHaveBeenCalledWith(2));
  expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
});
