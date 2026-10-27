# Luồng luyện tập local

Từ thư mục repo `C:\WORKS\STUDY\MedResident-Tutor` (PowerShell, Docker Desktop đang chạy):

```powershell
docker compose up -d --build db backend frontend
```

- Đăng nhập: http://localhost:3000/login bằng admin local hiện có (SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD).
- Admin seed có miền `.local` được chấp nhận đúng theo SEED_ADMIN_EMAIL trong development; không đổi tài khoản/quyền/mật khẩu và không mở rộng đăng ký email .local.
- Luyện tập và lịch sử: http://localhost:3000/learn ; `?attempt=<UUID>` mở lại kết quả từ DB.
- API/OpenAPI: http://localhost:8000/docs ; prefix `/api/v1`.
- Backend Compose kết nối `db:5432`; CLI Windows dùng `localhost:5433`.
- Lệnh trên không tự migration/seed/import. Revision cần có: `20261022_0004`.
- Sau khi đã sao lưu và xác nhận DB đích, chạy migration tương lai bằng `docker compose exec backend alembic upgrade head`. Không stamp/reset/drop volume.

## Chế độ mock

Backend mặc định `APP_ENV=development`, `PRACTICE_PROVIDER=mock`, `PRACTICE_MOCK_SCENARIO=success`.
Đặt các biến này trong `.env` rồi áp dụng bằng:

```powershell
docker compose up -d --force-recreate backend
```

Các scenario: `success`, `medical_error`, `medical_invalid`, `teaching_error`, `teaching_invalid`, `timeout`, `busy`.
- `medical_error` / `teaching_error`: lỗi lần xử lý ban đầu; retry chủ động được phép thành công.
- `medical_invalid` / `teaching_invalid`: output bị validator từ chối, không lưu làm kết quả hợp lệ.
- `timeout` / `busy`: lỗi cố định; đổi scenario rồi retry để phục hồi.
- Chỉ cấu hình backend chọn scenario; request người học không có field điều khiển provider/lỗi.
- Mock bị từ chối ngoài development. Không fallback HTTP → mock. Không retry bài mock bằng HTTP hoặc ngược lại; tạo bài mới sau khi đổi chế độ.
- Điểm fixture luôn 0, danh sách tiêu chí lấy từ request; không dựa trên từ khóa hoặc đánh giá câu trả lời. Đây không phải chấm năng lực.
- UI và record có `execution_mode=mock`. Luồng này không ghi LearningResult/mastery, kể cả khi dùng HTTP.

## API

Tất cả endpoint yêu cầu Bearer token từ `/auth/login`:

| Method | Path sau /api/v1 | Ý nghĩa |
|---|---|---|
| GET | /practice/config | Chỉ trả execution_mode |
| GET | /practice/questions | ID và nội dung câu hỏi có rubric/evidence trực tiếp |
| GET | /practice/questions/{external_id} | ID và nội dung; không rubric/reference/gold |
| POST | /practice/attempts | `{question_id, student_answer}` + header `Idempotency-Key` (1–128 ký tự) |
| GET | /practice/attempts | Tối đa 100 bài gần nhất của user hiện tại |
| GET | /practice/attempts/{uuid} | Kết quả lưu DB, snapshot evidence và provenance |
| POST | /practice/attempts/{uuid}/retry | Retry giai đoạn lỗi/claim hết hạn; giữ Medical hợp lệ |

Submission trả record với `status`, `medical_evaluation`, `teaching_feedback`, `stage_error`, `execution_mode`, `provider_metadata`, `snapshot_hash`, `evidence`, `provenance`. Lỗi provider được lưu trong record (`medical_failed`/`teaching_failed`); HTTP 200 cho record đã tiếp nhận, không đồng nghĩa chấm thành công. Auth thiếu 401; không sở hữu 404; key trùng input khác 409.

Request chạy đồng bộ nhưng mỗi giai đoạn commit riêng. Không giữ transaction khi chờ provider. Unique(user_id,idempotency_key), hash input và INSERT ON CONFLICT bảo vệ gửi trùng giữa nhiều request/process. Row lock + claim UUID + lease kiểm soát retry đồng thời; response trễ không ghi đè claim mới. Không có queue ngoài. Nếu process chết, người dùng retry sau khi lease hết hạn (timeout + 10 giây). Provider thật không có đảm bảo exactly-once khi process chết sau generation nhưng trước commit; không tự retry ngầm.

