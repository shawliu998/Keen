import { useEffect } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Toolbar } from "./Toolbar";
import { Inspector } from "./Inspector";
import { CommandPalette } from "./CommandPalette";
import { useAppStore } from "../state/appStore";

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, inspectorOpen, setCommandOpen } = useAppStore();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.metaKey) return;
      const key = event.key.toLowerCase();
      if (key === "k") { event.preventDefault(); setCommandOpen(true); }
      if (key === "n") { event.preventDefault(); navigate("/conversation/new"); }
      if (key === ",") { event.preventDefault(); navigate("/settings"); }
      if (event.shiftKey && key === "l") { event.preventDefault(); navigate("/feed"); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, setCommandOpen]);

  useEffect(() => {
    if (!isTauri()) return undefined;
    let disposed = false;
    let unlisten: UnlistenFn | undefined;
    void listen<string>("keen://menu", ({ payload }) => {
      if (payload === "new-conversation") navigate("/conversation/new");
      if (payload === "import-source") navigate("/knowledge?import=true");
      if (payload === "open-settings") navigate("/settings");
      if (payload === "open-learning-feed") navigate("/feed");
      if (payload === "command-palette") setCommandOpen(true);
    }).then((cleanup) => {
      if (disposed) cleanup();
      else unlisten = cleanup;
    });
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [navigate, setCommandOpen]);

  return (
    <div className={`app-shell ${sidebarCollapsed ? "is-collapsed" : ""} ${inspectorOpen ? "with-inspector" : ""}`}>
      <Sidebar />
      <main className="main-area">
        <Toolbar key={location.pathname} />
        <div className="page-viewport"><Outlet /></div>
      </main>
      {inspectorOpen && <Inspector />}
      <CommandPalette />
    </div>
  );
}
