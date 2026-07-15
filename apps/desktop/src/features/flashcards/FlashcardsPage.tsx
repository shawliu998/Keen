import { useEffect, useState } from "react";
import { BookOpenText, ChevronLeft, ChevronRight, Edit3 } from "lucide-react";
import { Badge, Button, Card, Progress } from "@keen/ui";
import { Page } from "../../components/Page";
import { useAppStore } from "../../state/appStore";

const cards = [
  { front: "What is an eigenvector?", back: "A nonzero vector whose direction is unchanged by a linear transformation: Av = λv.", source: "Chapter 5, p. 14" },
  { front: "What does a negative eigenvalue mean geometrically?", back: "The eigenvector flips direction and scales by the absolute value of λ.", source: "Lecture 06, p. 3" },
  { front: "Define an eigenspace.", back: "The set of all eigenvectors associated with one eigenvalue, together with the zero vector.", source: "Chapter 5, p. 18" },
];

export function FlashcardsPage() {
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [reviewed, setReviewed] = useState(0);
  const [lastRating, setLastRating] = useState("");
  const { setInspector } = useAppStore();
  const rate = (rating: string) => { setLastRating(rating); setReviewed((n) => Math.min(cards.length, n + 1)); setIndex((i) => (i + 1) % cards.length); setFlipped(false); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.code === "Space") { e.preventDefault(); setFlipped((v) => !v); } if (flipped && ["1","2","3","4"].includes(e.key)) rate(["Again","Hard","Good","Easy"][Number(e.key) - 1]); };
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  });
  return (
    <Page title="Flashcards" description="Deterministic sample deck. Ratings stay in this UI session and do not update mastery or a review schedule." actions={<><Button disabled><Edit3 size={14} />Edit unavailable</Button><Badge tone="warning">Demo · FSRS not connected</Badge></>}>
      <div className="demo-disclosure"><Badge tone="warning">Flashcard demo</Badge><span>Cards, source labels, due counts, and intervals are bundled examples; none are verified, saved, or scheduled.</span></div>
      <div className="review-progress"><span>{reviewed} reviewed</span><Progress value={(reviewed / cards.length) * 100} /><span>{cards.length - reviewed} remaining</span></div>
      <div className="flashcard-stage"><button className={`flashcard ${flipped ? "flipped" : ""}`} onClick={() => setFlipped(!flipped)} aria-label="Flip flashcard"><Card><small>{flipped ? "Answer" : "Question"}</small><h2>{flipped ? cards[index].back : cards[index].front}</h2><span>{flipped ? "Rate your recall below" : "Press space or click to reveal"}</span></Card></button>
        <div className="card-source"><button onClick={() => setInspector({ eyebrow: "Unverified demo source", title: cards[index].source, body: cards[index].back, meta: ["Bundled sample content", "No source document connected"] })}><BookOpenText size={14} />Demo source · {cards[index].source}</button><span>Card {index + 1} of {cards.length}</span></div>
      </div>
      <div className="rating-row">{[["Again","Sample: 1 min","1"],["Hard","Sample: 6 min","2"],["Good","Sample: 2 days","3"],["Easy","Sample: 5 days","4"]].map(([label, due, key]) => <button disabled={!flipped} className={label.toLowerCase()} key={label} onClick={() => rate(label)}><strong>{label}</strong><span>{due}</span><kbd>{key}</kbd></button>)}</div>
      <div className="review-footer"><Button onClick={() => { setIndex((i) => (i - 1 + cards.length) % cards.length); setFlipped(false); }}><ChevronLeft size={14} />Previous</Button>{lastRating && <span>Last rating: {lastRating}</span>}<Button onClick={() => { setIndex((i) => (i + 1) % cards.length); setFlipped(false); }}>Skip<ChevronRight size={14} /></Button></div>
    </Page>
  );
}
