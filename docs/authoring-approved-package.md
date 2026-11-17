# Biên soạn câu hỏi và gói chấm đã duyệt

Ngày triển khai: 12/11/2026. Đây là chức năng ứng dụng, không phải đợt benchmark mới.

Mở http://localhost:3000/admin/questions bằng tài khoản ADMIN hiện có. LEARNER không được gọi các API authoring, kể cả gọi trực tiếp ngoài giao diện.

## Cách dùng

1. Tạo câu hỏi, nhập đề, chủ đề và tổng điểm. Học phần là nhãn tổ chức; chưa dùng tên môn để suy phạm vi kiến thức hay lọc cứng sách.
2. Chọn **Tìm tài liệu liên quan**. Đọc cả đoạn nguồn, tên sách, năm và trang PDF; chọn/bỏ các đoạn. Gợi ý retrieval chưa phải xác nhận chuyên môn.
3. Khi model tắt, chọn **Dùng nguồn để soạn thủ công**, viết đáp án và tiêu chí, chọn evidence cho từng tiêu chí. Có thể lưu nháp chưa có tiêu chí/evidence; nháp không xuất hiện cho học viên.
4. Khi worker được bật, **Đề xuất đáp án và tiêu chí** dùng câu hỏi và các nguồn đã chọn. Model không tự phát hành. Admin sửa nội dung, điểm và nguồn rồi lưu.
5. **Đưa vào sử dụng** là hành động admin chấp nhận biên soạn/phát hành. Hệ thống yêu cầu đáp án, rubric hợp lệ và nguồn cho từng tiêu chí. Đây không phải xác nhận bác sĩ/chuyên gia duyệt.
6. Sửa bài đã phát hành tạo một Question mới làm revision nháp. Bài cũ còn khả dụng đến khi revision mới được phát hành; lúc đó bài cũ được ngừng dùng cho lượt mới. Hai bản nháp cạnh tranh không thể cùng thay thế một revision đã bị thay thế.

Đề, chủ đề, học phần hoặc tổng điểm đổi sau retrieval thì phải tìm lại trước khi gọi model. Proposal có chữ ký và được ràng buộc với phạm vi câu hỏi; backend từ chối proposal thuộc đề khác. Bản sửa đáp án/tiêu chí của admin được lưu riêng với proposal gốc. Khi tiếp tục chỉnh bản nháp sau khi mở lại, metadata giữ proposal cũ và đánh dấu có thể đã cũ; admin cần kiểm tra lại căn cứ.

## Tái sử dụng dữ liệu và phiên bản

Không thêm bảng hoặc migration. Tái sử dụng Question, Rubric, RubricCriterion, SourceUnit và RubricCriterionSourceUnit.

| Vị trí | Nội dung |
| --- | --- |
| Question.reference_answer | Đáp án admin đang biên soạn |
| Question.import_metadata.authoring | Học phần/chủ đề, proposal gốc có phiên bản, người lưu |
| previous_revision / revision_number | Chuỗi revision; mỗi lần sửa bản đã duyệt tạo Question ID mới |
| approved_package | Payload chấm cố định, đáp án, provenance, người/thời điểm admin duyệt, SHA-256, revision ID |
| SourceUnit AUTH_SU_* | Đúng đoạn được chọn, hash nội dung, năm/sách/trang, provenance corpus/KG |
| PracticeAttempt.snapshot | Payload, provenance, gói và revision đã dùng, trace và hash riêng của attempt |

Nguồn corpus RB1_* không bị giả định là đã tồn tại trong PostgreSQL. Materialize chỉ đồng bộ các đoạn được chọn, sinh ID theo hash và dùng advisory lock để đồng bộ idempotent. Không dùng ID node KG thay ID SourceUnit. Document AUTH_DOC_* là bản ghi nguồn của snapshot; không giả vờ sao chép PDF vào storage. Đọc đoạn nguồn được hỗ trợ; việc tải PDF gốc qua ID AUTH_DOC_* chưa được triển khai.

Bundle/proposal dùng chữ ký backend, hết hạn sau hai giờ. Không đưa JWT secret hoặc cấu hình model nội bộ vào frontend. SourceUnit có hash bất biến; sửa nội dung trực tiếp ngoài ứng dụng bị kiểm tra khi phát hành. Package có hash riêng và được kiểm tra trước khi tạo attempt. Source/version của package được pin bằng snapshot, không tự cập nhật theo corpus mới.

