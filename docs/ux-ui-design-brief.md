# MedResident Tutor — tài liệu bàn giao thiết kế UX/UI

Ngày rà soát: 27/10/2026. Nguồn: mã frontend hiện tại trong `apps/frontend`.

Tài liệu này có thể đưa nguyên văn vào công cụ thiết kế UX/UI. “Route” là đường dẫn trên website; “file nguồn” là nơi triển khai trong dự án. Địa chỉ chạy local: `http://localhost:3000`.

## 1. Bối cảnh sản phẩm và phạm vi thiết kế

MedResident Tutor là website hỗ trợ học tập cho bác sĩ nội trú: luyện trả lời câu hỏi tự luận ngắn, xem phản hồi theo tiêu chí, đối chiếu tài liệu nguồn và xem lại các lượt làm bài. Quản trị viên quản lý câu hỏi, rubric chấm điểm và tải tài liệu lên.

Đối tượng sử dụng:

- Khách: xem trang giới thiệu, đăng ký, đăng nhập.
- Người học (`LEARNER`): luyện tập và xem lịch sử cá nhân.
- Quản trị viên (`ADMIN`): sử dụng luồng luyện tập và quản lý câu hỏi/tài liệu.

Hiện tại cần thiết kế lại trải nghiệm web dựa trên chức năng hiện có. Phản hồi Medical/Teaching đang được giả lập; thiết kế vẫn cần thể hiện cấu trúc kết quả, nhưng không diễn đạt như hệ thống đã chấm năng lực thật. Sản phẩm phục vụ học tập, không phục vụ chẩn đoán hoặc quyết định điều trị.

Ngôn ngữ thiết kế đề xuất: tiếng Việt nhất quán. Giao diện hiện tại đang lẫn tiếng Việt và tiếng Anh; không cần giữ cách đặt tên tiếng Anh hiện tại nếu có thể thay bằng nhãn tiếng Việt dễ hiểu.

## 2. Danh mục toàn bộ route hiện có

| Trang | Route | Truy cập hiện tại | Mức độ triển khai | File nguồn |
|---|---|---|---|---|
| Trang chủ | `/` | Công khai | Có nội dung giới thiệu và CTA | `apps/frontend/app/page.tsx` |
| Đăng nhập | `/login` | Công khai | Có chức năng | `apps/frontend/app/login/page.tsx` |
| Đăng ký | `/register` | Công khai | Có chức năng | `apps/frontend/app/register/page.tsx` |
| Tổng quan | `/dashboard` | Hiện chưa có chặn đăng nhập riêng | Trang giữ chỗ | `apps/frontend/app/dashboard/page.tsx` |
| Luyện tập, kết quả và lịch sử | `/learn` | Cần đăng nhập | Có chức năng | `apps/frontend/app/learn/page.tsx` |
| Bài thi | `/exams` | Hiện chưa có chặn đăng nhập riêng | Trang giữ chỗ | `apps/frontend/app/exams/page.tsx` |
| Tiến độ học tập | `/progress` | Hiện chưa có chặn đăng nhập riêng | Trang giữ chỗ | `apps/frontend/app/progress/page.tsx` |
| Ngân hàng câu hỏi | `/admin/questions` | Chỉ ADMIN | Có chức năng | `apps/frontend/app/admin/questions/page.tsx` |
| Quản trị tài liệu | `/admin/documents` | Chỉ ADMIN | Có chức năng tải lên | `apps/frontend/app/admin/documents/page.tsx` |

Có **9 route trang**. Những địa chỉ dưới đây là trạng thái của route hiện có, không phải trang độc lập:

- `/learn?attempt=<UUID>`: mở lại một lượt luyện tập cụ thể.
- `/login?reason=required&next=...`: yêu cầu đăng nhập để tiếp tục đến trang đích.
- `/login?reason=expired&next=...`: thông báo phiên hết hạn và đường dẫn quay lại.
- `/login?reason=logout`: thông báo đã đăng xuất.

API documentation ở `http://localhost:8000/docs` là công cụ kỹ thuật của backend, không nằm trong 9 trang sản phẩm cần thiết kế.

## 3. Điều hướng và thành phần dùng chung

Hiện tại mọi trang dùng một thanh điều hướng trên cùng:

