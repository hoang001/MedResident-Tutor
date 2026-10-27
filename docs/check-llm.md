# Kiểm tra kết nối LLM

Chạy PowerShell từ `C:\WORKS\STUDY\MedResident-Tutor`. Script đọc riêng
`knowledge_pipeline/.env`, không sửa env, không OCR/extract, không retry, không in key.
URL/model dùng `LLM_BASE_URL` (hoặc `OPENAI_BASE_URL`), `LLM_API_KEY` (hoặc
`OPENAI_API_KEY`), `LLM_MODEL`, `LLM_CHAT_ENDPOINT`.

PowerShell trên máy hiện tại chặn chạy `.ps1` (ExecutionPolicy). Không cần thay
chính sách; dùng Python trực tiếp từ thư mục repo:

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'
& "$env:TEMP\medresident-extraction-venv\Scripts\python.exe" -m knowledge_pipeline.connection --tcp-only --timeout 5
& "$env:TEMP\medresident-extraction-venv\Scripts\python.exe" -m knowledge_pipeline.connection --timeout 30
```

Hai lệnh dưới đây bằng `.ps1` chỉ dùng khi chính sách máy cho phép script.

```powershell
# Kiểm tra host/port, không gọi model:
.\scripts\test_llm.ps1 -TcpOnly

# Một lượt generation rất nhỏ (có thể tính phí API):
.\scripts\test_llm.ps1 -TimeoutSeconds 30

# Nạp thành hàm dùng lại trong terminal hiện tại:
. .\scripts\test_llm.ps1
Test-MedResidentLLM -TcpOnly
Test-MedResidentLLM -TimeoutSeconds 30
```

Script tìm Python ở `.venv-extraction`, tiếp đến venv extraction trong TEMP rồi
Python hệ thống. Chọn rõ runtime nếu cần bằng `-Python 'C:/path/to/python.exe'`.
Dependencies trong `document_toolkit/requirements.txt`. Hàm Python tái sử dụng:
`knowledge_pipeline.connection.check_llm(settings, tcp_only=False, timeout_seconds=15)`.

Lệnh mạng Windows cho endpoint nội bộ hiện tại:

```powershell
ping 10.8.0.1
Test-NetConnection 10.8.0.1 -Port 4000
```

Ping ICMP không kiểm chứng API/model, và có thể bị chặn dù TCP vẫn thông.
TCP_CONNECTED chỉ chứng minh mở được socket, chưa xác nhận auth, HTTP hay model.
MODEL_OK nghĩa là HTTP200 và câu trả lời JSON đúng cho probe nhỏ, chưa kiểm chứng
schema extraction hoặc chất lượng y khoa. Exit code 0 khi thành công, 1 khi thất bại.

Các mã lỗi chính: CONNECT_TIMEOUT (chưa kết nối), RESPONSE_TIMEOUT (chờ phản hồi
quá lâu), HTTP_ERROR (xem http_status: 401/403/503...), API_NO_DB_CONNECTION
(API báo thiếu kết nối DB), INVALID_JSON_OUTPUT/OUTPUT_TRUNCATED (HTTP200 nhưng
output probe không hợp lệ). Thông báo không đưa raw response hay key ra log.
