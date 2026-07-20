import { mockLearnerDashboard } from "@/fixtures/dashboard";
import { GreetingHeader } from "@/components/dashboard/GreetingHeader";
import { SummaryStats } from "@/components/dashboard/SummaryStats";
import { TopicList } from "@/components/dashboard/TopicList";
import { RecommendedDocuments } from "@/components/dashboard/RecommendedDocuments";
import { RecentExams } from "@/components/dashboard/RecentExams";
import { Panel } from "@/components/ui/Panel";

export default function DashboardPage() {
  const { summary, currentTopics, weakTopics, recommendedDocuments, recentExams } =
    mockLearnerDashboard;

  return (
    <div className="page">
      <GreetingHeader name={summary.learnerName} />
      <SummaryStats summary={summary} />

      <div className="dashboard-grid">
        <Panel
          title="Chủ đề đang học"
          description="Những chủ đề bạn đang theo dõi gần đây"
          action={{ label: "Xem tất cả", href: "/learn" }}
        >
          <TopicList
            topics={currentTopics}
            variant="current"
            emptyMessage="Bạn chưa bắt đầu chủ đề nào."
          />
        </Panel>

        <Panel
          title="Chủ đề còn yếu"
          description="Ưu tiên củng cố những phần dưới đây"
          action={{ label: "Ôn lại", href: "/review" }}
        >
          <TopicList
            topics={weakTopics}
            variant="weak"
            emptyMessage="Chưa xác định được chủ đề cần củng cố."
          />
        </Panel>

        <Panel
          title="Tài liệu được đề xuất"
          description="Dựa trên tiến độ và chủ đề còn yếu"
          action={{ label: "Kho tài liệu", href: "/learn" }}
        >
          <RecommendedDocuments
            documents={recommendedDocuments}
            emptyMessage="Chưa có tài liệu đề xuất."
          />
        </Panel>

        <Panel
          title="Bài thi gần đây"
          description="Kết quả các bài thi thử mới nhất"
          action={{ label: "Xem lịch sử", href: "/progress" }}
        >
          <RecentExams
            exams={recentExams}
            emptyMessage="Bạn chưa hoàn thành bài thi thử nào."
          />
        </Panel>
      </div>
    </div>
  );
}
