# Quản trị ngân hàng câu hỏi local

Mở http://localhost:3000/admin/questions bằng admin local hiện có. Backend và frontend chạy bằng `docker compose up -d --build backend frontend` từ thư mục gốc repo; DB phát triển giữ nguyên volume, cổng localhost:5433. Medical/Teaching tiếp tục dùng mock.

## Ba thao tác kiểm tra

1. Đăng nhập admin, mở **Ngân hàng câu hỏi**, tạo câu hỏi tự luận ngắn, nhập rubric và các criterion; chọn SourceUnits hiện có cho từng criterion rồi lưu.
2. Chọn **Đưa vào sử dụng**, mở `/learn`, chọn câu hỏi và nộp câu trả lời. Kết quả là giả lập, không đánh giá năng lực thật.
3. Quay lại trang quản trị, sửa rubric rồi lưu hoặc ngừng sử dụng; mở lịch sử `/learn` để kiểm tra kết quả cũ vẫn giữ snapshot ban đầu.

## API và dữ liệu

Prefix `/api/v1`, mọi API quản trị yêu cầu AdminUser:

- GET/POST `/admin/questions`: danh sách/tìm kiếm (q, limit, offset) và tạo mới.
- GET/PUT `/admin/questions/{question_id}`: xem/sửa câu hỏi, rubric, criteria và mapping evidence.
- PATCH `/admin/questions/{question_id}/availability`: đưa vào/ngừng sử dụng.
- GET `/admin/source-units` và `/admin/source-units/{source_unit_id}`: tìm kiếm/xem evidence, không sửa.

PUT và PATCH yêu cầu version hiện tại, xung đột phiên bản trả 409. ID mới do server tạo với prefix APP_Q_/APP_R_/APP_C_; criterion đã tồn tại giữ ID khi sửa. Mỗi lần lưu phải có nội dung, điểm hữu hạn dương, tổng điểm khớp và evidence hợp lệ cho mọi criterion. Form chưa lưu không được đưa vào sử dụng. SourceUnit cần nguồn có external ID, tên, SHA-256, locator PDF hợp lệ và trạng thái review rõ ràng.

Migration `20261022_0004` thêm `questions.is_available` (mặc định false), `bank_version` (mặc định 1, CHECK >=1). Chỉ các câu hỏi cũ thỏa cấu trúc reader trước đây được bật khi nâng cấp. Trạng thái khả dụng tách khỏi review chuyên gia; nội dung chỉnh từ UI được đánh dấu chưa xác minh, không thay review flags trong file pilot. Không tạo Topic/Specialty giả. Chưa có UI gán Topic hoặc chỉnh reference answer.

Snapshot attempt không bị thay đổi bởi sửa/ngừng sử dụng. Request mới bị chặn với câu hỏi ngừng sử dụng; gửi lại idempotency key cũ vẫn đọc attempt cũ. API xem đề learner không chứa rubric/reference answer. Lưu và mapping dùng một transaction; submit và sửa cùng khóa Question để snapshot nhất quán.

## Kiểm tra biệt lập

Từ repo, Docker Desktop đang chạy:

```powershell
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml up -d --build db backend frontend
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml exec backend alembic upgrade head
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml exec backend python /e2e/seed.py --synthetic-bank
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml run --rm --no-deps -e E2E_SUITE=bank browser npx playwright test
```

Fixture chỉ được seed vào database `medresident_test_browser`, dùng PDF tổng hợp và tài khoản test; không seed vào DB phát triển. Browser chạy frontend/backend/PG thật, chỉ provider mock. Các test PostgreSQL nằm tại `apps/backend/postgres_tests/test_question_bank*.py`; DATABASE_URL kiểm thử phải trỏ DB biệt lập có tên medresident_test_*. Không dùng SQLite để chứng minh migration.

Trước migration DB có dữ liệu: kiểm tra revision/schema drift, sao lưu pg_dump định dạng custom và kiểm tra pg_restore --list; dừng backend để tránh truy cập đồng thời và cache prepared statement cũ, chạy Alembic bằng Python dự án rồi khởi động lại backend. Không stamp/reset/drop. Bản sao lưu chứa dữ liệu ứng dụng, nằm trong data/backups đã được loại khỏi Git.
