"use client";
import Link from "next/link";
import {useRouter,useSearchParams} from "next/navigation";
import {FormEvent,Suspense,useEffect,useState} from "react";
import {apiRequest,errorMessage} from "@/lib/api";
import {useWorkspace} from "@/lib/knowledge";
import {Attempt,PracticeHistory} from "@/lib/practice-types";
import {attemptName,executionLabel,formatDate,statusLabel,statusTone} from "@/lib/practice-display";
import {PracticeResult} from "@/components/PracticeResult";
import {Alert,Badge,EmptyState,Loading,PageHeading,Pagination} from "@/components/ui";
import {Icon} from "@/components/Icon";

function History(){
  const {user,error:authError}=useWorkspace();const params=useSearchParams();const router=useRouter();const id=params.get("attempt");
  const [data,setData]=useState<PracticeHistory|null>(null);const [result,setResult]=useState<Attempt|null>(null);
  const [search,setSearch]=useState("");const [query,setQuery]=useState("");const [status,setStatus]=useState("all");const [offset,setOffset]=useState(0);
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [reload,setReload]=useState(0);
  useEffect(()=>{
    if(!user)return;let active=true;queueMicrotask(()=>{setLoading(true);setError("");setResult(null);});
    const request=id?apiRequest<Attempt>(`/practice/attempts/${encodeURIComponent(id)}`).then(a=>{if(active)setResult(a);}):apiRequest<PracticeHistory>(`/practice/history?${new URLSearchParams({q:query,status,offset:String(offset),limit:"15"})}`).then(d=>{if(active)setData(d);});
    void request.catch(e=>{if(active)setError(errorMessage(e));}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};
  },[user,id,query,status,offset,reload]);
  useEffect(()=>{
    if(!result||!["pending","medical_running","teaching_running"].includes(result.status))return;
    let active=true;const timer=setInterval(()=>void apiRequest<Attempt>(`/practice/attempts/${result.id}`).then(a=>{if(active)setResult(a);}).catch(e=>{if(active)setError(errorMessage(e));}),1500);
    return()=>{active=false;clearInterval(timer);};
  },[result]);
  async function retry(){
    if(!result||busy)return;setBusy(true);setError("");try{
      const cfg=await apiRequest<{request_timeout_ms?:number}>("/practice/config");
      setResult(await apiRequest<Attempt>(`/practice/attempts/${result.id}/retry`,{method:"POST"},{timeoutMs:cfg.request_timeout_ms}));
    }catch(e){setError(errorMessage(e));}finally{setBusy(false);}
  }
  function submit(e:FormEvent){e.preventDefault();setOffset(0);setQuery(search);}
  return <main className="container library">{id&&<p><Link className="text-link" href="/history">Về lịch sử bài làm</Link></p>}<PageHeading title={id&&result?attemptName(result):"Lịch sử & kết quả"} description={id?"Đề, câu trả lời và tài liệu đối chiếu của phiên bản đã làm.":"Xem lại các lượt làm đã lưu trong tài khoản của bạn."} action={<Link className="button secondary" href="/learn">Chọn bài tập<Icon name="arrow" size={18}/></Link>}/>
    {(authError||error)&&<Alert kind="error">{authError||error} <button className="text-button" onClick={()=>setReload(x=>x+1)}>Tải lại</button></Alert>}
    {id?loading?<Loading label="Đang mở bài làm đã lưu…"/>:result&&<><PracticeResult attempt={result} busy={busy} retry={retry}/><div className="actions"><Link className="button secondary" href={`/learn?question=${encodeURIComponent(result.question_id)}`}>Mở lại bài tập</Link><p className="helper">Xem lịch sử không tạo lần đánh giá mới.</p></div></>:<><form className="filters" onSubmit={submit}><label htmlFor="history-search">Tìm bài đã làm<span className="search-input"><Icon name="search"/><input id="history-search" type="search" maxLength={200} value={search} onChange={e=>setSearch(e.target.value)} placeholder="Nhập nội dung bài tập"/></span></label><label htmlFor="history-status">Trạng thái<select id="history-status" value={status} onChange={e=>{setStatus(e.target.value);setOffset(0);}}><option value="all">Tất cả trạng thái</option><option value="completed">Hoàn tất</option><option value="processing">Đang xử lý</option><option value="attention">Cần tiếp tục xử lý</option></select></label><button>Tìm bài làm</button></form>
      {loading?<Loading label="Đang tải lịch sử…"/>:data?.items.length?<><p className="muted">{data.overall_total} lượt đã lưu · {data.completed_total} lượt hoàn tất</p><ul className="list-surface data-list history-list">{data.items.map(a=><li key={a.id}><div><Link className="history-title" href={`/history?attempt=${a.id}`}>{attemptName(a)}</Link><p>{formatDate(a.created_at)} · {executionLabel(a)}</p><Badge tone={statusTone(a.status)}>{statusLabel(a.status)}</Badge></div><div className="row-actions">{a.medical_evaluation?<span className="history-score">{a.medical_evaluation.total_score}/{a.medical_evaluation.max_score}{a.execution_mode==="mock"?" điểm mô phỏng":" điểm"}</span>:a.structured_result?<span className="history-score">{a.structured_result.total_score}/{a.structured_result.max_score} điểm</span>:null}<button className="secondary" onClick={()=>router.push(`/history?attempt=${a.id}`)}>Xem kết quả</button></div></li>)}</ul></>:!error&&<EmptyState icon="history" title={query||status!=="all"?"Không có bài làm phù hợp":"Chưa có bài làm nào"} description={query||status!=="all"?"Thử từ khóa khác hoặc chọn tất cả trạng thái.":"Sau khi nộp bài, bạn có thể xem lại câu trả lời, kết quả và nguồn đối chiếu tại đây."} href="/learn" label="Chọn bài tập đầu tiên"/>}
      {data&&<Pagination total={data.total} offset={offset} limit={15} onPage={setOffset} busy={loading}/>}
    </>}
  </main>;
}
export default function HistoryPage(){return <Suspense fallback={<main className="container"><Loading/></main>}><History/></Suspense>;}
