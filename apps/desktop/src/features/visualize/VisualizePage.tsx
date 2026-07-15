import { useState } from "react";
import { Check, Code2, Download, Image, LoaderCircle, Play, Sparkles } from "lucide-react";
import { Badge, Button, Card, Progress } from "@keen/ui";
import { Page, Segmented } from "../../components/Page";

type Format = "Diagram" | "SVG" | "Animation";
type Job = "idle" | "generating" | "ready";

export function VisualizePage() {
  const [format, setFormat] = useState<Format>("Diagram");
  const [prompt, setPrompt] = useState("Show how a matrix transforms space while an eigenvector keeps its direction");
  const [job, setJob] = useState<Job>("idle");
  const [progress, setProgress] = useState(0);
  const generate = () => {
    if (!prompt.trim() || job === "generating") return;
    setJob("generating"); setProgress(18);
    window.setTimeout(() => setProgress(58), 300);
    window.setTimeout(() => { setProgress(100); setJob("ready"); }, 800);
  };
  return (
    <Page title="Visualize" description="Preview the visualization workflow using a bundled local example." actions={<Badge tone="warning">Demo renderer · no source grounding</Badge>}>
      <div className="visualize-layout"><Card className="visual-builder"><div className="field"><label>What should the visual explain?</label><textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} /></div><div className="field"><label>Output format</label><Segmented value={format} options={["Diagram","SVG","Animation"]} onChange={setFormat} /></div><div className="field"><label>Knowledge context</label><select disabled><option>Unavailable until document indexing is connected</option></select></div><div className="visual-options"><label><input type="checkbox" defaultChecked /> Include labels</label><label><input type="checkbox" disabled /> Cite source concepts (unavailable)</label><label><input type="checkbox" disabled /> Show narration script (unavailable)</label></div><Button className="primary" onClick={generate} disabled={job === "generating"}>{job === "generating" ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}{job === "generating" ? "Loading demo…" : "Load demo preview"}</Button>{job === "generating" && <div className="job-progress"><Progress value={progress} /><span>Rendering bundled SVG preview</span></div>}</Card>
        <Card className="visual-preview">{job === "idle" ? <div className="preview-empty"><Image size={32} /><h3>Your demo preview will appear here</h3><p>The generator and export pipeline are not connected in this build.</p></div> : job === "generating" ? <div className="preview-empty"><LoaderCircle className="spin" size={30} /><h3>Loading bundled visual</h3><p>No model, renderer, or source retrieval is running.</p></div> : <><div className="preview-head"><span><Check size={13} />Bundled deterministic demo</span><div><Button disabled><Code2 size={14} />Source unavailable</Button><Button disabled><Download size={14} />Export unavailable</Button></div></div><div className="matrix-diagram"><div className="diagram-plane before"><span className="grid-lines" /><i className="diagram-vector">v</i><small>Before</small></div><div className="transform-arrow"><code>A</code><span>→</span></div><div className="diagram-plane after"><span className="grid-lines transformed" /><i className="diagram-vector long">Av</i><small>After</small></div><div className="diagram-caption"><strong>Av = λv</strong><span>Direction preserved · magnitude scaled</span></div></div><div className="preview-footer"><Badge tone="warning">Demo SVG</Badge><span>Not source-grounded</span><Button disabled><Play size={13} />Motion unavailable</Button></div></>}</Card></div>
      <Card className="future-renderer"><div><Code2 size={17} /><span><strong>Manim video renderer</strong><small>Script, narration, code, rendering, and final artifact pipeline</small></span></div><Badge>Not configured</Badge><Button disabled>Setup unavailable</Button></Card>
    </Page>
  );
}
