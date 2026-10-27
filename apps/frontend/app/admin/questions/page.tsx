"use client";
import {FormEvent, useEffect, useState} from "react";
import {AdminOnly} from "@/components/AdminOnly";
import {ApiError, apiRequest, errorMessage} from "@/lib/api";
type Source = {source_unit_id: string; title: string; content: string; source_id: string; source_title: string; pdf_page_start: number; pdf_page_end: number; printed_page_start: number | null; printed_page_end: number | null; review: {status: string}; metadata_errors: string[]};
type Criterion = {criterion_id?: string; description: string; max_score: number; source_unit_ids: string[]; evidence?: Source[]};
type Edit = {question_id?: string; version?: number; content: string; rubric_name: string; max_score: number; is_available?: boolean; criteria: Criterion[]};
type Summary = {question_id: string; content: string; is_available: boolean; version: number};
const signature = (q: Edit) => JSON.stringify({content:q.content,rubric_name:q.rubric_name,max_score:q.max_score,criteria:q.criteria.map(c => ({criterion_id:c.criterion_id,description:c.description,max_score:c.max_score,source_unit_ids:c.source_unit_ids}))});
const blank = (): Edit => ({content: "", rubric_name: "Rubric tự luận ngắn", max_score: 1, criteria: [{description: "", max_score: 1, source_unit_ids: []}]});
function QuestionBank() {
  const [savedState, setSavedState] = useState<string | null>(null);
  const [items, setItems] = useState<Summary[]>([]);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Edit>(blank);
  const [knownSources, setKnownSources] = useState<Record<string,Source>>({});
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceSearch, setSourceSearch] = useState("");
  const [sourceOffset, setSourceOffset] = useState(0);
  const [preview, setPreview] = useState<Source | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const total = editing.criteria.reduce((sum,c) => sum+c.max_score, 0);
  async function load(q = search, start = offset) {setItems(await apiRequest<Summary[]>(`/admin/questions?q=${encodeURIComponent(q)}&limit=20&offset=${start}`));}
  async function loadSources(q = sourceSearch, start = sourceOffset) {
    const rows = await apiRequest<Source[]>(`/admin/source-units?q=${encodeURIComponent(q)}&limit=20&offset=${start}`);
    setSources(rows); setKnownSources(previous => ({...previous,...Object.fromEntries(rows.map(s => [s.source_unit_id,s]))}));
  }
  useEffect(() => {
    Promise.all([apiRequest<Summary[]>("/admin/questions?limit=20"), apiRequest<Source[]>("/admin/source-units?limit=20")]).then(([qs,ss]) => {setItems(qs); setSources(ss); setKnownSources(Object.fromEntries(ss.map(s => [s.source_unit_id,s])));}).catch(reason => setError(errorMessage(reason)));
  }, []);
  async function action(work: () => Promise<void>) {
    if (busy) return; setBusy(true); setError(""); setNotice(""); setFields({});
    try {await work();} catch(reason) {setError(errorMessage(reason)); setFields(reason instanceof ApiError ? reason.fields : {});} finally {setBusy(false);}
  }
  function change(index: number, patch: Partial<Criterion>) {setEditing({...editing, criteria: editing.criteria.map((c,i) => i===index ? {...c,...patch} : c)});}
  function open(id: string) {void action(async () => {const q = await apiRequest<Edit>(`/admin/questions/${encodeURIComponent(id)}`); setEditing(q); setSavedState(signature(q)); setPreview(null);});}
  function save(event: FormEvent) {
    event.preventDefault();
    if (!editing.content.trim() || !editing.rubric_name.trim()) {setError("Cần nhập nội dung câu hỏi và tên rubric."); return;}
    const missing = editing.criteria.map((c,i) => c.description.trim() ? null : i+1).filter(x => x!==null);
    if (missing.length) {setError(`Tiêu chí ${missing.join(", ")} chưa có mô tả.`); return;}
    if (!Number.isFinite(total) || !Number.isFinite(editing.max_score) || Math.abs(total-editing.max_score)>1e-9 || editing.criteria.some(c => !Number.isFinite(c.max_score) || c.max_score<=0)) {setError("Điểm phải hữu hạn, lớn hơn 0; tổng điểm tiêu chí phải bằng điểm tối đa rubric."); return;}
    if (editing.criteria.some(c => c.source_unit_ids.length===0)) {setError("Mỗi tiêu chí cần ít nhất một evidence."); return;}
    void action(async () => {
      const body = {version: editing.version, content: editing.content, rubric_name: editing.rubric_name, max_score: editing.max_score, criteria: editing.criteria.map(c => ({criterion_id: c.criterion_id, description: c.description, max_score: c.max_score, source_unit_ids: c.source_unit_ids}))};
      const result = await apiRequest<Edit>(editing.question_id ? `/admin/questions/${editing.question_id}` : "/admin/questions", {method: editing.question_id ? "PUT" : "POST", body: JSON.stringify(body)});
      setEditing(result); setSavedState(signature(result)); setNotice("Đã lưu câu hỏi và rubric. Trạng thái khả dụng được quản lý riêng."); await load();
    });
  }
  async function availability() {
    if (!editing.question_id) return;
    await action(async () => {setEditing(await apiRequest<Edit>(`/admin/questions/${editing.question_id}/availability`, {method: "PATCH", body: JSON.stringify({version: editing.version, is_available: !editing.is_available})})); setNotice(editing.is_available ? "Đã ngừng sử dụng cho lượt làm mới; lịch sử được giữ nguyên." : "Đã đưa câu hỏi đã lưu vào sử dụng. Đây không phải chuyên gia duyệt."); await load();});
  }
  return <main className="container"><h1>Ngân hàng câu hỏi</h1><p className="notice">Khả dụng trong ứng dụng và chuyên gia duyệt là hai trạng thái riêng. Nội dung tạo/sửa tại đây: chuyên gia duyệt chưa xác minh. Topic có thể để trống.</p>
    <section className="card"><h2>Danh sách câu hỏi</h2><form onSubmit={e => {e.preventDefault(); setOffset(0); void action(() => load(search,0));}}><label htmlFor="bank-search">Tìm câu hỏi</label><input id="bank-search" value={search} onChange={e => setSearch(e.target.value)}/><button disabled={busy}>Tìm câu hỏi</button></form>
      <ul>{items.map(q => <li key={q.question_id}><button className="secondary" disabled={busy} onClick={() => open(q.question_id)}>{q.content} — {q.is_available ? "Đang sử dụng" : "Chưa sử dụng"}</button></li>)}</ul>
      <div className="actions"><button disabled={busy || offset===0} onClick={() => {const n=Math.max(0,offset-20); setOffset(n); void action(() => load(search,n));}}>Trang trước</button><button disabled={busy || items.length<20} onClick={() => {const n=offset+20; setOffset(n); void action(() => load(search,n));}}>Trang tiếp</button><button disabled={busy} onClick={() => {setEditing(blank()); setError(""); setNotice("");}}>Tạo câu hỏi mới</button></div>
    </section>
    <section className="card"><h2>{editing.question_id ? "Sửa câu hỏi" : "Tạo câu hỏi tự luận ngắn"}</h2><p>Trạng thái: {editing.is_available ? "Đang sử dụng" : "Chưa sử dụng"}. Chuyên gia duyệt: chưa xác minh.</p>
      {editing.question_id && <details><summary>Định danh ổn định</summary><p>{editing.question_id} · phiên bản {editing.version}</p>{editing.criteria.map(c => <p key={c.criterion_id}>{c.criterion_id}</p>)}</details>}
      <form onSubmit={save} noValidate><label htmlFor="bank-content">Nội dung câu hỏi</label><textarea id="bank-content" maxLength={4000} value={editing.content} onChange={e => setEditing({...editing,content:e.target.value})}/><span className="error">{fields.content}</span>
        <label htmlFor="bank-rubric">Tên rubric</label><input id="bank-rubric" maxLength={255} value={editing.rubric_name} onChange={e => setEditing({...editing,rubric_name:e.target.value})}/>
        <label htmlFor="bank-max">Điểm tối đa rubric</label><input id="bank-max" type="number" min="0.01" step="any" value={Number.isFinite(editing.max_score) ? editing.max_score : ""} onChange={e => setEditing({...editing,max_score:e.target.valueAsNumber})}/>
        <p data-testid="criterion-total">Tổng điểm tiêu chí: {Number.isFinite(total) ? total : "không hợp lệ"}</p>
        {editing.criteria.map((c,i) => {
          const options = [...new Map([...sources,...Object.values(knownSources).filter(s => c.source_unit_ids.includes(s.source_unit_id)),...(c.evidence??[])].map(s => [s.source_unit_id,s])).values()];
          return <fieldset key={c.criterion_id??`new-${i}`} data-testid="criterion-editor"><legend>Tiêu chí {i+1}</legend>
            <label htmlFor={`description-${i}`}>Mô tả tiêu chí {i+1}</label><textarea id={`description-${i}`} maxLength={4000} value={c.description} onChange={e => change(i,{description:e.target.value})}/>
            <label htmlFor={`score-${i}`}>Điểm tiêu chí {i+1}</label><input id={`score-${i}`} type="number" min="0.01" step="any" value={Number.isFinite(c.max_score) ? c.max_score : ""} onChange={e => change(i,{max_score:e.target.valueAsNumber})}/>
            <p>Evidence đã chọn: {c.source_unit_ids.length}</p>
            {options.map(s => <div className="notice" key={s.source_unit_id}><label className="source-choice"><input type="checkbox" checked={c.source_unit_ids.includes(s.source_unit_id)} disabled={s.metadata_errors.length>0 && !c.source_unit_ids.includes(s.source_unit_id)} onChange={e => change(i,{source_unit_ids:e.target.checked ? [...c.source_unit_ids,s.source_unit_id] : c.source_unit_ids.filter(id => id!==s.source_unit_id)})}/>{s.title}</label><p>{s.content}</p><p>{s.source_title} · PDF {s.pdf_page_start}–{s.pdf_page_end} · trang in {s.printed_page_start??"chưa xác minh"} · Review: {s.review.status}</p>{s.metadata_errors.map(x => <p className="error" key={x}>{x}</p>)}<button type="button" className="secondary" onClick={() => void action(async () => setPreview(await apiRequest<Source>(`/admin/source-units/${s.source_unit_id}`)))}>Xem evidence</button></div>)}
            <button type="button" className="secondary" disabled={editing.criteria.length<=1} onClick={() => setEditing({...editing,criteria:editing.criteria.filter((_,n) => n!==i)})}>Xóa tiêu chí {i+1}</button>
          </fieldset>;
        })}
        <button type="button" disabled={editing.criteria.length>=100} onClick={() => setEditing({...editing,criteria:[...editing.criteria,{description:"",max_score:1,source_unit_ids:[]}]})}>Thêm tiêu chí</button>
        <button disabled={busy}>Lưu câu hỏi và rubric</button>
      </form>
      {editing.question_id && <button className="secondary" disabled={busy || signature(editing)!==savedState} onClick={() => void availability()}>{editing.is_available ? "Ngừng sử dụng" : "Đưa vào sử dụng"}</button>}
      {editing.question_id && signature(editing)!==savedState && <p className="muted">Lưu thay đổi trước khi đổi trạng thái khả dụng.</p>}
    </section>
    <section className="card"><h2>Tìm evidence hiện có</h2><form onSubmit={e => {e.preventDefault(); setSourceOffset(0); void action(() => loadSources(sourceSearch,0));}}><label htmlFor="bank-source-search">Tìm SourceUnit</label><input id="bank-source-search" value={sourceSearch} onChange={e => setSourceSearch(e.target.value)}/><button disabled={busy}>Tìm evidence</button></form><p>Chỉ xem/chọn evidence, không sửa nội dung nguồn.</p><div className="actions"><button disabled={busy || sourceOffset===0} onClick={() => {const n=Math.max(0,sourceOffset-20); setSourceOffset(n); void action(() => loadSources(sourceSearch,n));}}>Evidence trước</button><button disabled={busy || sources.length<20} onClick={() => {const n=sourceOffset+20;setSourceOffset(n);void action(() => loadSources(sourceSearch,n));}}>Evidence tiếp</button></div>
      {preview && <aside><h3>{preview.title}</h3><p>{preview.source_title} · PDF {preview.pdf_page_start}–{preview.pdf_page_end} · trang in {preview.printed_page_start??"chưa xác minh"} · review {preview.review.status}</p><blockquote>{preview.content}</blockquote></aside>}
    </section>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
  </main>;
}
export default function QuestionsPage() {return <AdminOnly><QuestionBank/></AdminOnly>;}
