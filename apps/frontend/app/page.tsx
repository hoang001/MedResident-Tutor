import Link from "next/link";

export default function Home() {
  return <main className="container"><section className="hero"><p className="muted">FOUNDATION PROTOTYPE</p><h1>Structured learning support for medical residents</h1><p>Organize topics, practice assessments, track learning progress, and prepare a grounded knowledge workflow.</p><div className="notice"><strong>Learning support only.</strong> This prototype is not a diagnostic tool and must not be used for clinical decisions or patient care.</div><div className="actions"><Link className="button" href="/register">Create account</Link><Link className="button secondary" href="/login">Sign in</Link></div></section></main>;
}