Snapshot JSONB giữ nguyên Medical input, evidence, locator PDF/trang in, source hash và metadata review nhập từ dataset; SHA-256 canonical gắn với snapshot. Kết quả đọc lịch sử không phụ thuộc rubric hiện tại. Không nâng review flag. Không tạo Exam, Topic hay Specialty giả.

## Nối API thật sau này

Đặt trên backend, không đưa key vào frontend:

```dotenv
PRACTICE_PROVIDER=http
PRACTICE_TIMEOUT_SECONDS=120
MEDICAL_SERVICE_URL=https://<medical-service-origin>
TEACHING_SERVICE_URL=https://<teaching-service-origin>
MEDICAL_SERVICE_API_KEY=<secret>
TEACHING_SERVICE_API_KEY=<secret>
```

HTTP client đã có; không cần đổi DB/FE hoặc orchestration. Medical dùng `POST /medical/evaluate` với đúng 4 field reader: question/student_answer/rubric/evidence; nhận medical_evaluation/model_metadata/timing theo service hiện có. Teaching cần một endpoint thật `POST /teaching/evaluate`, nhận Teaching schema v1 (schema_version 1.0.0, question, student_answer, medical_evaluation, learner_context, metadata), trả teaching_feedback/model_metadata/timing. Teaching service thật chưa triển khai trong bước này. Context hiện rỗng; metadata chương trình chưa xác minh để null, course_id chỉ lấy từ rubric dataset. Khi dựng prompt Teaching phải tiếp tục dùng builder pilot, không đưa schema_version/gold vào prompt.

Cả hai gửi X-API-Key, timeout hữu hạn; busy/timeout/lỗi JSON/HTTP thành stage_error. Medical dùng validator CPU dùng chung với serving (`model-training/src/medical/validation.py`); Teaching dùng contract_errors/input_errors/prediction_metrics và apply_teaching_guards nguyên logic pilot, không tải dataset/model. Cần service thật/artifact đúng, mạng/TLS và timeout phù hợp GPU để kiểm chứng thực tế; chưa gọi dịch vụ ngoài.

## Kiểm tra và bàn giao lần này

- PostgreSQL biệt lập image pgvector/pgvector:pg16, cổng 55439, tmpfs riêng; không dùng volume ứng dụng.
- Migration baseline/head và 0002→0003 bảo toàn dữ liệu; drift vẫn chặn.
- Backend tests: API auth/ownership, idempotency đồng thời, validation, Teaching retry không chấm Medical lại, DB reload/history, không ghi mastery; HTTP provider test bằng MockTransport không gọi mạng.
- Kết quả tự động: 35 test PostgreSQL PASS; 16 test backend PASS; 42 test Medical CPU PASS; Ruff, TypeScript, ESLint và production build PASS.
- Medical service: test CPU giả runner, không GPU.
- Frontend: TypeScript, ESLint, production build; HTTP /learn kiểm tra riêng. Chưa kiểm tra thao tác trong browser tương tác.
- DB phát triển: backup `data/backups/medical_learning_pre_practice_20261022_084040.dump`, kiểm tra pg_restore --list trước migration; 0002→0003, fingerprint dữ liệu cũ giữ nguyên. Backup đã được gitignore.
- HTTP smoke local PASS cả login admin, bảo mật câu hỏi, submit, idempotency, đọc lại/lịch sử; PDF trong upload storage hash khớp và LearningResult vẫn 0.
- HTTP smoke local tạo một bài mock của admin với key `local-pipeline-smoke-20261022-v1`; giữ để xem ở lịch sử. Không xóa hoặc ghi vào pilot dataset.
- Container/volume phát triển giữ lại. Tài nguyên test biệt lập được dọn sau kiểm tra.
- npm ci báo audit trên dependency hiện có; không tự cập nhật package/lock trong bước này.

