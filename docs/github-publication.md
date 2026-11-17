# Nội dung đưa lên GitHub

Repository lưu source code frontend/backend, migration, pipeline KG, công cụ biên soạn/kiểm thử, cấu hình mẫu và tài liệu thiết kế/triển khai. Các đường dẫn nguồn và manifest nhỏ được giữ để đối chiếu phiên bản; chúng không chứa trọng số model hay bản sao database.

Các thành phần sau vẫn nằm trên máy local và không được đưa vào commit:

- `.env`, API key, mật khẩu, thông tin đăng nhập demo và bản sao database.
- Model base, embedding weights, adapter LoRA, môi trường Python và cache.
- Sách PDF/OCR, tài liệu giảng viên trong `data/new_data`, tài sản/ca bệnh được tải về.
- Kết quả extraction, snapshot/exports Neo4j, chỉ mục retrieval, gói authoring và artifact benchmark.
- Thư mục tham khảo dự án khác `advance`, công cụ/session thiết kế local và screenshot kiểm thử.

Clone repository sẽ không tự tái tạo ngân hàng câu hỏi, tiến độ học hoặc nội dung Neo4j đang có trên máy này. Để chạy với bộ dữ liệu hiện tại trên máy khác, cần sao lưu/khôi phục PostgreSQL và Neo4j riêng, chuyển các file nguồn/tài sản được phép sử dụng, rồi tạo `.env` từ `.env.example`. Không công khai các bản sao này trong Git. Không chạy đồng thời các script import hoặc seed khi chỉ muốn khôi phục giao diện.

Để phục vụ model trên RunPod, tải riêng hai thư mục adapter và dùng đúng model base; hướng dẫn tại [runpod-model-api.md](runpod-model-api.md). Không cần tải dữ liệu người học hoặc database lên Pod để gọi inference theo luồng hiện có.

Một số báo cáo thiết kế/nghiên cứu dẫn tới artifact local đã bị Git ignore. Đây là liên kết bằng chứng của đợt chạy trên máy phát triển, không phải file được đóng gói cùng repository. Source code và các test/fixture tổng hợp được giữ để kiểm tra độc lập; không coi fixture là dữ liệu học thật.
