import { useState } from "react";
import { ArrowRight, Check, ChevronRight, Lightbulb, RotateCcw, X } from "lucide-react";
import { Badge, Button, Card, Progress } from "@keen/ui";
import { Page } from "../../components/Page";

const questions = [
  { prompt: "Which statement best describes an eigenvector of matrix A?", options: ["Any nonzero vector in the domain", "A vector whose direction is preserved by A", "A vector with magnitude 1", "A row of matrix A"], correct: 1, concept: "Eigenvector definition" },
  { prompt: "If Av = −2v, what happens geometrically?", options: ["v rotates 90°", "v is unchanged", "v flips direction and doubles in length", "v becomes zero"], correct: 2, concept: "Negative eigenvalues" },
  { prompt: "True or false: every square matrix has a real eigenvector.", options: ["True", "False"], correct: 1, concept: "Existence of eigenvectors" },
];

export function QuizPage() {
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [checked, setChecked] = useState(false);
  const [hint, setHint] = useState(0);
  const [confidence, setConfidence] = useState(3);
  const [score, setScore] = useState(0);
  const q = questions[index];
  const finish = index === questions.length;
  const check = () => { if (selected === null) return; setChecked(true); if (selected === q.correct) setScore((s) => s + 1); };
  const next = () => { setIndex((i) => i + 1); setSelected(null); setChecked(false); setHint(0); };
  if (finish) return <Page title="Practice complete" description="Demo result only: this session does not mutate mastery or schedule a review." actions={<Badge tone="warning">Demo · not persisted</Badge>}><Card className="quiz-summary"><div className="score-ring">{score}/{questions.length}</div><h2>{score === questions.length ? "Excellent recall" : "Good diagnostic signal"}</h2><p>This result remains in the current UI session until the learning-core assessment contract is connected.</p><div className="summary-stats"><span><small>Accuracy</small><strong>{Math.round(score / questions.length * 100)}%</strong></span><span><small>Mastery change</small><strong>Not applied</strong></span><span><small>Next review</small><strong>Not scheduled</strong></span></div><Button className="primary" onClick={() => { setIndex(0); setScore(0); }}>Practice again<RotateCcw size={14} /></Button></Card></Page>;
  return (
    <Page title="Eigenvectors quick check" description="3 deterministic sample questions. Answers remain in this UI session and do not update mastery." actions={<Badge tone="warning">Demo · not adaptive</Badge>}>
      <div className="demo-disclosure"><Badge tone="warning">Quiz demo</Badge><span>Hints, feedback, and scores are bundled logic; no assessment event or review task is persisted.</span></div>
      <div className="quiz-progress"><span>Question {index + 1} of {questions.length}</span><Progress value={(index / questions.length) * 100} /><Badge>{q.concept}</Badge></div>
      <Card className="question-card"><div className="question-label">Single choice</div><h2>{q.prompt}</h2><div className="options">{q.options.map((option, i) => <button disabled={checked} className={`${selected === i ? "selected" : ""} ${checked && i === q.correct ? "correct" : ""} ${checked && selected === i && i !== q.correct ? "wrong" : ""}`} key={option} onClick={() => setSelected(i)}><i>{String.fromCharCode(65 + i)}</i><span>{option}</span>{checked && i === q.correct && <Check size={17} />}{checked && selected === i && i !== q.correct && <X size={17} />}</button>)}</div>
        {checked && <div className={`answer-feedback ${selected === q.correct ? "correct" : "wrong"}`}><strong>{selected === q.correct ? "Correct" : "Not quite"}</strong><p>An eigenvector's transformed result is a scalar multiple of itself, so it remains on the same line.</p></div>}
        {hint > 0 && !checked && <div className="hint-box"><Lightbulb size={15} /><span>{hint === 1 ? "Focus on direction, not length." : "Use the equation Av = λv: the output is a scalar multiple of v."}</span></div>}
        <div className="question-footer"><div className="confidence"><span>Confidence</span>{[1,2,3,4,5].map((n) => <button className={confidence === n ? "active" : ""} onClick={() => setConfidence(n)} key={n}>{n}</button>)}</div><div><Button disabled={hint === 2 || checked} onClick={() => setHint((h) => Math.min(2, h + 1))}><Lightbulb size={14} />{hint === 0 ? "Hint" : "More scaffold"}</Button>{checked ? <Button className="primary" onClick={next}>Next<ArrowRight size={14} /></Button> : <Button className="primary" disabled={selected === null} onClick={check}>Check answer<ChevronRight size={14} /></Button>}</div></div>
      </Card>
    </Page>
  );
}
