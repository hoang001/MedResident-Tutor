interface GreetingHeaderProps {
  name: string;
}

function greetingForNow(date: Date): string {
  const hour = date.getHours();
  if (hour < 11) return "Chào buổi sáng";
  if (hour < 14) return "Chào buổi trưa";
  if (hour < 18) return "Chào buổi chiều";
  return "Chào buổi tối";
}

export function GreetingHeader({ name }: GreetingHeaderProps) {
  // Computed on render; acceptable for a greeting label.
  const greeting = greetingForNow(new Date());

  return (
    <div className="greeting">
      <h1 className="greeting-title">
        {greeting}, {name}
      </h1>
      <p className="greeting-sub muted">
        Đây là tổng quan tiến độ học tập và ôn luyện của bạn.
      </p>
    </div>
  );
}
