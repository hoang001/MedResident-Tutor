# Đánh giá dữ liệu giảng viên cung cấp ngày 04/11/2026

Đã kiểm tra hai file trong `data/new_data`. Cả hai mở và trích xuất được trực tiếp
từ cấu trúc DOCX/XLSX, không cần OCR hoặc gọi LLM. Kiểm tra tính toàn vẹn ZIP của
cả hai file đều đạt. Không chỉnh sửa file gốc, không import hoặc sửa Neo4j/PostgreSQL.

Kết luận: **file Ngoại khoa dùng được làm nguồn xây dựng khung năng lực ở trạng
thái bản thảo; file Nội tổng hợp nên giữ riêng làm mẫu tham khảo, chưa ghép vào
chương trình Ngoại khoa.** Hai file bổ sung cấu trúc mục tiêu/đánh giá năng lực,
chưa thay thế giáo trình hoặc đề cương nội dung từng học phần.

## 1. Khung năng lực BSNT Ngoại khoa.docx

- SHA-256: `86c13429db33aef5620c165fd4e27f843bf4e63f8280390e227e158449718355`.
- Tiêu đề thực tế: **BẢN THẢO THỐNG NHẤT KHUNG NĂNG LỰC CHO BÁC SĨ NỘI TRÚ NGOẠI KHOA**.
- Đoạn mở đầu nêu chương trình BSNT của Đại học Y Hà Nội và mô hình sáu lĩnh vực.
  Đây là thông tin do tài liệu tự nêu; chưa xác nhận độc lập tình trạng ban hành.
- Có 19 bảng năng lực. Mỗi bảng có năm cột mức độ và đủ nội dung ở cả năm cột:
  **19 tiểu năng lực × 5 mức = 95 ô mô tả**, không phải 95 câu hỏi hoặc 95 điểm số.
- Nội dung chính là văn bản và bảng thật; hai ảnh lớn là hình minh họa các mô hình
  phát triển năng lực. Không phải bản scan cần OCR.
- Không có tracked insertions/deletions trong nội dung chính. Không phát hiện
  bảng điểm học viên đã điền; dòng “Chưa hoàn thành mức độ 1”, “Chưa luân khoa”
  là lựa chọn của biểu mẫu, không được nhập như kết quả của một người học.

| Nhóm năng lực | Mã trong tài liệu | Số tiểu năng lực | Số ô mô tả theo mức |
|---|---|---:|---:|
| Kiến thức y khoa | MK1–MK2 | 2 | 10 |
| Chăm sóc người bệnh | PC1–PC4 | 4 | 20 |
| Tính chuyên nghiệp | P1–P4 | 4 | 20 |
| Thực hành dựa trên hệ thống | SBP1–SBP4 | 4 | 20 |
| Học từ thực hành và phát triển bản thân | PBLI1–PBLI2 | 2 | 10 |
| Giao tiếp và phối hợp | ICS1–ICS3 | 3 | 15 |
| **Tổng** | | **19** | **95** |

Những phần bổ sung hữu ích gồm giải phẫu/kỹ thuật phẫu thuật, lập luận lâm sàng,
chăm sóc sau mổ, đạo đức, an toàn người bệnh, năng lực số, thực hành dựa trên bằng
chứng, tự phản ánh và giao tiếp. Các mô tả nêu hành vi được mong đợi; không tự
cung cấp bài giảng, đáp án, barem hoặc bằng chứng người học đã thực hiện được.

Các điểm cần lưu khi sử dụng:

1. **Trạng thái bản thảo:** cần giảng viên xác nhận phiên bản đang áp dụng,
   phạm vi BSNT Ngoại khoa/chuyên ngành CTCH và tình trạng phê duyệt. Metadata tạo
   file tháng 09/2025 không chứng minh năm áp dụng hoặc quyết định ban hành.
2. **Mở đầu chưa cập nhật đồng nhất:** đoạn thứ ba của phần mở đầu nói tài liệu
   giới thiệu bốn lĩnh vực, nhưng phần bảng thực tế có đủ sáu nhóm, gồm cả MK và
   PC. Giữ nguyên văn nguồn và ghi chú điểm này, không tự sửa bản gốc.
3. **Mức năng lực không đồng nghĩa năm học:** đoạn nói về CCC nêu rõ mức độ không
   tương ứng trực tiếp với năm đào tạo. Không tự gán mức 1/2/3 cho Round 1/2/3.
4. **Không tự đặt điều kiện tốt nghiệp:** nguồn mô tả mức 4 là mục tiêu, đồng
   thời nói không phải điều kiện bắt buộc. Chưa dùng nó làm quy tắc đạt/trượt.
5. **Chưa có ánh xạ đến từng học phần:** các mã MK/PC/P/SBP/PBLI/ICS không phải mã
   môn hoặc PLO1–PLO17. Cần giữ riêng và chỉ nối sau khi xác nhận ánh xạ.
6. **Chuẩn hóa có lưu vết:** một số đoạn dùng Unicode tổ hợp và có lỗi gõ nhỏ.
   Có thể chuẩn hóa NFC/khoảng trắng để tìm kiếm, đồng thời giữ nguyên văn và
   locator `bảng / hàng / cột mức` để đối chiếu.

## 2. Nội tổng hợp_Khung năng lực.xlsx

- SHA-256: `dc5391982d492f2960997ea3317d29f3d113d28421a7f51d9cd41b5e321899d0`.
- Có một worksheet, vùng khai báo `A1:J32`, 29 hàng có dữ liệu và 35 vùng gộp ô.
- Có **25 tiểu năng lực có tên và mô tả**, với 125 ô mức độ không trống; có
  **15 PLO**, mã PLO1–PLO15.
