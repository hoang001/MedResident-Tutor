# Bài tập ca bệnh và X-quang: staging và demo phát triển

> Cập nhật 10/11/2026: hai revision **V2 structured** đã chạy thật trên web,
> chấm theo ID lựa chọn bằng backend, không gọi model. Xem
> [hướng dẫn structured](structured-clinical-practice.md). Phần dưới là báo cáo
> lịch sử của **V1 tự luận/mock**, được giữ để đối chiếu.

Ngày thực hiện: 09/11/2026. Biên soạn thủ công, không gọi LLM/OCR. Không thu thập
thêm ca. Không thay prompt, model, contract Medical/Teaching, training data hoặc
locked test. Không import/thay đổi Neo4j. Không commit/push.

## Mở ngay

Web đang chạy tại `http://localhost:3000`. Đăng nhập bằng tài khoản của bạn rồi mở:

- Ca bệnh: http://localhost:3000/learn?question=CLINICAL_DEMO_V1_CASE01
- X-quang: http://localhost:3000/learn?question=CLINICAL_DEMO_V1_XR01

Hoặc chọn **Mô phỏng AI** trên thanh điều hướng, chọn **Ca bệnh 01** hoặc
**Đọc X-quang 01** trong danh sách. Điểm và phản hồi hiện là **mock cố định**;
không phải chấm nội dung thật và không cập nhật mastery.

Review đủ 10 bài, gồm bản dịch, hình, đáp án, rubric và nguồn:

```powershell
Start-Process .\data\clinical-cases\exercises\review.html
```

Review chứa lời giải, chỉ phục vụ người biên soạn; không phải trang đề học viên.

## Kết quả biên soạn và lựa chọn

| ID ngắn | Dữ liệu nguồn | Nội dung được hỏi | Trạng thái |
| --- | --- | --- | --- |
| CASE01 | PMC10182394, Figure 1 | Đoạn xương gãy và phạm khớp | Demo |
| CASE02 | PMC12978651, Figure 1 | Hướng trật háng và gãy ổ cối đi kèm | Staging |
| CASE03 | PMC8062123, Figure 1 | Hội chứng tác giả xác nhận và phép đo xác nhận | Staging |
| CASE04 | PMC9960912, Figures 1–2 | Vị trí thận lạc chỗ và mức độ rách tác giả báo cáo | Staging |
| CASE05 | PMC10288178, Figure 1 | Khoang ổ dịch và tạng thủng được xác nhận | Staging |
| XR01 | GRAZPEDWRI-DX v2, patient 1 / study 1 | Nhãn tổn thương và vị trí tương đối | Demo |
| XR02 | GRAZPEDWRI-DX v2, patient 6 / study 1 | Nhãn tổn thương và vị trí tương đối | Staging |
| XR03 | GRAZPEDWRI-DX v2, patient 8 / study 1 | Nhãn tổn thương và vị trí tương đối | Staging |
| XR04 | GRAZPEDWRI-DX v2, patient 10 / study 1 | Nhãn tổn thương và vị trí tương đối | Staging |
| XR05 | GRAZPEDWRI-DX v2, patient 19 / study 1 | Nhãn tổn thương và vị trí tương đối | Staging |

External ID đầy đủ có tiền tố `CLINICAL_DEMO_V1_`. Tổng cộng 10 bài đạt đối chiếu
nguồn, mỗi bài hai tiêu chí độc lập, 1 điểm/tiêu chí, tối đa 2 điểm. Không phạt
phần không hỏi. **Đối chiếu nguồn không phải chuyên gia duyệt**; tất cả giữ
`expert_verified=false`, yêu cầu review chuyên môn.

Nguồn ca bệnh giữ tiếng Anh nguyên bản trong `raw/` và các source_refs. Đề tiếng
Việt là bản dịch chọn lọc có ghi phạm vi lược trích, không thay tuổi, giới, triệu
chứng hay xét nghiệm. Câu hỏi và rubric là nội dung biên soạn mới, không phải
SampleQuestion trích nguyên văn. Hai câu con bám nguồn ca hoặc annotation;
không tự tạo đáp án xử trí chung. Đáp án ca bệnh chỉ áp dụng cho người bệnh
được báo cáo.

Với CASE03, số đo áp lực có sẵn trong nguồn được đưa vào bệnh cảnh chọn lọc.
Với CASE02 chỉ dùng phim X-quang ban đầu; CT Figure 2 được giữ ngoài vì caption
và nội dung có khác biệt mô tả thời điểm. Không chọn phim cổ cao còn ngày/header,
ảnh sau điều trị hoặc ảnh có mũi tên để đặt câu hỏi nhận diện mù.

## Ảnh, nhãn và quyền sử dụng

Giấy phép của các bài và dataset được đối chiếu với catalog/credit của đợt
thu thập trước, CC BY 4.0. Attribution và link gốc lưu trong grading/source,
hiển thị ở lời giải sau nộp. Không gắn tiêu đề bài báo chứa đáp án vào đề.

