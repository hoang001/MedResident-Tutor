# UX audit — 16/11/2026

Baseline: 102 câu trong PostgreSQL, 100 khả dụng, 2 draft; 9 tài khoản, 6 attempt, 105 ghi nhận đọc và 21 bài tự ôn. Không cộng 5.784 gợi ý tự ôn từ KG vào ngân hàng chấm.

| Màn hình | Backend và hiện trạng | Thay đổi cần thiết |
| --- | --- | --- |
| Tổng quan | Có thống kê đọc, ghi chú, tự ôn; chưa tổng hợp attempt luyện tập | Dữ liệu thật, tiếp tục học, hoạt động gần đây; bỏ thông tin container/Neo4j khỏi student |
| Bài tập | 100 mục thật; tìm/lọc bằng metadata; danh sách chọn dài | Danh mục có phân trang server, tên dễ đọc, trạng thái đã làm và workspace làm bài |
| Kết quả | Medical/Teaching và evidence đã pin; có giữ Medical khi Teaching lỗi | Phân cấp điểm/tiêu chí, đóng mở nguồn, giữ nguyên output và nhãn mô phỏng |
| Lịch sử | Có API attempt, giao diện chỉ là nút ID cuối trang | Trang riêng, trạng thái tiếng Việt, mở đúng snapshot |
| Tiến độ | Có API đọc, bookmark, ghi chú và bài tự ôn | Tách hoàn thành khỏi năng lực, thống nhất empty/error/loading |
| Thư viện, sách, chương trình | Có Neo4j đọc thật, mục lục và liên kết PDF; mapping chưa phải đề cương chính thức | Giữ chức năng, chuyển thành tài nguyên học bổ trợ; không quảng bá lộ trình hoàn chỉnh |
| Ngân hàng admin | CRUD, revision, publish, SourceUnit thật; thiếu tổng số/filter trạng thái | Danh sách quản lý + workspace biên soạn, nguồn bên cạnh tiêu chí |
| Tài liệu admin | Upload và list API có; UI chỉ upload | Danh sách tài liệu thật + tải lên, thông báo rõ chưa OCR/lập chỉ mục |
| Tài khoản | Đăng ký, đăng nhập, auth/me, logout thật | Menu tài khoản gọn, xem thông tin đã có, không tạo chỉnh sửa hồ sơ giả |
| Quản lý người dùng | Chưa có endpoint quản lý đầy đủ | Không thêm menu hay nút không hoạt động |

Điểm yếu chung: navigation ngang dày, trộn student/admin; label “Mô phỏng AI” lấn công việc học; nhiều card/khối chữ giống nhau; UUID, raw JSON và thuật ngữ kỹ thuật lộ ở student; form chọn evidence dài và cuộn nhiều; thiếu tên trạng thái nhất quán. Tự ôn theo sách hoạt động nhưng chưa chấm, không phải thi thử hay lộ trình năng lực.

Nguồn tham khảo kiểm ngày 16/11/2026:

- https://hmu.edu.vn/: công cụ tra cứu timeout; không đánh giá trực tiếp giao diện, không dùng logo/ảnh của trường.
- https://ump.edu.vn/: công cụ tra cứu trả 502; không đánh giá trực tiếp giao diện, không dùng logo/ảnh của trường.
- https://service-manual.nhs.uk/design-system và trang Components/Design principles truy cập được. Dùng nguyên tắc tổ chức form, label, lỗi, details, trạng thái và khả năng tiếp cận; không sao chép nhận diện NHS.

Đã sao lưu code hiện tại và ghi git status vào `data/authoring/ui-completion-20261116`. Có nhiều thay đổi sẵn từ các task trước; không reset hay ghi đè dữ liệu ngân hàng.
