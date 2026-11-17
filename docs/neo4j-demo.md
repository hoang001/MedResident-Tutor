# Xem dữ liệu LLM dưới dạng graph demo

Đã import mẫu OCR graduate ngày 28/10/2026 vào database Neo4j cấu hình trong `.env` gốc. Không import dữ liệu bị validator từ chối, không xóa hoặc thay dữ liệu ngoài nhóm demo. Không gọi LLM lại.

Demo ID: `graduate-20261028-0381f7dd8a7e`.

## Mở và xem

Mở Neo4j Browser của instance đang chạy (thường `http://localhost:7474`, hoặc nút Query/Open của Neo4j Desktop), đăng nhập bằng tài khoản instance và chọn đúng database `NEO4J_DATABASE` trong `.env`.

Chạy truy vấn xem toàn bộ nhóm demo, chọn chế độ **Graph**:

```cypher
MATCH p=(a:MedResidentDemo {demo_id:'graduate-20261028-0381f7dd8a7e'})
  -[r]->(b:MedResidentDemo {demo_id:'graduate-20261028-0381f7dd8a7e'})
RETURN p LIMIT 100;
```

Chỉ xem phần kiến thức, bớt các node kỹ thuật:

```cypher
MATCH p=(s:MedResidentDemo:MedicalStatement {demo_id:'graduate-20261028-0381f7dd8a7e'})
  -[:SUPPORTED_BY]->(u:MedResidentDemo:SourceUnit)
OPTIONAL MATCH q=(s)-[:ABOUT]->(c:MedResidentDemo:MedicalConceptCandidate)
RETURN p,q;
```

Chỉ xem nguồn trích dẫn:

```cypher
MATCH p=(d:MedResidentDemo:DocumentEdition {demo_id:'graduate-20261028-0381f7dd8a7e'})
  -[:HAS_SOURCE_UNIT]->(u)-[:HAS_EXCERPT]->(e)
RETURN p;
```

Bấm node để xem thuộc tính. Nếu graph hiển thị ID thay tên, chọn từng nhãn dưới kết quả và đặt caption thành `display_name` hoặc `name`. Có thể dùng `:style` trong Neo4j Browser và nạp/dán stylesheet `docs/neo4j-demo.grass` để tô màu theo loại node; cách nhập style phụ thuộc phiên bản Browser. Chưa tự thay style của phiên Browser trên máy người dùng.

## Cấu trúc đã tạo

| Nhãn node | Số lượng | Mục đích |
|---|---:|---|
| DemoDataset | 1 | Nhóm dữ liệu demo, fingerprint và đường dẫn trial |
| DocumentEdition | 1 | Sách 2021, phiên bản/năm/hash nguồn |
| OCRArtifact | 1 | File OCR Chandra, đường dẫn/hash/model |
| ExtractionRun | 1 | Lượt extraction Gemma và fingerprint schema/prompt/code |
| SourceUnit | 2 | Đoạn bằng chứng được chọn |
| EvidenceExcerpt | 2 | Trích dẫn nguyên văn, trang PDF/trang in, offsets |
| MedicalConceptCandidate | 4 | Khái niệm ứng viên, tên nguyên văn và tên chuẩn hóa đề xuất |
| MedicalStatement | 3 | Phát biểu nguồn, quote, điều kiện/phủ định, loại phát biểu |
| **Tổng** | **15** | **31 quan hệ** |

Không có node sách 2006 trong demo này vì lượt OCR graduate chưa có record của sách đó qua validator. Chưa gom dữ liệu thử Tesseract hôm trước vào đây.

Quan hệ cấu trúc: DocumentEdition → HAS_SOURCE_UNIT → SourceUnit → HAS_EXCERPT → EvidenceExcerpt; SourceUnit → MENTIONS → MedicalConceptCandidate; MedicalStatement → SUPPORTED_BY → SourceUnit; MedicalStatement → ABOUT → MedicalConceptCandidate. Các node tài liệu/OCR/run giữ provenance.

