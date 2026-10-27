# Pipeline và route MedResident Tutor — 22/10/2026

> Đây là bản ghi trước sửa. Validation/error handling, logout/hết phiên, idempotency FE và trang kết quả đã được bổ sung và kiểm tra browser E2E; xem phần “Hoàn thiện luồng local” trong [local-practice.md](local-practice.md). Các phần refresh/revocation, audit retry đầy đủ, readiness provider và model thật vẫn chưa triển khai.

## Kết luận và bằng chứng

Chưa hoàn chỉnh toàn hệ thống. Luồng luyện tập local dùng Medical/Teaching mock đã có persistence; các pipeline model thật, ingestion/retrieval, thi và tiến độ chưa hoàn chỉnh.

- Kiểm tra lại: 35 test PostgreSQL, 16 test backend, 42 test Medical CPU PASS (93 test). PostgreSQL test dùng container riêng medresident-audit-test-20261022, pgvector/pgvector:pg16, localhost:55439, tmpfs riêng; không dùng volume ứng dụng. Container test được dọn sau kiểm tra.
- HTTP local: health/ready/login admin và các API đọc trả 200; 8 trang frontend trả 200. Chưa test trình duyệt tương tác. TypeScript/ESLint/build đã PASS ở lượt triển khai trước, không chạy lại trong audit này.
- DB phát triển: revision 20261022_0003, vector 0.8.7, schema drift check PASS. Có 1 user, 1 Document, 1 Question, 1 Rubric, 2 criteria, 1 SourceUnit, 2 mapping criterion–SourceUnit, 1 practice attempt completed/mock. LearningResult và các bảng thi/taxonomy/retrieval còn rỗng. Snapshot hash và PDF storage hash khớp.
- Runtime development/mock; chưa cấu hình đủ HTTP Medical/Teaching. Không gọi GPU/RunPod, tải weights hoặc đọc locked test. Không migration/seed/import/nộp bài mới vào DB phát triển trong audit.

## Pipeline và chức năng

| Pipeline | Trạng thái |
|---|---|
| Đăng ký, đăng nhập, JWT, active user, admin authorization | Có API/test; admin login HTTP PASS; lỗi invalid email bên dưới |
| Import Question→Rubric→Criterion→SourceUnit→Document | Có importer/reader/DB; ca ORTHO_B21CN1_Q_0001 đã có |
| FE→BE→Medical mock→validate→persist→Teaching mock→guards→persist | MVP hoạt động, điểm fixture không phải đánh giá năng lực |
| Idempotency, ownership, Teaching retry giữ Medical | Test PostgreSQL/concurrency PASS |
| Lịch sử/reload kết quả | Đọc lại DB qua API PASS; UI có lịch sử và ?attempt=UUID |
| Provenance | DB giữ snapshot/rubric/evidence/hash/PDF/trang in/review metadata; UI chưa hiện đầy đủ |
| HTTP provider thật | Client và MockTransport tests có; chưa gọi hai service thật |
| Medical serving | Code và CPU tests có; chưa artifact/GPU verification; không chạy trong Compose |
| Teaching serving | Chưa có service HTTP thật |
| Upload tài liệu | Lưu file/metadata, kiểm quyền admin; chưa OCR/parse/chunk/index |
| RAG/embedding/retrieval/Neo4j | RAG endpoint dùng mock, retriever trả rỗng; chưa pipeline thật |
| Topic/taxonomy | API list/create/get; create cần Specialty có sẵn; chưa API/UI quản lý Specialty |
| Dashboard, Exams, Progress | Trang placeholder; thi/progress/recommendations mới có ORM/table |
| Huấn luyện/đánh giá offline | Có script Medical/Teaching; không chạy hoặc xác minh GPU trong audit |

## Phát hiện và giới hạn

1. **P1 — invalid email login trả 500 thay vì 422, đã tái hiện HTTP.** POST /api/v1/auth/login với email not-an-email và mật khẩu giả nhận 500. app/modules/auth/schemas.py:19 ném ValueError; app/main.py:58 đưa exc.errors() trực tiếp vào JSONResponse, context exception không JSON-serializable. Chưa sửa; 93 test hiện có chưa bắt ca này.
2. **P2 — định dạng lỗi API/FE chưa thống nhất.** Practice dùng HTTPException/detail, frontend lib/api.ts chỉ đọc error.message; các lỗi 404/409/503 có thể chỉ hiện Request failed.
3. **Auth frontend chưa đủ vòng đời:** token localStorage, chưa logout/refresh/revocation/tự chuyển đăng nhập khi token hết hạn. Login chuyển đến Dashboard placeholder. Nav Documents chưa theo role, nhưng API vẫn kiểm quyền admin.
4. **Idempotency FE chưa bền qua reload/mất response:** key chỉ trong useRef. Backend bảo vệ cùng key đúng, nhưng reload rồi gửi với key mới có thể tạo bài mới nếu request trước đã commit. Chưa có browser/network failure E2E.
5. **UI Medical/provenance chưa đầy đủ:** đang hiện điểm/criteria/reason; chưa hiện riêng correct/incorrect/missing points, sufficient_evidence, evidence_refs. Hiển thị toàn bộ evidence snapshot chưa phân biệt refs model đã dùng; printed pages/hash/review có trong API nhưng chưa hiện UI. Chưa route xem/tải PDF.
6. **Audit retry còn tối thiểu:** stage_error hiện tại bị xóa khi retry; provider metadata chỉ ghi sau stage thành công, chưa có lịch sử đầy đủ các lần lỗi/retry.
7. **Vận hành MVP:** request đồng bộ; process chết cần retry khi lease hết hạn; chưa exactly-once generation nếu chết giữa model response và commit. History tối đa 100, chưa phân trang. Backend /ready chỉ SELECT 1, không xác nhận schema/provider/model readiness.
8. **Chưa sẵn sàng chạy hai model thật:** cần artifact provenance/snapshot/manifest, Medical GPU readiness, service Teaching thật, URL/key/timeout và test HTTP xuyên suốt. Hash tự tính không chứng minh đúng checkpoint pilot.

