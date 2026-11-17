# Deploy Medical + Teaching qua GitHub

Luồng chính thức: **PC local → implement/test → commit/push GitHub → người vận
hành chạy bootstrap/pull trên Pod → restart model service → gửi log nếu lỗi**.
Repository GitHub là source of truth. Tất cả thay đổi ở đây là code/scripts/docs
trong repo; task này không truy cập hoặc sửa trực tiếp Pod.

## Kiến trúc và trạng thái

Một FastAPI app, một worker và port **8000**:

```text
GET  /health
GET  /ready
POST /medical/evaluate
POST /teaching/feedback
```

Backend PC điều phối retrieval/approved package → Medical → Teaching → lưu DB.
Frontend chỉ gọi backend và không nhận model-service key. Provider `runpod` không
fallback sang mock; mock vẫn dùng tường minh cho development hiện tại.

Medical endpoint đã có lần kiểm chứng live HTTP 200 trước task này. Teaching đã
được người vận hành kiểm tra riêng; endpoint ghép chung trong bản code này được
kiểm chứng bằng fake runners, chưa được xác nhận live sau deployment. Không có
probe/inference trực tiếp tới Pod trong task triển khai GitHub này.

Teaching import nguyên prompt V1, MAX_NEW_TOKENS, schema và deterministic guards
hiện có. Medical/Teaching đều NF4 4-bit, float16, LoRA V1, local-only và offline.
Không download Hugging Face khi startup. Sau generation Teaching: strict JSON →
schema check → guards → final validation. Không trả raw generation khi lỗi, không
đánh giá lại Medical hoặc xuất điểm Teaching. Sáu field nằm trong `teaching_feedback`
của envelope có metadata/timing, tương thích client backend.

`/ready` trả 200 chỉ khi cả hai model load thành công; lúc đang load hoặc một
model load lỗi trả 503. Một khóa GPU chung giữ tới khi generate kết thúc, kể cả
khi HTTP request bị hủy. Inference không tự retry.

## Bootstrap đã inspect

Bản `/workspace/bootstrap.sh` được lưu trong file local `run.md` clone/pull repo
vào `/root/MedResident-Tutor`, dùng main và fast-forward, cài packages và tạo
directories. Bản snippet đó không khởi động inference. File thực tế trên Pod
không được đọc trực tiếp trong task này.

Script được theo dõi trong Git: **`scripts/runpod/bootstrap.sh`**. Nó clone hoặc
fetch/merge fast-forward đúng repo/branch, từ chối origin/branch khác hoặc tracked
changes chưa lưu, rồi `python -m pip install -e services/medical`. Không reset
hard, khởi động GPU hoặc tải weights/adapters. Bootstrap không phụ thuộc model
đã load hay `/ready` thành công.

## Env và artifact trên Pod

Chỉ cần key service đã có trong environment để chạy với các path mặc định:

| Biến | Mặc định / ý nghĩa |
|---|---|
| `MODEL_SERVICE_API_KEY` | Key chung đúng với backend PC; ưu tiên hơn MEDICAL_API_KEY |
| `MEDICAL_API_KEY` | Dùng khi MODEL key chưa đặt/rỗng; không bypass MODEL placeholder |
| `MEDICAL_BASE_MODEL_PATH` | `/workspace/models/qwen3-4b-instruct-2507` |
| `MEDICAL_ADAPTER_PATH` | `/workspace/adapters/medical-v1` |
| `TEACHING_BASE_MODEL_PATH` | `/workspace/models/qwen2.5-7b-instruct` |
| `TEACHING_ADAPTER_PATH` | `/workspace/adapters/teaching-v1` |
| `MEDICAL_ADAPTER_SHA256` | Tùy chọn pin hash Medical adapter weights |
| `MEDICAL_BASE_CONFIG_SHA256` | Tùy chọn pin Medical base config |
| `MEDICAL_ADAPTER_CONFIG_SHA256` | Tùy chọn pin Medical adapter config |
| `TEACHING_ADAPTER_SHA256` | Tùy chọn pin Teaching adapter weights |
| `TEACHING_BASE_CONFIG_SHA256` | Tùy chọn pin Teaching base config |
| `TEACHING_ADAPTER_CONFIG_SHA256` | Tùy chọn pin Teaching adapter config |

