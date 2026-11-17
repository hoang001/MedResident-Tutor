"use client";

import {PageHeading} from "@/components/ui";
import {ResourceNav} from "@/components/ResourceNav";

import Link from "next/link";
import {useRouter, useSearchParams} from "next/navigation";
import {Suspense, useEffect, useState} from "react";
import {apiRequest, errorMessage} from "@/lib/api";
import {StudyQuestion, Source, StudySession, date, relations, useWorkspace} from "@/lib/knowledge";
import {Citations} from "@/components/KnowledgeReader";
import {newRequestKey} from "@/lib/idempotency";

function Exams() {const p = useSearchParams(); return <SelfStudy key={p.toString()} query={p.toString()}/>;}
function SelfStudy({query}: {query: string}) {
  const router = useRouter();
  const {user, error: authError} = useWorkspace();
  const sessionId = new URLSearchParams(query).get("session");
  const nodeId = new URLSearchParams(query).get("node") ?? "";
  const [sources, setSources] = useState<Source[]>([]);
  const [book, setBook] = useState(nodeId ? "" : "SRC_ORTHO_TEXTBOOK_001");
  const [origin, setOrigin] = useState("all");
  const [focus, setFocus] = useState("all");
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [chapter, setChapter] = useState("");
  const [questionPage, setQuestionPage] = useState(0);
  const [bank, setBank] = useState<{total: number; items: StudyQuestion[]}>({total: 0, items: []});
  const [selected, setSelected] = useState<string[]>([]);
  const [session, setSession] = useState<StudySession | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dirty = session?.status === "draft" && JSON.stringify(answers) !== JSON.stringify(session.answers);
  useEffect(() => {
    if (!user) return; let active = true;
    if (sessionId) {
      void apiRequest<StudySession>(`/study/sessions/${encodeURIComponent(sessionId)}`).then(s => {if (active) {setSession(s); setAnswers(s.answers); setLoading(false);}}).catch(e => {if (active) {setError(errorMessage(e)); setLoading(false);}});
    } else {
      void apiRequest<Source[]>("/knowledge/sources").then(s => {if (active) setSources(s);}).catch(e => {if (active) setError(errorMessage(e));});
      void apiRequest<{total: number; items: StudyQuestion[]}>(`/study/questions?origin=${origin}&focus=${focus}&q=${encodeURIComponent(submittedSearch)}&book=${encodeURIComponent(book)}&offset=${questionPage * 50}&limit=50${chapter ? `&chapter=${chapter}` : ""}${nodeId ? `&node_id=${encodeURIComponent(nodeId)}` : ""}`)
        .then(r => {if (active) {setBank(r); setLoading(false);}}).catch(e => {if (active) {setError(errorMessage(e)); setLoading(false);}});
    }
    return () => {active = false;};
  }, [user, sessionId, book, chapter, questionPage, origin, focus, submittedSearch, nodeId]);
  useEffect(() => {
    if (!dirty) return;
    const unload = (e: BeforeUnloadEvent) => {e.preventDefault();};
    const navigate = (e: MouseEvent) => {if ((e.target as HTMLElement).closest("a") && !window.confirm("Câu trả lời chưa lưu. Bạn muốn rời trang?")) {e.preventDefault(); e.stopPropagation();}};
    window.addEventListener("beforeunload", unload); document.addEventListener("click", navigate, true);
    return () => {window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true);};
  }, [dirty]);
  async function create() {
    if (!user || busy) return; setBusy(true); setError("");
    try {
      const storageKey = `study-create:${user.id}`;
      let pending: {idempotency_key: string; question_ids: string[]} | null = null;
      try {pending = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");} catch { /* Replace invalid stored selection. */ }
      if (!pending || !/^[a-f0-9-]{36}$/.test(pending.idempotency_key) || JSON.stringify(pending.question_ids) !== JSON.stringify(selected)) pending = {idempotency_key: newRequestKey(), question_ids: selected};
      sessionStorage.setItem(storageKey, JSON.stringify(pending));
      const s = await apiRequest<StudySession>("/study/sessions", {method: "POST", body: JSON.stringify(pending)});
      router.push(`/exams?session=${s.id}`); sessionStorage.removeItem(storageKey);
    } catch (e) {setError(errorMessage(e));} finally {setBusy(false);}
  }
  async function save(submit: boolean) {
    if (!session || busy) return;
    if (submit && !window.confirm("Hoàn tất và khóa bài này? Hệ thống lưu câu trả lời để bạn xem lại, chưa chấm điểm.")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const s = await apiRequest<StudySession>(`/study/sessions/${session.id}`, {method: "PUT", body: JSON.stringify({version: session.version, answers, submit})});
      setSession(s); setAnswers(s.answers); setMessage(submit ? "Đã hoàn tất và lưu bài. Bài chưa được chấm điểm." : "Đã lưu bản nháp vào tài khoản.");
    } catch (e) {setError(errorMessage(e));} finally {setBusy(false);}
  }
  function changeBook(value: string) {setBook(value); setChapter(""); setSelected([]); setBank({total: 0, items: []}); setQuestionPage(0); setLoading(true); setError("");}
  function toggle(id: string) {setSelected(s => s.includes(id) ? s.filter(v => v !== id) : s.length < 20 ? [...s, id] : s);}
  return <main className="container library"><PageHeading title="Tự ôn theo tài liệu" description="Câu hỏi từ sách và gợi ý ôn tập theo nội dung, mối liên hệ có nguồn."/><ResourceNav/><p className="helper">Đây là khu vực tham khảo chưa chấm điểm. Để làm bài có đáp án và tiêu chí chấm, mở <Link href="/learn">ngân hàng bài tập</Link>.</p>
    <p className="notice">Bạn có thể lưu nháp, tiếp tục và hoàn tất bài. Chưa có đáp án được duyệt hoặc chấm điểm, nên bài này chưa dùng để đánh giá năng lực.</p>
    {(authError || error) && <p className="error" role="alert">{authError || error}</p>}
    {loading && !error && !authError && <p role="status">Đang mở bài tự luyện…</p>}
    {!sessionId && user && <section className="card wide"><h2>Chọn câu hỏi</h2>{nodeId && <p className="notice">Đang chọn câu liên quan đến nội dung bạn vừa đọc. <Link href="/exams">Mở toàn bộ ngân hàng tự luyện</Link></p>}<div className="filter-row"><label>Sách<select value={book} onChange={e => changeBook(e.target.value)} disabled={busy}><option value="">Tất cả sách</option>{sources.map(s => <option key={s.id} value={s.id}>{s.title} ({s.year})</option>)}</select></label><label>Bài<select value={chapter} onChange={e => {setChapter(e.target.value); setSelected([]); setQuestionPage(0); setLoading(true); setError("");}} disabled={busy}><option value="">Tất cả bài</option>{sources.find(s => s.id === book)?.chapters.map(c => <option key={c.number} value={c.number}>Bài {c.number}. {c.title}</option>)}</select></label></div>
      <div className="filter-row"><label>Nguồn câu hỏi<select aria-label="Nguồn câu hỏi" value={origin} disabled={busy} onChange={e => {setOrigin(e.target.value); setSelected([]); setQuestionPage(0); setLoading(true); setError("");}}><option value="all">Sách và mối liên hệ</option><option value="book">Câu lượng giá trong sách</option><option value="kg">Câu tự ôn từ mối liên hệ</option></select></label><label>Phạm vi ôn tập<select aria-label="Phạm vi ôn tập" value={focus} disabled={busy} onChange={e => {setFocus(e.target.value); setSelected([]); setQuestionPage(0); setLoading(true); setError("");}}><option value="all">Toàn bộ nội dung có nguồn</option><option value="read">Nội dung tôi đã đọc</option><option value="bookmarked">Nội dung tôi đánh dấu</option></select></label></div>
      <form className="filter-row" onSubmit={e => {e.preventDefault(); if (search === submittedSearch) return; setSubmittedSearch(search); setSelected([]); setQuestionPage(0); setLoading(true); setError("");}}><label>Tìm câu hỏi<input value={search} maxLength={200} onChange={e => setSearch(e.target.value)}/></label><button className="secondary" disabled={busy}>Tìm câu hỏi</button></form>
      {!loading && !bank.total && <p className="notice">Chưa có câu hỏi có đủ nguồn cho bộ lọc này. Hãy thử đổi sách, bài hoặc phạm vi đã đọc. Bạn vẫn có thể đọc tài liệu trong <Link href={`/knowledge?book=${book}`}>thư viện</Link>.</p>}
      {bank.total > 0 && <><p>{bank.total} câu trong phạm vi đã chọn · Đã chọn {selected.length}/20 câu</p><div className="actions"><button className="secondary" disabled={busy || loading} onClick={() => setSelected(bank.items.slice(0, 5).map(q => q.id))}>Chọn 5 câu đầu trang</button><button className="secondary" disabled={busy || !selected.length} onClick={() => setSelected([])}>Bỏ chọn</button></div><fieldset disabled={busy || loading}><legend>Câu hỏi tự luyện</legend>{bank.items.map(q => <label className="source-choice question-choice" key={q.id}><input type="checkbox" checked={selected.includes(q.id)} disabled={selected.length >= 20 && !selected.includes(q.id)} onChange={() => toggle(q.id)}/><span><span>{q.title}</span><small className="muted" style={{display:"block"}}>{q.origin === "kg_template" ? "Từ mối liên hệ · bản nháp chưa được chuyên gia duyệt" : "Câu hỏi lượng giá từ sách"}</small></span></label>)}</fieldset>
        <div className="actions">{questionPage > 0 && <button className="secondary" disabled={busy} onClick={() => {setQuestionPage(p => p - 1); setLoading(true);}}>Câu trước</button>}{(questionPage + 1) * 50 < bank.total && <button className="secondary" disabled={busy} onClick={() => {setQuestionPage(p => p + 1); setLoading(true);}}>Câu tiếp</button>}</div><button disabled={busy || loading || !selected.length} onClick={create}>{busy ? "Đang tạo…" : `Bắt đầu bài ${selected.length} câu`}</button></>}
    </section>}
    {session && <section className="card wide"><h2>Bài tự luyện · {session.questions.length} câu</h2><p className="muted">Tạo lúc {date(session.created_at)} · {session.status === "submitted" ? "Đã hoàn tất · chưa chấm điểm" : "Đang làm"}</p>
      {session.questions.map((q, i) => <section className="reader-section" key={q.id}><h3>Câu {i + 1}</h3><p>{q.title}</p><p className="muted">{q.origin === "kg_template" ? "Câu tự ôn từ mối liên hệ · chưa được chuyên gia duyệt" : "Câu hỏi lượng giá từ sách"}</p><label htmlFor={`study-answer-${i}`}>Câu trả lời {i + 1}</label><textarea id={`study-answer-${i}`} maxLength={16000} value={answers[q.id] ?? ""} disabled={busy || session.status === "submitted"} onChange={e => {setAnswers(a => ({...a, [q.id]: e.target.value})); setMessage("");}}/><details><summary>Nguồn câu hỏi</summary><Citations items={q.sources}/></details>{session.status === "submitted" && q.study_basis && <details><summary>Nội dung nguồn để tự đối chiếu — không phải đáp án chấm điểm</summary>{q.study_basis.map((b,j) => <div key={j}>{b.text && <p className="prose">{b.text}</p>}{b.relation_type && <p>Mối liên hệ: {relations[b.relation_type] ?? "liên quan đến"}{b.condition ? ` · Điều kiện: ${b.condition}` : ""}</p>}<Citations items={b.sources}/></div>)}<p className="muted">Đây là bản nguồn được lưu lúc tạo bài; chưa xác nhận tính đầy đủ hoặc chuyên gia duyệt.</p></details>}</section>)}
      {session.status === "draft" && <div className="actions"><button onClick={() => save(false)} disabled={busy || !dirty}>Lưu nháp</button><button className="secondary" onClick={() => save(true)} disabled={busy}>Hoàn tất bài</button>{dirty && <span role="status" className="muted">Câu trả lời chưa lưu</span>}</div>}
      <p><Link href="/progress">Xem các bài đã lưu</Link> · <Link href="/exams">Tạo bài mới</Link></p>
    </section>}
    {message && <p role="status" className="notice">{message}</p>}
  </main>;
}
export default function ExamsPage() {return <Suspense fallback={<main className="container">Đang mở bài tự luyện…</main>}><Exams/></Suspense>;}
