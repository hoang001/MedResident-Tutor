# Chạy các bài còn lại của sách Cấp cứu ngoại khoa – Chấn thương (2006)

Plan đã chuẩn bị: `knowledge_pipeline/kg_v2/book-2006-full-plan.json`.
Chỉ dùng OCR `data/graduate/Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi.json`,
không trộn sách 2021. Thứ tự bài và ranh giới lấy từ tiêu đề trong OCR,
đối chiếu danh sách 25 bài; không coi số trang mục lục là số trang PDF.

## Phạm vi

- Chạy bài **1–14, 17–25**: 23 bài, **250 cửa sổ / 93 nhóm request**.
- Bài 3 Gãy xương hở chạy đủ phạm vi PDF16–26: kết quả thử một phần trước đây
  không được tính là đã hoàn thành toàn bài.
- Bỏ gọi lại **bài 15 Trật khớp vai** (đã có extraction và overlay kiểm nguồn)
  và **bài 16 Trật khớp khuỷu** (đã xử lý 9/9 cửa sổ).
  Bài 16 còn 4 node giữ ngoài và chưa kiểm nguồn toàn bài; bỏ extraction không
  đồng nghĩa đã hoàn tất review. Kocher của bài 15 vẫn đang giữ ngoài.
- Không đưa lại output cũ vào aggregate mới bằng `base_runs`, tránh làm mất
  overlay đã sửa của chương vai. Hai bài bỏ qua được liên kết trong chapter index.

## Lệnh chạy

Bật WireGuard, giữ terminal và máy chạy trong lúc chờ:

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'

& "$env:TEMP\medresident-draft-venv\Scripts\python.exe" -m knowledge_pipeline.kg_v2 batch `
  --scope knowledge_pipeline/kg_v2/book-2006-full-plan.json `
  --output data/knowledge-extraction/v2/book-2006-full-wait `
  --max-calls 500 `
  --no-response-timeout `
  --connect-timeout 30
```

Ngân sách tối đa **500 request cho mỗi lần gọi lệnh**: 250 cửa sổ, tối đa 2 lần
thử/cửa sổ khi lỗi tạm thời. Nếu mọi request thành công lần đầu, dùng 250 request.
Không retry ẩn; không tự gọi lại các phản hồi sai schema đã phục hồi một phần.
Không giới hạn thời gian phản hồi, gửi request, chờ pool hoặc tổng thời gian chờ;
chỉ giới hạn thiết lập kết nối 30 giây. Server vẫn có thể trả lỗi hoặc đóng kết nối.

Nếu gián đoạn, thêm `--resume` vào cuối **cùng lệnh**, giữ cùng output và code/cấu
hình sinh kết quả. Các cửa sổ đã checkpoint được dùng lại, không gọi LLM lại cho
chúng. Giới hạn 500 là của mỗi invocation, không phải tổng cứng qua nhiều lần resume.
Code, schema, prompt hoặc cấu hình sinh kết quả đổi sẽ không dùng được checkpoint
cũ; pipeline dừng để tránh ghi đè âm thầm. Không đổi code pipeline trong lúc chạy.

## Kiểm tra đã làm trước khi bàn giao

- Chạy `prepare()` offline thành công cho cả 93 scope: không có cửa sổ bị loại.
- Giữ mỗi mục đánh số nhỏ nguyên khối; ghép tối đa 3 mục trong cùng nhánh cha,
  không cắt theo số trang để ép vừa. Các bảng OCR nguyên HTML được giữ trong cùng
  một cửa sổ với nội dung trang tương ứng.
- Đối chiếu mọi dòng nội dung còn lại với selector: không có dòng chuyên môn
  bị bỏ ngoài phạm vi đã chọn. Không có nghĩa LLM chắc chắn sẽ trích hết mọi ý.
- Kiểm cả JSON schema, prompt, block ID và ancestry trong request thực tế:
  prompt lớn nhất 60.366 byte, dưới cấu hình 70.000 byte hiện tại.
- Giữ nguyên OCR; loại caption/mô tả ảnh do OCR sinh, footer và trang xuất bản
  PDF169. Chưa đối chiếu ảnh PDF toàn sách hoặc sửa các lỗi OCR y khoa.
- Chưa gọi LLM, không OCR mới, không ghi Neo4j trong bước chuẩn bị.

[Danh sách bài và phạm vi](../data/knowledge-extraction/book-2006-full-preparation-20261102/chapter-index.json),
[kiểm bao phủ nguồn](../data/knowledge-extraction/book-2006-full-preparation-20261102/source-coverage.json),
[các dòng loại cùng lý do](../data/knowledge-extraction/book-2006-full-preparation-20261102/excluded-lines.json).

## Xem kết quả

Mỗi nhóm nằm trong `data/knowledge-extraction/v2/book-2006-full-wait/shards/`,
tên `bai-01-nhom-01` chỉ rõ bài trong mục lục và nhóm xử lý của bài đó.
Mỗi nhóm có `review.html`, JSON graph và audit riêng, xem được sau khi nhóm xong.
Khi batch kết thúc, mở `report.md` ở thư mục output để đến aggregate mới nhất.

Đây là bước tạo bản nháp. Node/cạnh sai schema hoặc chưa đủ căn cứ có thể bị giữ
ngoài, số cửa sổ xử lý đủ không đồng nghĩa tri thức đã đầy đủ hoặc được chuyên gia
duyệt. Lệnh này không tự nạp Neo4j hay đưa nội dung vào evidence/rubric chấm điểm.