- Logo chữ “Resident Learning”, bấm về `/`.
- Các liên kết luôn xuất hiện: Dashboard, Luyện tập, Exams, Progress.
- Khi chưa đăng nhập: Đăng nhập và Đăng ký.
- Khi đã đăng nhập: nút Đăng xuất.
- Khi xác định tài khoản ADMIN: thêm Ngân hàng câu hỏi và Documents.

Đăng xuất xóa token của trình duyệt và chuyển về trang đăng nhập. Khi phiên hết hạn, người dùng được đưa về đăng nhập; dữ liệu bản nháp luyện tập được giữ riêng theo tài khoản. Các trang admin có trạng thái đang kiểm tra quyền; người học truy cập trực tiếp sẽ thấy thông báo không có quyền.

Đề xuất thiết kế, chưa phải chức năng mới đã triển khai:

- Tách điều hướng công khai với không gian học tập sau đăng nhập.
- Nhóm các mục quản trị rõ ràng, chỉ hiển thị với ADMIN.
- Có chỉ dấu trang đang mở và bố cục điều hướng phù hợp trên điện thoại.
- Dùng cùng hệ thống nút, input, thông báo, loading, trạng thái trống và lỗi trên toàn bộ web.
- Với các mục giữ chỗ, thể hiện “Sắp có” hoặc ẩn khỏi điều hướng chính; lựa chọn này cần được quyết định khi triển khai thiết kế.

File thành phần: `components/Nav.tsx`, `components/AdminOnly.tsx`, `app/layout.tsx`, `app/globals.css` bên trong `apps/frontend`.

## 4. Chi tiết từng trang

### 4.1. Trang chủ — `/`

**Mục đích:** giới thiệu website và đưa khách đến đăng ký/đăng nhập.

**Nội dung hiện có:** nhãn prototype, tiêu đề hỗ trợ học tập có cấu trúc cho bác sĩ nội trú, đoạn mô tả tổ chức chủ đề/luyện tập/theo dõi tiến độ và thông báo giới hạn sử dụng cho học tập.

**Thao tác:** “Create account” đi tới `/register`; “Sign in” đi tới `/login`; logo về trang chủ.

**Giới hạn hiện tại:** đây là trang giới thiệu tĩnh; không có thống kê cá nhân, danh sách khóa học, giá dịch vụ hoặc tìm kiếm. Các ý về tiến độ trong nội dung giới thiệu chưa tương ứng với chức năng tiến độ hoàn chỉnh.

**Yêu cầu thiết kế:** làm rõ giá trị của việc luyện tập và đối chiếu tài liệu; CTA chính dễ nhận biết. Không tự thêm số lượng học viên, lời chứng thực, điểm đánh giá hoặc số liệu chưa có dữ liệu thực.

### 4.2. Đăng nhập — `/login`

**Mục đích:** xác thực tài khoản bằng email/mật khẩu và tiếp tục phiên học.

**Trường nhập:** email; mật khẩu.

**Thao tác:** Đăng nhập; liên kết sang Đăng ký. Thành công mặc định chuyển đến `/learn`, hoặc trang đích hợp lệ trong tham số `next`.

**Trạng thái cần thiết kế:** mặc định; đang gửi; lỗi email; sai email/mật khẩu; lỗi mạng; phiên hết hạn; yêu cầu đăng nhập trước khi truy cập; đã đăng xuất.

**Google:** có vùng giao diện đăng nhập Google nhưng chưa có Client ID, nên nút đang bị vô hiệu hóa. Có thể bỏ vùng Google khỏi mockup phiên bản đầu; nếu đưa vào, thể hiện là tùy chọn chưa kích hoạt, không mô tả là đã dùng được.

**Chưa có:** quên mật khẩu, đặt lại mật khẩu, xác thực hai bước, lựa chọn “ghi nhớ đăng nhập”. Không tạo các luồng này như thể đã có backend hỗ trợ.

**Yêu cầu thiết kế:** lỗi gắn với đúng trường; thông báo phiên hết hạn tách khỏi lỗi nhập sai; đường sang đăng ký rõ ràng. Có thể đề xuất hiện/ẩn mật khẩu như cải tiến UI.

**Thành phần chính:** `apps/frontend/components/AuthForm.tsx` và `GoogleSignIn.tsx`.

### 4.3. Đăng ký — `/register`

**Mục đích:** tạo tài khoản người học mới.

**Trường nhập:** họ tên; email; mật khẩu; xác nhận mật khẩu.

