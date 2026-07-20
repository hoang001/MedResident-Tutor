"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { UserRole } from "@/lib/types";
import { navItems } from "@/components/shell/nav-items";
import { CloseIcon } from "@/components/shell/Icons";

interface SidebarProps {
  role: UserRole;
  /** Whether the mobile off-canvas sidebar is open. */
  open: boolean;
  onClose: () => void;
}

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({ role, open, onClose }: SidebarProps) {
  const pathname = usePathname();
  const items = navItems.filter((item) => !item.roles || item.roles.includes(role));

  return (
    <>
      <div
        className={`sidebar-scrim ${open ? "is-open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        id="app-sidebar"
        className={`sidebar ${open ? "is-open" : ""}`}
        aria-label="Điều hướng chính"
      >
        <div className="sidebar-head">
          <Link href="/dashboard" className="sidebar-brand" onClick={onClose}>
            <span className="sidebar-brand-mark" aria-hidden="true">
              MR
            </span>
            <span className="sidebar-brand-text">MedResident Tutor</span>
          </Link>
          <button
            type="button"
            className="icon-button sidebar-close"
            onClick={onClose}
            aria-label="Đóng menu điều hướng"
          >
            <CloseIcon />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Danh mục">
          <ul>
            {items.map((item) => {
              const active = isActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={`sidebar-link ${active ? "is-active" : ""}`}
                    aria-current={active ? "page" : undefined}
                    onClick={onClose}
                  >
                    <Icon className="sidebar-link-icon" />
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <p className="sidebar-note">
          Công cụ hỗ trợ học tập. Không dùng cho chẩn đoán hay điều trị.
        </p>
      </aside>
    </>
  );
}
