"use client";

import {PageHeading} from "@/components/ui";
import Link from "next/link";
import {useEffect, useState} from "react";
import {apiRequest, errorMessage} from "@/lib/api";
import {Reading, SessionBrief, Summary, date, nodeHref, useWorkspace} from "@/lib/knowledge";

export default function ProgressPage() {
  const {user, error: authError} = useWorkspace();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [records, setRecords] = useState<{total: number; items: Reading[]}>({total: 0, items: []});
  const [sessions, setSessions] = useState<{total: number; items: SessionBrief[]}>({total: 0, items: []});
  const [onlyBookmarks, setOnlyBookmarks] = useState(false);
  const [recordOffset, setRecordOffset] = useState(0);
  const [sessionOffset, setSessionOffset] = useState(0);
  const [error, setError] = useState("");
  const [loadedQuery, setLoadedQuery] = useState("");
  const queryKey = `${onlyBookmarks}:${recordOffset}:${sessionOffset}`;
  const loading = loadedQuery !== queryKey;
  useEffect(() => {
    if (!user) return; let active = true;
    void Promise.all([apiRequest<Summary>("/study/summary"), apiRequest<{total: number; items: Reading[]}>(`/study/records?bookmarked=${onlyBookmarks}&offset=${recordOffset}`), apiRequest<{total: number; items: SessionBrief[]}>(`/study/sessions?offset=${sessionOffset}`)]).then(([s, r, h]) => {if (active) {setSummary(s); setRecords(r); setSessions(h); setError(""); setLoadedQuery(queryKey);}}).catch(e => {if (active) setError(errorMessage(e));});
    return () => {active = false;};
  }, [user, onlyBookmarks, recordOffset, sessionOffset, queryKey]);
  return <main className="container library"><PageHeading title="Tiến độ học tập" description="Nội dung đã đọc, ghi chú, dấu trang và những bài tự ôn đã lưu." action={<Link className="button secondary" href="/history">Xem lịch sử bài tập</Link>}/>
    {(authError || error) && <p className="error" role="alert">{authError || error}</p>}
    <p className="notice">Tiến độ đọc và số lần tự luyện chưa phải điểm năng lực. Hệ thống chưa chấm bài tự luyện và không tính điểm giả lập AI vào kết quả này.</p>
    {summary && <div className="stats-grid">{[["Đang đọc", summary.reading], ["Đã đọc", summary.read], ["Dấu trang", summary.bookmarked], ["Bài đang làm", summary.drafts]].map(([label, n]) => <div className="stat" key={label}><strong>{n}</strong><span>{label}</span></div>)}</div>}
    {loading && !error && !authError && <p className="notice" role="status">Đang tải tiến độ và bài đã lưu…</p>}<section className="card wide" aria-busy={loading && !error}><h2>Ghi chú và dấu trang ({records.total})</h2><label className="source-choice"><input type="checkbox" checked={onlyBookmarks} onChange={e => {setOnlyBookmarks(e.target.checked); setRecordOffset(0);}}/>Chỉ xem dấu trang</label>
      {!loading && !error && !records.total && <p className="muted">Chưa có mục nào phù hợp. Bạn có thể lưu nội dung từ <Link href="/knowledge">thư viện</Link>.</p>}
      <ul className="clean-list">{records.items.map(r => <li key={r.node_id}><h3><Link href={nodeHref(r.node_id)}>{r.title}</Link></h3><p className="muted">{r.read_state === "read" ? "Đã đọc" : r.read_state === "reading" ? "Đang đọc" : "Chưa đọc"}{r.bookmarked && " · Dấu trang"} · {date(r.updated_at)}</p>{r.note && <p className="prose">{r.note}</p>}</li>)}</ul>
      <div className="actions">{recordOffset > 0 && <button className="secondary" onClick={() => setRecordOffset(Math.max(0, recordOffset - 30))}>Ghi chú trước</button>}{recordOffset + 30 < records.total && <button className="secondary" onClick={() => setRecordOffset(recordOffset + 30)}>Ghi chú tiếp</button>}</div>
    </section>
    <section className="card wide"><h2>Bài tự luyện ({sessions.total})</h2><p><Link href="/exams">Tạo bài tự luyện mới →</Link></p>
      {!loading && !error && !sessions.total && <p className="muted">Chưa có bài tự luyện.</p>}
      <ul className="clean-list">{sessions.items.map(s => <li key={s.id}><Link href={`/exams?session=${s.id}`}>Bài {s.question_count} câu · {date(s.created_at)}</Link><p className="muted">{s.status === "draft" ? "Đang làm" : "Đã hoàn tất · chưa chấm điểm"} · Đã trả lời {s.answered_count}/{s.question_count} câu</p></li>)}</ul>
      <div className="actions">{sessionOffset > 0 && <button className="secondary" onClick={() => setSessionOffset(Math.max(0, sessionOffset - 20))}>Bài trước</button>}{sessionOffset + 20 < sessions.total && <button className="secondary" onClick={() => setSessionOffset(sessionOffset + 20)}>Bài tiếp</button>}</div>
    </section>
  </main>;
}
