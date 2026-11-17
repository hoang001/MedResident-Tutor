import {evidenceTitle} from "@/lib/practice-display";
import {Attempt} from "@/lib/practice-types";
import {PracticeImages} from "./PracticeImages";

const statuses = {correct: "Đúng", incorrect: "Sai", unanswered: "Chưa trả lời", unscored: "Không tính điểm"};

export function StructuredResult({attempt: a}: {attempt: Attempt}) {
  const result = a.structured_result!;
  return <article className="result-view" aria-live="polite" data-testid="practice-result">
    <h2>Kết quả luyện tập</h2>
    <p className="notice">Chấm theo đáp án biên soạn và tiêu chí từ nguồn, với nhận xét soạn trước. Chưa có xác nhận chuyên gia duyệt và không ghi nhận thành mức độ thành thạo.</p>
    <h3 data-testid="structured-score">Điểm: {result.total_score}/{result.max_score}</h3>
    {result.parts.map(p => <section className="structured-part-result" key={p.id} data-testid={`result-${p.id}`}>
      <h3>{p.label}</h3>
      <p><strong>{statuses[p.status]}</strong>{p.status !== "unscored" && ` · ${p.score}/${p.max_score} điểm`}</p>
      <p className="prose">Bạn đã nộp: {p.status === "unscored" ? p.answer || "Không nhập giải thích." : p.answer_label ?? "Chưa chọn đáp án."}</p>
      {p.status !== "unscored" && <>
        <p><strong>Đáp án đối chiếu:</strong> {p.correct_answer}</p>
        <p>{p.feedback}</p><p className="prose">{p.explanation}</p>
        {!!p.review_focus?.length && <p>Nội dung nên ôn: {p.review_focus.map(f => f.label).join("; ")}. Đối chiếu nguồn dưới đây; chưa ghi nhận thành năng lực thực hành.</p>}
        {a.evidence.filter(e => p.evidence_ids?.includes(e.source_unit_id)).map((e,index) => <details key={e.source_unit_id}>
          <summary>Nguồn đối chiếu · {evidenceTitle(e.title,index)}</summary>
          <blockquote className="prose">{e.content}</blockquote>
          <p>Trang {e.page_start}–{e.page_end} của gói evidence tổng hợp; không phải trang bài gốc.</p>
        </details>)}
      </>}
    </section>)}
    {a.clinical_exercise && a.clinical_solution && <section data-testid="clinical-solution">
      <h3>Ảnh đối chiếu và nguồn</h3><p className="notice">{a.clinical_solution.notice}</p>
      <PracticeImages exercise={a.clinical_exercise} solution={a.clinical_solution}/>
      <p className="prose">{a.clinical_solution.source.attribution_text}</p>
      <a href={a.clinical_solution.source.original_url} target="_blank" rel="noopener noreferrer">Xem nguồn gốc</a>{" · "}
      <a href={a.clinical_solution.source.license_url} target="_blank" rel="noopener noreferrer">{a.clinical_solution.source.license}</a>
    </section>}

  </article>;
}
