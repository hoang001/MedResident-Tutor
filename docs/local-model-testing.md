# Kiểm thử hai model V1 trên PC local

Lượt tiếp theo đã sửa timeout local và kiểm 4 Medical HTTP thật với Teaching mock:
[profile deadline và điều tra nội dung](local-medical-deadlines-20261109.md).

## Lượt chạy sau khi nhận adapter

Đã nhận hai bộ file trong `adapter/`, kiểm cấu trúc/tokenizer và chạy cả Medical/Teaching thật.
Kết quả mới nằm trong `data/local-model-tests/runs/20261109T063733Z/`;
xem [báo cáo lượt chạy](local-model-run-20261109.md).
Các thông tin “thiếu adapter/0 generation” bên dưới là trạng thái của **giai đoạn chuẩn bị ban đầu**.

## Giai đoạn chuẩn bị ban đầu, trước khi nhận adapter

**Chưa chạy inference Medical V1 hoặc Teaching V1: thiếu cả hai adapter đã khóa.**
Không chạy base model thay adapter, không train, không gọi server trả phí, không chạy locked test cũ.

Máy xác minh thực tế: RTX 5060, VRAM 8151 MiB, driver 616.92; RAM vật lý khoảng 15,76 GiB.
Baseline lúc 04:45 UTC: RAM khả dụng 5.476.265.984 byte; VRAM dùng 1350 MiB/còn 6546 MiB;
ổ C còn 319.936.606.208 byte. Xem `data/local-model-tests/baseline.json`.

Windows Python 3.13.15 có venv `.venv-local-models`. Đã cài PyTorch 2.10.0+cu128 và dependency
đúng phiên bản trong `services/medical/requirements-gpu.txt`. Tuy nhiên Windows Application
Control chặn `torch/lib/shm.dll`: **OSError / WinError 4551**. Không sửa chính sách bảo mật,
driver hay CUDA hệ thống. Import lỗi này chưa phải lỗi model, adapter hay database.

Đã kiểm tra Ubuntu WSL có GPU nhưng Python 3.14 chưa có pip. Docker truy cập được GPU thật:
`cuInit=0`, `cuDeviceGetCount=0`, số GPU = 1. Chọn runtime Linux trong container dùng image
backend đã có, với venv riêng ở Docker volume `medresident-local-model-venv`, đường dẫn
`/opt/local-models-venv`. Việc này không cài dependency vào container backend đang phục vụ web.
Python/PyTorch/runtime local khác môi trường Kaggle lịch sử; không khẳng định tái lập bitwise.

**Hai base đã tải xong, tổng 23.303.721.749 byte.** Chi tiết hash/revision từng file:
`data/local-model-tests/medical-download.json` và `teaching-download.json`.
**Probe Linux đã đạt**: Python 3.12.16, PyTorch 2.10.0+cu128, CUDA build 12.8,
GPU compute capability 12.0; CUDA matmul, NF4 double quant/dequant và Linear4bit đều chạy.
Peak tensor allocation của probe: 8.712.192 byte, không phải peak của model LLM.
Xem `runtime-probe.json`. `pip check` trên cả hai venv không phát hiện dependency lỗi.
Chỉ `complete=true` cùng hash hợp lệ mới là tải xong. Probe CUDA/NF4 không phải test chấm bài.

## Base model được chọn cố định

| Vai trò | Repo chính thức | Revision tải | Thư mục trên PC |
| --- | --- | --- | --- |
| Medical | Qwen/Qwen3-4B-Instruct-2507 | cdbee75f17c01a7cc42f958dc650907174af0554 | `data/local-models/base/Qwen3-4B-Instruct-2507` |
| Teaching | Qwen/Qwen2.5-7B-Instruct | a09a35458c702b33eeacc393d103063234e8bc28 | `data/local-models/base/Qwen2.5-7B-Instruct` |

Dung lượng các file đã chọn: Medical 8.060.915.998 byte, Teaching 15.242.805.751 byte.
Lưu safetensors gốc, tokenizer/config/LICENSE; lúc load mới lượng tử NF4 4-bit, double quant,
compute float16, batch 1. Không chuyển GGUF. Revision tải là snapshot chính thức hiện tại;
chưa có provenance adapter để xác minh có trùng commit của lần train V1 lịch sử hay không.
Mỗi file được đối chiếu kích thước và SHA-256 LFS hoặc Git blob ID từ Hugging Face.
Tải tiếp tái sử dụng file đã kiểm hash, giữ `.part` nếu gián đoạn, không tải lại file hợp lệ.
Không sử dụng implicit Hugging Face token. Weights, cache, venv và output đã được gitignore.

Các lệnh đã chạy trong repo (đã kiểm `pip check` và `.gitignore`):

```powershell
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.provision medical
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.provision teaching
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.prepare
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.check_app
& ./.venv-local-models/Scripts/python.exe -m pytest local_model_testing/tests -q --junitxml=data/local-model-tests/pytest-preparation.xml
```

