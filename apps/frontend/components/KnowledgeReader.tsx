"use client";

import Link from "next/link";
import {FormEvent, useEffect, useState} from "react";
import {apiRequest, errorMessage} from "@/lib/api";
import {Citation, KnowledgeNode, Reading, Review, User, date, nodeHref, pdfHref, relations, reviewLabels, types} from "@/lib/knowledge";

export function Citations({items}: {items: Citation[]}) {
  return <div className="citations">{items.map((c, i) => <details key={`${c.source_id}-${i}`}>
    <summary>{c.title} · trang PDF {c.pdf_pages.join(", ") || "chưa ghi"}</summary>
    {c.printed_pages.length > 0 && <p>Trang in: {c.printed_pages.join(", ")}</p>}
    <p>{c.pdf_pages.map(p => <Link className="source-page" key={p} href={pdfHref(c.source_id, p)}>Mở trang {p}</Link>)}</p>
    {c.excerpt && <blockquote className="prose">{c.excerpt}</blockquote>}
  </details>)}</div>;
}

export function KnowledgeReader({id, user}: {id: string; user: User}) {
  const [node, setNode] = useState<KnowledgeNode | null>(null);
  const [record, setRecord] = useState<Reading | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewStatus, setReviewStatus] = useState("needs_review");
  useEffect(() => {
    let active = true;
    const encoded = encodeURIComponent(id);
    void Promise.all([apiRequest<KnowledgeNode>(`/knowledge/node?id=${encoded}`), apiRequest<Reading>(`/study/record?node_id=${encoded}`), apiRequest<Review[]>(`/study/reviews?node_id=${encoded}`)])
      .then(([n, r, history]) => {if (active) {setNode(n); setRecord(r); setReviews(history);}})
      .catch(e => {if (active) setError(errorMessage(e));});
    return () => {active = false;};
  }, [id]);
  useEffect(() => {
    if (!dirty) return;
    const unload = (e: BeforeUnloadEvent) => {e.preventDefault();};
    const navigate = (e: MouseEvent) => {
      const link = (e.target as HTMLElement).closest("a");
      if (link && !link.hasAttribute("download") && link.target !== "_blank" && !window.confirm("Ghi chú chưa lưu. Bạn muốn rời trang?")) {e.preventDefault(); e.stopPropagation();}
    };
    window.addEventListener("beforeunload", unload); document.addEventListener("click", navigate, true);
    return () => {window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true);};
  }, [dirty]);
  function change(values: Partial<Reading>) {if (record) {setRecord({...record, ...values}); setDirty(true); setMessage("");}}
  async function save(e: FormEvent) {
    e.preventDefault(); if (!record) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await apiRequest<Reading>("/study/record", {method: "PUT", body: JSON.stringify({node_id: id, version: record.version, read_state: record.read_state, bookmarked: record.bookmarked, note: record.note})});
      setRecord(saved); setDirty(false); setMessage("Đã lưu vào tài khoản của bạn.");
    } catch (e) {setError(errorMessage(e));} finally {setBusy(false);}
  }
  async function review(e: FormEvent) {
    e.preventDefault(); if (!node) return;
    setBusy(true); setError("");
    try {
      await apiRequest("/study/reviews", {method: "POST", body: JSON.stringify({node_id: id, revision: node.revision, status: reviewStatus, note: reviewNote})});
      setReviews(await apiRequest<Review[]>(`/study/reviews?node_id=${encodeURIComponent(id)}`)); setReviewNote(""); setMessage("Đã ghi nhận kết quả đối chiếu nguồn.");
    } catch (e) {setError(errorMessage(e));} finally {setBusy(false);}
  }
  if (!node || !record) return <section className="card wide" aria-live="polite">{error ? <p className="error" role="alert">{error}</p> : <p>Đang mở nội dung…</p>}</section>;
  return <article className="reader card wide">
    <h2>{node.title}</h2><span className="badge">{types[node.type] ?? "Nội dung học tập"}</span>
    {!node.curricular && <p><Link className="source-page" href={`/exams?node=${encodeURIComponent(node.id)}`}>Tự luyện từ nội dung này</Link></p>}
    <p className="notice">{node.curricular ? "Thông tin chương trình từ nguồn HMU công khai; cần cô giáo xác nhận phiên bản áp dụng và nội dung từng môn." : "Bản nháp đã đối chiếu nguồn, chưa được chuyên gia y khoa phê duyệt. Hãy kiểm tra trích dẫn khi học."}</p>
    {reviews[0] && <p className="badge">{reviewLabels[reviews[0].status]}{!reviews[0].current && " · thuộc phiên bản cũ"}</p>}
    {node.metadata.text && node.metadata.text !== node.title && <p className="prose">{String(node.metadata.text)}</p>}
    {node.metadata.description && <p className="prose">{String(node.metadata.description)}</p>}
    {node.metadata.url && <p><a href={String(node.metadata.url)} target="_blank" rel="noopener noreferrer">Mở tài liệu HMU công khai ↗</a></p>}
    {node.metadata.hmu_course_url && <p><a href={String(node.metadata.hmu_course_url)} target="_blank" rel="noopener noreferrer">Mở học phần trên HMU LMS ↗</a><br/><small className="muted">Nội dung bài học yêu cầu tài khoản do trường cấp.</small></p>}
    {node.content.map((block, i) => <section key={i} className="content-block"><p className="prose">{block.text}</p><Citations items={block.sources}/></section>)}
    {node.type === "SampleQuestion" && <p className="muted">Câu hỏi chép từ sách. Hệ thống chưa có đáp án đã được duyệt và chưa chấm điểm câu này.</p>}
    {node.sources.length > 0 && <details><summary>Tất cả trích dẫn ({node.sources.length})</summary><Citations items={node.sources}/></details>}
    {node.evidence.length > 0 && <details><summary>Bằng chứng nguồn HMU</summary>{node.evidence.map((e, i) => <section key={i}>{e.quote && <blockquote className="prose">{e.quote}</blockquote>}{e.url && <a href={e.url} target="_blank" rel="noopener noreferrer">Xem nguồn HMU</a>}</section>)}</details>}
    <section className="reader-section"><h3>Nội dung liên quan ({node.relation_count})</h3>
      {node.relations.length ? <ul className="clean-list">{node.relations.map((r, i) => <li key={i}><span className="muted">{r.outgoing ? "→" : "←"} {relations[r.type] ?? "liên quan đến"}: </span><Link href={nodeHref(r.target.id)}>{r.target.title}</Link>{r.condition && <p className="muted">Điều kiện: {r.condition}</p>}</li>)}</ul> : <p className="muted">Chưa có quan hệ trong dữ liệu hiện tại.</p>}
      {node.relation_count > node.relations.length && <p className="muted">Đang hiển thị {node.relations.length} quan hệ đầu tiên.</p>}
    </section>
    <section className="reader-section"><h3>Không gian học cá nhân</h3>
      {record.version > 0 && record.revision !== node.revision && <p className="notice">Nội dung đã thay đổi từ lần bạn lưu gần nhất. Ghi chú được giữ lại để bạn đối chiếu.</p>}
      <form onSubmit={save}><label>Tiến độ đọc<select value={record.read_state} onChange={e => change({read_state: e.target.value as Reading["read_state"]})}><option value="unread">Chưa đọc</option><option value="reading">Đang đọc</option><option value="read">Đã đọc</option></select></label>
        <label className="source-choice"><input type="checkbox" checked={record.bookmarked} onChange={e => change({bookmarked: e.target.checked})}/>Lưu dấu trang</label>
        <label>Ghi chú riêng của bạn<textarea maxLength={4000} value={record.note} onChange={e => change({note: e.target.value})}/></label>
        <div className="actions"><button disabled={busy || !dirty}>Lưu ghi chú và tiến độ</button>{dirty && <span className="muted" role="status">Có thay đổi chưa lưu</span>}</div>
      </form><p className="muted">“Đã đọc” do bạn tự đánh dấu, chưa phản ánh mức độ nắm vững kiến thức.</p>
    </section>
    <details className="reader-section"><summary>Lịch sử đối chiếu nguồn ({reviews.length})</summary>
      <p className="muted">Đây là ghi nhận đối chiếu tài liệu, chưa phải phê duyệt chuyên môn.</p>
      {reviews.map(r => <div key={r.id} className="content-block"><strong>{reviewLabels[r.status]}</strong> · {r.reviewer} · {date(r.created_at)}{!r.current && <span> · phiên bản cũ</span>}<p className="prose">{r.note}</p></div>)}
      {user.role === "ADMIN" && <form onSubmit={review}><label>Kết quả đối chiếu<select value={reviewStatus} onChange={e => setReviewStatus(e.target.value)}>{Object.entries(reviewLabels).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label><label>Nhận xét đối chiếu<textarea value={reviewNote} onChange={e => setReviewNote(e.target.value)} maxLength={4000} required/></label><button disabled={busy || !reviewNote.trim()}>Ghi kết quả đối chiếu</button></form>}
    </details>
    {error && <p className="error" role="alert">{error}</p>}{message && <p className="notice" role="status">{message}</p>}
  </article>;
}
