# Medical KG v2 — khảo sát, triển khai và chạy thử ngày 29/10/2026

## 1. Khảo sát và thay đổi chính

Luồng cũ đã đọc: `document_toolkit` (README, reader/chunker, client, config, pipeline, checkpoint, CLI), `knowledge_pipeline` (OCR adapter, scope, schema, prompt, validation, mapping/export), graph demo/import và export Neo4j, test/CLI liên quan. Không tìm thấy AGENTS.md trong repo. Dùng toolkit tích hợp trong repo, không sửa toolkit ngoài repo.

Luồng cũ: OCR/page → chunks → SourceUnit, concept candidates, MedicalStatement → kiểm tra → graph demo gồm cả DocumentEdition/OCRArtifact/ExtractionRun/SourceUnit/EvidenceExcerpt. Đó là graph trình bày provenance, không phải graph nội dung đích mới.

Luồng v2 nằm riêng tại `knowledge_pipeline/kg_v2/`, không thay luồng v1:

```text
OCR JSON có sẵn → kiểm PDF hash/page mapping → block có locator/offset
→ cửa sổ theo mục/phạm vi đã đối chiếu → LLM local nodes/edges
→ JSON Schema → đối chiếu nguồn và taxonomy → cấp ID theo bằng chứng
→ dedup có kiểm soát → nodes.jsonl / edges.jsonl
→ loader dry-run và round-trip thuộc tính JSON
```

Graph đích chỉ có MedicalConcept với type cụ thể, Skill và SampleQuestion. Không có node Book/Section/Page/SourceUnit/ExtractionRun, không có HAS_SECTION/EXTRACTED_FROM/SUPPORTED_BY. Metadata trạng thái/model/prompt/hash/run không nằm trên node/cạnh graph. Provenance vẫn được giữ trong content.sources/edge.sources và audit ngoài graph.

## 2. Hợp đồng, taxonomy và ID

File kiểm soát:

- `contracts.py`, `taxonomy-v2.json`: 9 loại y khoa + Skill/SampleQuestion, 15 quan hệ và bảng domain/range.
- `extraction-v2.schema.json`: intermediate local IDs; sources dùng block_id/excerpt.
- `graph-v2.schema.json`: node/edge đích; edge dùng **from_id/to_id**, tránh nhầm với mã tài liệu trong `sources[].source_id`.
- `extract-v2.txt`: chỉ nguồn OCR; khi gọi được bổ sung bảng domain/range từ code, snapshot prompt đầy đủ lưu trong audit.

Các loại y khoa: Condition, Anatomy, Finding, Classification, ClassificationCategory, DiagnosticMethod, Intervention, Drug, ClinicalPrinciple. Loader gán hai label `MedicalConcept` và type cụ thể; Skill/SampleQuestion chỉ mang label riêng.

Quan hệ: IS_A, LOCATED_IN, HAS_FINDING, CLASSIFIED_BY, HAS_CATEGORY, EVALUATED_BY, MANAGED_BY, USES_DRUG, MAY_CAUSE, GUIDED_BY, APPLIES_TO, REQUIRES_KNOWLEDGE_OF, HAS_SUBSKILL, ABOUT, ASSESSES. Không cho LLM thêm tên cạnh. Xem `taxonomy-v2.json` để biết chính xác các type đầu/cuối.

ID `KG2N_*`/`KG2E_*` do chương trình cấp. Identity node dựa vào type, tên và **bằng chứng có locator/source hash**, không chỉ tên/embedding. Cùng bằng chứng trong cửa sổ overlap khử trùng được; cùng tên nhưng khác nguồn/bằng chứng không tự merge. `audit/identity_registry.json` giữ mapping local→ID đã resolve. `audit/merge_proposals.json` chỉ đề xuất đối chiếu tên/type; cần duyệt equivalence để có canonical registry toàn cục. Chưa khẳng định đã giải quyết identity xuyên mọi sách; không đổi canonical/pilot ID cũ.

Edge ID bao gồm điều kiện và nguồn của chính khẳng định, không dedup đơn thuần from/type/to. Các content block được giữ riêng; không hòa hai sách thành kết luận mới.

## 3. Phạm vi thực chạy

Dùng đúng hai JSON Chandra trong `data/graduate`:

- `Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi.json` → PDF 2006, 169 trang.
- `DVC.005844.json` → PDF 2021, 532 trang.

Adapter hiện có kiểm source SHA-256 trùng PDF gốc, page count và chỉ số PDF 1-based. Không OCR lại; số lần gọi OCR mới bằng 0. Printed labels chỉ dùng giá trị đã đối chiếu; PDF21/2006 và PDF73/2021 chưa xác minh label bằng ảnh trong lượt này nên xuất `printed_pages=[]`.

Đã chạy hai phạm vi có giới hạn, tổng **9 request**, mỗi request chỉ 1 attempt, timeout tối đa 60 giây; không full corpus:

