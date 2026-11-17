import type {Attempt,Question} from "@/lib/practice-types";
// Presentation only: the original evidence title/ID remains in the saved attempt.
export function evidenceTitle(title:string,index=0) {
  return !title.trim()||/^Evidence for\b/i.test(title)||/CLINICAL_DEMO|_SU\d|^[A-Z0-9_]{8,}$/u.test(title)
    ? `Trích đoạn đối chiếu ${index+1}` : title;
}
export function questionTitle(text:string) {
  const clean=text.replace(/^Theo [\s\S]{1,220}?\(\d{4}\),\s*/u,"").trim();
  const result=clean.charAt(0).toLocaleUpperCase("vi")+clean.slice(1);
  return result.length>135?result.slice(0,132).replace(/\s+\S*$/,"")+"…":result;
}
export function questionName(q:Question) {
  if(q.clinical_exercise){
    if(q.clinical_exercise.presentation.toLocaleLowerCase("vi").includes("cổ tay"))return q.structured_exercise?"Nhận diện chấn thương cổ tay":"Phân tích ca chấn thương cổ tay";
    return q.structured_exercise?"Đọc phim và định vị tổn thương":"Phân tích hình ảnh chấn thương";
  }
  return questionTitle(q.question);
}
export function attemptName(a:Attempt) {return questionName({question_id:a.question_id,question:a.question,clinical_exercise:a.clinical_exercise,structured_exercise:a.structured_result?{schema_version:"",revision_id:"",max_score:0,scoring_policy:"",parts:[]}:undefined});}
export function statusLabel(status:string) {return ({completed:"Hoàn tất",pending:"Đang chờ xử lý",medical_running:"Đang đánh giá",teaching_running:"Đang chuẩn bị phản hồi",medical_failed:"Chưa đánh giá được",teaching_failed:"Đã có điểm · thiếu phản hồi"} as Record<string,string>)[status]??"Đã lưu";}
export function statusTone(status:string):"success"|"warning"|"danger"|"info" {return status==="completed"?"success":status==="medical_failed"?"danger":status==="teaching_failed"?"warning":"info";}
export function executionLabel(a:Pick<Attempt,"execution_mode"|"provider_metadata">) {
  if(a.execution_mode==="structured")return "Theo đáp án biên soạn";
  if(a.execution_mode==="mock")return "Kết quả mô phỏng";
  const replay=a.execution_mode==="replay"||Object.values(a.provider_metadata??{}).some(v=>v&&typeof v==="object"&&"execution_mode" in v&&(v as {execution_mode:string}).execution_mode==="replay");
  return replay?"Phát lại kết quả đã lưu":"Đánh giá tự động";
}
export function formatDate(value?:string) {return value?new Intl.DateTimeFormat("vi-VN",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"}).format(new Date(value)):"";}
