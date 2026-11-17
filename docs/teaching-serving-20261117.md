# Teaching trong cùng Medical service — 17/11/2026

Đây là báo cáo lượt chuẩn bị local trước khi bổ sung auto-hash/restart. Quy trình
và lệnh deploy đang dùng: [GitHub deployment](runpod-github-deploy.md).

Đã hoàn thiện code trong repo cho một app, một worker, port **8000**, gồm:

```text
GET  /health
GET  /ready
POST /medical/evaluate
POST /teaching/feedback
```

Teaching runner/endpoint đã có từ lượt tích hợp local trước. Đợt này tái kiểm tra
và giữ nguyên implementation đó, hoàn thiện startup, checksum, log và entrypoint
production để không tiếp tục vô tình khởi động bản Medical-only.
Code mới chưa được đưa lên tiến trình Pod đang chạy bằng thao tác nào trong task
này; kết quả dưới là kiểm thử CPU/fake model, không phải xác nhận GPU Teaching live.

## Implementation và files

| File | Nội dung |
|---|---|
| `services/medical/medical_service/teaching.py` | Tái sử dụng runner hiện có: Qwen2.5-7B, NF4 double quant, float16, LoRA V1, seed 42, greedy 1600 tokens, local-only; không thay file/prompt trong đợt này |
| `services/medical/medical_service/app.py` | Giữ factory hai runner và khóa GPU chung; thêm log tiến độ load và mã lỗi đã loại thông tin nhạy cảm |
| `services/medical/medical_service/config.py` | Chọn một key chung: MODEL_SERVICE_API_KEY ưu tiên, MEDICAL_API_KEY khi biến MODEL chưa đặt/rỗng |
| `services/medical/medical_service/unified.py` | Cả hai Settings cùng nguồn key, require_teaching=True |
| `services/medical/medical_service/main.py` | Alias của cùng app unified; không tạo app/lock thứ hai hoặc còn mặc định Medical-only |
| `services/medical/medical_service/bootstrap.py` | Mới: tính sáu SHA-256, kiểm tra artifact/identity, từ chối port bận, exec một Uvicorn worker |
| `services/medical/start-runpod.sh` | Nạp secret env, đặt paths/PYTHONPATH/offline flags, ghi nối log, chạy bootstrap; không install/download |
| `services/medical/runpod.env.example` | Env mẫu không secret thật; có thể chọn Python venv persistent |
| `services/medical/tests/test_bootstrap.py` | Mới: hash mismatch/missing, key precedence/fallback, port bận, một app/worker, shell env/log và không lộ key |
| `services/medical/tests/test_unified.py` | Mở rộng kiểm tra HTTP không trả raw generation, log lỗi không chứa exception/key; giữ readiness/cancellation/shared lock tests |
| `services/medical/README.md`, `docs/unified-model-service.md` | Cập nhật một port, entrypoint, preflight, key và lệnh deploy/curl |

Teaching import trực tiếp `SYSTEM_PROMPT` trong `src.teaching.prepare_dataset`,
`MAX_NEW_TOKENS` V1 và các hàm `input_errors`, `contract_errors`,
`apply_teaching_guards`, `prediction_metrics`. Không copy prompt hoặc tự viết lại
các quy tắc Teaching. Sau generation: strict JSON → schema check → guards → final
alignment validation. Teaching không đánh giá lại Medical hoặc tạo score.

Request giữ contract V1 gồm `schema_version=1.0.0`, question, student_answer,
medical_evaluation, learner_context, metadata. HTTP response giữ envelope tương
thích backend:

```json
{
  "teaching_feedback": {
    "strengths": [],
    "corrections": [],
    "missing_focus": [],
    "learning_priority": [],
    "feedback_text": "Phản hồi hợp lệ, không rỗng, theo Medical Evaluation.",
    "follow_up_question": null
  },
  "model_metadata": {},
  "timing": {}
}
```

Readiness chỉ thành công khi cả hai load xong. Trong lúc nạp hoặc khi một model
load lỗi, `/ready` trả 503; `/health` chỉ báo process sống. Lock chung giữ đến khi
thread generate xong ngay cả khi request bị hủy. Không có queue/retry tự động.

