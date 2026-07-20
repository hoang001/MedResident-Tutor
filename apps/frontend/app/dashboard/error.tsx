"use client";

import { ErrorState } from "@/components/ui/StateViews";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorState
      message={error.message || "Đã xảy ra lỗi khi tải tổng quan học tập."}
      onRetry={reset}
    />
  );
}
