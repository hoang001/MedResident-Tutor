// Domain types shared across the learner-facing UI.

export type TopicStatus = "learning" | "weak" | "mastered";

export type UserRole = "learner" | "admin";

export interface CurrentUser {
  id: string;
  fullName: string;
  role: UserRole;
}

export interface Topic {
  id: string;
  name: string;
  specialty: string;
  /** Completion percentage, 0-100. */
  progress: number;
  status: TopicStatus;
  lastStudied: string;
}

export type DocumentKind = "PDF" | "Markdown" | "Text";

export interface RecommendedDocument {
  id: string;
  title: string;
  kind: DocumentKind;
  specialty: string;
  reason: string;
}

export interface ExamAttempt {
  id: string;
  title: string;
  date: string;
  correct: number;
  totalQuestions: number;
  /** Score percentage, 0-100. */
  score: number;
}

export interface DashboardSummary {
  learnerName: string;
  topicsStudied: number;
  examsTaken: number;
  /** Average score percentage, 0-100. */
  averageScore: number;
  topicsToReview: number;
}

export interface LearnerDashboard {
  summary: DashboardSummary;
  currentTopics: Topic[];
  weakTopics: Topic[];
  recommendedDocuments: RecommendedDocument[];
  recentExams: ExamAttempt[];
}
