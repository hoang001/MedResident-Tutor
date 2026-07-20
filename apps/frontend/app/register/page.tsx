"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiRequest, saveToken } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    const data = new FormData(event.currentTarget);
    const credentials = { email: data.get("email"), password: data.get("password") };
    try {
      await apiRequest("/auth/register", { method: "POST", body: JSON.stringify({ ...credentials, full_name: data.get("full_name") }) });
      const result = await apiRequest<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify(credentials) });
      saveToken(result.access_token); router.push("/dashboard");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to register"); }
    finally { setLoading(false); }
  }
  return <main className="container"><section className="card"><h1>Create learner account</h1><form onSubmit={submit}><label>Full name<input name="full_name" required /></label><label>Email<input name="email" type="email" required /></label><label>Password<input name="password" type="password" minLength={8} required /></label>{error && <p className="error">{error}</p>}<button disabled={loading}>{loading ? "Creating…" : "Create account"}</button></form></section></main>;
}
