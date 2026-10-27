"use client";
import Link from "next/link";
import {useEffect, useState} from "react";
import {apiRequest, clearToken, getToken, loginRedirect, logout} from "@/lib/api";
const links = [["Dashboard", "/dashboard"], ["Luyện tập", "/learn"], ["Exams", "/exams"], ["Progress", "/progress"]];
export function Nav() {
  const [admin, setAdmin] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    let expiryTimer: ReturnType<typeof setTimeout> | undefined;
    const update = () => {
      clearTimeout(expiryTimer);
      const token = getToken(); setSignedIn(!!token); setAdmin(false);
      if (token) void apiRequest<{role: string}>("/auth/me", {}, {redirectOn401: false}).then(user => {if (getToken() === token) setAdmin(user.role === "ADMIN");}).catch(() => setAdmin(false));
      if (!token) return;
      try {
        const claims = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
        if (typeof claims.exp === "number" && Number.isFinite(claims.exp)) {
          expiryTimer = setTimeout(() => {clearToken(); loginRedirect("expired");}, Math.max(0, Math.min(claims.exp * 1000 - Date.now(), 2147483647)));
        }
      } catch { /* Malformed credentials are rejected by backend /auth/me. */ }
    };
    queueMicrotask(update);
    window.addEventListener("auth-changed", update);
    window.addEventListener("storage", update);
    return () => {clearTimeout(expiryTimer); window.removeEventListener("auth-changed", update); window.removeEventListener("storage", update);};
  }, []);
  return <header className="nav"><Link className="brand" href="/">Resident Learning</Link><nav>
    {links.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}
    {admin && <><Link href="/admin/questions">Ngân hàng câu hỏi</Link><Link href="/admin/documents">Documents</Link></>}
    {signedIn ? <button className="secondary" onClick={logout}>Đăng xuất</button> : <><Link href="/login">Đăng nhập</Link><Link href="/register">Đăng ký</Link></>}
  </nav></header>;
}