| Giai đoạn | Scope | Cửa sổ | Request mới | Kết quả |
|---|---|---:|---:|---|
| Trial đầu | 2006 PDF16,20,21; 2021 PDF66,69–70,73 | 6 | 6 | 10 node, 0 edge; 21 record bị giữ ngoài graph |
| Kiểm chứng prompt/hợp đồng sửa | 2006 PDF20; 2021 PDF66,73 | 3 | 3 | Có cạnh Skill hợp lệ; raw được giữ riêng |
| Revalidate offline cuối | Dùng raw của phạm vi kiểm chứng | 3 | 0 | **12 node, 4 edge; 5 edge bị loại** |

Trial đầu cho thấy cần truyền rõ domain/range vào system prompt: model dùng ABOUT cho Skill, APPLIES_TO cho Drug, GUIDED_BY cho Skill. Bản sửa bổ sung bảng này, tách Classification khỏi ClassificationCategory và không yêu cầu model sinh lại cùng quote trong content.text. Intermediate mới chỉ nhận content.sources; chương trình dựng content.text từ các trích dẫn đã kiểm. Raw schema đầu và schema sau sửa khác nhau, không tự tái sử dụng như thể tương thích.

Các giai đoạn/output trung gian giữ nguyên. **Bộ bàn giao cuối nằm tại**:

`data/knowledge-extraction/v2/result-20261029/`

## 4. Số lượng trong bộ cuối

| Node type | Số lượng |
|---|---:|
| Condition | 2 |
| Classification | 1 |
| ClassificationCategory | 5 |
| Skill | 4 |
| SampleQuestion | **0** |
| Các type y khoa còn lại | 0 |
| **Tổng** | **12** |

4 cạnh đều là **APPLIES_TO**. Node từ cả hai sách: 6 node căn cứ sách 2006 và 6 node căn cứ sách 2021.

Skill có 3 kỹ năng cognitive từ mục tiêu học tập và 1 kỹ năng practical được phần hướng dẫn xử lý vết thương hỗ trợ. Chúng mô tả yêu cầu/kỹ năng theo sách, không chứng minh người học đã thực hiện được thủ thuật.

**Không có câu hỏi thực sự trong các block đã chọn**, nên SampleQuestion bằng 0. Không sinh câu hỏi, đáp án hay rubric để lấp đầy schema. Trường hợp câu hỏi thực, câu hỏi nhiều ý/options và đáp án ở trang khác đã được kiểm bằng dữ liệu tổng hợp trong unit test, không giả là output LLM thật.

5 cạnh bị giữ ngoài graph:

- 3 cạnh thiếu tên đầu mút trong chính đoạn chứng minh cạnh (`edge_end_not_mentioned_in_own_evidence`).
- 2 cạnh sai domain/range (`invalid_relationship_end_types`), trong đó các mức phân loại không tự dùng HAS_CATEGORY như hệ thống phân loại.

Không sửa cạnh tự động cho đẹp graph. Toàn lượt vẫn **partial**, mọi dữ liệu vẫn cần review nội dung/chuyên môn ở audit; không tự cập nhật expert_verified và không coi việc bỏ status khỏi graph là đã duyệt y khoa.

## 5. File đầu ra

Trong bộ cuối:

- `nodes.jsonl`, `edges.jsonl`, `graph.json`: graph nội dung đích, không có node provenance hoặc trường confidence/status/model/prompt trên node.
- `audit/catalog.json`, `sections.json`, `pages.jsonl`, `windows.json`: tài liệu, cấu trúc nguồn và block/text/HTML/offset cho RAG/đối chiếu.
- `audit/locators.json`: locator → block, trang, char offsets, source/OCR hash và trích dẫn thực.
- `audit/raw/*.json`: candidate LLM, bao gồm phần sau đó bị loại.
- `audit/rejected.json`: record bị giữ ngoài graph và lý do.
- `audit/identity_registry.json`, `merge_proposals.json`: resolve/dedup và đề xuất đối chiếu.
- `audit/manifest.json`: version, parent extraction manifest, code validation, model/prompt/schema/source fingerprint; không chứa key.
- `audit/report.json`, `verification.json`: thống kê, kết quả kiểm độc lập và phần chưa đạt.
- `audit/loader-preview.json`: labels/properties/relationships sẽ dùng, nhưng **chỉ preview**, không kết nối hoặc ghi Neo4j.

Checkpoint LLM thật ở `verification-20261029/audit/checkpoint-v2.json`; bộ cuối là revalidation offline và không tạo checkpoint giả cho việc gọi model. Resume đã kiểm trước khi code đổi, dùng 0 request. Code đổi thì checkpoint cũ phải bị từ chối; dùng output mới, hoặc revalidate offline khi raw schema thực sự giống nhau.

Audit/raw được Git ignore; không commit OCR toàn sách/PDF, secrets hoặc output lớn. Các JSONL sample nhỏ có thể xem ngay trên máy; chưa commit/push thay đổi của lượt này.

## 6. Loader Neo4j và round-trip

V2 **không có lệnh apply/import**, không import driver để thực thi query.