Các thay đổi chính: `app/modules/practice/*`, migration `20261022_0003_practice.py`, registry models/router/settings, schema drift guard hỗ trợ revision mới, shared Medical validator, trang `app/learn/page.tsx`, Dockerfiles/context và `.env.example`. Không sửa dataset, không gọi model, không commit/push.


## Hoàn thiện luồng local và Browser E2E (22/10/2026)

Đã bổ sung validation JSON an toàn/HTTPException envelope; API client chung phân loại network/auth/validation/processing, lỗi theo trường; login quay lại đường dẫn nội bộ trong allowlist; logout client và xử lý 401/idle expiry; bản nháp/pending submission theo UUID user đã xác thực qua /auth/me. Nhãn mock, Medical đầy đủ, trạng thái từng giai đoạn, evidence_refs, trang PDF/trang in và review chưa xác minh đã hiển thị; ID/hash/metadata đặt trong Chi tiết nguồn. Không có migration mới.

### Tự kiểm tra local trong 3 thao tác

Tại repo root chạy `docker compose up -d --build backend frontend` nếu service chưa chạy.

1. Mở http://localhost:3000/login, đăng nhập admin local hiện có; trang đích mặc định là /learn. Email sai định dạng có thông báo tại trường và HTTP 422.
2. Chọn câu hỏi, nhập câu trả lời, gửi. Xem Medical/Teaching và nguồn; reload hoặc chọn lịch sử vẫn mở đúng bài. Gửi lại nội dung của lần nộp đã biết mở bài cũ; bấm Tạo lượt mới để cố ý tạo lần nộp mới.
3. Soạn bản nháp rồi Đăng xuất, đăng nhập lại cùng tài khoản để kiểm tra bản nháp. Tài khoản khác không nhận được bản nháp hoặc dữ liệu bài cũ. Khi hết phiên, đăng nhập lại quay về trang nội bộ đang làm.

### Lưu trữ/idempotency và logout

- Trước POST, lưu `{key,payload}` vào localStorage theo `practice:v1:<user-uuid>`. Mất response/timeout không đổi key; sau reload dùng Gửi lại lần nộp đang chờ để backend trả bài hiện có. Khi nhận attempt_id, lưu ID trước khi đổi URL; lần sau GET bài đó.
- Sửa payload tạo key mới khi nộp; Tạo lượt mới xóa pending của lượt hiện tại và cho phép tạo lượt mới dù nội dung giống lần trước. Không có auto-retry generation.
- Bản nháp và pending được giữ theo tài khoản trên trình duyệt này; không đồng bộ thiết bị, không mã hóa trong localStorage. App chỉ hydrate sau khi backend xác nhận user; đổi token ở tab khác sẽ xóa state hiển thị và reload. Không lưu mật khẩu/API key.
- Đăng xuất chỉ xóa token client, không thu hồi JWT server. Chưa có refresh token hoặc revocation. /auth/me và API backend vẫn là nguồn xác thực; expiry timer phía client chỉ hỗ trợ UX.
- Mọi validation response chỉ có loc/type/msg an toàn; không gửi input/ctx/exception. Unexpected exception trả mã chung và chỉ log sự kiện cùng request ID, không log exception/answer/password. Chi tiết lỗi stage tiếp tục lưu theo cơ chế hiện có.

### Chạy lại test browser biệt lập (PowerShell, repo root)

Cần Docker Desktop. Test dùng Compose project riêng, PostgreSQL tmpfs riêng, upload volume riêng; không dùng .env/database/volume phát triển. Browser Chromium thật chạy trên image Playwright v1.56.1, API/Next.js/PostgreSQL đều thật, chỉ model mock.

```powershell
$env:E2E_MOCK_SCENARIO = 'success'
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml up -d --build db backend frontend
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml exec -T backend python -m alembic upgrade head
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml exec -T backend python /e2e/seed.py
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml run --rm --no-deps browser npm ci
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml run --rm --no-deps browser npm run test:e2e
$env:E2E_MOCK_SCENARIO = 'teaching_error'
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml up -d --force-recreate backend
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml run --rm --no-deps -e E2E_SUITE=retry browser npm run test:e2e
Remove-Item Env:E2E_MOCK_SCENARIO
docker compose -p medresident-practice-e2e -f compose.practice-e2e.yml down
docker volume rm medresident-practice-e2e_uploads
```

