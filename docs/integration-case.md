# Ca tích hợp kỹ thuật ORTHO_B21CN1_Q_0001

## DB phát triển Docker local

Service `db` dùng `pgvector/pgvector:pg16`, volume lưu bền vững
`medresident-tutor_postgres_data`. Cổng mặc định là `127.0.0.1:5433` để không
đụng PostgreSQL Windows tại 5432; có thể cấu hình `POSTGRES_HOST_PORT`.

- Backend trong Compose: `db:5432`, database theo `POSTGRES_DB`.
- CLI Windows: `localhost:5433`, cùng database và credentials `POSTGRES_*`.
- `FILE_STORAGE_PATH` trong Compose: `/app/data/uploads`, được bind tới
  `<repo>/data/uploads`; CLI Windows phải dùng đường dẫn host này.
- Giữ `.env` với hostname/path cho Compose. Nếu chạy CLI Windows, chỉ override
  `DATABASE_URL` và `FILE_STORAGE_PATH` trong process như hướng dẫn bên dưới.
- Khởi động DB: `docker compose up -d db` từ repo root. Không dùng `down -v`.
- Nếu được phép tạo admin mới, seed riêng admin bằng
  `python -m app.scripts.seed --admin-only` với `SEED_ADMIN_EMAIL` và
  `SEED_ADMIN_PASSWORD` đã có trong environment. Chế độ này không tạo learner
  hoặc Topic/Specialty demo, không đổi quyền của tài khoản có sẵn.

## Phạm vi dữ liệu

Chưa có model/API mới. PostgreSQL giữ nội dung và quan hệ; UUID dùng nội bộ,
external ID dataset dùng trong payload. Không tự tạo Topic/Specialty hoặc admin.
SourceUnit giữ nguyên content/review flags; locator đọc payload là PDF 16–16,
trang in 15–15 theo manifest. Locator dataset 16–17 vẫn nằm trong metadata.
Đây không phải phê duyệt chuyên gia hoặc xác nhận kiến thức y khoa hiện hành.

## Môi trường và migration (PowerShell)

Chạy từ thư mục repo. Dùng PostgreSQL có pgvector; không dùng SQLite cho importer.
Chọn database muốn áp dụng một cách tường minh. Các lệnh dưới đây là hướng dẫn
cho người vận hành; tác vụ triển khai không tự áp dụng vào database đang dùng.

```powershell
Set-Location C:\WORKS\STUDY\MedResident-Tutor
$repoRoot = (Get-Location).Path
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e './apps/backend[dev]'
$backendPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$env:DEBUG = 'false'
# Tự đặt DATABASE_URL của DB đích (postgresql+asyncpg); không ghi secret vào Git.
# Có thể lấy an toàn từ môi trường vận hành hoặc nhập ẩn:
$dbSecret = Read-Host 'DATABASE_URL của DB đích' -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new('', $dbSecret).Password
$env:FILE_STORAGE_PATH = Join-Path $repoRoot 'data/uploads'
Set-Location (Join-Path $repoRoot 'apps/backend')
& $backendPython -m alembic current
& $backendPython -m alembic upgrade head
```

0001 đã được đóng băng bằng DDL từ Git `cf6f6a2`; không import live ORM.
0002 thêm SourceUnit/quan hệ/external IDs/JSONB và nới `questions.topic_id`.
Migration online kiểm tra schema trước/sau; DB không revision nhưng đã có bảng,
revision lạ hoặc drift được phát hiện sẽ bị từ chối. Không tự stamp/reset/repair.
Kiểm tra dùng Alembic type/FK/index/unique/nullable và CHECK constraints có tên;
đây không phải công cụ audit mọi đối tượng SQL ngoài ORM (ví dụ function/trigger).
Nếu DB lệch baseline, đối chiếu riêng trước khi chạy lại. Không dùng `create_all`
để nâng cấp DB. Downgrade bị chặn khi có dữ liệu nhập cần bảo toàn.

## Import / đọc payload

