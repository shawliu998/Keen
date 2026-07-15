import { useState } from "react";
import { ArrowRight, BookOpen, Brain, FilePlus2, Gauge, Mic, Paperclip, Send, Sparkles, Square } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, IconButton, Progress } from "@keen/ui";
import type { AgentMode } from "@keen/domain";
import { useAppStore } from "../../state/appStore";

const prompts = [
  ["Teach", "Teach eigenvectors with a visual analogy", BookOpen], ["Solve", "Walk me through problem 4, one step at a time", Gauge],
  ["Review", "Build a 20-minute review from my weak concepts", Brain], ["Research", "Compare three explanations in my sources", Sparkles],
] as const;

export function HomePage() {
  const navigate = useNavigate();
  const { agentMode, setAgentMode } = useAppStore();
  const [message, setMessage] = useState("");
  const [attached, setAttached] = useState(false);
  const [generating, setGenerating] = useState(false);
  const submit = () => {
    if (!message.trim()) return;
    sessionStorage.setItem("keen-new-message", message);
    setGenerating(true);
    window.setTimeout(() => navigate("/conversation/new"), 350);
  };
  return (
    <div className="home-page">
      <div className="demo-disclosure"><Badge tone="warning">Demo surface</Badge><span>Prompts, recommendations, statistics, and attachments on this page are deterministic UI samples. No model runs, file is read, or learning record is changed.</span></div>
      <section className="welcome-section">
        <div className="orb" aria-hidden><span>K</span></div>
        <div><p className="eyebrow">Wednesday, July 15</p><h1>What would you like to understand?</h1><p>Ask me to teach, solve, review, or research across your learning materials.</p></div>
      </section>
      <div className="composer card">
        <textarea aria-label="Message Keen" placeholder="Ask anything about what you're learning…" value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} />
        {attached && <div className="attachment-chip"><FilePlus2 size={14} /> Chapter_5.pdf <button aria-label="Remove attachment" onClick={() => setAttached(false)}>×</button></div>}
        <div className="composer-bottom"><div className="composer-tools"><IconButton label="Attach a file" onClick={() => setAttached(true)}><Paperclip size={17} /></IconButton>
          {(["Teach", "Solve", "Review", "Research"] as AgentMode[]).map((mode) => <button key={mode} className={`mode-chip ${agentMode === mode ? "active" : ""}`} onClick={() => setAgentMode(mode)}>{mode}</button>)}
        </div><div className="composer-submit"><IconButton label="Voice input, not available" disabled><Mic size={17} /></IconButton><button aria-label={generating ? "Stop generating" : "Send message"} className="send-button" onClick={generating ? () => setGenerating(false) : submit}>{generating ? <Square size={14} /> : <Send size={15} />}</button></div></div>
      </div>
      <div className="prompt-grid">{prompts.map(([mode, text, Icon]) => <button key={mode} onClick={() => { setAgentMode(mode); setMessage(text); }}><Icon size={16} /><span><strong>{mode}</strong>{text}</span><ArrowRight size={14} /></button>)}</div>
      <section className="home-section"><div className="home-section-head"><div><Sparkles size={16} /><h2>Proactive Learning Feed</h2><Badge tone="accent">3 for today</Badge></div><button onClick={() => navigate("/feed")}>View all <ArrowRight size={14} /></button></div>
        <div className="feed-preview">
          <Card className="priority-card"><div className="priority-top"><Badge tone="warning">Recommended next</Badge><span>18 min</span></div><h3>Review eigenvectors before Chapter 6</h3><p>You missed this concept twice yesterday, and it unlocks your next chapter.</p><div className="concept-line"><span>Mastery</span><Progress value={42} /><strong>42%</strong></div><Button className="primary" onClick={() => navigate("/deep-learn/1")}>Start review <ArrowRight size={14} /></Button></Card>
          <div className="mini-task-list">{[["Cellular respiration recall", "Biology 101 · 12 min", "Due 2:00 PM"], ["Practice confidence intervals", "Statistics · 25 min", "Tomorrow"]].map(([title, meta, due]) => <button key={title} onClick={() => navigate("/feed")}><span><strong>{title}</strong><small>{meta}</small></span><Badge>{due}</Badge><ArrowRight size={14} /></button>)}</div>
        </div>
      </section>
      <section className="home-section home-stats"><button onClick={() => navigate("/quiz")}><Gauge size={18} /><span><small>Practice accuracy</small><strong>78%</strong><em>+6% this week</em></span></button><button onClick={() => navigate("/knowledge")}><BookOpen size={18} /><span><small>Knowledge base</small><strong>5 sources</strong><em>4 fully indexed</em></span></button><button onClick={() => navigate("/memory")}><Brain size={18} /><span><small>Learner memory</small><strong>18 insights</strong><em>2 need review</em></span></button></section>
    </div>
  );
}
