// Development-only mock data for the learner dashboard.
// Kept isolated here so components stay free of hard-coded content and can be
// swapped for real API responses later without touching the UI layer.

import type { CurrentUser, LearnerDashboard } from "@/lib/types";

export const mockCurrentUser: CurrentUser = {
  id: "usr_demo_001",
  fullName: "Nguyễn Minh Anh",
  role: "learner",
};

export const mockLearnerDashboard: LearnerDashboard = {
  summary: {
    learnerName: "Minh Anh",
    topicsStudied: 24,
    examsTaken: 12,
    averageScore: 78,
    topicsToReview: 5,
  },
  currentTopics: [
    {
      id: "top_001",
      name: "Suy tim cấp",
      specialty: "Tim mạch",
      progress: 72,
      status: "learning",
      lastStudied: "2026-07-18",
    },
    {
      id: "top_002",
      name: "Viêm phổi cộng đồng",
      specialty: "Hô hấp",
      progress: 55,
      status: "learning",
      lastStudied: "2026-07-17",
    },
    {
      id: "top_003",
      name: "Rối loạn điện giải",
      specialty: "Nội tiết - Chuyển hóa",
      progress: 40,
      status: "learning",
      lastStudied: "2026-07-15",
    },
    {
      id: "top_004",
      name: "Nhiễm khuẩn huyết",
      specialty: "Hồi sức",
      progress: 88,
      status: "learning",
      lastStudied: "2026-07-19",
    },
  ],
  weakTopics: [
    {
      id: "top_010",
      name: "Cân bằng toan kiềm",
      specialty: "Hồi sức",
      progress: 28,
      status: "weak",
      lastStudied: "2026-07-10",
    },
    {
      id: "top_011",
      name: "Đọc điện tâm đồ nâng cao",
      specialty: "Tim mạch",
      progress: 34,
      status: "weak",
      lastStudied: "2026-07-12",
    },
    {
      id: "top_012",
      name: "Kháng sinh theo kinh nghiệm",
      specialty: "Truyền nhiễm",
      progress: 45,
      status: "weak",
      lastStudied: "2026-07-13",
    },
  ],
  recommendedDocuments: [
    {
      id: "doc_001",
      title: "Hướng dẫn tiếp cận suy tim cấp",
      kind: "PDF",
      specialty: "Tim mạch",
      reason: "Liên quan chủ đề đang học",
    },
    {
      id: "doc_002",
      title: "Bảng tra cân bằng toan kiềm",
      kind: "Markdown",
      specialty: "Hồi sức",
      reason: "Củng cố chủ đề còn yếu",
    },
    {
      id: "doc_003",
      title: "Nguyên tắc dùng kháng sinh kinh nghiệm",
      kind: "Text",
      specialty: "Truyền nhiễm",
      reason: "Củng cố chủ đề còn yếu",
    },
  ],
  recentExams: [
    {
      id: "exam_001",
      title: "Đề thi thử Tim mạch số 3",
      date: "2026-07-18",
      correct: 34,
      totalQuestions: 40,
      score: 85,
    },
    {
      id: "exam_002",
      title: "Đề thi thử Hô hấp số 2",
      date: "2026-07-14",
      correct: 27,
      totalQuestions: 40,
      score: 68,
    },
    {
      id: "exam_003",
      title: "Đề tổng hợp Nội khoa số 1",
      date: "2026-07-09",
      correct: 31,
      totalQuestions: 40,
      score: 78,
    },
  ],
};
