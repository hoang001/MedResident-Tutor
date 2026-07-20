import type { DashboardSummary } from "@/lib/types";
import { StatCard } from "@/components/dashboard/StatCard";

interface SummaryStatsProps {
  summary: DashboardSummary;
}

export function SummaryStats({ summary }: SummaryStatsProps) {
  return (
    <div className="stat-grid">
      <StatCard label="Chủ đề đã học" value={String(summary.topicsStudied)} hint="Tổng số chủ đề" />
      <StatCard label="Bài thi đã làm" value={String(summary.examsTaken)} hint="Bài thi thử" />
      <StatCard
        label="Điểm trung bình"
        value={`${summary.averageScore}%`}
        hint="Trên các bài thi thử"
      />
      <StatCard
        label="Chủ đề cần ôn lại"
        value={String(summary.topicsToReview)}
        hint="Ưu tiên củng cố"
        emphasis
      />
    </div>
  );
}
