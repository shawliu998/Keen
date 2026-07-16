import { useMemo, useState } from "react";
import { ArrowRight, BookOpen, Brain, Gauge, Mic, Paperclip, Send, Sparkles, Square } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, IconButton, Progress } from "@keen/ui";
import type { AgentRunKind, AgentRunMode } from "@keen/api-client";
import { AgentActivityPanel, type AgentActivityViewState, type AgentMutationActionState } from "../agent/AgentActivityPanel";
import { useAgentRuntime } from "../../services/AgentRuntimeProvider";

const prompts = [
  ["teach", "Teach eigenvectors with a visual analogy", BookOpen], ["ask", "Walk me through problem 4, one step at a time", Gauge],
  ["review", "Build a 20-minute review from my weak concepts", Brain], ["study", "Build a source-grounded study session", Sparkles],
] as const;
const modes: readonly AgentRunMode[] = ["ask", "teach", "study", "review", "plan"];
const modeLabels: Record<AgentRunMode, string> = { ask: "Ask", teach: "Teach", study: "Study", review: "Review", plan: "Plan" };

function kindForMode(mode: AgentRunMode): AgentRunKind {
  if (mode === "study" || mode === "teach") return "deep_learn";
  if (mode === "review") return "review";
  return "conversation";
}

export function HomePage() {
  const navigate = useNavigate();
  const runtime = useAgentRuntime();
  const [mode, setMode] = useState<AgentRunMode>("ask");
  const [message, setMessage] = useState("");
  const [mutationTarget, setMutationTarget] = useState<string | null>(null);
  const demo = runtime.learningCoreStatus === "demo";
  const runActive = runtime.run !== null && !runtime.activity.terminal;
  const operationActive = runtime.phase === "creating" || runtime.phase === "recovering" || runtime.phase === "streaming" || runtime.phase === "cancelling";

  const submit = async () => {
    if (!message.trim()) return;
    if (demo) {
      sessionStorage.setItem("keen-new-message", message.trim());
      navigate("/conversation/new");
      return;
    }
    const created = await runtime.startRun({
      kind: kindForMode(mode),
      mode,
      userIntent: message.trim(),
      input: {},
    });
    if (created) setMessage("");
  };

  const viewState: AgentActivityViewState = runtime.issue?.code === "provider_missing"
    ? "provider_missing"
    : runtime.issue?.code === "provider_unavailable"
      ? "provider_unavailable"
      : runtime.learningCoreStatus !== "healthy"
        ? "offline"
        : runtime.phase === "recovering" && runtime.activity.partial
          ? "reconnecting"
          : "ready";

  const mutationActions = useMemo(() => {
    const result: Record<string, AgentMutationActionState> = {};
    for (const mutation of runtime.activity.mutations) {
      if (!mutation.targetMutationId || !mutation.action) continue;
      result[mutation.targetMutationId] = {
        undone: mutation.action === "undo",
        pendingAction: null,
        error: null,
      };
    }
    const direct = runtime.mutationAction.lastResult;
    if (direct) {
      result[direct.targetMutationId] = {
        undone: direct.action === "undo",
        pendingAction: null,
        error: null,
      };
    }
    const pending = runtime.mutationAction.pending;
    if (pending) {
      result[pending.mutationId] = {
        undone: result[pending.mutationId]?.undone ?? pending.action === "redo",
        pendingAction: pending.action,
        error: null,
      };
    }
    if (mutationTarget && runtime.mutationAction.error) {
      result[mutationTarget] = {
        undone: result[mutationTarget]?.undone ?? false,
        pendingAction: null,
        error: `${runtime.mutationAction.error.message} ${runtime.mutationAction.error.recovery}`,
      };
    }
    return result;
  }, [mutationTarget, runtime.activity.mutations, runtime.mutationAction]);

  const undo = (mutationId: string) => {
    setMutationTarget(mutationId);
    void runtime.undoMutation(mutationId);
  };
  const redo = (mutationId: string) => {
    setMutationTarget(mutationId);
    void runtime.redoMutation(mutationId);
  };

  return (
    <div className="home-page">
      <div className="demo-disclosure"><Badge tone={demo ? "warning" : "accent"}>{demo ? "Demo surface" : "Local Agent"}</Badge><span>{demo ? "Prompts, recommendations, statistics, and attachments on this page are deterministic UI samples. No model runs, file is read, or learning record is changed." : "The composer and Agent activity use the authenticated local learning core. Recommendations and statistics below remain labeled sample content."}</span></div>
      <section className="welcome-section">
        <div className="orb" aria-hidden><span>K</span></div>
        <div><p className="eyebrow">Local learning workspace</p><h1>What would you like to understand?</h1><p>Ask, teach, study, review, or plan across your learning materials.</p></div>
      </section>
      <div className="composer card">
        <textarea aria-label="Message Keen" placeholder="Ask anything about what you're learning…" value={message} disabled={!demo && (runActive || operationActive)} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!runActive && !operationActive) void submit(); } }} />
        <div className="composer-bottom"><div className="composer-tools"><IconButton label="Attachments are not available for Agent runs yet" disabled><Paperclip size={17} /></IconButton>
          {modes.map((candidate) => <button type="button" key={candidate} className={`mode-chip ${mode === candidate ? "active" : ""}`} disabled={!demo && (runActive || operationActive)} onClick={() => setMode(candidate)}>{modeLabels[candidate]}</button>)}
        </div><div className="composer-submit"><IconButton label="Voice input, not available" disabled><Mic size={17} /></IconButton><button type="button" aria-label={!demo && runActive ? "Cancel Agent run" : "Send message"} className="send-button" disabled={!runActive && (!message.trim() || (!demo && (runtime.learningCoreStatus !== "healthy" || operationActive)))} onClick={() => { if (!demo && runActive) void runtime.cancelRun(); else void submit(); }}>{!demo && (runActive || operationActive) ? <Square size={14} /> : <Send size={15} />}</button></div></div>
      </div>
      <div className="prompt-grid">{prompts.map(([promptMode, text, Icon]) => <button type="button" key={promptMode} disabled={!demo && (runActive || operationActive)} onClick={() => { setMode(promptMode); setMessage(text); }}><Icon size={16} /><span><strong>{modeLabels[promptMode]}</strong>{text}</span><ArrowRight size={14} /></button>)}</div>
      {!demo ? <div className="agent-home-activity">
        {runtime.issue ? <div className="agent-runtime-issue" role="alert"><strong>{runtime.issue.message}</strong><span>{runtime.issue.recovery}</span></div> : null}
        <AgentActivityPanel
          runId={runtime.run?.id ?? null}
          state={runtime.activity}
          viewState={viewState}
          mutationActions={mutationActions}
          cancelPending={runtime.phase === "cancelling"}
          onCancel={() => { void runtime.cancelRun(); }}
          onUndo={undo}
          onRedo={redo}
        />
      </div> : null}
      <section className="home-section"><div className="home-section-head"><div><Sparkles size={16} /><h2>Proactive Learning Feed</h2><Badge tone="warning">Sample · 3 for today</Badge></div><button onClick={() => navigate("/feed")}>View all <ArrowRight size={14} /></button></div>
        <div className="feed-preview">
          <Card className="priority-card"><div className="priority-top"><Badge tone="warning">Recommended next</Badge><span>18 min</span></div><h3>Review eigenvectors before Chapter 6</h3><p>You missed this concept twice yesterday, and it unlocks your next chapter.</p><div className="concept-line"><span>Mastery</span><Progress value={42} /><strong>42%</strong></div><Button className="primary" onClick={() => navigate("/deep-learn/1")}>Start review <ArrowRight size={14} /></Button></Card>
          <div className="mini-task-list">{[["Cellular respiration recall", "Biology 101 · 12 min", "Due 2:00 PM"], ["Practice confidence intervals", "Statistics · 25 min", "Tomorrow"]].map(([title, meta, due]) => <button key={title} onClick={() => navigate("/feed")}><span><strong>{title}</strong><small>{meta}</small></span><Badge>{due}</Badge><ArrowRight size={14} /></button>)}</div>
        </div>
      </section>
      <section className="home-section home-stats"><button onClick={() => navigate("/quiz")}><Gauge size={18} /><span><small>Practice accuracy</small><strong>78%</strong><em>+6% this week</em></span></button><button onClick={() => navigate("/knowledge")}><BookOpen size={18} /><span><small>Knowledge base</small><strong>5 sources</strong><em>4 fully indexed</em></span></button><button onClick={() => navigate("/memory")}><Brain size={18} /><span><small>Learner memory</small><strong>18 insights</strong><em>2 need review</em></span></button></section>
    </div>
  );
}
