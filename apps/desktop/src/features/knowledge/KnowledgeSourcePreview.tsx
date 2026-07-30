import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, FileText, LoaderCircle } from "lucide-react";
import {
  LearningCoreDocumentContentError,
  LearningCoreResponseError,
  type LearningCoreClient,
} from "@keen/api-client";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import { Button } from "@keen/ui";
import { loadPdfRuntime } from "../conversation/pdfRuntimeLoader";
import type { DisplayDocument } from "./documentJobs";

type PreviewStatus = "idle" | "loading" | "rendering" | "ready" | "error";

function previewError(error: unknown): string {
  if (error instanceof LearningCoreResponseError) {
    if (error.status === 404) return "The stored PDF is no longer available. Re-import it before retrying.";
    return error.detail?.message ?? "The learning core could not return this PDF.";
  }
  if (error instanceof LearningCoreDocumentContentError) {
    if (error.reason === "too_large") return "This PDF exceeds Keen's 32 MiB preview limit.";
    if (error.reason === "non_pdf") return "This source is not a PDF, so no document preview was opened.";
    return "The PDF response was incomplete or invalid.";
  }
  if (error instanceof Error && error.name === "AbortError") return "PDF loading was cancelled.";
  return "Keen could not safely render this PDF.";
}

function EmptyPreview({ title, body }: { title: string; body: string }) {
  return <div className="knowledge-preview-empty">
    <span><FileText size={24} aria-hidden="true" /></span>
    <strong>{title}</strong>
    <p>{body}</p>
  </div>;
}

export function KnowledgeSourcePreview({
  document,
  demo,
  client,
}: {
  document: DisplayDocument;
  demo: boolean;
  client: LearningCoreClient | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const isPdf = document.type === "PDF";
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [status, setStatus] = useState<PreviewStatus>(() => demo || !isPdf ? "idle" : "loading");
  const [error, setError] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [retryKey, setRetryKey] = useState(0);
  const [renderWidth, setRenderWidth] = useState(0);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const update = () => setRenderWidth(Math.max(0, Math.floor(stage.clientWidth)));
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (demo || !isPdf || !client) return;
    const controller = new AbortController();
    let disposed = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    void (async () => {
      try {
        setStatus("loading");
        setError(null);
        const content = await client.getDocumentContent(document.id, { signal: controller.signal });
        if (disposed) return;
        const { createPdfLoadingTask } = await loadPdfRuntime();
        if (disposed) return;
        loadingTask = createPdfLoadingTask(new Uint8Array(content.data));
        const loadedPdf = await loadingTask.promise;
        if (disposed) {
          await loadedPdf.destroy();
          return;
        }
        setPdf(loadedPdf);
      } catch (caught) {
        if (disposed || (caught instanceof Error && caught.name === "AbortError")) return;
        setStatus("error");
        setError(previewError(caught));
      }
    })();
    return () => {
      disposed = true;
      controller.abort();
      if (loadingTask) void loadingTask.destroy().catch(() => undefined);
    };
  }, [client, demo, document.id, isPdf, retryKey]);

  useEffect(() => {
    if (!pdf || renderWidth === 0) return;
    let disposed = false;
    let page: PDFPageProxy | null = null;
    let renderTask: RenderTask | null = null;
    void (async () => {
      try {
        setStatus("rendering");
        page = await pdf.getPage(pageNumber);
        if (disposed) return;
        const baseViewport = page.getViewport({ scale: 1 });
        const availableWidth = Math.max(320, Math.min(940, renderWidth - 48));
        const scale = Math.max(0.5, Math.min(1.5, availableWidth / baseViewport.width));
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d", { alpha: false });
        if (!canvas || !context) throw new Error("canvas unavailable");
        const outputScale = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.ceil(viewport.width * outputScale);
        canvas.height = Math.ceil(viewport.height * outputScale);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        renderTask = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
        });
        await renderTask.promise;
        if (!disposed) setStatus("ready");
      } catch (caught) {
        if (disposed || (caught instanceof Error && caught.name === "RenderingCancelledException")) return;
        setStatus("error");
        setError(previewError(caught));
      }
    })();
    return () => {
      disposed = true;
      try {
        renderTask?.cancel();
        page?.cleanup();
      } catch {
        // A completed PDF.js render may already have released its page resources.
      }
    };
  }, [pageNumber, pdf, renderWidth]);

  useEffect(() => () => {
    if (pdf) void pdf.destroy().catch(() => undefined);
  }, [pdf]);

  const retry = () => {
    setPdf(null);
    setError(null);
    setStatus("loading");
    setRetryKey((key) => key + 1);
  };

  return <div className="knowledge-preview-stage" ref={stageRef}>
    {demo ? <EmptyPreview title="Preview unavailable" body="This sample row contains organization metadata only. Keen did not read or store a file." /> : !isPdf ? <EmptyPreview title={`${document.type} preview is not available yet`} body="The source can still be searched and used by learning flows when its indexing state allows it." /> : null}
    {!demo && isPdf && (status === "loading" || status === "rendering") ? <div className="knowledge-preview-state" role="status"><LoaderCircle className="spin" size={21} /><strong>{status === "loading" ? "Loading authenticated PDF…" : `Rendering page ${pageNumber}…`}</strong><span>The file remains local to Keen's authenticated learning service.</span></div> : null}
    {!demo && isPdf && status === "error" ? <div className="knowledge-preview-state error" role="alert"><AlertTriangle size={21} /><strong>PDF preview unavailable</strong><span>{error}</span><Button onClick={retry}>Retry preview</Button></div> : null}
    {!demo && isPdf ? <div className={`knowledge-pdf-page ${status === "ready" ? "is-ready" : ""}`}><canvas ref={canvasRef} aria-label={`PDF page ${pageNumber}`} /></div> : null}
    {!demo && isPdf && pdf ? <div className="knowledge-preview-pagination" aria-label="PDF pagination">
      <Button aria-label="Previous PDF page" disabled={pageNumber <= 1 || status === "rendering"} onClick={() => setPageNumber((page) => Math.max(1, page - 1))}><ChevronLeft size={15} /></Button>
      <span>Page {pageNumber} of {pdf.numPages}</span>
      <Button aria-label="Next PDF page" disabled={pageNumber >= pdf.numPages || status === "rendering"} onClick={() => setPageNumber((page) => Math.min(pdf.numPages, page + 1))}><ChevronRight size={15} /></Button>
    </div> : null}
  </div>;
}
