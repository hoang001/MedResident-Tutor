# Một RunPod service cho Medical và Teaching

Luồng deploy chính thức và các lệnh một dòng hiện tại:
[GitHub → bootstrap → model service](runpod-github-deploy.md).

## Luồng đã triển khai

```text
Frontend → FastAPI backend → evidence retrieval / approved package
                           → RunPod POST /medical/evaluate
                           → lưu MedicalEvaluation
                           → RunPod POST /teaching/feedback
                           → lưu TeachingFeedback → Frontend
```

Backend vẫn quản lý đăng nhập, quyền sở hữu, idempotency, snapshot nguồn và
PostgreSQL. Retrieval dùng cấu hình hiện có: `prelinked`, `vector`, `kg_lookup`
hoặc `hybrid`; câu có approved package dùng gói nguồn đã duyệt. Không phải mọi
câu đều truy vấn Neo4j trực tiếp. Service model không kết nối database/KG.
Frontend chỉ gọi backend; API key không được chuyển xuống trình duyệt.

Medical nhận đúng bốn trường `question`, `student_answer`, `rubric`, `evidence`.
Teaching nhận contract V1 hiện có: `schema_version`, `question`, `student_answer`,
`medical_evaluation`, `learner_context`, `metadata`. Evidence chỉ đi vào Medical.
Teaching giữ nguyên Medical làm anchor, không được tạo điểm hoặc sửa điểm.

Lịch sử Teaching được chụp vào snapshot lúc nộp bài: tối đa 5 lượt `http` đã
hoàn tất của đúng học viên, chỉ tóm tắt số ý đúng/sai/thiếu. Không dùng lượt mock,
lượt structured, thông tin người khác, câu trả lời cũ hoặc gold answer làm lịch sử.
Các mảng mastery/recurring_errors/recent_improvements vẫn rỗng khi chưa có dữ liệu
được xác nhận. Đây chưa phải bộ suy luận mức thành thạo cá nhân.

Medical đã lưu sẽ được giữ nếu Teaching lỗi. Reload/idempotent replay không gọi
model lại. Retry phải do người dùng yêu cầu; chỉ chạy bước còn thiếu, dùng snapshot
và lịch sử cũ. Không có retry inference tự động hay fallback sang mock.

## Backend local: một file `.env` gốc

Mở `C:\WORKS\STUDY\MedResident-Tutor\.env`:

```dotenv
RUNPOD_POD_ID=ID_POD_CUA_BAN
MODEL_SERVICE_BASE_URL=
MODEL_SERVICE_API_KEY=<KEY_GIONG_RUNPOD>
MODEL_SERVICE_CONNECT_TIMEOUT_SECONDS=10
MODEL_SERVICE_READ_TIMEOUT_SECONDS=120

# Chỉ bật hai dòng dưới sau khi service mới đã deploy và /ready trả 200.
PRACTICE_PROVIDER=runpod
MODEL_CALLS_ENABLED=true
AUTHORING_PROVIDER=off
```

Chỉ điền ID vào `RUNPOD_POD_ID` (không thêm `https://`, `-8000` hoặc tên miền).
Backend tự tạo `https://<ID>-8000.proxy.runpod.net` cho cả Medical và Teaching.
Khi đổi Pod, chỉ sửa ID và recreate backend bằng lệnh bên dưới; key chỉ cần đổi
nếu key trên service mới khác key cũ.

`MODEL_SERVICE_BASE_URL` là override tùy chọn cho URL local/custom. **URL đầy đủ
được ưu tiên hơn ID** nếu cả hai được điền. Để trống biến này khi muốn chỉ đổi ID.
URL override là origin, không thêm `/v1`, `/medical/evaluate` hoặc
`/teaching/feedback`; trailing slash được loại bỏ.
Client mới không đọc các URL/key Medical/Teaching/OpenAI/LLM cũ làm fallback.
`PRACTICE_PROVIDER=http` là provider legacy, không phải provider `runpod` mới.

