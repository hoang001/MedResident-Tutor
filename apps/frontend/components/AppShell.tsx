"use client";
import Link from "next/link";
import {usePathname} from "next/navigation";
import {ReactNode,useEffect,useRef,useState} from "react";
import {apiRequest,clearToken,getToken,loginRedirect,logout} from "@/lib/api";
import {Icon,IconName} from "@/components/Icon";
type Account={full_name:string;email:string;role:string};
const studentLinks:[string,string,IconName][]=[["Tổng quan","/dashboard","home"],["Thư viện học tập","/knowledge","book"],["Bài tập","/learn","practice"],["Lịch sử & kết quả","/history","history"],["Tiến độ học tập","/progress","chart"]];
const adminLinks:[string,string,IconName][]=[["Ngân hàng câu hỏi","/admin/questions","practice"],["Tài liệu & nguồn","/admin/documents","files"]];
export function AppShell({children}:{children:ReactNode}) {
  const pathname=usePathname();const [user,setUser]=useState<Account|null>(null);
  const menu=useRef<HTMLDialogElement>(null);const account=useRef<HTMLDetailsElement>(null);
  const publicPage=["/","/login","/register"].includes(pathname);
  const adminSpace=pathname.startsWith("/admin")&&user?.role==="ADMIN";
  useEffect(()=>{
    let active=true;let timer:ReturnType<typeof setTimeout>|undefined;
    const update=()=>{
      clearTimeout(timer);const token=getToken();if(!token){setUser(null);return;}
      void apiRequest<Account>("/auth/me",{},{redirectOn401:false}).then(u=>{if(active&&getToken()===token)setUser(u);}).catch(()=>{if(active)setUser(null);});
      try{const claims=JSON.parse(atob(token.split(".")[1].replace(/-/g,"+").replace(/_/g,"/")));if(typeof claims.exp==="number"&&Number.isFinite(claims.exp))timer=setTimeout(()=>{clearToken();loginRedirect("expired");},Math.max(0,Math.min(claims.exp*1000-Date.now(),2147483647)));}catch{/* Backend validates credentials. */}
    };
    queueMicrotask(update);window.addEventListener("auth-changed",update);window.addEventListener("storage",update);
    return()=>{active=false;clearTimeout(timer);window.removeEventListener("auth-changed",update);window.removeEventListener("storage",update);};
  },[]);
  function close(){menu.current?.close();if(account.current)account.current.open=false;}
  const brand=<Link className="brand" href={user?"/dashboard":"/"} onClick={close}><span className="brand-mark"><Icon name="book" size={24}/></span><span>MedResident<span className="brand-second">Tutor</span></span></Link>;
  const navigation=<><nav aria-label={adminSpace?"Điều hướng quản trị":"Điều hướng học tập"}>{(adminSpace?adminLinks:studentLinks).map(([label,href,icon])=><Link key={href} href={href} onClick={close} aria-current={pathname===href?"page":undefined}><Icon name={icon}/>{label}</Link>)}</nav><div className="nav-secondary"><p>Tài nguyên học tập</p><Link href="/sources" onClick={close}><Icon name="files"/>Sách & mục lục</Link><Link href="/curriculum" onClick={close}><Icon name="book"/>Khung chương trình</Link><Link href="/exams" onClick={close}><Icon name="edit"/>Tự ôn theo tài liệu</Link></div>{user?.role==="ADMIN"&&<Link className="space-switch" href={adminSpace?"/dashboard":"/admin/questions"} onClick={close}><Icon name={adminSpace?"home":"edit"}/>{adminSpace?"Không gian học tập":"Quản trị nội dung"}<Icon name="arrow" size={16}/></Link>}</>;
  if(publicPage)return <div className="public-shell"><header className="public-header">{brand}<nav aria-label="Tài khoản">{user?<Link className="button" href="/dashboard">Vào không gian học<Icon name="arrow" size={18}/></Link>:<><Link href="/login">Đăng nhập</Link><Link className="button" href="/register">Tạo tài khoản</Link></>}</nav></header><div id="main-content" tabIndex={-1}>{children}</div><footer className="public-footer">MedResident Tutor · Đồ án hỗ trợ học tập bác sĩ nội trú</footer></div>;
  return <div className="app-shell"><aside className="sidebar">{brand}<div className="space-label">{adminSpace?"Quản trị nội dung":"Không gian học tập"}</div>{navigation}<div className="sidebar-foot">Học tập có nguồn đối chiếu</div></aside><div className="app-main"><header className="app-header"><button className="icon-button mobile-menu" aria-label="Mở điều hướng" onClick={()=>menu.current?.showModal()}><Icon name="menu"/></button><Link className="header-section" href={adminSpace?"/admin/questions":"/dashboard"}>{adminSpace?"Quản trị nội dung":"Không gian học tập"}</Link><details className="account-menu" ref={account}><summary><span className="account-avatar">{user?.full_name.trim().split(/\s+/).slice(-2).map(n=>n[0]).join("")??"…"}</span><span className="account-name">{user?.full_name??"Đang xác thực…"}</span><Icon name="down" size={16}/></summary><div className="account-popover"><p>{user?.email}</p><Link href="/account" onClick={close}><Icon name="person"/>Thông tin tài khoản</Link><button className="text-button" onClick={logout}><Icon name="logout"/>Đăng xuất</button></div></details></header><div id="main-content" tabIndex={-1}>{children}</div><footer className="app-footer">MedResident Tutor · Không gian học tập và đối chiếu tài liệu</footer></div><dialog className="mobile-nav" ref={menu} onClick={e=>{if(e.target===menu.current)close();}}><div className="mobile-nav-head">{brand}<button className="icon-button" aria-label="Đóng điều hướng" onClick={close}><Icon name="close"/></button></div>{navigation}</dialog></div>;
}
