# Kiểm tra nguồn HMU công khai cho các học phần CTCH — 05/11/2026

Kết luận: **có thể tìm và đọc thêm nội dung chuyên môn từ nguồn HMU mà không
đăng nhập**. Yêu cầu đăng nhập của LMS không áp dụng cho toàn bộ nguồn do HMU
công bố. Trong đợt này đã kiểm tra truy cập ẩn danh, tải và mở sáu PDF bài báo.
Không gọi LLM, không import hoặc sửa dữ liệu Neo4j/PostgreSQL.

## Phạm vi truy cập đã kiểm tra trực tiếp

| Nơi lưu trữ | Kết quả |
|---|---|
| LMS, 12 trang B21CN7–B21CN18 | Cả 12 chuyển về `/login/index.php`. HTTP cuối 200 là trang đăng nhập, không phải bài học đã mở được. |
| Tạp chí Nghiên cứu Y học | Sáu trang bài báo và sáu PDF đều trả HTTP 200; PDF có chữ ký `%PDF-` hợp lệ và mở được bằng parser. Không gửi tài khoản/cookie đăng nhập. |
| Cổng Sau đại học, bốn liên kết PDF cũ | Đều trả HTTP 500 tại thời điểm kiểm tra. Không chuyển tới đăng nhập; chưa thể khẳng định file còn tải được hoặc lỗi do quyền truy cập. |

Hai ví dụ LMS là [B21CN7](https://lms.hmu.edu.vn/course/view.php?id=21465) và
[B21CN14](https://lms.hmu.edu.vn/course/view.php?id=21492). Các mã còn lại đã kiểm
tra theo URL học phần trong dữ liệu Curriculum hiện có.

Tạp chí sử dụng tên miền `tapchinghiencuuyhoc.vn`; trang
[giới thiệu](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/about) và chân trang
các bài ghi cơ quan chủ quản là **Trường Đại học Y Hà Nội**. Đây là nguồn do HMU
xuất bản, dù tên miền không kết thúc bằng `hmu.edu.vn`. Không đồng nghĩa tất cả
tác giả đều công tác ở HMU hoặc bài báo thuộc đề cương của một học phần.

## Sáu nguồn toàn văn đã xác nhận

Tên dưới đây rút gọn theo chủ đề; nhan đề và metadata xuất bản giữ trong catalog.
Ghép học phần là đề xuất theo chủ đề, **chưa phải ánh xạ đề cương được duyệt**.

| Bài báo | PDF | Học phần có thể tham khảo |
|---|---|---|
| [Thay khớp háng với trợ cụ cá thể hóa](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/view/1348) | [10 trang](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/download/1348/875) | B21CN9, B21CN13 |
| [Cố định cột sống ít xâm lấn trong chấn thương ngực–thắt lưng](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/view/485) | [9 trang](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/download/485/746) | B21CN10, B21CN15, B21CN18 |
| [Nội soi liên bản sống điều trị thoát vị đĩa đệm thắt lưng](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/view/2878) | [6 trang](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/download/2878/2067) | B21CN17, B21CN18 |
| [Giải phẫu và cơ sinh học gân mác dài trong tái tạo dây chằng](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/view/1367) | [8 trang](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/download/1367/884) | B21CN9, B21CN13 |
| [Hàn xương liên thân đốt và cảnh báo thần kinh trong điều trị trượt đốt sống](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/view/3462) | [11 trang](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/download/3462/2336) | B21CN17, B21CN18 |
| [Phẫu thuật lối bên trong hẹp ống sống và trượt đốt sống thắt lưng](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/view/2443) | [9 trang](https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/download/2443/1623) | B21CN17, B21CN18 |

Mỗi nguồn có URL bài báo/PDF, thông tin trích dẫn, thời điểm kiểm tra, số trang và
SHA-256 trong [catalog ứng viên](../data/sources/hmu-public-candidates-20261105.json).
Ngày trong citation metadata có thể khác ngày hiển thị trên trang; chưa tự chọn
một ngày làm mốc duy nhất. Bản trích text của PDF 485 có ký tự NUL xen giữa từ,
cần chuẩn hóa có lưu bản gốc nếu xử lý nội dung sau này.

Các PDF cũ tại cổng Sau đại học đã thử:

- `https://sdh.hmu.edu.vn/images/DOMANHHUNG-LA_Ctch%26th.pdf`
- `https://sdh.hmu.edu.vn/images/ngcuusinh/LEMANHSON_LA.pdf`
- `https://sdh.hmu.edu.vn/images/DOVANMINH-LA%20Ctch%26TH33.pdf`
- `https://sdh.hmu.edu.vn/images/TVLA%20LETHANHTUNG.pdf`

Kết quả search index có thể vẫn hiển thị nội dung của các file này, nhưng chưa
dùng preview được lập chỉ mục như bằng chứng rằng hiện đã tải được toàn văn.

## Giá trị và giới hạn cho dự án

Có thể bổ sung bài đọc chuyên sâu, tài liệu đối chiếu và ví dụ để thảo luận bằng
chứng cho các chủ đề tương ứng. Hai sách sẵn có vẫn là nguồn nội dung nền theo
chủ đề; các bài báo này bổ sung một số vấn đề chuyên sâu.

Chưa tìm được bộ đề cương công khai đầy đủ cho cả 12 học phần trong đợt tìm kiếm
này. Sáu bài nghiên cứu cũng chưa phủ đủ 12 môn. Không tự coi một nghiên cứu là
hướng dẫn lâm sàng chung, bài giảng chính thức, barem hoặc chuẩn đầu ra của môn.
Giảng viên vẫn cần xác nhận mục tiêu, phạm vi và thứ tự bài học, nhưng việc tìm
và chuẩn bị tài liệu công khai có thể tiếp tục trước khi có toàn bộ đề cương.

Catalog chỉ ghi ứng viên, `imported_to_neo4j=false`. Chưa thay allowlist URL,
catalog runtime hai sách, hoặc import các phát biểu chuyên môn vào KG. Log truy
cập và bản PDF dùng để đối chiếu nằm ở
`data/backups/hmu-access-check-20261105/`, được Git bỏ qua.
