"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";
import { segmentLabels } from "@/components/shell/nav-items";
import { ChevronRightIcon } from "@/components/shell/Icons";

function toLabel(segment: string): string {
  return (
    segmentLabels[segment] ??
    segment.charAt(0).toUpperCase() + segment.slice(1).replace(/-/g, " ")
  );
}

export function Breadcrumb() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  const crumbs = segments.map((segment, index) => ({
    label: toLabel(segment),
    href: `/${segments.slice(0, index + 1).join("/")}`,
    isLast: index === segments.length - 1,
  }));

  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <ol>
        <li>
          <Link href="/dashboard">Trang chủ</Link>
        </li>
        {crumbs.map((crumb) => (
          <Fragment key={crumb.href}>
            <li className="breadcrumb-sep" aria-hidden="true">
              <ChevronRightIcon width={14} height={14} />
            </li>
            <li>
              {crumb.isLast ? (
                <span aria-current="page">{crumb.label}</span>
              ) : (
                <Link href={crumb.href}>{crumb.label}</Link>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