Tiếp tục trong `apps/backend`, với `$repoRoot`, `$backendPython`, `DATABASE_URL`
và `FILE_STORAGE_PATH` như trên. Admin UUID phải thuộc user ADMIN active đã có;
không có admin thì dừng để người vận hành cấp tài khoản đúng quy trình.

```powershell
$adminId = Read-Host 'UUID admin hiện có'
& $backendPython -m app.scripts.integration_case --repo-root $repoRoot import `
  --manifest data/integration/ORTHO_B21CN1_Q_0001.manifest.json `
  --created-by $adminId

& $backendPython -m app.scripts.integration_case --repo-root $repoRoot payload `
  --question-id ORTHO_B21CN1_Q_0001 `
  --student-answer 'Câu trả lời minh họa từ runtime'
```

Importer chỉ đọc catalog/processed/manifest/PDF; không mở training/prepared/test.
Mọi DB write dùng một transaction, không gọi repository tự commit. File được
copy đã kiểm hash, xuất bản độc quyền dưới upload root:
`integration/<source_id>/<sha256>.pdf`. `Document.storage_path` chỉ chứa key này;
đường dẫn repo gốc nằm trong metadata. Không di chuyển hoặc sửa PDF gốc.

Chạy lại ca giống nhau là no-op và không copy thêm file. Cùng external ID mà
khác nội dung, metadata, owner hoặc quan hệ sẽ báo conflict, không ghi đè hoặc
tự nối lại phần dữ liệu bị thiếu. Chỉ hỗ trợ một manifest nguồn/locator chung
trong đợt này; chưa phải importer tổng quát cho nhiều ca dùng chung tài liệu.

File đã có không bị xóa. Khi commit lỗi, chỉ xóa file mới do invocation tạo nếu
một transaction mới xác nhận không Document nào tham chiếu key. Nếu không xác
minh được kết quả commit, giữ file để tránh mất dữ liệu; retry có thể tái sử dụng
file đó. Cần filesystem hỗ trợ hard link cho thao tác xuất bản file độc quyền;
không hỗ trợ thì import thất bại và DB rollback, không fallback ghi đè.

Payload chỉ gồm `question`, `student_answer`, `rubric`, `evidence`, không có gold,
reference_answer hoặc toàn bộ import_metadata. Reader CLI dùng snapshot read-only;
không gọi model. Hàm `medical_payload(session, external_id, student_answer)` dành
cho caller đã mở transaction nhất quán.

## Tests

Từ `apps/backend`:

```powershell
# Chỉ trỏ tới DB PostgreSQL biệt lập tên medresident_test_*.
# Fixture XÓA schema public của chính DB thử nghiệm này trước mỗi test.
$testDbSecret = Read-Host 'URL PostgreSQL thử nghiệm biệt lập' -AsSecureString
$env:INTEGRATION_TEST_DATABASE_URL = [System.Net.NetworkCredential]::new('', $testDbSecret).Password
& $backendPython -m pytest postgres_tests tests -q -rs
& $backendPython -m ruff check app tests postgres_tests alembic
```

API tests cũ dùng SQLite; chúng không chứng minh JSONB/migration PostgreSQL.
Importer tests dùng PostgreSQL thật và chạy DDL 0002 trên baseline liên quan;
chỉ loại `document_chunks` khỏi fixture khi không có vector và bypass riêng
full-schema preflight trong test. Không có production bypass. Các test full
0001→0002 và bảo toàn dữ liệu legacy qua chuỗi migration sẽ skip có lý do khi
PostgreSQL thiếu pgvector. Không được coi các skip này là đã xác minh migration.

Ca mẫu đòi PDF gốc tại đường dẫn manifest; fixture chỉ hard-link file trong vùng
tạm, không thay đổi bản gốc. Kiểm tra gồm no-op, nội dung/quan hệ conflict,
missing reference/hash/admin, lỗi giữa transaction, lỗi commit trước/sau khi DB
đã commit, bảo toàn file cũ, JSONB/FK/check constraints và so sánh pure builder pilot.
