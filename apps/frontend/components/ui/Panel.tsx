import Link from "next/link";

interface PanelProps {
  title: string;
  description?: string;
  action?: { label: string; href: string };
  children: React.ReactNode;
}

/** A titled surface/section used to group related dashboard content. */
export function Panel({ title, description, action, children }: PanelProps) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">{title}</h2>
          {description ? <p className="panel-desc muted">{description}</p> : null}
        </div>
        {action ? (
          <Link href={action.href} className="panel-action">
            {action.label}
          </Link>
        ) : null}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
