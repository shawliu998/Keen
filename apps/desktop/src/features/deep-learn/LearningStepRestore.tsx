export function LearningStepRestore({ label }: { label: string }) {
  return <div className="learning-step-restore" role="status" aria-label={label}>
    <span>{label}</span>
    <i className="restore-line short" aria-hidden="true" />
    <i className="restore-line heading" aria-hidden="true" />
    <i className="restore-line long" aria-hidden="true" />
    <i className="restore-line medium" aria-hidden="true" />
    <div className="restore-action" aria-hidden="true"><i /><i /></div>
  </div>;
}
