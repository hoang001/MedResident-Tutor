# Chạy thử LLM trên hai sách — 27/10/2026

## Kết quả

Đã chạy đọc PDF, OCR chọn trang và extraction thật bằng `vtllm/gemma-4-26b`, endpoint đã kiểm tra kết nối. Cấu hình đọc từ `.env` gốc; không lưu key vào báo cáo/checkpoint. `LLM_MAX_ATTEMPTS=1`: không tự retry. Không dùng LLM checker; không tự duyệt chuyên môn.

| Sách | Tổng trang PDF | Trang nội dung OCR trong trial | Trang có SourceUnit được chấp nhận | SourceUnit | ConceptCandidate | MedicalStatement |
|---|---:|---|---|---:|---:|---:|
| Cấp cứu ngoại khoa – Chấn thương, 2006 | 169 | 16, 19–20 | 16, 20 | 2 | 11 | 3 |
| Bệnh học ngoại khoa – Chấn thương chỉnh hình, 2021 | 532 | 66, 69–70, 77 | 66, 69 | 2 | 8 | 4 |
| Tổng | 701 | 7 trang nội dung | 4 trang | **4** | **19** | **7** |

Ngoài trang nội dung, OCR trang bìa và mục lục: PDF 2, 6 của sách 2006; PDF 2, 5 của sách 2021. Tổng 11 trang OCR ở mỗi lượt chuẩn bị phạm vi nhỏ; không OCR toàn sách. Inventory đọc lớp chữ để khảo sát 701 trang, chỉ thấy lớp chữ ở 167/169 trang sách 2006 và 0/532 trang sách 2021.

Đã xem ảnh bìa, mục lục và trang mẫu từ chính file PDF để kiểm tên, NXB Y học, năm và locator. Sách 2021 ghi dành cho đào tạo sau đại học. Trang đầu bài Gãy xương hở là PDF66/trang in75, không mặc định PDF67 từ metadata pilot cũ. Printed labels chưa kiểm vẫn null; không áp offset toàn sách.

Mẫu được chấp nhận gồm 2 definition, 1 classification, 2 principle, 1 procedure, 1 observation. Hai nguồn cùng đề cập định nghĩa gãy xương hở; các statements vẫn riêng theo phiên bản. Có 3 đề xuất đối chiếu concept giữa hai nguồn và 5 đề xuất mapping với SourceUnit cũ; không tự merge hoặc thay ID.

## Hai lượt thử và phần lỗi

1. `data/knowledge-extraction/trial-20261027-llm`: đọc phạm vi trang đầy đủ, tạo 5 chunks. LLM trả kết quả hợp lệ cho 1 chunk; hai chunk bị chặn với `Quote not found in specified source span`. Do reader dừng từng sách ở chunk lỗi, hai chunk còn lại chưa gọi. Kết quả riêng: 1 SourceUnit, 2 concept candidates, 3 statements. Không cộng trùng vào bộ mẫu tổng ở trên.
2. `data/knowledge-extraction/trial-20261027-probes`: thu hẹp thành 5 trích đoạn đã khảo sát, giữ nguyên text OCR và locator/char offsets. Hai đoạn sách 2006 thành công; định nghĩa 2021 thành công. Đoạn phân loại 2021 bị chặn với `Statement quote not supported by linked source units`; đoạn nguyên tắc tiếp theo chưa được gọi trong vòng lặp đó.
3. Trong cùng thư mục probes, chạy riêng đoạn nguyên tắc 2021 bằng toolkit, lưu `runs/supplemental-principle.raw.json`; thành công. Bộ mẫu tổng ở bảng là 3 chunks hợp lệ của lượt probes cộng 1 chunk bổ sung này.

Tổng 8 request extraction ban đầu qua ba bước trên, không tính request kiểm tra “OK” trước nhiệm vụ. Không tự retry các request lỗi. Resume kiểm chứng sau đó không phát sinh request.

Trạng thái extraction tổng vẫn là **partial**. Các loại mẫu tối thiểu đã đủ, nhưng chưa hoàn tất tất cả các đoạn được chọn. Không nới validator hoặc sửa trích dẫn bằng kiến thức mô hình để làm đẹp kết quả. Lỗi OCR và lỗi liên kết trích dẫn vẫn cần người đối chiếu; bảng phân loại/MESS bị hỏng cấu trúc không được coi đã đọc chính xác. Không kết luận sách mới hơn đúng hơn; khác biệt nguồn chỉ là đề xuất cần kiểm ngữ cảnh.

## File kết quả chính

Trong `data/knowledge-extraction/trial-20261027-probes/`:

