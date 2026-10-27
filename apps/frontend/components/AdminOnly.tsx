"use client";
import {ReactNode, useEffect, useState} from "react";
import {apiRequest, errorMessage, getToken, loginRedirect} from "@/lib/api";
export function AdminOnly({children}: {children: ReactNode}) {
  const [allowed, setAllowed] = useState(false);
  const [message, setMessage] = useState("Đang kiểm tra quyền quản trị…");
  useEffect(() => {
    let active = true;
    async function check() {
      if (!active) return;
      setAllowed(false);
      const token = getToken();
      if (!token) {loginRedirect(); return;}
      try {
        const user = await apiRequest<{role: string}>("/auth/me");
        if (active && getToken() === token) {setAllowed(user.role === "ADMIN"); setMessage(user.role === "ADMIN" ? "" : "Bạn không có quyền quản trị.");}
      } catch(reason) {if (active) setMessage(errorMessage(reason));}
    }
    queueMicrotask(() => void check());
    const changed = (e: StorageEvent) => {if (e.key === "access_token") void check();};
    window.addEventListener("storage", changed);
    return () => {active = false; window.removeEventListener("storage", changed);};
  }, []);
  return allowed ? children : <main className="container"><p role="status">{message}</p></main>;
}
