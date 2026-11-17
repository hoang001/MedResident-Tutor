# Chạy lại bằng OCR có sẵn trong data/graduate — 28/10/2026

## Đầu vào đã kiểm tra

| File OCR | PDF nguồn được nhận diện bằng SHA-256 | Số page records | Model OCR được file khai báo |
|---|---|---:|---|
| `data/graduate/Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi.json` | Sách Cấp cứu ngoại khoa – Chấn thương 2006 | 169 | `vtllm/chandra-ocr-2` |
| `data/graduate/DVC.005844.json` | Sách Bệnh học ngoại khoa – Chấn thương chỉnh hình 2021 | 532 | `vtllm/chandra-ocr-2` |

Hash PDF của cả hai JSON khớp file gốc và số trang khớp PDF thực tế. Các section có số trang PDF 1-based, duy nhất, `page_start=page_end`. Cả hai file tự khai báo complete, không unreadable/failure; đây không phải chứng nhận chất lượng nội dung. Không sửa hai file này.

Lượt này **không OCR lại**, không gọi Chandra; chỉ đọc nguyên văn trường `text` của JSON có sẵn. Có 0 lần gọi OCR mới. PDF gốc chỉ dùng kiểm identity/hash/số trang và inventory lớp chữ, không thay thế text bằng bản đọc PDF.

Text OCR chứa một số mô tả ảnh bằng tiếng Anh do model sinh, ví dụ mô tả ảnh X-quang/ảnh lâm sàng. Mẫu gửi LLM đã loại các vùng đó bằng cách chọn đúng đoạn văn khảo sát, không tự sửa file OCR. Vẫn còn lỗi dấu/chữ, nhãn trang in và footer: chẳng hạn trang PDF69 của sách 2021 có text footer “73” và dòng lặp bất thường; locator trang in vẫn lấy từ đối chiếu PDF đã kiểm, không lấy footer OCR đó.

## Phạm vi và cách chạy

Dùng 5 đoạn thuộc các trang đã khảo sát trước: định nghĩa 2006 PDF16, phân loại 2006 PDF20, định nghĩa 2021 PDF66, phân loại 2021 PDF69–70 và nguyên tắc 2021 PDF69. Chuẩn bị vẫn giới hạn trong phạm vi trang thử nhỏ cũ, không extraction toàn bộ hai sách.

