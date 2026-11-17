import {Attempt} from "@/lib/practice-types";
import {PracticeImages} from "@/components/PracticeImages";
import {StructuredResult} from "@/components/StructuredResult";
import {Badge} from "@/components/ui";
import {evidenceTitle,executionLabel,formatDate,statusLabel,statusTone} from "@/lib/practice-display";
function Points({title, points}: {title: string; points: string[]}) {
  return <section><h4>{title}</h4>{points.length ? <ul>{points.map((x,i) => <li key={i}>{x}</li>)}</ul> : <p>Không có mục được ghi nhận.</p>}</section>;
}
export function PracticeResult({attempt: a, busy, retry}: {attempt: Attempt; busy: boolean; retry: () => void}) {
  if (a.execution_mode === "structured" && a.structured_result) return <StructuredResult attempt={a}/>;
  const med = a.medical_evaluation;
  const teaching = a.teaching_feedback;
  const reviewActor = a.provenance.find(p => p.source_unit_metadata.source_review?.actor)?.source_unit_metadata.source_review?.actor;
  const running = ["pending", "medical_running", "teaching_running"].includes(a.status);
  const medicalState = med ? "Đã lưu" : a.status === "medical_failed" ? "Lỗi" : a.status === "medical_running" ? "Đang xử lý" : "Chờ xử lý";
  const teachingState = teaching ? "Đã lưu" : a.status === "teaching_failed" ? "Lỗi" : a.status === "teaching_running" ? "Đang xử lý" : "Chờ Medical";
  return <article className="result-view" aria-live="polite" data-testid="practice-result">
    <div className="result-summary"><div><h2>Kết quả bài làm</h2><div className="metadata-row"><Badge tone={statusTone(a.status)}>{statusLabel(a.status)}</Badge><span>{executionLabel(a)}</span>{a.created_at&&<time>{formatDate(a.created_at)}</time>}{a.question_version&&<span>Phiên bản {a.question_version}</span>}</div></div>{med&&<div className="result-score">{med.total_score}<small> / {med.max_score} điểm{a.execution_mode==="mock"?" mô phỏng":""}</small></div>}</div>
    {a.execution_mode === "mock" && <p className="notice"><strong>Chế độ thử nghiệm — điểm và phản hồi giả lập.</strong></p>}
    <details className="source-details"><summary>Đề và câu trả lời đã nộp</summary><p className="prose">{a.question}</p><p className="prose"><strong>Câu trả lời đã nộp:</strong><br/>{a.student_answer}</p></details>
    <p className="helper" data-testid="stage-status">Đánh giá nội dung: {medicalState} · Phản hồi hướng dẫn: {teachingState.replace("Medical","đánh giá")}</p>
    {med && <section className="result-section"><h3>Đánh giá nội dung</h3>
      <Points title="Ý đúng" points={med.correct_points}/><Points title="Ý sai" points={med.incorrect_points}/><Points title="Ý thiếu" points={med.missing_points}/>
      <h4>Điểm theo tiêu chí</h4><ul className="criterion-list">{med.rubric_scores.map(c => <li key={c.criterion_id}><div><strong>{c.criterion}</strong><p>{c.reason}</p></div><span className="criterion-score">{c.score}/{c.max_score}</span></li>)}</ul>
      <p className="helper">{med.sufficient_evidence ? "Bản đánh giá ghi nhận đủ căn cứ theo dữ liệu được cung cấp." : "Bản đánh giá ghi nhận chưa đủ căn cứ để kết luận đầy đủ."} Tổng điểm hợp lệ không bảo đảm mọi nhận xét đều đúng.</p>
    </section>}
    {teaching && <section className="result-section"><h3>Phản hồi hướng dẫn</h3><p className="prose">{teaching.feedback_text}</p><Points title="Điểm mạnh" points={teaching.strengths}/>
      <ul>{teaching.corrections.map((x,i) => <li key={i}>{x.incorrect_point}: {x.feedback}</li>)}{teaching.missing_focus.map((x,i) => <li key={i}>{x.missing_point}: {x.feedback}</li>)}{teaching.learning_priority.map((x,i) => <li key={i}>{x.focus} ({x.priority}): {x.reason}</li>)}</ul>
      {teaching.follow_up_question && <p>Câu hỏi tiếp theo: {teaching.follow_up_question}</p>}
    </section>}
    {a.clinical_solution && a.clinical_exercise && <section data-testid="clinical-solution"><h3>Đáp án biên soạn và ảnh đối chiếu</h3><p className="notice">{a.clinical_solution.notice}</p><ul>{a.clinical_solution.criteria.map(c => <li key={c.criterion_id}>{c.reference_answer_vi} · tối đa {c.max_score} điểm</li>)}</ul><PracticeImages exercise={a.clinical_exercise} solution={a.clinical_solution}/><p>{a.clinical_solution.source.attribution_text}</p><a href={a.clinical_solution.source.original_url} target="_blank" rel="noopener noreferrer">Xem nguồn gốc</a>{" · "}<a href={a.clinical_solution.source.license_url} target="_blank" rel="noopener noreferrer">{a.clinical_solution.source.license}</a></section>}
    {med && a.reference_answer && <section><h3>Đáp án tham khảo của phiên bản đã làm</h3><p className="prose">{a.reference_answer}</p><p>{reviewActor ? `Đối chiếu nguồn: ${reviewActor}.` : "Phát hành qua quản trị viên."} Chưa xác nhận chuyên gia y khoa duyệt.</p></section>}
    {a.stage_error && <p className="notice" role="alert">{a.stage_error.stage === "teaching" ? "Phản hồi hướng dẫn chưa sẵn sàng. Điểm và phần đánh giá nội dung đã lưu được giữ nguyên; bạn có thể thử lại phần phản hồi." : "Đánh giá chưa hoàn tất. Câu trả lời đã lưu vẫn được giữ lại; bạn có thể thử lại."}</p>}
    {a.status !== "completed" && <div className="actions"><button disabled={busy || running} onClick={retry}>{med ? "Thử lại phản hồi" : "Thử lại đánh giá"}</button>{running && <p className="muted">Đang xử lý. Kết quả sẽ tự cập nhật tại đây.</p>}</div>}
    {med && <section className="result-section"><h3>Tài liệu đối chiếu</h3>
      <p className="notice">Trạng thái chuyên gia duyệt: chưa xác minh. Đối chiếu tài liệu và validation kỹ thuật không thay thế chuyên gia duyệt.</p>
      {!med.evidence_refs.length && <p>Bản đánh giá không tham chiếu đoạn nguồn cụ thể.</p>}
      {a.evidence.filter(e => med.evidence_refs.includes(e.source_unit_id)).map((e,index) => {
        const p = a.provenance.find(x => x.source_unit_id === e.source_unit_id);
        return <details className="source-details" key={e.source_unit_id}><summary>{evidenceTitle(e.title,index)}</summary><p>Nguồn tài liệu: {p?.document_metadata.catalog?.title ?? p?.document_metadata.source?.title ?? "Chưa xác minh tên tài liệu"}</p>{a.clinical_solution ? <p>Trang {e.page_start}–{e.page_end} trong gói evidence do dự án tổng hợp; không phải số trang bài gốc. Locator XML/annotation được giữ trong chi tiết nguồn.</p> : <p>Trang PDF {e.page_start}–{e.page_end}; trang in {p?.printed_page_start ?? "chưa xác minh"}{p?.printed_page_end && p.printed_page_end !== p.printed_page_start ? `–${p.printed_page_end}` : ""}.</p>}<blockquote>{e.content}</blockquote></details>;
      })}

    </section>}
  </article>;
}
