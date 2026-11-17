"use client";
import Link from "next/link";
import {FormEvent,useEffect,useState} from "react";
import {apiRequest,errorMessage} from "@/lib/api";
import {PracticeCatalog} from "@/lib/practice-types";
import {questionName,statusLabel,statusTone} from "@/lib/practice-display";
import {readPractice} from "@/lib/practice-storage";
import {Alert,Badge,EmptyState,Loading,PageHeading,Pagination} from "@/components/ui";
import {Icon} from "@/components/Icon";

export function ExerciseCatalog({userId,initialTopic=""}:{userId:string;initialTopic?:string}) {
  const [q,setQ]=useState("");const [query,setQuery]=useState("");const [topic,setTopic]=useState(initialTopic);const [offset,setOffset]=useState(0);
  const [data,setData]=useState<PracticeCatalog|null>(null);const [loading,setLoading]=useState(true);const [error,setError]=useState("");
  const [resume,setResume]=useState<string|null>(null);const [reload,setReload]=useState(0);
  useEffect(()=>{const saved=readPractice(userId);queueMicrotask(()=>setResume(saved.pending?.attemptId?`/history?attempt=${saved.pending.attemptId}`:saved.draft?.question_id?`/learn?question=${encodeURIComponent(saved.draft.question_id)}`:null));},[userId]);
  useEffect(()=>{
    let active=true;queueMicrotask(()=>{setLoading(true);setError("");});
    const params=new URLSearchParams({q:query,topic,offset:String(offset),limit:"10"});
    void apiRequest<PracticeCatalog>(`/practice/catalog?${params}`).then(value=>{if(active)setData(value);}).catch(reason=>{if(active)setError(errorMessage(reason));}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[query,topic,offset,reload]);
  function search(e:FormEvent){e.preventDefault();setOffset(0);setQuery(q);}
  return <main className="container library"><PageHeading title="Ngân hàng bài tập" description="Chọn chủ đề, làm bài và đối chiếu với đáp án cùng tài liệu nguồn." action={<Link className="button secondary" href="/history"><Icon name="history"/>Lịch sử & kết quả</Link>}/>
    {resume&&<div className="catalog-intro"><p className="muted">Bạn có một bài gần đây đã lưu trong tài khoản này.</p><Link className="text-link" href={resume}>Tiếp tục xem bài<Icon name="arrow" size={18}/></Link></div>}
    <form className="filters" onSubmit={search}><label htmlFor="exercise-search">Tìm bài tập<span className="search-input"><Icon name="search"/><input id="exercise-search" type="search" maxLength={200} placeholder="Ví dụ: trật khớp vai" value={q} onChange={e=>setQ(e.target.value)}/></span></label><label htmlFor="exercise-topic">Chủ đề<select id="exercise-topic" value={topic} onChange={e=>{setTopic(e.target.value);setOffset(0);}}><option value="">Tất cả chủ đề</option>{data?.topics.map(t=><option value={t.name} key={t.name}>{t.name} ({t.count})</option>)}</select></label><button>Tìm bài tập</button></form>
    <div className="section-heading"><p className="muted" role="status">{loading?"Đang tìm bài tập…":data?`${data.total} bài phù hợp · ${data.available_total} bài khả dụng trong ngân hàng`:""}</p>{(query||topic)&&<button className="text-button" onClick={()=>{setQ("");setQuery("");setTopic("");setOffset(0);}}>Xóa bộ lọc</button>}</div>
    {error&&<Alert kind="error">{error} <button className="text-button" onClick={()=>setReload(x=>x+1)}>Tải lại danh sách</button></Alert>}
    {loading?<Loading label="Đang tải bài tập…"/>:data?.items.length?<section className="list-surface" aria-label="Danh sách bài tập">{data.items.map(item=><article className="question-row" key={item.question_id}><div><div className="metadata-row"><span>{item.topic||"Ca bệnh và hình ảnh"}</span><Badge>{item.structured_exercise?"Bài có lựa chọn":item.clinical_exercise?"Phân tích ca bệnh":"Tự luận ngắn"}</Badge>{item.attempt_status&&<Badge tone={statusTone(item.attempt_status)}>{statusLabel(item.attempt_status)}</Badge>}</div><h2><Link href={`/learn?question=${encodeURIComponent(item.question_id)}`}>{questionName(item)}</Link></h2>{item.clinical_exercise&&<span className="exercise-type"><Icon name="files" size={15}/> Có hình ảnh đối chiếu</span>}</div><div className="actions"><Link className="button secondary" href={`/learn?question=${encodeURIComponent(item.question_id)}`}>{item.attempt_status?"Làm lại bài":"Mở bài"}<Icon name="arrow" size={17}/></Link>{item.last_attempt_id&&<Link className="text-link" href={`/history?attempt=${item.last_attempt_id}`}>Xem kết quả</Link>}</div></article>)}</section>:!error&&<EmptyState icon="search" title="Chưa có bài phù hợp" description="Thử từ khóa ngắn hơn hoặc bỏ bộ lọc chủ đề. Các câu chưa phát hành sẽ không xuất hiện ở đây."/>}
    {data&&<Pagination total={data.total} offset={offset} limit={10} onPage={setOffset} busy={loading}/>}
    <p className="helper">Muốn ôn thêm theo sách? <Link href="/exams">Tự ôn theo tài liệu</Link> là khu vực tham khảo riêng, chưa chấm điểm.</p>
  </main>;
}
