import type { ReactNode } from "react";

export function CollectionEmptyState({
  icon,
  label,
  count,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  label: string;
  count: string;
  title: string;
  description: string;
  action: ReactNode;
}) {
  return (
    <section className="collection-empty" aria-labelledby="collection-empty-title">
      <header>
        <strong>{label}</strong>
        <span>{count}</span>
      </header>
      <div className="collection-empty-body">
        <span className="collection-empty-icon" aria-hidden="true">{icon}</span>
        <h2 id="collection-empty-title">{title}</h2>
        <p>{description}</p>
        <div className="collection-empty-action">{action}</div>
      </div>
    </section>
  );
}
