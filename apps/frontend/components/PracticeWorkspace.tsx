"use client";
import Link from "next/link";
import {FormEvent,useEffect,useRef,useState} from "react";
import {ApiError,apiRequest,errorMessage} from "@/lib/api";
import {PendingSubmission,Submission,prepareSubmission,readPractice,rememberAttempt,writePractice} from "@/lib/practice-storage";
import {Attempt,Question} from "@/lib/practice-types";
import {questionName} from "@/lib/practice-display";
import {PracticeImages} from "@/components/PracticeImages";
import {StructuredAnswers} from "@/components/StructuredAnswers";
import {PracticeResult} from "@/components/PracticeResult";
import {Alert,Badge,Loading,PageHeading} from "@/components/ui";
import {Icon} from "@/components/Icon";

export function PracticeWorkspace({userId,questionId,attemptId}:{userId:string;questionId?:string;attemptId?:string}) {
  const [selected,setSelected]=useState<Question|null>(null);const [answer,setAnswer]=useState("");
  const [structuredAnswers,setStructuredAnswers]=useState<Record<string,string|null>>({});
  const [result,setResult]=useState<Attempt|null>(null);const [pending,setPending]=useState<PendingSubmission>();
  const [busy,setBusy]=useState(false);const [ready,setReady]=useState(false);const [error,setError]=useState("");
  const [fields,setFields]=useState<Record<string,string>>({});const [mode,setMode]=useState<string|null>(null);
  const [timeout,setTimeoutMs]=useState<number>();const sending=useRef(false);
  useEffect(()=>{
    let active=true;
    async function initialize(){
      try{
        const cfg=await apiRequest<{execution_mode:string;request_timeout_ms?:number}>("/practice/config");
        if(!active)return;setMode(cfg.execution_mode);setTimeoutMs(cfg.request_timeout_ms&&Number.isFinite(cfg.request_timeout_ms)&&cfg.request_timeout_ms>0?cfg.request_timeout_ms:undefined);
        if(attemptId){const a=await apiRequest<Attempt>(`/practice/attempts/${encodeURIComponent(attemptId)}`);if(active)setResult(a);}
        else if(questionId){
          const q=await apiRequest<Question>(`/practice/questions/${encodeURIComponent(questionId)}`);if(!active)return;
          setSelected(q);const local=readPractice(userId);setPending(local.pending);
          if(local.draft?.question_id===questionId){setAnswer(local.draft.student_answer??"");setStructuredAnswers(local.draft.structured_answers??{});}
        }
      }catch(reason){if(active)setError(errorMessage(reason));}finally{if(active)setReady(true);}
    }
    void initialize();return()=>{active=false;};
  },[userId,questionId,attemptId]);
  useEffect(()=>{
    if(!result||!["pending","medical_running","teaching_running"].includes(result.status))return;
    let active=true;const timer=setInterval(()=>void apiRequest<Attempt>(`/practice/attempts/${result.id}`).then(a=>{if(active)setResult(a);}).catch(e=>{if(active)setError(errorMessage(e));}),1500);
    return()=>{active=false;clearInterval(timer);};
  },[result]);
  function draft(payload:Submission){
    setAnswer(payload.student_answer??"");setStructuredAnswers(payload.structured_answers??{});
    try{writePractice(userId,{...readPractice(userId),draft:payload});}catch(e){setError(errorMessage(e));}
  }
  async function send(payload:Submission){
    if(sending.current)return;sending.current=true;setBusy(true);setError("");setFields({});
    try{
      const submission=prepareSubmission(userId,payload);setPending(submission);
      const a=submission.attemptId?await apiRequest<Attempt>(`/practice/attempts/${submission.attemptId}`):await apiRequest<Attempt>("/practice/attempts",{method:"POST",headers:{"Idempotency-Key":submission.key},body:JSON.stringify(submission.payload)},{timeoutMs:timeout});
      rememberAttempt(userId,submission,a.id);setPending({...submission,attemptId:a.id});setResult(a);
      window.history.replaceState(null,"",`/learn?attempt=${a.id}`);
    }catch(e){setError(errorMessage(e));setFields(e instanceof ApiError?e.fields:{});}finally{sending.current=false;setBusy(false);}
  }
  function submit(e:FormEvent){e.preventDefault();if(!selected)return;void send(selected.structured_exercise?{question_id:selected.question_id,revision_id:selected.structured_exercise.revision_id,structured_answers:structuredAnswers}:{question_id:selected.question_id,student_answer:answer});}
  function newAttempt(){
    const id=selected?.question_id??result?.question_id;if(!id||busy)return;
    if(!result&&(answer.trim()||Object.values(structuredAnswers).some(Boolean))&&!window.confirm("Tạo lượt mới sẽ xóa nội dung đang nhập. Tiếp tục?"))return;
    try{writePractice(userId,{draft:{question_id:id,student_answer:""}});window.location.assign(`/learn?question=${encodeURIComponent(id)}`);}catch(e){setError(errorMessage(e));}
  }
  async function retry(){
    if(!result||sending.current)return;sending.current=true;setBusy(true);setError("");
    try{setResult(await apiRequest<Attempt>(`/practice/attempts/${result.id}/retry`,{method:"POST"},{timeoutMs:timeout}));}catch(e){setError(errorMessage(e));}finally{sending.current=false;setBusy(false);}
  }
  const structured=selected?.structured_exercise;
  return <main className="container library"><div className="exercise-header"><Link className="text-link" href="/learn">Về ngân hàng bài tập</Link><Link className="text-link" href="/history"><Icon name="history" size={18}/>Lịch sử & kết quả</Link></div>
    <PageHeading title={result?"Bài làm đã lưu":selected?questionName(selected):"Mở bài tập"} description={result?"Kết quả và tài liệu đối chiếu thuộc đúng lượt làm này.":selected?.topic??"Đọc kỹ đề và trả lời theo phạm vi tài liệu được nêu."}/>
    {!ready&&<Loading label="Đang mở bài tập…"/>}{error&&<Alert kind="error">{error} Nội dung đã nhập được giữ lại.</Alert>}
    {result?<><PracticeResult attempt={result} busy={busy} retry={retry}/><div className="actions"><button onClick={newAttempt} disabled={busy}>Tạo lượt mới</button><Link className="button secondary" href={`/history?attempt=${result.id}`}>Mở trong lịch sử</Link></div></>:selected&&<>
      {mode==="mock"&&!structured&&<Alert kind="warning" title="Đang dùng chế độ mô phỏng">Điểm và phản hồi là dữ liệu giả lập để thử luồng sử dụng, không đánh giá câu trả lời của bạn.</Alert>}
      {structured&&<p className="helper">Bài có lựa chọn được chấm theo đáp án biên soạn. Phần giải thích ngắn chưa tính điểm.</p>}
      {pending?.payload.question_id===selected.question_id&&<Alert>{pending.attemptId?<><p>Lượt nộp gần đây của bài này đã được lưu.</p><Link href={`/history?attempt=${pending.attemptId}`}>Xem kết quả đã lưu</Link>{" · "}<button className="text-button" onClick={newAttempt}>Tạo lượt mới</button></>:<>Có một lần nộp chưa nhận được kết quả. <button className="text-button" disabled={busy} onClick={()=>void send(pending.payload)}>Kiểm tra lại lần nộp</button></>}</Alert>}
      <div className="exercise-layout"><section className="exercise-prompt" aria-label="Đề bài"><div className="metadata-row"><Badge>{structured?"Bài có lựa chọn":selected.clinical_exercise?"Phân tích ca bệnh":"Tự luận ngắn"}</Badge><span>{selected.topic||"Ca bệnh và hình ảnh"}</span></div><h2>Đề bài</h2>{selected.clinical_exercise?<><p className="prose">{selected.clinical_exercise.presentation}</p><PracticeImages exercise={selected.clinical_exercise}/><p className="prose">{selected.clinical_exercise.question}</p></>:<p className="prose">{selected.question}</p>}</section>
        <section className="answer-panel" aria-label="Khu vực trả lời"><h2>Câu trả lời của bạn</h2><form onSubmit={submit} noValidate aria-busy={busy}>{structured?<StructuredAnswers exercise={structured} answers={structuredAnswers} disabled={busy} change={value=>draft({question_id:selected.question_id,revision_id:structured.revision_id,structured_answers:value})}/>:<><label htmlFor="practice-answer">Câu trả lời</label><textarea id="practice-answer" maxLength={16000} placeholder="Trình bày các ý chính và điều kiện áp dụng…" value={answer} onChange={e=>draft({question_id:selected.question_id,student_answer:e.target.value})} disabled={busy} aria-invalid={!!fields.student_answer} aria-describedby="answer-help answer-error"/><span className="error" id="answer-error">{fields.student_answer}</span><p id="answer-help" className="helper">Tự lưu trên trình duyệt này theo tài khoản của bạn · {answer.length.toLocaleString("vi-VN")}/16.000 ký tự.</p></>}
          <div className="actions"><button disabled={busy||(!structured&&(!answer.trim()||!mode||mode==="unavailable"))}>{busy?"Đang xử lý bài nộp…":"Gửi câu trả lời"}<Icon name="arrow" size={18}/></button></div>{busy&&<p role="status" className="helper">Bạn có thể chờ tại đây. Lần nộp đã được ghi nhớ để tránh gửi lặp.</p>}{mode==="unavailable"&&!structured&&<Alert kind="warning">Đánh giá tự động chưa sẵn sàng. Câu trả lời của bạn vẫn được lưu trên trình duyệt.</Alert>}
        </form></section></div>
    </>}
  </main>;
}
