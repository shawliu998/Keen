import { BookOpenText, CalendarClock } from "lucide-react";
import { Badge, Button, Card, Progress } from "@keen/ui";

const sampleCitations = [
  { page: "p. 1", label: "Direction and scale" },
  { page: "p. 2", label: "Eigenvalue equation" },
] as const;

const sampleMastery = [
  { label: "Invariant direction", value: 68 },
  { label: "Eigenspaces", value: 46 },
] as const;

const sampleReviews = [
  { when: "Tomorrow · 5 min", task: "Explain direction versus magnitude" },
  { when: "In 3 days · 8 min", task: "Solve one eigenvalue check" },
  { when: "Next week · 10 min", task: "Compare eigenvectors and eigenspaces" },
] as const;

export function DemoLearningEvidence({ onOpenSource }: { onOpenSource: () => void }) {
  return (
    <Card className="checkpoint demo-summary">
      <div className="demo-summary-heading">
        <div>
          <Badge tone="warning">Browser Demo</Badge>
          <h3>Session review</h3>
          <p>Illustrative values only. Nothing below was calculated, saved, or scheduled.</p>
        </div>
      </div>

      <section className="demo-feedback-block" aria-label="Bundled feedback">
        <span>Bundled feedback</span>
        <p>You separated invariant direction from changing magnitude. Next, connect that geometric idea to the equation Av = λv.</p>
        <div className="demo-citation-row" aria-label="Unverified sample citations">
          {sampleCitations.map((citation) => (
            <button type="button" key={citation.label} onClick={onOpenSource}>
              <BookOpenText size={13} aria-hidden="true" />
              <span>{citation.label}</span>
              <small>{citation.page}</small>
            </button>
          ))}
        </div>
      </section>

      <div className="demo-evidence-columns">
        <section aria-labelledby="sample-mastery-title">
          <div className="demo-section-title">
            <div>
              <span id="sample-mastery-title">Mastery preview</span>
              <small>Illustrative, not saved</small>
            </div>
          </div>
          <div className="demo-mastery-list">
            {sampleMastery.map((item) => (
              <div key={item.label}>
                <span><strong>{item.label}</strong><small>{item.value}% preview</small></span>
                <Progress value={item.value} />
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="sample-review-title">
          <div className="demo-section-title">
            <div>
              <span id="sample-review-title">Review ideas</span>
              <small>Not scheduled</small>
            </div>
            <CalendarClock size={16} aria-hidden="true" />
          </div>
          <ol className="demo-review-list">
            {sampleReviews.map((review) => (
              <li key={review.when}>
                <span>{review.when}</span>
                <p>{review.task}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <div className="demo-summary-footer">
        <p>Scheduling becomes available only in a connected local session after confirmation.</p>
        <Button disabled>Review scheduling unavailable</Button>
      </div>
    </Card>
  );
}
