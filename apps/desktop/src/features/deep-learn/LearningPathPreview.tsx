import { BookOpenText, Clock3, Files } from "lucide-react";
import { Badge } from "@keen/ui";
import type { AutonomousStudyPlan } from "@keen/api-client";
import { FormattedMathText } from "../MathText";

export function LearningPathPreview({ plan }: { plan: AutonomousStudyPlan }) {
  const totalMinutes = plan.units.reduce((total, unit) => total + unit.estimated_minutes, 0);
  const sourceCount = new Set(plan.units.flatMap((unit) => unit.source_chunk_ids)).size;

  return (
    <section className="learning-path-preview" aria-labelledby="learning-path-preview-title">
      <div className="learning-path-preview-heading">
        <div>
          <span className="lesson-kicker">Saved learning path</span>
          <h2 id="learning-path-preview-title">See the route before you begin</h2>
          <p>
            These steps come from the persisted, course-scoped plan. The opening
            reflection does not score you or change mastery.
          </p>
        </div>
        <Badge tone="accent">Saved locally</Badge>
      </div>

      <dl className="learning-path-preview-facts" aria-label="Learning path facts">
        <div>
          <BookOpenText size={15} aria-hidden="true" />
          <dt>Path</dt>
          <dd>{plan.units.length} steps</dd>
        </div>
        <div>
          <Clock3 size={15} aria-hidden="true" />
          <dt>Planned time</dt>
          <dd>{totalMinutes} min</dd>
        </div>
        <div>
          <Files size={15} aria-hidden="true" />
          <dt>Source scope</dt>
          <dd>{sourceCount} indexed {sourceCount === 1 ? "passage" : "passages"}</dd>
        </div>
      </dl>

      <ol className="learning-path-preview-steps">
        {plan.units.map((unit) => (
          <li key={unit.id}>
            <span className="learning-path-preview-index" aria-hidden="true">{unit.ordinal + 1}</span>
            <div>
              <div className="learning-path-preview-step-heading">
                <h3>{unit.title}</h3>
                <span>{unit.estimated_minutes} min</span>
              </div>
              <p><FormattedMathText>{unit.objective}</FormattedMathText></p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
