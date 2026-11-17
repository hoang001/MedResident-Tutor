# Kiểm chứng ngữ cảnh, OCR và canonical identity — 29/10/2026

Đã sửa trực tiếp `knowledge_pipeline/kg_v2`, sinh lại graph từ raw LLM bằng quy tắc tổng quát và quyết định identity có nguồn. Không chỉnh tay nodes/edges, không import Neo4j. Đây là kiểm chứng kỹ thuật trong phạm vi nhỏ; chưa được chuyên gia y khoa duyệt.

## 1. Vì sao bản cũ chỉ có 4 cạnh?

Output đối chiếu: `data/knowledge-extraction/v2/result-20261029/`. Validator cũ yêu cầu tên hai đầu mút xuất hiện trong chính quote của cạnh nên loại 3 quan hệ vốn cần kết hợp tiêu đề với bullet. Hai đề xuất khác sai domain/range bị loại đúng. Prompt giới hạn 6 node mỗi cửa sổ khiến một hệ thống cùng 6 mức không thể xuất đủ; mức 3c bị thiếu. Ngữ cảnh phân cấp chưa được biểu diễn rõ, tên mức còn chung chung và heading-only bị xem như nội dung. Vì vậy không thể sửa bằng cách chỉ nới validator hoặc thêm cạnh theo khoảng cách trên trang.

## 2. Quy tắc và code đã sửa

- `context.py`: tách dòng thành block có thứ tự, đường dẫn heading, hệ thống phân loại và cha danh mục. Ngắt kế thừa khi đổi mục hoặc đổi trang chưa xác minh nối tiếp. Bằng chứng của quan hệ có thể gồm nhiều block trong cùng cấu trúc đã xác minh.
- `normalize_edge_context` chỉ xử lý cạnh LLM đã đề xuất. Truy xuất bullet bị thiếu khi nhãn khớp duy nhất và thuộc đúng danh sách; không suy quan hệ chỉ vì cùng trang. Đổi đề xuất `HAS_CATEGORY` giữa hai Category thành `IS_A` con → cha chỉ khi danh sách nguồn xác nhận cha/con. Giữ đề xuất gốc và thay đổi trong audit.
- Heading-only không đủ tạo nội dung. Classification có thể nhận nội dung từ các bullet thuộc hệ thống; Intervention từ các bước nằm trong chính mục thao tác. Không mở rộng sang mục kế tiếp.
- `corrections.py`: patch OCR riêng, kiểm hash PDF/OCR/ảnh, offset và chuỗi trước sửa; giữ nguyên raw. Chặn thay đổi số, đơn vị, dấu so sánh và phủ định. Có cơ chế sidecar `ocr_issues` để giữ ngoài graph đoạn ảnh hưởng nghĩa chưa xác minh.
- `registry.py`: ID ứng viên `CAND2_*` khác ID canonical UUID `MC_*`, `SK_*`, `SQ_*`. Chỉ quyết định identity được duyệt tường minh mới gắn canonical; ứng viên mới chưa duyệt nằm ngoài graph. Không tự merge theo tên hoặc embedding. Category bắt buộc scope hệ thống, đối tượng và mức.
- `migration.py`: crosswalk ID cũ chỉ khi cùng loại, tên tương thích và trace quote gốc cùng nguồn/trang cho kết quả duy nhất. Không sửa output cũ.
- Prompt tăng giới hạn lên 12 node/16 cạnh mỗi cửa sổ, yêu cầu đủ các mức, phân biệt Intervention với Skill và giữ các mục tiêu nhận thức. Schema nguồn cho phép bỏ `excerpt` để pipeline lấy nguyên block nguồn thay vì để model chép sai OCR.
- Provenance nằm trong `content.sources`, `edge.sources` và audit ngoài graph. Không thêm node Document/Run/Evidence hoặc status/confidence/model vào graph y khoa.

## 3. Phạm vi và trước–sau

Dùng OCR đã có trong `data/graduate/`, không OCR lại PDF. Đã kiểm hash PDF và mapping PDF page trong artifact thực tế.

