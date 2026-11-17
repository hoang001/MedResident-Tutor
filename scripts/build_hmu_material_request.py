"""Build a standalone lecturer handout using official HMU course links only."""

import argparse
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/knowledge-extraction/hmu-public-20261104"
SCOPE = ROOT / "apps/backend/app/modules/knowledge/residency_scope.json"


def hmu_link(url: str, label: str, *, show_url: bool = False) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not (host == "hmu.edu.vn" or host.endswith(".hmu.edu.vn"))
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Every source link must be an official HMU HTTPS URL")
    link = (
        f'<a href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(label)}</a>'
    )
    if show_url:
        link += f'<span class="url">{html.escape(url)}</span>'
    return link


def render_material_review(graph: dict, scope: dict) -> str:
    courses = {
        n["properties"]["course_code"]: n["properties"]
        for n in graph["nodes"]
        if n["type"] == "Course"
    }
    sources = [n["properties"] for n in graph["nodes"] if n["type"] == "CurriculumSource"]
    programme = next(s for s in sources if "categoryid=1944" in s.get("url", ""))
    outcomes = next(s for s in sources if "2.Chuandaura_BSNT_Ngoai.pdf" in s.get("url", ""))
    year_two = next(s for s in sources if "categoryid=2420" in s.get("url", ""))
    year_three = next(s for s in sources if "categoryid=2421" in s.get("url", ""))
    expected = [c["course_code"] for g in scope["groups"] for c in g["courses"]]
    if len(expected) != 12 or len(set(expected)) != 12 or not set(expected) <= courses.keys():
        raise ValueError("The lecturer handout requires the twelve scoped courses")
    chunks = [
        """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Danh mục xin và xác nhận tài liệu học tập chính thức cho bác sĩ nội trú Chấn thương chỉnh hình, Round 2 và Round 3.">
<title>Đề nghị cung cấp tài liệu học tập BSNT CTCH — HMU</title>
<style>
:root{color-scheme:light;--ink:#203a38;--green:#176b5e;--line:#d1dfda;--soft:#edf5f1}
*{box-sizing:border-box}body{margin:0;background:#f4f7f5;color:var(--ink);font:16px/1.65 system-ui,Arial,sans-serif}
main{max-width:1120px;margin:32px auto;padding:0 24px 40px}header{padding:12px 0 22px}
h1{font-size:clamp(1.7rem,4vw,2.4rem);line-height:1.2;margin:8px 0 16px}h2{font-size:1.3rem;margin:0 0 12px}
h3{font-size:1.05rem;margin:18px 0 8px}.eyebrow{color:var(--green);font-size:.8rem;font-weight:700;letter-spacing:.07em}
.muted{color:#526b63}.notice,blockquote{padding:16px 20px;border-left:4px solid var(--green);background:var(--soft);border-radius:6px;margin:18px 0}
.card{padding:24px;background:white;border:1px solid var(--line);border-radius:10px;margin:20px 0}
.facts{display:flex;flex-wrap:wrap;gap:12px 30px}.facts strong{display:block;font-size:1.3rem;color:var(--green)}
a{color:#075ba0;text-underline-offset:3px}a:focus-visible,button:focus-visible{outline:3px solid #379f83;outline-offset:4px}
table{border-collapse:collapse;width:100%;font-size:.94rem}caption{text-align:left;padding:0 0 12px;color:#526b63}
th,td{border:1px solid var(--line);padding:11px 12px;vertical-align:top;text-align:left}th{background:var(--soft)}
.code{white-space:nowrap;font-weight:700}.credit{white-space:nowrap}.url{display:block;font-size:.73rem;overflow-wrap:anywhere;color:#526b63;margin-top:5px}
.tag{display:block;font-size:.78rem;color:#785b18;margin-top:5px}.source-links{display:grid;gap:12px;margin:14px 0}
li{margin:8px 0}blockquote{margin:0;white-space:pre-line}.table-wrap{overflow-x:auto}
button{font:inherit;padding:9px 16px;border:0;border-radius:6px;background:var(--green);color:white;cursor:pointer}
footer{font-size:.85rem;color:#526b63;margin-top:26px}.teacher-note{border-top:1px dashed var(--line);padding-top:14px;margin-top:16px}
@media(max-width:680px){main{padding:0 14px 24px;margin-top:18px}.card{padding:16px}th,td{padding:8px}table{min-width:640px}}
@page{size:A4;margin:14mm}
@media print{body{background:white;color:#111;font-size:10pt;line-height:1.45}main{max-width:none;margin:0;padding:0}.card{padding:12px 0;border:0;border-top:1px solid #aaa;border-radius:0;margin:14px 0}.no-print{display:none!important}h1{font-size:21pt}h2{font-size:14pt}h2,h3{break-after:avoid}table{font-size:9pt;min-width:0;table-layout:fixed}th,td{padding:7px;overflow-wrap:anywhere}th:first-child{width:14%}th:nth-child(2){width:35%}th:nth-child(3){width:12%}th:last-child{width:39%}thead{display:table-header-group}tr{break-inside:avoid}.table-wrap{overflow:visible}.notice,blockquote{background:#f4f4f4}.url{font-size:7.3pt}.facts strong{font-size:14pt}a{color:#134b6f}footer{font-size:8pt}}
</style>
</head>
<body><main>
<header>
<div class="eyebrow">BÁC SĨ NỘI TRÚ · CHẤN THƯƠNG CHỈNH HÌNH · ĐẠI HỌC Y HÀ NỘI</div>
<h1>Đề nghị cung cấp tài liệu học tập chính thức</h1>
<p class="muted">Bản tổng hợp gửi giảng viên để xin và xác nhận tài liệu đang sử dụng. Cập nhật ngày 05/11/2026.</p>
<p>Đối tượng của web là bác sĩ nội trú đã học giai đoạn nền tảng. Phạm vi cần phát triển bài học tập trung vào <strong>Round 2 và Round 3</strong> trong khung chương trình đã được cung cấp.</p>
<div class="facts"><div><strong>4 môn bắt buộc</strong>Round 2 · 24 tín chỉ</div><div><strong>Chọn 4/8 môn</strong>Round 3 · 16 tín chỉ</div><div><strong>40 tín chỉ</strong>4 lý thuyết · 36 thực hành</div></div>
<div class="notice"><strong>Các liên kết dưới đây là trang học phần trên LMS HMU.</strong> Truy cập bài học cần đăng nhập bằng tài khoản có quyền của trường; đây chưa phải liên kết tải giáo trình. Tài liệu bên trong và phiên bản áp dụng cần cô xác nhận.</div>
<button class="no-print" type="button" onclick="window.print()">In / lưu thành PDF</button>
</header>
<section class="card" aria-labelledby="materials-title">
<h2 id="materials-title">1. Những tài liệu cần xin cho mỗi học phần</h2>
<p>Kính nhờ cô cho em xin các tài liệu hiện có và đang được sử dụng, theo mức độ sẵn có:</p>
<ol>
<li><strong>Đề cương chi tiết:</strong> mục tiêu, chuẩn đầu ra của học phần, danh sách bài/chủ đề, thứ tự học và phân bố lý thuyết–thực hành.</li>
<li><strong>Giáo trình hoặc chương sách được chỉ định:</strong> tên sách, tác giả/chủ biên, phiên bản hoặc năm xuất bản; chương/trang bắt buộc và phần đọc thêm.</li>
<li><strong>Bài giảng và tài liệu thực hành:</strong> slide, tài liệu phát cho học viên, video giảng dạy, hướng dẫn kỹ năng hoặc bảng kiểm thực hành nếu có.</li>
<li><strong>Yêu cầu đánh giá:</strong> hình thức kiểm tra, câu hỏi ôn tập, đáp án hoặc tiêu chí/bảng kiểm đánh giá nếu có sẵn và có thể chia sẻ.</li>
</ol>
<p class="muted">Em xin tài liệu giảng dạy chính thức hiện có; không cần cô soạn thêm. Nếu đã nằm trên LMS, cô có thể chỉ giúp đúng mục hoặc gửi file/link có quyền xem phù hợp.</p>
</section>""",
    ]
    for index, group in enumerate(scope["groups"], start=2):
        round_number = group["round"]
        rule = (
            "Học toàn bộ 4 học phần bắt buộc, tổng 24 tín chỉ (4 LT, 20 TH)."
            if round_number == 2
            else "Chọn 4 trong 8 học phần, tổng 16 tín chỉ thực hành. Danh sách 8 môn là phạm vi để xin tài liệu, không yêu cầu mỗi học viên học cả 8 môn."
        )
        chunks.extend([
            f'<section class="card" aria-labelledby="round-{round_number}">',
            f'<h2 id="round-{round_number}">{index}. {html.escape(group["title"])} — năm {group["year"]}</h2>',
            f"<p>{rule}</p>",
            '<div class="table-wrap"><table>',
            '<caption>Mỗi học phần cần bộ tài liệu ở mục 1; nhờ cô xác nhận bộ đang sử dụng.</caption>',
            '<thead><tr><th scope="col">Mã HP</th><th scope="col">Tên học phần</th><th scope="col">Tín chỉ</th><th scope="col">Trang học phần HMU</th></tr></thead><tbody>',
        ])
        for spec in group["courses"]:
            code = spec["course_code"]
            course = courses[code]
            link = hmu_link(course["hmu_course_url"], f"Mở trang LMS — {code}", show_url=True)
            chunks.append(
                f'<tr data-course-code="{html.escape(code, quote=True)}">'
                f'<th scope="row" class="code">{html.escape(code)}</th>'
                f'<td>{html.escape(course["name"])}</td>'
                f'<td class="credit">{spec["total_credits"]}<br><small>{spec["theory_credits"]} LT · {spec["practice_credits"]} TH</small></td>'
                f'<td>{link}<span class="tag">Bài học yêu cầu đăng nhập</span></td></tr>'
            )
        chunks.append(
            '</tbody></table></div><p class="teacher-note"><strong>Nhờ cô xác nhận:</strong> '
            'tên tài liệu/giáo trình đang dùng, phiên bản áp dụng và phần bắt buộc phải học. '
            'Ảnh chương trình chưa quy định thứ tự giữa các môn trong cùng Round.</p></section>'
        )
    chunks.extend([
        """<section class="card">
<h2>4. Nền tảng đã học trước — chỉ xin yêu cầu đầu ra</h2>
<p>Đối với các học phần kiến thức chung, cơ sở/hỗ trợ và kiến thức cơ bản ngành (Round 1), gồm cả Cấp cứu ngoại Chấn thương chỉnh hình, em chỉ cần <strong>chuẩn đầu ra hoặc những kiến thức/kỹ năng nền tảng cần có khi bước vào Round 2</strong>. Đợt này chưa xin bộ bài giảng chi tiết của các môn đó.</p>
<p>Khung năng lực BSNT Ngoại khoa cô đã gửi giúp xác định yêu cầu năng lực chung. Kính nhờ cô xác nhận phiên bản áp dụng và ma trận liên kết học phần–năng lực/chuẩn đầu ra nếu đã có sẵn.</p>
<p class="muted">Chuẩn đầu ra cấp chương trình và chuẩn đầu ra của từng học phần được giữ đúng phạm vi; không tự coi hai loại này là tương đương.</p>
</section>
<section class="card">
<h2>5. Các trang HMU để đối chiếu chương trình</h2>
<p>Các trang này giúp xác định chương trình và danh mục môn; không thay thế đề cương và tài liệu học chính thức của từng môn.</p>
<div class="source-links">""",
        hmu_link(programme["url"], "Chương trình BSNT Ngoại khoa — HMU", show_url=True),
        hmu_link(year_two["url"], "Danh mục học phần năm thứ hai — HMU", show_url=True),
        hmu_link(year_three["url"], "Danh mục học phần năm thứ ba — HMU", show_url=True),
        hmu_link(outcomes["url"], "Chuẩn đầu ra cấp chương trình — PDF HMU", show_url=True),
        """</div><p class="muted">Kính nhờ cô xác nhận chương trình và tài liệu phù hợp với khóa học đang áp dụng.</p>
</section>
<section class="card">
<h2>6. Lời nhắn kèm danh mục</h2>
<blockquote>Dạ em gửi cô danh sách các học phần Chấn thương chỉnh hình Round 2 và Round 3 mà em dự định tập trung xây dựng nội dung học trên web. Em đã đối chiếu được tên và mã môn trên LMS của trường, nhưng chưa xem được tài liệu bên trong vì cần tài khoản có quyền truy cập.

Cô cho em xin đề cương chi tiết, danh sách bài và giáo trình/slide hoặc tài liệu thực hành đang dùng cho các môn này được không ạ? Nếu tài liệu đã có trên LMS, cô chỉ giúp em đúng mục hoặc gửi bản có thể chia sẻ cũng được ạ. Các môn nền tảng trước đó em chỉ cần chuẩn đầu ra/yêu cầu đầu vào, chưa cần bài giảng chi tiết.

Em xin các tài liệu hiện có, cô không cần chuẩn bị thêm. Cô có sẵn môn nào thì cho em xin môn đó trước để em làm mẫu và gửi cô góp ý ạ.</blockquote>
</section>
<footer>Bản tổng hợp phục vụ trao đổi và xin tài liệu giảng dạy. Danh mục môn theo ảnh chương trình người dùng cung cấp, đối chiếu với trang HMU; chưa phải đề cương được ban hành hoặc xác nhận đã nhận đủ tài liệu.</footer>
</main></body></html>""",
    ])
    return "\n".join(chunks) + "\n"


def write_material_review(package: Path = PACKAGE, output: Path | None = None) -> Path:
    graph = json.loads((package / "graph.json").read_text(encoding="utf-8"))
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    target = output or package / "review.html"
    target.write_text(render_material_review(graph, scope), encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(write_material_review(output=args.output).relative_to(ROOT).as_posix())
