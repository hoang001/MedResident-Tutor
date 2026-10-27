# Bộ đọc và trích xuất tài liệu dùng lại

Copy nguyên thư mục `document_toolkit` vào thư mục gốc của dự án mới. Bộ này không phụ thuộc `src/`, SGV/SGK/SBT, mapping IXL hay Neo4j. Prompt và JSON Schema do công việc mới cung cấp.

## Những phần đã gom

| File | Công dụng |
| --- | --- |
| `documents.py` | Đọc PDF có lớp chữ, JSON/JSONL; chia đoạn theo dung lượng UTF-8; giữ file nguồn và số trang. Có callback để nối OCR riêng. |
| `llm_client.py` | Gọi API chat tương thích OpenAI; đọc JSON, kiểm tra schema, retry khi mất kết nối hoặc JSON lỗi. |
| `checkpoint.py` | Lưu từng lần gọi thành công; chạy tiếp không gọi lại phần đã lưu. |
| `pipeline.py` | Nối đọc → chia đoạn → trích xuất → đối chiếu tùy chọn → xuất JSON; ghi trạng thái hoàn tất hoặc còn thiếu. |
| `common.py`, `config.py` | Đọc/ghi JSON UTF-8, ghi checkpoint an toàn, cấu hình độc lập. |
| `__main__.py` | Lệnh terminal cho đọc và trích xuất. |

Không kèm prompt chuyên biệt, dữ liệu sách, model, thông tin đăng nhập hay kết quả cũ.

## Cài đặt

Chạy tại thư mục gốc dự án mới, nơi chứa `document_toolkit`:

```powershell
python -m pip install -r document_toolkit/requirements.txt
```

Nếu cần LLM, copy `document_toolkit/.env.example` thành `.env` của dự án mới rồi điền URL, key và model của bạn. Không copy `.env` của dự án cũ. Biến môi trường terminal có ưu tiên cao hơn file `.env`.

## Chỉ đọc tài liệu, không gọi LLM

```powershell
python -m document_toolkit read --input "data/book.pdf" --output "outputs/book_text.json"
```

Đầu vào cũng nhận `.json`/`.jsonl`: mỗi bản ghi có `text`, có thể thêm `page_start`, `page_end` và metadata tùy ý. JSON nhận một bản ghi, danh sách bản ghi hoặc object chứa `sections`.

Kết quả gồm `sections` với nội dung, file nguồn, số trang bắt đầu/kết thúc, cách đọc, mã đoạn. Trang PDF không có chữ được ghi trong `unreadable_pages`, không tự tạo nội dung thay thế. Số trang là vị trí thực tế trong PDF, bắt đầu từ 1, có thể khác số in trên sách.

## Trích xuất bằng prompt của công việc mới

Tự chuẩn bị file prompt dạng văn bản và JSON Schema cho dữ liệu cần lấy:

```powershell
python -m document_toolkit extract --input "data/book.pdf" --output "outputs/extracted.json" --prompt "prompts/extract.txt" --schema "schemas/extracted.json" --env-file ".env"
```

Có thể dùng `outputs/book_text.json` làm đầu vào để tái sử dụng phần đã đọc. Mỗi lần gọi nhận một đoạn nguồn và metadata; đầu ra LLM phải khớp schema của bạn.

Thêm `--judge-prompt "prompts/review.txt"` nếu cần LLM kiểm tra lại kết quả trên cùng đoạn nguồn. Dùng `--judge-schema "schemas/reviewed.json"` nếu schema sau kiểm tra khác schema trích xuất. Đây là bước kiểm tra tùy chọn, không bảo đảm nội dung chính xác tuyệt đối.

Lệnh chạy trực tiếp và chỉ kết thúc sau khi xong hoặc gặp lỗi, không tạo worker chạy ngầm. File kết quả có `status`, `completed_chunks`, `total_chunks`, `unreadable_pages`, `failures` và `results`; mỗi kết quả đi cùng nguồn của đoạn đó. Đếm ở đây là **đoạn văn bản**, không phải số bài học.

## Chạy tiếp sau khi bị ngắt

Giữ nguyên lệnh và thêm `--continue`:

```powershell
python -m document_toolkit extract --input "data/book.pdf" --output "outputs/extracted.json" --prompt "prompts/extract.txt" --schema "schemas/extracted.json" --continue
```

Checkpoint nằm cạnh kết quả: `outputs/extracted.checkpoint.json`. Lượt gọi hoàn tất được lưu ngay; lượt đang gọi khi ngắt có thể phải gọi lại. Dữ liệu không vượt schema hoặc validator không được đánh dấu hoàn tất. Nếu ngắt bằng Ctrl+C thông thường, bộ này ghi kết quả một phần trước khi thoát; nếu tắt tiến trình đột ngột, checkpoint vẫn chứa các lượt đã lưu.

Thêm `--force` để bỏ checkpoint cũ và chạy lại. Thay tài liệu, prompt, schema hoặc code xử lý thì dùng output khác hoặc `--force`, không tiếp tục kết quả cũ. Không dùng đồng thời `--continue` và `--force`.

Điều chỉnh `--chunk-bytes 6000` để đổi kích thước đoạn. Giới hạn này tính bằng byte UTF-8, không phải token. `LLM_PROMPT_BUDGET_BYTES` giới hạn tổng prompt; `LLM_MAX_OUTPUT_TOKENS` giới hạn câu trả lời. Bộ chia đoạn hiện giữ theo từng trang/section, chưa nhận biết ranh giới bài hay mục qua nhiều trang.

## PDF ảnh và OCR

Bộ này **chưa kèm engine OCR**. Với PDF scan, nối engine bạn chọn bằng Python:

```python
from document_toolkit import read_document

def my_ocr(pdf_path, page_number):
    # Gọi bộ OCR của công việc mới, trả về chữ của trang này.
    # page_number bắt đầu từ 1.
    return your_ocr_engine(pdf_path, page_number)

document = read_document("data/scan.pdf", ocr_page=my_ocr)
```

Mặc định chỉ gọi callback khi trang không đọc được chữ. Đặt `force_ocr=True` để OCR toàn bộ trang nếu lớp chữ PDF bị hỏng. Khi dùng callback qua `extract_document`, truyền thêm `ocr_version` để checkpoint nhận biết phiên bản OCR.

## Dùng trong code

```python
from document_toolkit import Settings, extract_document
from document_toolkit.common import read_json
from pathlib import Path

result = extract_document(
    "data/book.pdf",
    "outputs/extracted.json",
    settings=Settings.from_env(".env"),
    prompt=Path("prompts/extract.txt").read_text(encoding="utf-8"),
    schema=read_json("schemas/extracted.json"),
)
```

Để kiểm tra quy tắc riêng như trích dẫn đúng nguyên văn, khoảng số hoặc quan hệ giữa các trường, truyền `validator(result, chunk)` và `validator_version="v1"`. Validator phải ném `ValueError` khi dữ liệu không hợp lệ; đổi version khi đổi quy tắc. JSON Schema chỉ kiểm tra cấu trúc, không thay thế kiểm tra nội dung này.

## Kiểm tra bộ tiện ích

```powershell
python -m unittest document_toolkit.test_toolkit
```

Các kiểm tra dùng client giả lập, không gọi LLM/API thật.
