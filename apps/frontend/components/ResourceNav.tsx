"use client";
import Link from "next/link";
import {usePathname} from "next/navigation";
export function ResourceNav(){const path=usePathname();return <nav className="content-tabs" aria-label="Tài nguyên học tập">{[["/knowledge","Thư viện kiến thức"],["/sources","Sách & mục lục"],["/curriculum","Khung chương trình"],["/exams","Tự ôn theo tài liệu"]].map(([href,label])=><Link key={href} href={href} aria-current={path===href?"page":undefined}>{label}</Link>)}</nav>;}
