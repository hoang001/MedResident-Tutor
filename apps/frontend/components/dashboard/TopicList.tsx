import type { Topic } from "@/lib/types";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Badge } from "@/components/ui/Badge";
import { InlineEmpty } from "@/components/ui/StateViews";

interface TopicListProps {
  topics: Topic[];
  variant?: "current" | "weak";
  emptyMessage: string;
}

export function TopicList({
  topics,
  variant = "current",
  emptyMessage,
}: TopicListProps) {
  if (topics.length === 0) {
    return <InlineEmpty message={emptyMessage} />;
  }

  const tone = variant === "weak" ? "warning" : "primary";

  return (
    <ul className="topic-list">
      {topics.map((topic) => (
        <li key={topic.id} className="topic-item">
          <div className="topic-item-top">
            <div className="topic-item-info">
              <p className="topic-item-name">{topic.name}</p>
              <p className="topic-item-specialty muted">{topic.specialty}</p>
            </div>
            <Badge tone={variant === "weak" ? "warning" : "primary"}>
              {topic.progress}%
            </Badge>
          </div>
          <ProgressBar
            value={topic.progress}
            tone={tone}
            label={`Tiến độ ${topic.name}`}
          />
        </li>
      ))}
    </ul>
  );
}
