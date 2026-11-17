"use client";
import {useEffect,useState} from "react";
import {apiRequest,errorMessage,logout} from "@/lib/api";
import {useWorkspace} from "@/lib/knowledge";
import {Alert,Badge,Loading,PageHeading} from "@/components/ui";
type Account={full_name:string;email:string;role:string};
export default function AccountPage(){
 const {user,error:authError}=useWorkspace();const [account,setAccount]=useState<Account|null>(null);const [error,setError]=useState("");
 useEffect(()=>{if(!user)return;let active=true;void apiRequest<Account>("/auth/me").then(u=>{if(active)setAccount(u);}).catch(e=>{if(active)setError(errorMessage(e));});return()=>{active=false;};},[user]);
 return <main className="container"><PageHeading title="Thông tin tài khoản" description="Thông tin của tài khoản đang sử dụng trên trình duyệt này."/>{(authError||error)&&<Alert kind="error">{authError||error}</Alert>}{!account&&!error?<Loading/>:account&&<section className="panel account-details"><dl><dt>Họ và tên</dt><dd>{account.full_name}</dd><dt>Email</dt><dd>{account.email}</dd><dt>Vai trò</dt><dd><Badge>{account.role==="ADMIN"?"Quản trị viên":"Học viên"}</Badge></dd></dl><p className="helper">Hệ thống hiện hỗ trợ xem thông tin tài khoản. Chức năng thay đổi hồ sơ và mật khẩu chưa được triển khai.</p><div className="actions"><button className="secondary" onClick={logout}>Đăng xuất</button></div></section>}</main>;
}
