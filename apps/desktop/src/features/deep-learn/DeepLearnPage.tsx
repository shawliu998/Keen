import { useState } from "react";
import { BookOpenText, Check, ChevronLeft, ChevronRight, Lightbulb, Pause, Play, Save, X } from "lucide-react";
import { Badge, Button, Card, Progress } from "@keen/ui";
import { useAppStore } from "../../state/appStore";

const units = ["Goal & baseline", "Geometric intuition", "The eigenvalue equation", "Eigenspaces", "Checkpoint", "Targeted practice", "Summary"];

export function DeepLearnPage() {
  const [unit, setUnit] = useState(1);
  const [paused, setPaused] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState("");
  const { setInspector } = useAppStore();
  const submit = () => { setFeedback(answer.toLowerCase().includes("direction") || answer.toLowerCase().includes("scalar") ? "Exactly. You separated direction from magnitude." : "Good start. Add what changes—and what stays invariant."); setAnswering(false); };
  return (
    <div className="deep-learn-page">
      <div className="demo-disclosure"><Badge tone="warning">Deep Learn demo</Badge><span>Bundled lesson content and illustrative mastery only. Answers, progress, and ratings are not persisted or sent to an Agent.</span></div>
      <header className="session-header"><div><span>Deep Learn demo · not persisted</span><h1>Eigenvectors & eigenspaces</h1></div><div className="session-progress"><span>Unit {unit + 1} of {units.length}</span><Progress value={((unit + 1) / units.length) * 100} /></div><div><Button onClick={() => setPaused(!paused)}>{paused ? <Play size={14} /> : <Pause size={14} />}{paused ? "Resume demo" : "Pause demo"}</Button><Button disabled><Save size={14} />Save unavailable</Button><button aria-label="Close unavailable" className="icon-button" disabled><X size={16} /></button></div></header>
      <div className="session-layout"><aside className="unit-nav"><small>Learning path</small>{units.map((label, index) => <button key={label} className={unit === index ? "active" : index < unit ? "done" : ""} onClick={() => setUnit(index)}><i>{index < unit ? <Check size={12} /> : index + 1}</i><span>{label}</span></button>)}</aside>
        <main className="lesson-content"><div className="lesson-kicker">Unit {unit + 1} · Concept</div><h2>{units[unit]}</h2><p className="lesson-lead">Imagine drawing a vector as an arrow on a rubber sheet. A linear transformation stretches and rotates the sheet. Most arrows point somewhere new—but a few special directions remain on their original line.</p>
          <Card className="concept-visual"><div className="axis"><span className="x-axis" /><span className="y-axis" /><span className="vector original">v</span><span className="vector transformed">Av = λv</span></div><div><strong>Direction stays invariant</strong><p>The transformation changes length by λ, while the vector remains in the same span.</p></div></Card>
          <h3>Connect the picture to the equation</h3><p>When <code>Av = λv</code>, the output is a scalar multiple of the input. A negative λ flips the arrow, but it still lies on the same line. That is why eigenvectors describe the natural axes of a transformation.</p>
          <Card className="checkpoint"><div><Badge tone="accent">Active recall</Badge><h3>What can change when a matrix acts on an eigenvector, and what stays the same?</h3></div>{answering ? <div className="answer-box"><textarea autoFocus value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Explain in your own words…" /><Button className="primary" onClick={submit}>Check answer</Button></div> : <div className="checkpoint-actions"><Button className="primary" onClick={() => setAnswering(true)}>Answer now</Button><Button onClick={() => setFeedback("Hint: compare magnitude with direction.")}><Lightbulb size={14} />Give me a hint</Button><Button onClick={() => setFeedback("Imagine resizing an arrow without changing the line it sits on.")}>Explain differently</Button></div>}{feedback && <p className="feedback">{feedback}</p>}</Card>
          <div className="lesson-nav"><Button disabled={unit === 0} onClick={() => setUnit(unit - 1)}><ChevronLeft size={14} />Previous</Button><Button onClick={() => setInspector({ eyebrow: "Unverified demo source", title: "Chapter 5 · Eigenvectors", body: "This source label is bundled seed content. No source PDF or indexed chunk is connected to this lesson.", meta: ["No verified citations", "Source viewing unavailable"] })}><BookOpenText size={14} />Demo source</Button><Button className="primary" disabled={unit === units.length - 1} onClick={() => setUnit(unit + 1)}>Next unit<ChevronRight size={14} /></Button></div>
        </main>
        <aside className="session-aside"><small>Illustrative demo mastery</small><strong>Eigenvectors <Badge tone="warning">Sample only</Badge></strong><Progress value={54} /><div className="mastery-change"><span>Example 42%</span><ChevronRight size={13} /><span>Example 54%</span></div><hr /><small>Sample concept values</small>{["Direction invariance", "Eigenvalue", "Eigenspace"].map((x, i) => <div className="concept-row" key={x}><span>{x}</span><strong>{[72, 58, 31][i]}%</strong></div>)}</aside>
      </div>
    </div>
  );
}
