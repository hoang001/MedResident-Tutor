import type { ComponentType, SVGProps } from "react";
import type { UserRole } from "@/lib/types";
import {
  OverviewIcon,
  LearnIcon,
  ChatIcon,
  ExamIcon,
  ProgressIcon,
  ReviewIcon,
  DocumentsIcon,
} from "@/components/shell/Icons";

export interface NavItem {
  label: string;
  href: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Roles allowed to see this item. Omitted means every role. */
  roles?: UserRole[];
}

export const navItems: NavItem[] = [
  { label: "Tổng quan", href: "/dashboard", icon: OverviewIcon },
  { label: "Học tập", href: "/learn", icon: LearnIcon },
  { label: "Hỏi đáp AI", href: "/ai", icon: ChatIcon },
  { label: "Thi thử", href: "/exams", icon: ExamIcon },
  { label: "Kết quả học tập", href: "/progress", icon: ProgressIcon },
  { label: "Nội dung cần ôn lại", href: "/review", icon: ReviewIcon },
  {
    label: "Quản lý tài liệu",
    href: "/admin/documents",
    icon: DocumentsIcon,
    roles: ["admin"],
  },
];

/** Human-readable labels used by the breadcrumb for known route segments. */
export const segmentLabels: Record<string, string> = {
  dashboard: "Tổng quan",
  learn: "Học tập",
  ai: "Hỏi đáp AI",
  exams: "Thi thử",
  progress: "Kết quả học tập",
  review: "Nội dung cần ôn lại",
  admin: "Quản trị",
  documents: "Quản lý tài liệu",
  login: "Đăng nhập",
  register: "Đăng ký",
};