Startup tự tính hash còn thiếu/rỗng; hash được cung cấp luôn được verify và sai
hoặc placeholder thì dừng. Cấu hình model identity/LoRA cũng được kiểm tra. Hash
tự tính là fingerprint của file hiện có, không tự chứng minh đó là artifact V1
đã khóa; có thể pin expected hashes từ manifest đã xác nhận để kiểm tra provenance.
Không hard-code hashes hoặc secret trong source. Weights/adapters không vào Git.

Không bắt buộc tạo file env khác. Nếu muốn lưu cấu hình persistent, dùng mẫu
`services/medical/runpod.env.example` tại `/workspace/secrets/medresident-serving.env`.
**Biến đã export hoặc truyền trước lệnh ưu tiên hơn file**; không để key/file cũ
ghi đè key vừa nhập. `MODEL_SERVICE_ENV_FILE` chọn file khác; file được chỉ định
nhưng không tồn tại thì startup báo lỗi.

Các biến tùy chọn: `MODEL_SERVICE_PYTHON` chọn venv Python;
`MODEL_SERVICE_LOG_FILE` đổi log mặc định;
`MODEL_SERVICE_STOP_TIMEOUT_SECONDS` đặt thời gian dừng mềm (mặc định 60s).

## Chính xác các lệnh chạy trên Pod

Sau khi commit đã được push, dùng terminal RunPod của bạn. Ba dòng dưới dùng
bootstrap persistent hiện có rồi bootstrap từ Git để đồng bộ và cài HTTP service:

```bash
nvidia-smi && bash /workspace/bootstrap.sh
cd /root/MedResident-Tutor && bash scripts/runpod/bootstrap.sh
set +x && cd /root/MedResident-Tutor && read -rsp 'MODEL_SERVICE_API_KEY: ' MODEL_SERVICE_API_KEY && printf '\n' && export MODEL_SERVICE_API_KEY && bash scripts/runpod/start_model_service.sh
```

Dòng cuối hỏi key bằng input ẩn, không in/ghi giá trị vào command history. Nhập
đúng key đang dùng trong `.env` backend PC. Nếu key đã export, dòng cuối có thể là:

```bash
cd /root/MedResident-Tutor && bash scripts/runpod/start_model_service.sh
```

Script chạy foreground; giữ terminal đó chạy hoặc dùng nó làm startup command
của bạn. Nó đặt PYTHONPATH/offline flags, paths, tính/verify SHA-256, kiểm tra key
và cả hai bộ artifact **trước khi dừng service cũ**. Chỉ gửi SIGTERM cho đúng một
Uvicorn process cùng chủ sở hữu đang nghe port 8000 với entrypoint Medical service.
Không dừng process không rõ danh tính, PID 1 hoặc process khác; không force-kill.
Chờ process cũ thoát rồi exec một Uvicorn worker tại `0.0.0.0:8000`.

Không tạo port 8001 hoặc container model thứ hai. Preflight lỗi sẽ giữ service cũ
và thoát mã 1. Nếu PID 1 đang là listener, script báo từ chối; cần restart bằng cơ
chế Pod của bạn thay vì kill PID 1. Nếu old process không thoát trong timeout,
script dừng và không nạp thêm GPU worker.

Log persistent: **`/workspace/outputs/model-service.log`**, ghi nối và hiển thị
terminal; không key, full request payload hay raw model output. Kiểm tra CPU-only:

```bash
cd /root/MedResident-Tutor && bash scripts/runpod/start_model_service.sh --check-only
cd /root/MedResident-Tutor && bash scripts/runpod/start_model_service.sh --print-hashes
```

