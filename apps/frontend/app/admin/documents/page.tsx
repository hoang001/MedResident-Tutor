"use client";

import { FormEvent, useState } from "react";
import { apiRequest } from "@/lib/api";

export default function DocumentsPage() {
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError(""); setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const document = await apiRequest<{ name: string; processing_status: string }>("/documents/upload", { method: "POST", body: form });
      setMessage(`${document.name} uploaded with status ${document.processing_status}. OCR and indexing have not started.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Upload failed"); }
    finally { setLoading(false); }
  }
  return <main className="container"><section className="card"><h1>Document administration</h1><p>Admin access is required. Accepted types: PDF, TXT, and Markdown.</p><form onSubmit={submit}><label>Display name (optional)<input name="name" /></label><label>File<input name="file" type="file" accept=".pdf,.txt,.md,.markdown" required /></label><button disabled={loading}>{loading ? "Uploading…" : "Upload"}</button></form>{error && <p className="error">{error}</p>}{message && <p className="notice">{message}</p>}</section></main>;
}
