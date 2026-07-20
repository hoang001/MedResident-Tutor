"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiRequest, saveToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const result = await apiRequest<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) });
      saveToken(result.access_token); router.push("/dashboard");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to sign in"); }
    finally { setLoading(false); }
  }
  return <main className="container"><section className="card"><h1>Sign in</h1><form onSubmit={submit}><label>Email<input name="email" type="email" required /></label><label>Password<input name="password" type="password" required /></label>{error && <p className="error">{error}</p>}<button disabled={loading}>{loading ? "Signing in…" : "Sign in"}</button></form></section></main>;
}