Docker Compose đọc `.env` gốc qua `env_file`. Biến terminal có thể ghi đè các
giá trị `${...}` trong Compose, đặc biệt `MODEL_CALLS_ENABLED`; process environment
cũng ưu tiên hơn dotenv khi chạy Settings trực tiếp. Đặc biệt, URL đầy đủ cũ còn
trong process environment có thể tiếp tục ghi đè cách dùng ID; hãy bỏ override đó.
Service trên Pod đọc process
environment, không tự đọc `.env` web. Không dùng `docker compose config` để chia sẻ
chẩn đoán vì kết quả có thể chứa secret. Thay `.env` cần recreate backend, restart
đơn thuần không cập nhật environment container.

Từ thư mục gốc, với Docker Desktop đang chạy và môi trường local authoring đã có:

```powershell
docker compose -f docker-compose.yml -f docker-compose.authoring.yml up -d --no-deps --force-recreate backend
docker compose exec backend python -m app.ai.check_model_service
```

Lệnh thứ hai chỉ GET `/health`, `/ready`, không inference/retry và không in key.
Có thể dùng nó khi web còn ở mock. Giữ provider mock và chốt model false nếu probe
chưa thành công; provider runpod khi lỗi sẽ báo lỗi rõ ràng, không tự chuyển mock.
Với triển khai không dùng source mount, build lại image backend trước khi recreate.
Frontend không cần đổi URL/key hoặc build lại cho thay đổi serving này.

Transport: connect 10s, read 120s, write 10s, pool 5s mặc định; deadline backend
150s mỗi bước, trình duyệt nhận timeout 310s cho hai bước. Đây là giới hạn vận hành,
không thay đổi token budget/prompt/decoding V1.

## RunPod: một process, một port 8000

Chuyển code mới lên Pod trước. Source of truth là repo; weights/adapters persistent
nằm ngoài repo. Không chạy script dưới trên PC local.

| Model | Base local | Adapter local |
|---|---|---|
| Medical | `/workspace/models/qwen3-4b-instruct-2507` | `/workspace/adapters/medical-v1` |
| Teaching | `/workspace/models/qwen2.5-7b-instruct` | `/workspace/adapters/teaching-v1` |

Giữ đúng CUDA/PyTorch tương thích pilot. Ví dụ tạo venv kế thừa Torch có sẵn và
cài dependency serving, không cài lại Torch hoặc tải weights lúc startup:

```bash
cd /root/MedResident-Tutor
python -m venv --system-site-packages /workspace/venvs/medresident-serving
source /workspace/venvs/medresident-serving/bin/activate
python -m pip install -r services/medical/requirements-gpu.txt -e services/medical

mkdir -p /workspace/secrets
cp -n services/medical/runpod.env.example /workspace/secrets/medresident-serving.env
chmod 600 /workspace/secrets/medresident-serving.env
# Xem SHA-256 của sáu file local, không nạp GPU; đối chiếu manifest V1 đã khóa.
bash services/medical/start-runpod.sh --print-hashes
# Hash pin là tùy chọn; startup tự tính hash còn thiếu. Không in key.
# Có thể đặt MODEL_SERVICE_PYTHON=/workspace/venvs/medresident-serving/bin/python
# trong file để những lần sau không cần activate venv bằng tay.
bash services/medical/start-runpod.sh --check-only
# Nhập key vào environment bằng input ẩn; không lưu secret trong câu lệnh.
set +x
read -rsp 'MODEL_SERVICE_API_KEY: ' MODEL_SERVICE_API_KEY
printf '\n'
export MODEL_SERVICE_API_KEY
bash scripts/runpod/start_model_service.sh
```

