import type { ReactNode } from "react";

export function Page({ title, description, actions, children, className = "" }: { title: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return <div data-slot="page" className={`page ${className}`}><div data-slot="page-header" className="page-header"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</div>{children}</div>;
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: readonly T[]; onChange: (value: T) => void }) {
  return <div data-slot="tabs-list" data-variant="pill" className="segmented" role="group">{options.map((option) => <button data-slot="tabs-trigger" type="button" key={option} className={value === option ? "active" : ""} aria-pressed={value === option} onClick={() => onChange(option)}>{option.charAt(0).toUpperCase() + option.slice(1)}</button>)}</div>;
}
