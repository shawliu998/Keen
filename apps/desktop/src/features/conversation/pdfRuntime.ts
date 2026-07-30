import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export function createPdfLoadingTask(data: Uint8Array) {
  return getDocument({
    data,
    isEvalSupported: false,
    stopAtErrors: true,
    useWasm: false,
  });
}