- Sách 2006: PDF20, mục phân độ; thêm heading và định nghĩa PDF16 để xác định đối tượng. Không đọc toàn chương.
- Sách 2021: PDF66, mục tiêu và định nghĩa; PDF73, mục xử lý vết thương với heading cha 4.2, nguyên tắc và các bước 4.2.1. Dùng heading/định nghĩa PDF66 làm context cho PDF73. Không lấy mô tả ảnh AI làm kiến thức.

| Node | Cũ | Mới |
|---|---:|---:|
| Condition | 2 | 1 |
| Classification | 1 | 1 |
| ClassificationCategory | 5 | 6 |
| Skill | 4 | 4 |
| Intervention | 0 | 1 |
| ClinicalPrinciple | 0 | 1 |
| SampleQuestion | 0 | 0 |
| Tổng | 12 | 14 |

| Cạnh | Cũ | Mới |
|---|---:|---:|
| APPLIES_TO | 4 | 4 |
| CLASSIFIED_BY | 0 | 1 |
| HAS_CATEGORY | 0 | 3 |
| IS_A | 0 | 3 |
| MANAGED_BY | 0 | 1 |
| GUIDED_BY | 0 | 1 |
| Tổng | 4 | 13 |

Condition mới gộp hai định nghĩa cùng khái niệm từ hai sách qua quyết định identity có nguồn, giữ hai content block riêng. Condition cũ chỉ chứa heading vết thương không được giữ như một định nghĩa đầy đủ. Intervention “Xử lý vết thương phần mềm” có nội dung các bước, tách khỏi năng lực thực hiện thủ thuật.

## 4. Bằng chứng khôi phục phân loại

PDF20 sách 2006 có câu công bố hệ thống phân độ và các bullet Độ 1, 2, 3; phần Độ 3 ghi chia thành 3a/3b/3c. Pipeline ghép heading đối tượng, câu công bố hệ thống và đúng bullet để chứng minh `CLASSIFIED_BY` và `HAS_CATEGORY`; metadata cha/con chứng minh `3a/3b/3c IS_A 3`. Không tạo `HAS_CATEGORY` Category → Category.

Sáu tên Category canonical đều gồm đối tượng — hệ thống — mức; nhãn ngắn giữ trong aliases. Kết quả này dùng nhãn số Ả Rập của nguồn 2006, không tuyên bố đã kiểm chứng thêm một cửa sổ phân loại IIIA/IIIB/IIIC của sách 2021.

## 5. OCR và trace

Sidecar `knowledge_pipeline/kg_v2/ocr-patches-20261029.json` chứa 15 patch đã đối chiếu trực tiếp bốn ảnh PDF16/PDF20 năm 2006 và PDF66/PDF73 năm 2021. Ảnh bằng chứng có hash tại `data/knowledge-extraction/v2/context-20261029/audit/pdf-review/`.

- PDF16 và PDF66: sửa chữ sai trong heading “GÃY XƯƠNG HỞ”; PDF66 sửa “mà ở gãy thông” → “mà ổ gãy thông”.
- PDF20: “vật” → “vạt” trong hai cụm vạt da-cân/vạt cơ; “Đập nát” → “Dập nát”; “dưng dấp” → “đụng dập”; “cắt đứt chi” → “cắt cụt chi”.
- PDF73: “cần rách” → “cân rạch”; hai “đầu là” → “đâu là”; sửa “cần cơ đập nát”, “cơ đập nát” theo ảnh thành “cân cơ dập nát”, “cơ dập nát”; “gây xương hở” → “gãy xương hở”.

Không sửa số liệu, thuốc/liều hay phủ định; đây là xác nhận chép chữ theo ảnh, không phải duyệt chuyên môn. Raw JSON giữ nguyên. Đã kiểm 26 locator có chuỗi offset corrected → raw đúng nguyên văn, kèm patch ID/revision. Không có issue OCR ảnh hưởng nghĩa còn treo trong các trích đoạn được nhận của mẫu này; điều đó không chứng nhận phần còn lại của sách.

## 6. Canonical identity