## Chính xác các lệnh health/ready và curl inference

Mở terminal thứ hai trong Pod khi service đã khởi động:

```bash
curl -sS -i http://127.0.0.1:8000/health
curl -sS -i http://127.0.0.1:8000/ready
```

Chỉ tiếp tục khi `/ready` là **HTTP 200**. Trong terminal thử này, nạp key bằng
input ẩn; không dùng `-v`, trace hoặc echo key:

```bash
set +x && cd /root/MedResident-Tutor && read -rsp 'MODEL_SERVICE_API_KEY: ' MODEL_SERVICE_API_KEY && printf '\n' && export MODEL_SERVICE_API_KEY
```

Medical, đúng một request tổng hợp, không locked dataset:

```bash
mkdir -p /workspace/outputs/model-service-probe && printf 'X-API-Key: %s\n' "$MODEL_SERVICE_API_KEY" | curl -sS --fail-with-body --connect-timeout 10 --max-time 145 -H @- -H 'Content-Type: application/json' --data-binary @services/medical/examples/medical-request.json -o /workspace/outputs/model-service-probe/medical.json -w 'Medical HTTP %{http_code}; total %{time_total}s\n' http://127.0.0.1:8000/medical/evaluate
```

Teaching: chỉ chạy sau Medical HTTP 200. Builder giữ nguyên MedicalEvaluation vừa
nhận; Teaching không nhận evidence/rubric và không tạo điểm:

```bash
python services/medical/examples/build_teaching_request.py services/medical/examples/medical-request.json /workspace/outputs/model-service-probe/medical.json /workspace/outputs/model-service-probe/teaching-request.json && printf 'X-API-Key: %s\n' "$MODEL_SERVICE_API_KEY" | curl -sS --fail-with-body --connect-timeout 10 --max-time 145 -H @- -H 'Content-Type: application/json' --data-binary @/workspace/outputs/model-service-probe/teaching-request.json -o /workspace/outputs/model-service-probe/teaching.json -w 'Teaching HTTP %{http_code}; total %{time_total}s\n' http://127.0.0.1:8000/teaching/feedback
```

Headers được truyền qua stdin, không đưa key vào argv. Curl không tự retry.
Kết quả JSON nằm trong `/workspace/outputs/model-service-probe/`.

Nếu lỗi, gửi HTTP status/error code và log sau (không gửi file secret/env):

```bash
tail -n 100 /workspace/outputs/model-service.log
```

## Backend PC sau deployment

`.env` gốc trên PC giữ `RUNPOD_POD_ID=<ID hiện tại>`, `MODEL_SERVICE_BASE_URL=`
và key chung. Chỉ sau hai endpoint đã được kiểm tra mới chủ động bật
`PRACTICE_PROVIDER=runpod`, `MODEL_CALLS_ENABLED=true`, rồi recreate backend.
Task này giữ nguyên mock/model calls false của web local.

## Kiểm thử và phạm vi thay đổi

- Service regression: 92 passed, gồm fake model/readiness, shared GPU lock và
  cancellation, raw-output guards, auto/pinned hashes, key precedence, restart
  decisions không gửi signal thật, bootstrap Git/pip giả không mạng/GPU.
- Backend regression: 135 passed. Tổng: **227 passed**.
- Không chạy locked Medical/Teaching evaluation sets, train, download/load model
  local hoặc sửa prompts/adapters. Code inference/validators V1 được import/reuse.
- Git diff và secret/large-artifact scan được kiểm tra trước commit/push; chỉ đưa
  code, tests, env mẫu và docs vào Git. Các report riêng nằm trong ignored data/authoring.

Các file chính: `scripts/runpod/{bootstrap,start_model_service}.sh`,
`services/medical/medical_service/{bootstrap,processes,app,config,main,unified,teaching}.py`,
startup/env example, tests service/backend, backend client/provider/settings và
các tài liệu liên quan. Commit/push status cụ thể được báo sau khi Git hoàn tất.