## Retrieval và model

Authoring dùng BookIndex, semantic encoder E5 và PracticeBookRetriever/source resolver hiện có. Câu hỏi mới không cần ID benchmark: backend tìm tối đa ba concept bằng phrase của name/title/alias trong đề/chủ đề, rồi đọc tối đa một hop và 24 quan hệ qua Neo4jEvidenceRepository. Các truy vấn read-only, tham số hóa, có timeout. Course không phải bộ lọc cứng. Nếu KG không kết nối được/không có alias phù hợp, fallback vector có lý do trong trace; không kết luận sách thiếu nội dung. Chọn ít nguyên đoạn hơn để giữ context budget, không cắt điều kiện cuối đoạn.

Prompt/schema `authoring-v1` là tác vụ riêng. Worker tùy chọn dùng base Qwen3-4B-Instruct-2507 đã có cache, không gắn adapter Medical. Không sử dụng `/medical/evaluate` để soạn đáp án. Schema kiểm evidence IDs, điểm và tổng điểm; không có evidence thì không gọi model. Validation cấu trúc không chứng minh đúng chuyên môn.

## Khi học viên nộp

Nhánh approved_package được ưu tiên trước vector/hybrid. Backend lấy payload và evidence trong package PostgreSQL, thay student_answer của attempt rồi gửi Medical. Đáp án tham khảo nằm trong metadata rubric được contract V1 cho phép; giữ nguyên bốn trường cấp đầu question/student_answer/rubric/evidence và prompt/guard V1. Đáp án tham khảo không thay evidence hoặc bắt buộc học viên dùng cùng câu chữ.

Trace ghi `effective_strategy=approved_package`, `data_source=postgresql_approved_package`, `neo4j_queries=0`, `vector_search=false`, revision và package hash. Package thiếu/hỏng bị từ chối, không fallback sang truy xuất. Các nhánh vector/hybrid và V2 chấm xác định vẫn được giữ.

Catalog học viên không lộ đáp án/rubric. Sau khi có MedicalEvaluation, chỉ chủ attempt được xem evidence và đáp án tham khảo của revision đã làm. Teaching lỗi vẫn giữ MedicalEvaluation và hiển thị trạng thái từng stage. Không cập nhật kết luận Medical để vượt guard.

## Chạy local

Môi trường đã áp dụng dùng:

```powershell
Set-Alias docker 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
docker compose -f docker-compose.yml -f docker-compose.authoring.yml up -d --build backend frontend
```

Override chỉ phục vụ retrieval CPU, tái sử dụng volume venv local; không nạp GPU. Provider chấm và MODEL_CALLS_ENABLED được giữ như trước. `AUTHORING_PROVIDER` mặc định `off`, tách khỏi provider chấm.

Khi RAM trống ít nhất 6 GiB và không có worker GPU khác:

```powershell
python -m local_model_testing.authoring_runtime start
$env:AUTHORING_PROVIDER='local_http'
$env:AUTHORING_SERVICE_URL='http://host.docker.internal:8103'
docker compose -f docker-compose.yml -f docker-compose.authoring.yml up -d --no-build backend
```

Worker mất thời gian nạp model; chờ log worker báo Uvicorn sẵn sàng trước khi nhấn đề xuất. Không có smoke generation. Ledger riêng `data/authoring/local-v1-20261112/ledger.sqlite3` khóa tối đa hai attempt và append category authoring vào ledger tổng nếu tồn tại; không mở lại các run đã đóng. Output kém/invalid vẫn tính attempt, không retry tự động.

```powershell
python -m local_model_testing.authoring_runtime stop
$env:AUTHORING_PROVIDER='off'
docker compose -f docker-compose.yml -f docker-compose.authoring.yml up -d --no-build backend
```

Lệnh stop chỉ dừng container có nhãn sở hữu của task. Không xóa weights/adapter/cache/venv; không tự dừng ứng dụng khác. Khi tắt provider, tiếp tục soạn thủ công.

## Kiểm chứng và giới hạn

