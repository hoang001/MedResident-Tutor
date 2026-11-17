# Chạy sách Bệnh học ngoại khoa – Chấn thương chỉnh hình (2021)

Plan: `knowledge_pipeline/kg_v2/book-2021-all-lessons-plan.json`.
Nguồn duy nhất: PDF `data/raw-source/DVC.005844.pdf` và bản OCR có sẵn
`data/graduate/DVC.005844.json`. Không dùng nội dung sách 2006 để bù chỗ thiếu.

## Tình trạng sách Cấp cứu 2006

Đã hoàn tất lượt extraction cho phạm vi 25 bài khi tính cả các lượt riêng bài
15–16 và batch 23 bài còn lại (250/250 cửa sổ, 93/93 nhóm). Điều này chưa phải
hoàn tất đối chiếu nguồn, canonical hoặc nạp toàn bộ Neo4j: riêng batch mới còn
328 bản ghi giữ ngoài, Kocher của bài 15 và một số mục bài 16 còn chờ kiểm tra.
Neo4j hiện chỉ chứa phần chương vai đã được đối chiếu và nạp trước đó.

## Phạm vi sách 2021 và giới hạn nguồn

Lượt này lên lịch **36 bài**, theo mục lục, **685 cửa sổ / 265 nhóm**. Bài 5
Gãy xương hở và bài 19 Điều trị trật khớp vai trước đây mới có thử nghiệm một
phần, nên không bỏ qua hai bài này. Không có bài nào của sách 2021 đã hoàn tất
extraction toàn bài để loại khỏi lượt chạy.

**PDF hiện có thiếu phần mở đầu của bài 10, 14, 16 và 18.** Đã đối chiếu ảnh
PDF và OCR tại các ranh giới; các trang đầu còn lại bắt đầu giữa nội dung.
Plan dùng dòng mục lục làm ngữ cảnh tên bài cho bốn trường hợp này, không coi
mục lục là nội dung chuyên môn và không tự sinh mục tiêu/nội dung bị thiếu.
Cần bổ sung PDF đầy đủ để bao phủ các phần không có trong nguồn hiện tại.

Không tìm thấy mục câu hỏi lượng giá trong phạm vi PDF của bài 9, 11, 13, 15.
Không tự tạo câu hỏi hay câu trả lời để bù. Mục tiêu học tập có trong 32 bài,
câu hỏi lượng giá có trong 32 bài; toàn bộ các mục hiện có đều được giữ nguyên
để LLM trích, cùng bối cảnh câu hỏi, câu con và lựa chọn. Số trên là số mục,
không phải số câu hỏi hoặc số năng lực.

Giữ các mục đánh số nhỏ và bảng nguyên khối, không cắt chỉ vì hết trang.
Bảng dùng scope riêng với `structured_context=false` để gửi HTML bảng nguyên
vẹn, tránh lặp lại HTML trên từng dòng. Các cửa sổ khác dùng context có cấu trúc.
Ảnh minh họa, mô tả ảnh do OCR sinh, header/footer và danh mục tài liệu tham khảo
không được dùng làm nội dung chuyên môn. Câu hỏi phụ thuộc ảnh vẫn cần người
dùng đối chiếu ảnh sau extraction; không suy đáp án từ kiến thức của model.

## Lệnh chạy

Bật WireGuard và mở PowerShell:

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'

& "$env:TEMP\medresident-draft-venv\Scripts\python.exe" -m knowledge_pipeline.kg_v2 batch `
  --scope knowledge_pipeline/kg_v2/book-2021-all-lessons-plan.json `
  --output data/knowledge-extraction/v2/book-2021-full-wait `
  --max-calls 1370 `
  --no-response-timeout `
  --connect-timeout 30
```

Nếu mọi request thành công lần đầu thì dùng **685 request**. **1370** là hạn mức
có dự phòng tối đa 2 lần thử/cửa sổ khi lỗi tạm thời, không phải 1370 cửa sổ phải
chạy. Hạn mức tính riêng mỗi lần gọi lệnh; cache đã lưu không tiêu tốn request mới.
Không có retry HTTP ẩn. Phản hồi sai schema có thể phục hồi một phần và đưa các
bản ghi lỗi vào audit, không tự sửa thành tri thức hợp lệ.

Không giới hạn thời gian phản hồi hoặc tổng thời gian chờ; chỉ giới hạn thiết
lập kết nối 30 giây. Server vẫn có thể trả HTTP lỗi hoặc đóng kết nối.

Nếu bị gián đoạn, thêm **`--resume`** vào cuối cùng lệnh, giữ cùng thư mục output,
code/prompt/schema và cấu hình sinh kết quả. Không khởi chạy hai batch cùng lúc
vào cùng output hoặc cùng draft registry. Các đoạn đã cache được dùng lại; các
cửa sổ từng thất bại chưa có cache có thể được gọi lại.

## Kiểm tra và đầu ra

Đã chuẩn bị offline đủ 265 scope, không cửa sổ nào bị loại; kiểm các dòng nguồn
được chọn không bỏ sót. Prompt thực tế lớn nhất **53.057 byte**, dưới cấu hình
70.000 byte. Đã kiểm riêng role mục tiêu/câu hỏi, giữ lựa chọn câu hỏi, nối mục
qua trang và trường hợp thiếu phần mở đầu. Chưa gọi LLM/OCR mới hoặc ghi Neo4j
trong bước chuẩn bị.

Mỗi nhóm có review/audit riêng trong
`data/knowledge-extraction/v2/book-2021-full-wait/shards/bai-XX-nhom-YY/`.
Sau khi batch kết thúc, mở `report.md` tại thư mục output để xem aggregate mới nhất.
Kết quả là bản nháp có nguồn; cần kiểm nguồn và xử lý định danh trước khi import.
Lệnh không tự nạp Neo4j hoặc đưa nội dung vào evidence/rubric chấm điểm.

- [Danh sách 36 bài và phạm vi](../data/knowledge-extraction/book-2021-preparation-20261102/chapter-index.json)
- [Các khoảng thiếu đầu bài](../data/knowledge-extraction/book-2021-preparation-20261102/source-gaps.json)
- [Đối chiếu ảnh tại ranh giới](../data/knowledge-extraction/book-2021-preparation-20261102/boundary-contact.png)
- [Kiểm bao phủ nguồn](../data/knowledge-extraction/book-2021-preparation-20261102/source-coverage.json)
- [Các dòng loại và lý do](../data/knowledge-extraction/book-2021-preparation-20261102/excluded-lines.json)
