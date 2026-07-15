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
    <Page title="Flashcards" description="Linear Algebra · 12 cards due" actions={<><Button><Edit3 size={14} />Edit deck</Button><Badge tone="accent">FSRS scheduled</Badge></>}>
      <div className="review-progress"><span>{reviewed} reviewed</span><Progress value={(reviewed / cards.length) * 100} /><span>{cards.length - reviewed} remaining</span></div>
      <div className="flashcard-stage"><button className={`flashcard ${flipped ? "flipped" : ""}`} onClick={() => setFlipped(!flipped)} aria-label="Flip flashcard"><Card><small>{flipped ? "Answer" : "Question"}</small><h2>{flipped ? cards[index].back : cards[index].front}</h2><span>{flipped ? "Rate your recall below" : "Press space or click to reveal"}</span></Card></button>
        <div className="card-source"><button onClick={() => setInspector({ eyebrow: "Flashcard source", title: cards[index].source, body: cards[index].back, meta: ["Linear Algebra", "Verified against source"] })}><BookOpenText size={14} />{cards[index].source}</button><span>Card {index + 1} of {cards.length}</span></div>
      </div>
      <div className="rating-row">{[["Again","1 min","1"],["Hard","6 min","2"],["Good","2 days","3"],["Easy","5 days","4"]].map(([label, due, key]) => <button disabled={!flipped} className={label.toLowerCase()} key={label} onClick={() => rate(label)}><strong>{label}</strong><span>{due}</span><kbd>{key}</kbd></button>)}</div>
      <div className="review-footer"><Button onClick={() => { setIndex((i) => (i - 1 + cards.length) % cards.length); setFlipped(false); }}><ChevronLeft size={14} />Previous</Button>{lastRating && <span>Last rating: {lastRating}</span>}<Button onClick={() => { setIndex((i) => (i + 1) % cards.length); setFlipped(false); }}>Skip<ChevronRight size={14} /></Button></div>
    </Page>
  );
}
