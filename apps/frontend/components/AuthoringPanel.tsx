"use client";
import {useState,useRef,useEffect} from "react";
import {ApiError, apiRequest, errorMessage} from "@/lib/api";

type Evidence = {source_unit_id:string;source_id:string;title:string;content:string;page_start:number;page_end:number;retrieval_id?:string};
type Source = {source_unit_id:string;source_id:string;title:string;content:string;source_title:string;pdf_page_start:number;pdf_page_end:number;printed_page_start:null;printed_page_end:null;review:{status:string};metadata_errors:string[]};
type Criterion = {description:string;max_score:number;source_unit_ids:string[]};
type Bundle = {bundle_token:string;evidence:Evidence[];provenance:{source_unit_id:string;book_year?:number;book_title?:string}[];trace:{fallback_reason?:string};status:string};
export function AuthoringPanel({question,maxScore,course,topic,onScope,onApply,onSources}:{question:string;maxScore:number;course:string;topic:string;onScope:(course:string,topic:string)=>void;onApply:(answer:string,criteria:Criterion[],token?:string)=>void;onSources:(sources:Source[])=>void}) {
  const [bundle,setBundle]=useState<Bundle|null>(null);
  const [selection,setSelection]=useState<string[]>([]);
  const [basis,setBasis]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [proposalAvailable,setProposalAvailable]=useState(false);
  useEffect(()=>{let active=true;void apiRequest<{proposal_available:boolean}>("/admin/authoring/config").then(c=>{if(active)setProposalAvailable(c.proposal_available);}).catch(()=>{if(active)setProposalAvailable(false);});return()=>{active=false;};},[]);
  const scope={question,topic,course,max_score:maxScore,source_ids:[]};
  const current=JSON.stringify(scope);
  const latest=useRef(current);
  useEffect(()=>{latest.current=current;},[current]);
  const stale=!!bundle && basis!==current;
  async function run(task:()=>Promise<void>) {if(busy)return;setBusy(true);setError("");setNotice("");try{await task();}catch(e){setError(e instanceof ApiError&&e.code==="AUTHORING_MODEL_OFF"?"Model soạn thảo đang tắt. Bạn vẫn có thể chọn nguồn, soạn thủ công và lưu nháp.":errorMessage(e));}finally{setBusy(false);}}
  function applyProposal(answer:string,criteria:Criterion[],token:string) {if(latest.current!==current){setError("Đề đã đổi trong khi chờ. Hãy tìm lại nguồn; đề xuất cũ chưa được áp dụng.");return;}onApply(answer,criteria,token);}
  async function materialize() {
    const rows=await apiRequest<Evidence[]>("/admin/authoring/materialize",{method:"POST",body:JSON.stringify({bundle_token:bundle!.bundle_token,selected_ids:selection})});
    onSources(rows.map(e=>({source_unit_id:e.source_unit_id,source_id:e.source_id,title:e.title,content:e.content,source_title:e.source_id,pdf_page_start:e.page_start,pdf_page_end:e.page_end,printed_page_start:null,printed_page_end:null,review:{status:"unverified"},metadata_errors:[]})));
    return rows;
  }
  return <fieldset className="authoring-tools" disabled={busy}><legend>Tìm nguồn và hỗ trợ biên soạn</legend>
    {!proposalAvailable&&<p className="notice">Đề xuất tự động chưa được bật. Bạn vẫn có thể chọn đoạn nguồn, nhập đáp án và tiêu chí rồi lưu nháp thủ công.</p>}
    <label htmlFor="author-course">Học phần (nhãn tổ chức)</label><input id="author-course" value={course} maxLength={255} onChange={e=>onScope(e.target.value,topic)}/>
    <label htmlFor="author-topic">Chủ đề cần tìm</label><input id="author-topic" value={topic} maxLength={255} onChange={e=>onScope(course,e.target.value)}/>
    <p>Học phần chưa có đề cương được xác nhận nên không dùng để giới hạn tài liệu. Có thể lưu nháp và soạn thủ công khi model chưa bật.</p>
    <button type="button" disabled={!question.trim()||busy} onClick={()=>void run(async()=>{const result=await apiRequest<Bundle>("/admin/authoring/retrieve",{method:"POST",body:JSON.stringify(scope)},{timeoutMs:120000});setBundle(result);setBasis(current);setSelection(result.evidence.map(e=>e.source_unit_id));})}>{busy?"Đang xử lý…":"Tìm tài liệu liên quan"}</button>
    {stale&&<p role="status">Đề hoặc phạm vi đã đổi. Hãy tìm lại nguồn trước khi dùng đề xuất.</p>}
    {bundle&&<><p>{bundle.evidence.length?"Các đoạn gợi ý cần admin kiểm tra, chưa được xác minh chuyên môn.":"Chưa tìm thấy căn cứ. Có thể tìm lại bằng chủ đề cụ thể hơn hoặc soạn thủ công."}</p>
      {bundle.trace.fallback_reason&&<p>KG chưa hỗ trợ đầy đủ; lý do truy xuất: {bundle.trace.fallback_reason}</p>}
      {bundle.evidence.map(e=><div key={e.source_unit_id}><label className="source-choice"><input type="checkbox" checked={selection.includes(e.source_unit_id)} onChange={event=>setSelection(event.target.checked?[...selection,e.source_unit_id]:selection.filter(x=>x!==e.source_unit_id))}/>{e.title} · {bundle.provenance.find(p=>p.source_unit_id===e.source_unit_id)?.book_title??e.source_id} · {bundle.provenance.find(p=>p.source_unit_id===e.source_unit_id)?.book_year??"chưa rõ năm"} · PDF {e.page_start}–{e.page_end}</label><details><summary>Đọc toàn bộ đoạn nguồn</summary><blockquote>{e.content}</blockquote></details></div>)}
      <div className="actions"><button type="button" disabled={stale||!selection.length||busy} onClick={()=>void run(async()=>{await materialize();setNotice("Đã thêm các đoạn nguồn vào danh sách evidence bên dưới. Chọn nguồn cho từng tiêu chí khi soạn thủ công.");})}>Dùng nguồn để soạn thủ công</button>
      <button type="button" disabled={!proposalAvailable||stale||!selection.length||busy} onClick={()=>void run(async()=>{const proposal=await apiRequest<{reference_answer:string;criteria:Criterion[];insufficient_basis:string[];proposal_token:string}>("/admin/authoring/propose",{method:"POST",body:JSON.stringify({scope,bundle_token:bundle.bundle_token,selected_ids:selection})},{timeoutMs:900000});const rows=await materialize();applyProposal(proposal.reference_answer,proposal.criteria.map(c=>({...c,source_unit_ids:c.source_unit_ids.map(id=>rows.find(r=>r.retrieval_id===id)!.source_unit_id)})),proposal.proposal_token);setNotice("Đã áp dụng bản nháp để sửa. Chưa phát hành. Phần thiếu căn cứ: "+(proposal.insufficient_basis.join("; ")||"model không báo; admin vẫn cần kiểm tra"));})}>Đề xuất đáp án và tiêu chí</button></div></>}
    {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  </fieldset>;
}
