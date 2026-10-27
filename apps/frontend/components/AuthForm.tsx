"use client";
import {FormEvent, useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import Link from "next/link";
import {GoogleSignIn} from "@/components/GoogleSignIn";
import {ApiError, apiRequest, errorMessage, safeReturnPath, saveToken} from "@/lib/api";

export function AuthForm({register = false}: {register?: boolean}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const reason = new URLSearchParams(window.location.search).get("reason");
    queueMicrotask(() => setNotice(reason === "expired" ? "Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục; bản nháp được giữ riêng cho tài khoản của bạn." : reason === "logout" ? "Đã đăng xuất trên trình duyệt này." : reason === "required" ? "Vui lòng đăng nhập để tiếp tục." : ""));
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(""); setFields({});
    const data = new FormData(event.currentTarget);
    if (register && data.get("password") !== data.get("confirm_password")) {
      setFields({confirm_password: "Mật khẩu xác nhận không khớp."});
      setBusy(false); return;
    }
    const credentials = {email: data.get("email"), password: data.get("password")};
    try {
      if (register) await apiRequest("/auth/register", {method: "POST", body: JSON.stringify({...credentials, full_name: data.get("full_name")})});
      const result = await apiRequest<{access_token: string}>("/auth/login", {method: "POST", body: JSON.stringify(credentials)});
      saveToken(result.access_token);
      const next = safeReturnPath(new URLSearchParams(window.location.search).get("next"));
      router.replace(next);
    } catch (reason) {
      setFields(reason instanceof ApiError ? reason.fields : {});
      setError(reason instanceof ApiError && reason.status === 401 ? "Email hoặc mật khẩu không đúng." : errorMessage(reason));
    } finally { setBusy(false); }
  }
  return <main className="container"><section className="card"><h1>{register ? "Tạo tài khoản" : "Đăng nhập"}</h1>
    {notice && <p className="notice" role="status">{notice}</p>}
    <form onSubmit={submit} noValidate>
      {register && <><label htmlFor="auth-name">Họ tên</label><input id="auth-name" name="full_name" autoComplete="name" aria-invalid={!!fields.full_name} aria-describedby="full-name-error"/><span className="error" id="full-name-error">{fields.full_name}</span></>}
      <label htmlFor="auth-email">Email</label><input id="auth-email" name="email" type="email" autoComplete="username" aria-invalid={!!fields.email} aria-describedby="email-error"/><span className="error" id="email-error">{fields.email}</span>
      <label htmlFor="auth-password">Mật khẩu</label><input id="auth-password" name="password" type="password" autoComplete={register ? "new-password" : "current-password"} aria-invalid={!!fields.password} aria-describedby="password-error"/><span className="error" id="password-error">{fields.password}</span>
      {register && <><p className="muted">Mật khẩu từ 8 đến 128 ký tự.</p><label htmlFor="auth-confirm">Xác nhận mật khẩu</label><input id="auth-confirm" name="confirm_password" type="password" autoComplete="new-password" aria-invalid={!!fields.confirm_password} aria-describedby="confirm-password-error"/><span className="error" id="confirm-password-error">{fields.confirm_password}</span></>}
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Đang xử lý…" : register ? "Tạo tài khoản" : "Đăng nhập"}</button>
    </form>
    <p>{register ? "Đã có tài khoản? " : "Chưa có tài khoản? "}<Link href={register ? "/login" : "/register"}>{register ? "Đăng nhập" : "Đăng ký"}</Link></p>
    <GoogleSignIn/>
    </section></main>;
}