16 asset học viên: 6 figure của 5 ca và 10 ảnh của 5 lượt chụp. Tệp gốc không
thay đổi. Bản học viên chỉ sao chép nguyên byte sang tên hash trung tính; không
crop, che, xóa chữ hay chỉnh pixel. Đã kiểm hash, kích thước, EXIF và rà hình;
16 ảnh được chọn không có EXIF tag, nhưng điều đó không chứng minh tuyệt đối
không còn thông tin nhận diện trong pixel. Cần người dùng rà soát ảnh gốc trước
khi phát hành thật. Mapping/lịch sử biến đổi nằm trong từng grading JSON và
`image-metadata-review.json`.

Các ảnh GRAZ cùng study giữ chung patient/study group. Ảnh mục tiêu được đưa
lên đầu, các góc còn lại vẫn đi cùng. Không có ảnh mục tiêu gắn
`diagnosis_uncertain=1`; chỉ chọn một box fracture trên ảnh được hỏi. Không suy
ảnh không có box là bình thường, không hỏi phân loại hay điều trị.

Vị trí tương đối là tâm box trong lưới 3×3, tính theo ảnh hiển thị. Đây là phép
chuyển đổi hình học minh bạch từ annotation, không phải chẩn đoán giải phẫu mới.
Học viên trả lời bằng chữ; không có bài chấm click tọa độ. VOC/YOLO nguyên bản
đã đối chiếu từ đợt thu thập; không dịch gốc tọa độ hoặc thay đổi hình học.

Lưới và khung vàng lời giải là SVG riêng trong trình duyệt, dùng cùng viewBox
với kích thước pixel gốc. Khung annotation không có trong API đọc đề; chỉ gửi
ở kết quả sau Medical hoàn tất. Alt text, tên file và URL trước nộp trung tính.

## Adapter và luồng thực tế

Khảo sát runtime trước import xác nhận:

- `APP_ENV=development`, database local Compose `medical_learning`, host `db`;
  PostgreSQL chỉ bind loopback host port 5433.
- `PRACTICE_PROVIDER=mock`, `MODEL_CALLS_ENABLED=false`.
- Medical chỉ nhận bốn trường văn bản: question, student_answer, rubric, evidence.
  Không có ảnh gửi vào model và không có năng lực thị giác nào được xác nhận.

Không sửa contract đã khóa. SourceUnit hiện yêu cầu trang PDF, nên adapter tạo
**PDF evidence packet có thật** từ excerpt XML hoặc mô tả annotation. Trang PDF
là trang gói tổng hợp do dự án tạo, **không giả là trang của bài báo gốc**.
XPath/block/offset hoặc đường dẫn VOC, box, hash gốc được giữ trong metadata.
Giao diện lời giải phân biệt rõ hai loại locator này.

Adapter tái sử dụng `persist_case`, `CaseInput`, `ensure_row`, cơ chế transaction
lock và công bố file độc quyền của importer hiện có. Hai bài dùng external ID
ổn định, Doc/SourceUnit/Rubric riêng; không sửa bài pilot. Không tạo Course/Topic
mới; `course_id` và `topic_id` vẫn null. Không cần migration ảnh: mapping được
lưu trong JSON metadata hiện có, ảnh ở file storage, không base64 trong DB.

Ảnh và learner metadata được chụp vào snapshot attempt ngoài payload Medical,
để lịch sử giữ đúng bản đề và ảnh khi nộp. Đọc đề chỉ nhận whitelist trường
học viên; không nhận gold, rubric, annotation hay source excerpt. File ảnh đi
qua API yêu cầu Bearer, tên trung tính, `Cache-Control: private, no-store`.
Ảnh lịch sử dùng ownership của attempt; người khác nhận 404. Không có URL raw
hoặc grading asset công khai. Câu trả lời thật của học viên được giữ nguyên,
không thay bằng reference answer trong adapter.

Ba liên kết Concept được đối chiếu read-only theo nghĩa và nội dung node:
gãy đầu dưới xương quay, trật háng ra trước, chèn ép khoang cấp. Các mục chưa
rõ/Skill để trống, không gắn cưỡng ép. Đây là tham chiếu nội dung, không phải
bằng chứng chấm hoặc ghi nhận mastery. Chi tiết ở `kg-links-verified.json`.

## Import, backup và kiểm thử

Bản sao local trước import:
`data/backups/clinical-exercise-demo-20261109T031437Z/` gồm pg_dump, hàng dữ liệu
trước/sau và hash file được bảo vệ. Không có mật khẩu/token in ra báo cáo.

