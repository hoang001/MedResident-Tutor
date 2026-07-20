// Reusable loading / error / empty states used across data-driven views.

interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = "Đang tải dữ liệu…" }: LoadingStateProps) {
  return (
    <div className="state-view" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Không thể tải dữ liệu",
  message,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="state-view state-view--error" role="alert">
      <p className="state-view-title">{title}</p>
      <p className="muted">{message}</p>
      {onRetry ? (
        <button type="button" className="button secondary" onClick={onRetry}>
          Thử lại
        </button>
      ) : null}
    </div>
  );
}

interface EmptyStateProps {
  title?: string;
  message: string;
  action?: React.ReactNode;
}

export function EmptyState({
  title = "Chưa có dữ liệu",
  message,
  action,
}: EmptyStateProps) {
  return (
    <div className="state-view state-view--empty">
      <p className="state-view-title">{title}</p>
      <p className="muted">{message}</p>
      {action}
    </div>
  );
}

interface InlineEmptyProps {
  message: string;
}

/** Compact empty message for use inside a card body. */
export function InlineEmpty({ message }: InlineEmptyProps) {
  return <p className="inline-empty muted">{message}</p>;
}
