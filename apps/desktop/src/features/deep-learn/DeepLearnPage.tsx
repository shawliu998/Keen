import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpenText, Check, ChevronLeft, ChevronRight, Lightbulb, Pause, Play, Save, X } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, EmptyState, Progress } from "@keen/ui";
import { LearningCoreResponseError, type AutonomousStudyPlan } from "@keen/api-client";
import { useAppStore } from "../../state/appStore";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";

const demoUnits = ["Goal & baseline", "Geometric intuition", "The eigenvalue equation", "Eigenspaces", "Checkpoint", "Targeted practice", "Summary"];

function DemoDeepLearn() {
  const [unit, setUnit] = useState(1);
  const [paused, setPaused] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState("");
  const { setInspector } = useAppStore();
  const submit = () => { setFeedback(answer.toLowerCase().includes("direction") || answer.toLowerCase().includes("scalar") ? "Exactly. You separated direction from magnitude." : "Good start. Add what changes—and what stays invariant."); setAnswering(false); };
  return <div className="deep-learn-page">
    <div className="demo-disclosure"><Badge tone="warning">Deep Learn demo</Badge><span>Bundled lesson content and illustrative mastery only. Answers, progress, and ratings are not persisted or sent to an Agent.</span></div>
    <header className="session-header"><div><span>Deep Learn demo · not persisted</span><h1>Eigenvectors & eigenspaces</h1></div><div className="session-progress"><span>Unit {unit + 1} of {demoUnits.length}</span><Progress value={((unit + 1) / demoUnits.length) * 100} /></div><div><Button onClick={() => setPaused(!paused)}>{paused ? <Play size={14} /> : <Pause size={14} />}{paused ? "Resume demo" : "Pause demo"}</Button><Button disabled><Save size={14} />Save unavailable</Button><button aria-label="Close unavailable" className="icon-button" disabled><X size={16} /></button></div></header>
    <div className="session-layout"><aside className="unit-nav"><small>Learning path</small>{demoUnits.map((label, index) => <button key={label} className={unit === index ? "active" : index < unit ? "done" : ""} onClick={() => setUnit(index)}><i>{index < unit ? <Check size={12} /> : index + 1}</i><span>{label}</span></button>)}</aside>
      <main className="lesson-content"><div className="lesson-kicker">Unit {unit + 1} · Sample</div><h2>{demoUnits[unit]}</h2><p className="lesson-lead">This is bundled sample content, not a persisted study plan.</p>
        <Card className="checkpoint"><div><Badge tone="accent">Demo recall</Badge><h3>What can change when a matrix acts on an eigenvector?</h3></div>{answering ? <div className="answer-box"><textarea autoFocus value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Explain in your own words…" /><Button className="primary" onClick={submit}>Check demo answer</Button></div> : <div className="checkpoint-actions"><Button className="primary" onClick={() => setAnswering(true)}>Answer now</Button><Button onClick={() => setFeedback("Hint: compare magnitude with direction.")}><Lightbulb size={14} />Give me a hint</Button></div>}{feedback && <p className="feedback">{feedback}</p>}</Card>
        <div className="lesson-nav"><Button disabled={unit === 0} onClick={() => setUnit(unit - 1)}><ChevronLeft size={14} />Previous</Button><Button onClick={() => setInspector({ eyebrow: "Unverified demo source", title: "Bundled demo", body: "This is sample-only content; no indexed source is connected.", meta: ["No verified citations"] })}><BookOpenText size={14} />Demo source</Button><Button className="primary" disabled={unit === demoUnits.length - 1} onClick={() => setUnit(unit + 1)}>Next unit<ChevronRight size={14} /></Button></div>
      </main><aside className="session-aside"><small>Illustrative demo mastery</small><strong>Sample only <Badge tone="warning">Not persisted</Badge></strong><Progress value={54} /></aside>
    </div>
  </div>;
}

function unitProgress(plan: AutonomousStudyPlan): number {
  return plan.units.length === 0 ? 0 : (plan.units.filter((unit) => unit.status === "completed" || unit.status === "skipped").length / plan.units.length) * 100;
}

export function DeepLearnPage() {
  const { id: sessionId } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const courseId = search.get("course_id");
  const core = useLearningCore();
  const { setInspector } = useAppStore();
  const query = useQuery({
    queryKey: ["learning-core", "study-session", core.connectionGeneration, courseId, sessionId],
    queryFn: ({ signal }) => {
      if (!core.client || !sessionId || !courseId) throw new Error("A session and its course are required.");
      return core.client.getStudySession(sessionId, courseId, { signal });
    },
    enabled: core.status === "healthy" && core.client !== null && Boolean(sessionId && courseId),
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const unit = useMemo(() => {
    if (!query.data?.plan) return null;
    return query.data.plan.units.find((item) => item.id === selectedUnitId)
      ?? query.data.plan.units.find((item) => item.id === query.data?.current_unit_id)
      ?? query.data.plan.units[0]
      ?? null;
  }, [query.data, selectedUnitId]);

  if (!sessionId) return <DemoDeepLearn />;
  if (core.status === "demo") return <DemoDeepLearn />;
  if (!courseId) return <div className="deep-learn-page"><Card><EmptyState icon={<BookOpenText size={28} />} title="Study session needs a course" description="This link is missing its course scope. Return to the Learning Feed and start the task again." action={<Button onClick={() => navigate("/feed")}>Return to Learning Feed</Button>} /></Card></div>;
  if (core.status !== "healthy") return <div className="deep-learn-page"><Card className="service-state" role={isLearningCoreStarting(core.status) ? "status" : "alert"}><BookOpenText size={23} /><div><strong>{isLearningCoreStarting(core.status) ? "Learning core is starting" : "Local study session is unavailable"}</strong><p>{isLearningCoreStarting(core.status) ? "Keen will load the persisted study session after the local service is ready." : "The local service cannot read this session right now. No sample lesson was substituted."}</p></div><Button onClick={() => { void core.retry(); }}>Retry</Button></Card></div>;
  if (query.isPending) return <div className="deep-learn-page"><Card className="service-state" role="status"><BookOpenText size={23} /><div><strong>Loading local study session</strong><p>Keen is reading its persisted plan and source citations.</p></div></Card></div>;
  if (query.isError) {
    const missing = query.error instanceof LearningCoreResponseError && query.error.status === 404;
    return <div className="deep-learn-page"><Card className="service-state" role="alert"><BookOpenText size={23} /><div><strong>{missing ? "Study session was not found" : "Study session could not be read"}</strong><p>{missing ? "This local session is unavailable for the requested course. Return to the Learning Feed and start a current task." : "The session was not rendered because its local response could not be confirmed. Retry after the service recovers."}</p></div>{missing ? <Button onClick={() => navigate("/feed")}>Return to Learning Feed</Button> : <Button onClick={() => { void query.refetch(); }}>Retry</Button>}</Card></div>;
  }
  if (!query.data) return null;
  if (query.data.outcome === "plan_unavailable") return <div className="deep-learn-page"><Card><EmptyState icon={<BookOpenText size={28} />} title="Study plan unavailable" description={query.data.recovery_action ?? "Return to the Learning Feed and start a source-grounded task."} action={<Button onClick={() => navigate("/feed")}>Return to Learning Feed</Button>} /></Card></div>;
  const { session, plan } = query.data;
  if (!plan || !unit) return <div className="deep-learn-page"><Card><EmptyState icon={<BookOpenText size={28} />} title="Study plan unavailable" description="Return to the Learning Feed and refresh the local recommendation." /></Card></div>;
  return <div className="deep-learn-page">
    <header className="session-header"><div><span>Persisted local study session</span><h1>{session.title}</h1><p>{session.goal}</p></div><div className="session-progress"><span>{Math.round(session.progress * 100)}% session progress · {Math.round(unitProgress(plan))}% units complete</span><Progress value={session.progress * 100} /></div><div><Badge>{session.status.replaceAll("_", " ")}</Badge></div></header>
    <div className="session-layout"><aside className="unit-nav"><small>Source-grounded plan</small>{plan.units.map((item) => <button key={item.id} className={item.id === unit.id ? "active" : item.status === "completed" ? "done" : ""} onClick={() => setSelectedUnitId(item.id)}><i>{item.status === "completed" ? <Check size={12} /> : item.ordinal + 1}</i><span>{item.title}</span></button>)}</aside>
      <main className="lesson-content"><div className="lesson-kicker">Unit {unit.ordinal + 1} · {unit.status}</div><h2>{unit.title}</h2><p className="lesson-lead">{unit.objective}</p><Card className="checkpoint"><Badge tone="accent">Source-grounded material</Badge><p>{unit.content || "This unit has no display text; use the cited source chunks in the inspector."}</p></Card><div className="lesson-nav"><Button onClick={() => setInspector({ eyebrow: "Source citations", title: unit.title, body: "The following persisted source chunk IDs ground this unit. Source text is displayed as data, not as instructions.", meta: unit.source_chunk_ids.map((source) => `Chunk ${source}`) })}><BookOpenText size={14} />View source citations</Button></div></main>
      <aside className="session-aside"><small>Local session</small><strong>{session.mode}</strong><p>{session.estimated_minutes} minute estimate</p><hr /><small>Plan rationale</small><p>{plan.rationale}</p><small>Concept IDs</small>{unit.concept_ids.map((concept) => <Badge key={concept}>{concept}</Badge>)}</aside>
    </div>
  </div>;
}
