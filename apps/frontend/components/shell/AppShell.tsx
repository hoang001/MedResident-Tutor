"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/shell/Sidebar";
import { Header } from "@/components/shell/Header";
import { Breadcrumb } from "@/components/shell/Breadcrumb";
import { Disclaimer } from "@/components/shell/Disclaimer";
import { mockCurrentUser } from "@/fixtures/dashboard";

/** Routes that render standalone (no sidebar/header chrome). */
const BARE_ROUTES = new Set(["/", "/login", "/register"]);

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastPath, setLastPath] = useState(pathname);

  // Close the mobile sidebar on navigation by adjusting state during render
  // (the recommended alternative to a route-change effect).
  if (pathname !== lastPath) {
    setLastPath(pathname);
    setSidebarOpen(false);
  }

  if (BARE_ROUTES.has(pathname)) {
    return <>{children}</>;
  }

  return (
    <div className="app-shell">
      <Sidebar
        role={mockCurrentUser.role}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="app-main">
        <Header user={mockCurrentUser} onOpenSidebar={() => setSidebarOpen(true)} />
        <div className="app-content">
          <Breadcrumb />
          <Disclaimer />
          <main id="main-content">{children}</main>
        </div>
      </div>
    </div>
  );
}
