# Pipeline trích xuất kiến thức nguồn (offline)

Chạy từ `C:\WORKS\STUDY\MedResident-Tutor`. Đây là dữ liệu trung gian cho kiểm chứng KG/RAG, chưa import Neo4j/PostgreSQL, chưa nối API hay thay SourceUnit pilot. `knowledge_pipeline` tái sử dụng reader, chunker, LLMClient, JSON Schema validation và checkpoint của `document_toolkit` trong repo. Toolkit gốc ở đường dẫn D: không được tìm thấy; không sửa thư mục toolkit ngoài repo. Backend knowledge_graph hiện chỉ có placeholder, retrieval mock trả rỗng; không có graph cần đồng bộ trong bước này.

## Kết quả thực tế

- Đọc lớp chữ của 701 trang: sách 2006 có 169 trang, 167 trang có chữ; sách 2021 có 532 trang, không trang nào có lớp chữ. Hai trang không chữ trong sách 2006 không tự coi là lỗi hay scan: cần phân biệt trang trắng bằng ảnh. Lớp chữ 2006 có nhiều lỗi dấu/ký tự.
- Bìa/tên cơ quan/NXB/năm được kiểm bằng ảnh PDF trang 2 của mỗi sách; mục lục ở PDF 6 (2006), PDF 5–7 (2021). Chưa xác minh đầy đủ tác giả/chủ biên nên metadata này null. Đối tượng độc giả sau đại học chỉ ghi ở cấp tài liệu 2021.
- OCR thăm dò cục bộ: 2021 PDF 1–7, 66–71, 76–77; 2006 PDF 2, 6, 16, 19–20. Không OCR toàn bộ sách. Đã xem ảnh một số trang bìa, mục lục và trang mẫu; không coi OCR là đã duyệt nội dung.
- Phạm vi pipeline chính: 2006 PDF 16, 19–20 (2 chunks); 2021 PDF 66, 69–70, 77 (3 chunks), cộng 2 trang bìa/mục lục mỗi sách. 11 page records OCR trong phạm vi chính, 7 trang nội dung đều needs_review, không có trang không đọc được trong phạm vi này. Các trang ngoài phạm vi được liệt kê rõ trong dry-run-report.
- 11 DocumentSections; 5 source probes chọn thủ công: 2 định nghĩa, 2 phân loại (một đoạn qua 2 trang), 1 nguyên tắc. Probes giữ nguyên lỗi OCR và dẫn span/char offsets/PDF/printed label; **không phải SourceUnits đã duyệt hay MedicalStatements do LLM trích xuất**.
- Chưa gọi LLM: chưa có extraction env-file/endpoint/model được cung cấp cho lượt này. SourceUnit/ConceptCandidate/MedicalStatement trích xuất thật đều **0**. Các JSONL rỗng kèm status not_extracted ở raw/dry-run-candidates, không giả lập thành extraction thật. Không gọi Medical/Teaching.

## Sai lệch và phần cần review