`content`, `sources`, `answer_sources` được serialize thành **JSON string** trong property, không gán list-of-map vào Neo4j. `decode_properties()` phục hồi cấu trúc JSON; `decode_relationship()` phục hồi edge. Neo4j không lưu property null: các answer/explanation/condition null được bỏ khi encode và phục hồi null khi decode. Node/cạnh chỉ chứa các field đích, không thêm node kỹ thuật để lưu provenance.

Loader kiểm lại taxonomy, ID/reference, domain/range, chu trình IS_A/HAS_SUBSKILL và round-trip trước khi xuất preview. Các graph demo cũ trong Neo4j không bị thay đổi.

## 7. Kiểm thử và bảo toàn

- **62 test đạt, 2 subtests đạt**: toàn bộ `knowledge_pipeline/tests` và `document_toolkit/test_toolkit.py`; không gọi LLM thật trong unit test.
- Ruff check/format cho package v2 và test mới: đạt.
- Locator nhiều trang, trang in chưa rõ, quote/marker/ngữ cảnh phủ định/điều kiện/số, alias không tự suy từ ngoặc, Skill có căn cứ và phân biệt theory/practical, câu hỏi đầy đủ/options/đáp án nguồn khác trang.
- ID nguồn neo giữ ổn định, overlap dedup, không merge chỉ theo tên, edge khác condition giữ ID khác, domain/range/cycle, metadata không rơi vào node KG.
- Resume cùng config dùng cache; đổi model không gọi lại/ngầm ghi đè output; raw schema cũ không được tự migrate; bảng/câu hỏi quá lớn bị giữ lại thay vì chia mất cấu trúc.
- Kiểm độc lập toàn bộ source refs của bộ cuối với substring/offset JSON gốc; loader round-trip đạt.
- Hash **104 file** OCR, pilot, processed, curriculum, Medical/Teaching và các module ứng dụng trước–sau: **0 thay đổi**.
- Không sửa authentication/practice/database; không chạy lại OCR; không import/reset/xóa Neo4j.

## 8. Lệnh tiếp theo

Đọc scope hiện có và kiểm trang/anchor trước khi mở rộng. Scope vẫn được giới hạn theo mục và dung lượng, không gửi sách nguyên khối. Dùng output mới:

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
$scope = 'knowledge_pipeline/kg_v2/trial-scope.json'
$out = 'data/knowledge-extraction/v2/trial-next'
& $py -m knowledge_pipeline.kg_v2 prepare --scope $scope --output $out
# Có gọi model; tối đa 6 request, 60s/request, ngân sách thời gian 360s:
& $py -m knowledge_pipeline.kg_v2 extract --scope $scope --output $out --max-calls 6 --timeout 60 --total-seconds 360
# Chỉ dùng khi giữ nguyên code/input/model/prompt/schema/cấu hình:
& $py -m knowledge_pipeline.kg_v2 extract --scope $scope --output $out --max-calls 6 --timeout 60 --total-seconds 360 --resume
# Chỉ tạo payload Neo4j, không import:
& $py -m knowledge_pipeline.kg_v2 loader-dry-run --output $out
```

Revalidate raw cùng schema mà không gọi model:

```powershell
& $py -m knowledge_pipeline.kg_v2 revalidate --input-run data/knowledge-extraction/v2/verification-20261029 --output data/knowledge-extraction/v2/revalidate-next
```

CLI không cho hơn 6 cửa sổ/request mới mỗi lần chạy, timeout >60s hoặc total >360s. `prepare` không đọc key hoặc gọi mạng; `extract` dùng cơ chế `.env` hiện có, không in/đưa key vào audit.

## 9. Chuyển đổi và giới hạn còn lại

- V1 SourceUnit/EvidenceExcerpt/DocumentEdition/Run chuyển vai trò sang audit/provenance, không đổi ID hay tự thay dữ liệu cũ.
- V1 MedicalStatement không thành node ở v2: nội dung được trích lại vào content block của khái niệm hoặc cạnh có nguồn; không ép mọi statement thành triple.
- V1 type Injury không được đổi hàng loạt thành Condition; v2 phải kiểm nguồn và taxonomy mới. Không tự dùng v1 raw/checkpoint như v2.
- Nhận diện mục/chương hiện theo scope/anchor đã đối chiếu và cấu trúc nguồn giữ trong audit, chưa phải bộ phân tích toàn bộ hai sách. Cửa sổ nhiều trang được giữ ngữ cảnh; bảng giữ HTML nguyên bản, nhưng OCR bảng vẫn cần đối chiếu ô/cột bằng người.
- Các kiểm lexical/domain/quote không chứng minh toàn bộ ý nghĩa của quan hệ. Semantic/expert review chưa hoàn tất; loader chỉ dry-run và không có cổng xuất bản tự động.
- Canonical identity xuyên nguồn cần bảng duyệt equivalence, chưa tự merge hai sách vì cùng tên. Không tự tạo Course/Topic hoặc dùng embedding xác nhận chương trình.

Đây là pipeline và dữ liệu thử có provenance cho KG nội dung v2, không phải KG y khoa hoàn chỉnh hoặc dữ liệu đã được chuyên gia duyệt.
