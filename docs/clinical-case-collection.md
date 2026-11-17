# Thu thập ca bệnh và hình ảnh — bộ kiểm mẫu thủ công

Đã chạy thật ngày 09/11/2026, không gọi LLM/OCR. Chưa import Neo4j/PostgreSQL,
chưa nối vào Question/Rubric hoặc luồng chấm. Không thay Medical/Teaching,
authentication, training data hoặc locked test. Không có daemon/tác vụ nền.

## Kết quả đợt đầu

| Loại dữ liệu | Kết quả thực tế |
| --- | --- |
| Ứng viên | 30 bài, 15 CTCH và 15 Ngoại khoa/cấp cứu; một ứng viên ngoài phạm vi được giữ riêng ở excluded-candidates.json |
| ClinicalCase | 10 ca: 6 CTCH + 4 Ngoại khoa/cấp cứu |
| Hình bài báo | 25 figure gốc, giữ nguyên montage |
| ImagingStudy | 20 lượt chụp từ 20 người bệnh khác nhau |
| Ảnh dataset | 39 PNG X-quang cổ tay trẻ em, giữ nguyên 16-bit |
| Chẩn đoán / xử trí / kết quả | 10/10 ca có trích dẫn nguồn cho từng phần |
| AuthoredExercise / đáp án sư phạm / rubric | 0; chưa biên soạn hoặc chấm |

Chẩn đoán tham chiếu là điều tác giả nêu cho người bệnh đó. Không gọi là đáp án
chuẩn của mọi ca tương tự. Trích nguyên bản tiếng Anh, không dịch hay bổ sung
kiến thức ngoài nguồn. Một số trường giữ cả đoạn bối cảnh để không mất điều kiện.
Những đoạn này có thể trùng giữa bệnh cảnh, thăm dò và diễn biến; chưa được
biên tập thành bệnh án tóm tắt hoặc bài tập.

Review mở trực tiếp:

```powershell
Start-Process .\data\clinical-cases\review\index.html
```

## Đã kiểm tra dự án trước khi làm

- Không tìm thấy AGENTS.md áp dụng ở repo/các thư mục cha đã kiểm tra.
- `data/sources/source_catalog.schema.json` phục vụ tài liệu của pipeline CTCH,
  có ràng buộc chuyên khoa và file-scope, chưa mô tả lượt chụp hay nhiều figure.
  Vì vậy không ghi đè catalog sách bằng catalog ca bệnh.
- `document_toolkit/common.py` có JSON UTF-8, atomic write và content fingerprint;
  bộ mới giữ cùng cách tổ chức. Không đổi `document_toolkit` hoặc pipeline KG.
- `document_toolkit/documents.py` ưu tiên PDF/JSON, còn nguồn mới có JATS XML;
  thêm parser XML riêng để giữ section, figure, caption và locator, không OCR.
- `knowledge_pipeline/kg_v2/contracts.py`: `SampleQuestion` thuộc graph,
  có quan hệ ABOUT/ASSESSES và nguồn. Chưa tạo SampleQuestion từ ca mới.
- `apps/backend/app/modules/questions/models.py`: Question có reference_answer,
  Rubric/RubricCriterion là tiêu chí chấm; chưa có MedicalImage/ImagingStudy
  tương ứng cho đợt thu thập này. Không đổi các model hay authentication.
- Manifest hiện có ở `data/integration/` gắn external ID, hash và evidence.
  Bộ mới dùng ID theo nguồn công bố + ca/figure/study, SHA-256, source_refs
  và bản audit riêng; chưa dùng import adapter để ghi vào app.

## Nguồn và quyền sử dụng

Chi tiết nằm ở `data/clinical-cases/catalog/source-survey.json` và `sources.json`.

- **JSCR / PMC:** 10 bài đã kiểm giấy phép CC BY 4.0 trong JATS XML. Figure
  đã đối chiếu caption/credit, không thấy credit riêng loại trừ trong các figure
  được chọn. Dùng ESearch/ESummary chính thức để tìm metadata, rồi PMC AWS
  Cloud để lấy metadata/XML/media. Không crawl HTML bài báo.
- **GRAZPEDWRI-DX v2:** giấy phép CC BY 4.0 từ API Figshare chính chủ.
  `dataset.csv` và annotation ZIP kiểm MD5 theo publisher. Ảnh lấy bằng HTTP
  byte ranges từ các thành viên ZIP, kiểm CRC-32 và SHA-256 từng ảnh.
  Không kiểm MD5 toàn ZIP ảnh vì không tải cả ZIP.
