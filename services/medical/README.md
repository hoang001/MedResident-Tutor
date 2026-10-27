# Medical inference service (MVP, RunPod)

Service riêng, không import backend nghiệp vụ, không đọc DB/dataset và không
retrieval/orchestration. Chỉ nạp artifact local đã provision; không tải weights,
không train hoặc đọc test split. Một worker, một generation; request thứ hai nhận
429 `INFERENCE_BUSY` thay vì tạo hàng đợi không giới hạn.

## Logic pilot được tái sử dụng

`model-training/src/medical/inference.py` là module dùng chung, không có side
effect khi import. `prepare_dataset.py` tái sử dụng nguyên system prompt và
`build_user_content`; `evaluate_baseline.py` tái sử dụng loader/parser/generation.
`evaluate_adapter.py` vẫn gọi baseline và nạp adapter như trước.

- Base identity: `Qwen/Qwen3-4B-Instruct-2507`; tokenizer từ base, không lấy
  tokenizer của adapter để thay chat template.
- NF4 4-bit, double quantization, float16, GPU 0, `trust_remote_code=True`,
  `low_cpu_mem_usage=True`, PEFT `is_trainable=False`.
- Chat template: `tokenize=True`, `add_generation_prompt=True`,
  `return_dict=True`, `return_tensors="pt"`.
- Generation giữ nguyên: `max_new_tokens=1200`, `do_sample=False`, temperature,
  top_p, top_k = None; PAD/EOS từ tokenizer/model. Không có retry generation.
- Timing giữ cách đo pilot: wall time quanh `model.generate`, không bao gồm load,
  tokenization hoặc HTTP. Đây chưa phải benchmark CUDA latency đã đồng bộ.

Chỉ serving bật các giới hạn vận hành và strict validation. Không cắt input:
toàn bộ prompt phải vừa max_input_tokens và input + 1200 phải vừa cả giới hạn
context cấu hình lẫn `model.config.max_position_embeddings`.

## Artifact cần đưa lên RunPod

Repo runtime đặt ở `/root/MedResident-Tutor`, không đặt Git repo vào Global Volume.

1. **Base snapshot hoàn chỉnh** từ đúng model/version dùng pilot, ví dụ
   `/workspace/models/Qwen3-4B-Instruct-2507`: config, generation_config,
   tokenizer_config, tokenizer.json/vocab/merges/special-token assets và tất cả
   weight shards cùng index. Đừng chỉ copy `config.json`.
2. **Adapter Medical pilot cuối cùng**, ví dụ
   `/workspace/adapters/medical-qwen3-pilot/adapter`: ít nhất
   `adapter_config.json` và `adapter_model.safetensors`. Không dùng checkpoint
   smoke, Teaching adapter hoặc merged/base-only model. Repo evaluator mặc định
   tìm `model-training/outputs/medical-qwen3-pilot/adapter`, nhưng service chỉ dùng
   `MEDICAL_ADAPTER_PATH`.
3. Giữ báo cáo training/validation và manifest/checksum của lần pilot đã chốt
   để đối chiếu nguồn gốc artifact. Service không cần mở báo cáo hay dataset này.
4. Chuyển cả code service `services/medical` và module dùng chung
   `model-training/src/medical/inference.py` (cùng package `src/medical`) sang repo
   runtime. Các thay đổi hiện chưa commit/push; một checkout Git cũ chưa có module
   này. Không cần chuyển locked test hoặc dataset để chạy service.

Xác nhận adapter bằng provenance của lần pilot, rồi ghi checksum từ **bản đã
chốt đó** vào cấu hình deployment. Tính lại SHA-256 sau khi copy để so khớp.
Không lấy hash từ một thư mục bất kỳ rồi coi đó là chứng minh đúng pilot.
Service kiểm tra base ID trong adapter_config, PEFT LORA/CAUSAL_LM, hash weights
adapter, hash adapter_config và hash base config; không fallback nếu sai/thiếu.
Hash base config không thay thế việc xác minh toàn bộ snapshot weights/tokenizer
ở bước provision. Tên thư mục và `model_selection.json` không chứng minh pilot
đã hoàn tất. Hiện repo local không có weights/hash của adapter đã chốt để tự xác
nhận thay người vận hành. Không chỉnh artifacts trong khi service đang load/chạy.