Registry bền vững: `knowledge_pipeline/kg_v2/canonical-registry.json`; quyết định cho mẫu: `identity-decisions-20261029.json`. Hiện có 14 canonical entity, 15 candidate binding. Hai candidate định nghĩa gãy xương hở được map cùng UUID sau đối chiếu nội dung; mỗi nguồn giữ content riêng. Các Category được duyệt theo đầy đủ scope, không theo nhãn “Độ” đơn lẻ.

Tái biên dịch offline giữ nguyên toàn bộ graph và UUID, không tạo trùng registry. Khi trang/chunk/quote thay đổi, candidate có thể đổi; phải map tường minh sang UUID hiện có sau duyệt. Không có auto-equivalence cho nguồn mới.

Crosswalk cũ → canonical: 10 node có chứng cứ ánh xạ duy nhất; 2 node chưa map là Condition heading-only và Skill thao tác cũ không có ứng viên cùng loại được chứng minh. Không ép Skill cũ sang Intervention. Xem `audit/old-v2-to-canonical.json` trong output bàn giao.

## 7. Request và kiểm thử

- Đúng 3 request LLM thật trong `context-20261029`, một cho mỗi cửa sổ; timeout 60 giây/request, tổng budget cấu hình 180 giây, không retry. Không dùng raw cũ khác prompt/schema như cache tương thích.
- Các thư mục revalidate sau đó dùng đúng 3 raw JSON đủ schema của lượt này, 0 request mới. Chỉnh sửa chuẩn hóa context chỉ chạy offline. Không gọi OCR mới.
- `pytest knowledge_pipeline/tests document_toolkit/test_toolkit.py -q`: **78 passed, 2 subtests passed**. Không chạy locked model test. Test phủ ngắt context, heading + bullet, cha/con, OCR trace/protected markers/unresolved meaning, canonical scope và identity, giữ content riêng, chống trùng và remap/serialization round-trip.
- Ruff check và format check cho package `kg_v2` cùng test context đều qua.
- Loader chỉ dry-run, kiểm domain/range, chu trình, ID, null và JSON round-trip cho 14 node/13 cạnh.
- Hai snapshot bảo toàn 135 và 104 file đều không có thay đổi; gồm OCR gốc, output cũ và các file ứng dụng/model được khóa trong snapshot. Không sửa database, VPN, route hoặc `.env` trong lượt này.

## 8. Bàn giao và phần còn thiếu

Output cuối: `data/knowledge-extraction/v2/context-delivery-20261029/` gồm `graph.json`, `nodes.jsonl`, `edges.jsonl`. Audit có report, raw, locator, registry snapshot, crosswalk, structural normalizations và `delivery-verification.json`. Giữ nguyên mọi output trước đó.

Giới hạn thực tế: chưa được chuyên gia duyệt ý nghĩa y khoa; chưa import Neo4j. Bốn Skill của mẫu mới đều là nhận thức: ba mục tiêu nguồn và kỹ năng đánh giá cơ lành/cơ dập nát. Model không đề xuất một Skill thực hành tổng thể đủ riêng biệt; không tự thêm để đạt số lượng. Không có SampleQuestion vì phạm vi không chứa câu hỏi nguồn. Chưa kiểm toàn chương/toàn corpus, chưa tự giải quyết identity cho nguồn mới, chưa chứng minh đầy đủ mọi quan hệ ngoài các cạnh có evidence trong mẫu. `complete_scope` trong report chỉ nói hoàn tất xử lý phạm vi kỹ thuật, không phải hoàn tất duyệt chuyên môn hay cho phép xuất bản.

Lệnh tái kiểm offline (đổi output sang thư mục chưa tồn tại):

```powershell
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
& $py -m knowledge_pipeline.kg_v2 revalidate --input-run data/knowledge-extraction/v2/context-20261029 --output data/knowledge-extraction/v2/review-next --identity-decisions knowledge_pipeline/kg_v2/identity-decisions-20261029.json
& $py -m pytest knowledge_pipeline/tests document_toolkit/test_toolkit.py -q
```

OCR patch preflight cần giữ các ảnh bằng chứng bên trên để xác minh hash; không xóa audit ảnh nếu cần prepare/extract lại.
