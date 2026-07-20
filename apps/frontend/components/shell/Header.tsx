"use client";

import type { CurrentUser } from "@/lib/types";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { MenuIcon } from "@/components/shell/Icons";

interface HeaderProps {
  user: CurrentUser;
  onOpenSidebar: () => void;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.charAt(0) ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : "";
  return (first + last).toUpperCase() || "?";
}

const roleLabels: Record<CurrentUser["role"], string> = {
  learner: "Bác sĩ nội trú",
  admin: "Quản trị viên",
};

export function Header({ user, onOpenSidebar }: HeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header-left">
        <button
          type="button"
          className="icon-button app-header-menu"
          onClick={onOpenSidebar}
          aria-label="Mở menu điều hướng"
          aria-controls="app-sidebar"
        >
          <MenuIcon />
        </button>
        <span className="app-header-title">MedResident Tutor</span>
      </div>

      <div className="app-header-right">
        <ThemeToggle />
        <div className="app-user">
          <span className="app-user-avatar" aria-hidden="true">
            {initials(user.fullName)}
          </span>
          <span className="app-user-meta">
            <span className="app-user-name">{user.fullName}</span>
            <span className="app-user-role">{roleLabels[user.role]}</span>
          </span>
        </div>
      </div>
    </header>
  );
}
