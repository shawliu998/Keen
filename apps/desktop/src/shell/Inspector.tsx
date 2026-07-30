import { useEffect, useRef, type KeyboardEvent } from "react";
import { Activity, BookOpenText, ChevronRight, ListTree, X } from "lucide-react";
import { IconButton } from "@keen/ui";
import { AgentActivityDrawerPane } from "../features/agent-activity/AgentActivityDrawerPane";
import { useAppStore, type ContextDrawerView } from "../state/appStore";

const tabs = [
  { id: "activity", label: "Activity", Icon: Activity },
  { id: "sources", label: "Sources", Icon: BookOpenText },
  { id: "outline", label: "Outline", Icon: ListTree },
] as const;

function DrawerEmpty({ view }: { view: Exclude<ContextDrawerView, "activity"> }) {
  const outline = view === "outline";
  const Icon = outline ? ListTree : BookOpenText;
  return (
    <div className="context-drawer-empty" role="status">
      <Icon size={18} aria-hidden="true" />
      <h2>{outline ? "No outline connected" : "No source context selected"}</h2>
      <p>{outline
        ? "Open a guided Study session to connect its current learning outline here."
        : "Select a citation or source-backed detail in the learning workspace to inspect it here."}</p>
    </div>
  );
}

function ContextPane({ view }: { view: Exclude<ContextDrawerView, "activity"> }) {
  const inspector = useAppStore((state) => state.inspector);
  const inspectorKind = inspector?.kind ?? "sources";
  if (!inspector || inspectorKind !== view) return <DrawerEmpty view={view} />;

  return (
    <section className="context-drawer-detail" aria-labelledby="context-detail-title">
      <p className="context-drawer-label">{inspector.eyebrow ?? (view === "sources" ? "Selected source" : "Learning outline")}</p>
      <h2 id="context-detail-title">{inspector.title}</h2>
      <p className="context-drawer-body">{inspector.body}</p>
      {inspector.meta?.length ? (
        <ol className="context-drawer-meta">
          {inspector.meta.map((meta) => (
            <li key={meta}>
              <ChevronRight size={14} aria-hidden="true" />
              <span>{meta}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="context-drawer-no-meta">No additional {view === "sources" ? "source details" : "outline steps"} are available.</p>
      )}
    </section>
  );
}

export function Inspector({ activityContextReady = true }: { activityContextReady?: boolean }) {
  const { drawerView, closeDrawer, setDrawerView } = useAppStore();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const returnFocusRef = useRef<HTMLElement | null>(
    typeof document !== "undefined" && document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  );

  useEffect(() => {
    const returnFocusTarget = returnFocusRef.current;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeDrawer();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      if (returnFocusTarget?.isConnected) {
        window.setTimeout(() => returnFocusTarget.focus({ preventScroll: true }), 0);
      }
    };
  }, [closeDrawer]);

  const moveTabFocus = (event: KeyboardEvent<HTMLButtonElement>, current: number) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const offset = event.key === "ArrowRight" ? 1 : -1;
    const next = (current + offset + tabs.length) % tabs.length;
    setDrawerView(tabs[next].id);
    tabRefs.current[next]?.focus();
  };

  return (
    <aside className="context-drawer" aria-label="Context and activity drawer">
      <div className="context-drawer-head">
        <strong>Context</strong>
        <IconButton label="Close context drawer" onClick={closeDrawer}><X size={16} /></IconButton>
      </div>
      <div className="context-drawer-tabs" role="tablist" aria-label="Drawer views">
        {tabs.map(({ id, label, Icon }, index) => (
          <button
            key={id}
            ref={(node) => { tabRefs.current[index] = node; }}
            type="button"
            role="tab"
            id={`context-drawer-tab-${id}`}
            aria-controls="context-drawer-panel"
            aria-selected={drawerView === id}
            tabIndex={drawerView === id ? 0 : -1}
            onClick={() => setDrawerView(id)}
            onKeyDown={(event) => moveTabFocus(event, index)}
          >
            <Icon size={14} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
      <div
        className="context-drawer-scroll"
        role="tabpanel"
        id="context-drawer-panel"
        aria-labelledby={`context-drawer-tab-${drawerView}`}
        tabIndex={0}
      >
        {drawerView === "activity"
          ? <AgentActivityDrawerPane contextReady={activityContextReady} />
          : <ContextPane view={drawerView} />}
      </div>
    </aside>
  );
}
