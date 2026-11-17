import {StructuredExercise} from "@/lib/practice-types";

export function StructuredAnswers({exercise, answers, disabled, change}: {
  exercise: StructuredExercise; answers: Record<string, string | null>; disabled: boolean;
  change: (answers: Record<string, string | null>) => void;
}) {
  return <section aria-label="Trả lời bài có cấu trúc">
    <p className="notice">Tối đa {exercise.max_score} điểm. Mỗi phần được chấm độc lập theo lựa chọn đã chọn. Bỏ trống được ghi nhận là chưa trả lời, 0 điểm; tổng điểm tối đa không đổi. Giải thích ngắn chưa tính điểm.</p>
    {exercise.parts.map(p => p.kind === "short_explanation" ? <div key={p.id}>
      <label htmlFor={`structured-${p.id}`}>{p.label}</label>
      <textarea id={`structured-${p.id}`} maxLength={p.max_length} value={answers[p.id] ?? ""} disabled={disabled} onChange={e => change({...answers, [p.id]: e.target.value})}/>
      <p className="muted">{(answers[p.id] ?? "").length}/{p.max_length} ký tự · chỉ lưu để xem lại.</p>
    </div> : <fieldset key={p.id} disabled={disabled} className="structured-part">
      <legend>{p.label} · {p.max_score} điểm</legend>
      {p.kind === "grid_location" && <p>Chỉ dùng ảnh số 1. Hàng từ trên xuống, cột từ trái sang; bắt đầu từ 1. Phần vị trí vẫn được chấm độc lập với phần nhận diện gãy.</p>}
      <div className={p.kind === "grid_location" ? "structured-grid" : "structured-choices"}>
        {p.options.map(option => <label className="structured-option" key={option.id}>
          <input type="radio" name={p.id} value={option.id} checked={answers[p.id] === option.id} onChange={() => change({...answers, [p.id]: option.id})}/>
          <span>{option.label}</span>
        </label>)}
      </div>
      <button type="button" className="secondary" disabled={disabled || !answers[p.id]} onClick={() => change({...answers, [p.id]: null})}>Bỏ lựa chọn phần này</button>
    </fieldset>)}
  </section>;
}