**Quy tắc:** họ tên không được chỉ gồm khoảng trắng; mật khẩu 8–128 ký tự; hai lần nhập mật khẩu phải khớp; email đã tồn tại không được đăng ký lại. Tài khoản mới có quyền LEARNER, người dùng không chọn quyền ADMIN.

**Thao tác:** Tạo tài khoản; chuyển sang Đăng nhập nếu đã có tài khoản. Tạo thành công sẽ tự đăng nhập và mặc định chuyển tới `/learn`.

**Trạng thái:** đang tạo; thiếu/sai trường; xác nhận không khớp; email trùng; mất kết nối; tạo thành công và chuyển trang.

**Dữ liệu:** tài khoản lưu trong PostgreSQL; mật khẩu được hash Argon2id. Không hiển thị hash hoặc nội dung kỹ thuật này trong form người dùng.

**Chưa có:** xác minh email, OTP, nhập hồ sơ chuyên khoa, onboarding nhiều bước hoặc màn hình xác nhận email.

**Yêu cầu thiết kế:** chỉ dẫn độ dài mật khẩu trước khi gửi, lỗi dễ sửa, nút chính rõ ràng; không thêm checkbox đồng ý điều khoản nếu chưa có nội dung và chính sách tương ứng.

### 4.4. Tổng quan — `/dashboard`

**Hiện trạng:** chỉ có tiêu đề Dashboard và mô tả đây là khu vực tổng quan hoạt động học tập, chủ đề và bước tiếp theo trong tương lai. Không có số liệu hoặc tác vụ thật.

**Quyền hiện tại:** component chưa kiểm tra đăng nhập riêng; không coi đây là dashboard cá nhân đã được bảo vệ và triển khai.

**Phạm vi thiết kế hiện tại:** trang “Đang phát triển” có đường dẫn tới Luyện tập. Nếu thiết kế dashboard tương lai, đánh dấu riêng là ý tưởng mở rộng; không dùng số liệu mock như dữ liệu thật và không yêu cầu thêm tính năng trong lần thay UI hiện tại.

### 4.5. Luyện tập — `/learn`

**Mục đích:** chọn câu hỏi tự luận ngắn, nhập câu trả lời, gửi bài, xem kết quả và xem lại lịch sử cá nhân.

**Cấu trúc hiện tại gồm 4 vùng nằm chung trang:**

1. Thông báo chế độ thử nghiệm.
2. Form làm bài.
3. Kết quả của lượt đang chọn, nếu có.
4. Lịch sử của tôi.

**Vùng làm bài:** danh sách chọn câu hỏi hiện hiển thị mã câu hỏi; nội dung câu hỏi hiện ở đoạn văn bên dưới. Có ô trả lời tối đa 16.000 ký tự, nút Gửi câu trả lời và Tạo lượt mới. Nút gửi bị khóa khi chưa tải xong, chưa chọn câu hỏi, câu trả lời trống hoặc đang xử lý.

**Bản nháp:** được lưu trên trình duyệt theo từng tài khoản; tải lại trang có thể khôi phục. Không hiển thị bản nháp của người trước sau khi đổi tài khoản.

**Lượt đang chờ:** nếu mất kết nối trước khi nhận kết quả, hiển thị thông báo và nút “Gửi lại lần nộp đang chờ”. Gửi lại phải lấy đúng lượt đã lưu, tránh tạo bài trùng. Giao diện có thể diễn đạt đơn giản, không cần đưa thuật ngữ kỹ thuật “key” cho người học.

**Vùng kết quả:**

- Câu hỏi và câu trả lời đã nộp.
- Trạng thái riêng của hai giai đoạn Medical và Teaching.
- Medical: tổng điểm/điểm tối đa; ý đúng; ý sai; ý thiếu; điểm từng tiêu chí và lý do; thông báo đủ/chưa đủ tài liệu căn cứ.
- Teaching: nhận xét tổng quát; điểm mạnh; hướng sửa ý sai; nội dung cần bổ sung; ưu tiên học tập; câu hỏi tiếp theo nếu có.
- Evidence: tên đoạn nguồn, tên tài liệu, trang PDF, trang in nếu có và nội dung trích dẫn; trạng thái chuyên gia duyệt chưa xác minh.
- Chi tiết nguồn có thể mở rộng: định danh lượt/câu hỏi, thông tin nguồn và metadata. Nên đặt thông tin kỹ thuật ở vùng phụ, không làm trọng tâm kết quả.

