# Gọi model trên RunPod từ MedResident-Tutor

Backend local giữ PostgreSQL, Neo4j, gói chấm và kiểm tra quyền. RunPod phục vụ inference. Không cần chuyển database hoặc toàn bộ sách lên Pod để chấm câu có approved_package; request Medical vẫn chứa đúng evidence của revision.

## File cấu hình thực tế

Mở `.env` tại gốc `C:\WORKS\STUDY\MedResident-Tutor`. Docker Compose đọc file này qua `env_file: .env`; `.env.example` chỉ là mẫu. Không thêm file .env thứ hai cho luồng web.

Đã chuẩn bị sẵn các biến dưới đây trong cả hai file. Giá trị `<...>` là placeholder, không phải key thật; backend từ chối gọi khi còn placeholder. Không lấy key từ `LLM_API_KEY`, `OPENAI_API_KEY` hoặc `KG_LLM_API_KEY` để fallback. Cấu hình LLM cũ của pipeline được giữ riêng.

```dotenv
# Chỉ bật sau khi điền xong URL/key và model đã sẵn sàng.
MODEL_CALLS_ENABLED=false
PRACTICE_PROVIDER=mock
AUTHORING_PROVIDER=off
PRACTICE_TIMEOUT_SECONDS=90

MEDICAL_API_FORMAT=openai
MEDICAL_SERVICE_URL=https://<MEDICAL_POD_ID>-8000.proxy.runpod.net/v1
MEDICAL_SERVICE_API_KEY=<DIEN_KEY_MEDICAL_RUNPOD>
MEDICAL_MODEL=medical-v1

TEACHING_API_FORMAT=openai
TEACHING_SERVICE_URL=https://<TEACHING_POD_ID>-8000.proxy.runpod.net/v1
TEACHING_SERVICE_API_KEY=<DIEN_KEY_TEACHING_RUNPOD>
TEACHING_MODEL=teaching-v1

AUTHORING_SERVICE_URL=https://<AUTHORING_POD_ID>-8000.proxy.runpod.net/v1
AUTHORING_SERVICE_API_KEY=<DIEN_KEY_AUTHORING_RUNPOD>
AUTHORING_MODEL=Qwen/Qwen3-4B-Instruct-2507
```

| Tác vụ | Model cần được phục vụ trên server | Dữ liệu gửi |
|---|---|---|
| Medical | Qwen3-4B-Instruct-2507 cùng Medical adapter V1 đã chọn | Câu hỏi, câu trả lời, rubric, evidence |
| Teaching | Qwen2.5-7B-Instruct cùng Teaching adapter V1 đã chọn | MedicalEvaluation, ngữ cảnh và learner_context |
| Authoring (tùy chọn) | Base Qwen3-4B-Instruct-2507, prompt authoring riêng | Câu hỏi/phạm vi và các đoạn nguồn admin chọn |

`medical-v1` và `teaching-v1` là **tên model/alias gợi ý**, phải trùng tên server thực sự phục vụ. Điền tên alias không tự tải hoặc gắn adapter. Phải triển khai đúng base/adapter trên RunPod trước. Nếu server chỉ có model base thì chưa phải Medical/Teaching V1 đã fine-tune. Không dùng model gắn Medical adapter làm mặc định cho soạn đáp án.

Ba URL có thể thuộc các Pod khác nhau. Nếu server hỗ trợ đồng thời base và LoRA alias, authoring có thể dùng cùng URL Medical với model base riêng; cần xác nhận cấu hình server, không tự fallback.

## Hai kiểu API được hỗ trợ

### API tương thích OpenAI (mặc định cho RunPod/vLLM)

`MEDICAL_API_FORMAT=openai`, `TEACHING_API_FORMAT=openai`, `AUTHORING_PROVIDER=openai`.

Backend gửi Bearer token, `model`, `messages`, `max_tokens`, `temperature=0`, `stream=false` vào endpoint chat completions. Không dùng OpenAI SDK hoặc gọi dịch vụ OpenAI.

- Pod: `https://POD_ID-8000.proxy.runpod.net/v1`.
- RunPod Serverless **vLLM OpenAI-compatible**: `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1`.
- Helper giữ nguyên prefix và nối `/chat/completions`, không tạo `/v1/v1`. Có thể nhận URL gốc chưa có `/v1` hoặc URL đã đủ `/chat/completions`.
- Pod vLLM: key là key inference bạn cấu hình cho server, ví dụ bằng tham số `--api-key` của vLLM. Serverless vLLM: dùng key được RunPod cho phép gọi endpoint. Không mặc định hai loại key là một.
- Endpoint Serverless tùy biến `/run` hoặc `/runsync` với envelope `input`/job ID chưa được hỗ trợ; không điền URL đó vào ô chat base URL.

