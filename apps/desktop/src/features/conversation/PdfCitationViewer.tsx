import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AlertTriangle, FileSearch, LoaderCircle, X } from "lucide-react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import {
  LearningCoreDocumentContentError,
  LearningCoreResponseError,
  type AnswerCitation,
  type LearningCoreClient,
} from "@keen/api-client";
import { loadPdfRuntime } from "./pdfRuntimeLoader";

type ViewerStatus = "loading" | "rendering" | "ready" | "error";
type CitationBbox = NonNullable<AnswerCitation["bbox"]>;
class CitationPageUnavailableError extends Error {}
class CitationPageTooLargeError extends Error {}
const MAX_CANVAS_EDGE = 8192;
const MAX_CANVAS_PIXELS = 16 * 1024 * 1024;

export function calculateCitationHighlight(
  bbox: CitationBbox,
  viewport: { viewBox: number[]; convertToViewportRectangle: (rectangle: [number, number, number, number]) => number[] },
): CSSProperties {
  const [originX, originY] = viewport.viewBox;
  const [x0, y0, x1, y1] = viewport.convertToViewportRectangle([
    bbox.x0 + originX,
    bbox.y0 + originY,
    bbox.x1 + originX,
    bbox.y1 + originY,
  ]);
  return {
    left: Math.min(x0, x1),
    top: Math.min(y0, y1),
    width: Math.abs(x1 - x0),
    height: Math.abs(y1 - y0),
  };
}

function geometryMatchesPage(bbox: CitationBbox, viewBox: number[]): boolean {
  const width = Math.abs(viewBox[2] - viewBox[0]);
  const height = Math.abs(viewBox[3] - viewBox[1]);
  const widthTolerance = Math.max(1, width * 0.005);
  const heightTolerance = Math.max(1, height * 0.005);
  return Math.abs(bbox.pageWidth - width) <= widthTolerance && Math.abs(bbox.pageHeight - height) <= heightTolerance;
}

function viewerError(error: unknown): string {
  if (error instanceof CitationPageUnavailableError) return "The cited page does not exist in this PDF. The stored citation may be stale; re-index the document before retrying.";
  if (error instanceof CitationPageTooLargeError) return "This PDF page exceeds Keen's safe canvas limits and was not rendered. The citation excerpt remains available.";
  if (error instanceof LearningCoreResponseError) {
    if (error.status === 404) return "This source document is no longer available. Re-import it before opening this citation.";
    return error.detail?.message ?? "The learning core could not return this PDF. Retry after the service recovers.";
  }
  if (error instanceof LearningCoreDocumentContentError) {
    if (error.reason === "non_pdf") return "This citation does not point to a PDF document, so the PDF viewer was not opened.";
    if (error.reason === "too_large") return "This PDF is larger than the 32 MiB viewer limit. The citation metadata remains available in the inspector.";
    return "The PDF response was incomplete or invalid. No page was rendered.";
  }
  if (error instanceof Error && error.name === "AbortError") return "PDF loading was cancelled.";
  return "Keen could not safely render this PDF page. The citation excerpt remains available in the inspector.";
}

