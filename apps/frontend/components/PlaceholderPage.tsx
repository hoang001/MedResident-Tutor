export function PlaceholderPage({ title, detail }: { title: string; detail: string }) {
  return <main className="container"><section className="card"><h1>{title}</h1><p>{detail}</p><p className="muted">This module is a foundation placeholder and does not claim completed AI functionality.</p></section></main>;
}
