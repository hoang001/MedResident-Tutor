# Câu tự luyện từ KG Neo4j

Luồng mới dùng thư viện Neo4j và StudySession hiện có, không tạo bộ bảng Question/Rubric thứ hai và không sửa KG hoặc dữ liệu nguồn. Không có migration mới; DB cần revision study workspace `20261104_0006` đã triển khai trước đó.

## Dùng trên giao diện

1. Mở `/knowledge`, chọn một nội dung và bấm **Tự luyện từ nội dung này**; hoặc mở `/exams` trực tiếp.
2. Lọc sách/bài, **Nguồn câu hỏi** (sách/KG/cả hai), **Phạm vi ôn tập** (toàn bộ/đã đọc/đánh dấu), tìm từ khóa và chọn tối đa 20 câu.
3. Làm bài, lưu nháp, hoàn tất; mở phần **Nội dung nguồn để tự đối chiếu**. Kết quả và căn cứ được lưu snapshot, không thay đổi theo KG sau đó.

Khởi động từ repo gốc bằng `docker compose up -d --build db backend frontend`, mở http://localhost:3000/exams và đăng nhập hiện có. Neo4j phải đang chạy; cấu hình NEO4J_* và data/library/catalog.json như thư viện hiện tại. Lệnh Compose không tự migration/seed: nếu DB chưa có revision study workspace, cần kiểm tra/sao lưu và nâng cấp riêng, không reset/stamp.

## Dữ liệu và thuật toán

`GET /api/v1/study/questions`: q, book, chapter, origin=all|book|kg, focus=all|read|bookmarked, node_id, offset, limit (tối đa 50).

Neo4j → Snapshot nguồn → câu lượng giá SampleQuestion + câu theo mẫu từ nội dung/quan hệ lâm sàng có nguồn → lọc theo sách/bài/trạng thái đọc riêng của tài khoản → chọn câu → StudySession PostgreSQL.

- Các câu KG được dựng theo mẫu tự luận: trình bày nội dung, phân loại, nguyên tắc, can thiệp hoặc mối liên hệ có trích dẫn. Không có câu tình huống lâm sàng mới, không suy diễn nhân quả hay sinh dữ kiện y khoa.
- Không gọi LLM, embedding, retrieval bên ngoài. Medical/Teaching không bị thay đổi. Không giả lập rằng các câu này đã được AI/chuyên gia kiểm định.
- Mỗi câu KG chỉ dùng một sách/phiên bản. Giữ riêng nguồn 2006 và 2021, không hòa trộn thành khuyến nghị mới. Không gán môn học/Topic bằng suy đoán.
- Bắt buộc có đoạn trích, số trang PDF hợp lệ và hash tài liệu trong catalog. Không có trích dẫn riêng cho quan hệ thì không sinh câu quan hệ. Bỏ qua concept quá dài thay vì cắt mất điều kiện. Chưa sinh câu riêng cho Drug.
- Câu được đánh dấu `origin=kg_template`, `review_status=needs_review`, `expert_verified=false`. KG source_reviewed_draft không có nghĩa chuyên gia y khoa đã duyệt.
- Câu liên quan node đang bị đánh dấu needs_correction ở đúng revision hiện tại bị loại khỏi lượt mới. Bài đã lưu vẫn đọc được snapshot cũ.
- focus=read chỉ chọn nội dung mà người dùng đã đánh dấu đọc ở cùng revision hiện tại; focus=bookmarked theo bookmark riêng. Đây là ưu tiên ôn tập theo lựa chọn người học, không phải ước lượng năng lực hay mastery.

Các câu KG có ID `KGQ:<hash>` gắn nội dung, phiên bản mẫu, node/revision, quan hệ/điều kiện và nguồn/hash. ID thay đổi khi căn cứ thay đổi; tạo lượt mới bằng ID cũ trả 409 yêu cầu tải danh sách lại. Idempotency key đã có vẫn mở lượt cũ.

## Bảo toàn và giới hạn

POST/GET/PUT `/api/v1/study/sessions` tiếp tục giới hạn sở hữu tài khoản và lưu đáp án/snapshot. Danh sách câu và bài nháp KG không trả text căn cứ hay excerpt chứa đáp án. Sau hoàn tất mới trả study_basis và trích dẫn để tự đối chiếu. Người học vẫn có quyền chủ động mở thư viện/PDF trước khi làm; đây không phải chế độ thi kín.

Không có rubric được duyệt hoặc chấm điểm cho các câu mới: `graded=false`, `score=null`. Luồng này nằm ở `/exams` (Bài tự luyện) hiện có; chưa tự đưa câu vào `/learn` chấm Medical. Nếu cần chấm, phải bổ sung rubric/criterion và SourceUnit đã đối chiếu qua ngân hàng câu hỏi, không tự coi mọi đoạn KG là đáp án đầy đủ.

Kiểm tra read-only ngày 05/11/2026 trên KG thật: 126 câu SampleQuestion và 5.658 ứng viên KG (3.797 câu nội dung, 1.861 câu quan hệ; 3.429 thuộc sách 2021, 2.229 thuộc sách 2006). Đây là số ứng viên trước khi lọc cờ cần sửa/đọc cá nhân, không phải bộ câu đã được chuyên gia duyệt. Các ứng viên được dựng khi đọc, không chèn hàng nghìn record vào PostgreSQL/Neo4j.

## Kiểm chứng

Tests backend: `tests/test_kg_questions.py`, cùng hồi quy `tests/test_study_workspace.py`. Dùng graph tổng hợp + DB kiểm thử, không API LLM. Browser: `e2e/study.spec.ts`, chạy frontend/backend thật và PostgreSQL biệt lập; graph fixture tổng hợp, không sửa KG thật.

Chạy browser từ repo gốc, Docker Desktop đang bật:

```powershell
docker compose -p medresident-kg-study-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml up -d --build db backend frontend
docker compose -p medresident-kg-study-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml exec backend alembic upgrade head
docker compose -p medresident-kg-study-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml exec backend python /e2e/seed_study.py
# Cần npm ci trong apps/frontend trước nếu chưa có dependencies cho Playwright.
docker compose -p medresident-kg-study-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml run --rm --no-deps -e E2E_SUITE=study browser npx playwright test
```

Project thử nghiệm có DB tmpfs và volume uploads riêng; không dùng volume phát triển. Không dùng các lệnh seed fixture cho môi trường phát triển. Khi xong dừng đúng project test; chỉ xóa volume test sau khi xác minh label project.

Thay đổi chính: `modules/study/questions.py`, router study, `/exams`, KnowledgeReader và kiểu dữ liệu knowledge. Không thay schema DB, prompt Medical/Teaching, file sách hoặc manifest pilot.

Kết quả kiểm chứng đợt này: 14 test backend PASS; 5/5 browser E2E PASS trên PostgreSQL biệt lập, graph fixture tổng hợp; typecheck/ESLint/Ruff và Next.js production build PASS. Neo4j thật chỉ đọc để kiểm tra nguồn và dựng số lượng ứng viên nêu trên. Đã dọn container/volume test riêng, không migration/import vào DB phát triển, không sửa KG, không gọi model, không commit/push.
