import { BookOpenText, ChevronRight, Info, Quote, X } from "lucide-react";
import { Badge, IconButton, Progress } from "@keen/ui";
import { useAppStore } from "../state/appStore";

export function Inspector() {
  const { inspector, toggleInspector } = useAppStore();
  return (
    <aside className="inspector" aria-label="Context inspector">
      <div className="inspector-head"><div><small>{inspector?.eyebrow ?? "Learning context"}</small><strong>{inspector?.title ?? "Linear Algebra"}</strong></div><IconButton label="Close inspector" onClick={toggleInspector}><X size={16} /></IconButton></div>
      {inspector ? (
        <div className="inspector-content"><p>{inspector.body}</p>{inspector.meta?.map((meta) => <div className="detail-row" key={meta}><ChevronRight size={14} /><span>{meta}</span></div>)}</div>
      ) : (
        <>
          <section className="inspector-section"><div className="section-title"><span>Course mastery</span><Badge tone="accent">64%</Badge></div><Progress value={64} label="Course mastery 64%" /><div className="mastery-scale"><span>12 concepts strong</span><span>4 need work</span></div></section>
          <section className="inspector-section"><div className="section-title"><span>Current sources</span><small>3</small></div>
            {["Chapter 5 · Eigenvectors", "Lecture notes · Week 6", "Problem set 04"].map((x, i) => <button className="source-row" key={x}><BookOpenText size={15} /><span>{x}<small>{i === 0 ? "48 pages · indexed" : "Referenced recently"}</small></span><ChevronRight size={14} /></button>)}
          </section>
          <section className="inspector-section"><div className="section-title"><span>Agent insight</span><Info size={15} /></div><div className="insight-box"><Quote size={15} /><p>You understand the algebraic procedure. The next useful step is connecting it to geometric intuition.</p></div></section>
        </>
      )}
    </aside>
  );
}
