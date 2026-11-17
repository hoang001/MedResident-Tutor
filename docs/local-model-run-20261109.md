# Chạy hai adapter local — 2026-11-09

Thư mục kết quả: `data/local-model-tests/runs/20261109T063733Z/`.
**Đã chạy xong cả hai model bằng adapter người dùng cung cấp và đã cleanup.**
Model chạy được local, nhưng grading/feedback còn lỗi và luồng HTTP live bị timeout.
Chi tiết máy đọc được nằm ở `run-summary.json`.
Không dùng server trả phí, không train và không chạy/chỉnh locked benchmark cũ.

## Artifact và runtime

| Vai trò | Base | Adapter người dùng cung cấp |
| --- | --- | --- |
| Medical | Qwen/Qwen3-4B-Instruct-2507 | `adapter/adapter/` |
| Teaching | Qwen/Qwen2.5-7B-Instruct | `adapter/teaching-qwen2.5-v1/adapter/` |

Cả hai config đúng base, LoRA/CAUSAL_LM, r=16, alpha=32, dropout=0,05,
đúng bảy module projection. Đã kiểm mọi tên/shape tensor theo kiến trúc base:
Medical 504 tensor, Teaching 392 tensor; kích thước file khớp offset safetensors.

Tokenizer khác byte do cách save: header merges, định dạng cặp merges, chat template tách
sang `.jinja`, trường mặc định `ignore_merges`. Vocab, merges có thứ tự, special tokens và
chat template tương đương về nội dung. Inference dùng tokenizer base gốc đúng code V1.

Manifest nằm ở `data/local-models/locked-adapters.json`; audit ở `adapter-inspection.json`.
Hash weights nhận được:

- Medical: `cafcf7b7e3793ee7e09149a614f4289912609641d020d9b8c38d69684141e5a8`
- Teaching: `6c22ef9e2b6b4ae31f6d57940c801df7b3c6173622b86d284d20c549e970aec6`

**Giới hạn provenance:** đây là hai bộ artifact người dùng đưa để chạy V1. Không có hash
lịch sử độc lập để chứng nhận đúng bản từng khóa. Teaching có training_summary/trainer_state
khớp V1: không phải smoke, 35 mẫu train, 10 validation, 15 optimizer steps, epoch 3.
Medical không kèm training report. Hash mới chỉ cố định chính bộ file vừa nhận.

RTX 5060 8151 MiB, RAM 15,76 GiB; runtime Linux Docker, Python 3.12.16,
torch 2.10.0+cu128, transformers 4.57.6, PEFT 0.21.2, accelerate 1.15.0,
bitsandbytes 0.50.2. Adapter lưu bởi PEFT 0.19.1; runtime theo pin GPU hiện tại của repo.
Giữ NF4 4-bit/double quant/float16, batch 1, GPU 0, greedy; không đổi prompt/guard.
Không khẳng định tái lập bitwise môi trường train Tesla T4.

## Medical thật

Một smoke, 8 câu không rỗng của bộ tích hợp mới và một generation qua HTTP.
Hai câu rỗng được BE thật từ chối HTTP 422; không gọi model để chấm câu rỗng.
Giữ nguyên input/expected đã đóng băng ở lượt chuẩn bị, kiểm hash trước khi chạy.

| Bài | Loại câu trả lời | Điểm kỳ vọng | Điểm model | Nhận xét |
| --- | --- | --- | --- | --- |
| CASE01 | Đầy đủ | 2 | 2 | Đúng các ý theo nguồn |
| CASE01 | Một phần | 1 | 1 | Đúng phần có/thiếu |
| CASE01 | Sai rõ | 0 | **1** | Sai điểm và phân loại ý đúng |
| CASE01 | Không liên quan | 0 | 0 | Hai tiêu chí được đánh dấu thiếu |
| XR01 | Đầy đủ | 2 | 2 | Đúng các ý theo annotation |
| XR01 | Một phần | 1 | 1 | Đúng phần có/thiếu |
| XR01 | Sai rõ | 0 | 0 | Điểm khớp nhưng ý đúng mâu thuẫn câu trả lời |
| XR01 | Không liên quan | 0 | 0 | Gán câu về nghe nhạc thành incorrect_point |

**8/8 đúng schema, 7/8 khớp điểm kỳ vọng; có 3 câu bị gắn cờ qua review nội dung.**
Đây là bộ nhỏ gồm hai bài mới, không phải thước đo accuracy tổng quát hay duyệt chuyên gia.

Lỗi rõ nhất: “Gãy đầu dưới xương trụ, không phạm khớp” được model đưa vào correct_points
và chấm tiêu chí “Gãy đầu dưới xương quay” 1 điểm. Evidence thực tế nói distal radius,
intra-articular. XR01 trả lời “không có gãy” nhưng correct_points lại ghi nhận diện gãy.
Không sửa output để khớp expected và không tune prompt/validator theo kết quả.

Raw và parsed output ở `medical-batch.json`, `raw/`, `medical-smoke-raw.json`.
Review thủ công được gắn SHA-256 của đúng batch ở `manual-review-notes.json`;
không được áp ghi chú này lên một model run khác. Model chỉ chấm văn bản, không đọc ảnh.

## Practice với Medical HTTP thật

Dùng lại Medical FastAPI service/PilotRunner, `/ready` trả **200** sau khi nạp adapter.
Một child app BE thật chạy qua ASGI, dùng auth/router/snapshot/validator và PostgreSQL thật;
provider test ghép Medical HTTP thật với Teaching mock rõ ràng. Không đổi process BE port 8000.
Mọi write test nằm trong outer transaction rollback, đã kiểm attempt không còn sau rollback.