Script tự nạp `/workspace/secrets/medresident-serving.env` nếu file tồn tại.
Có thể chọn file bằng `MODEL_SERVICE_ENV_FILE`; nếu đã chỉ định một file không
tồn tại, script từ chối khởi động. Biến môi trường đã export hoặc truyền vào lệnh
được ưu tiên hơn file. Nếu không có file mặc định, dùng environment
đã export. Không cần thêm `.env` web thứ hai.

Một key cho cả hai endpoint: `MODEL_SERVICE_API_KEY` phải giống backend; nếu biến
này chưa đặt/rỗng thì dùng `MEDICAL_API_KEY` hiện có. MODEL key được ưu tiên nếu
cả hai có giá trị; MODEL key là placeholder sẽ bị từ chối, không dùng key cũ để
bỏ qua lỗi. Không tạo key riêng cho Teaching. Paths có mặc định; hash có thể pin
bằng các biến sau, hoặc để startup tự tính khi chưa đặt/rỗng:

```text
MEDICAL_BASE_MODEL_PATH, MEDICAL_ADAPTER_PATH
MEDICAL_ADAPTER_SHA256, MEDICAL_BASE_CONFIG_SHA256, MEDICAL_ADAPTER_CONFIG_SHA256
TEACHING_BASE_MODEL_PATH, TEACHING_ADAPTER_PATH
TEACHING_ADAPTER_SHA256, TEACHING_BASE_CONFIG_SHA256, TEACHING_ADAPTER_CONFIG_SHA256
```

Ba hash mỗi model lần lượt của `adapter_model.safetensors`, base `config.json`,
adapter `adapter_config.json`. Đối chiếu manifest V1 đã khóa trước khi điền; không
lấy hash của artifact bất kỳ rồi coi đó là chứng minh đúng V1. Service kiểm tra
hash trước/sau load, base identity, PEFT LORA/CAUSAL_LM. Việc xác minh toàn bộ
snapshot weights/tokenizer vẫn thuộc bước provision artifact.

Startup tính SHA-256 của sáu file và verify hash được pin **trước khi nạp GPU**.
Hash chưa đặt/rỗng được tính từ file local và truyền vào runner; đó là fingerprint,
không tự chứng minh provenance V1. Sau preflight thành công, script dừng mềm đúng
process Uvicorn Medical service cùng chủ sở hữu đang nghe port 8000, chờ thoát rồi
khởi động app hai model. Không dừng PID 1, process không rõ hoặc ứng dụng khác;
không force-kill. Không tải model, cài package hoặc tạo service thứ hai.

Stdout/stderr được ghi nối vào **`/workspace/outputs/model-service.log`**, đồng
thời hiện trên terminal. Log có mã preflight, hash và tiến độ load từng model;
không ghi key, request payload, raw generation hay exception nhạy cảm. Có thể đổi
đường dẫn bằng `MODEL_SERVICE_LOG_FILE`. Script tắt xtrace, đặt umask 077.

`--print-hashes` chỉ tính hash, không yêu cầu key và không dùng GPU.
`--check-only` xác minh cả hai bộ artifact/key cấu hình rồi thoát, không dùng GPU.
Nếu preflight sai, process thoát mã 1 trước khi mở HTTP; xem log để biết mã lỗi.
Khi preflight qua và đang load GPU, `/health` trả 200, `/ready` trả 503 cho tới khi
cả hai model load xong. Load lỗi giữ ready 503, không fallback sang một model.

Entrypoint production là `medical_service.unified:app`. Script đặt
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `WEB_CONCURRENCY=1`, một worker;
tất cả loaders dùng `local_files_only=True`. Cả hai model NF4 4-bit cùng GPU 0,
load tuần tự. Medical giữ prompt/decoding 1200 token cũ; Teaching tái sử dụng
prompt/guards V1, seed 42, greedy temperature 0, 1600 token. Không đổi adapter.

