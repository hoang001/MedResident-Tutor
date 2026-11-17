# Kết quả cải thiện frontend — 05/11/2026

Đã triển khai các sửa đổi frontend, cài Impeccable và kiểm thử trên môi trường Docker riêng `medresident-ui-review`. Không sửa backend/database/RAG/KG/model, không commit/push. Các thay đổi có sẵn của người dùng được giữ nguyên.

## Phạm vi và thay đổi

Đã đánh giá Dashboard, Learning/mô phỏng AI, Exams/tự luyện, Progress, Login/Register, Admin Questions/Documents; đồng thời kiểm tra Curriculum, Knowledge và Sources vì chúng dùng chung điều hướng và hệ thống đọc nguồn.

- Điều hướng: đánh dấu trang hiện tại bằng `aria-current`, màu nền và gạch chân; thêm skip link và đích focus bằng bàn phím.
- CSS: focus cho input/textarea, màu accent/hover dùng chung, kiểm soát xuống dòng của nội dung dài, fieldset co giãn, nút/menu tối thiểu 44px, trạng thái forced-colors, số liệu tabular, khung đăng nhập và khoảng cách mobile.
- Dashboard/Progress: phân biệt đang tải với chưa có hoạt động; không báo dữ liệu rỗng trong lần tải đầu.
- Auth: căn giữa biểu mẫu, nhóm nhãn/ô nhập, trạng thái busy, mô tả ngắn; lỗi xác nhận mật khẩu chuyển focus về đúng ô.
- Admin documents: nhãn tiếng Việt, thông báo lỗi/success qua alert/status, giữ nguyên upload và trạng thái xử lý.
- Admin questions: cảnh báo khi bỏ nội dung/rubric chưa lưu lúc mở câu khác, tạo mới, bấm liên kết và unload; trạng thái chưa lưu; liên kết lỗi với trường câu hỏi. Nội dung evidence và metadata đặt trong disclosure có nhãn; checkbox, preview, locator và nội dung đầy đủ vẫn truy cập được.
- Learning: hỏi trước khi tạo lượt mới nếu đang có câu trả lời; không sửa cơ chế lưu nháp/nộp bài/retry/Medical/Teaching.

## Baseline và đánh giá lại

Xem `baseline.md`, `detect-before.json`, `detect-after.json`.

| Bằng chứng | Trước | Sau |
|---|---:|---:|
| Detector source warnings | 3 | 0 |
| P1 xác nhận trong các đường đi đã xem | 1: mất nội dung quản trị chưa lưu | 0 |
| Critique Nielsen, nhận định của reviewer | 24/40 | 27/40 |
| Audit kỹ thuật, nhận định của reviewer | 11/20 | 15/20 |

Điểm là đánh giá định tính, không phải phép đo usability. Baseline từ mã nguồn, đánh giá cuối có thêm ảnh/render và tests nên không phải thí nghiệm trước/sau có kiểm soát. Không có ảnh baseline. Ba cảnh báo detector ban đầu là thẩm mỹ về viền: viền trích dẫn/nguồn có mục đích biên tập hợp lý, không phải ba lỗi accessibility. Kết quả detector sạch không chứng minh chất lượng toàn ứng dụng.

Tương phản tính từ giá trị màu CSS: chữ trắng trên accent cũ 5.00:1, accent mới 6.29:1; muted trên nền trang 5.07:1, trên trắng 5.32:1. Màu cũ đã đạt AA cho chữ thường; sửa accent tăng độ rõ, không phải khắc phục một vi phạm AA đã đo. Chưa kiểm toán toàn bộ cặp màu/trạng thái.

## Kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| ESLint | Qua |
| TypeScript `tsc --noEmit` | Qua |
| Next.js production build | Qua, đủ 14 route output |
| practice/client hiện có | 9/9 |
| study hiện có | 5/5 |
| bank hiện có | 2/2 |
| retry hiện có, `teaching_error` | 1/1 |
| review bổ sung | 5/5 |
| Tổng | 22/22, gồm 2 client logic và 20 browser tests |

Review bổ sung kiểm tra skip link/focus lỗi, hủy bỏ chuyển trang/tạo mới khi rubric chưa lưu, đăng ký/đăng xuất, upload quản trị và tràn ngang trên 11 trang × 3 viewport 390/768/1440. Có 33 ảnh tại `screenshots/`; đã xem trực tiếp các ảnh đại diện desktop/tablet/mobile. Dữ liệu trong ảnh là fixture tổng hợp, không phải dữ liệu học thật.

Luồng đã qua: xác thực/đăng ký/đăng xuất/hết phiên/401, return path an toàn, tách tài khoản, giữ draft, nộp idempotent khi mất response, Medical/Teaching/evidence, retry chỉ Teaching giữ nguyên Medical, đọc và lưu ghi chú/dấu trang, snapshot nguồn tự luyện, nộp bài không chấm điểm, quyền review/admin, quản trị rubric, PDF bearer ngoài URL và upload.

