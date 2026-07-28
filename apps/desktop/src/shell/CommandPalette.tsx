import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, FileStack, History, Home, Plus, Repeat2, Search, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "../state/appStore";

type CommandGroup = "Actions" | "Pages";
type PaletteCommand = { id: string; label: string; hint: string; to: string; icon: LucideIcon; group: CommandGroup; shortcut?: string; keywords: string };

const commands: readonly PaletteCommand[] = [
  { id: "new-learning", label: "New learning", hint: "Choose sources, then ask or start focused study", to: "/?mode=ask", icon: Plus, group: "Actions", shortcut: "⌘N", keywords: "ask study conversation sources deep learn focus" },
  { id: "home", label: "Home", hint: "Return to your workspace", to: "/", icon: Home, group: "Pages", keywords: "workspace" },
  { id: "knowledge", label: "Knowledge Base", hint: "Browse local learning material", to: "/knowledge", icon: FileStack, group: "Pages", keywords: "documents sources local" },
  { id: "feed", label: "Learning Feed", hint: "Review tasks and progress", to: "/feed", icon: CalendarDays, group: "Pages", shortcut: "⇧⌘L", keywords: "tasks calendar progress" },
  { id: "history", label: "History", hint: "Resume saved learning sessions", to: "/history", icon: History, group: "Pages", keywords: "sessions continue recent progress" },
  { id: "review", label: "Review", hint: "Open the due review queue", to: "/review", icon: Repeat2, group: "Pages", keywords: "flashcards spaced repetition fsrs due" },
  { id: "settings", label: "Settings", hint: "Check runtime and availability", to: "/settings", icon: Settings, group: "Pages", shortcut: "⌘,", keywords: "status provider connections" },
] as const;

export function CommandPalette() {
  const { commandOpen, setCommandOpen } = useAppStore();
  const navigate = useNavigate();
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = useMemo(() => commands.filter((command) => `${command.label} ${command.hint} ${command.keywords}`.toLowerCase().includes(normalizedQuery)), [normalizedQuery]);

  useEffect(() => {
    if (commandOpen) return undefined;
    const rememberFocus = (event: FocusEvent) => {
      if (event.target instanceof HTMLElement && !event.target.closest(".command-palette")) restoreFocusRef.current = event.target;
    };
    if (document.activeElement instanceof HTMLElement) restoreFocusRef.current = document.activeElement;
    document.addEventListener("focusin", rememberFocus);
    return () => document.removeEventListener("focusin", rememberFocus);
  }, [commandOpen]);

  if (!commandOpen) return null;

  const close = () => {
    const focusTarget = restoreFocusRef.current?.isConnected && restoreFocusRef.current !== document.body
      ? restoreFocusRef.current
      : document.querySelector<HTMLElement>('[aria-label="Open command palette"]');
    setQuery("");
    setActiveIndex(0);
    setCommandOpen(false);
    requestAnimationFrame(() => focusTarget?.focus());
  };
  const run = (to: string) => {
    navigate(to);
    close();
  };
  const moveSelection = (offset: number) => {
    if (!filtered.length) return;
    setActiveIndex((current) => (current + offset + filtered.length) % filtered.length);
  };
  const handleDialogKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('input, button:not([disabled])') ?? []);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={close} role="presentation">
      <div ref={dialogRef} className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(event) => event.stopPropagation()} onKeyDown={handleDialogKeyDown}>
        <div className="command-search">
          <Search size={17} aria-hidden="true" />
          <input
            autoFocus
            value={query}
            onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") { event.preventDefault(); moveSelection(1); }
              if (event.key === "ArrowUp") { event.preventDefault(); moveSelection(-1); }
              if (event.key === "Enter" && filtered[activeIndex]) { event.preventDefault(); run(filtered[activeIndex].to); }
            }}
            placeholder="Search Keen…"
            aria-label="Search commands"
            aria-controls="command-results"
          />
          <kbd>esc</kbd>
        </div>
        <div className="command-results" id="command-results">
          {(["Actions", "Pages"] as const).map((group) => {
            const groupCommands = filtered.filter((command) => command.group === group);
            if (!groupCommands.length) return null;
            return (
              <section className="command-group" aria-labelledby={`command-group-${group.toLowerCase()}`} key={group}>
                <h2 id={`command-group-${group.toLowerCase()}`}>{group}</h2>
                {groupCommands.map((command) => {
                  const index = filtered.indexOf(command);
                  const Icon = command.icon;
                  return (
                    <button
                      className={index === activeIndex ? "is-active" : ""}
                      onClick={() => run(command.to)}
                      onMouseMove={() => setActiveIndex(index)}
                      key={command.id}
                    >
                      <Icon size={16} aria-hidden="true" />
                      <span><strong>{command.label}</strong><small>{command.hint}</small></span>
                      {command.shortcut && <kbd>{command.shortcut}</kbd>}
                    </button>
                  );
                })}
              </section>
            );
          })}
          {filtered.length === 0 && <div className="command-empty"><Search size={18} aria-hidden="true" /><strong>No matching command</strong><span>Try “tasks”, “sources”, or “settings”.</span></div>}
        </div>
        <div className="command-help" aria-hidden="true"><span><kbd>↑</kbd><kbd>↓</kbd> Move</span><span><kbd>↵</kbd> Open</span></div>
      </div>
    </div>
  );
}
