"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {apiRequest,errorMessage} from "@/lib/api";
import {Summary,nodeHref,useWorkspace} from "@/lib/knowledge";
import {PracticeCatalog,PracticeHistory} from "@/lib/practice-types";
import {attemptName,executionLabel,formatDate,statusLabel,statusTone} from "@/lib/practice-display";
import {Alert,Badge,EmptyState,Loading,PageHeading} from "@/components/ui";
import {Icon} from "@/components/Icon";

export default function Overview(){
  const {user,error:authError}=useWorkspace();
  const [study,setStudy]=useState<Summary|null>(null);const [practice,setPractice]=useState<PracticeHistory|null>(null);const [catalog,setCatalog]=useState<PracticeCatalog|null>(null);
  const [studyError,setStudyError]=useState("");const [practiceError,setPracticeError]=useState("");const [reload,setReload]=useState(0);
  useEffect(()=>{
    if(!user)return;let active=true;
    void apiRequest<Summary>("/study/summary").then(d=>{if(active){setStudy(d);setStudyError("");}}).catch(e=>{if(active)setStudyError(errorMessage(e));});
    void apiRequest<PracticeHistory>("/practice/history?limit=5").then(d=>{if(active){setPractice(d);setPracticeError("");}}).catch(e=>{if(active)setPracticeError(errorMessage(e));});
    void apiRequest<PracticeCatalog>("/practice/catalog?limit=1").then(d=>{if(active)setCatalog(d);}).catch(e=>{if(active)setPracticeError(errorMessage(e));});
    return()=>{active=false;};
  },[user,reload]);
  const recent=practice?.items[0];const reading=study?.recent.find(r=>r.read_state==="reading")??study?.recent[0];
  const href=recent?`/history?attempt=${recent.id}`:reading?nodeHref(reading.node_id):"/learn";
  return <main className="container library"><PageHeading title={user?`Chào ${user.full_name.split(/\s+/).slice(-2).join(" ")}`:"Tổng quan học tập"} description="Tiếp tục phiên học của bạn, từng nội dung và từng bài tập." action={user?.role==="ADMIN"?<Link className="button secondary" href="/admin/questions">Quản trị nội dung</Link>:undefined}/>
    {authError&&<Alert kind="error">{authError}</Alert>}{practiceError&&<Alert kind="error">Chưa tải được hoạt động luyện tập. <button className="text-button" onClick={()=>setReload(x=>x+1)}>Tải lại</button></Alert>}
    {!practice&&!practiceError?<Loading label="Đang tải hoạt động học tập…"/>:<section className="welcome-panel"><div><h2>{recent?"Bài làm gần đây của bạn":reading?"Tiếp tục nội dung đang học":"Bắt đầu một phiên học"}</h2><p>{recent?attemptName(recent):reading?.title??"Chọn một chủ đề, đọc kỹ đề và tự kiểm tra kiến thức bằng bài tập có tài liệu đối chiếu."}</p><Link className="button" href={href}>{recent?"Xem lại bài gần nhất":reading?"Tiếp tục đọc":"Chọn bài tập đầu tiên"}<Icon name="arrow" size={18}/></Link></div><div className="welcome-summary">{catalog&&<div><span>Bài tập khả dụng</span><strong>{catalog.available_total}</strong></div>}{practice&&<><div><span>Lượt làm đã lưu</span><strong>{practice.overall_total}</strong></div><div><span>Lượt hoàn tất</span><strong>{practice.completed_total}</strong></div></>}</div></section>}
    <div className="dashboard-columns"><section><div className="section-heading"><h2>Hoạt động luyện tập</h2><Link className="text-link" href="/history">Xem tất cả<Icon name="arrow" size={16}/></Link></div>{practice?.items.length?<ul className="data-list">{practice.items.map(a=><li key={a.id}><div><Link className="history-title" href={`/history?attempt=${a.id}`}>{attemptName(a)}</Link><p>{formatDate(a.created_at)} · {executionLabel(a)}</p><Badge tone={statusTone(a.status)}>{statusLabel(a.status)}</Badge></div><Link href={`/history?attempt=${a.id}`} aria-label={`Xem kết quả: ${attemptName(a)}`}><Icon name="chevron"/></Link></li>)}</ul>:practice&&<EmptyState icon="practice" title="Chưa có bài làm nào" description="Bài đã nộp sẽ được lưu tại đây để bạn xem lại câu trả lời và nguồn đối chiếu." href="/learn" label="Khám phá bài tập"/>}
      <div className="section-heading"><h2>Nội dung đã đọc và lưu</h2><Link className="text-link" href="/progress">Xem tiến độ<Icon name="arrow" size={16}/></Link></div>{studyError?<Alert>Chưa tải được dữ liệu đọc. Bạn có thể tiếp tục luyện tập và thử tải lại sau.</Alert>:study?<><div className="reading-summary"><span><strong>{study.read}</strong> mục đã đọc</span><span><strong>{study.reading}</strong> mục đang đọc</span><span><strong>{study.bookmarked}</strong> dấu trang</span></div>{study.recent.length?<ul className="clean-list">{study.recent.slice(0,4).map(r=><li key={r.node_id}><Link href={nodeHref(r.node_id)}>{r.title}</Link><p className="helper">{r.read_state==="read"?"Đã đọc":r.read_state==="reading"?"Đang đọc":"Đã lưu ghi chú"}</p></li>)}</ul>:<p className="muted">Bạn chưa lưu nội dung nào. <Link href="/knowledge">Mở thư viện</Link> để tìm chủ đề và ghi chú.</p>}</>:<Loading label="Đang tải nội dung đã lưu…"/>}</section>
      <aside className="dashboard-side"><h2>Chủ đề có thể luyện</h2><div className="topic-list">{catalog?.topics.slice(0,6).map(t=><Link key={t.name} href={`/learn?topic=${encodeURIComponent(t.name)}`}><span>{t.name}</span><Badge>{t.count}</Badge></Link>)}</div><p><Link className="text-link" href="/learn">Xem ngân hàng bài tập<Icon name="arrow" size={16}/></Link></p><h3>Tài liệu học tập</h3><p className="helper">Đọc nội dung theo nguồn và mở sách tại trang được dẫn.</p><div className="topic-list"><Link href="/sources">Sách & mục lục<Icon name="files" size={18}/></Link><Link href="/exams">Tự ôn theo tài liệu<Icon name="edit" size={18}/></Link></div></aside></div>
    <p className="helper">Tiến độ đọc là ghi nhận hoàn thành của bạn, không phải mức độ thành thạo y khoa. Kết quả mô phỏng không được dùng để xác nhận năng lực.</p>
  </main>;
}