`prepare` từ chối ghi đè bộ input đã đóng băng; không chạy lại để sửa expected sau inference.
Kết quả hiện có: **6 test chuẩn bị/an toàn đạt**, không có locked benchmark hay model generation.

## Adapter còn thiếu

Đã tìm `adapter_config.json`, `adapter_model.safetensors`, `adapter_model.bin` trong vùng truy cập
được của `C:/WORKS`, `C:/Users/huyho`, `C:/000`, `C:/ProgramData`, `C:/inetpub`: không thấy.
Không coi các đường dẫn Kaggle trong tài liệu là artifact có trên PC.

Cần cung cấp đúng artifact V1 đã khóa:

- Medical: `model-training/outputs/medical-qwen3-pilot/adapter/`
- Teaching: `model-training/outputs/teaching-qwen2.5-v1/adapter/`

Mỗi thư mục cần `adapter_config.json` và `adapter_model.safetensors`, cùng báo cáo/manifest
hoặc căn cứ xác nhận đúng bản V1. Config phải chỉ đúng base, `peft_type=LORA`,
`task_type=CAUSAL_LM`. Không tự chọn checkpoint hay adapter khác.

Sau khi nhận artifact, sao chép `local_model_testing/locked-adapters.example.json` thành
`data/local-models/locked-adapters.json`; điền hash **được đối chiếu với artifact đã duyệt** và
`locked_v1_provenance` (tham chiếu lần chạy/báo cáo gốc). Đường dẫn tương đối tính từ repo,
dùng được cả Windows lẫn mount Docker `/workspace`. Hash tự tính chỉ chứng minh toàn vẹn,
không tự chứng minh một file bất kỳ là V1 đã khóa. Không điền token/API key vào manifest này.

## Bộ test tích hợp mới

`local_model_testing/prepare.py` tạo 10 tình huống cho CASE01 và XR01, mỗi bài gồm đầy đủ,
một phần, sai rõ, rỗng, không liên quan. Có 8 input model và 2 kiểm tra rỗng ở API.
`data/local-model-tests/integration-inputs.json` cố định hash input và expected trước inference;
`inputs/` và `expected/` tách riêng. Không đưa expected verdict vào request model.
Không dùng/sửa split test hoặc prepared training data cũ.

CASE01: hai tiêu chí độc lập, mỗi tiêu chí 1 điểm: gãy đầu dưới xương quay; phạm khớp.
Đã kiểm hash XML nguồn PMC10182394 và đối chiếu lại nguyên đoạn evidence 412 ký tự.
XR01: gãy xương; tâm box ở hàng 2/cột 2. Đã kiểm hash XML annotation, box gốc
180/428/356/508, ảnh mục tiêu 536×836, thứ tự ảnh và tính lại lưới 3×3.
Đã kiểm hash ảnh/PDF packet và tổng rubric. Chưa có chứng nhận chuyên gia.

Medical chỉ nhận câu trả lời chữ, rubric và evidence chữ; học viên xem ảnh trên web.
Không tuyên bố model tự đọc ảnh. Đáp án/rubric không nằm trong learner payload.

Đã kiểm **BE thật** qua account review có sẵn: hai đề lấy được, không lộ gold; câu rỗng
đều HTTP 422, lịch sử attempt không đổi. Provider vẫn mock; không gọi model để chấm câu rỗng.
Xem `app-preflight.json`. Chưa có practice HTTP với Medical thật/Teaching mock;
chưa có FE/model E2E hay replay Medical thật → Teaching thật.

## Chạy lại khi đã bổ sung đúng adapter

Chạy trong repo, PowerShell:

```powershell
# Smoke: một generation; không phải batch hay kết luận chất lượng.
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.launch medical --smoke

# Batch: smoke rồi tối đa 8 input chấm + 2 case rỗng không gọi model.
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.launch medical

# Chỉ sau khi Medical đã thoát; dùng MedicalEvaluation thật đã lưu.
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.launch teaching --smoke
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.launch teaching

# Có thể gọi ở terminal khác; chỉ dừng container có record/label đúng của lần test.
& ./.venv-local-models/Scripts/python.exe -m local_model_testing.launch stop
```

Các lệnh khởi chạy trên **đã thử bước preflight và dừng vì thiếu adapter**. Không được hiểu
là đã thử thành công load/generate V1. Câu lệnh stop đã thử khi không có worker.
PowerShell máy này chặn chạy `.ps1`; dùng lệnh Python trên không đổi execution policy.
Vẫn có wrapper `scripts/Start-MedicalLocal.ps1`, `Start-TeachingLocal.ps1`,
`Test-LocalModel.ps1 -Kind medical|teaching`, `Stop-LocalModels.ps1` cho môi trường cho chạy script.

