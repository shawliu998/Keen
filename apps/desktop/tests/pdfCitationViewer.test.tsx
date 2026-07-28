import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  LearningCoreDocumentContentError,
  LearningCoreResponseError,
  type AnswerCitation,
  type LearningCoreClient,
} from "@keen/api-client";

const pdfMocks = vi.hoisted(() => ({
  getDocument: vi.fn(),
  loadRuntime: vi.fn(),
}));

vi.mock("../src/features/conversation/pdfRuntimeLoader", () => ({ loadPdfRuntime: pdfMocks.loadRuntime }));

import { PdfCitationViewer, calculateCitationHighlight } from "../src/features/conversation/PdfCitationViewer";

const bbox = {
  x0: 100,
  y0: 100,
  x1: 200,
  y1: 150,
  pageWidth: 600,
  pageHeight: 800,
  coordinateSystem: "pdf_bottom_left" as const,
};
const citation: AnswerCitation = {
  citationId: "citation-1",
  sourceIndex: 1,
  chunkId: "chunk-1",
  documentId: "doc-1",
  documentName: "Fixture.pdf",
  pageNumber: 4,
  sectionPath: ["Section"],
  excerpt: "Original source excerpt",
  bbox,
};

function clientWithContent(result: ArrayBuffer | Error): LearningCoreClient {
  return {
    getDocumentContent: vi.fn(async () => {
      if (result instanceof Error) throw result;
      return { data: result, contentType: "application/pdf" as const };
    }),
  } as unknown as LearningCoreClient;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function installPdfMock(viewBox = [0, 0, 600, 800], renderPromise: Promise<void> = Promise.resolve()) {
  const width = Math.abs(viewBox[2] - viewBox[0]);
  const height = Math.abs(viewBox[3] - viewBox[1]);
  const renderTask = { promise: renderPromise, cancel: vi.fn() };
  const page = {
    getViewport: vi.fn(({ scale }: { scale: number }) => ({
      width: width * scale,
      height: height * scale,
      viewBox,
      convertToViewportRectangle: ([x0, y0, x1, y1]: number[]) => [x0 * scale, (viewBox[3] - y0) * scale, x1 * scale, (viewBox[3] - y1) * scale],
    })),
    render: vi.fn(() => renderTask),
    cleanup: vi.fn(),
  };
  const pdf = { numPages: 8, getPage: vi.fn(async () => page), destroy: vi.fn(async () => undefined) };
  const loadingTask = { promise: Promise.resolve(pdf), destroy: vi.fn(async () => undefined) };
  pdfMocks.getDocument.mockReturnValue(loadingTask);
  return { page, pdf, loadingTask };
}

beforeEach(() => {
  pdfMocks.getDocument.mockReset();
  pdfMocks.loadRuntime.mockReset();
  pdfMocks.loadRuntime.mockResolvedValue({ createPdfLoadingTask: pdfMocks.getDocument });
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: vi.fn(() => ({})) });
});