**Trạng thái xử lý:** chờ, đang xử lý Medical, đang xử lý Teaching, hoàn tất, lỗi Medical, lỗi Teaching. Khi Teaching lỗi, phần Medical đã lưu vẫn được giữ lại. Có nút thử lại phần tương ứng. Khi quá trình đang chạy, trang tự cập nhật trạng thái.

**Lịch sử:** danh sách các lượt của tài khoản hiện tại, hiện hiển thị mã câu hỏi và trạng thái. Bấm một lượt để xem kết quả ngay trong trang và cập nhật URL `/learn?attempt=<UUID>`. Backend trả tối đa 100 lượt gần nhất; chưa có tìm kiếm hoặc phân trang lịch sử trên UI.

**Tạo lượt mới:** xóa phần trả lời đang soạn và kết quả đang mở khỏi form, giữ lịch sử đã lưu; URL trở về `/learn`.

**Trạng thái cần thiết kế thêm về cách trình bày:** đang xác thực; tải dữ liệu; chưa có câu hỏi; chưa có lịch sử; chưa làm bài; đang soạn; đang gửi; kết quả từng phần; lỗi mạng; lượt không tồn tại/không thuộc tài khoản; phiên hết hạn. Một số trạng thái trống hiện chưa có lời giải thích riêng rõ ràng.

**Giới hạn:** chưa có thi tính giờ, chọn độ khó/chuyên khoa, chat gia sư, bảng xếp hạng hoặc tự động cập nhật tiến độ/mastery. Chế độ mock trả điểm/phản hồi giả lập, không chấm năng lực thật.

**Yêu cầu thiết kế:** phân tách rõ việc làm bài với xem kết quả; lịch sử dễ tìm; câu hỏi dễ đọc hơn mã kỹ thuật. Có thể đề xuất tab hoặc panel trong cùng `/learn`, giữ khả năng mở lượt bằng URL. Nếu muốn tách thành route lịch sử/chi tiết riêng, ghi rõ là thay đổi cấu trúc cần triển khai sau.

**Thành phần liên quan:** `PracticeResult.tsx`, `lib/practice-types.ts`, `lib/practice-storage.ts`.

### 4.6. Bài thi — `/exams`

**Hiện trạng:** trang giữ chỗ thông báo chức năng tổ chức thi và chấm bài thuộc giai đoạn sau.

**Chưa có trên UI:** danh sách đề, bắt đầu thi, đồng hồ, điều hướng câu hỏi, nộp đề, kết quả thi.

**Phạm vi thiết kế hiện tại:** trạng thái “Sắp có” và CTA sang Luyện tập. Mockup thi đầy đủ, nếu tạo, phải được ghi là phạm vi tương lai.

### 4.7. Tiến độ học tập — `/progress`

**Hiện trạng:** trang giữ chỗ cho trực quan hóa kết quả học và gợi ý học tập.

**Chưa có trên UI:** biểu đồ tiến độ, thống kê năng lực, streak, mục tiêu ngày, gợi ý học cá nhân hóa.

**Phạm vi thiết kế hiện tại:** trạng thái “Sắp có”. Không chuyển điểm giả lập của các lượt luyện tập thành biểu đồ năng lực thật.

### 4.8. Ngân hàng câu hỏi — `/admin/questions`

**Mục đích:** ADMIN tạo/sửa câu hỏi tự luận ngắn, cấu hình rubric và gắn căn cứ tài liệu cho từng tiêu chí; quản lý câu hỏi được đưa vào luyện tập.

**Vùng danh sách:** tìm theo nội dung hoặc mã; 20 câu/trang; Trang trước/Trang tiếp; hiển thị nội dung và trạng thái đang/chưa sử dụng; bấm câu để sửa; nút Tạo câu hỏi mới.

**Vùng tạo/sửa:**

- Nội dung câu hỏi, tối đa 4.000 ký tự.
- Tên rubric, tối đa 255 ký tự.
- Điểm tối đa rubric và tổng điểm các tiêu chí.
- Một hoặc nhiều tiêu chí; mỗi tiêu chí có mô tả, điểm tối đa và danh sách evidence được chọn.
- Thêm tiêu chí; xóa tiêu chí, giữ tối thiểu 1 và tối đa 100 tiêu chí.
- Lưu câu hỏi và rubric.
- Với câu đã có: vùng định danh ổn định và phiên bản có thể mở rộng.