Đã thực hiện theo thứ tự backup → kiểm source/schema → dry-run rollback →
import đúng hai bài → import lại. Kết quả lần lặp là `unchanged` cho cả hai.
Tám bài còn lại không có trong PostgreSQL. Có thêm hai tài khoản review kỹ thuật
và bốn attempt mock để kiểm API/browser; không thay tài khoản hoặc attempt cũ.
Thông tin đăng nhập kỹ thuật nằm riêng trong `data/backups`, không dùng làm
tài khoản mặc định cho người học và không in trong hướng dẫn.

Kiểm thử đã đạt:

- 16 test backend, gồm adapter/projection/private image và 6 test contract cũ.
- 16 test parser/checkpoint/source/grouping của bộ thu thập.
- Hai ca E2E bằng Playwright trên FE/BE/PostgreSQL local thật: ảnh, mở bản lớn,
  nộp, Medical/Teaching mock, lời giải, reload lịch sử, ownership.
- Kiểm API trực tiếp cả hai bài: không lộ gold trước nộp, ảnh 401 khi chưa đăng
  nhập, hash ảnh khớp, attempt/ảnh lịch sử 404 với tài khoản khác, idempotency.
- Next production build và TypeScript đạt, ESLint/Ruff đạt; detector UI không có
  finding, đã xem desktop/mobile và kiểm không tràn ngang.
- Đối chiếu 26 bảng: mọi hàng cũ giữ nguyên; chỉ thêm hai câu hỏi cùng bằng chứng,
  hai tài khoản kiểm thử và bốn attempt. LearningResult/mastery không đổi.
- 53 file model/training/frozen-data đã lưu hash giữ nguyên. Không chạy locked
  model test, không kiểm định chất lượng model thật, không có LLM call.

Artifact:

- `data/clinical-cases/exercises/authoring.json`: lựa chọn thủ công và lý do.
- `learner/`, `grading/`, `translations/`: tách đề, lời giải và bản dịch.
- `manifest.json`: 10 bài và đúng hai ID cho demo.
- `assets/`, `packets/`: ảnh nguyên byte và PDF evidence packet.
- `validation.json`, `import-results.json`, `api-check.json`,
  `integration-verification.json`: kết quả thực tế.
- `audit/`: ảnh chụp desktop/mobile; chứa dữ liệu kiểm thử nên chỉ giữ local.

## Lệnh kiểm tra và chạy lại

```powershell
# Kiểm tra nguồn và tạo lại review, không cần model
& "$env:TEMP/medresident-cases-venv/Scripts/python.exe" -m clinical_cases.exercise_review

# Xem dry-run của adapter, không commit dữ liệu
docker exec medresident-tutor-backend-1 python -m app.integration.clinical_cases --bundle /app/data/clinical-cases/exercises

# Import lại có kiểm tra conflict, không tạo trùng
docker exec medresident-tutor-backend-1 python -m app.integration.clinical_cases --bundle /app/data/clinical-cases/exercises --apply

# Backend regression liên quan, không chạy locked model test
& "$env:TEMP/medresident-web-venv/Scripts/python.exe" -m pytest apps/backend/tests/test_clinical_exercises.py apps/backend/tests/test_practice_contracts.py -q
```

`docker` trên máy hiện tại có thể cần đường dẫn đầy đủ:
`C:/Program Files/Docker/Docker/resources/bin/docker.exe`.

Browser test dùng `apps/frontend/playwright.clinical.config.ts`, phải chỉ định
`CLINICAL_DEMO_ACCOUNTS` trỏ file tài khoản kỹ thuật local. Khi browser chạy trong
Docker, test chỉ chuyển tiếp request thật tới host; không dựng response/điểm giả
trong browser. Mock nằm ở provider backend và được ghi rõ trên giao diện.

Không tạo lại backup sau import rồi gọi đó là bản trước import. Script
`scripts/snapshot_clinical_demo.py` dành cho một lượt thay đổi mới, không phải
lệnh cần chạy để xem demo. Không reset volume/database hoặc chạy seed pilot.

## Cần duyệt trước khi dùng cho học viên

1. Giảng viên kiểm chẩn đoán, phạm vi câu hỏi, rubric và các cách diễn đạt tương
   đương; xác nhận phù hợp với trình độ bác sĩ nội trú.
2. Duyệt bản dịch chọn lọc, tính hiếm/biến thể và toàn bộ thông tin nhận diện
   trên ảnh ở độ phân giải gốc. Không đổi thành expert_verified trước khi duyệt.
3. Rà tính đúng/đầy đủ của nhãn dataset; chấp nhận lưới 3×3 chỉ là bài tập kỹ thuật
   đơn giản, chưa phải thang đánh giá năng lực đọc phim đã chuẩn hóa.
4. Chọn cách chấm thật: giảng viên/rule engine phù hợp hoặc bật provider đã kiểm
   chứng ở lượt được phép riêng; hiện mock cố định không chấm câu trả lời.
5. Sau khi duyệt, mới đưa thêm tám bài staging vào luyện tập và xây đánh giá
   thực hành có giám sát. Không quy điểm web thành đạt tín chỉ thực hành.