Không thay tên project hoặc dùng lệnh cleanup với Compose phát triển. Bộ test mặc định chọn nhóm success/client; nhóm retry chạy riêng sau khi backend test dùng teaching_error. Nguồn thật chỉ được đọc để importer tạo fixture một ca; không mở locked test. Fixture account/mật khẩu và JWT signing key trong file E2E là public test-only, không dùng cho môi trường phát triển.

### Bằng chứng lần hoàn thiện này

- **Browser E2E: 8 ca PASS**, gồm: invalid email 422/field error; login→submit→results/provenance→reload/history/new attempt; response thật bị ngắt sau commit→reload/gửi lại cùng key không trùng; idle expiry và bản nháp/user isolation/logout; owner protection read/retry; internal redirect guard; backend 401; Teaching failure/retry giữ nguyên Medical/invocation ID.
- **2 client contract tests PASS** trong Playwright runner (parse errors và safe return path; hai test này không phải thao tác browser).
- **13 backend API/error tests PASS**; **11 PostgreSQL practice tests PASS** trên database test riêng. Không lặp bộ migration/Medical GPU tests không bị ảnh hưởng.
- Ruff PASS. TypeScript, ESLint và production build PASS. Browser test dùng request thật; test mất response gọi route.fetch tới backend thật rồi abort response, không fulfill bằng JSON giả.
- Lần chạy browser đầu bắt lỗi randomUUID không có trên HTTP hostname; đã sửa fallback getRandomValues. Labels tách khỏi textarea/error text để field accessible name ổn định khi khôi phục bản nháp. Những ca lỗi đã được chạy lại PASS; không bỏ assertion hoặc skip.
- DB phát triển giữ 1 user/1 question/1 document/1 attempt và LearningResult=0 trong quá trình kiểm tra; không migration/import/seed mới ở DB này. Test fixtures chỉ có trong DB test.

Giới hạn giữ nguyên: xử lý request đồng bộ, timeout/claim cần retry chủ động khi process chết; history tối đa 100; chưa có lịch sử audit đầy đủ từng lần retry. Không có model thật/RunPod, refresh token, thi, dashboard hay ingestion trong đợt này.


### Danh sách file của đợt hoàn thiện

- Backend: `apps/backend/app/main.py`, `apps/backend/app/modules/practice/providers.py`.
- Backend tests: `apps/backend/tests/test_error_contract.py`, `apps/backend/tests/e2e/seed.py`, `apps/backend/postgres_tests/test_practice.py`.
- Frontend pages/style: `apps/frontend/app/learn/page.tsx`, `app/login/page.tsx`, `app/register/page.tsx`, `app/admin/documents/page.tsx`, `app/globals.css` (các đường dẫn app tương đối từ apps/frontend).
- Frontend components: `apps/frontend/components/AuthForm.tsx`, `Nav.tsx`, `PracticeResult.tsx`.
- Frontend shared code: `apps/frontend/lib/api.ts`, `practice-storage.ts`, `practice-types.ts`.
- Browser tests: `apps/frontend/playwright.config.ts`, `apps/frontend/e2e/helpers.ts`, `client.spec.ts`, `practice.spec.ts`, `retry.spec.ts`.
- Cấu hình/dependency: `compose.practice-e2e.yml`, `apps/frontend/package.json`, `package-lock.json`, `.gitignore`, `apps/frontend/.dockerignore`. Chỉ thêm Playwright test dependency; bảo toàn metadata platform và phiên bản các package hiện hữu. `tsconfig.tsbuildinfo` là cache typecheck sinh ra, không phải thay đổi nghiệp vụ.
- Hướng dẫn: `docs/local-practice.md`, ghi chú cập nhật ở `docs/system-pipeline-route-audit.md`.

FE/BE phát triển đã được build/chạy lại. Kiểm tra HTTP trên stack phát triển: email invalid trả 422 an toàn, admin login 200, provider mock, lịch sử vẫn 1 bài cũ. Tài nguyên E2E container/network/upload volume đã dọn đúng project riêng; container/volume phát triển giữ nguyên. Không commit/push.
