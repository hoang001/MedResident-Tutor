interface ProgressBarProps {
  value: number;
  /** Visual tone of the fill. */
  tone?: "primary" | "warning";
  label?: string;
}

export function ProgressBar({ value, tone = "primary", label }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span
        className={`progress-fill progress-fill--${tone}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
