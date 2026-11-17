# Luyện tập ca bệnh có cấu trúc

Hoàn tất ngày 10/11/2026. Hai demo chạy trên FE → BE → PostgreSQL local thật,
không cần Medical/Teaching service. Đây là **chấm bài tập có cấu trúc theo đáp án
đã biên soạn**, không phải bằng chứng model chấm tự luận chính xác hoặc đọc hiểu ảnh.
Đáp án đã đối chiếu nguồn local; **chưa được chuyên gia duyệt**, chưa dùng để xác
nhận năng lực thực hành hay chấm điểm chính thức của học phần.

## Mở bài

Đăng nhập bằng tài khoản web của bạn tại http://localhost:3000/login rồi mở:

- [Ca bệnh 01 — structured](http://localhost:3000/learn?question=CLINICAL_DEMO_V2_CASE01)
- [X-quang 01 — structured](http://localhost:3000/learn?question=CLINICAL_DEMO_V2_XR01)

Chọn đáp án từng phần, có thể nhập giải thích ngắn, rồi **Gửi câu trả lời**.
Không bắt buộc chọn đủ; bỏ trống có trạng thái riêng. Kết quả gồm điểm, lựa chọn
đã nộp, nhận xét, đáp án, giải thích, trích đoạn nguồn và nội dung nên ôn.
Sau nộp, biểu mẫu khóa; **Tạo lượt mới** bắt đầu lượt độc lập. Lịch sử giữ nguyên
phiên bản và kết quả kể cả khi đề hiện tại thay đổi. Không ghi mastery.

Ảnh XR chỉ đặt lưới trên ảnh số 1. Nhãn `hàng,cột`, bắt đầu từ 1; hàng từ trên
xuống, cột từ trái sang. **Xem ảnh 1 lớn với lưới** giữ nguyên cách tính và có thể
đóng bằng Esc. Không xoay/lật/crop ảnh. Box nguồn chỉ xuất hiện sau nộp.

Review nội bộ chứa lời giải, mở trực tiếp, không đưa lên API học viên:

```powershell
Start-Process .\data\clinical-cases\exercises\review.html
```

## Phạm vi và chính sách điểm

| Bài | Phần tính điểm | Đáp án nguồn | Điểm |
| --- | --- | --- | --- |
| CASE01 | Đoạn xương được mô tả là gãy | Đầu dưới xương quay | 1 |
| CASE01 | Phạm mặt khớp | Có | 1 |
| XR01 | Vùng gãy được nguồn gán nhãn | Có, nhãn fracture | 1 |
| XR01 | Tâm box trên ảnh số 1 | Hàng 2, cột 2 (`r2c2`) | 1 |

Single choice/grid: đối chiếu **ID chính xác** trong phiên bản đề; đúng được
toàn bộ điểm phần đó, sai 0. Không chọn là `unanswered`, khác `incorrect`.
Mọi phần độc lập, mẫu số cố định 2; không có nhánh ẩn khi chọn không có gãy.
Chưa cần multiple choice nên không triển khai công thức điểm từng phần.
Giải thích tối đa 4000 ký tự, giữ nguyên văn bản API nhận được, luôn 0 điểm,
trạng thái `unscored`. Không tìm keyword hay sửa ý học viên bằng model.

| Bài và câu trả lời | Điểm | Nhận xét tương ứng |
| --- | --- | --- |
| CASE01: đầu dưới xương quay + có phạm khớp | 2/2 | Hai lựa chọn khớp đoạn CASE REPORT p005 |
| CASE01: đầu dưới xương quay + không phạm khớp | 1/2 | Phần xương đúng; nguồn ghi intra-articular, khác lựa chọn không phạm khớp |
| CASE01: không phải đầu dưới xương quay + không phạm khớp | 0/2 | Mỗi lựa chọn được đối chiếu với mô tả nguồn, không gán suy luận về hiểu nhầm lâm sàng |
| CASE01: không chọn gì | 0/2 | Hai phần **chưa trả lời**, không ghi là chọn sai |
| XR01: có vùng gãy + hàng 2 cột 2 | 2/2 | Nhãn fracture và tâm box đều trùng annotation |
| XR01: có vùng gãy + hàng 1 cột 1 | 1/2 | Nhận diện đúng; ô chọn khác ô tâm box hàng 2 cột 2 |
| XR01: không có vùng gãy + hàng 1 cột 1 | 0/2 | Hai phần sai; nhận xét nêu cụ thể nhãn và ô đối chiếu |
| XR01: không có vùng gãy + hàng 2 cột 2 | 1/2 | Vị trí vẫn tính độc lập; không tự hủy phần này |
| XR01: bỏ trống vị trí | 0 điểm phần vị trí | “Bạn chưa chọn ô”, khác nhận xét cho một ô sai cụ thể |
| Bất kỳ bài, thêm giải thích đúng/sai/tùy ý | Điểm lựa chọn không đổi | Văn bản chỉ được lưu để xem lại |

Nguồn CASE01: PMC10182394, CASE REPORT p005, XPath và hash XML có sẵn trong
provenance. Chỉ hỏi xương và phạm khớp, không thêm xử trí. XR01: VOC v2, box
`(180,428)–(356,508)` trên ảnh `536×836`; tâm `(268,468)` nằm trong ô `(2,2)`.
Không suy thêm giải phẫu, phân loại, mức độ hay điều trị từ annotation này.

## Dữ liệu thực tế và phiên bản

- `data/clinical-cases/exercises/structured/CLINICAL_DEMO_V2_*.json`: định nghĩa
  private đã biên soạn; `manifest.json` phân biệt hai demo và tám staging.
- `schema_version=structured-v1`, `revision_id` là external ID V2, liên kết về
  `legacy_question_id` V1. Các phần có `id`, `kind`, `label`, `max_score`, options
  với ID ổn định; gold, feedback theo từng option, evidence IDs và review focus
  chỉ lưu ở phía server/review. `correct_option_id` tham chiếu ID, không nhãn.
- ID phần demo: `part_1`, `part_2`, `explanation`. CASE01 dùng single choice cho
  hai phần; XR01 dùng single choice và grid_location. Ô hợp lệ `r1c1`..`r3c3`.
- Importer tái sử dụng `load_bundle`, `CaseInput`, `persist_case`, advisory lock,
  xuất bản file không ghi đè và kiểm source/packet/hash của luồng cũ. Tạo bộ
  Question/Rubric/SourceUnit mới, tái sử dụng byte ảnh và packet nguồn gốc.
  Không tạo Course/Topic, concept hoặc mapping mastery mới.
- Metadata Question chứa `dataset_fields.structured_exercise`; đây là định dạng
  đánh giá nhiều phần, không đổi enum QuestionType cũ hoặc contract model.
- Migration `20261110_0007`: thêm cột JSONB nullable `structured_result` và cho
  phép `execution_mode=structured`. Không xóa/chuyển đổi câu trả lời tự luận cũ.
- Attempt snapshot lưu toàn bộ định nghĩa private, câu trả lời theo ID, rubric,
  evidence/provenance/ảnh và `question_version`, kèm SHA-256. Kết quả đã lưu
  không chấm lại khi GET/history/retry. Nội dung revision structured bị chặn
  chỉnh sửa bằng editor tự luận; thay đáp án phải tạo revision mới.
- Điểm và nhận xét lưu riêng ở `structured_result`; `medical_evaluation` và
  `teaching_feedback` là null. Metadata: `grader=deterministic-v1`,
  `feedback=authored-source-linked-v1`, `model_calls=0`. Không giả tên model,
  latency hay trạng thái Medical/Teaching đã chạy.

Ví dụ body POST `/api/v1/practice/attempts`, kèm Bearer của tài khoản và
`Idempotency-Key` riêng của lượt nộp:

```json
{
  "question_id": "CLINICAL_DEMO_V2_XR01",
  "revision_id": "CLINICAL_DEMO_V2_XR01",
  "structured_answers": {
    "part_1": "o1",
    "part_2": "r2c2",
    "explanation": "Giải thích của học viên; chưa tính điểm."
  }
}
```

Không gửi điểm/đáp án đúng/trạng thái hoặc `student_answer` cho bài structured.
`{}` là bài bỏ trống hợp lệ. Null/missing ID phần hợp lệ là chưa trả lời; ID
field/option/grid lạ, text quá dài hoặc revision sai nhận HTTP 422. Gửi cùng key
và cùng body trả lại attempt đã lưu; đổi body dùng lại key nhận 409. Transaction
lock theo user/key ngăn nộp đồng thời chấm lặp. Không có provider trong transaction.

GET đề dùng whitelist ở server: chỉ bệnh cảnh, ảnh trung tính, câu hỏi, trường
nhập và điểm tối đa. Không gửi gold/rubric riêng/feedback/annotation/evidence
chứa lời giải trước nộp. Ảnh yêu cầu Bearer, hash kiểm tra, private/no-store.
GET kết quả, retry và ảnh lịch sử kiểm chủ sở hữu; tài khoản khác nhận 404.
Không có endpoint public lấy toàn bộ answer key.

Điểm mở rộng nhỏ: Teaching sau này có thể nhận **kết quả đã chấm cùng feedback
đã biên soạn** để diễn đạt lại; trong phiên bản này không gọi và không cần
Teaching để hoàn thành bài. Không nối vào contract model hiện có.

## Tám bài staging

Chỉ biên soạn sau khi hai demo qua E2E. Không import hoặc phát hành:

| ID V2 staging | Phần có nguồn đủ để chấm | Giới hạn |
| --- | --- | --- |
| CASE02 | Trật háng phải ra trước; gãy ổ cối đi kèm | Chỉ phim ban đầu và case text; không thêm phân loại/điều trị |
| CASE03 | ACS; đo áp lực khoang bằng áp kế cầm tay | Theo chẩn đoán và phép đo tác giả xác nhận |
| CASE04 | Thận lạc chỗ trong tiểu khung; rách độ III AAST | Ngoại khoa, chưa gắn vào môn CTCH |
| CASE05 | Ổ dịch/áp-xe sau phúc mạc; thủng tá tràng | Ngoại khoa, chưa gắn vào môn CTCH |
| XR02, XR03, XR05 | Nhãn fracture; tâm box hàng 2 cột 2 | Không suy điều trị/chẩn đoán giải phẫu mới |
| XR04 | Nhãn fracture; tâm box hàng 3 cột 2 | Cùng hệ tọa độ ảnh gốc |

Tất cả giữ hai tiêu chí **vì rubric nguồn trước đó có đúng hai tiêu chí đủ căn
cứ**, không phải ép mỗi bài mới phải có hai phần. Lựa chọn sai ở các ca là phủ
định mệnh đề đã có nguồn, không bịa chẩn đoán khác để đủ số distractor. Đây là
bài nhận biết cơ bản; muốn tăng độ khó/phù hợp BSNT cần chuyên gia soạn thêm.
Không có tiêu chí cũ nào phải tính điểm bằng nguồn thiếu trong mười bản này;
nội dung ngoài phạm vi nguồn vẫn để ngoài phần chấm.

## Thêm bài và chạy lại

Các file chính:

- `apps/backend/app/modules/practice/structured.py`: schema, whitelist và grader.
- `practice/service.py`, `router.py`, `models.py`, `assets.py`: định tuyến, snapshot,
  transaction/idempotency, ownership và projection; luồng tự luận còn nguyên.
- `app/integration/clinical_cases.py`: mở rộng importer với `--structured`.
- `clinical_cases/structured_exercises.py`: cấu hình biên soạn thủ công và tạo JSON.
- `clinical_cases/exercise_review.py`: trang review đủ lựa chọn/điểm/feedback/nguồn.
- `apps/frontend/components/StructuredAnswers.tsx`, `StructuredResult.tsx`,
  `PracticeImages.tsx`, `app/learn/page.tsx`: form, kết quả, ảnh/lưới và lịch sử.
- `apps/frontend/lib/practice-{types,storage}.ts`: contract và bản nháp theo tài khoản.

Để thêm một bài: kiểm nguồn và rubric trước; tạo một revision private hợp schema,
đặt ID phần/option ổn định và ánh xạ đúng evidence/criterion. Biên soạn đầy đủ
feedback đúng, từng option sai và bỏ trống. Chỉ dùng concept đã được xác minh;
nếu chưa có thì để null. Kiểm review trước khi cho phép import ID mới.
Importer hiện **chỉ cho phép hai demo**, nên tám staging chưa thể vô tình import
qua `--structured`. Không chỉnh file một revision đã import để tái sử dụng ID.

```powershell
# Tạo lại 10 định nghĩa từ cấu hình thủ công; không import, không model.
python -m clinical_cases.structured_exercises --staging
& "$env:TEMP/medresident-cases-venv/Scripts/python.exe" -m clinical_cases.exercise_review

# Chỉ chạy sau backup phù hợp nếu có đợt thay đổi mới.
python scripts/import_clinical_demo_local.py --structured

# Kiểm native + integration PostgreSQL cô lập, sau đó tự xóa DB test.
& "$env:TEMP/medresident-web-venv/Scripts/python.exe" -m pytest apps/backend/tests/test_structured_practice.py apps/backend/tests/test_clinical_exercises.py apps/backend/tests/test_practice_contracts.py -q
& "$env:TEMP/medresident-web-venv/Scripts/python.exe" scripts/test_structured_postgres_local.py
```

Docker CLI trên máy này:
`C:/Program Files/Docker/Docker/resources/bin/docker.exe`.
Browser tests: `apps/frontend/playwright.structured.config.ts`, dùng hai tài khoản
review local riêng trong `data/backups/clinical-demo-accounts.json`; không cần
đưa thông tin đăng nhập vào lệnh hoặc báo cáo. Khi chạy trong image Playwright,
mount repo ở `/workspace`, node_modules của frontend và đặt
`CLINICAL_DEMO_ACCOUNTS=/workspace/data/backups/clinical-demo-accounts.json`.
Request bridge chỉ chuyển tiếp tới web/backend thật, không tạo đáp án giả.
Sau test, `python scripts/cleanup_structured_browser.py` chỉ dọn attempt mà
run browser đã ghi ownership; không dùng công cụ đó để xóa bài của người dùng.

## Kiểm chứng và bàn giao

- **36 backend tests đạt**: điểm đúng/sai/đúng một phần/bỏ trống, giải thích không
  tính điểm, ID/type/length sai, whitelist, cấu trúc mười bài và hồi quy contract cũ.
- **20 PostgreSQL tests đạt**: API thật qua ASGI, lưu/đọc/history, snapshot giữ
  phiên bản sau khi đề thay đổi, quyền sở hữu, idempotency đồng thời chỉ gọi grader
  một lần, import no-op và luồng tự luận/mock cũ. Bao gồm sáu kiểm migration/schema,
  nâng từ baseline lên head và bảo toàn dữ liệu legacy trong DB test.
- **3 Playwright browser tests đạt**: hai bài trên web/BE/PG thật, tải ảnh thật,
  lưới phóng lớn, bản nháp sau reload, điểm 2/2, feedback/nguồn/annotation sau nộp,
  form khóa, reload kết quả, replay cùng key, ảnh/kết quả 404 cho người khác,
  desktop/mobile không tràn ngang; test thứ ba kiểm review đủ 10 bài, tám staging.
- Source verification local đạt cho 10 bài/16 ảnh. Next production build,
  TypeScript, ESLint phần thay đổi và Ruff backend đạt. Đã xem ảnh chụp giao diện
  desktop/mobile; detector UI không có finding. Không chạy kiểm định model thật.
- Backup trước migration/import:
  `data/backups/clinical-exercise-demo-20261110T014349Z/`, pg_dump custom 95.952 byte,
  đã kiểm `pg_restore --list` thành công. Không đổi file `.env`.
- Đối chiếu 33 hàng cũ ngoài hàng version migration: mọi giá trị cột cũ giữ nguyên.
  370 file adapter/training/run cũ/grading/learner giữ hash, cùng 53 file được bảo vệ
  của cơ chế backup cũ. Old expected/raw không thay đổi; không model load/call.
- Hai attempt browser cuối đã dọn theo ownership; DB kiểm thử đã xóa. Web/BE/DB
  đang phục vụ demo. Container kiểm thử tạm tự xóa; không đụng Neo4j/VPN/routes,
  weights/cache/venv. Không commit/push.

Artifact local (gitignored vì có dữ liệu tài khoản/bài làm):
`data/clinical-cases/exercises/structured/audit/`: backend-tests.xml,
postgres-tests.xml, browser-tests.xml, ảnh chụp trước/sau nộp, integrity.json,
browser-cleanup.json, protected-hashes.json. Kết quả import riêng:
`data/clinical-cases/exercises/structured/import-results.json`.

Còn cần người dùng/giảng viên duyệt: đáp án và bản dịch; độ khó BSNT; quyền
riêng tư ảnh gốc; độ chính xác/đầy đủ annotation; phạm vi hỏi/tiêu chí phù hợp
môn học. Không tự đổi `expert_verified=false` thành đã duyệt.

Để quay lại luồng cũ, mở `?question=CLINICAL_DEMO_V1_CASE01` hoặc
`?question=CLINICAL_DEMO_V1_XR01`; provider cũ vẫn do cấu hình hiện có quyết định
(máy hiện tại là mock). Không cần downgrade DB. Có thể ngừng hiển thị V2 bằng
cơ chế availability của ngân hàng câu hỏi; lịch sử đã nộp vẫn giữ nguyên.