Schema, prompt extraction và model `vtllm/gemma-4-26b` giữ như lượt trước. Tạo scope riêng vì anchor text của bản Chandra khác bản Tesseract. Mọi trích đoạn giữ đúng text và char offsets trong JSON; không sửa chính tả để qua validator.

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
$scope = 'knowledge_pipeline/scopes/two-books-graduate-trial.json'
$out = 'data/knowledge-extraction/trial-20261028-graduate'
& $py -m knowledge_pipeline inventory --scope $scope --output $out
& $py -m knowledge_pipeline dry-run --scope $scope --output $out --ocr-json-dir data/graduate --source-probes-only
# Có gọi LLM thật; không chạy lại vào output đã có nếu chưa xem checkpoint:
& $py -m knowledge_pipeline extract --scope $scope --output $out --ocr-json-dir data/graduate --source-probes-only --env-file .env
```

Vòng lặp chuẩn dừng từng sách tại chunk lỗi. Hai chunk chưa được gọi được thử riêng bằng `document_toolkit.extract_document` trên chính section tương ứng, cùng prompt/schema/settings/validator, lưu ở `runs/supplement-classification-2006.raw.json` và `runs/supplement-principle-2021.raw.json`. Tổng cộng **5 request**, không tự retry các request lỗi, không gọi lại chunk đã lỗi.

## Kết quả thực tế

| Nguồn | Đoạn đã gọi LLM | Đoạn được chấp nhận | SourceUnit | ConceptCandidate | MedicalStatement |
|---|---:|---:|---:|---:|---:|
| Sách 2006 | 2 | 0 | 0 | 0 | 0 |
| Sách 2021 | 3 | 2 | 2 | 4 | 3 |
| Tổng | **5** | **2** | **2** | **4** | **3** |

Ba statements được chấp nhận gồm definition, indication và principle. Chúng đều có quote/locator hợp lệ với JSON OCR, không có dangling reference hoặc ID trùng. Mọi record vẫn `expert_review=unverified`, `usable_as_default_evidence=false`, `course_id/topic_id=null`.

Ba lỗi được giữ lại:

1. Định nghĩa 2006: `Unsupported concept name or alias`.
2. Phân loại 2021: `Unsupported concept name or alias`.
3. Phân loại 2006: `Statement text must retain complete supporting quotations`.

Trạng thái toàn lượt là **partial**. Không nới điều kiện đối chiếu nguyên văn hoặc chỉnh sửa đầu ra LLM để coi là hợp lệ. Lỗi tên/alias có thể bao gồm sai khác chữ/cách viết so với quote; cần kiểm tra đầu ra và thiết kế extraction tiếp, không tự kết luận JSON OCR sai chỉ từ thông báo này.

Lượt Tesseract trước có 4 SourceUnit, 19 concept candidates, 7 statements được chấp nhận sau các bước bổ sung. Lượt Chandra này có ít record hơn; đây không phải phép đo chất lượng OCR hoặc so sánh kiểm soát đầy đủ, vì text nguyên văn và kết quả sinh của LLM khác nhau. Bản OCR sạch hơn cũng không tự bảo đảm model tuân thủ contract tốt hơn.

## Mã nguồn và kiểm chứng

- `knowledge_pipeline/ocr.py`: adapter `provided_ocr_json`, kiểm source hash, số trang, section trùng/sai số trang và thiếu trang. Lưu hash/model/path của artifact trong metadata để thay JSON sẽ đổi fingerprint checkpoint.
- `knowledge_pipeline/__main__.py`: thêm `--ocr-json-dir`; không cho dùng đồng thời adapter này với `--tessdata/--ocr-python`.
- `knowledge_pipeline/scopes/two-books-graduate-trial.json`: cùng identity PDF/phạm vi mẫu, selector riêng cho JSON Chandra.
- `knowledge_pipeline/tests/test_provided_ocr.py`: test giữ nguyên text, không sửa file, hash artifact, thiếu trang, sai hash/count và duplicate/zero-based page.
- **42 test đạt, 2 subtests đạt**, không gọi LLM thật trong unit test.
- Kiểm độc lập từng span gửi LLM đúng substring/char offsets trong JSON gốc; không chứa vùng mô tả ảnh được loại khỏi mẫu.
- 12 file OCR/pilot/processed/curriculum/coverage được ghi hash trước–sau, 0 file thay đổi. Không sửa database, API hoặc luồng Medical/Teaching.
- Không có key trong output; cấu hình đọc từ `.env` gốc. Không commit sách, toàn văn OCR, raw output hay checkpoint.

## File để xem

Thư mục `data/knowledge-extraction/trial-20261028-graduate/`:

- `ocr-input-manifest.json`: đường dẫn/hash/model của hai artifact OCR và hash PDF nguồn.
- `raw/*.pages.jsonl`, `*.probe-input.json`, `*.probe-chunks.json`: dữ liệu nguồn và các đoạn thực gửi.
- `runs/*.raw.json`, `*.checkpoint.json`: kết quả và lỗi từng request/chunk, các file bổ sung giữ riêng.
- `runs/validated/source_units.jsonl`, `concept_candidates.jsonl`, `medical_statements.jsonl`: chỉ các record qua kiểm kỹ thuật.
- `runs/validation-report.json`, `validation-summary.json`: số lượng tổng, lỗi và so sánh với lượt trước.

Báo cáo tổng đã gom hai file bổ sung thủ công. Không chạy lại CLI vào cùng thư mục chỉ để xem tổng vì CLI chuẩn chỉ tổng hợp hai output theo sách; hãy đọc `validation-summary.json`. Muốn thử phạm vi khác, dùng scope/output mới, giữ `--ocr-json-dir data/graduate` để chắc chắn không OCR lại.