## Biến môi trường

Không sửa `.env` backend để cấu hình service này. Service đọc process environment.

| Biến | Bắt buộc / ý nghĩa |
|---|---|
| `MEDICAL_BASE_MODEL_PATH` | Có; thư mục base local, đường dẫn tuyệt đối |
| `MEDICAL_ADAPTER_PATH` | Có; thư mục adapter local, đường dẫn tuyệt đối |
| `MEDICAL_ADAPTER_SHA256` | Có; SHA-256 `adapter_model.safetensors` của pilot chốt |
| `MEDICAL_ADAPTER_CONFIG_SHA256` | Có; SHA-256 `adapter_config.json` tương ứng |
| `MEDICAL_BASE_CONFIG_SHA256` | Có; SHA-256 base `config.json` đã xác nhận |
| `MEDICAL_API_KEY` | Có; ít nhất 16 ký tự, lấy từ secret environment; không commit/log |
| `MEDICAL_MAX_BODY_BYTES` | Mặc định 262144 (256 KiB) |
| `MEDICAL_MAX_INPUT_TOKENS` | Mặc định 4096, tính sau chat template |
| `MEDICAL_MAX_CONTEXT_TOKENS` | Mặc định 8192; vẫn bị chặn bởi context thật của model |
| `WEB_CONCURRENCY` | Chỉ dùng 1; lệnh chạy cũng phải `--workers 1` |

Service tự bật HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE và `local_files_only=True`.
Thiếu env bắt buộc: tiến trình từ chối startup với tên biến, không in giá trị.
Thiếu/sai artifact hoặc lỗi load: `/health` vẫn 200, `/ready` 503 với code; nạp lại
cần restart có chủ đích, không tự reload/fallback. Trong lúc load, `/ready` báo
`MODEL_LOADING`. Không dùng nhiều worker/process cùng GPU này.

## Chạy trên RunPod — CHƯA thực thi ở bước triển khai này

Thư mục chạy: `/root/MedResident-Tutor/services/medical`. Dùng môi trường CUDA
của pilot hoặc venv riêng kế thừa bản CUDA PyTorch đó. Không tự nâng cấp torch.
`requirements-gpu.txt` giữ đúng các version ghi trong `run.md`:
transformers 4.57.6, peft 0.21.2, accelerate 1.15.0, bitsandbytes 0.50.2.
Đây là pin từ repo, chưa phải xác minh package thực tế của RunPod/pilot từ xa.

```bash
cd /root/MedResident-Tutor/services/medical
python -m venv --system-site-packages /root/medical-serving-venv
source /root/medical-serving-venv/bin/activate
python -m pip install -e .
# Chỉ cài GPU dependencies nếu môi trường chưa có đúng bản pilot:
python -m pip install -r requirements-gpu.txt

export PYTHONPATH="/root/MedResident-Tutor/model-training${PYTHONPATH:+:$PYTHONPATH}"
export MEDICAL_BASE_MODEL_PATH=/workspace/models/Qwen3-4B-Instruct-2507
export MEDICAL_ADAPTER_PATH=/workspace/adapters/medical-qwen3-pilot/adapter
# Cấp ba MEDICAL_*SHA256 từ manifest artifact pilot đã xác nhận.
# Cấp MEDICAL_API_KEY qua secret environment; không hardcode vào script/repo.
export WEB_CONCURRENCY=1
python -m uvicorn medical_service.main:app --host 0.0.0.0 --port 8001 \
  --workers 1 --no-access-log
```

Chưa thực hiện pip install GPU dependencies, download, upload hoặc GPU inference
trong công việc chuẩn bị này. TLS/network exposure do RunPod/backend deployment
quản lý; API key gửi trong header `X-API-Key`, không đặt trong URL.

## HTTP contract

- `GET /health` public: `200 {"status":"healthy"}` — liveness, không chứng minh GPU ready.
- `GET /ready` public: `200 {"status":"ready"}` chỉ sau khi base + adapter load thành công;
  chưa sẵn sàng trả 503 `{"error":{"code":"..."}}`.
- `POST /medical/evaluate`: `Content-Type: application/json`, header `X-API-Key`.

