import { useMemo } from "react";
import { useLearningCore } from "../../services/LearningCoreProvider";

const MAX_CONCEPTS = 6;

/**
 * Current mastery snapshot for the selected History course. The demo-state
 * mastery read is a current snapshot, not time-series history, so this is a
 * ranked bar list of the weakest recorded concepts, not a trend line. Rows
 * without recorded attempts are priors rather than evidence and are not shown.
 */
export function CurrentMastery({ courseId }: { courseId: string }) {
  const core = useLearningCore();
  const concepts = useMemo(() => {
    if (core.status !== "healthy" || core.demoStatePending || core.demoStateError || !core.demoState || courseId === "") return [];
    return core.demoState.mastery
      .filter((row) => row.course_id === courseId && row.attempts > 0)
      .sort((left, right) => left.probability - right.probability)
      .slice(0, MAX_CONCEPTS);
  }, [core.status, core.demoStatePending, core.demoStateError, core.demoState, courseId]);

  if (concepts.length === 0) return null;

  return (
    <section className="history-section history-mastery" aria-labelledby="history-mastery-title">
      <div className="history-list-head">
        <div>
          <h2 id="history-mastery-title">Current mastery</h2>
          <span>Based on recorded recall and practice attempts.</span>
        </div>
      </div>
      <ul className="history-mastery-list">
        {concepts.map((concept) => {
          const percent = Math.round(concept.probability * 100);
          const attemptLabel = `${concept.attempts} ${concept.attempts === 1 ? "attempt" : "attempts"}`;
          return (
            <li key={concept.concept_id}>
              <div className="history-mastery-head">
                <strong title={concept.concept_name}>{concept.concept_name}</strong>
                <span>{percent}%</span>
                <small>{attemptLabel}</small>
              </div>
              <div
                className="history-mastery-bar"
                role="meter"
                aria-label={concept.concept_name}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
                aria-valuetext={`${percent}% current mastery from ${attemptLabel}`}
              >
                <span style={{ width: `${concept.probability * 100}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
