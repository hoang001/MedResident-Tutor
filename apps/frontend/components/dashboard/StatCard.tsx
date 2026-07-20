interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  emphasis?: boolean;
}

export function StatCard({ label, value, hint, emphasis = false }: StatCardProps) {
  return (
    <div className={`stat-card ${emphasis ? "stat-card--emphasis" : ""}`}>
      <p className="stat-card-label">{label}</p>
      <p className="stat-card-value">{value}</p>
      {hint ? <p className="stat-card-hint muted">{hint}</p> : null}
    </div>
  );
}
