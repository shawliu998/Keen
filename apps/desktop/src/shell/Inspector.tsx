import { BookOpenText, ChevronRight, Info, Quote, X } from "lucide-react";
import { Badge, IconButton, Progress } from "@keen/ui";
import { useAppStore } from "../state/appStore";

export function Inspector() {
  const { inspector, toggleInspector } = useAppStore();
  return (
    <aside className="inspector" aria-label="Context inspector">
      <div className="inspector-head"><div><small>{inspector?.eyebrow ?? "Demo context"}</small><strong>{inspector?.title ?? "Seed preview"}</strong></div><IconButton label="Close inspector" onClick={toggleInspector}><X size={16} /></IconButton></div>
      {inspector ? (
        <div className="inspector-content"><p>{inspector.body}</p>{inspector.meta?.map((meta) => <div className="detail-row" key={meta}><ChevronRight size={14} /><span>{meta}</span></div>)}</div>
      ) : (
        <>
          <section className="inspector-section"><div className="section-title"><span>Illustrative mastery</span><Badge tone="warning">Sample 64%</Badge></div><Progress value={64} label="Illustrative mastery sample 64%" /><div className="mastery-scale"><span>Seed values only</span><span>Not live state</span></div></section>
          <section className="inspector-section"><div className="section-title"><span>Demo source labels</span><small>Unverified</small></div>
            {["Chapter 5 · Eigenvectors", "Lecture notes · Week 6", "Problem set 04"].map((x) => <button className="source-row" key={x} disabled><BookOpenText size={15} /><span>{x}<small>No source document connected</small></span><ChevronRight size={14} /></button>)}
          </section>
          <section className="inspector-section"><div className="section-title"><span>Demo insight</span><Info size={15} /></div><div className="insight-box"><Quote size={15} /><p>Seeded UI example only: no Agent analyzed learner evidence or produced this recommendation.</p></div></section>
        </>
      )}
    </aside>
  );
}