Lượt PDF đầu không chạy được vì thiếu synthetic PDF; chạy `seed_study.py` trong stack test đã khắc phục, 5/5 study qua. Lượt retry đầu dùng nhầm tên scenario không hỗ trợ; sửa biến môi trường test thành `teaching_error`, 1/1 qua. Không đổi code sản phẩm để làm tests qua.

Không có frontend unit runner riêng; hai client logic tests chạy bằng Playwright. Không chạy lại backend tests vì không sửa backend. Không dùng dữ liệu/tài khoản/volume production để thử.

## Giới hạn còn lại

Không còn P0/P1 được xác nhận trong bằng chứng đã kiểm tra. Chưa thể tuyên bố đạt WCAG toàn diện hay kiểm chứng mọi trạng thái sản xuất.

P2 còn lại: menu và dashboard dài trên điện thoại; thông tin môn được chọn nằm sau danh sách môn; editor lặp bộ chọn evidence khi có nhiều tiêu chí; nút lưu của bài 20 câu ở cuối trang; một số thuật ngữ kỹ thuật và tên trang mô phỏng chưa đồng nhất. Đây là cải tiến hiệu suất thao tác, không có bằng chứng chặn hoàn thành tác vụ trong fixture đã thử.

Chưa thử thiết bị thật/Safari/Firefox/NVDA, zoom chữ 200%, Core Web Vitals, tập dữ liệu rất lớn, toàn bộ lỗi timeout/offline, browser Back/Forward với nội dung chưa lưu, và toàn bộ dữ liệu Neo4j thật. Guard dùng mẫu hiện có của Exams: liên kết/open/new/unload; không tuyên bố đã chặn mọi chuyển route có thể có. Google OAuth chưa cấu hình trong stack test nên chưa kiểm chứng đăng nhập Google.

## File thay đổi trong đợt này

- `apps/frontend/app/globals.css`
- `apps/frontend/app/layout.tsx`
- `apps/frontend/app/dashboard/page.tsx`
- `apps/frontend/app/progress/page.tsx`
- `apps/frontend/app/learn/page.tsx`
- `apps/frontend/app/admin/questions/page.tsx`
- `apps/frontend/app/admin/documents/page.tsx`
- `apps/frontend/components/Nav.tsx`
- `apps/frontend/components/AuthForm.tsx`
- `apps/frontend/playwright.config.ts`
- `apps/frontend/e2e/practice.spec.ts` — chấp nhận xác nhận tạo lượt mới
- `apps/frontend/e2e/ui-review.spec.ts` — 5 regression/viewport tests
- `PRODUCT.md`, `DESIGN.md`, `.impeccable/design.json`
- `.agents/skills/impeccable/` — CLI/skill/reference cài bằng lệnh chính thức
- `docs/frontend-review/` — baseline, kết quả, detector JSON, ảnh

## Chạy lại

Frontend khi có Node 22/npm:

```powershell
cd apps/frontend
npm ci
$env:NEXT_PUBLIC_API_BASE_URL='http://localhost:8000/api/v1'
npm run dev
# http://localhost:3000
npm run lint
npm run typecheck
npm run build
```

Backend cần chạy theo `docs/study-workspace.md`; không cần model cho thư viện/tự luyện. Không seed lại DB dùng thật.

Stack test riêng (Docker Desktop; dùng project name này để tránh DB thật):

```powershell
docker compose -p medresident-ui-review -f compose.practice-e2e.yml -f compose.study-e2e.yml up -d --build db backend frontend
docker compose -p medresident-ui-review -f compose.practice-e2e.yml -f compose.study-e2e.yml exec -T backend alembic upgrade head
docker compose -p medresident-ui-review -f compose.practice-e2e.yml -f compose.study-e2e.yml exec -T backend python /e2e/seed_study.py
# Chuẩn bị deps theo docs/study-workspace.md, hoặc npm ci trên máy.
docker compose -p medresident-ui-review -f compose.practice-e2e.yml -f compose.study-e2e.yml run --rm -e E2E_SUITE=review browser
# E2E_SUITE=study, bank; bỏ biến để chạy practice/client.
# Retry cần khởi động backend với E2E_MOCK_SCENARIO=teaching_error rồi E2E_SUITE=retry.
docker compose -p medresident-ui-review -f compose.practice-e2e.yml -f compose.study-e2e.yml down
```

Để lưu ảnh review qua Compose mặc định (chỉ mount frontend), mount thêm repository hoặc thư mục docs thích hợp; lượt thực hiện này mount toàn bộ repo vào `/work`, chạy tại `/work/apps/frontend`. Terminal phiên này không có Node/Git trên PATH; dùng Docker Node và Git đi kèm GitHub Desktop. Stack test đã được dừng sau khi kiểm tra.