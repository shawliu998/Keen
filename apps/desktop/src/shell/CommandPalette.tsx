import { useMemo, useState } from "react";
import { BookOpen, Brain, FileStack, Home, MessageCircle, Search, Settings, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "../state/appStore";

const commands = [
  ["Go to Home", "/", Home], ["Open Learning Feed", "/feed", Sparkles], ["Browse Knowledge Base", "/knowledge", FileStack],
  ["Start a conversation", "/conversation/new", MessageCircle], ["Start Deep Learn", "/deep-learn/new", BookOpen],
  ["Review learner memory", "/memory", Brain], ["Open Settings", "/settings", Settings],
] as const;

export function CommandPalette() {
  const { commandOpen, setCommandOpen } = useAppStore();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => commands.filter(([label]) => label.toLowerCase().includes(query.toLowerCase())), [query]);
  if (!commandOpen) return null;
  const close = () => { setQuery(""); setCommandOpen(false); };
  const run = (to: string) => { navigate(to); close(); };
  return (
    <div className="modal-backdrop" onMouseDown={close} role="presentation">
      <div className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="command-search"><Search size={18} /><input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") close(); if (e.key === "Enter" && filtered[0]) run(filtered[0][1]); }} placeholder="Search pages and actions…" /></div>
        <div className="command-results"><small>Quick actions</small>{filtered.map(([label, to, Icon]) => <button onClick={() => run(to)} key={to}><Icon size={17} /><span>{label}</span><kbd>↵</kbd></button>)}{filtered.length === 0 && <p>No commands found.</p>}</div>
      </div>
    </div>
  );
}