**Quy tắc lưu:** nội dung câu hỏi/tên rubric/mô tả tiêu chí không trống; điểm mỗi tiêu chí phải hữu hạn và lớn hơn 0; tổng điểm tiêu chí bằng điểm rubric; mỗi tiêu chí cần ít nhất một evidence.

**Vùng tìm/chọn evidence:** tìm các đoạn tài liệu hiện có; phân trang 20 đoạn; chọn bằng checkbox cho từng tiêu chí. Hiển thị tên đoạn, nội dung, tài liệu, trang PDF, trang in, trạng thái review và lỗi metadata nếu có. Đoạn có metadata lỗi không được chọn mới. Nút Xem evidence mở phần xem trước trong cùng trang. Chỉ đọc/chọn, không sửa nguồn tại đây.

**Trạng thái khả dụng:** sau khi lưu có thể Đưa vào sử dụng hoặc Ngừng sử dụng. Phải lưu thay đổi trước khi chuyển trạng thái. Ngừng sử dụng ngăn chọn cho lượt mới nhưng giữ lịch sử cũ. “Đang sử dụng” không đồng nghĩa “đã được chuyên gia duyệt”.

**Trạng thái cần thiết kế:** kiểm tra quyền; không có quyền; tải danh sách; danh sách rỗng; không có kết quả tìm; tạo mới; chỉnh sửa; thay đổi chưa lưu; đang lưu; lưu thành công; lỗi theo trường; phiên bản xung đột do dữ liệu đã thay đổi; nguồn thiếu/sai metadata.

**Giới hạn:** chưa có xóa câu hỏi, thao tác hàng loạt, upload/import câu hỏi ngay trên trang, duyệt chuyên gia, chỉnh nguồn, hoặc form quản lý Topic. Topic có thể để trống nhưng UI không có bộ chọn Topic.

**Yêu cầu thiết kế:** đây là trang có mật độ thông tin cao nhất. Ưu tiên bố cục danh sách + trình biên tập, cách thêm tiêu chí gọn, bộ chọn evidence dễ tra cứu. Giữ tách biệt thao tác “Lưu” với “Đưa vào sử dụng”. Không cần biến mã định danh và phiên bản thành nội dung chính.

### 4.9. Quản trị tài liệu — `/admin/documents`

**Mục đích:** ADMIN tải tài liệu lên hệ thống.

**Trường nhập:** tên hiển thị, không bắt buộc; một file, bắt buộc. Chấp nhận PDF, TXT và Markdown (`.pdf`, `.txt`, `.md`, `.markdown`). Giới hạn dung lượng do backend cấu hình; mặc định 10 MB.

**Thao tác:** chọn file và Upload. Gửi thành công hiển thị tên tài liệu, trạng thái xử lý và giải thích OCR/indexing chưa bắt đầu.

**Trạng thái:** đang kiểm tra quyền; không có quyền; chưa chọn file; đã chọn file; đang upload; upload thành công; sai loại file/quá dung lượng/lỗi mạng.

**Giới hạn:** trang hiện chỉ có form upload và thông báo. Chưa có danh sách tài liệu, xem PDF, tìm kiếm tài liệu, xóa/tải xuống, hàng đợi OCR hoặc nút xử lý tự động. Upload xong chưa tự sinh đoạn nguồn cho ngân hàng câu hỏi.

**Yêu cầu thiết kế:** thể hiện rõ tên file đã chọn, loại file/dung lượng cho phép và phản hồi thành công. Có thể thiết kế vùng kéo thả như cải tiến UI; danh sách quản lý tài liệu là tính năng mở rộng cần ghi riêng.

## 5. Các luồng người dùng cần bàn giao

