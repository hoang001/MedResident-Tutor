# Phạm vi học cho bác sĩ nội trú CTCH

Cập nhật theo yêu cầu và ảnh chương trình người dùng cung cấp ngày 05/11/2026.
Đối tượng sử dụng là bác sĩ nội trú đã học giai đoạn kiến thức chung, cơ sở hỗ
trợ và kiến thức cơ bản ngành/Round 1. Phạm vi triển khai bài học tập trung vào
khối Chấn thương chỉnh hình trong ảnh, với tổng yêu cầu **40 tín chỉ: 4 lý thuyết,
36 thực hành**.

## Nội dung học trọng tâm

Round 2, năm 2: bốn học phần bắt buộc, mỗi môn 6 tín chỉ (1 LT, 5 TH), tổng 24:

| Mã | Học phần |
|---|---|
| B21CN7 | Chấn thương chỉnh hình chi trên |
| B21CN8 | Chấn thương chỉnh hình chi dưới |
| B21CN9 | Phẫu thuật khớp |
| B21CN10 | Chấn thương cột sống |

Round 3, năm 3: **chọn 4 trong 8 học phần**, mỗi môn 4 tín chỉ thực hành; yêu cầu
16 tín chỉ, không cộng cả 32 tín chỉ được cung cấp:

| Mã | Học phần |
|---|---|
| B21CN11 | Phẫu thuật gãy xương, trật khớp chi trên |
| B21CN12 | Phẫu thuật gãy xương, trật khớp chi dưới - khung chậu |
| B21CN13 | Phẫu thuật thay khớp và nội soi khớp |
| B21CN14 | Phẫu thuật kết hợp xương ít xâm lấn |
| B21CN15 | Phẫu thuật chấn thương cột sống |
| B21CN16 | Bệnh lý thoái hóa cột sống cổ |
| B21CN17 | Bệnh lý thoái hóa cột sống thắt lưng |
| B21CN18 | Phẫu thuật cột sống ít xâm lấn |

Có 12 học phần để tổ chức nội dung; mỗi người học theo chương trình này học 4
môn Round 2 và 4 môn Round 3 được lựa chọn, không mặc định học toàn bộ 12 môn.
Ảnh chưa chỉ định thứ tự giữa các môn trong cùng Round. Không lấy mức năng lực
1–5 trong khung đánh giá để tự suy ra thứ tự năm học/Round.

## Các học phần trước đó

Giữ danh mục đầy đủ để đối chiếu nguồn, nhưng giao diện học chính không xếp lại
các môn trước đó thành khóa học bắt buộc. B21CN1 Cấp cứu ngoại CTCH cũng thuộc
phần nền tảng, không còn là học phần mẫu được ưu tiên phát triển bài học.

Phần nền tảng chỉ hiển thị yêu cầu/chuẩn đầu ra. Khi chưa có chuẩn đầu ra riêng
của học phần, ghi rõ đang chờ giảng viên xác nhận. Các PLO cấp chương trình hiện
có vẫn giữ đúng phạm vi chương trình, không biến thành CLO của từng môn. Các môn
tự chọn ở giai đoạn trước không tự động trở thành điều kiện bắt buộc phải hoàn
thành tất cả. Không đánh dấu học viên đã đạt hoặc đã hoàn thành chỉ từ giả định
về đối tượng sử dụng của sản phẩm.

Hai sách hiện có tiếp tục làm tài liệu nguồn cho các chủ đề phù hợp trong 12
môn trọng tâm, hoặc tài liệu ôn lại theo nhu cầu. Không tự coi hai sách đã bao phủ
đầy đủ các môn chuyên sâu như nội soi, thay khớp và phẫu thuật ít xâm lấn. Phần
thiếu tài liệu vẫn được ghi nhận để bổ sung; không gọi model để tự viết bù.

## Cách áp dụng

Phạm vi sản phẩm nằm tại
`apps/backend/app/modules/knowledge/residency_scope.json`. Metadata môn được
đối chiếu với `data/curriculum/curriculum_map.json` và ảnh mới; đây là phạm vi
sản phẩm người dùng chọn, không phải một quyết định ban hành CTĐT mới.

API `/api/v1/knowledge/curriculum` giữ đủ danh mục và nguồn hiện có, đồng thời
gắn `study_role=focus` cho B21CN7–B21CN18, và `prior_outcomes_only` cho các môn
khác. Các môn nền tảng không còn được trả danh sách chủ đề học gợi ý. Trang
`/curriculum` hiển thị hai nhóm chuyên ngành trước; phần nền tảng thu gọn ở dưới.

Điều chỉnh này không sửa/xóa node hoặc quan hệ Neo4j, không đổi dữ liệu tiến độ
PostgreSQL, không biến phạm vi học thành kết quả đánh giá, không gọi model. Nó
thu hẹp đúng đối tượng và danh sách môn; đề cương và việc đóng gói bài học cụ thể
cho 12 môn vẫn là công việc tiếp theo.
