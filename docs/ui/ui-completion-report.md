# Bàn giao giao diện học tập — 16–17/11/2026

Hướng học thuật navy–teal, nền sáng, Source Sans 3 cho tiêu đề/wordmark và chữ hệ thống cho nội dung. Font tự lưu trong dự án, hỗ trợ tiếng Việt, có giấy phép OFL và hash nguồn tại `apps/frontend/public/fonts/sources.json`; không gọi dịch vụ font lúc sử dụng. Nguồn: [Adobe Source Sans](https://github.com/adobe-fonts/source-sans). Giữ nhận diện riêng MedResident Tutor. Đây là MVP theo các chức năng hiện có, chưa phải hệ thống đánh giá năng lực y khoa chính thức.

## Màn hình và đường đi

| Vai trò | URL local | Nội dung |
| --- | --- | --- |
| Công khai | http://localhost:3000/ | Giới thiệu đúng chức năng; đăng nhập/đăng ký |
| Student | http://localhost:3000/dashboard | Tiếp tục học, số lượt làm và hoạt động thật; chủ đề có thể luyện |
| Student | http://localhost:3000/learn | Danh mục bài khả dụng, tìm kiếm, chủ đề, phân trang, trạng thái đã làm |
| Student | http://localhost:3000/learn?question=QB26_SHOULDER_STABILIZERS | Đọc đề và trả lời; không hiện lời giải trước nộp |
| Student | http://localhost:3000/history | Tìm, lọc và mở lại kết quả/nguồn của đúng lượt làm |
| Student | http://localhost:3000/knowledge | Thư viện kiến thức, đọc, ghi chú, đánh dấu |
| Student | http://localhost:3000/sources | Sách, mục lục, trang PDF nguồn |
| Student | http://localhost:3000/progress | Tiến độ đọc và bài tự ôn; không quy đổi thành phần trăm năng lực |
| Student | http://localhost:3000/account | Thông tin tài khoản thật, đăng xuất |
| Admin | http://localhost:3000/admin/questions | Danh sách → biên soạn đề/đáp án/tiêu chí cạnh đoạn nguồn → lưu nháp → kiểm tra/phát hành |
| Admin | http://localhost:3000/admin/documents | Danh sách tài liệu thật và tải tệp lên |
| Tài nguyên bổ trợ | http://localhost:3000/curriculum | Khung chương trình, không hứa có đầy đủ đề cương/lộ trình |
| Tài nguyên bổ trợ | http://localhost:3000/exams | Tự ôn theo tài liệu, ghi rõ chưa chấm điểm; tách khỏi ngân hàng có gói chấm |

Menu chính tập trung vào học, bài tập, lịch sử, tiến độ. Admin chuyển qua không gian quản trị. Menu tài khoản dùng dữ liệu `/auth/me`; mobile mở điều hướng bằng dialog có đóng/Escape. Có skip link và focus bàn phím.

## Thay đổi hành vi

- Kết quả phân cấp điểm, từng tiêu chí, ý đúng/sai/thiếu, phản hồi, đáp án tham khảo và nguồn đóng mở. Giữ nguyên output/điểm được lưu.
- Nếu Teaching lỗi, phần Medical đã lưu vẫn hiện; người dùng chủ động thử lại phản hồi. Không đổi trạng thái để che lỗi.
- Lịch sử chỉ đọc snapshot của lượt làm. Không lấy rubric hiện hành rồi chấm lại.
- Giữ nháp theo tài khoản, khóa nút trong lúc nộp và dùng lại khóa idempotency khi kiểm tra lần nộp chưa nhận được phản hồi.
- Ảnh bài tập được xem lớn, giữ tỷ lệ gốc và tọa độ lưới/annotation. Không thêm ảnh AI hoặc thay evidence y khoa.
- Biên soạn thủ công hoạt động khi đề xuất tự động tắt. Tên sách, trang, đoạn trích và nguồn gắn với tiêu chí được hiển thị trực tiếp. Mobile chuyển giữa đề và nguồn; chọn đọc toàn bộ đoạn nguồn sẽ đưa focus tới nội dung đó.
- Lưu nháp và phát hành là hai thao tác riêng. Sửa câu đã phát hành tạo bản nháp phiên bản mới, kể cả câu legacy chưa có approved package. Lịch sử cũ giữ nguyên.

Không đưa UUID/hash/raw JSON/provider debug/mock scenarios ra màn hình học viên. ID vẫn dùng bên trong URL/API/reference. Thông tin phiên bản/hash cần thiết còn ở quản trị; test/fixture/benchmark và code nghiên cứu vẫn giữ trong repo. Nhãn mô phỏng, phát lại và chấm theo đáp án giữ đúng nguồn execution.

## Phạm vi API nhỏ

Thêm các endpoint đọc có kiểm quyền: `/admin/question-catalog`, `/admin/source-catalog`, `/admin/authoring/config`, `/practice/history`. Catalog student thêm trạng thái lượt làm mới nhất của chính tài khoản đó; không trả đáp án/tiêu chí/evidence trong danh mục. Endpoint cũ được giữ. Không migration, không đổi cơ chế chấm hay contract model.

## Giới hạn được thể hiện trong UI

Chưa có backend quản lý người dùng đầy đủ, sửa hồ sơ hay đổi mật khẩu: không dựng nút giả. Tải tài liệu chỉ lưu tệp, không tự OCR/trích xuất/lập chỉ mục. Danh sách tài liệu dùng tối đa 100 mục gần đây theo API hiện có và ghi rõ phạm vi đó. Chưa bật authoring LLM; không giả sinh đáp án. Phát hành trong ứng dụng không phải chuyên gia y khoa phê duyệt. Khung chương trình và mapping sách vẫn cần giảng viên xác nhận. Không thử tích hợp model live trong đợt này.

## Kiểm tra và bằng chứng

Backend: **56 kiểm thử qua**, gồm các regression authoring, contract practice, retrieval, structured grading, question bank, mở rộng ngân hàng và test catalog/history/quyền mới. Chạy trong `medresident_test_ui_regression_20261116`, không chạy DDL trên DB chính. Log/JUnit: `data/authoring/ui-completion-20261116/tests.log`, `tests.xml`.

Frontend typecheck, ESLint và production build đã chạy. Các suite Playwright cũ được giữ nguyên; chúng dùng selector/điều hướng của giao diện trước, không được tính là đã qua trong đợt này. Suite mới kiểm các hành vi đang thay đổi bằng API thật và provider mock trong DB test riêng.

**3 kiểm thử Playwright qua** với API thật và mock có nhãn: admin tạo/sửa/chọn nguồn/lưu nháp/phát hành; student tìm kiếm/phân trang/empty state/làm bài; mạng lỗi giữ câu trả lời; Teaching lỗi giữ Medical và thử lại thủ công; mở evidence, reload history giữ nguyên snapshot/kết quả; bài có lựa chọn, ảnh phóng lớn và không lộ annotation trước nộp; quyền 403 và đăng xuất; mất phản hồi sau commit rồi reload/gửi lại chỉ có 1 attempt, cùng khóa idempotency; trang công khai/đăng nhập/đăng ký responsive và lỗi trường email. Kiểm desktop 1440px, mobile 390px, tablet 768px; không tràn ngang ở các màn hình đã chụp. Có kiểm mở disclosure bằng bàn phím và font tiếng Việt đã nạp. Log: `browser-after.log`; chi tiết: `browser-assertions.json`, `browser-idempotency.json`.

Typecheck và ESLint kết thúc mã **0** (`frontend-checks.json`); production build thành công và image mới đã được áp dụng lên FE local. Detector thiết kế chạy một lần, không có finding (`design-detector.json`). Các kết quả này không thay thế kiểm toán bảo mật hay chuyên môn y khoa.

Review độc lập [finish-review.md](finish-review.md) yêu cầu sửa tên nguồn kỹ thuật ở kết quả, dấu đóng/mở nguồn, font tiêu đề và hoàn tất tài liệu. Đã sửa theo một đợt, chụp lại toàn bộ ảnh và chạy lại ba kiểm thử trên. [Verdict sau sửa](finish-verdict.md): **ship**, cả bốn mục được chấm là resolved; đây là verdict trên danh sách sửa, không phải chứng nhận toàn bộ hệ thống. `DESIGN.md`, sidecar, `PRODUCT.md` và hướng dẫn component đã hoàn tất, được kiểm tra YAML/JSON và tiếng Việt sau khi sửa lỗi mã hóa tài liệu; kết quả tại `design-doc-checks.json`.

Lệnh chạy lại từ repo:

```powershell
python -m local_model_testing.ui_completion.checks
python -m local_model_testing.ui_completion.browser
python -m local_model_testing.ui_completion.verify
```

Runner browser tạo lại **chỉ** DB có tên cố định `medresident_test_ui_completion_20261116`, sao chép dữ liệu chính vào đó và thêm fixture tổng hợp. Provider mock, model calls false, authoring off. Không nạp model, không cập nhật mastery thật. Sau chạy, API/browser kiểm thử được dừng.

Ảnh trước/sau cùng viewport 1440×1000 và 390×1000: `data/authoring/ui-completion-20261116/before-*.png`, `after-*.png`. Ảnh kết quả, biên soạn, đăng nhập/đăng ký và tablet 768px bổ sung cùng thư mục; đã xem ảnh và xử lý các lỗi thấy được. Contact sheet `gallery-before-1..2.png`, `gallery-after-1..7.png` giúp so sánh nhanh. Ảnh sau dùng dữ liệu sao chép và fixture tổng hợp trong DB test, không cấy dữ liệu demo mới vào DB chính. Không thay ảnh lịch sử từ các đợt chạy model trước.

Đối chiếu dữ liệu ở `data-preservation.json`: tất cả hàng của 13 bảng chính giữ nguyên hash, gồm câu hỏi, rubric, evidence mapping, người dùng, attempt, ghi nhận đọc và tự ôn. Vẫn **102 câu / 100 khả dụng / 2 nháp**. File ngân hàng đợt trước và các artifact đã khóa giữ nguyên. Cấu hình chính: practice mock, model calls false, authoring off. Không ghi Neo4j, không OCR, tải/nạp/train model hay gọi dịch vụ model trả phí.

## Tài liệu và quay lại thay đổi

Audit ở [ux-audit.md](ux-audit.md), hợp đồng bố cục ở [surface-direction.md](surface-direction.md), hệ thống thiết kế ở [design-system.md](design-system.md) và `DESIGN.md`; [mục ảnh trước/sau](screenshots.md).

Trước khi sửa đã lưu `code-before.zip`, `code-before-hashes.json` và `git-status-before.txt` trong thư mục bằng chứng. Để quay lại, giải nén ZIP sang thư mục tạm, so sánh và phục hồi **từng file code liên quan** với bản đang có; các component/route mới có thể bỏ sau khi gỡ import tương ứng. Không dùng `git reset --hard`/`git restore .`: repo có nhiều thay đổi sẵn từ các công việc trước. Không phục hồi DB hay thay file dữ liệu để quay lại giao diện. Sau phục hồi code, rebuild FE và restart BE local.

Không commit/push. Giữ FE/BE/PostgreSQL và Neo4j của người dùng để mở web; chỉ dừng worker kiểm thử tạo trong đợt này.
