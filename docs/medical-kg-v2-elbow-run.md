# Chạy chương Trật khớp khuỷu — 2006

Phạm vi PDF 93–97, dùng OCR có sẵn trong `data/graduate`, 9 cửa sổ / 3 nhóm.
Chương tiếp theo (Trật khớp háng) bắt đầu ở PDF 98 theo OCR.

Chạy từ PowerShell sau khi bật WireGuard:

```powershell
Set-Location 'C:\WORKS\STUDY\MedResident-Tutor'
& "$env:TEMP\medresident-draft-venv\Scripts\python.exe" -m knowledge_pipeline.kg_v2 batch `
  --scope knowledge_pipeline/kg_v2/chapter-elbow-2006-plan.json `
  --output data/knowledge-extraction/v2/chapter-elbow-2006-wait `
  --max-calls 18 `
  --no-response-timeout `
  --connect-timeout 30
```

`--no-response-timeout` tắt timeout đọc phản hồi, gửi dữ liệu và chờ connection pool;
đồng thời bỏ giới hạn tổng thời gian chờ của batch và từng nhóm.
Trong chế độ này, `--timeout` và `--total-seconds` không áp dụng.
Chỉ thiết lập kết nối bị giới hạn 30 giây. HTTPX dùng
`httpx.Timeout(None, connect=30)`; xem [tài liệu HTTPX](https://www.python-httpx.org/advanced/timeouts/).
Server/proxy vẫn có thể đóng kết nối hoặc trả HTTP lỗi; code giữ nguyên chẩn đoán.

Giới hạn 18 request vẫn áp dụng, tối đa 2 lần thử mỗi cửa sổ khi gặp lỗi transport
hoặc HTTP tạm thời. Không có retry HTTP ẩn. Không giới hạn thời gian không bảo đảm
chất lượng tối đa: giới hạn output token và kiểm tra nguồn/schema vẫn giữ nguyên.
OCR chương này còn lỗi thuật ngữ và hai ngưỡng Reagan trùng nhau, cần duyệt nguồn.

Lệnh đọc `.env` gốc trực tiếp, không in key, không chạy OCR mới, không ghi Neo4j.
Kết quả gồm bản nháp node/cạnh, JSON và trang review; mở `report.md` trong thư mục
output để tìm bản tổng hợp mới nhất.

Nếu bị gián đoạn, thêm `--resume` với cùng thư mục và các cấu hình sinh kết quả.
Dùng thư mục output mới cho lần chạy đầu với code/chính sách timeout mới:
checkpoint của code trước đó không tương thích và không được tự động ghi đè.
`Ctrl+C` dừng request đang chờ; các cửa sổ đã lưu vẫn được giữ lại.