| Luồng | Các bước |
|---|---|
| Người dùng mới | Trang chủ → Đăng ký → nhập thông tin → tạo tài khoản → tự đăng nhập → Luyện tập |
| Người dùng quay lại | Đăng nhập → Luyện tập → khôi phục bản nháp nếu có |
| Làm bài | Chọn câu hỏi → đọc đề → nhập câu trả lời → gửi → xem trạng thái → xem kết quả/căn cứ |
| Xem lại bài | Luyện tập → Lịch sử của tôi → chọn lượt → xem kết quả đã lưu |
| Phục hồi sau lỗi mạng | Có lượt đang chờ → gửi lại lượt đang chờ → mở đúng kết quả đã lưu |
| Phục hồi xử lý | Medical/Teaching lỗi → thử lại phần tương ứng → cập nhật kết quả |
| Quản lý câu hỏi | ADMIN → Ngân hàng câu hỏi → tạo/sửa → thêm tiêu chí và evidence → lưu → đưa vào sử dụng |
| Dừng câu hỏi | ADMIN → mở câu đã lưu → ngừng sử dụng → lượt mới không còn chọn được, lịch sử vẫn xem được |
| Tải tài liệu | ADMIN → Quản trị tài liệu → chọn file → upload → xem trạng thái đã lưu |
| Phiên hết hạn | Trang cần xác thực → Đăng nhập với thông báo → đăng nhập lại → quay lại trang đích hợp lệ |

## 6. Những màn hình chưa có route riêng

Để tránh thiết kế vượt phạm vi, lưu ý hiện chưa có trang hồ sơ, cài đặt tài khoản, đổi/quên mật khẩu, quản lý người dùng, quản lý chuyên khoa/chủ đề, thư viện tài liệu cho người học, chi tiết PDF, chat gia sư, trang lịch sử độc lập hoặc trang chi tiết câu hỏi độc lập. Trình biên tập câu hỏi và trình xem evidence nằm trong `/admin/questions`; kết quả và lịch sử nằm trong `/learn`.

Nếu công cụ thiết kế đề xuất các trang mới, yêu cầu đặt chúng trong mục “Đề xuất mở rộng”, ghi rõ route dự kiến và không coi là phần chức năng đã có.

## 7. Đầu ra mong muốn từ công cụ thiết kế

- Sitemap tương ứng các route hiện tại; đánh dấu 3 trang giữ chỗ.
- Thiết kế desktop và mobile cho Trang chủ, Đăng nhập, Đăng ký, Luyện tập, Ngân hàng câu hỏi và Quản trị tài liệu.
- Thiết kế các trạng thái loading, trống, lỗi, thành công, mất quyền và hết phiên.
- Bộ thành phần dùng chung: điều hướng, button, input, textarea, select, checkbox, badge trạng thái, alert, pagination, card, vùng nguồn trích dẫn và tiêu chí chấm.
- Prototype bấm chuyển trang cho các luồng ở mục 5; ghi rõ nút nào đổi route, nút nào chỉ đổi trạng thái trong cùng trang.
- Quy tắc typography, màu sắc, spacing, breakpoint và trạng thái focus/disabled; nhãn/độ tương phản dễ đọc, thao tác bằng bàn phím.
- Với bố cục mới, giữ nguyên dữ liệu và ý nghĩa chức năng hiện có; mọi đề xuất thêm chức năng được tách thành danh sách mở rộng.

## 8. Prompt có thể sao chép vào công cụ thiết kế

> Hãy thiết kế lại UX/UI cho MedResident Tutor, một web hỗ trợ học tập cho bác sĩ nội trú. Sử dụng bản mô tả route và chức năng trong tài liệu này làm nguồn yêu cầu. Ngôn ngữ tiếng Việt; phong cách chuyên nghiệp, rõ ràng, dễ đọc nội dung dài và thao tác trên desktop/mobile. Có 3 nhóm: khách, người học, quản trị viên. Tập trung vào luồng đăng ký/đăng nhập, luyện tập tự luận, xem kết quả và nguồn trích dẫn, xem lại lịch sử, quản trị câu hỏi/rubric/evidence, tải tài liệu. Giữ nguyên 9 route đã liệt kê; Dashboard, Exams và Progress hiện là trang sắp có. Lịch sử/kết quả nằm trong /learn; chỉnh sửa câu hỏi và xem evidence nằm trong /admin/questions. Không tự thêm chức năng backend chưa có. Google login chưa kích hoạt, có thể bỏ khỏi phiên bản thiết kế đầu. Thiết kế đủ trạng thái rỗng/loading/lỗi/thành công/quyền truy cập và quá trình xử lý từng giai đoạn. Phân biệt trạng thái đưa câu hỏi vào sử dụng với chuyên gia duyệt; giữ cảnh báo kết quả giả lập ở chế độ thử nghiệm. Trả về sitemap, design system, các màn hình desktop/mobile và prototype chuyển trang. Nếu đề xuất tính năng hoặc route mới, trình bày riêng là mở rộng tương lai.
