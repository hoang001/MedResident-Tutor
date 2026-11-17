import Link from "next/link";
import type {ReactNode} from "react";
import {Icon,IconName} from "@/components/Icon";
export function PageHeading({title,description,action}:{title:string;description?:string;action?:ReactNode}) {
  return <div className="page-heading"><div><h1>{title}</h1>{description&&<p>{description}</p>}</div>{action&&<div className="heading-action">{action}</div>}</div>;
}
export function Badge({children,tone="neutral"}:{children:ReactNode;tone?:"neutral"|"success"|"warning"|"danger"|"info"}) {return <span className={`status-badge ${tone}`}>{children}</span>;}
export function Alert({children,kind="info",title}:{children:ReactNode;kind?:"info"|"error"|"success"|"warning";title?:string}) {
  return <div className={`message ${kind}`} role={kind==="error"?"alert":"status"}><Icon name={kind==="success"?"check":kind==="error"||kind==="warning"?"alert":"info"}/><div>{title&&<strong>{title}</strong>}<div>{children}</div></div></div>;
}
export function EmptyState({title,description,href,label,icon="book"}:{title:string;description:string;href?:string;label?:string;icon?:IconName}) {
  return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={28}/></span><h3>{title}</h3><p>{description}</p>{href&&label&&<Link className="button" href={href}>{label}<Icon name="arrow" size={18}/></Link>}</div>;
}
export function Loading({label="Đang tải nội dung…"}:{label?:string}) {return <div className="loading-state" role="status"><span>{label}</span><div className="loading-line"/><div className="loading-line short"/></div>;}
export function Pagination({total,offset,limit,onPage,busy=false,label="Phân trang"}:{total:number;offset:number;limit:number;onPage:(offset:number)=>void;busy?:boolean;label?:string}) {
  return <nav className="pagination" aria-label={label}><span>{total?`${offset+1}–${Math.min(offset+limit,total)} trong ${total}`:"0 kết quả"}</span><div><button type="button" className="secondary" disabled={busy||offset===0} onClick={()=>onPage(Math.max(0,offset-limit))}>Trang trước</button><button type="button" className="secondary" disabled={busy||offset+limit>=total} onClick={()=>onPage(offset+limit)}>Trang sau</button></div></nav>;
}
