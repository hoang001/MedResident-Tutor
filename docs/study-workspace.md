# Chạy web và học tập khi server model đang tắt

**Cập nhật 05/11/2026:** nội dung học tập trung B21CN7–B21CN18 (Round 2 và 3).
Các học phần trước đó chỉ giữ yêu cầu đầu ra/nền tảng; danh mục nguồn vẫn đủ 27
môn. Xem [phạm vi bác sĩ nội trú](residency-study-scope.md).

Web có thể hoạt động với PostgreSQL và Neo4j đang bật; không cần WireGuard hay
server LLM cho các chức năng bên dưới. Không có bước OCR, extraction hoặc gọi model
trong lúc mở các trang này.

## Các trang đã nối

| Trang | Chức năng |
|---|---|
| `/dashboard` | Tổng quan hoạt động thật của tài khoản, trạng thái thư viện, tiếp tục đọc |
| `/curriculum` | Cây chương trình, 27 học phần, nguồn HMU, mục tiêu và PLO cấp chương trình |
| `/knowledge` | Tìm từ khóa có/không dấu, lọc sách/bài/loại node, đọc nội dung và quan hệ |
| `/knowledge?id=…` | Chi tiết node, trích dẫn, ghi chú riêng, dấu trang, trạng thái đọc |
| `/sources` | Hai sách nguồn, mục lục 25 và 36 bài, mở PDF theo trang |
| `/exams` | Tự luyện với câu hỏi đã có trong sách, lưu nháp, mở lại và hoàn tất bài |
| `/progress` | Ghi chú, dấu trang, tiến độ đọc và lịch sử bài tự luyện của tài khoản |
| `/learn` | Luồng mô phỏng Medical/Teaching đã có; điểm giả lập không tính vào tiến độ thật |
| `/admin/questions`, `/admin/documents` | Quản trị ngân hàng câu hỏi và tài liệu tải lên đã có |

Quản trị viên có thể ghi nhận kết quả đối chiếu ngay trong **Lịch sử đối chiếu
nguồn** ở cuối trang node. Lịch sử được thêm mới, gắn với phiên bản nội dung và
quan hệ; sửa KG làm đánh dấu cũ hết hiệu lực. Đối chiếu nguồn không tự nâng thành
phê duyệt chuyên môn và không sửa nội dung Neo4j.

## Khởi động

Tại thư mục gốc, với Docker Desktop và instance Neo4j đang chạy:

```powershell
docker compose build backend frontend
docker compose up -d db
# Sao lưu trước khi nâng cấp DB đang có dữ liệu.
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up -d backend frontend
```

Mở http://localhost:3000/dashboard. Dùng tài khoản hiện có hoặc đăng ký tài khoản
mới trên web. Không chạy seed để đặt lại tài khoản.

Migration `20261104_0006` chỉ thêm `study_records`, `study_sessions`,
`knowledge_reviews` và index/constraint tương ứng. Các bản ghi cũ được giữ nguyên.
Không dùng `stamp`, `drop`, `reset` hoặc xóa volume để nâng cấp. `/ready` kiểm tra
PostgreSQL; `/api/v1/knowledge/status` có đăng nhập kiểm tra riêng Neo4j.

## Cấu hình và chặn model

Compose đọc **`.env` gốc** qua `env_file`. Các biến có trong khối `environment` của
Compose ưu tiên hơn `env_file`; shell có thể ảnh hưởng những giá trị được nội suy
`${…}`. `MODEL_CALLS_ENABLED: "false"` trong Compose là giá trị cố định để chặn
provider model HTTP. Mặc định trong backend cũng là `false`. Giữ
`PRACTICE_PROVIDER=mock`, `LLM_PROVIDER=mock`, `EMBEDDING_PROVIDER=mock` để dùng
mục mô phỏng; mock không có kết nối mạng đến model.

- Script chạy trên Windows tiếp tục đọc `NEO4J_URI` trong `.env`, thường là
  `bolt://localhost:7687`.
- Backend Docker dùng `APP_NEO4J_URI`, mặc định
  `bolt://host.docker.internal:7687`. Địa chỉ `localhost` bên trong container
  không trỏ tới Neo4j Desktop trên Windows.
- `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` vẫn lấy từ `.env` gốc.
  Không đưa mật khẩu lên frontend hay query string.
- `KNOWLEDGE_DATA_ROOT=/app/data` được mount từ `./data`. Catalog runtime là
  `data/library/catalog.json`; PDF giữ ở vị trí tương đối đã khai báo dưới
  `data/raw-source`. Catalog không chứa API key và không thay catalog extraction cũ.
- Chạy backend trực tiếp: Pydantic đọc `.env` theo thư mục làm việc; biến môi
  trường terminal có ưu tiên cao hơn. Hướng dẫn này ưu tiên Compose để tránh
  nhầm đường dẫn `.env` và địa chỉ DB.

Lớp thư viện chỉ dùng truy vấn Neo4j cố định, tham số hóa và transaction chỉ đọc.
Tìm kiếm bằng từ khóa, không dùng embedding hay GraphRAG. Snapshot được cache
ngắn trong bộ nhớ, không ghi ngược KG. Khi Neo4j không kết nối được, API trả
`KNOWLEDGE_UNAVAILABLE` thay vì dùng dữ liệu giả thay thế. Ghi chú và bài đã lưu
trong PostgreSQL vẫn xem được ở `/progress` và `/exams?session=…`.

