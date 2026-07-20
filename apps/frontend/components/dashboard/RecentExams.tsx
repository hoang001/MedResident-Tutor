import type { ExamAttempt } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { InlineEmpty } from "@/components/ui/StateViews";

interface RecentExamsProps {
  exams: ExamAttempt[];
  emptyMessage: string;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function scoreTone(score: number): "success" | "warning" | "neutral" {
  if (score >= 80) return "success";
  if (score >= 60) return "neutral";
  return "warning";
}

export function RecentExams({ exams, emptyMessage }: RecentExamsProps) {
  if (exams.length === 0) {
    return <InlineEmpty message={emptyMessage} />;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Bài thi</th>
            <th scope="col">Ngày</th>
            <th scope="col">Số câu đúng</th>
            <th scope="col">Điểm</th>
          </tr>
        </thead>
        <tbody>
          {exams.map((exam) => (
            <tr key={exam.id}>
              <td className="data-table-primary">{exam.title}</td>
              <td className="muted">{formatDate(exam.date)}</td>
              <td className="muted">
                {exam.correct}/{exam.totalQuestions}
              </td>
              <td>
                <Badge tone={scoreTone(exam.score)}>{exam.score}%</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
