"""Offline review artifact: no network dependencies, credentials or student data."""
import html
import json
from pathlib import Path
from urllib.parse import quote

from .common import ROOT, RUN, read
from .content import TOPICS

def h(value): return html.escape(str(value),quote=True)

def main():
    questions=read('authored-questions.json')
    units={s['source_unit_id']:s for s in read('source-units.json')}
    sources=read('sources-verified.json')
    records=[]
    for q in questions:
        rubric=[]
        for c in q['criteria']:
            evidence=[]
            for sid in c['source_unit_ids']:
                u=units[sid]; s=sources[u['source_id']]
                path=quote('../../../'+s['pdf_path'],safe='/')+'#page='+str(u['pdf_page_start'])
                evidence.append(f'<details><summary>{h(s["title"])} ({s["year"]}) · PDF {u["pdf_page_start"]}</summary><p><a href="{path}">Mở bản PDF gốc tại trang này</a></p><p>{h(u["source_id"])} · {h(sid)}</p><blockquote>{h(u["content"])}</blockquote><p class="meta">Locator: {h(u["locator"])}<br>SHA-256 PDF: {h(s["sha256"])}<br>SHA-256 đoạn trích: {h(u["content_sha256"])}</p></details>')
            rubric.append(f'<li><p><strong>{h(c["criterion_id"])} · {c["max_score"]:g} điểm</strong><br>{h(c["description"])}</p>{"".join(evidence)}</li>')
        records.append(f'<details class="question" data-topic="{h(q["topic"])}" data-search="{h(q["question"]+" "+q["question_id"])}"><summary>{h(TOPICS[q["topic"]])} · {h(q["objective"])}<span>{h(q["question"])}</span></summary><div class="body"><p class="meta">{h(q["question_id"])} · {h(q["source_type"])} · Đã phát hành demo</p><h3>Đáp án tham khảo</h3><p class="answer">{h(q["reference_answer"])}</p><h3>Rubric và bằng chứng · Tổng {q["max_score"]:g} điểm</h3><p>{h(q["criteria"][0]["scoring_rule"])}</p><ol>{"".join(rubric)}</ol><p>Đối chiếu nguồn: Codex · 16/11/2026. Chưa được giảng viên hoặc bác sĩ phê duyệt.</p><a href="http://localhost:3000/learn?question={h(q["question_id"])}">Mở câu này trên web</a></div></details>')
    statuses=read('qa18-disposition.json')
    arows=''.join(f'<tr><td>{h(x["id"])}</td><td>{h(x["status"])}</td><td>{h(x["reason"])}</td></tr>' for x in statuses)
    topics=''.join(f'<option value="{h(k)}">{h(v)}</option>' for k,v in TOPICS.items())
    output='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Rà soát ngân hàng câu hỏi · MedResident Tutor</title>