Tài liệu chính thức: [RunPod HTTP proxy](https://docs.runpod.io/pods/configuration/expose-ports), [RunPod Serverless vLLM OpenAI compatibility](https://docs.runpod.io/serverless/vllm/openai-compatibility), [vLLM serving](https://docs.vllm.ai/en/latest/serving/openai_compatible_server/).

### API riêng có contract dự án

Nếu bạn chạy một service tương thích contract hiện có trên Pod:

- Đặt `MEDICAL_API_FORMAT=service`, `TEACHING_API_FORMAT=service`.
- URL là origin của service, không có `/v1` hoặc `/medical/evaluate` ở cuối.
- Backend nối `/medical/evaluate` và `/teaching/evaluate`, gửi `X-API-Key`.
- Medical response có `medical_evaluation`, Teaching response có `teaching_feedback`; có thể kèm `model_metadata` và `timing` như provider cũ.
- `AUTHORING_PROVIDER=service_http` hỗ trợ service HTTPS riêng với `/authoring/propose`, header `X-API-Key`, body authoring-v1 và response Proposal. Server phải triển khai endpoint/auth này; worker local trong repo chỉ là worker local, không mặc định là service công khai đã được bảo vệ.
- `AUTHORING_PROVIDER=local_http` tiếp tục dùng worker local và địa chỉ localhost/host.docker.internal; không dùng mode này cho URL RunPod.

## Bật và áp dụng sau khi điền

Để chấm thật bằng hai model:

```dotenv
MODEL_CALLS_ENABLED=true
PRACTICE_PROVIDER=http
```

Để soạn đáp án bằng base model từ xa, bật thêm:

```dotenv
AUTHORING_PROVIDER=openai
```

Có thể bật soạn thảo nhưng vẫn giữ `PRACTICE_PROVIDER=mock` để chưa gọi hai model chấm. Ngược lại, có thể bật chấm nhưng giữ `AUTHORING_PROVIDER=off` và soạn câu hỏi thủ công.

Chạy kiểm tra cấu hình không gọi mạng, không in key:

```powershell
python -m local_model_testing.runpod_config
```

Lệnh báo đúng file .env, URL/model, key đã điền hay chưa và tên biến nào đang có trong môi trường terminal. Không gửi request tới RunPod, kể cả `/models` hoặc `/health`.

Sau khi thay .env, **tạo lại container backend** để nhận biến mới; `docker restart` giữ môi trường cũ:

```powershell
Set-Alias docker 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
docker compose -f docker-compose.yml -f docker-compose.authoring.yml up -d --build --force-recreate backend
```

Sau lần build mã mới, những lần chỉ đổi .env có thể thay `--build` bằng `--no-build`. Không cần dừng DB/Neo4j. Frontend không nhận API key.

Thứ tự ưu tiên cần lưu ý: biến môi trường terminal ảnh hưởng nội suy Compose trước `.env`; khối `environment` trong Compose ghi đè `env_file`; biến tiến trình backend ghi đè dotenv Pydantic. Đã bỏ hai giá trị cố định gây chặn cấu hình (`MODEL_CALLS_ENABLED=false`, URL authoring local). Dùng lệnh audit để phát hiện terminal override; không dùng `docker compose config` in toàn bộ ra terminal vì có thể lộ secrets.

## Điều phối, validation và thời gian

Medical → kiểm contract → lưu kết quả → Teaching → guards giữ nguyên. Prompt Medical/Teaching V1 được import từ nguồn đã khóa; không sửa adapter, benchmark hoặc expected. Medical vẫn nhận evidence; authoring là tác vụ riêng. API chat khác backend inference cũ về serving/tokenizer/quantization có thể cho kết quả khác; chưa khẳng định tương đương số đo benchmark local.

Mỗi request chỉ gửi một lần: không tự retry, không fallback sang mock/model khác, không tự sửa JSON. Response cắt vì max token bị từ chối với `MODEL_OUTPUT_TRUNCATED`. HTTP 401/403/500/524 giữ mã trong `REMOTE_HTTP_*`; 429 thành `PROVIDER_BUSY`. Không chuyển nguyên thông báo upstream có thể chứa key về frontend/log. Metadata lưu model yêu cầu/model server báo và usage, không lưu credential.

`PRACTICE_TIMEOUT_SECONDS=90` áp dụng từng stage ở profile mặc định. `/practice/config` trả timeout đủ cho cả hai stage để trình duyệt không bỏ cuộc sau mặc định 45 giây. Mode local hiện có vẫn giữ profile timeout riêng. Authoring dùng read timeout không giới hạn ở backend, connect timeout 5 giây; trình duyệt chờ tối đa 15 phút như luồng authoring hiện có.

Giới hạn hạ tầng không bị xóa bằng timeout của client: RunPod ghi HTTP proxy Pod có giới hạn 100 giây và có thể trả 524. Không tự gọi lại khi gặp 524, vì generation trên server có thể vẫn đang chạy. Nếu model thường cần lâu hơn, cần chọn đường kết nối/job API phù hợp rồi bổ sung transport đó; bản này chưa triển khai job polling hoặc stream keepalive. Không thể hứa request đi qua proxy sẽ chờ vô hạn.

## Tắt

```dotenv
MODEL_CALLS_ENABLED=false
PRACTICE_PROVIDER=mock
AUTHORING_PROVIDER=off
```

Tạo lại backend bằng Compose. Đây là tắt gọi từ web; không tự dừng/terminate Pod và không bảo đảm dừng khoản phí giữ Pod/GPU đang bật trên tài khoản RunPod.

## Kiểm chứng của đợt chuẩn bị

Kiểm thử chỉ dùng httpx.MockTransport, fixture và validator hiện có. Không nạp GPU, không gửi request thật đến RunPod, không có inference mới. Check URL có/không `/v1`, prefix Serverless, placeholder/key riêng, prompt/evidence Medical, Teaching, authoring schema/source IDs, JSON sai/cắt ngắn, lỗi HTTP/429 và công tắc tắt. Báo cáo: `data/authoring/runpod-config-20261112/`.

Chạy lại test offline: `python -m local_model_testing.runpod_checks`. Việc kết nối live và chất lượng model phải kiểm tra sau khi bạn cung cấp cấu hình endpoint thật; không lấy test mock làm bằng chứng đã gọi thành công trên RunPod.
