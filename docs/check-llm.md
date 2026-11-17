# Kiểm tra kết nối LLM

File cấu hình dùng chung: `C:/WORKS/STUDY/MedResident-Tutor/.env` ở thư mục gốc. File `knowledge_pipeline/.env` đã được gộp và xóa.

```dotenv
LLM_BASE_URL=http://10.8.0.1:4000/v1
LLM_API_KEY=<TOI_SE_TU_DIEN>
LLM_MODEL=vtllm/gemma-4-26b
LLM_CHAT_ENDPOINT=/v1/chat/completions
```

Chỉ thay placeholder bằng key thật trên máy. Không commit file `.env`.

Lệnh test dùng `dotenv_values(interpolate=False)` để đọc file được chỉ định: không lấy cấu hình LLM từ terminal, không nội suy biến, không fallback sang OPENAI_API_KEY hoặc KG_LLM_API_KEY. Key trống hoặc placeholder bị chặn trước khi gọi HTTP.

Lệnh extraction cũng đọc trực tiếp file qua `Settings.from_env()`, mặc định dùng cùng `.env` gốc; biến terminal không ghi đè cấu hình LLM và không có fallback OPENAI_*. Không chạy extraction để thử kết nối. Docker Compose vẫn có quy tắc ưu tiên biến môi trường riêng cho các biến triển khai; bước này không thay đổi cấu hình database/backend.

## Chạy sau khi điền key và xác nhận muốn gọi API

Bật WireGuard, bảo đảm máy truy cập được `10.8.0.1:4000`.

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'
& "$env:TEMP\medresident-extraction-venv\Scripts\python.exe" -m knowledge_pipeline.connection --env-file 'C:/WORKS/STUDY/MedResident-Tutor/.env' --reply-ok --timeout 30
```

Một POST duy nhất yêu cầu trả đúng `OK`; không retry, không tự đi theo redirect và không dùng HTTP proxy từ terminal. URL cuối: `http://10.8.0.1:4000/v1/chat/completions`, không lặp `/v1/v1`.

Báo cáo JSON gồm đường dẫn file cấu hình, endpoint, model, HTTP status, nội dung phản hồi chat và thời gian giây. Khi HTTP lỗi, giữ status, error type và message của API; nội dung trùng key được che. Thông báo `no_db_connection` đến từ API, không chứng minh PostgreSQL local có lỗi. Không in Authorization header hoặc key.

Nếu PowerShell cho phép script, lệnh tương đương: `.\scripts\test_llm.ps1 -TimeoutSeconds 30`. Script dùng đúng file trên và cờ `--reply-ok`. Tùy chọn `-TcpOnly` chỉ kiểm tra socket, chưa xác nhận key/model.

Không chạy pipeline/OCR/extraction và không thay đổi database, VPN hoặc route trong bước test này.
