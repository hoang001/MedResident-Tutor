# Hệ thống giao diện MedResident Tutor

Hướng đã triển khai là học thuật navy–teal, nền sáng, ưu tiên thao tác học và đọc nguồn. [DESIGN.md](../../DESIGN.md) chứa token chuẩn; [.impeccable/design.json](../../.impeccable/design.json) bổ sung breakpoint, chuyển động và mẫu component. Giá trị lấy từ code đã giao.

## Nguồn và token

`apps/frontend/app/layout.tsx` nạp `globals.css` trước `ui-theme.css`. Theme sau ghi đè nhận diện cũ; quy tắc đọc, form và bài có lựa chọn chưa bị ghi đè vẫn áp dụng. Kiểm tra cả specificity và media query khi mở rộng.

| Vai trò | Giá trị hiện tại | Cách dùng |
| --- | --- | --- |
| Navy | `--navy: #142d4e`; hover `#10253f` | Sidebar, nút chính, tiêu đề |
| Teal | `--accent: #0b7779`; hover `#075f62`; nền `#eaf4f3` | Link, chọn, focus, checkbox/radio |
| Chữ | `--ink: #1c3049`; phụ `#5d6d80` | Nội dung và metadata |
| Bề mặt / nền / đường phân nhóm | `#fff` / `#f4f6f9` / `#d9e2ec` | Panel, nền trang, hàng danh sách |
| Thành công | `#176244` trên `#edf7f2` | Lưu và hoàn tất |
| Cần chú ý | `#825a12` trên `#fff5df` | Cần tiếp tục xử lý, giới hạn |
| Lỗi | `#a02836` trên `#fff1f2` | Alert và validation |

Khoảng cách lặp lại: 8, 10, 12, 16, 20, 24, 26, 28, 32, 36px; đây là giá trị đang dùng, chưa phải biến spacing. Bo góc: badge 5px; control 7px; notice 8px; popover 10px; panel 12px. Panel phẳng, viền 1px; menu tài khoản có bóng `0 8px 30px #10253f24`.

## Chữ và bố cục

Tiêu đề và wordmark dùng Source Sans 3, fallback Segoe UI/Arial; body dùng Segoe UI/Arial ở 16px, line-height 1.6. Tiêu đề trang 1.9rem, line-height 1.15; h2 1.35rem; h3 1.1rem. Nguồn tối đa 75ch, line-height 1.85, giữ xuống dòng. Điểm dùng tabular figures.

Font upright variable tự host tại `apps/frontend/public/fonts/source-sans-3-upright.woff2` (200–900, `font-display: swap`), preload trong layout. [sources.json](../../apps/frontend/public/fonts/sources.json) ghi URL Adobe chính thức ở commit cố định, byte count và SHA-256; [OFL 1.1](../../apps/frontend/public/fonts/LICENSE-Source-Sans-3.md) đi kèm. Ảnh y khoa giữ tài sản hiện có, attribution/license từ dữ liệu; không thêm ảnh AI thay evidence.

| Ngưỡng | Hành vi thực tế |
| --- | --- |
| Desktop | Sidebar 232px; header 80px; nội dung tối đa 1120px, gutter 36px; biên soạn tối đa 1320px |
| ≤1150px | Vùng đề/trả lời và biên soạn một cột; bỏ sticky; admin chuyển tab đề/nguồn; upload xếp dọc |
| ≤900px | Sidebar thành dialog; header 72px; gutter 24px; dashboard một cột; ẩn phần giới thiệu bên auth |
| ≤600px | Gutter 16px; panel padding 20px; h1 trang 1.55rem; h2 1.2rem; kết quả xếp dọc; bảng admin thành hàng có nhãn |

Quy tắc đọc/chọn đặc thù còn có ngưỡng 820px/560px trong CSS gốc. Không ép mọi phần vào card; dùng list/table cho dữ liệu và prose cho đoạn đọc.

## Component và hành vi

| Component | Hợp đồng sử dụng |
| --- | --- |
| `AppShell` | Menu student/admin riêng; tài nguyên phụ tách nhóm; tài khoản từ `/auth/me`; dialog có đóng/Escape; giữ skip link |
| `PageHeading` | Một tiêu đề, mô tả ngắn, hành động khi cần; mobile xếp dọc |
| Button/link | Nút tối thiểu 44px; navy chính, secondary trắng có viền, text teal; disabled .5 opacity; nhãn bận rõ |
| Field | Label luôn hiện, helper/lỗi liên kết ARIA; input/select tối thiểu 46px; viền lỗi 2px; placeholder không thay label |
| `Badge` | Nhãn neutral/info/success/warning/danger có chữ; badge không phải nút lọc |
| `Pagination` | Tổng số/offset thật; khóa đầu/cuối hoặc đang tải; không tính gợi ý KG như bài có gói chấm |
| `Loading`, `EmptyState`, `Alert` | Phân biệt tải/rỗng/lỗi/đã lưu; lỗi dùng alert, thông báo khác dùng status; có hành động khôi phục |
| `ResourceNav` / tabs | ARIA và gạch teal cho tab hiện tại; không thêm wizard cho chỉnh sửa nhỏ |
| `PracticeResult` | Điểm, stage, tiêu chí, phản hồi/đáp án, nguồn; giữ Medical khi Teaching lỗi; retry do người dùng chọn |
| `StructuredResult` | Ghi rõ chấm theo đáp án biên soạn, chưa xác nhận chuyên gia, không ghi mastery; nguồn giữ marker native |
| `QuestionBankWorkspace` | Nguồn cạnh rubric trên desktop, tab màn hình nhỏ; đọc toàn bộ nguồn đưa focus tới preview; lưu nháp khác phát hành |
| `DocumentWorkspace` | Danh sách/upload thật; nêu giới hạn 100 tài liệu gần đây và chưa tự OCR/lập chỉ mục |

Focus: outline 3px, offset 3px, teal trên nền sáng và trắng trong điều hướng navy. `source-details` có chevron phải/xuống theo đóng/mở. `evidenceTitle` chỉ đổi nhãn kỹ thuật sang “Trích đoạn đối chiếu”; dữ liệu lưu không đổi. Kết quả giữ ID, nội dung nguồn, trang, phiên bản và provenance của đúng attempt.

Chuyển động: fade nội dung .18s khi không yêu cầu giảm chuyển động; đổi nền/viền nút .15s. Loading không nhấp nháy; chevron đổi hướng theo trạng thái native.

## Quy tắc mở rộng

- Tiếng Việt ngắn, có hướng xử lý; không dùng raw JSON/provider debug/UUID làm tiêu đề học viên.
- Phân biệt mô phỏng, phát lại và đáp án biên soạn; giữ điểm và output đã lưu.
- Tiến độ hoàn thành không phải năng lực y khoa. Phát hành không phải chuyên gia phê duyệt.
- Giữ nháp theo tài khoản, idempotency và cảnh báo bỏ thay đổi; không chấm lại ngầm khi mở lịch sử.
- Không thêm nút sửa hồ sơ, đổi mật khẩu, quản lý người dùng hay lời hứa thi thử/lộ trình khi backend chưa có.
- `.eyebrow` chỉ là selector tương thích nội dung cũ; không dùng làm mẫu kicker mới.

Kiểm thử và bảo toàn dữ liệu ở [báo cáo bàn giao](ui-completion-report.md); tài liệu này không tự xác nhận đã chạy lại các kiểm tra đó.
