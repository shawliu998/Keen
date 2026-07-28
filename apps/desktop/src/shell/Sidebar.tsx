import { NavLink, useNavigate } from "react-router-dom";
import { CalendarDays, ChevronLeft, ChevronRight, FileStack, History, Home, Plus, Repeat2, Settings } from "lucide-react";
import { IconButton } from "@keen/ui";
import { useAppStore } from "../state/appStore";
import { LearningCoreStatus } from "../components/LearningCoreStatus";
import { useLearningCore } from "../services/LearningCoreProvider";

const primary = [
  ["/", "Home", Home], ["/knowledge", "Knowledge Base", FileStack], ["/feed", "Learning Feed", CalendarDays], ["/history", "History", History],
  ["/review", "Review", Repeat2],
] as const;
export function Sidebar() {
  const navigate = useNavigate();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const { status } = useLearningCore();
  const nav = (items: typeof primary) => items.map(([to, label, Icon]) => (
    <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-row ${isActive ? "active" : ""}`} title={label}>
      <Icon size={17} aria-hidden /><span>{label}</span>
    </NavLink>
  ));
  return (
    <aside className="sidebar shell-sidebar" aria-label="Primary navigation">
      <div className="traffic-space" data-tauri-drag-region />
      <div className="brand-row shell-brand-row">
        <div className="shell-brand-lockup">
          <span className="brand-mark" aria-hidden="true"><img src="/brand/keen-mark.svg" alt="" /></span>
          <span className="brand-wordmark"><img src="/brand/keen-wordmark.svg" alt="Keen" /></span>
        </div>
        <IconButton label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={toggleSidebar}>
          {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </IconButton>
      </div>
      <button className="new-button shell-new-learning" aria-label="New learning" onClick={() => navigate("/?mode=ask")}><Plus size={17} aria-hidden="true" /><span>New learning</span><kbd>⌘N</kbd></button>
      <nav className="sidebar-scroll shell-primary-nav">{nav(primary)}</nav>
      <div className="sidebar-footer">
        <div className="agent-status shell-agent-status" aria-live="polite"><LearningCoreStatus status={status} compact={status === "demo"} />{status === "demo" ? <span className="compact-demo-disclosure" aria-label="Browser Demo · no service calls">Demo</span> : null}</div>
        <NavLink to="/settings" className="user-row shell-settings-row" aria-label="Settings"><Settings size={17} aria-hidden="true" /><span>Settings</span></NavLink>
      </div>
    </aside>
  );
}
