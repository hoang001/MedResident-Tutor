"use client";

import { FormEvent, useState } from "react";
import { apiRequest } from "@/lib/api";

type RAGResponse = { answer: string; warning: string | null; grounded: boolean; provider: string };

export default function LearnPage() {
  const [result, setResult] = useState<RAGResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError(""); setResult(null);
    const question = new FormData(event.currentTarget).get("question");
    try { setResult(await apiRequest<RAGResponse>("/ai/rag/query", { method: "POST", body: JSON.stringify({ question, topic_id: null }) })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Query failed"); }
    finally { setLoading(false); }
  }
  return <div className="container"><section className="card"><h1>Learn</h1><p className="muted">The current endpoint uses an empty retriever and safe mock provider.</p><form onSubmit={submit}><label>Learning question<textarea name="question" required /></label><button disabled={loading}>{loading ? "Submitting…" : "Ask mock RAG"}</button></form>{error && <p className="error">{error}</p>}{result && <div className="notice"><p>{result.answer}</p><strong>{result.warning}</strong><p>Provider: {result.provider}; grounded: {String(result.grounded)}</p></div>}</section></div>;
}
