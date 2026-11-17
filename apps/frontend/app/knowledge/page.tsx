"use client";

import {PageHeading} from "@/components/ui";
import {ResourceNav} from "@/components/ResourceNav";

import Link from "next/link";
import {useRouter, useSearchParams} from "next/navigation";
import {FormEvent, Suspense, useEffect, useState} from "react";
import {apiRequest, errorMessage} from "@/lib/api";
import {Brief, Source, nodeHref, types, useWorkspace} from "@/lib/knowledge";
import {KnowledgeReader} from "@/components/KnowledgeReader";

function Library() {
  const params = useSearchParams();
  return <LibraryView key={params.toString()} query={params.toString()}/>;
}

function LibraryView({query}: {query: string}) {
  const {user, error: authError} = useWorkspace();
  const router = useRouter();
  const params = new URLSearchParams(query);
  const id = params.get("id");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [book, setBook] = useState(params.get("book") ?? "");
  const [chapter, setChapter] = useState(params.get("chapter") ?? "");
  const [kind, setKind] = useState(params.get("kind") ?? "");
  const [sources, setSources] = useState<Source[]>([]);
  const [result, setResult] = useState<{total: number; items: Brief[]} | null>(null);
  const [error, setError] = useState("");
  const rawOffset = Number(params.get("offset") ?? 0);
  const offset = Number.isInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0;
  useEffect(() => {
    if (!user) return;
    let active = true;
    void apiRequest<Source[]>("/knowledge/sources").then(s => {if (active) setSources(s);}).catch(e => {if (active) setError(errorMessage(e));});
    if (!id) void apiRequest<{total: number; items: Brief[]}>(`/knowledge/search?${query}`).then(r => {if (active) setResult(r);}).catch(e => {if (active) setError(errorMessage(e));});
    return () => {active = false;};
  }, [user, id, query]);
  function search(e: FormEvent) {
    e.preventDefault(); const p = new URLSearchParams();
    if (q) p.set("q", q); if (book) p.set("book", book); if (chapter) p.set("chapter", chapter); if (kind) p.set("kind", kind);
    router.push(`/knowledge?${p}`);
  }
  function pageHref(n: number) {const p = new URLSearchParams(query); p.set("offset", String(n)); return `/knowledge?${p}`;}
  return <main className="container library"><PageHeading title="Thư viện học tập" description="Tra cứu nội dung, đọc các mối liên hệ và đối chiếu tài liệu nguồn."/><ResourceNav/>
    <form className="card wide search-form" onSubmit={search}>
      <label>Từ khóa<input value={q} onChange={e => setQ(e.target.value)} placeholder="Ví dụ: trật khớp vai" maxLength={200}/></label>
      <label>Sách<select value={book} onChange={e => {setBook(e.target.value); setChapter("");}}><option value="">Tất cả sách</option>{sources.map(s => <option key={s.id} value={s.id}>{s.title} ({s.year})</option>)}</select></label>
      <label>Bài<select value={chapter} onChange={e => setChapter(e.target.value)} disabled={!book}><option value="">Tất cả bài</option>{sources.find(s => s.id === book)?.chapters.map(c => <option key={c.number} value={c.number}>Bài {c.number}. {c.title}</option>)}</select></label>
      <label>Loại nội dung<select value={kind} onChange={e => setKind(e.target.value)}><option value="">Tất cả loại</option>{Object.entries(types).filter(([v]) => !v.startsWith("Curriculum") && v !== "Course").map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>
      <button disabled={!user}>Tìm kiếm</button>
    </form>
    {(authError || error) && <p className="error" role="alert">{authError || error}</p>}
    {!user && !authError && <p role="status">Đang xác thực…</p>}
    {user && id ? <><Link href="/knowledge">← Quay lại thư viện</Link><KnowledgeReader key={id} id={id} user={user}/></> : result ? <section aria-live="polite"><p>{result.total} nội dung · {result.total ? offset + 1 : 0}–{Math.min(offset + 20, result.total)}</p>
      <div className="result-list">{result.items.map(n => <Link className="result-item" href={nodeHref(n.id)} key={n.id}><h2>{n.title}</h2><span className="badge">{types[n.type] ?? "Nội dung học tập"}</span><p className="muted">{n.snippet}</p><span className="text-link">Đọc nội dung và nguồn →</span></Link>)}</div>
      {!result.total && <p className="notice">Chưa tìm thấy nội dung phù hợp. Thử từ khóa khác hoặc bỏ bớt bộ lọc.</p>}
      <nav className="actions" aria-label="Phân trang">{offset > 0 && <Link className="button secondary" href={pageHref(Math.max(0, offset - 20))}>Trang trước</Link>}{offset + 20 < result.total && <Link className="button secondary" href={pageHref(offset + 20)}>Trang sau</Link>}</nav>
    </section> : user && !error && !id && <p role="status">Đang đọc thư viện…</p>}
  </main>;
}

export default function KnowledgePage() {return <Suspense fallback={<main className="container">Đang mở thư viện…</main>}><Library/></Suspense>;}
