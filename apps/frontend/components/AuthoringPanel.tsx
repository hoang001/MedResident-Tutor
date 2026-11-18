"use client";
import {useEffect,useRef,useState} from "react";
import {ApiError,apiRequest,errorMessage} from "@/lib/api";
export type AuthoringEvidence={source_unit_id:string;source_id:string;title:string;content:string;page_start:number;page_end:number};
export type AuthoringBundle={bundle_token:string;evidence:AuthoringEvidence[];provenance:{source_unit_id:string;book_title?:string;book_year?:number}[];trace:{fallback_reason?:string};status:string};
type Criterion={description:string;max_score:number;source_unit_ids:string[]};
type Proposal={reference_answer:string;criteria:Criterion[];insufficient_basis:string[];proposal_token:string};
export function AuthoringPanel({question,maxScore,course,topic,hasDraft,onBusy,onApply}:{question:string;maxScore:number;course:string;topic:string;hasDraft:boolean;onBusy:(busy:boolean)=>void;onApply:(proposal:Proposal,bundle:AuthoringBundle)=>void}) {
 const [available,setAvailable]=useState(false),[checking,setChecking]=useState(true);
 const [step,setStep]=useState<"idle"|"retrieving"|"generating">("idle"),[error,setError]=useState("");
 const [bundle,setBundle]=useState<AuthoringBundle|null>(null),[basis,setBasis]=useState(""),[insufficient,setInsufficient]=useState<string[]>([]);
 const running=useRef(false),scope={question,topic,course,max_score:maxScore,source_ids:[]};
 const current=JSON.stringify(scope),latest=useRef(current);
 useEffect(()=>{latest.current=current;},[current]);
 useEffect(()=>{let alive=true;void apiRequest<{proposal_available:boolean}>("/admin/authoring/config").then(config=>{if(alive)setAvailable(config.proposal_available);}).catch(e=>{if(alive)setError(errorMessage(e));}).finally(()=>{if(alive)setChecking(false);});return()=>{alive=false;};},[]);
 async function suggest(){
  if(running.current)return;
  if(hasDraft&&!window.confirm("Đề xuất mới sẽ thay phần đáp án và tiêu chí đang soạn. Tiếp tục?"))return;
  running.current=true;onBusy(true);setError("");setInsufficient([]);setStep("retrieving");
  try {
   const sources=await apiRequest<AuthoringBundle>("/admin/authoring/retrieve",{method:"POST",body:JSON.stringify(scope)},{timeoutMs:120000});
   if(latest.current!==current)throw new ApiError("Câu hỏi đã đổi. Hãy tạo lại đề xuất cho nội dung mới.");
   setBundle(sources);setBasis(current);
   if(!sources.evidence.length){setError("Chưa tìm thấy nguồn đủ phù hợp. Hãy làm rõ câu hỏi hoặc chọn nguồn thủ công.");return;}
   setStep("generating");
   const proposal=await apiRequest<Proposal>("/admin/authoring/propose",{method:"POST",body:JSON.stringify({scope,bundle_token:sources.bundle_token,selected_ids:sources.evidence.map(e=>e.source_unit_id)})},{timeoutMs:900000});
   if(latest.current!==current)throw new ApiError("Câu hỏi đã đổi. Đề xuất cũ chưa được áp dụng.");
   setInsufficient(proposal.insufficient_basis);onApply(proposal,sources);
  } catch(e){setError(e instanceof ApiError&&["AUTHORING_OUTPUT_INVALID","MODEL_INFERENCE_FAILED"].includes(e.code)?"AI chưa tạo được đề xuất hợp lệ. Nội dung đang soạn được giữ nguyên; hãy kiểm tra câu hỏi và nguồn trước khi thử lại.":errorMessage(e));} finally {running.current=false;setStep("idle");onBusy(false);}
 }
 return <section className="assisted-authoring" aria-label="AI hỗ trợ biên soạn" aria-busy={step!=="idle"}><h3>Đề xuất đáp án từ tài liệu</h3><p>Nhập câu hỏi, hệ thống sẽ tìm nguồn trong KG và sách, rồi đề xuất đáp án cùng tiêu chí. Bạn chỉnh sửa và duyệt trước khi lưu.</p><button type="button" disabled={checking||!available||step!=="idle"||!question.trim()||!Number.isFinite(maxScore)||maxScore<=0} onClick={()=>void suggest()}>{step==="retrieving"?"Đang tìm nguồn…":step==="generating"?"Đang soạn đáp án…":"Tìm nguồn và đề xuất đáp án"}</button>{step!=="idle"&&<p role="status">{step==="retrieving"?"Đang đối chiếu câu hỏi với tài liệu liên quan.":"AI đang biên soạn từ các đoạn nguồn vừa tìm. Bản đề xuất chưa được lưu."}</p>}{!checking&&!available&&<p className="notice">Dịch vụ đề xuất chưa được bật. Bạn vẫn có thể soạn thủ công ở các ô bên dưới.</p>}{error&&<p className="error" role="alert">{error}</p>}{!!insufficient.length&&<div className="notice" role="status"><strong>Cần bổ sung căn cứ</strong><ul>{insufficient.map((item,i)=><li key={i}>{item}</li>)}</ul></div>}{bundle&&<details className="authoring-evidence"><summary>Xem {bundle.evidence.length} đoạn nguồn đã tìm</summary>{basis!==current&&<p className="notice">Câu hỏi hoặc phạm vi đã đổi; cần tìm lại nguồn trước khi dùng đề xuất.</p>}{bundle.evidence.map(e=><section key={e.source_unit_id}><h4>{bundle.provenance.find(p=>p.source_unit_id===e.source_unit_id)?.book_title??e.title}</h4><p className="helper">PDF {e.page_start}–{e.page_end}</p><blockquote>{e.content}</blockquote></section>)}</details>}</section>;
}
