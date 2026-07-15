import { NavLink, useNavigate } from "react-router-dom";
import { BookOpen, Brain, CalendarDays, ChevronLeft, CircleUserRound, FileStack, Gauge, Home, Layers3, MessageCircle, Plus, Settings, Sparkles, WandSparkles } from "lucide-react";
import { IconButton } from "@keen/ui";
import { recentConversations, recentSessions } from "../data/seed";
import { useAppStore } from "../state/appStore";

const primary = [
  ["/", "Home", Home], ["/feed", "Learning Feed", Sparkles], ["/knowledge", "Knowledge Base", FileStack],
] as const;
const learning = [
  ["/quiz", "Quiz & Practice", Gauge], ["/flashcards", "Flashcards", Layers3], ["/planner", "Study Planner", CalendarDays],
  ["/memory", "Memory", Brain], ["/visualize", "Visualize", WandSparkles],
] as const;

export function Sidebar() {
  const navigate = useNavigate();
  const { toggleSidebar } = useAppStore();
  const nav = (items: typeof primary | typeof learning) => items.map(([to, label, Icon]) => (
    <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-row ${isActive ? "active" : ""}`} title={label}>
      <Icon size={17} aria-hidden /><span>{label}</span>
    </NavLink>
  ));
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="traffic-space" data-tauri-drag-region />
      <div className="brand-row"><div className="brand-mark">K</div><strong>Keen</strong><IconButton label="Collapse sidebar" onClick={toggleSidebar}><ChevronLeft size={16} /></IconButton></div>
      <button className="new-button" onClick={() => navigate("/conversation/new")}><Plus size={17} /><span>New conversation</span><kbd>⌘N</kbd></button>
      <nav>{nav(primary)}</nav>
      <div className="sidebar-scroll">
        <div className="nav-label">Learn</div>{nav(learning)}
        <div className="nav-label">Deep Learn</div>
        {recentSessions.map((label, i) => <NavLink to={`/deep-learn/${i + 1}`} className="recent-row" key={label}><BookOpen size={14} /><span>{label}</span></NavLink>)}
        <div className="nav-label">Conversations</div>
        {recentConversations.map((label, i) => <NavLink to={`/conversation/${i + 1}`} className="recent-row" key={label}><MessageCircle size={14} /><span>{label}</span></NavLink>)}
      </div>
      <div className="sidebar-footer">
        <div className="agent-status" aria-label="Demo mode; learning sidecar offline"><span className="paused-dot" /><span>Demo mode · sidecar offline</span></div>
        <NavLink to="/settings" className="user-row"><CircleUserRound size={22} /><span><strong>Alex Chen</strong><small>Personal workspace</small></span><Settings size={16} /></NavLink>
      </div>
    </aside>
  );
}