- `inventory.json`: SHA-256, metadata, số trang, lớp chữ và danh sách trang chưa đọc được bằng lớp chữ; không phát hiện PDF trùng cho hai file này.
- `document_sections.jsonl`: 11 mục/chương khảo sát; quan hệ cha–con theo nguồn, không phải Topic học phần.
- `source_probes.jsonl`, `survey-report.json`: 5 trích đoạn khảo sát và loại mẫu; không phải dữ liệu LLM tự sinh.
- `raw/*.pages.jsonl`: text OCR, phương thức/engine, hash traineddata, trang và chất lượng.
- `raw/*.probe-input.json`, `raw/*.probe-chunks.json`: input và mapping span/page/char offsets.
- `runs/*.raw.json`, `runs/*.raw.checkpoint.json`: kết quả từng sách, phần lỗi và checkpoint; file bổ sung lưu riêng.
- `runs/config/*/`: snapshot prompt, JSON Schema và fingerprint code/dependencies/generation.
- `runs/validated/source_units.jsonl`: **4** SourceUnit qua kiểm kỹ thuật.
- `runs/validated/concept_candidates.jsonl`: **19** ứng viên, canonical ID vẫn null.
- `runs/validated/medical_statements.jsonl`: **7** phát biểu riêng theo nguồn.
- `runs/validated/concept-match-proposals.json`, `legacy-mapping-proposals.json`: chỉ đề xuất đối chiếu.
- `runs/validation-report.json`: trạng thái partial và lỗi còn lại.
- `validation-summary.json`: kiểm độc lập schema, quote/locator, reference, dedup, loại mẫu, số lượng và bảo toàn dữ liệu cũ.

Raw, OCR text, ảnh kiểm chứng và checkpoints trong các thư mục trial được Git ignore. Báo cáo không chứa key. Không commit PDF gốc hoặc output lớn.

## Kiểm chứng

- **37 pytest đạt, 2 subtests đạt**, dùng client giả, không gọi LLM thật trong unit test.
- Kiểm lại 4 chunk được chấp nhận: JSON Schema và quote/locator đều đạt; không dangling reference hoặc ID trùng; qualifiers và markers được kiểm bởi validator có sẵn.
- Kiểm quote với đúng trang OCR và char offsets; schema bản ghi export hợp lệ.
- Export lại cùng input cho JSONL giống hệt, không sinh ID mới.
- Resume 2 chunk sách 2006 và 1 chunk nguyên tắc với client bị chặn mạng: dùng lại cache, kết quả không đổi, **0 request**.
- 42 file nguồn pilot/catalog/processed/curriculum/coverage/Medical/Teaching được đối chiếu hash trước–sau: **0 file thay đổi**.
- Quét 68 file output văn bản của hai lượt: không có key cấu hình trong output.
- Mọi ứng viên `expert_review=unverified`, `usable_as_default_evidence=false`, `course_id/topic_id=null`. Semantic support vẫn cần review; schema/quote đúng không chứng minh kiến thức y khoa đúng hoặc hiện hành.

## Mã nguồn đã điều chỉnh

- `knowledge_pipeline/pipeline.py`, `survey.py`: tìm đúng repo gốc khi output nằm trong thư mục trial con; giữ mapping dữ liệu cũ hoạt động.
- `knowledge_pipeline/pipeline.py`, `__main__.py`: tùy chọn `--source-probes-only`, chỉ gửi trích đoạn khảo sát nguyên văn, giữ mapping trang và offset. Không hard-code bệnh vào schema/logic.
- `knowledge_pipeline/tests/test_pipeline.py`: test thư mục output con và trích đoạn giữ nguyên OCR/locator, từ chối quote bị thay.
- `.gitignore`: loại raw/runs/pages của thư mục trial con.

Toolkit ngoài repo ở đường dẫn D: được yêu cầu không tồn tại trên máy này; đã đọc và dùng bản tích hợp trong repo. OCR gọi runtime có sẵn tại `C:/WORKS/JOBS/Schema/.venv/Scripts/python.exe`, PyMuPDF/Tesseract vie+eng, không sửa môi trường Schema. Không import Neo4j/PostgreSQL, không sửa API, không sửa model/prompt Medical/Teaching, training data hay locked test.

## Lệnh chạy phạm vi mới

Tạo scope mới sau khi đối chiếu trang nguồn. Giới hạn đang có: tối đa 20 trang nội dung mỗi sách, 30 trang gồm identity cho một trial. Bắt đầu bằng phạm vi nhỏ; không dùng toàn bộ hai sách.

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
$out = 'data/knowledge-extraction/trial-next'
$scope = 'knowledge_pipeline/scopes/two-books-trial.json'
& $py -m knowledge_pipeline inventory --scope $scope --output $out
& $py -m knowledge_pipeline dry-run --scope $scope --output $out --tessdata C:/WORKS/JOBS/Schema/data/ocr/tessdata --ocr-python C:/WORKS/JOBS/Schema/.venv/Scripts/python.exe
# Chỉ chạy dòng tiếp theo sau khi kiểm dry-run; có gọi LLM thật:
& $py -m knowledge_pipeline extract --scope $scope --output $out --source-probes-only --env-file .env --tessdata C:/WORKS/JOBS/Schema/data/ocr/tessdata --ocr-python C:/WORKS/JOBS/Schema/.venv/Scripts/python.exe
```

Giữ nguyên input/code/model/prompt/schema và lệnh, thêm `--resume` để tiếp tục. Chunk chưa qua validator có thể được gọi lại; không đồng nghĩa resume toàn lượt là miễn gọi API. Nếu thay input/config/code, dùng output mới; không tự ép sử dụng checkpoint cũ. CLI chuẩn không tự gom file bổ sung thủ công vào báo cáo, vì vậy không chạy lại CLI lên thư mục probes chỉ để xem tổng đã gom; đọc `validation-summary.json` hiện tại.

Đây là dữ liệu trung gian kiểm chứng KG/RAG, chưa phải KG hoàn chỉnh hoặc evidence đã duyệt.
