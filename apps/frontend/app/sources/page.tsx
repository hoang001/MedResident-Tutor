"use client";

import {PageHeading} from "@/components/ui";
import {ResourceNav} from "@/components/ResourceNav";

import Link from "next/link";
import {useSearchParams} from "next/navigation";
import {Suspense, useEffect, useState} from "react";
import {apiRequest, errorMessage, getToken, loginRedirect, parseApiError} from "@/lib/api";
import {Source, pdfHref, useWorkspace} from "@/lib/knowledge";

function Sources() {
  const params = useSearchParams();
  return <SourcesView key={params.toString()} query={params.toString()}/>;
}
function SourcesView({query}: {query: string}) {
  const {user, error: authError} = useWorkspace();
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [blob, setBlob] = useState("");
  const params = new URLSearchParams(query);
  const source = sources.find(s => s.id === params.get("id"));
  const requested = Number(params.get("page") ?? "1");
  const page = source && Number.isInteger(requested) && requested > 0 && requested <= source.pages ? requested : 1;
  useEffect(() => {
    if (!user) return; let active = true;
    void apiRequest<Source[]>("/knowledge/sources").then(s => {if (active) setSources(s);}).catch(e => {if (active) setError(errorMessage(e));});
    return () => {active = false;};
  }, [user]);
  useEffect(() => () => {if (blob) URL.revokeObjectURL(blob);}, [blob]);
  async function openPdf() {
    if (!source) return; setBusy(true); setError("");
    try {
      const token = getToken(); if (!token) {loginRedirect(); return;}
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/knowledge/pdf/${encodeURIComponent(source.id)}`, {headers: {Authorization: `Bearer ${token}`}, cache: "no-store", signal: AbortSignal.timeout(120000)});
      if (!response.ok) {
        if (response.status === 401) loginRedirect("expired");
        let payload = null; try {payload = await response.json();} catch { /* Generic error below. */ }
        throw parseApiError(response.status, payload);
      }
      if (!response.headers.get("content-type")?.includes("application/pdf")) throw new Error("Invalid PDF");
      setBlob(URL.createObjectURL(await response.blob()));
    } catch (e) {setError(errorMessage(e));} finally {setBusy(false);}
  }
  return <main className="container library"><PageHeading title="Sách & mục lục" description="Đọc theo từng bài và mở tài liệu tại trang PDF được dẫn."/><ResourceNav/>
    {(authError || error) && <p className="error" role="alert">{authError || error}</p>}
    {!sources.length && !error && !authError && <p role="status">Đang tải danh mục…</p>}
    <div className="source-grid">{sources.map(s => <section key={s.id} className="card wide"><h2><Link href={pdfHref(s.id)}>{s.title}</Link></h2><p className="helper">Đại học Y Hà Nội · {s.year}</p><p>{s.pages} trang PDF · {s.chapters.length} bài · {s.node_count} mục kiến thức</p><p className="muted">Bản nháp đã đối chiếu nguồn, chưa phê duyệt chuyên môn.</p><Link href={`/knowledge?book=${s.id}`}>Tra cứu nội dung trong sách →</Link></section>)}</div>
    {source && <section className="card wide"><h2>{source.title}</h2><p className="notice">Nội dung phản ánh tài liệu năm {source.year}; chưa mặc định là hướng dẫn thực hành hiện hành.</p>
      <div className="actions"><button onClick={openPdf} disabled={busy || !source.pdf_available || !!blob}>{busy ? "Đang mở PDF…" : blob ? "Đã mở PDF" : `Mở PDF gốc · trang ${page}`}</button>{blob && <a className="button secondary" target="_blank" rel="noopener noreferrer" href={`${blob}#page=${page}`}>Mở ở thẻ mới</a>}</div>
      {!source.pdf_available && <p className="notice">Bản PDF hiện chưa sẵn sàng trong thư viện.</p>}
      {blob && <iframe title={`${source.title}, trang ${page}`} className="pdf-viewer" src={`${blob}#page=${page}`}/>}
      <h3>Mục lục theo sách</h3><ol className="chapter-list">{source.chapters.map(c => <li key={c.number} value={c.number}><div><strong>{c.title}</strong><p className="muted">Trang PDF {c.start}–{c.end}{c.opening_missing && " · Thiếu phần mở đầu trong file nguồn"}</p></div><div className="inline-actions"><Link href={`/knowledge?book=${source.id}&chapter=${c.number}`}>Đọc kiến thức</Link><Link href={pdfHref(source.id, c.start)}>Xem trang nguồn</Link></div></li>)}</ol>
      {user?.role==="ADMIN"&&<details><summary>Thông tin kiểm tra tài liệu</summary><p>SHA-256 của PDF</p><code className="hash">{source.sha256}</code><p>Hash giúp nhận biết phiên bản file, không xác nhận độ đúng chuyên môn.</p></details>}
    </section>}
  </main>;
}
export default function SourcesPage() {return <Suspense fallback={<main className="container">Đang mở nguồn…</main>}><Sources/></Suspense>;}