## Env trên Pod

File mẫu: `services/medical/runpod.env.example`. File secret thực tế trên Pod:
`/workspace/secrets/medresident-serving.env` (không phải `.env` web trên PC).

```dotenv
MODEL_SERVICE_API_KEY='<CUNG_KEY_BACKEND_DA_CO>'
TEACHING_BASE_MODEL_PATH=/workspace/models/qwen2.5-7b-instruct
TEACHING_ADAPTER_PATH=/workspace/adapters/teaching-v1
TEACHING_ADAPTER_SHA256='<SHA256_ADAPTER_WEIGHTS_DA_XAC_MINH>'
TEACHING_BASE_CONFIG_SHA256='<SHA256_BASE_CONFIG_DA_XAC_MINH>'
TEACHING_ADAPTER_CONFIG_SHA256='<SHA256_ADAPTER_CONFIG_DA_XAC_MINH>'
```

Giữ ba biến MEDICAL_*SHA256 hiện có; Medical base/adapter mặc định lần lượt
`/workspace/models/qwen3-4b-instruct-2507`, `/workspace/adapters/medical-v1`.
Nếu chỉ có key service cũ `MEDICAL_API_KEY`, có thể giữ biến đó và bỏ MODEL key
khỏi file; bootstrap và cả hai entrypoint dùng chung key này. Không fallback qua
placeholder MODEL key và không đọc LLM/KG/OPENAI key.

## Một lệnh khởi động

Sau khi chuyển code, provision dependencies và file env/hash, dừng process
serving cũ đang dùng port 8000 rồi chạy từ repo trên Pod:

```bash
bash services/medical/start-runpod.sh
```

Không có port/container model thứ hai. Script dùng `os.execv` để thay process
preflight bằng Uvicorn unified, host 0.0.0.0, port 8000, workers 1. Log append tại:

```text
/workspace/outputs/model-service.log
```

Hai chế độ không dùng GPU:

```bash
bash services/medical/start-runpod.sh --print-hashes
bash services/medical/start-runpod.sh --check-only
```

Lệnh đầu tính hash của sáu file local; phải đối chiếu manifest V1 trước khi điền.
Lệnh thứ hai so hash/identity của cả hai và kiểm tra cấu hình. Sai preflight thì
thoát mã 1 trước khi mở HTTP; xem log. Script không tự dùng hash mới tính làm
trusted expected hash, không kill process đang dùng port 8000.

Xem [provision env/venv và hai lệnh curl Medical/Teaching](unified-model-service.md#curl-kiểm-tra-từng-bước-trên-pod).
Builder ví dụ dùng **MedicalEvaluation thực tế vừa nhận**, không thay score và
không truyền evidence cho Teaching. Headers qua stdin để không đặt key vào argv.

## Kiểm chứng

- Focused bootstrap + unified trước mở rộng case key legacy: **32 passed**.
- Service regression cuối: **75 passed**; dùng fake runners và Torch/model stubs.
- Backend regression: **135 passed**, gồm client Medical/Teaching, lỗi, timeout,
  provider gates và config Pod ID. Tổng hai bộ regression: **210 passed**.
- Ruff và bash syntax pass; shell test xác nhận env/path có dấu cách, offline flags,
  append log, forward args và không in key ngay cả khi gọi script bằng `bash -x`.
- 52 protected source/adapter files khớp SHA-256 trước đó; không có diff trong
  model-training hoặc data/training. Không sửa prompts, adapters, locked sets,
  training; không chạy locked evaluations, không load GPU/download model local.
- File Git có thể theo dõi không chứa API key thật. `.env` backend không thay đổi;
  không đổi provider web hoặc dữ liệu/tiến độ của học viên.

JUnit và hash verification nằm tại `data/authoring/teaching-serving-20261117/`
(ignored). Không gọi inference RunPod trong task này. Sau khi deploy bản code mới,
cần kiểm tra lại `/ready`, thử hai endpoint và một lượt web đủ cả hai model;
chưa thể kết luận chất lượng Teaching hoặc VRAM/latency thật từ unit tests.
