import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Spinner({ small = false }: { small?: boolean }) {
  return <span className={`spinner${small ? " spinner--small" : ""}`} aria-hidden="true" />;
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "primary",
  loading = false,
  icon,
  children,
  disabled,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`button button--${variant} ${className}`.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Spinner small /> : icon}
      <span>{children}</span>
    </button>
  );
}

export function Modal({
  title,
  subtitle,
  children,
  onClose,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal__header">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  text,
  action,
}: {
  icon: string;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-banner" role="alert">
      <span className="error-banner__icon">!</span>
      <div>
        <strong>Не удалось выполнить запрос</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}

export function ScoreBar({ value, label }: { value: number; label?: string }) {
  const normalized = Math.max(0, Math.min(1, value));
  return (
    <div className="score-bar">
      <div className="score-bar__meta">
        <span>{label || "Уверенность"}</span>
        <strong>{Math.round(normalized * 100)}%</strong>
      </div>
      <div className="score-bar__track">
        <span style={{ width: `${normalized * 100}%` }} />
      </div>
    </div>
  );
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`tag tag--${tone}`}>{children}</span>;
}
