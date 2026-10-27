import {ApiError} from "./api";
export type Submission = {question_id: string; student_answer: string};
export type PendingSubmission = {key: string; payload: Submission; attemptId?: string};
export type PracticeState = {draft?: Submission; pending?: PendingSubmission};
function key(userId: string) { return `practice:v1:${userId}`; }
export function readPractice(userId: string): PracticeState {
  try {
    const value = JSON.parse(localStorage.getItem(key(userId)) ?? "{}");
    if (!value || typeof value !== "object") return {};
    const valid = (p: Submission) => p && typeof p.question_id === "string" && typeof p.student_answer === "string";
    return {draft: valid(value.draft) ? value.draft : undefined,
      pending: value.pending && /^[a-zA-Z0-9-]{1,128}$/.test(value.pending.key) && valid(value.pending.payload) && (value.pending.attemptId === undefined || /^[a-f0-9-]{36}$/.test(value.pending.attemptId)) ? value.pending : undefined};
  }
  catch { return {}; }
}
export function writePractice(userId: string, state: PracticeState): void {
  try { localStorage.setItem(key(userId), JSON.stringify(state)); }
  catch { throw new ApiError("Trình duyệt không lưu được lần nộp. Vui lòng bật bộ nhớ trang trước khi gửi.", 0, "STORAGE_UNAVAILABLE", "processing"); }
}
function newSubmissionKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // getRandomValues remains available on plain-HTTP development hostnames.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function prepareSubmission(userId: string, payload: Submission): PendingSubmission {
  const state = readPractice(userId);
  const previous = state.pending;
  const pending = previous && JSON.stringify(previous.payload) === JSON.stringify(payload)
    ? previous : {key: newSubmissionKey(), payload};
  // Must succeed before any network request. Reload/retry reuses this key.
  writePractice(userId, {draft: payload, pending});
  return pending;
}
export function rememberAttempt(userId: string, pending: PendingSubmission, attemptId: string): void {
  const state = readPractice(userId);
  if (state.pending?.key === pending.key) writePractice(userId, {...state, pending: {...pending, attemptId}});
}
