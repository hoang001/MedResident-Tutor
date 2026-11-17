import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import "./globals.css";
import "./ui-theme.css";

export const metadata: Metadata = {
  title: "MedResident Tutor — Không gian học tập",
  description: "Chương trình, thư viện kiến thức và tự luyện theo tài liệu nguồn cho bác sĩ nội trú",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi"><head><link rel="preload" href="/fonts/source-sans-3-upright.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/></head><body><a className="skip-link" href="#main-content">Chuyển đến nội dung chính</a><AppShell>{children}</AppShell></body></html>;
}
