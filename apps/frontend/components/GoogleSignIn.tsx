"use client";
import Script from "next/script";
import {useEffect, useRef, useState} from "react";
import {useRouter} from "next/navigation";
import {apiRequest, errorMessage, safeReturnPath, saveToken} from "@/lib/api";

type GoogleIdentity = {accounts: {id: {
  initialize: (options: {client_id: string; nonce: string; callback: (result: {credential: string}) => void}) => void;
  renderButton: (element: HTMLElement, options: {theme: string; size: string; text: string}) => void;
}}};
declare global {interface Window {google?: GoogleIdentity}}

export function GoogleSignIn() {
  const router = useRouter();
  const container = useRef<HTMLDivElement>(null);
  const [config, setConfig] = useState<{client_id: string | null; nonce: string | null}>();
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    apiRequest<{client_id: string | null; nonce: string | null}>("/auth/google/config", {credentials: "include"})
      .then(value => {if (active) setConfig(value);})
      .catch(() => {if (active) setError("Không thể tải đăng nhập Google. Bạn vẫn có thể dùng email và mật khẩu.");});
    return () => {active = false;};
  }, []);
  useEffect(() => {
    if (!loaded || !config?.client_id || !config.nonce || !container.current || !window.google) return;
    window.google.accounts.id.initialize({client_id: config.client_id, nonce: config.nonce, callback: result => {
      setBusy(true); setError("");
      void apiRequest<{access_token: string}>("/auth/google", {
        method: "POST", credentials: "include", body: JSON.stringify({credential: result.credential}),
      }, {redirectOn401: false}).then(value => {
        saveToken(value.access_token);
        router.replace(safeReturnPath(new URLSearchParams(window.location.search).get("next")));
      }).catch(reason => setError(errorMessage(reason))).finally(() => setBusy(false));
    }});
    container.current.replaceChildren();
    window.google.accounts.id.renderButton(container.current, {theme: "outline", size: "large", text: "continue_with"});
  }, [loaded, config, router]);
  return <section aria-label="Đăng nhập bằng Google">
    <p className="muted">Hoặc tiếp tục bằng Google</p>
    {config?.client_id ? <><Script src="https://accounts.google.com/gsi/client" onReady={() => setLoaded(true)} onError={() => setError("Không thể tải Google. Vui lòng thử lại sau.")}/><div ref={container} hidden={busy}/></> : <button type="button" className="secondary" disabled>Google — chưa được cấu hình</button>}
    {busy && <p role="status">Đang đăng nhập…</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