Controller dùng Docker `--pull never`, volume venv bền vững, không tải thêm lúc inference,
không tạo listener, service hệ thống, scheduled task hay daemon. Đây là **batch standalone**,
tái sử dụng `PilotRunner` của Medical, chưa phải service HTTP `/ready`/luồng practice.
Teaching wrapper dùng `prepare_dataset.SYSTEM_PROMPT`, cách generate từ evaluator V1 và
`apply_teaching_guards` gốc; không chạy hàm main của evaluator/locked test.

Một GPU chỉ load một model. Input tối đa 4096 token, context tối đa 8192, không cắt ngầm;
Medical giữ max output 1200, Teaching 1600, greedy, không retry. Giới hạn context của
Teaching là giới hạn local an toàn bổ sung, nhỏ hơn context kiến trúc gốc. Script kiểm RAM
khả dụng ≥4 GiB và VRAM còn ≥4 GiB (Medical)/6 GiB (Teaching); đây là gate bảo thủ,
không bảo đảm mọi request đều vừa bộ nhớ. Nếu OOM phải lưu lỗi, dừng process, không đổi model.

Không ghi đè report inference cũ. Muốn chạy lại có chủ đích, trước hết lưu trữ output của
lần trước sang thư mục riêng; không tự xóa hoặc ghi đè để chọn kết quả đẹp.
Hai báo cáo thử khởi chạy ghi rõ lỗi thiếu adapter đã được giữ trong
`data/local-model-tests/preflight/*-missing-adapter.json`, không chứa generation.
Smoke/batch chưa tạo output model.

Teaching batch dự kiến tối đa 6 input: bốn MedicalEvaluation thật đã lưu, thêm learner context
giả lập và một fixture thiếu evidence được gắn nhãn riêng. Không coi fixture là Medical thật.
Raw và output sau guard lưu riêng. Schema/guard/điểm khớp chỉ là các kiểm tra riêng;
đúng chuyên môn và chất lượng phản hồi vẫn cần review, không tự kết luận PASS.

## Kiểm tra và cleanup

`pytest local_model_testing/tests -q` là test **an toàn/chuẩn bị**, không phải test model.
Đã kiểm từ chối adapter thiếu/sai, không fallback base, hash input/expected, từ chối PID
bị tái sử dụng; đã dùng hai container CPU tạm do test tạo để kiểm stop đúng ownership
và không dừng container khác. Hai container này được xóa trong finally.

Controller có `try/finally`, giữ CID + label project, stop đúng container/PID đã xác minh,
không kill theo tên. Worker có `try/finally` để đóng runner, giữ output khi lỗi.
Process/container exit mới giải phóng CUDA context; không coi `empty_cache()` là đủ.
FE/BE/PostgreSQL/Neo4j hiện có được giữ nguyên, provider không sửa nên không phải khôi phục.
Kết quả cleanup cuối cùng, tài nguyên trước/sau và hash các file bảo vệ nằm ở
`data/local-model-tests/final-status.json` khi hoàn tất chuẩn bị đợt này.

Probe container `0d54e5065ea5`, Docker/WSL PID **61652**, đã thoát và được xóa;
container setup/package-check và các container CPU dùng kiểm thử ownership cũng đã thoát/xóa.
Không khởi động worker LLM, không có cổng model nào từng được mở trong đợt này.
Cổng 8101/8102 đều trống; 3000/8000/5433/7687 vẫn truy cập được.
51 tệp bảo vệ giữ nguyên hash; provider `mock`, `model_calls_enabled=false` giữ nguyên.

Đã gửi `POSIX_FADV_DONTNEED` cho các file thường nằm **chỉ trong volume venv vừa tạo**,
với mount chỉ đọc; không xóa file, không dùng global drop_caches. Đây là lời khuyên cache cho
kernel, không bảo đảm Windows lấy lại ngay RAM của WSL hoặc các ứng dụng đang chạy.
Chi tiết ở `cache-release.json`. Đo cuối sau cleanup: RAM khả dụng **5,10 → 5,23 GiB**;
VRAM dùng **1350 → 1138 MiB**, còn 6758 MiB trống. Ổ C còn **257,48 GiB**.
RAM tạm thời xuống 2,35 GiB ngay sau probe, sau đó đã hồi lại trên gate 4 GiB;
xem timestamp và số liệu cuối trong `final-status.json`.
Script sẽ đo lại bộ nhớ trước mỗi lần load; không tự đóng ứng dụng/Docker/DB để đạt gate.
Chưa xác nhận toàn bộ model V1 vừa RAM/VRAM hay chất lượng grading/feedback.

Nguồn chính thức: [Medical base](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
[Teaching base](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct),
[PyTorch wheels](https://pytorch.org/get-started/previous-versions/),
[bitsandbytes installation](https://huggingface.co/docs/bitsandbytes/main/en/installation).