PDF yêu cầu đăng nhập, chọn từ catalog có kiểm tra đường dẫn; frontend lấy bằng
Bearer header rồi mở Blob URL, không gắn token vào URL.

## Giới hạn dữ liệu và đánh giá

- Có 126 câu hỏi nguồn trong sách 2021. Sách 2006 chưa có SampleQuestion trong KG;
  web báo chưa có câu hỏi cho phạm vi này. Không sinh câu hỏi hoặc đáp án mới.
- Bài tự luyện chưa chấm điểm; `graded=false`, `score=null`. Không ghi
  LearningResult/mastery, không tự coi “đã đọc” là đạt chuẩn đầu ra.
- Bài được lưu với snapshot câu hỏi và nguồn. Sửa KG không làm thay đổi câu hỏi
  trong bài đã tạo. Gửi lại cùng idempotency key không tạo bài trùng. Phiên bản
  bản nháp giúp chặn ghi đè từ hai tab; bài hoàn tất không sửa tiếp.
- Ghi chú/dấu trang/bài làm tách theo tài khoản. Bấm **Lưu** trước khi rời trang;
  web cảnh báo khi còn thay đổi chưa lưu. Lỗi lưu giữ nguyên nội dung đang nhập.
- Các gợi ý môn → chủ đề → sách lấy từ coverage map tạm thời, không suy đoán
  chúng là đề cương được duyệt. 27 môn vẫn chờ nội dung giảng viên.
- Dữ liệu sách là bản nháp đã đối chiếu nguồn, chưa phê duyệt chuyên môn. Bốn
  bài 2021 thiếu phần mở đầu trong PDF được đánh dấu tại mục lục, không bù bằng AI.
- Tính năng đặt thời gian bài thi, thi chính thức, đáp án/rubric đã duyệt,
  chấm điểm, đánh giá năng lực, gợi ý cá nhân hóa và trả lời bằng AI chưa nằm trong
  luồng tự luyện này.

## Kiểm tra

Backend unit/API tests không cần Neo4j hay model:

```powershell
cd apps/backend
python -m pytest -q
```

Kiểm tra migration dùng PostgreSQL **dùng riêng cho test**, tên database bắt đầu
`medresident_test_`; fixture sẽ reset schema của database test này:

```powershell
$env:INTEGRATION_TEST_DATABASE_URL='postgresql+asyncpg://<test-user>:<test-password>@localhost:<test-port>/medresident_test_workspace'
python -m pytest postgres_tests -q
```

Browser test dùng Compose test riêng, PostgreSQL tmpfs và graph tổng hợp được
inject qua `tests/e2e/study_app.py`. Ứng dụng production không import fixture này.
Không chạy test trên tài khoản/DB dùng thật.

```powershell
# Chạy từ gốc repo. Cần Node/npm để cài dependency test trên máy phát triển.
cd apps/frontend
npm ci
cd ../..
# Overlay study dùng volume dependency riêng; chuẩn bị bằng Docker Node nếu cần.
docker run --rm --mount "type=bind,source=${PWD}/apps/frontend,target=/tests" --mount type=volume,source=medresident-web-node-modules,target=/tests/node_modules -w /tests node:22-bookworm-slim npm ci --no-audit --no-fund
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml up -d --build db backend frontend
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml exec -T backend alembic upgrade head
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml exec -T backend python /e2e/seed.py
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml run --rm browser
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml -f compose.study-e2e.yml down
```

Backend test không nhận `.env` thật. Seed có kiểm tra đúng tên DB test; source PDF
được mount chỉ đọc. Các bài và ghi chú fixture không xuất hiện trong DB dùng thật.

## Kết quả kiểm tra ngày 04/11/2026

- 33 unit/API tests, 44 PostgreSQL integration tests và 13 browser/client tests
  đều qua; Ruff, ESLint, TypeScript và production build đều qua.
- Browser test dùng graph tổng hợp riêng, kiểm tra chuyển trang, lọc kiến thức,
  lưu/tải lại ghi chú, riêng tư giữa tài khoản, lưu/tải lại/hoàn tất bài tự luyện,
  quyền đối chiếu nguồn, PDF có xác thực và chiều rộng màn hình 390px.
- Kiểm tra chỉ đọc trên backend đang chạy với Neo4j thật: 4.167 node,
  2.138 quan hệ, 27 học phần, 126 câu hỏi; các endpoint thư viện và học tập trả 200.
- Đã tạo và kiểm tra bản sao lưu PostgreSQL trong `data/backups` trước migration.
  Sau khi nâng cấp từ `20261027_0005` lên `20261104_0006`, hash dữ liệu và số dòng
  của toàn bộ 22 bảng cũ không thay đổi. Chưa tạo ghi chú/bài thử trong DB dùng thật.
- Không gọi model, không chạy OCR/extraction, không ghi sửa KG hay thay đổi VPN/route.