export function PdfCitationViewer({
  citation,
  client,
  onClose,
}: {
  citation: AnswerCitation;
  client: LearningCoreClient | null;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  const [previousFocus] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null);
  const [status, setStatus] = useState<ViewerStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<CSSProperties | null>(null);
  const [geometryWarning, setGeometryWarning] = useState<string | null>(citation.bbox ? null : "Geometry was not extracted for this citation, so Keen did not invent a highlight.");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!client) return;
    const controller = new AbortController();
    let disposed = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    let pdf: PDFDocumentProxy | null = null;
    let page: PDFPageProxy | null = null;
    let renderTask: RenderTask | null = null;
    let cleanupStarted = false;
    const cleanup = async () => {
      if (cleanupStarted) return;
      cleanupStarted = true;
      try {
        renderTask?.cancel();
      } catch {
        // Rendering may already have completed or cancelled itself.
      }
      try {
        page?.cleanup();
      } catch {
        // Page resources may already have been released by the loading task.
      }
      try {
        if (loadingTask) await loadingTask.destroy();
        else if (pdf) await pdf.destroy();
      } catch {
        // Closing the viewer must not surface cleanup failures as unhandled rejections.
      }
    };
    void (async () => {
      try {
        const content = await client.getDocumentContent(citation.documentId, { signal: controller.signal });
        if (disposed) return;
        const { createPdfLoadingTask } = await loadPdfRuntime();
        if (disposed) return;
        loadingTask = createPdfLoadingTask(new Uint8Array(content.data));
        pdf = await loadingTask.promise;
        if (disposed) return;
        if (citation.pageNumber > pdf.numPages) throw new CitationPageUnavailableError();
        page = await pdf.getPage(citation.pageNumber);
        if (disposed) return;
        setStatus("rendering");
        const baseViewport = page.getViewport({ scale: 1, rotation: 0 });
        const scale = Math.max(0.5, Math.min(1.6, 760 / baseViewport.width));
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d", { alpha: false });
        if (!canvas || !context) throw new Error("canvas unavailable");
        const outputScale = Math.min(window.devicePixelRatio || 1, 2);
        const canvasWidth = Math.ceil(viewport.width * outputScale);
        const canvasHeight = Math.ceil(viewport.height * outputScale);
        if (
          !Number.isFinite(viewport.width)
          || !Number.isFinite(viewport.height)
          || viewport.width <= 0
          || viewport.height <= 0
          || !Number.isSafeInteger(canvasWidth)
          || !Number.isSafeInteger(canvasHeight)
          || canvasWidth <= 0
          || canvasHeight <= 0
          || canvasWidth > MAX_CANVAS_EDGE
          || canvasHeight > MAX_CANVAS_EDGE
          || canvasWidth * canvasHeight > MAX_CANVAS_PIXELS
        ) {
          throw new CitationPageTooLargeError();
        }
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        renderTask = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
        });
        await renderTask.promise;
        if (disposed) return;
        if (citation.bbox && geometryMatchesPage(citation.bbox, baseViewport.viewBox)) {
          setHighlight(calculateCitationHighlight(citation.bbox, viewport));
          setGeometryWarning(null);
        } else if (citation.bbox) {
          setHighlight(null);
          setGeometryWarning("Stored citation geometry does not match this PDF page, so Keen did not draw a potentially incorrect highlight.");
        }
        setStatus("ready");
      } catch (caught) {
        if (disposed || (caught instanceof Error && caught.name === "AbortError")) return;
        setStatus("error");
        setError(viewerError(caught));
      }
    })();

    return () => {
      disposed = true;
      controller.abort();
      void cleanup();
    };
  }, [citation, client, retryKey]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const handleDialogKeyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
      ) ?? []);
      if (!focusable.length) {
        event.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (focusable.length === 1 || (event.shiftKey && (active === first || !dialogRef.current?.contains(active))) || (!event.shiftKey && (active === last || !dialogRef.current?.contains(active)))) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      }
    };
    window.addEventListener("keydown", handleDialogKeyboard);
    return () => {
      window.removeEventListener("keydown", handleDialogKeyboard);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [previousFocus]);

  const visibleStatus = client ? status : "error";
  const visibleError = client ? error : "The learning core is offline. Recover it before loading this authenticated PDF.";
  const retry = () => {
    setStatus("loading");
    setError(null);
    setHighlight(null);
    setGeometryWarning(citation.bbox ? null : "Geometry was not extracted for this citation, so Keen did not invent a highlight.");
    setRetryKey((key) => key + 1);
  };
  const footerTitle = visibleStatus === "ready"
    ? highlight ? "Citation highlighted from stored PDF geometry" : "Page located; highlight unavailable"
    : visibleStatus === "error" ? "Citation excerpt · PDF page unavailable" : "Citation excerpt · page location pending";
  const footerWarning = visibleStatus === "ready" && geometryWarning ? ` ${geometryWarning}` : "";

  return <div className="pdf-viewer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section ref={dialogRef} className="pdf-viewer" role="dialog" aria-modal="true" aria-labelledby="pdf-viewer-title" tabIndex={-1}>
      <header>
        <div><small>Authenticated local PDF · page {citation.pageNumber}</small><strong id="pdf-viewer-title">{citation.documentName}</strong></div>
        <button aria-label="Close PDF citation" onClick={onClose} autoFocus><X size={17} /></button>
      </header>
      <div className="pdf-viewer-stage">
        {(visibleStatus === "loading" || visibleStatus === "rendering") && <div className="pdf-viewer-state" role="status"><LoaderCircle className="spin" size={22} /><strong>{visibleStatus === "loading" ? "Loading authenticated PDF…" : `Rendering page ${citation.pageNumber}…`}</strong><span>Only the cited page will be rendered.</span></div>}
        {visibleStatus === "error" && <div className="pdf-viewer-state error" role="alert"><AlertTriangle size={22} /><strong>PDF page unavailable</strong><span>{visibleError}</span>{client && <button onClick={retry}>Retry PDF page</button>}</div>}
        <div className={`pdf-page ${visibleStatus === "ready" ? "ready" : "pending"}`}>
          <canvas ref={canvasRef} aria-label={`PDF page ${citation.pageNumber}`} />
          {visibleStatus === "ready" && highlight && <span className="pdf-citation-highlight" style={highlight} aria-label="Citation highlight" />}
        </div>
      </div>
      <footer>
        <FileSearch size={15} />
        <div><strong>{footerTitle}</strong><p>{citation.excerpt}{footerWarning}</p></div>
      </footer>
    </section>
  </div>;
}
