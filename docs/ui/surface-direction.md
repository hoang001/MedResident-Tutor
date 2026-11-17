# Learning workspace — UI completion

Mode: Operate, với khu vực đọc nội dung theo mode Read. Người dùng là bác sĩ nội trú sử dụng laptop hoặc điện thoại trong phiên học ngắn và tập trung. Nền sáng phù hợp đọc tài liệu dài, không giả lập hồ sơ bệnh viện.

## Direction contract

THESIS: Ưu tiên đường đi từ tài liệu tới bài tập và kết quả đã lưu; mỗi vai trò có không gian nhiệm vụ riêng.

OWN-WORLD: Navy cho điều hướng và hành động chính, teal cho trạng thái chọn và liên kết. Bề mặt trắng, nền xám xanh, chữ sans hỗ trợ tiếng Việt; danh sách, bảng và bố cục đọc thay cho các card đồng dạng.

STORY: Student tiếp tục học, chọn bài, trả lời, đối chiếu và mở lịch sử. Admin tìm câu, soạn thủ công với nguồn cạnh rubric, lưu nháp rồi phát hành.

FIRST VIEWPORT: Desktop có sidebar navy 232px, header tài khoản, nội dung rộng vừa đủ; tổng quan dẫn bằng hoạt động thật và một hành động tiếp tục. Mobile dùng menu gọn, một cột, không cuộn ngang. Bài tập có vùng đọc/trả lời tách rõ, kết quả và nguồn đóng mở.

FORM: Hướng học thuật navy–teal do brief của người dùng chỉ định; code-led. Seed reference: seed:8890582f24906581. Signature interaction: chọn bài từ danh mục rồi tiếp tục đúng bản nháp/kết quả, nguồn mở tại tiêu chí tương ứng. Không có vòng chọn lại thương hiệu vì người dùng đã giao chọn hướng và triển khai liên tục.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Ràng buộc: không đổi dữ liệu, nguồn, prompt, chấm, provider, KG hoặc mastery; test bằng mock có nhãn trên DB riêng; không model, ảnh trang trí hay thư viện UI mới. Không hứa quản lý người dùng/thi thử/lộ trình khi thiếu backend.
