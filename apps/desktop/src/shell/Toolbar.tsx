import { ChevronDown, Command, PanelRightClose, PanelRightOpen, Plus } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { IconButton } from "@keen/ui";
import type { AgentMode } from "@keen/domain";
import { useAppStore } from "../state/appStore";
import { LearningCoreStatus } from "../components/LearningCoreStatus";
import { useLearningCore } from "../services/LearningCoreProvider";

const titles: Record<string, string> = {
  "/": "Agent", "/feed": "Learning Feed", "/knowledge": "Knowledge Base", "/quiz": "Quiz & Practice",
  "/flashcards": "Flashcards", "/planner": "Study Planner", "/memory": "Learner Memory", "/visualize": "Visualize", "/settings": "Settings",
};

export function Toolbar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { agentMode, setAgentMode, inspectorOpen, toggleInspector, setCommandOpen } = useAppStore();
  const { status } = useLearningCore();
  const title = pathname.startsWith("/conversation") ? "Conversation" : pathname.startsWith("/deep-learn") ? "Deep Learn" : titles[pathname] ?? "Keen";
  return (
    <header className="toolbar" data-tauri-drag-region>
      <div className="toolbar-title"><strong>{title}</strong><LearningCoreStatus status={status} compact /></div>
      <div className="toolbar-actions">
        <label className="select-control agent-mode" aria-label="Agent mode preview"><select title="Agent routing is unavailable" value={agentMode} onChange={(e) => setAgentMode(e.target.value as AgentMode)} disabled>
          <option>Teach</option><option>Solve</option><option>Review</option><option>Research</option>
        </select><ChevronDown size={14} /></label>
        <button className="context-button" disabled title="Course selector is unavailable"><span className="context-dot" />Demo course<ChevronDown size={14} /></button>
        <IconButton label="Open command palette" onClick={() => setCommandOpen(true)}><Command size={17} /></IconButton>
        <IconButton label={inspectorOpen ? "Close inspector" : "Open inspector"} onClick={toggleInspector}>{inspectorOpen ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}</IconButton>
        <IconButton label="New demo conversation" onClick={() => navigate("/conversation/new")}><Plus size={18} /></IconButton>
      </div>
    </header>
  );
}