52 kiểm thử CPU/PostgreSQL đã qua: schema/nguồn giả, proposal ràng buộc đề, replay HTTP, đồng bộ idempotent, lưu nháp/phát hành/revision, lịch sử bất biến, phân quyền, evidence thực tế trong payload Medical, Teaching lỗi giữ Medical, cùng hồi quy retrieval/contract/V2. Test chấm package đặt bộ tìm kiếm thành hàm phát lỗi nếu bị gọi và vẫn hoàn thành Medical. Không chạy benchmark hoặc thay expected.

Browser kiểm thử trên DB `medresident_test_authoring_20261112`: đăng nhập thật, tìm nguồn replay, đề xuất replay, admin sửa/lưu/phát hành, học viên nộp, xem kết quả và reload history. Authoring replay và Medical/Teaching mock được ghi nhãn; không phải model live. Typecheck và production build frontend đã qua. Ảnh desktop/mobile đã được kiểm tra, không tràn ngang tại 390px.

Hai bản nháp nguồn thật đã được tạo trong DB ứng dụng, tìm bằng **Nháp minh họa nguồn**. Dùng hai sách khác nhau, semantic retrieval thật trên CPU; phần đáp án là nguyên đoạn nguồn để admin biên soạn, chưa phải lời giải LLM/chuyên gia và chưa phát hành. Chi tiết ID/trace: `data/authoring/checks-20261112/demo-drafts.json`.

Neo4j hiện trả ServiceUnavailable trong hai lần tìm nguồn thật; đã fallback vector có nhãn, mỗi lần lấy ba đoạn ứng viên. Đường tìm alias/quan hệ trên Neo4j trực tiếp cần kiểm chứng thêm khi instance được bật. Chưa có căn cứ để tuyên bố mapping KG mới đã chạy live thành công.

Kiểm tra lại sau khi người dùng bật Neo4j ngày 12/11/2026: kết nối read-only thành công, có 3959 node MedicalConcept/Skill. Gọi API admin thật cho hai câu hỏi mới: cả hai HTTP 200, effective_strategy=hybrid, kg_contributed=true, không có fallback/discovery error; mỗi câu lấy ba đoạn nguồn. Câu thứ nhất đọc 12 node/9 quan hệ, câu thứ hai 14 node/12 quan hệ, mỗi lần ba truy vấn Neo4j (một tìm concept và hai lookup). Thời gian lần lượt 19,180 giây (có nạp encoder CPU) và 0,399 giây. Bằng chứng mới: `data/authoring/neo4j-recheck-20261112/report.json`. Hai bản nháp không thay đổi, không có inference LLM; đoạn ServiceUnavailable phía trên mô tả lần kiểm tra trước khi instance được bật.

Authoring live chưa kiểm chứng: RAM đo khi chuẩn bị nạp chỉ 1,69 GiB, dưới ngưỡng 6 GiB; startup guard chặn trước khi tải model, 0 inference mới. Không dùng dịch vụ trả phí. Ledger tổng vẫn 556; model/adapter/prompt chấm và artifact nghiên cứu lịch sử được giữ nguyên. Không có worker authoring chạy tự động.

Artifacts mới: `data/authoring/checks-20261112/{results.xml,tests.log,browser.log,admin-desktop.png,admin-mobile.png,demo-drafts.json}` và `data/authoring/local-v1-20261112/startup.json`. Mã chính: `modules/questions/authoring.py`, service/router/schemas câu hỏi, nhánh package trong practice/service.py, AuthoringPanel, form admin và PracticeResult. Không commit/push Git.

Bằng chứng payload Medical và trace không truy xuất khi chấm: `data/authoring/checks-20261112/approved-package-proof.json`. Worker kiểm thử đã dừng; FE/BE/DB được giữ chạy. Kiểm tra cuối: trang admin và OpenAPI đều HTTP 200, không có worker authoring/browser còn chạy; VRAM dùng 698 MiB, trống 7198 MiB.

Cấu hình model từ xa được chuẩn bị sau đó: xem [RunPod model API](runpod-model-api.md). Authoring hỗ trợ thêm `openai` và `service_http`; remote inference cần công tắc MODEL_CALLS_ENABLED. Các kết quả kiểm thử authoring local ở trên vẫn mô tả đúng đợt chạy trước.