<style>
:root{color-scheme:light;font-family:Arial,sans-serif;color:#18312d;background:#f7faf9;line-height:1.6;accent-color:#116c60}*{box-sizing:border-box}body{margin:0}main{max-width:1080px;margin:auto;padding:32px 20px 72px}h1{font-size:2rem;line-height:1.25}h2{margin-top:2rem}h3{font-size:1.1rem;margin:1.8rem 0 .5rem}p{max-width:75ch}a{color:#0b554b;text-underline-offset:3px}input,select,button{font:inherit;border:1px solid #cbdad7;border-radius:7px;min-height:44px;padding:8px 12px;background:#fff;color:inherit;caret-color:#116c60}input{flex:2;min-width:200px}select{flex:1;min-width:200px}button{cursor:pointer}button:hover{background:#e8f4f1}*:focus-visible{outline:3px solid #116c60;outline-offset:3px}::selection{background:#e8f4f1;color:#18312d}.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;padding:16px 0;border-block:1px solid #cbdad7}.filters label{display:flex;flex:1;flex-direction:column;gap:6px}.question{border-bottom:1px solid #cbdad7;background:white}.question>summary{padding:20px;cursor:pointer;font-weight:bold}.question>summary span{display:block;font-weight:normal;margin-top:8px;max-width:75ch}.body{padding:0 24px 24px}.meta{font-size:.85rem;color:#58706b;overflow-wrap:anywhere}.answer,blockquote{white-space:pre-wrap;max-width:75ch}blockquote{margin:12px 0;padding:12px;background:#e8f4f1;border:1px solid #cbdad7}li{padding:4px 0 16px;overflow-wrap:anywhere}li details{margin:8px 0}li summary{cursor:pointer;color:#0b554b}table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #cbdad7;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}[hidden]{display:none!important}@media(max-width:560px){main{padding:20px 16px}h1{font-size:1.6rem}.body{padding:0 16px 20px}.question>summary{padding:16px}ol{padding-left:20px}.filters label{flex-basis:100%}}
</style><main><h1>Rà soát ngân hàng câu hỏi</h1><p>Đã kiểm tra qua student API: <strong>100 câu khả dụng</strong>, gồm 5 câu giữ nguyên và 95 câu bổ sung thuộc 10 chủ đề. Có 2 bản nháp gốc chưa phát hành.</p><p>Trang này trình bày đáp án nội bộ để rà soát. Nội dung do Codex đối chiếu tài liệu, chưa phải phê duyệt chuyên môn. Chấm tự luận trên web hiện là giả lập có nhãn; không xác nhận độ chính xác model.</p><p>12 câu từ tập QA cũ, 5 câu gốc cuối chương và 78 câu biên soạn từ tài liệu. Không nhập câu theo mẫu KG. Hai file quy trình Bộ Y tế là một bản trùng byte, Quyết định 5728/QĐ-BYT năm 2017; không gọi là hướng dẫn hiện hành.</p><p><a href="http://localhost:3000/learn">Mở ngân hàng trên web</a> · <a href="statistics.json">Số liệu JSON</a> · <a href="questions.csv">Danh sách CSV</a> · <a href="book-candidates-disposition.json">Đối chiếu 126 câu trong KG</a></p><h2>95 câu đã bổ sung</h2><div class="filters"><label>Tìm nội dung hoặc mã câu<input id="search" type="search" placeholder="Ví dụ: chèn ép khoang"></label><label>Chủ đề<select id="topic"><option value="">Tất cả chủ đề</option>'''+topics+'''</select></label><button id="reset">Xóa bộ lọc</button></div><p id="count" role="status">95 câu</p>'''+''.join(records)+'''<h2>Xử lý tập 18 QA ban đầu</h2><div class="table-wrap"><table><thead><tr><th>Mã câu</th><th>Trạng thái</th><th>Lý do</th></tr></thead><tbody>'''+arows+'''</tbody></table></div><h2>Nội dung còn chờ</h2><p>Hai bản nháp trong DB giữ nguyên. Ngoài DB, 2 QA cần biên tập chuyên môn; 3 QA loại khỏi batch do trùng; 121 câu gốc KG chưa được hoàn thiện toàn bộ phạm vi. Các ca staging được kiểm kê riêng, giữ nguyên ảnh và bản dịch, không tự gắn nhãn đã duyệt.</p><p><a href="review-queue.json">Hàng chờ rà soát</a> · <a href="clinical-staging-disposition.json">Kiểm kê ca bệnh</a> · <a href="crosswalk.json">ID gốc và revision trong DB</a> · <a href="release-manifest.json">Manifest phát hành</a></p></main><script>
const norm=s=>s.toLocaleLowerCase('vi').replaceAll('đ','d').normalize('NFD').replace(/[\u0300-\u036f]/g,'');const rows=[...document.querySelectorAll('.question')];function filter(){const needle=norm(document.querySelector('#search').value);const topic=document.querySelector('#topic').value;let n=0;rows.forEach(row=>{const show=(!topic||row.dataset.topic===topic)&&norm(row.dataset.search).includes(needle);row.hidden=!show;if(show)n++});document.querySelector('#count').textContent=n?`${n} câu phù hợp`:'Không tìm thấy. Thử từ khóa khác hoặc xóa bộ lọc.'}document.querySelector('#search').addEventListener('input',filter);document.querySelector('#topic').addEventListener('change',filter);document.querySelector('#reset').addEventListener('click',()=>{document.querySelector('#search').value='';document.querySelector('#topic').value='';filter()});
</script></html>'''
    (RUN/'review.html').write_text(output,encoding='utf-8')
    (RUN/'README.md').write_text('''# Ngân hàng demo — 16/11/2026

Đã phát hành 100 câu khả dụng qua student API (102 tổng trong PostgreSQL, 2 draft). 95 câu bổ sung có đáp án, rubric, bằng chứng và approved grading package. 5 câu cũ và toàn bộ dữ liệu người học được giữ nguyên.

Mở http://localhost:3000/learn, đăng nhập bằng tài khoản hiện có, lọc chủ đề hoặc tìm mã `QB26_` / `ORTHO_B21CN1_Q_`. Dùng Trang trước/Trang sau để xem danh sách. Các câu mới vẫn hiển thị dù chưa gán học phần chính thức. Admin xem ở http://localhost:3000/admin/questions.

Mở review.html để xem đề → đáp án → rubric → đoạn nguồn, trang PDF, hash. Backup chứa dữ liệu riêng tư ở backup/postgres.dump; không chia sẻ thư mục backup.

12/17 ID QA chưa nhập đã hoàn thiện và phát hành. 5 giữ ngoài đợt: Q0004/Q0006 cần biên tập nội dung xử trí; Q0016/Q0017/Q0018 trùng tiêu chí. 5/126 câu gốc sách đã hoàn thiện, 121 câu còn là candidate; 78 câu khác được ghi rõ biên soạn từ tài liệu. Không nhập 5.658 template.

Nguồn: hai sách 2006/2021 và một tài liệu quy trình Bộ Y tế 2017 (hai tên file local trùng SHA). Không tải thêm tài liệu lâm sàng. Tra trang KCB chính thức chỉ để xác nhận quyết định, tên, năm; không tuyên bố hiệu lực hiện hành. Các ca ảnh staging được kiểm kê nhưng không phát hành thêm vì chưa tái rà soát riêng từng ảnh/annotation/giấy phép trong đợt này; các ca demo cũ giữ nguyên.

Người đối chiếu: Codex. Không phải cô giáo, bác sĩ hay hội đồng y khoa. Chỉ phát hành demo. Không train, không chạy benchmark, không gọi inference (0 attempt); provider web vẫn mock. Ngân hàng dữ liệu sẵn sàng không đồng nghĩa model đã chấm chính xác các câu này.

Kiểm tra nhập lại: `python -m local_model_testing.bank_expansion.import_bank` (95 unchanged, 0 created). Kiểm tra chỉ đọc: `python -m local_model_testing.bank_expansion.verify`.

Đã giữ FE/BE/PostgreSQL/Neo4j để mở kiểm tra. Không commit/push Git.
''',encoding='utf-8')
    print('review.html written:',len(questions),'questions')

if __name__=='__main__': main()
