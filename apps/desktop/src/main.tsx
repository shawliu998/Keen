import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "@keen/design-tokens/tokens.css";
import "./styles.css";
import "./features.css";
import "./features-extra.css";
import "./ui-refresh.css";
import "./deeptutor-pages.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

const preferredColorScheme = window.matchMedia("(prefers-color-scheme: dark)");
const syncPreferredColorScheme = () => {
  document.documentElement.dataset.theme = preferredColorScheme.matches ? "dark" : "light";
};
syncPreferredColorScheme();
preferredColorScheme.addEventListener("change", syncPreferredColorScheme);

if (import.meta.env.VITE_NATIVE_UI_AUDIT === "true") {
  const probe = document.createElement("output");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const updateProbe = () => {
    const visualViewport = window.visualViewport;
    const report = [
      `inner=${window.innerWidth}x${window.innerHeight}`,
      `client=${document.documentElement.clientWidth}x${document.documentElement.clientHeight}`,
      `visual=${visualViewport ? `${visualViewport.width}x${visualViewport.height}` : "unavailable"}`,
      `dpr=${window.devicePixelRatio}`,
      `screen=${window.screen.width}x${window.screen.height}`,
      `reduced=${reducedMotion.matches}`,
    ].join("; ");
    probe.textContent = report;
    document.title = `Keen UI Audit — ${report}`;
  };

  probe.setAttribute("aria-label", "Native UI audit metrics");
  probe.style.cssText = "position:fixed;z-index:2147483647;top:8px;left:50%;transform:translateX(-50%);padding:6px 10px;border:1px solid #d0d5dd;border-radius:6px;background:#fff;color:#101828;font:12px/1.4 ui-monospace,monospace;white-space:nowrap";
  document.body.append(probe);
  window.addEventListener("resize", updateProbe);
  reducedMotion.addEventListener("change", updateProbe);
  updateProbe();
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter><App /></BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
