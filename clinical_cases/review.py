"""Offline review with original images and source excerpts; no application integration."""
import html
import json
from urllib.parse import quote

from .build import FIELDS, validate
from .contracts import SCHEMAS
from .io import DATA, read, write

FIELD_NAMES = {"presentation": "Bệnh cảnh nguồn nêu", "investigations": "Thăm dò và phát hiện",
               "reference_diagnosis": "Chẩn đoán được tác giả nêu", "management": "Xử trí thực tế trong ca", "outcome": "Diễn biến / kết quả nguồn nêu"}


def esc(value):
    return html.escape(str(value), quote=True)


def link(url, title):
    if not url or not str(url).startswith("https://"):
        return esc(title) + " (chưa xác minh)"
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a>'


def figure(image):
    url = "../" + quote(image["local_path"], safe="/")
    caption = image["caption"] or ("Ảnh nguồn " + image["image_id"])
    flags = "Chưa duyệt chuyên môn hoặc quyền riêng tư. Chú thích/nhãn có thể tiết lộ chẩn đoán."
    return (f'<figure><a href="{url}"><img src="{url}" alt="{esc(caption)}" loading="lazy"></a>'
            f'<figcaption>{esc(caption)}<small>{esc(image["modality"])} · {esc(image["view"] or "Góc chụp: chưa xác định từ nguồn")}<br>{flags}</small></figcaption></figure>')


