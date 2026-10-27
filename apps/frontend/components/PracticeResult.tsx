import {Attempt} from "@/lib/practice-types";
function Points({title, points}: {title: string; points: string[]}) {
  return <section><h4>{title}</h4>{points.length ? <ul>{points.map((x,i) => <li key={i}>{x}</li>)}</ul> : <p>Không có mục được ghi nhận.</p>}</section>;
}
export function PracticeResult({attempt: a, busy, retry}: {attempt: Attempt; busy: boolean; retry: () => void}) {
  const med = a.medical_evaluation;
  const teaching = a.teaching_feedback;
  const running = ["pending", "medical_running", "teaching_running"].includes(a.status);
  const medicalState = med ? "Đã lưu" : a.status === "medical_failed" ? "Lỗi" : a.status === "medical_running" ? "Đang xử lý" : "Chờ xử lý";
  const teachingState = teaching ? "Đã lưu" : a.status === "teaching_failed" ? "Lỗi" : a.status === "teaching_running" ? "Đang xử lý" : "Chờ Medical";
  return <article aria-live="polite" data-testid="practice-result">
    <h2>Kết quả luyện tập</h2>
    {a.execution_mode === "mock" && <p className="notice"><strong>Chế độ thử nghiệm — điểm và phản hồi giả lập.</strong></p>}
    <p>{a.question}</p><p>Câu trả lời đã nộp: {a.student_answer}</p>
    <p data-testid="stage-status">Medical: {medicalState} · Teaching: {teachingState}</p>
    {med && <section><h3>Medical — {a.execution_mode === "mock" ? "điểm mô phỏng" : "điểm"}: {med.total_score}/{med.max_score}</h3>
      <Points title="Ý đúng" points={med.correct_points}/><Points title="Ý sai" points={med.incorrect_points}/><Points title="Ý thiếu" points={med.missing_points}/>
      <h4>Điểm theo tiêu chí</h4><ul>{med.rubric_scores.map(c => <li key={c.criterion_id}>{c.criterion}: {c.score}/{c.max_score}<p>{c.reason}</p></li>)}</ul>
      <p>{med.sufficient_evidence ? "Medical báo có đủ evidence cho phần đánh giá này." : "Medical báo chưa đủ evidence để kết luận đầy đủ."}</p>
    </section>}
    {teaching && <section><h3>Feedback Teaching</h3><p>{teaching.feedback_text}</p><Points title="Điểm mạnh" points={teaching.strengths}/>
      <ul>{teaching.corrections.map((x,i) => <li key={i}>{x.incorrect_point}: {x.feedback}</li>)}{teaching.missing_focus.map((x,i) => <li key={i}>{x.missing_point}: {x.feedback}</li>)}{teaching.learning_priority.map((x,i) => <li key={i}>{x.focus} ({x.priority}): {x.reason}</li>)}</ul>
      {teaching.follow_up_question && <p>Câu hỏi tiếp theo: {teaching.follow_up_question}</p>}
    </section>}
    {a.stage_error && <p className="error" role="alert">{a.stage_error.stage === "teaching" ? "Teaching lỗi. Medical đã lưu được giữ nguyên; bạn có thể thử lại feedback." : "Medical chưa hoàn tất; bạn có thể thử lại phần đánh giá."} Mã lỗi: {a.stage_error.code}</p>}
    {a.status !== "completed" && <><button disabled={busy} onClick={retry}>{med ? "Thử lại feedback" : "Thử lại Medical"}</button>{running && <p className="muted">Đang xử lý. Nếu tiến trình bị gián đoạn, thử lại sau khi lượt đang chạy hết thời gian chờ.</p>}</>}
    {med && <section><h3>Evidence được tham chiếu</h3>
      <p className="notice">Trạng thái chuyên gia duyệt: chưa xác minh. Đối chiếu tài liệu và validation kỹ thuật không thay thế chuyên gia duyệt.</p>
      {!med.evidence_refs.length && <p>Medical không tham chiếu evidence nào.</p>}
      {a.evidence.filter(e => med.evidence_refs.includes(e.source_unit_id)).map(e => {
        const p = a.provenance.find(x => x.source_unit_id === e.source_unit_id);
        return <section key={e.source_unit_id}><h4>{e.title}</h4><p>Nguồn tài liệu: {p?.document_metadata.catalog?.title ?? "Chưa xác minh tên tài liệu"}</p><p>Trang PDF {e.page_start}–{e.page_end}; trang in {p?.printed_page_start ?? "chưa xác minh"}{p?.printed_page_end && p.printed_page_end !== p.printed_page_start ? `–${p.printed_page_end}` : ""}.</p><blockquote>{e.content}</blockquote></section>;
      })}
      <details><summary>Chi tiết nguồn</summary><p>Question ID: {a.question_id}</p><p>Attempt ID: <span data-testid="attempt-id">{a.id}</span></p><p>Snapshot SHA-256: {a.snapshot_hash}</p>
        {a.provenance.map(p => <div key={p.source_unit_id}><p>SourceUnit: {p.source_unit_id}<br/>Source: {p.source_id}<br/>PDF SHA-256: {p.sha256}</p><p>Review trong metadata: {p.source_unit_metadata.expert_review?.status ?? "chưa xác minh"}</p></div>)}
        <details><summary>Metadata kỹ thuật đã lưu</summary><pre>{JSON.stringify({provenance: a.provenance, provider: a.provider_metadata}, null, 2)}</pre></details>
      </details>
    </section>}
  </article>;
}