- Các cột A/B là nhóm/tiểu năng lực; C–G là mức 1–5; H/I/J là nhóm chuẩn đầu ra,
  mã PLO và nội dung. Phần đầu có Y1/Y2/Y3 và các học phần Nội khoa.
- Các ô là dữ liệu văn bản; không có công thức hoặc hàng ẩn trong sheet đã đọc.

Những điểm quan trọng:

1. **Khác chuyên ngành:** tên file, danh sách học phần và nội dung đều xác định
   phạm vi Nội khoa, gồm Nội khoa cơ bản, Hô hấp–Tiêu hóa, Nội tiết–Thận tiết niệu,
   Cơ xương khớp–Tim mạch, Huyết học–Lão khoa. Không coi đây là đề cương Ngoại khoa.
2. **Thiếu nội dung ở hàng 19:** I19/J19 có PLO10 và nội dung cải tiến chất lượng,
   nhưng B19 và C19:G19 trống. Các ô này không thuộc vùng gộp che giấu một mô tả
   ở ô khác; không tự sinh tiểu năng lực hoặc điền năm mức còn thiếu.
3. **Tên và nội dung cần đối chiếu ở hàng 20:** B20 nói điều phối nguồn lực/khắc
   phục thiếu sót y khoa, trong khi C20:G20 tập trung vào chi phí và hiệu quả sử
   dụng nguồn lực, tương ứng nội dung PLO11 ở I20/J20. Chưa tự đổi tiêu đề.
4. **Ô gộp có ý nghĩa:** B25:B26 và C25:G26 gộp theo chiều dọc; hàng 26 không phải
   một tiểu năng lực trống khác. Các PLO gộp theo nhiều hàng cũng phải được giữ
   đúng phạm vi, không tạo PLO trùng hoặc coi ô nối tiếp là thiếu dữ liệu.
5. **Không ghép theo mã PLO:** chẳng hạn PLO7 trong Excel là giao tiếp/cung cấp
   thông tin, còn PLO7 của nguồn HMU Ngoại khoa hiện có nói về đạo đức và tính
   nhân văn trong chăm sóc, phẫu thuật/thủ thuật và nghiên cứu. Mã giống nhau
   không có nghĩa nội dung hoặc chương trình giống nhau.
6. **Chưa xác minh đơn vị ban hành/phiên bản:** ghi nhận xuất xứ “giảng viên cung
   cấp qua người dùng”; không tự nâng thành tài liệu HMU đã được ban hành chỉ
   dựa vào thư mục, tên file hoặc metadata.

Có thể tham khảo cách trình bày ma trận năng lực–mức độ–PLO, hoặc phục vụ một
nhánh Nội khoa riêng sau này. Các nội dung chung cũng chỉ là ứng viên tham khảo
cho Ngoại khoa cho đến khi giảng viên xác nhận phạm vi sử dụng.

## 3. Cách bổ sung vào dự án

Ưu tiên xử lý DOCX Ngoại khoa bằng parser cục bộ, theo trình tự:

1. Đăng ký nguồn giảng viên cung cấp với hash, trạng thái bản thảo và phiên bản.
2. Trích sáu nhóm, 19 tiểu năng lực và 95 mô tả theo mức; mỗi mô tả giữ định vị
   bảng/hàng/cột và nguyên văn nguồn. Không cần LLM để đọc các bảng này.
3. Thêm lớp khung năng lực riêng, ví dụ:
   `Curriculum → CompetencyDomain → Competency → MilestoneDescriptor`.
   Mỗi descriptor mang số mức; đây là mô hình đề xuất, chưa phải node đã import.
4. Chỉ tạo liên kết môn–năng lực ở trạng thái đề xuất nếu chưa có ma trận chính
   thức. Ví dụ gần về nội dung là CS032 với P/PBLI, CS033 với SBP/ICS, CS034 với
   giải phẫu/kỹ năng ngoại khoa. Đây là suy luận đối chiếu tên, chưa phải CLO được duyệt.
5. Giữ Excel thành nguồn tham khảo khác chuyên ngành; không dùng `MERGE` theo mã
   `PLO7`, `MK1` hoặc số mức đơn lẻ. ID cần có phạm vi chương trình và phiên bản.
6. Cập nhật API/giao diện để đọc các loại node mới trước khi kỳ vọng chúng xuất
   hiện trên web. Thư viện hiện giới hạn danh sách loại node; import đơn thuần
   không tự tạo màn hình theo dõi khung năng lực.

Các file chưa đủ để thay toàn bộ trạng thái `awaiting_teacher_content` của 27
học phần: còn cần đề cương/danh sách bài, chuẩn đầu ra từng môn, ma trận môn–năng
lực, tài liệu dạy học và quy định đánh giá. Việc đạt một milestone thực hành
không thể xác nhận chỉ từ việc đọc node hoặc trả lời một câu hỏi văn bản.

## 4. Nội dung nên xác nhận với giảng viên

> Dạ em đã đọc được khung năng lực Ngoại khoa cô gửi. Cô cho em hỏi đây đã là bản
> chốt áp dụng cho chương trình của mình chưa ạ? File Nội tổng hợp em dùng làm
> mẫu cấu trúc, hay có phần năng lực chung nào được áp dụng cho Ngoại khoa ạ?
> Nếu có sẵn ma trận liên kết các học phần với năng lực/chuẩn đầu ra, cô cho em
> xin để em gắn dữ liệu đúng phạm vi ạ.

Bản trích cấu trúc phục vụ kiểm tra được lưu cục bộ tại
`data/backups/new-data-review-20261104/` (đã được Git bỏ qua). Chưa có thay đổi
code ứng dụng hoặc dữ liệu KG/DB trong lần kiểm tra này.