1. Catalog sách 2021 ghi 150 trang trong khi file có 532; chỉ báo lại, không sửa catalog.
2. Bài 5 Gãy xương hở bắt đầu PDF **66 / trang in 75**, trong khi pilot_scope bắt đầu 67. Chương được khảo sát đến PDF 78 / in 87, chưa kiểm tra chương kế tiếp để chứng nhận ranh giới cuối. Sách 2006 bắt đầu bài ở PDF16/in15; chương tiếp theo bắt đầu PDF27 (lớp chữ), phù hợp bài trước kết thúc PDF26.
3. Printed labels chỉ gán cho trang đã kiểm ảnh; các trang khác null. Không dùng offset toàn sách. Trang PDF19 của sách 2006 trong output chính vẫn để printed label null vì chưa kiểm ảnh trang đó.
4. OCR có lỗi `ổ` thành `6`, mất khoảng trắng, nhầm số La Mã IIIA/B/C và hỏng cấu trúc bảng MESS/GHOIS. Không tự sửa bằng kiến thức LLM. Bảng chưa đủ điều kiện dùng làm evidence.
5. Mô tả nhóm IIIc giữa hai nguồn được ghi potential_conflict_needs_context_review, chưa kết luận mâu thuẫn, không chọn sách mới hơn là đúng. Hai statement nguồn không được hòa trộn.
6. Locator KU_0001 cũ là 16–17, integration manifest chính xác hơn là PDF16/in15. Crosswalk ưu tiên locator manifest cho đúng unit đó; mapping còn lại chỉ là đề xuất theo source/locator, không chứng nhận tương đương text hoặc thay ID cũ. SourceUnit cũ có rút gọn.
7. Kiểm schema và quote không chứng minh quan hệ/điều kiện đầy đủ hay tính hiện hành y khoa. Cần người đọc nguồn và chuyên gia duyệt; không có expert_verified trong pipeline tự động.

## File và hợp đồng

- `knowledge_pipeline/scopes/two-books-trial.json`: identity đã đối chiếu, file hash cố định, phạm vi, printed labels, cấu trúc nguồn và selectors cho source probes. Kiến thức bệnh cụ thể chỉ ở config mẫu, không nằm trong logic schema.
- `knowledge_pipeline/schemas/extraction.schema.json`: hợp đồng JSON LLM với local IDs, SourceUnits nhiều support spans, concept candidates, statements (text/quotes, conditions, negations, requirements, thời gian, relation tùy chọn, procedure context/sequence).
- `knowledge_pipeline/schemas/records.schema.json`: DocumentEdition, DocumentSection và bản ghi export có provenance; **không phải schema importer ORM hiện hành**.
- `knowledge_pipeline/prompts/extract.txt`: chỉ lấy nội dung nguồn, không sinh rubric/course/topic. Chưa dùng LLM checker; không có bước tự phê duyệt.
- `data/knowledge-extraction/inventory.json`: đường dẫn tương đối, SHA-256 thực tế, số trang, tình trạng text, trùng file (không phát hiện bản trùng hai file này trong raw-source).
- `pages/*.jsonl`: raw text từng trang, kể cả trang rỗng/lỗi; `raw/*.pages.jsonl`: OCR/đọc trang được chọn, kèm engine/version/language/DPI/hash traineddata; `raw/*.input.json` và `raw/*.chunks.json`: input và chunks thực tế của toolkit.
- `document_sections.jsonl`, `source_probes.jsonl`, `survey-report.json`, `legacy-locator-crosswalk.json`, `source-comparison-notes.json`, `dry-run-report.json`: đầu ra khảo sát nhỏ, review-gated.
- Khi chạy thật: `runs/*.raw.json`, `runs/*.raw.checkpoint.json`; `runs/validated/*.jsonl`, đề xuất đối chiếu concept/legacy và validation-report.json. “validated” chỉ nghĩa kiểm tra kỹ thuật; mọi record vẫn needs_review/unverified và usable_as_default_evidence=false.

ID xác định từ edition/hash/nguồn; concept candidate tách canonical ID (null). Chunk giữ ranh giới span/trang; trang dài chia tiếp giữ char offsets. Không mặc định page/chunk là SourceUnit. Statement MVP yêu cầu text giữ đủ các quote ghép, interpretation tách riêng; kiểm trích dẫn chỉ NFC/whitespace, không fuzzy/OCR correction. Quan hệ và thứ tự cần review nguồn dù JSON hợp lệ.

Checkpoint bao gồm input/OCR metadata/file hashes, model/endpoint, prompt, schema, cấu hình chunk/generation và fingerprint code wrapper/toolkit/dependencies. Đổi một phần liên quan phải bị từ chối resume; dùng output mới hoặc --force sau khi xem xét. API key không nằm trong signature/checkpoint, URL chứa credentials/query/fragment bị từ chối. Không log source dump hay secrets.