describe("PDF citation viewer", () => {
  it("converts bottom-left geometry through the PDF.js viewport, including CropBox origin", () => {
    const zeroOrigin = {
      viewBox: [0, 0, 600, 800],
      convertToViewportRectangle: vi.fn(() => [50, 350, 100, 325]),
    };
    expect(calculateCitationHighlight(bbox, zeroOrigin)).toEqual({ left: 50, top: 325, width: 50, height: 25 });
    expect(zeroOrigin.convertToViewportRectangle).toHaveBeenCalledWith([100, 100, 200, 150]);

    const croppedRotated = {
      viewBox: [10, 20, 610, 820],
      convertToViewportRectangle: vi.fn(() => [700, 100, 650, 200]),
    };
    expect(calculateCitationHighlight(bbox, croppedRotated)).toEqual({ left: 650, top: 100, width: 50, height: 100 });
    expect(croppedRotated.convertToViewportRectangle).toHaveBeenCalledWith([110, 120, 210, 170]);
  });

  it("fetches with the client, renders only the cited page, and draws stored geometry", async () => {
    const { pdf, page } = installPdfMock();
    const client = clientWithContent(new TextEncoder().encode("%PDF-fixture").buffer);
    render(<PdfCitationViewer citation={citation} client={client} onClose={vi.fn()} />);

    expect(await screen.findByText("Citation highlighted from stored PDF geometry")).toBeInTheDocument();
    expect(client.getDocumentContent).toHaveBeenCalledWith("doc-1", { signal: expect.any(AbortSignal) });
    expect(pdf.getPage).toHaveBeenCalledTimes(1);
    expect(pdf.getPage).toHaveBeenCalledWith(4);
    expect(page.render).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Citation highlight")).toBeInTheDocument();
  });

  it("locates the page without inventing a highlight when geometry is missing or mismatched", async () => {
    installPdfMock();
    const client = clientWithContent(new TextEncoder().encode("%PDF-fixture").buffer);
    const first = render(<PdfCitationViewer citation={{ ...citation, bbox: null }} client={client} onClose={vi.fn()} />);
    expect(await screen.findByText("Page located; highlight unavailable")).toBeInTheDocument();
    expect(screen.getByText(/Geometry was not extracted/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Citation highlight")).not.toBeInTheDocument();
    first.unmount();

    installPdfMock([0, 0, 700, 800]);
    render(<PdfCitationViewer citation={citation} client={client} onClose={vi.fn()} />);
    expect(await screen.findByText(/Stored citation geometry does not match/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Citation highlight")).not.toBeInTheDocument();
  });

  it("shows offline, missing-document, and non-PDF failures explicitly", async () => {
    const offline = render(<PdfCitationViewer citation={citation} client={null} onClose={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("learning core is offline");
    expect(screen.getByText("Citation excerpt · PDF page unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Page located; highlight unavailable")).not.toBeInTheDocument();
    expect(pdfMocks.getDocument).not.toHaveBeenCalled();
    offline.unmount();

    const missing = new LearningCoreResponseError(404, null, null);
    const missingView = render(<PdfCitationViewer citation={citation} client={clientWithContent(missing)} onClose={vi.fn()} />);
    expect(await screen.findByText(/source document is no longer available/)).toBeInTheDocument();
    expect(screen.queryByText("Page located; highlight unavailable")).not.toBeInTheDocument();
    missingView.unmount();

    const nonPdf = new LearningCoreDocumentContentError("non_pdf");
    render(<PdfCitationViewer citation={citation} client={clientWithContent(nonPdf)} onClose={vi.fn()} />);
    expect(await screen.findByText(/does not point to a PDF document/)).toBeInTheDocument();
  });

  it("rejects malicious page dimensions before allocating or rendering a canvas", async () => {
    const { page } = installPdfMock([0, 0, 100_000, 100_000]);
    render(<PdfCitationViewer citation={citation} client={clientWithContent(new TextEncoder().encode("%PDF-fixture").buffer)} onClose={vi.fn()} />);
    expect(await screen.findByText(/exceeds Keen's safe canvas limits/)).toBeInTheDocument();
    expect(page.render).not.toHaveBeenCalled();
    expect(screen.queryByText("Page located; highlight unavailable")).not.toBeInTheDocument();
  });

  it("does not create a loading task when closed during the lazy runtime import", async () => {
    const runtime = deferred<{ createPdfLoadingTask: typeof pdfMocks.getDocument }>();
    pdfMocks.loadRuntime.mockReturnValue(runtime.promise);
    const client = clientWithContent(new TextEncoder().encode("%PDF-fixture").buffer);
    const view = render(<PdfCitationViewer citation={citation} client={client} onClose={vi.fn()} />);
    await waitFor(() => expect(pdfMocks.loadRuntime).toHaveBeenCalled());
    const signal = (client.getDocumentContent as ReturnType<typeof vi.fn>).mock.calls[0]?.[1].signal as AbortSignal;
    view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => runtime.resolve({ createPdfLoadingTask: pdfMocks.getDocument }));
    expect(pdfMocks.getDocument).not.toHaveBeenCalled();
  });

  it("destroys a loading task without leaking cleanup rejection when closed during load", async () => {
    const loading = deferred<ReturnType<typeof installPdfMock>["pdf"]>();
    const destroy = vi.fn(async () => { throw new Error("already destroyed"); });
    pdfMocks.getDocument.mockReturnValue({ promise: loading.promise, destroy });
    const view = render(<PdfCitationViewer citation={citation} client={clientWithContent(new TextEncoder().encode("%PDF-fixture").buffer)} onClose={vi.fn()} />);
    await waitFor(() => expect(pdfMocks.getDocument).toHaveBeenCalled());
    view.unmount();
    await waitFor(() => expect(destroy).toHaveBeenCalledTimes(1));
  });

  it("cancels page rendering and destroys the loading task when closed during render", async () => {
    const rendering = deferred<void>();
    const { page, loadingTask } = installPdfMock(undefined, rendering.promise);
    const view = render(<PdfCitationViewer citation={citation} client={clientWithContent(new TextEncoder().encode("%PDF-fixture").buffer)} onClose={vi.fn()} />);
    await waitFor(() => expect(page.render).toHaveBeenCalled());
    view.unmount();
    expect(page.render.mock.results[0].value.cancel).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(loadingTask.destroy).toHaveBeenCalledTimes(1));
  });

  it("retries an authenticated page load after a recoverable failure", async () => {
    installPdfMock();
    const getDocumentContent = vi.fn()
      .mockRejectedValueOnce(new LearningCoreDocumentContentError("invalid_body"))
      .mockResolvedValue({ data: new TextEncoder().encode("%PDF-fixture").buffer, contentType: "application/pdf" });
    const client = { getDocumentContent } as unknown as LearningCoreClient;
    render(<PdfCitationViewer citation={citation} client={client} onClose={vi.fn()} />);

    expect(await screen.findByText(/response was incomplete or invalid/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry PDF page" }));
    expect(await screen.findByText("Citation highlighted from stored PDF geometry")).toBeInTheDocument();
    expect(getDocumentContent).toHaveBeenCalledTimes(2);
  });

  it("traps keyboard focus and restores the citation trigger after Escape", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return <><button onClick={() => setOpen(true)}>Open citation</button><button>Outside action</button>{open && <PdfCitationViewer citation={citation} client={null} onClose={() => setOpen(false)} />}</>;
    }
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open citation" });
    trigger.focus();
    fireEvent.click(trigger);
    const close = await screen.findByRole("button", { name: "Close PDF citation" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(close).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