MENTIONS chỉ nghĩa đoạn nguồn đề cập khái niệm; ABOUT chỉ liên kết phát biểu với khái niệm được đề cập. Chúng không xác nhận mọi phát biểu về khái niệm. Đề xuất quan hệ y khoa của LLM giữ ở thuộc tính JSON `relation` của statement, không chuyển thành cạnh y khoa được khẳng định. Concept vẫn là `MedicalConceptCandidate`, không tự tạo canonical concept hoặc gộp tên tương tự.

Mọi node có `is_demo=true`, `expert_review=unverified`, `usable_as_default_evidence=false`. Đây là demo cách biểu diễn dữ liệu, không phải KG y khoa đã duyệt hay nguồn đánh giá năng lực. Lượt extraction gốc vẫn partial.

## Chạy lại script

```powershell
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
# Chỉ chuẩn bị payload, không ghi Neo4j:
& $py -m knowledge_pipeline.neo4j_demo
# Ghi demo vào Neo4j đã cấu hình:
& $py -m knowledge_pipeline.neo4j_demo --apply
```

Khi cần cài dependency: `python -m pip install -r knowledge_pipeline/requirements-neo4j.txt`.

Script đọc `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` từ `.env` gốc, không đọc mật khẩu từ `.env.example`. Password thật đã chuyển khỏi file mẫu và được thay bằng placeholder. Không in mật khẩu vào log/báo cáo.

Mỗi demo có ID theo fingerprint nội dung; `MERGE` dùng cặp `(demo_id,id)`. Ghi toàn bộ trong một transaction, kiểm số node/cạnh trước commit, không tạo constraint toàn cục hay xóa dữ liệu. Cùng input chạy lại không sinh bản sao. Đổi input tạo demo ID khác để phân biệt phiên bản.

Payload, truy vấn xem và báo cáo import nằm tại `data/knowledge-extraction/trial-20261028-graduate/neo4j-demo/`. Các output này được Git ignore vì có nội dung trích nguồn.

## Xuất Neo4j ra JSON

```powershell
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
# Nhóm demo hiện tại:
& $py -m knowledge_pipeline.neo4j_export --output data/exports/neo4j-demo.json
# Toàn bộ database đang cấu hình, bao gồm node không có quan hệ:
& $py -m knowledge_pipeline.neo4j_export --all --output data/exports/neo4j-all.json
```

Nếu file đã tồn tại, chọn tên khác hoặc thêm `--overwrite`. Có thể chọn nhóm khác bằng `--demo-id <id>`.

Hàm Python: `export_neo4j_json(output_path, *, env_file=DEFAULT_ENV_FILE, demo_id=DEFAULT_DEMO_ID, overwrite=False)` trong `knowledge_pipeline/neo4j_export.py`. Truyền `demo_id=None` để xuất toàn database. Hàm trả số node, quan hệ, thống kê loại và đường dẫn file.

File chứa `scope`, `summary`, `nodes`, `relationships`. Mỗi node có `element_id`, `labels`, `properties`; mỗi quan hệ có `element_id`, `type`, `start_node`, `end_node`, `properties`. `start_node/end_node` tham chiếu `element_id` trong cùng file; đây là ID snapshot, không phải ID nghiệp vụ bền vững giữa các database. ID nghiệp vụ vẫn ở `properties.id` của node demo. Quan hệ song song và chiều quan hệ được giữ nguyên.

Thuộc tính ngày giờ/không gian/binary có dấu `$type`; text JSON lưu trong thuộc tính Neo4j vẫn giữ dạng string gốc, không tự diễn giải thành object. Export đọc toàn bộ phạm vi vào RAM, phù hợp graph demo/nhỏ; database lớn cần cơ chế xuất theo lô riêng. Không ghi ngược Neo4j hoặc lưu config kết nối vào JSON. File `data/exports/` được Git ignore.