Kết quả:

- POST practice trả HTTP **200**, nhưng attempt là **medical_failed**.
- Stage error giữ nguyên: `{"code":"PROVIDER_TIMEOUT","stage":"medical"}`.
- BE hiện có deadline **30 giây**. Generation thực tế xong sau **31,56 giây**, ra JSON hợp lệ,
  điểm 2/2. HTTP caller không nhận kết quả trước deadline; model không bị đổi sampling/retry.
- Medical gọi đúng một lần; Teaching mock **chưa được gọi** vì dừng ở stage Medical.
- Không quy lỗi này cho PostgreSQL. `practice-http.json` và `medical-http-generation.json`
  lưu riêng trạng thái app và output model hoàn thành muộn.

Không sửa timeout production trong đợt kiểm này. Generation batch không bị giới hạn thời gian;
HTTP client chỉ có connect timeout, nhưng deadline của orchestration BE vẫn có hiệu lực.

## Teaching và phép nối tuần tự

Sáu input được kiểm contract và cố định trước inference trong `teaching-replay-inputs.json`:
bốn MedicalEvaluation thật đã lưu, một context fixture dựa trên Medical thật, một fixture
đổi sufficient_evidence=false để kiểm guard. Các fixture có nhãn nguồn riêng.
Giữ nguyên MedicalEvaluation sai ở CASE01; Teaching không được tự sửa lại chuyên môn.

Đã chạy một smoke và cả sáu input. **6/6 đúng schema; 4/6 đạt toàn bộ proxy rule ở raw;
sau guard đạt 5/6.** Raw và kết quả sau guard giữ riêng trong `teaching-raw/`,
`teaching-guarded/`, `teaching-batch.json`.

- Fixture thiếu evidence: raw bỏ cảnh báo; guard thêm cảnh báo theo sufficient_evidence=false.
- CASE01 sai rõ: sau guard vẫn fail strengths_consistency, corrections_consistency,
  missing_focus_consistency. Teaching đưa “không phạm khớp” vào corrections/missing dù
  Medical đã xếp nó vào correct_points. MedicalEvaluation đầu vào vốn mâu thuẫn giữa
  các danh sách ý và rubric score; output này không đạt contract alignment V1.
- Không dùng Teaching để sửa ngược Medical, không sửa prompt/guard hoặc chạy lại chọn output.

Đã replay cả hai output thật cho CASE01 đầy đủ qua BE ASGI/PostgreSQL: attempt completed,
history reload đúng, sau đó rollback và kiểm attempt không tồn tại. Không có generation mới.
Với CASE01 sai rõ, replay chứng minh BE từ chối output Teaching bị lệch: **teaching_failed /
TEACHING_ALIGNMENT_INVALID**; dữ liệu cũng rollback. Đây là phép nối contract bằng replay,
không phải hai service live E2E. Metadata từng stage ghi rõ execution_mode=replay.

Thời gian generation batch: Medical trung bình khoảng 18,81 giây/câu;
Teaching khoảng 12,57 giây/input. Peak tensor allocation: Medical **2,97 GiB**,
Teaching **5,63 GiB**, theo torch.cuda.max_memory_allocated (không gồm toàn bộ VRAM của app khác).
Số token, thời gian từng request, cấu hình và hash prompt/chat template ở hai batch JSON.

## Chạy lại và dừng

Với hai adapter hiện tại, tạo lượt mới để tránh ghi đè output:

```powershell
$py = '.\.venv-local-models\Scripts\python.exe'
& $py -m local_model_testing.inspect_adapters
$env:LOCAL_MODEL_TEST_RUN_ID = (& $py -c "from local_model_testing.common import REPORT_BASE,read; print(read(REPORT_BASE/'active-run.json')['run_id'])")
& $py -m local_model_testing.launch medical
& $py -m local_model_testing.check_http
& $py -m local_model_testing.launch teaching
& $py -m local_model_testing.check_replay
& $py -m local_model_testing.launch stop
```

Lệnh stop ở terminal khác cần cùng `LOCAL_MODEL_TEST_RUN_ID`.
Mỗi model chỉ chạy khi chủ động gọi; container/PID có record và label kiểm ownership.
Giữ weights/adapter/venv trên đĩa, không tự khởi động lại. Folder `adapter/` được gitignore.

Web chính vẫn giữ provider mock; chưa chạy browser FE với model thật. Không cập nhật mastery
từ các bài thử này. Các attempt HTTP/replay đều rollback, không để lại điểm test trong DB.

## Cleanup và kết luận

- Không còn container/worker do đợt test tạo; cổng 8101 và 8102 trống.
- Medical HTTP Docker/WSL PID **82956** đã dừng; Teaching PID **86813** đã thoát.
  Medical batch đầu tự thoát/container tự xóa, không thu được Docker PID trước khi xóa.
- FE/BE/PostgreSQL/Neo4j và cấu hình provider ban đầu giữ nguyên.
- RAM khả dụng **5,03 → 6,70 GiB**; VRAM dùng **1340 → 1133 MiB** tại lần đo cuối sau cleanup.
- **55 tệp** nguồn/dữ liệu bảo vệ giữ nguyên hash. Adapter/base/venv và mọi raw output được giữ.
- Không gọi dịch vụ trả phí, không đổi precision/model, không tự retry generation, không train.

Hai adapter tương thích kiến trúc và chạy được trên PC này bằng NF4 tuần tự. Kết quả thử
chưa đủ tin cậy để chấm điểm chính thức: có lỗi nội dung Medical, lỗi alignment Teaching,
và deadline BE 30 giây làm hỏng một luồng HTTP dù model hoàn thành hợp lệ sau đó.
