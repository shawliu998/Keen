import { Command, PanelRightClose, PanelRightOpen } from "lucide-react";
import { useLocation } from "react-router-dom";
import { IconButton } from "@keen/ui";
import { useAppStore } from "../state/appStore";
import { AgentStatusButton } from "../features/agent-activity/AgentStatusButton";
import { useAgentRuntime } from "../services/AgentRuntimeProvider";
import { LearningCoreStatus } from "../components/LearningCoreStatus";
import { useLearningCore } from "../services/LearningCoreProvider";

const routes: Record<string, { title: string; demo?: boolean }> = {
  "/": { title: "Home" }, "/feed": { title: "Learning Feed" }, "/knowledge": { title: "Knowledge Base" },
  "/history": { title: "History" },
  "/quiz": { title: "Quiz", demo: true }, "/review": { title: "Review" }, "/flashcards": { title: "Review" },
  "/planner": { title: "Study Planner", demo: true }, "/memory": { title: "Learner Memory" },
  "/visualize": { title: "Visualize", demo: true }, "/settings": { title: "Settings" },
};

export function Toolbar() {
  const { pathname, search } = useLocation();
  const {
    drawerView,
    inspector,
    inspectorOpen,
    closeDrawer,
    openDrawer,
    setCommandOpen,
  } = useAppStore();
  const runtime = useAgentRuntime();
  const { status } = useLearningCore();
  const route = pathname === "/" && new URLSearchParams(search).has("mode")
    ? { title: "New learning" }
    : pathname.startsWith("/conversation")
    ? { title: "Conversation" }
    : pathname.startsWith("/deep-learn")
      ? { title: "Deep Learn" }
      : routes[pathname] ?? { title: "Keen" };
  return (
    <header className={`toolbar shell-toolbar ${pathname === "/" ? "toolbar-home" : ""}`} data-tauri-drag-region>
      <div className="toolbar-title"><strong>{route.title}</strong>{route.demo && <span className="toolbar-demo-label">UI demo</span>}{status !== "healthy" && status !== "demo" ? <LearningCoreStatus status={status} compact /> : null}</div>
      <div className="toolbar-actions">
        <IconButton label="Open command palette" onClick={() => setCommandOpen(true)}><Command size={17} /></IconButton>
        <AgentStatusButton
          runtime={runtime}
          pressed={inspectorOpen && drawerView === "activity"}
          onClick={() => inspectorOpen && drawerView === "activity" ? closeDrawer() : openDrawer("activity")}
        />
        {inspector ? (
          <IconButton
            className="context-drawer-trigger"
            label={inspectorOpen && drawerView === (inspector.kind ?? "sources") ? "Close selected context" : "Open selected context"}
            aria-pressed={inspectorOpen && drawerView === (inspector.kind ?? "sources")}
            onClick={() => inspectorOpen && drawerView === (inspector.kind ?? "sources")
              ? closeDrawer()
              : openDrawer(inspector.kind ?? "sources")}
          >
            {inspectorOpen && drawerView === (inspector.kind ?? "sources")
              ? <PanelRightClose size={17} />
              : <PanelRightOpen size={17} />}
          </IconButton>
        ) : null}
      </div>
    </header>
  );
}
