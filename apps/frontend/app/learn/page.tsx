"use client";
import {FormEvent, useEffect, useRef, useState} from "react";
import {ApiError, apiRequest, errorMessage, getToken, loginRedirect} from "@/lib/api";
import {PendingSubmission, readPractice, writePractice, prepareSubmission, rememberAttempt, Submission} from "@/lib/practice-storage";
import {Attempt, Question} from "@/lib/practice-types";
import {PracticeResult} from "@/components/PracticeResult";

export default function LearnPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [mode, setMode] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [questionId, setQuestionId] = useState("");
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState<Attempt[]>([]);
  const [result, setResult] = useState<Attempt | null>(null);
  const [pending, setPending] = useState<PendingSubmission | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const sending = useRef(false);
  function show(item: Attempt) { setResult(item); window.history.replaceState(null, "", `/learn?attempt=${item.id}`); }
  async function refresh() { setHistory(await apiRequest<Attempt[]>("/practice/attempts")); }
  useEffect(() => {
    let active = true;
    const changedAccount = () => {setResult(null); setHistory([]); setAnswer(""); setUserId(null); window.location.reload();};
    const storageChanged = (event: StorageEvent) => {if (event.key === "access_token") changedAccount();};
    window.addEventListener("storage", storageChanged);
    async function initialize() {
      if (!getToken()) {loginRedirect(); return;}
      try {
        // Never hydrate a draft/result until the server confirms this account.
        const user = await apiRequest<{id: string}>("/auth/me");
        const [qs, hs, cfg] = await Promise.all([apiRequest<Question[]>("/practice/questions"), apiRequest<Attempt[]>("/practice/attempts"), apiRequest<{execution_mode: string}>("/practice/config")]);
        if (!active) return;
        const local = readPractice(user.id);
        setUserId(user.id); setMode(cfg.execution_mode); setQuestions(qs); setHistory(hs); setPending(local.pending);
        setQuestionId(local.draft?.question_id ?? qs[0]?.question_id ?? ""); setAnswer(local.draft?.student_answer ?? "");
        const id = new URLSearchParams(window.location.search).get("attempt") ?? local.pending?.attemptId;
        if (id) {
          const item = await apiRequest<Attempt>(`/practice/attempts/${encodeURIComponent(id)}`);
          if (active) show(item);
        }
      } catch (reason) {if (active) setError(errorMessage(reason));}
    }
    void initialize();
    return () => {active = false; window.removeEventListener("storage", storageChanged);};
  }, []);
  useEffect(() => {
    if (!result || !["pending", "medical_running", "teaching_running"].includes(result.status)) return;
    let active = true;
    const timer = setInterval(() => apiRequest<Attempt>(`/practice/attempts/${result.id}`).then(item => {if (active) setResult(item);}).catch(reason => {if (active) setError(errorMessage(reason));}), 1500);
    return () => {active = false; clearInterval(timer);};
  }, [result]);
  function draft(payload: Submission) {
    if (!userId) return;
    setQuestionId(payload.question_id); setAnswer(payload.student_answer);
    try {writePractice(userId, {...readPractice(userId), draft: payload});} catch(reason) {setError(errorMessage(reason));}
  }
  async function send(payload: Submission) {
    if (!userId || sending.current) return;
    sending.current = true; setBusy(true); setError(""); setFields({});
    try {
      const submission = prepareSubmission(userId, payload);
      setPending(submission);
      if (submission.attemptId) {
        show(await apiRequest<Attempt>(`/practice/attempts/${submission.attemptId}`));
      } else {
        const item = await apiRequest<Attempt>("/practice/attempts", {method: "POST", headers: {"Idempotency-Key": submission.key}, body: JSON.stringify(submission.payload)});
        // Persist known identity before changing the URL/rendering the result.
        rememberAttempt(userId, submission, item.id); setPending({...submission, attemptId: item.id}); show(item);
      }
      await refresh();
    } catch(reason) {setError(errorMessage(reason)); setFields(reason instanceof ApiError ? reason.fields : {});}
    finally {sending.current = false; setBusy(false);}
  }
  function submit(event: FormEvent) {event.preventDefault(); void send({question_id: questionId, student_answer: answer});}
  async function resume() {if (pending) {draft(pending.payload); await send(pending.payload);}}
  function newAttempt() {
    if (!userId || busy) return;
    try {writePractice(userId, {draft: {question_id: questionId, student_answer: ""}}); setPending(undefined); setAnswer(""); setResult(null); setError(""); window.history.replaceState(null, "", "/learn");}
    catch(reason) {setError(errorMessage(reason));}
  }
  async function retry() {
    if (!result || sending.current) return;
    sending.current = true; setBusy(true); setError("");
    try {show(await apiRequest<Attempt>(`/practice/attempts/${result.id}/retry`, {method: "POST"})); await refresh();}
    catch(reason) {setError(errorMessage(reason));} finally {sending.current = false; setBusy(false);}
  }
  return <main className="container"><section className="card"><h1>Luyện tập</h1>
    {mode === "mock" && <p className="notice"><strong>Chế độ thử nghiệm — điểm và phản hồi giả lập.</strong><br/>Không dùng để đánh giá năng lực hoặc cập nhật tiến độ học thật.</p>}
    {!userId && !error && <p>Đang xác thực tài khoản…</p>}
    {pending && !pending.attemptId && <div className="notice" role="status">Có lần nộp chưa nhận được kết quả. Gửi lại sẽ dùng cùng key để lấy bài đã lưu.<button disabled={busy} onClick={resume}>Gửi lại lần nộp đang chờ</button></div>}
    <form onSubmit={submit} noValidate><label htmlFor="practice-question">Câu hỏi</label><select id="practice-question" value={questionId} onChange={e => draft({question_id: e.target.value, student_answer: answer})} disabled={busy || !userId}>{questions.map(q => <option key={q.question_id} value={q.question_id}>{q.question_id}</option>)}</select>
      <p>{questions.find(q => q.question_id === questionId)?.question}</p>
      <label htmlFor="practice-answer">Câu trả lời</label><textarea id="practice-answer" maxLength={16000} value={answer} onChange={e => draft({question_id: questionId, student_answer: e.target.value})} disabled={busy || !userId} aria-invalid={!!fields.student_answer} aria-describedby="answer-error"/><span className="error" id="answer-error">{fields.student_answer}</span>
      <button disabled={busy || !mode || !questionId || !answer.trim()}>{busy ? "Đang xử lý…" : "Gửi câu trả lời"}</button>
      <button type="button" className="secondary" disabled={busy || !userId} onClick={newAttempt}>Tạo lượt mới</button>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {result && <PracticeResult attempt={result} busy={busy} retry={retry}/>}
    <h2>Lịch sử của tôi</h2><ul>{history.map(a => <li key={a.id}><button className="secondary" onClick={() => show(a)}>{a.question_id} · {a.status}</button></li>)}</ul>
  </section></main>;
}