Ví dụ request **tổng hợp**, không phải dữ liệu y khoa/gold:

```json
{
  "question": "Nêu ý alpha.",
  "student_answer": "Nội dung alpha.",
  "rubric": {
    "rubric_id": "R1", "max_score": 1,
    "criteria": [{
      "criterion_id": "C1", "description": "Nêu ý alpha", "max_score": 1,
      "required_source_unit_ids": ["SU1"],
      "acceptable_variants": [], "common_incorrect_claims": []
    }]
  },
  "evidence": [{
    "source_unit_id": "SU1", "source_id": "SRC1", "title": "Nguồn minh họa",
    "page_start": 1, "page_end": 1, "content": "Nội dung alpha."
  }]
}
```

Thành công trả đúng ba field:

```json
{
  "medical_evaluation": {
    "correct_points": ["Ý alpha"], "incorrect_points": [], "missing_points": [],
    "rubric_scores": [{
      "criterion_id": "C1", "criterion": "Nêu ý alpha", "score": 1,
      "max_score": 1, "reason": "Phù hợp evidence"
    }],
    "total_score": 1, "max_score": 1, "sufficient_evidence": true,
    "evidence_refs": ["SU1"]
  },
  "model_metadata": {"model_id": "Qwen/Qwen3-4B-Instruct-2507"},
  "timing": {"inference_seconds": 0.5, "input_tokens": 200, "generated_tokens": 100}
}
```

`model_metadata` thực tế còn có adapter/config/prompt/chat-template hashes,
quantization/generation config, service version, package versions và limits.
Ví dụ timing/đánh giá trên chỉ minh họa contract. Không trả raw model text khi lỗi.

Validation: strict JSON (không duplicate keys/NaN/Infinity/overflow), typed schema,
unique input IDs, điểm rubric hữu hạn và tổng nhất quán. Output phải đúng đủ
criterion IDs **theo thứ tự rubric**, điểm trong khoảng, max_score khớp và tổng
nhất quán (sai số số thực tối đa 1e-9); evidence_refs chỉ thuộc request và không
trùng. JSON extraction giữ cách pilot xử lý code fence/prose, sau đó mới kiểm tra
strict schema. Không sửa điểm, reason, refs hoặc output để thành PASS.

Evidence rỗng/thiếu cho một criterion có thể được gửi để model báo không đủ
bằng chứng; service không tự tìm/bịa evidence. Validator không chứng minh factual
grounding hoặc tính đúng y khoa của free text; đây vẫn là trách nhiệm đánh giá model.

Mã lỗi: 401 `UNAUTHORIZED`; 413 `REQUEST_TOO_LARGE`, `INPUT_TOKEN_LIMIT`,
`CONTEXT_LIMIT`; 415 `JSON_CONTENT_TYPE_REQUIRED`; 422 `INVALID_REQUEST`;
429 `INFERENCE_BUSY`; 502 `INFERENCE_FAILED`, `MODEL_OUTPUT_INVALID_JSON`,
`MODEL_OUTPUT_INVALID_SCHEMA`, `MODEL_OUTPUT_CRITERION_MISMATCH`,
`MODEL_OUTPUT_SCORE_INVALID`, `MODEL_OUTPUT_TOTAL_MISMATCH`,
`MODEL_OUTPUT_EVIDENCE_INVALID`; 503 gồm `MODEL_LOADING`, `ADAPTER_*_MISSING`,
`ADAPTER_HASH_MISMATCH`, `ADAPTER_CONFIG_HASH_MISMATCH`,
`ADAPTER_IDENTITY_MISMATCH`, `BASE_*`, `CUDA_REQUIRED`, `MODEL_LOAD_FAILED`.
Không log key, request body, raw output hoặc student_answer mặc định.

## Test CPU, không tải model

```bash
cd /root/MedResident-Tutor/services/medical
python -m pip install -e '.[test]'
python -m pytest tests -q
```

Tests dùng FakeRunner và stub torch/transformers, chỉ dữ liệu tổng hợp. Không
import GPU package thật, không mở dataset/test split, không HTTP ra ngoài, không
đụng DB. Phân biệt rõ các test này với load/generation thật: chưa kiểm chứng CUDA,
VRAM, artifacts thực, model latency, output chất lượng hoặc network trên RunPod.
