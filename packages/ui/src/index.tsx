import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "secondary" | "primary" | "soft" | "outline" | "danger" | "ghost";
  size?: "small" | "medium";
  loading?: boolean;
  loadingLabel?: string;
};

export function Button({ className = "", variant = "secondary", size = "medium", loading = false, loadingLabel, disabled, children, ...props }: ButtonProps) {
  return <button
    {...props}
    data-slot="button"
    data-variant={variant}
    data-size={size}
    className={`ui-button ui-button-${variant} ui-button-${size} ${className}`.trim()}
    aria-busy={loading ? true : props["aria-busy"]}
    aria-label={loading && loadingLabel ? loadingLabel : props["aria-label"]}
    disabled={disabled || loading}
  >
    {loading && <span className="ui-button-spinner" aria-hidden />}
    {children}
  </button>;
}

export function IconButton({ label, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return <button type="button" data-slot="icon-button" aria-label={label} title={label} className={`icon-button ${className}`.trim()} {...props}>{children}</button>;
}

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card" className={`card ${className}`.trim()} {...props} />;
}

export function Badge({ tone = "neutral", children, className = "", ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "accent" | "success" | "warning" | "danger"; children: ReactNode }) {
  return <span data-slot="badge" data-tone={tone} className={`badge badge-${tone} ${className}`.trim()} {...props}>{children}</span>;
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const bounded = Math.max(0, Math.min(100, value));
  return <div data-slot="progress" className="progress" role="progressbar" aria-label={label ?? `Progress ${bounded}%`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(bounded)}><span style={{ transform: `scaleX(${bounded / 100})` }} /></div>;
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <div data-slot="empty-state" className="empty-state">{icon}<h3>{title}</h3><p>{description}</p>{action}</div>;
}

type ControlStyleProps = {
  variant?: "outline" | "soft";
  controlSize?: "small" | "medium" | "large";
};

export function Input({
  className = "",
  variant = "outline",
  controlSize = "medium",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & ControlStyleProps) {
  return <input
    {...props}
    data-slot="input"
    data-variant={variant}
    data-size={controlSize}
    className={`ui-input ui-input-${variant} ui-input-${controlSize} ${className}`.trim()}
  />;
}

export function Textarea({
  className = "",
  variant = "outline",
  controlSize = "medium",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & ControlStyleProps) {
  return <textarea
    {...props}
    data-slot="textarea"
    data-variant={variant}
    data-size={controlSize}
    className={`ui-input ui-textarea ui-input-${variant} ui-input-${controlSize} ${className}`.trim()}
  />;
}

export function Select({
  className = "",
  variant = "outline",
  controlSize = "medium",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & ControlStyleProps) {
  return <select
    {...props}
    data-slot="select"
    data-variant={variant}
    data-size={controlSize}
    className={`ui-input ui-select ui-input-${variant} ui-input-${controlSize} ${className}`.trim()}
  />;
}

export function Field({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="field" className={`ui-field ${className}`.trim()} {...props} />;
}

export function FieldLabel({ className = "", ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label data-slot="field-label" className={`ui-field-label ${className}`.trim()} {...props} />;
}

export function FieldDescription({ className = "", ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p data-slot="field-description" className={`ui-field-description ${className}`.trim()} {...props} />;
}

export function FieldError({ className = "", role, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p data-slot="field-error" className={`ui-field-error ${className}`.trim()} role={role ?? "alert"} {...props} />;
}

export function Alert({
  tone = "neutral",
  className = "",
  role,
  ...props
}: HTMLAttributes<HTMLDivElement> & { tone?: "neutral" | "info" | "success" | "warning" | "danger" }) {
  return <div data-slot="alert" data-tone={tone} className={`ui-alert ui-alert-${tone} ${className}`.trim()} role={role ?? "alert"} {...props} />;
}

export function Skeleton({
  effect = "shimmer",
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement> & { effect?: "shimmer" | "pulse" | "none" }) {
  return <div data-slot="skeleton" data-effect={effect} className={`ui-skeleton ui-skeleton-${effect} ${className}`.trim()} aria-hidden="true" {...props} />;
}

export function Separator({
  orientation = "horizontal",
  className = "",
  role,
  ...props
}: HTMLAttributes<HTMLDivElement> & { orientation?: "horizontal" | "vertical" }) {
  return <div data-slot="separator" data-orientation={orientation} className={`ui-separator ${className}`.trim()} role={role ?? "separator"} aria-orientation={orientation} {...props} />;
}