Ưu tiên trước RunPod: sửa lỗi 500 và hợp đồng lỗi; browser E2E login→submit→reload→Teaching retry; giữ idempotency key qua lỗi mạng/reload. Exams/Progress/ingestion không bắt buộc cho một ca pilot nhưng phải được đánh dấu chưa triển khai.

## Toàn bộ route frontend

Base http://localhost:3000. Không có Next.js route.ts API tùy biến.

| Route | Chức năng | Trạng thái |
|---|---|---|
| / | Giới thiệu, link đăng ký/đăng nhập | Trang tĩnh |
| /register | Tạo learner, tự login, lưu JWT | Có |
| /login | Đăng nhập | Có |
| /dashboard | Tổng quan | Placeholder |
| /learn | Chọn câu hỏi/trả lời/Medical/Teaching/evidence/lịch sử/retry | MVP mock; ?attempt=UUID |
| /exams | Thi | Placeholder |
| /progress | Tiến độ/gợi ý | Placeholder |
| /admin/documents | Upload PDF/TXT/Markdown | Có upload; chưa quản lý/ingestion đầy đủ |

## Toàn bộ endpoint backend chính

Base http://localhost:8000/api/v1. User = JWT user active; Admin = thêm role ADMIN; Owner = chỉ dữ liệu của chính user.

| Method | Route sau /api/v1 | Quyền | Chức năng |
|---|---|---|---|
| GET | /health | Public | Liveness |
| GET | /ready | Public | DB connectivity |
| POST | /auth/register | Public | Tạo learner |
| POST | /auth/login | Public | Cấp JWT |
| GET | /auth/me | User | User hiện tại |
| GET | /topics | User | List, limit/offset |
| POST | /topics | Admin | Tạo topic gắn Specialty |
| GET | /topics/{topic_id} | User | Chi tiết topic |
| GET | /documents | User | List metadata tài liệu |
| POST | /documents/upload | Admin | Lưu file/metadata |
| GET | /documents/{document_id} | User | Metadata, không trả PDF |
| POST | /ai/rag/query | User | RAG mock/empty retrieval |
| GET | /practice/config | User | execution_mode |
| GET | /practice/questions | User | ID/nội dung câu hỏi, không rubric/reference/gold |
| GET | /practice/questions/{question_id} | User | ID chuỗi/nội dung câu hỏi |
| POST | /practice/attempts | User | Nộp bài, Idempotency-Key bắt buộc |
| GET | /practice/attempts | Owner | 100 bài gần nhất |
| GET | /practice/attempts/{attempt_id} | Owner | Kết quả/evidence/provenance snapshot |
| POST | /practice/attempts/{attempt_id}/retry | Owner | Retry giai đoạn lỗi/claim hết hạn |

19 operations trên 17 paths. FastAPI tự sinh thêm GET /openapi.json, /docs, /docs/oauth2-redirect, /redoc (public, ngoài prefix). Backend không đăng ký GET / hoặc GET /api/v1; 404 tại đây không có nghĩa backend hỏng.

Không có API users/specialties/question/rubric/SourceUnit CRUD, exams, progress, recommendations, logout/refresh hoặc tải PDF. Có ORM không đồng nghĩa có API/chức năng tương ứng.

## Medical service riêng

Chưa chạy trong stack local; README đề xuất cổng 8001.

| Method | Route | Quyền | Chức năng |
|---|---|---|---|
| GET | /health | Public | Liveness |
| GET | /ready | Public | Base/adapter đã load đúng |
| POST | /medical/evaluate | X-API-Key | Inference/validation/metadata/timing |

Có docs/OpenAPI FastAPI tự sinh. Chưa có /teaching/evaluate đã triển khai; HTTPProvider chỉ chuẩn bị gọi endpoint tương lai này.

## CLI và root thư mục

- app.scripts.seed --admin-only: seed admin từ cấu hình.
- app.scripts.integration_case import: manifest/repo root/admin UUID, transaction/idempotency/hash.
- app.scripts.integration_case payload: question external ID và student_answer runtime → Medical payload, không model.
- Alembic: migration có drift guard, không tự migration khi Compose startup.

| Root | Vai trò |
|---|---|
| apps/backend | FastAPI, ORM, Alembic, integration CLI/tests |
| apps/frontend | Next.js UI và backend client |
| services/medical | Medical serving tách biệt |
| model-training | Script/prompt/validator offline Medical/Teaching |
| data | Nguồn/dataset/manifest/uploads/backups; không đọc locked test trong audit |
| docs | Hướng dẫn/báo cáo |
| infra | Khung hạ tầng |
| scripts | Tiện ích kiểm tra; không kết nối Neo4j trong audit |
| repo root | Compose, cấu hình, README, Makefile |

Lượt audit chỉ thêm báo cáo này; không sửa code để che lỗi, không commit/push.
