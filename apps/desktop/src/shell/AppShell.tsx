import { useEffect, useLayoutEffect, useMemo } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Toolbar } from "./Toolbar";
import { Inspector } from "./Inspector";
import { CommandPalette } from "./CommandPalette";
import "./shell-deeptutor.css";
import { useAppStore } from "../state/appStore";
import { useAgentRuntime } from "../services/AgentRuntimeProvider";
import {
  isSameAgentActivityContext,
  type AgentActivityContext,
} from "../features/agent/useAgentRunLifecycle";

const SAFE_ACTIVITY_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

const decodeActivitySegment = (segment: string): string | null => {
  try {
    const decoded = decodeURIComponent(segment);
    return SAFE_ACTIVITY_IDENTIFIER.test(decoded) ? decoded : null;
  } catch {
    return null;
  }
};

export function parseActivityContext(pathname: string): AgentActivityContext {
  if (!pathname) return null;

  const normalizedPath = pathname.split("?")[0].split("#")[0];
  const segments = normalizedPath.split("/").filter(Boolean);

  if (segments[0] === "conversation") {
    if (!segments[1] || segments[1] === "new") {
      return null;
    }
    const conversationId = decodeActivitySegment(segments[1]);
    return conversationId ? { conversationId } : null;
  }

  if (segments[0] === "deep-learn") {
    if (!segments[1]) {
      return null;
    }
    const studySessionId = decodeActivitySegment(segments[1]);
    return studySessionId ? { studySessionId } : null;
  }

  return null;
}

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, inspectorOpen, setCommandOpen } = useAppStore();
  const runtime = useAgentRuntime();
  const activityContext = useMemo(() => parseActivityContext(location.pathname), [location.pathname]);
  const { setActivityContext } = runtime;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.metaKey) return;
      const key = event.key.toLowerCase();
      if (key === "k") { event.preventDefault(); setCommandOpen(true); }
      if (key === "n") { event.preventDefault(); navigate("/?mode=ask"); }
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
      if (payload === "new-conversation") navigate("/?mode=ask");
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

  useLayoutEffect(() => {
    setActivityContext(activityContext);
  }, [activityContext, setActivityContext]);
  const activityContextReady = runtime.activityContextReady
    && isSameAgentActivityContext(activityContext, runtime.activityContext);

  return (
    <div className={`app-shell deeptutor-shell ${sidebarCollapsed ? "is-collapsed" : ""} ${inspectorOpen ? "drawer-open" : ""}`}>
      <Sidebar />
      <main className="main-area">
        <Toolbar key={location.pathname} />
        <div className="page-viewport"><Outlet /></div>
      </main>
      {inspectorOpen && <Inspector activityContextReady={activityContextReady} />}
      <CommandPalette />
    </div>
  );
}