- **MURA v1.0:** trang Stanford mô tả nhãn **normal/abnormal theo study**,
  không có đáp án xử trí. Download hiện dẫn sang Stanford AIMI/Redivis;
  điều khoản phát hành chưa xác minh được trong phản hồi đọc được. Chưa tải.
- **Radiopaedia:** trang licence/case trả 402 với công cụ duyệt; giữ link ứng viên
  có nhãn chưa xác minh, chưa tải hình hoặc suy đoán quyền tái sử dụng.
- **Orthobullets:** xem được danh sách và điều khoản; ca chi tiết được thử dẫn
  đến đăng nhập. Chỉ giữ link. Quyền sao chép cá nhân không được coi là quyền
  đưa hình vào ứng dụng.
- **AO Surgery Reference:** xem được trang tham khảo và điều khoản. Quyền
  dùng minh họa trong bài trình bày phi thương mại không phải quyền tái xuất bản
  trên website. Chưa sao chép ảnh, không đếm trang tham khảo là ca bệnh.
- **MIMIC-IV-ED v2.2:** chỉ xem tài liệu. Nguồn yêu cầu credentialing, đào tạo
  CITI và DUA. Chưa tạo tài khoản, ký thỏa thuận hoặc tải dữ liệu hạn chế.

Nguồn chính thức để kiểm lại:

- https://pmc.ncbi.nlm.nih.gov/tools/developers/
- https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/
- https://pmc-oa-opendata.s3.amazonaws.com/README.txt
- https://api.figshare.com/v2/articles/14825193
- https://www.nature.com/articles/s41597-022-01328-z
- https://stanfordmlgroup.github.io/competitions/mura/
- https://www.orthobullets.com/terms
- https://www.aofoundation.org/disclaimer
- https://physionet.org/content/mimic-iv-ed/2.2/

PMC đã đổi dịch vụ phân phối tháng 8/2026; code dùng cấu trúc hiện tại
`PMCxxxx.version/` trong bucket chính thức, không dựa vào FTP/tarball cũ.
Các record không có CC BY rõ ràng, bị rút bài hoặc bản manuscript không được
tự chọn thay cho phiên bản công bố.

## Cấu trúc và căn cứ

```text
clinical_cases/                       CLI, parser, kiểm tra, review độc lập
data/clinical-cases/
  catalog/
    manual-selection.json             Lựa chọn trường/đoạn/figure do biên soạn thủ công
    candidates.json                   Metadata 30 ứng viên
    candidates-reviewed.json          Trạng thái đã tải / chưa rõ quyền / ngoài phạm vi
    source-survey.json                Điều khoản và khả năng truy cập của 7 nhóm nguồn
    sources.json                      Catalog 10 bài + 1 dataset đã thực sự lấy
    manual-visual-review.json         Cờ cần kiểm tra trên ảnh
    schemas/                          ClinicalCase, MedicalImage, Source, ImagingStudy
  raw/                                XML, metadata, CSV, annotation ZIP và HTTP cache
  images/                             Tệp y khoa gốc, chưa sửa pixel hoặc tách panel
  processed/
    clinical-cases.json
    case-images.json
    imaging-studies.json
    dataset-images.json
    annotations/                      VOC XML, YOLO text nguyên bản
    authored-exercises.json           Mảng rỗng, giữ riêng lớp dữ liệu C
  review/index.html                   Review offline, 64 ảnh liên kết cục bộ
  review/review.md
  audit/                              Kết quả kiểm tra, request checkpoint, ảnh chụp review
```

`ClinicalCase.source_refs` lưu theo trường: source ID, XPath, block ID,
offset trong đoạn đã chuẩn hóa khoảng trắng, excerpt và SHA-256 XML.
Validator trích lại XML và so sánh toàn bộ trường, không chỉ kiểm xem locator tồn tại.

`MedicalImage` gắn case_id **hoặc** study_id, figure/caption, modality,
body_region, view chỉ khi nguồn nêu, URL gốc, đường dẫn cục bộ và SHA-256.
Ảnh hỗn hợp nhiều phương thức ghi `mixed_radiology`, không tự gọi toàn bộ là X-quang.

`ImagingStudy` giữ `patient_id + study_number` theo CSV. **Timehash của GRAZ là
theo ảnh**, không dùng làm study ID. Mẫu giữ toàn bộ ảnh của mỗi lượt đã chọn,
không tính hai góc chụp thành hai ca. Nhãn gốc vẫn theo từng dòng ảnh, không tự
suy thành chẩn đoán chung cho study. `projection` giữ mã gốc, view để null khi
chưa xác minh cách giải mã.