def build_review():
    report = validate()
    cases = read(DATA / "processed/clinical-cases.json")
    case_images = read(DATA / "processed/case-images.json")
    dataset_images = read(DATA / "processed/dataset-images.json")
    images = {i["image_id"]: i for i in case_images + dataset_images}
    studies = read(DATA / "processed/imaging-studies.json")
    sources = read(DATA / "catalog/case-sources.json") + [read(DATA / "catalog/graz-source.json")]
    source_index = {s["source_id"]: s for s in sources}
    survey = read(DATA / "catalog/source-survey.json")
    candidates = read(DATA / "catalog/candidates.json")
    privacy_path = DATA / "catalog/manual-visual-review.json"
    visual = read(privacy_path) if privacy_path.exists() else {"notes": "Chưa rà soát hình ảnh thủ công"}
    write(DATA / "catalog/sources.json", sources)
    for name, definition in SCHEMAS.items():
        write(DATA / "catalog/schemas" / (name + ".schema.json"), definition)
    selected = {c["article_group_id"] for c in cases}
    for candidate in candidates:
        candidate["collection_status"] = "sample_downloaded_source_checked_not_expert_verified" if candidate["pmcid"] in selected else "metadata_only_rights_and_full_case_not_yet_cleared"
        if candidate["pmcid"] == "PMC13460339":
            candidate["scope_review"] = "outside_first_sample_scope_cardiothoracic_bypass; do_not_select"
        elif candidate["pmcid"] == "PMC13499707":
            candidate["scope_review"] = "comparative_case_report_multiple_patients_requires_separate_case_grouping"
        else:
            candidate["scope_review"] = "title_screened_candidate_not_confirmed_course_material"
    write(DATA / "catalog/candidates-reviewed.json", candidates)
    parts = ['<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta name="robots" content="noindex,nofollow"><title>Review ca bệnh và X-quang — MedResident Tutor</title>',
             '<style>body{font:17px/1.65 system-ui,sans-serif;color:#18312d;background:#f7faf9;margin:0}main{max-width:1120px;margin:auto;padding:24px}a{color:#075c50;text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid #9f5100;outline-offset:4px}h1{font-size:2rem;line-height:1.25}h2{margin-top:3rem}h3{line-height:1.35}nav{display:flex;flex-wrap:wrap;gap:16px;margin:24px 0}article{padding:20px 0;border-top:2px solid #cbdad7}.note{background:#fff3d9;padding:16px;border-left:4px solid #9f5100}.figures{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}figure{margin:0;background:white;padding:12px;border:1px solid #cbdad7}img{width:100%;height:360px;object-fit:contain;background:#111}small{display:block;color:#58706b}details{margin:14px 0}summary{cursor:pointer;padding:8px 0;font-weight:600}p{max-width:85ch;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:12px;font-size:.85rem}table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{padding:10px;border:1px solid #cbdad7;text-align:left;vertical-align:top;overflow-wrap:anywhere}caption{text-align:left;font-weight:bold}.table{overflow:auto}footer{margin-top:40px} @media(max-width:650px){main{padding:16px}.figures{grid-template-columns:1fr}img{height:300px}h1{font-size:1.6rem}}@media print{details>*{display:block!important}nav{display:none}article{break-before:page}img{height:250px}}</style>',
             '<main id="main"><h1>Ca bệnh công bố và ảnh X-quang có nhãn</h1>',
             '<p>Bộ kiểm mẫu thủ công · 09/11/2026 · Chỉ lưu cục bộ, chưa đưa vào KG, ngân hàng đề hoặc luồng chấm.</p>',
             f'<p><strong>{len(cases)} ca bệnh · {len(case_images)} hình bài báo · {len(studies)} lượt chụp / {len(dataset_images)} ảnh dataset · 0 bài tập biên soạn · 0 lần gọi LLM.</strong></p>',
             '<div class="note">Chẩn đoán và xử trí dưới đây là nội dung tác giả báo cáo cho từng người bệnh. Chưa có đáp án sư phạm/rubric, chưa chuyên gia duyệt. Nhiều ca là biến thể hiếm. Ảnh gốc và montage được giữ nguyên; một số ảnh còn chữ, ngày chụp hoặc chú thích tiết lộ tổn thương nên cần kiểm tra trước khi xuất bản.</div>',
             '<nav aria-label="Nội dung review"><a href="#cases">10 ca bệnh</a><a href="#dataset">20 lượt chụp</a><a href="#sources">Nguồn và quyền</a><a href="#candidates">30 ứng viên</a><a href="../processed/clinical-cases.json">JSON ca bệnh</a><a href="review.md">Báo cáo Markdown</a></nav>',
             '<h2 id="cases">A. Ca bệnh đã công bố</h2><p>Nội dung tiếng Anh được trích đúng nguồn; chưa tạo bản dịch. Mỗi phần có locator/đoạn hỗ trợ trong JSON và mục căn cứ.</p>']
    for case in cases:
        source = source_index[case["source_refs"]["presentation"][0]["source_id"]]
        parts += [f'<article id="{esc(case["case_id"])}"><h3>{esc(case["title"])}</h3>',
                  f'<small>{esc(case["case_id"])} · {esc(case["specialty"])} · {esc(case["patient_in_article"])}</small>',
                  f'<p class="note">{esc(case["source_variant_note"])}</p>']
        for field in FIELDS:
            content = esc(case[field] or "Nguồn chưa cung cấp / chưa chọn được trích dẫn.").replace("\n\n", "</p><p>")
            parts.append(f'<details{" open" if field == "presentation" else ""}><summary>{FIELD_NAMES[field]}</summary><p lang="en">{content}</p></details>')
        parts += ['<div class="figures">', *[figure(images[i]) for i in case["image_ids"]], '</div>',
                  '<p>' + link(source["original_url"], "Bài gốc PMC") + ' · ' + link(source["publisher_url"], "Nhà xuất bản / DOI") + ' · ' + link(source["license_url"], source["license"]) + '</p>',
                  '<small>' + esc(source["attribution_text"]) + '</small>',
                  '<details><summary>Căn cứ theo trường và kiểm tra nguồn</summary><pre>' + esc(json.dumps(case["source_refs"], ensure_ascii=False, indent=2)) + '</pre></details></article>']
    parts += ['<h2 id="dataset">B. GRAZPEDWRI-DX v2 — ảnh có nhãn</h2>',
              '<p>20 lượt chụp của 20 người bệnh khác nhau, giữ toàn bộ góc chụp có trong từng lượt đã chọn. Đây là mẫu theo ID tăng dần, chưa cân bằng hay đại diện quần thể. Giữ nhãn gốc theo ảnh; không chuyển nhãn thành đáp án chẩn đoán hoặc xử trí. Ảnh PNG gốc 16-bit được trình duyệt hiển thị trực tiếp, không sửa pixel.</p>',
              '<p>Giữ mã projection gốc; chưa ánh xạ mã thành tên góc chụp. Annotation VOC/YOLO giữ nguyên. Gốc tọa độ VOC không bị tự dịch 0/1 pixel.</p>']
    parts.append('<small>' + esc(source_index['SRC_DATASET_GRAZPEDWRI_DX_V2']['attribution_text']) + '</small>')
    for study in studies:
        parts += [f'<article id="{esc(study["study_id"])}"><h3>{esc(study["study_id"])}</h3>',
                  '<div class="figures">', *[figure(images[i]) for i in study["image_ids"]], '</div>',
                  '<details><summary>Nhãn gốc và nhóm người bệnh/lượt chụp</summary><pre>' + esc(json.dumps(study, ensure_ascii=False, indent=2)) + '</pre></details></article>']
    parts += ['<h2 id="sources">Nguồn, quyền sử dụng và phần giữ ngoài</h2>', '<div class="table"><table><thead><tr><th>Nguồn</th><th>Truy cập / giấy phép</th><th>Giới hạn</th></tr></thead><tbody>']
    for source in survey["sources"]:
        extra = ''.join('<p>' + link(item['url'], item['topic']) + ': ' + esc(item['status']) + '</p>' for item in source.get('links', []))
        parts.append('<tr><td>' + link(source["original_url"], source["title"]) + extra + '</td><td>' + esc(source["access_status"]) + '<br>' + link(source["license_url"], source["license"] or "Chưa rõ giấy phép") + '</td><td>' + esc(source["limits"]) + '<br>' + link(source["terms_url"], "Điều khoản") + '</td></tr>')
    parts += ['</tbody></table></div>', '<details><summary>Rà soát ảnh thủ công và các trường hợp giữ lại để kiểm tra</summary><pre>' + esc(json.dumps(visual, ensure_ascii=False, indent=2)) + '</pre></details>',
              '<h2 id="candidates">Danh mục ứng viên — metadata, chưa mặc định được phép tái sử dụng</h2>', '<div class="table"><table><thead><tr><th>Nhóm</th><th>Bài / nguồn</th><th>Trạng thái</th></tr></thead><tbody>']
    for c in candidates:
        parts.append('<tr><td>' + esc(c["specialty"]) + '</td><td>' + link(c["original_url"], c["title"]) + '</td><td>' + esc(c["collection_status"]) + '<br>' + esc(c["scope_review"]) + '</td></tr>')
    parts += ['</tbody></table></div><footer><p>Giấy phép rõ ràng là điều kiện thu thập, không phải xác nhận độ đúng y khoa. Kiểm tra tự động và rà soát nguồn không được tính là chuyên gia duyệt.</p></footer></main></html>']
    folder = DATA / "review"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text("\n".join(parts), encoding="utf-8")
    md = ["# Bộ mẫu ca bệnh / ảnh chấn thương", "", "Ngày 09/11/2026. Thu thập thủ công; không gọi LLM, không import DB và không thay đổi luồng chấm.", "",
          "## Số lượng thực tế", "", "```json", json.dumps(report, ensure_ascii=False, indent=2), "```", "",
          "## Nguồn và quyền sử dụng", ""]
    for source in survey["sources"]:
        md += [f"- [{source['title']}]({source['original_url']}): {source['access_status']} Giấy phép: {source['license']}. [Điều khoản]({source['terms_url']}). {source['limits']}"]
    md += ["", "## Các ca mẫu", "", "| ID | Nhóm | Ca công bố | Hình |", "| --- | --- | --- | --- |"]
    for case in cases:
        md.append(f"| {case['case_id']} | {case['specialty']} | {case['title']} | {len(case['image_ids'])} |")
    md += ["", "## Chưa hoàn thành / giữ ngoài", "",
           "- Chưa biên soạn câu hỏi, đáp án sư phạm hoặc rubric; authored-exercises.json là mảng rỗng.",
           "- Các ca có biến thể/hiếm không được xem là ví dụ điển hình. Chưa có duyệt chuyên môn của giảng viên.",
           "- Còn cần rà soát quyền riêng tư trên chữ nhúng trong ảnh và caption tiết lộ chẩn đoán; không tự chỉnh/xóa chữ.",
           "- Các ứng viên ngoài 10 mẫu mới có metadata; query lọc CC BY không thay việc kiểm từng bài và credit hình.",
           "- MURA: điều khoản phát hành tại Redivis chưa xác minh; Radiopaedia: 402; Orthobullets/AO: chưa có quyền đưa ảnh vào app; MIMIC: hạn chế truy cập, chưa tải.",
           "- Chưa chia train/test và không chạm locked test. Giữ patient/study grouping cho lần chia tập sau.",
           "- Mẫu GRAZ gồm trẻ em và chỉ vùng cổ tay; không thay bộ ca người lớn hoặc hồ sơ xử trí.",
           "- Toàn bộ ảnh và XML gốc giữ nguyên. Ảnh ghép nhiều panel chưa tách. Chưa tạo bản dịch.",
           "", "## Mở review và chạy tiếp", "", "```powershell", "Start-Process .\\data\\clinical-cases\\review\\index.html", "python -m clinical_cases validate", "python -m clinical_cases collect", "```", "",
           "Lệnh collect tiếp tục từ cache; chỉ áp dụng lựa chọn thủ công đã có, không tự chọn thêm ca hay sinh câu hỏi.", ""]
    (folder / "review.md").write_text("\n".join(md), encoding="utf-8")
    return report