## Lệnh đã kiểm chứng trên máy này

```powershell
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
& $py -m knowledge_pipeline inventory
& $py -m knowledge_pipeline dry-run --tessdata C:/WORKS/JOBS/Schema/data/ocr/tessdata --ocr-python C:/WORKS/JOBS/Schema/.venv/Scripts/python.exe
& $py -m pytest knowledge_pipeline/tests -q
& $py -m unittest document_toolkit.test_toolkit
```

Runtime OCR thực tế là PyMuPDF 1.28.2/Tesseract với vie+eng tại thư mục trên; callback qua Python subprocess chỉ đọc nguồn, không sửa môi trường Schema. PyMuPDF 2.0 cài thử trong venv riêng không import được vì Windows Application Control chặn DLL; không tắt chính sách. Dùng runtime 1.28.2 đã hoạt động; chưa xác minh cài mới trên máy khác.

Để dựng môi trường khác, Python >=3.11:

```powershell
python -m venv .venv-extraction
.\.venv-extraction\Scripts\python.exe -m pip install -r knowledge_pipeline/requirements.txt
```

OCR cần runtime PyMuPDF hoạt động và vie.traineddata + eng.traineddata có sẵn. Có thể bỏ --ocr-python khi OCR nằm cùng môi trường. Không có OCR thì vẫn inventory được; dry-run phải báo trang không đọc được, không coi là extraction thành công.

## Chạy extraction thật và resume (chưa chạy)

Copy `knowledge_pipeline/.env.example` thành `knowledge_pipeline/.env`, điền LLM_BASE_URL, LLM_MODEL và LLM_API_KEY nếu endpoint yêu cầu. Đây là cấu hình extraction riêng, không copy .env backend và không gửi key qua chat. Endpoint phải hỗ trợ chat-completions JSON. Kiểm giới hạn context/model phù hợp; byte budget không thay token counter.

```powershell
& $py -m knowledge_pipeline extract --env-file knowledge_pipeline/.env --tessdata C:/WORKS/JOBS/Schema/data/ocr/tessdata --ocr-python C:/WORKS/JOBS/Schema/.venv/Scripts/python.exe
# Giữ nguyên scope/config/code để resume:
& $py -m knowledge_pipeline extract --env-file knowledge_pipeline/.env --tessdata C:/WORKS/JOBS/Schema/data/ocr/tessdata --ocr-python C:/WORKS/JOBS/Schema/.venv/Scripts/python.exe --resume
```

Kiểm raw output và validation-report trước; không đưa ứng viên vào evidence mặc định. Nếu input/prompt/schema/model thay đổi, không dùng lại checkpoint cũ; dùng --output data/knowledge-extraction/<run-moi> và chạy inventory/dry-run với cùng output trước, hoặc --force có chủ đích. Không có retry ở wrapper; client toolkit có giới hạn LLM_MAX_ATTEMPTS (ví dụ 1). Không tự chạy cả sách.

Để mở rộng, tạo scope JSON khác dựa trên nguồn đã kiểm, chọn tối đa 20 trang nội dung mỗi edition/30 trang gồm identity cho một lượt thử, xác minh labels từng trang rồi chạy inventory → dry-run → extract với output mới. Không thêm course/topic khi chưa có đề cương. Không thêm PDF, raw text lớn, checkpoints, env thật hoặc weights vào Git.

Kiểm tra đã chạy: 18 pytest pipeline + 6 unittest toolkit PASS (client giả, không mạng); Ruff PASS. Kiểm tra độc lập trên file thật: 2 Edition và 11 Section đúng schema; 5 source probes khớp nguyên văn/char offsets; 5 chunks, 0 trang lỗi trong trial. Tóm tắt: data/knowledge-extraction/validation-report.json. Chưa kiểm chứng extraction hoặc checker bằng LLM thật.
