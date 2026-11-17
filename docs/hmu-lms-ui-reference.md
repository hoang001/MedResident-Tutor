# Tham khảo LMS HMU để hoàn thiện trải nghiệm MedResident Tutor

Ngày khảo sát: 05/11/2026. Đây là bản đề xuất để trao đổi, chưa phải phương án
thiết kế đã chốt hoặc xác nhận chức năng nội bộ của LMS. Đã xem trang công khai,
chụp giao diện desktop 1440px/mobile 390px và đối chiếu với frontend hiện có.

Nguồn tham chiếu:

- [Trang chủ LMS HMU](https://lms.hmu.edu.vn/).
- [Chương trình BSNT Ngoại khoa](https://lms.hmu.edu.vn/course/index.php?categoryid=1944).
- `PRODUCT.md`, `DESIGN.md`, các trang trong `apps/frontend/app` và phạm vi
  B21CN7–B21CN18 tại `docs/residency-study-scope.md`.

## Phần thực sự quan sát được

Trang chủ có header nhận diện trường, tìm kiếm/đăng nhập, lựa chọn ngôn ngữ,
banner ảnh, phần giới thiệu chương trình, thẻ chương trình có ảnh, các nút vào
danh mục và footer liên kết dịch vụ của trường. Trang BSNT Ngoại khoa có đường
dẫn phân cấp, mô tả/mục tiêu chương trình, liên kết chuẩn đầu ra và danh mục thu
gọn theo năm học.

Trang học phần yêu cầu đăng nhập. Chưa xem được bố cục bài giảng, bài tập, điểm
số, giao bài hoặc màn hình quản lý khóa học bên trong. Các đề xuất về màn hình
học ở dưới dựa trên nhu cầu MedResident, không khẳng định đã quan sát chúng ở HMU.

## Hướng áp dụng cho MedResident

| Tham chiếu | Áp dụng vào dự án | Trạng thái hiện tại |
|---|---|---|
| Banner và hình ảnh đào tạo | Một hình giới thiệu phù hợp với học nội trú; tên sản phẩm và nút vào học rõ ràng | Trang chủ hiện chủ yếu là chữ và liên kết |
| Thẻ chương trình có ảnh | Thẻ cho các học phần CTCH, phân nhóm chi trên/chi dưới/khớp/cột sống; hiện mã, Round và số tín chỉ | Curriculum đã có 12 môn nhưng đang là danh sách chữ |
| Danh mục theo năm | Nhóm Round 2 năm 2: 4 môn bắt buộc; Round 3 năm 3: chọn 4/8 môn | API và giao diện đã phân phạm vi; chưa có hồ sơ lưu lựa chọn 4 môn của từng học viên |
| Đường dẫn phân cấp | Chương trình → học phần → chủ đề/bài học; người học biết đang ở đâu | Chưa có trang khóa học/bài học hoàn chỉnh theo học phần |
| Mục tiêu chương trình và nguồn | Mỗi môn có phần mục tiêu, chuẩn đầu ra, tài liệu và danh sách bài sau khi giảng viên cung cấp | Có PLO cấp chương trình và nguồn; chưa có đủ CLO/đề cương từng môn |
| Tìm kiếm dễ thấy | Giữ tra cứu thư viện, thêm tìm môn/bài trong phạm vi khóa học khi đã có cấu trúc bài | Có tìm kiếm từ khóa trong KG; chưa có chỉ mục bài học theo môn |

Tham khảo cách tạo phân cấp và nhịp đọc, giữ nhận diện MedResident nhất quán với
`DESIGN.md` hiện tại. Một người học trở lại cần thấy môn/bài đang học và hành động
tiếp theo sớm; phần giới thiệu dài phù hợp hơn với khách chưa đăng nhập.

## Luồng học đề xuất

**Trang chủ → không gian học cá nhân → Round 2 hoặc nhóm Round 3 đã chọn → học phần
→ bài học → tự luyện → xem lại và tiếp tục.**

Trang học phần nên có tên/mã môn, mục tiêu, điều kiện nền tảng, tài liệu chính
thức, các bài theo thứ tự và trạng thái chuẩn bị. Môn thiếu nội dung được ghi rõ
đang chờ tài liệu, không tạo nút học dẫn vào một trang rỗng.

Trang bài học nên có mục lục bên cạnh trên desktop, nội dung dễ đọc, nguồn/trang
PDF, hình minh họa, ghi chú và nút bài trước/bài tiếp. Trên điện thoại, mục lục
thu gọn; giữ chỗ cho nội dung và hành động học tiếp.

Không gian học cá nhân có thể dùng lại ghi chú, dấu trang và bài tự luyện đang
lưu. Muốn hiển thị phần trăm hoàn thành một môn cần có danh sách bài và liên kết
tiến độ tới từng bài; số node đã đọc hiện tại chưa đủ để tính tỷ lệ hoàn thành môn.

## Hình ảnh

- Dùng banner về môi trường học/thực hành y khoa và hình bìa theo nhóm CTCH để
  người học nhận ra nội dung; giữ ảnh trang trí ở mức vừa phải trong màn hình đọc.
- Ảnh minh họa giải phẫu/kỹ thuật trong bài cần nguồn, chú thích và kiểm tra nội
  dung, ưu tiên tài liệu giảng dạy giảng viên cung cấp. Không dùng ảnh trang trí
  như bằng chứng chuyên môn.
- Ảnh và logo trên HMU được khảo sát như tài liệu tham chiếu. Chưa xác minh quyền
  tái sử dụng chúng cho dự án; bản triển khai dự kiến dùng nhận diện MedResident
  và bộ ảnh riêng có nguồn sử dụng rõ ràng.
- Không đưa số người học/khóa học của HMU thành thống kê của MedResident.

## Phạm vi có thể triển khai trước khi có thêm tài liệu

1. Trang chủ có bố cục trực quan và hành động vào học rõ ràng.
2. Danh mục 12 học phần bằng thẻ; hiển thị đúng nhóm bắt buộc/tự chọn và tín chỉ.
3. Tiếp tục học từ những hoạt động cá nhân đã lưu; trạng thái môn có/chưa có nội dung.

Phần khóa học → bài giảng → tự luyện theo bài cần bổ sung cấu trúc bài và ánh xạ
tài liệu. Chấm điểm chính thức, giao bài và quy trình giảng viên phê duyệt cần
thiết kế nghiệp vụ/phân quyền riêng; chưa thể hoàn thành chỉ bằng thay giao diện.
Các phần đọc, tra cứu và tự luyện hiện có tiếp tục hoạt động không cần server model.

Bản chụp tham chiếu được lưu cục bộ trong
`data/backups/hmu-ui-reference-20261105/` (Git bỏ qua). Chưa chép tài sản hình ảnh
của trường vào frontend hoặc thay đổi giao diện ứng dụng trong lần khảo sát này.
