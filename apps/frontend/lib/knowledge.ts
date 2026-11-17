"use client";

import {useEffect, useState} from "react";
import {apiRequest, errorMessage, getToken, loginRedirect} from "@/lib/api";

export type User = {id: string; full_name: string; role: string};
export type Citation = {source_id: string; title: string; pdf_pages: number[]; printed_pages: (string | number)[]; excerpt: string};
export type Brief = {id: string; title: string; type: string; snippet: string; revision: string; book_ids: string[]};
export type KnowledgeNode = Brief & {
  curricular: boolean;
  content: {text: string; sources: Citation[]}[];
  sources: Citation[];
  metadata: Record<string, string | number | boolean>;
  evidence: {quote?: string; url?: string; source_id?: string; locator?: unknown}[];
  relations: {type: string; outgoing: boolean; target: Brief; condition?: string}[];
  relation_count: number;
  suggested_topics?: {title: string; status: string; source_ids: string[]}[];
  study_role?: "focus" | "prior_outcomes_only";
  course_outcomes_status?: string;
};
export type Source = {id: string; title: string; year: number; pages: number; sha256: string; node_count: number; pdf_available: boolean; chapters: {number: number; title: string; start: number; end: number; opening_missing: boolean}[]};
export type Reading = {node_id: string; title?: string; read_state: "unread" | "reading" | "read"; bookmarked: boolean; note: string; version: number; revision: string; updated_at?: string};
export type Summary = {reading: number; read: number; bookmarked: number; drafts: number; submitted: number; recent: Reading[]};
export type StudyQuestion = {id: string; title: string; sources: Citation[]; revision: string; origin?: "book" | "kg_template"; task?: string; node_ids?: string[]; study_basis?: {text?: string; relation_type?: string; condition?: string; sources: Citation[]}[]};
export type StudySession = {id: string; version: number; status: "draft" | "submitted"; questions: StudyQuestion[]; answers: Record<string, string>; created_at: string; updated_at: string; graded: false; score: null};
export type SessionBrief = Omit<StudySession, "questions" | "answers"> & {question_count: number; answered_count: number};
export type Review = {id: string; status: string; note: string; reviewer: string; created_at: string; current: boolean};

export const types: Record<string, string> = {
  Condition: "Bệnh / tổn thương", Anatomy: "Giải phẫu", Finding: "Dấu hiệu",
  Classification: "Phân loại", ClassificationCategory: "Nhóm phân loại",
  DiagnosticMethod: "Phương pháp chẩn đoán", Intervention: "Can thiệp", Drug: "Thuốc",
  ClinicalPrinciple: "Nguyên tắc lâm sàng", Skill: "Kỹ năng", SampleQuestion: "Câu hỏi từ sách",
  Course: "Học phần", Curriculum: "Chương trình", CurriculumGroup: "Khối kiến thức",
  CurriculumRequirement: "Yêu cầu", CurriculumOutcome: "Chuẩn đầu ra chương trình",
  CurriculumObjective: "Mục tiêu chương trình", CurriculumSource: "Nguồn HMU",
};
export const relations: Record<string, string> = {
  IS_A: "thuộc loại", MANAGED_BY: "xử trí bằng", HAS_CATEGORY: "có nhóm",
  CLASSIFIED_BY: "phân loại theo", HAS_FINDING: "có dấu hiệu", MAY_CAUSE: "có thể gây",
  LOCATED_IN: "ở vị trí", EVALUATED_BY: "đánh giá bằng", USES_DRUG: "sử dụng thuốc",
  GUIDED_BY: "theo nguyên tắc", APPLIES_TO: "áp dụng cho", ABOUT: "liên quan đến",
  ASSESSES: "đánh giá", REQUIRES_KNOWLEDGE_OF: "cần kiến thức về", SUPPORTED_BY: "được dẫn nguồn bởi",
  HAS_SOURCE: "có nguồn", HAS_OBJECTIVE: "có mục tiêu", HAS_PROGRAM_OUTCOME: "có chuẩn đầu ra",
  HAS_CAREER_PATH: "có định hướng nghề nghiệp", HAS_STUDY_PATH: "có hướng học tiếp",
  REFERENCES_FRAMEWORK: "tham chiếu khung", HAS_COURSE: "có học phần", HAS_GROUP: "có khối kiến thức",
  HAS_REQUIREMENT: "có yêu cầu",
};
export const reviewLabels: Record<string, string> = {needs_review: "Chờ đối chiếu", source_checked: "Đã đối chiếu nguồn", needs_correction: "Cần sửa nội dung"};
export function nodeHref(id: string) {return `/knowledge?id=${encodeURIComponent(id)}`;}
export function pdfHref(source: string, page = 1) {return `/sources?id=${encodeURIComponent(source)}&page=${page}`;}
export function date(value?: string) {return value ? new Date(value).toLocaleString("vi-VN") : "";}

export function useWorkspace() {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    if (!getToken()) {loginRedirect(); return;}
    void apiRequest<User>("/auth/me").then(value => {if (active) setUser(value);}).catch(e => {if (active) setError(errorMessage(e));});
    const changed = (e: StorageEvent) => {if (e.key === "access_token") window.location.reload();};
    window.addEventListener("storage", changed);
    return () => {active = false; window.removeEventListener("storage", changed);};
  }, []);
  return {user, error};
}