`medical_service.main:app` hiện là alias của cùng `medical_service.unified:app`.
Cả hai đều yêu cầu Teaching và readiness hai model; không còn entrypoint production
mặc định chỉ nạp Medical. Factory một runner chỉ dùng trong tests/local tooling.
Nếu `/workspace/bootstrap.sh` riêng đang khởi động service cũ, đổi lệnh khởi động
trong file trên Pod để gọi script mới; sửa repo không tự cập nhật file persistent
này. Không ghi key vào bootstrap/Git. Script restart chỉ xử lý process model đã
nhận diện; nếu không nhận diện được, giữ nguyên process và báo lỗi để đọc log.

| API | Ý nghĩa |
|---|---|
| `GET /health` | Process HTTP sống, không chứng minh model sẵn sàng |
| `GET /ready` | 200 `{"status":"ready"}` khi **cả hai** load xong; còn lại 503 |
| `POST /medical/evaluate` | Header X-API-Key, JSON; envelope Medical + metadata + timing |
| `POST /teaching/feedback` | Cùng key; strict JSON + guards + alignment; không raw output |

Load lỗi không tự retry. `/ready` báo mã có tiền tố MEDICAL/TEACHING khi lỗi từng
model. Một khóa GPU chung cho hai endpoint; request đồng thời nhận 429. Khi HTTP
bị hủy, khóa chỉ được nhả sau khi thread generate kết thúc. Không có hàng đợi jobs.
Input mặc định 256 KiB, 4096 token; context cap 8192 và giới hạn thật của model.
Input quá dài bị từ chối, không cắt âm thầm. Không dùng nhiều Uvicorn workers.

## Curl kiểm tra từng bước trên Pod

Đây là fixture protocol tổng hợp, không phải câu hỏi lâm sàng hay locked test.
Chỉ thực hiện sau `/ready` 200. Dùng shell đã có biến secret; tắt shell tracing.
Headers được truyền qua stdin để key không xuất hiện trong argv của curl.

```bash
set +x
# Trong terminal thử riêng, nạp key mà không in ra màn hình.
set -a
source /workspace/secrets/medresident-serving.env
set +a
export MODEL_SERVICE_API_KEY="${MODEL_SERVICE_API_KEY:-${MEDICAL_API_KEY:-}}"
export MODEL_SERVICE_BASE_URL=http://127.0.0.1:8000
curl --silent --show-error --fail-with-body "$MODEL_SERVICE_BASE_URL/health"
curl --silent --show-error --fail-with-body "$MODEL_SERVICE_BASE_URL/ready"
mkdir -p data/authoring/model-service-probe
set +x

# Medical: 1 request, không retry.
printf 'X-API-Key: %s\n' "$MODEL_SERVICE_API_KEY" |
  curl --silent --show-error --fail-with-body --connect-timeout 10 --max-time 145 \
    --header @- --header 'Content-Type: application/json' \
    --data-binary @services/medical/examples/medical-request.json \
    --output data/authoring/model-service-probe/medical-response.json \
    --write-out 'Medical HTTP %{http_code}; total %{time_total}s\n' \
    "$MODEL_SERVICE_BASE_URL/medical/evaluate"

# Chỉ tiếp tục nếu Medical HTTP 200; giữ nguyên MedicalEvaluation vừa nhận.
python services/medical/examples/build_teaching_request.py \
  services/medical/examples/medical-request.json \
  data/authoring/model-service-probe/medical-response.json \
  data/authoring/model-service-probe/teaching-request.json

# Teaching: 1 request, không gửi lại evidence và không retry.
printf 'X-API-Key: %s\n' "$MODEL_SERVICE_API_KEY" |
  curl --silent --show-error --fail-with-body --connect-timeout 10 --max-time 145 \
    --header @- --header 'Content-Type: application/json' \
    --data-binary @data/authoring/model-service-probe/teaching-request.json \
    --output data/authoring/model-service-probe/teaching-response.json \
    --write-out 'Teaching HTTP %{http_code}; total %{time_total}s\n' \
    "$MODEL_SERVICE_BASE_URL/teaching/feedback"
```