VOC/YOLO và class map `yolov5/meta.yaml` được giữ nguyên. Đã đối chiếu 70 object
về class, giới hạn ảnh và hình học giữa hai định dạng (cho phép sai số làm tròn
tối đa 2 pixel, không tự đổi gốc tọa độ). Annotation không được coi là hoàn hảo.

Một bài chứa hai người bệnh chỉ lấy **Case 1** của PMC8130875, Figures 1–3;
Figure 4 thuộc Case 2 nên không đưa vào. DOI/PMCID, case/study ID, patient grouping
và hash được giữ để chống trùng/chống rò rỉ khi chia tập sau. Không thể khẳng định
đã phát hiện mọi trường hợp cùng một người bệnh được công bố lại ở bài khác.

## Phần giữ lại để kiểm tra

- Ca cổ cao PMC11066803 Figure 2 còn ngày chụp/chữ header nhúng. Giữ cờ privacy,
  không xóa chữ và chưa cấp phép xuất bản dữ liệu cho người học.
- Một số phim ca floating arm có chữ/số rất nhỏ; cần kiểm tra ở ảnh gốc trước
  khi sử dụng. Caption/annotation của các ảnh đều có thể tiết lộ đáp án.
- Rà soát overview 25 hình ca và 39 ảnh dataset không phải kiểm duyệt riêng tư
  đầy đủ ở độ phân giải gốc hoặc chứng nhận chuyên môn.
- Nhiều ca hiếm, bệnh cảnh đặc biệt; danh mục ghi `not_validated_as_typical`.
- Bộ X-quang chỉ cổ tay trẻ em; thiếu hình người lớn và không có xử trí/diễn biến.
- Nhãn `normal/abnormal`, bounding box hoặc mã AO không phải bộ đáp án sư phạm.
- Chưa đánh giá tính hiện hành của xử trí từng bài; không hợp nhất thành phác đồ.

## CLI, checkpoint và giới hạn

Python 3.13 đã chạy thực tế. Môi trường cục bộ của lượt này:
`$env:TEMP/medresident-cases-venv/Scripts/python.exe`.

```powershell
# Nếu tạo môi trường mới:
python -m venv .venv-cases
.\.venv-cases\Scripts\python.exe -m pip install -r clinical_cases/requirements.txt

# Resume đúng 10 ca và 20 lượt chụp đã chọn, không tự sinh câu hỏi
python -m clinical_cases collect

# Kiểm tra và tạo lại review offline, không cần mạng
python -m clinical_cases validate
python -m clinical_cases review

# Test offline
python -m pytest clinical_cases/test_collection.py -q

# Sau khi kiểm mẫu: mở rộng METADATA lên khoảng 100–500 ứng viên
python -m clinical_cases discover --per-group 50
python -m clinical_cases discover --per-group 250

# Chuẩn bị XML một ứng viên có giấy phép phù hợp để đọc và chọn thủ công
python -m clinical_cases prepare PMC10030101
```

Trong môi trường hiện tại, thay `python` bằng:

```powershell
& "$env:TEMP/medresident-cases-venv/Scripts/python.exe" -m clinical_cases validate
```

Lệnh discover chỉ lấy metadata, không tự biến 100–500 bài thành ca đã duyệt.
Sau khi đọc nguồn, sửa `manual-selection.json` bằng block/đoạn/figure thật rồi
chạy collect. Mẫu imaging đang giới hạn tối đa 20 lượt; không vô tình mở rộng
tải ảnh theo số ứng viên bài báo. Candidate cũ giữ lại khi tìm tiếp; chống trùng
DOI/PMCID. Chưa dùng dữ liệu này để train/test hay thay bài locked test.

Mạng chạy tuần tự, ít nhất 0,55 giây giữa request; timeout kết nối 10 giây,
read 45 giây, không retry lỗi ngầm. Budget mặc định 300 request/lệnh, kể cả
redirect. Cache thành công kiểm hash và dùng lại; không tải lại khi resume.
Nếu nguồn không hỗ trợ Range, code dừng, không chuyển sang tải gói 4 GB.
Giới hạn kích thước từng response/ZIP member và allowlist hostname giúp ngăn
tải nhầm. TLS xác minh qua kho chứng thư hệ điều hành, không tắt kiểm chứng.
Cache không lưu URL redirect có chữ ký; chỉ giữ URL gốc và hostname cuối.
Không đọc `.env` và không biết/cần API key hoặc mật khẩu DB.

Raw/images/audit được Git ignore. Processed/review chứa trích đoạn và liên kết
đến ảnh cục bộ nên chưa được coi là gói phát hành công khai. Khi chia sẻ phải
kèm đúng asset/attribution và giải quyết cờ privacy trước; không commit/push
trong lượt này.