Không dùng `-v`, `--trace`, `set -x` hoặc gửi log chứa headers/payload. Ví dụ lưu
JSON phản hồi trong `data/authoring` đã ignore; service không trả raw prediction
khi validation lỗi. Trong luồng web, backend tự xây payload và persist attempt;
không cần chạy curl cho từng câu.

## Lỗi và giới hạn đã biết

| Upstream | Backend stage_error.code |
|---|---|
| 401/403 | `MODEL_SERVICE_UNAUTHORIZED` |
| 429 | `MODEL_SERVICE_BUSY` |
| 503 | `MODEL_SERVICE_NOT_READY` |
| 413 | `MODEL_INPUT_TOO_LARGE` |
| 422 | `MODEL_INPUT_INVALID` |
| 502 / JSON/schema/alignment sai | `MODEL_INFERENCE_FAILED` |
| Connect timeout/network | `MODEL_SERVICE_UNAVAILABLE` |
| Read/write timeout, HTTP 408/504/524 | `MODEL_SERVICE_TIMEOUT` |

Attempt lưu `upstream_http_status` và mã upstream hợp lệ nếu có; không lưu raw
error body/stack trace. Lỗi xác thực service không trả 401 của ứng dụng để tránh
đăng xuất nhầm học viên. Không tự quy lỗi inference thành lỗi PostgreSQL/Neo4j.

RunPod HTTP proxy có timeout Cloudflare **100 giây** theo
[tài liệu expose ports của RunPod](https://docs.runpod.io/pods/configuration/expose-ports).
Read timeout backend 120s không loại bỏ được giới hạn proxy; nếu inference vượt
giới hạn, có thể nhận 524 trong khi GPU vẫn chạy. Không tự gửi lại request đó.
Chưa triển khai job API/streaming hoặc benchmark hai model trên A40 từ môi trường
local này. Cần kiểm chứng GPU memory, runtime packages, chất lượng JSON và latency
trên Pod thật trước khi coi production đã sẵn sàng.

Kiểm tra ngày 17/11/2026: probe cũ từ Windows nhận 403 không phải JSON, nhưng
client backend trong Docker với `trust_env=False` đã nhận `/health` và `/ready`
HTTP 200. Một request Medical với fixture tổng hợp đã trả HTTP 200, đúng contract,
1/1 điểm; model báo `Qwen/Qwen3-4B-Instruct-2507`, NF4, tổng 9,877s, inference
8,843s. Không retry hoặc ghi attempt vào DB web.

OpenAPI của Pod hiện chỉ liệt kê `/health`, `/ready`, `/medical/evaluate`; **chưa
có `/teaching/feedback`**. Vì vậy `/ready` 200 hiện chỉ chứng minh bản Medical-only
đang sẵn sàng. Chưa xác nhận deploy code unified hoặc nạp Teaching trên Pod.
Web local vẫn giữ mock/model calls false đến khi triển khai service mới, kiểm tra
hai endpoint và chủ động bật provider runpod. Không có lỗi DB được suy diễn từ
các probe mạng này.

## Kiểm thử offline

- Backend: `pytest -q tests`; MockTransport kiểm tra endpoint/header/body,
  validation, lỗi, timeout, không retry/fallback.
- Service: `cd services/medical && pytest -q tests`; fake runners/Torch stubs,
  không GPU/model download/locked datasets.
- PostgreSQL: `pytest -q postgres_tests` với `INTEGRATION_TEST_DATABASE_URL` trỏ
  **database test `medresident_test_*` riêng**. Fixture sẽ xóa schema của DB test;
  tuyệt đối không dùng DB web. Kiểm tra cả Medical persist, Teaching fail/retry,
  snapshot, isolation và lịch sử. Không có migration mới.

Xem báo cáo thực thi [model-service-integration-20261117.md](model-service-integration-20261117.md).
