# Profile local và điều tra Medical — 2026-11-09

Run mới: `data/local-model-tests/runs/20261109T092457Z/`.
Run cũ `20261109T063733Z` giữ nguyên toàn bộ input, expected, raw và report.
**Đã sửa profile timeout, chạy đúng 4 generation Medical thật và cleanup. Teaching chỉ mock.**

## 1. Timeout cũ và mới

| Lớp | Trước đây | Profile local mới |
| --- | --- | --- |
| HTTPProvider connect | 30 s | 5 s |
| Medical HTTP read/generation wait | 30 s | 90 s |
| HTTP write | 30 s | 10 s |
| HTTP pool | 30 s | 5 s |
| BE Medical orchestration | 30 s | 115 s = 90+5+10+5+5 grace |
| BE Teaching stage | 30 s | 30 s, không đổi; đợt này dùng mock |
| Frontend submit/retry | 45 s mặc định | 155 s khi config trả profile local HTTP |
| Caller của bài test ASGI | Không có deadline bao ngoài rõ | 160 s, lớn hơn hai stage + overhead |
| Readiness/load model | Poll không có hạn tổng | 1200 s; connect 2 s, read 5 s riêng cho poll |
| Medical service | Không có deadline generation nội bộ | Giữ nguyên; output cap 1200 token như cũ |
| Uvicorn keep-alive | Idle connection, không phải active request | Giữ nguyên |
| Docker stop grace | 30 s lúc cleanup | Giữ nguyên; không phải deadline generation |

Ghi chú: HTTP client của harness cũ có read timeout=None, connect=10; chính deadline BE
30 s đã cắt lượt cũ ở 31,56 s. HTTPProvider thông thường trước sửa vẫn dùng 30 s cho cả bốn
timeout transport. Harness mới gọi HTTPProvider thực của source mới để kiểm đúng lớp đó.

Profile chỉ bật khi `practice_runtime_profile=local` và `app_env=development`.
Production không được bật local; default/mock vẫn có deadline 30 s và frontend 45 s.
`/practice/config` chỉ xuất request_timeout_ms=155000 cho local HTTP; các request khác vẫn
dùng timer mặc định. Không có proxy request deadline riêng trong đường frontend gọi BE trực tiếp.
Healthcheck DB 5 s không liên quan tới inference và không sửa.

Không có fallback, retry generation hay tự tăng deadline khi lỗi. Một giá trị trả muộn từ
provider bỏ qua cancellation cũng bị loại sau deadline. Claim token vẫn bảo vệ việc một
response cũ ghi đè attempt đã failed/reclaimed. Idempotency key ngăn tạo attempt/generation trùng.

**HTTP kết thúc không đồng nghĩa GPU generation đã bị hủy:** Medical service đang shield
task chạy trong thread, giữ lock tới khi generate xong. Model chỉ unload hoàn toàn khi process/
container thoát. Hành vi này được giữ nguyên và đã quan sát ở run cũ.

## 2. File sửa và kiểm thử

- `apps/backend/app/core/config.py`: profile development có bounds/validation, deadline từng stage.
- `apps/backend/app/modules/practice/providers.py`: transport timeout riêng; cấu hình stage rõ ràng;
  request ID để truy vết. Mặc định vẫn yêu cầu đủ hai service như trước.
- `apps/backend/app/modules/practice/service.py`: chọn deadline theo stage, loại response muộn.
- `apps/backend/app/modules/practice/router.py`: deadline profile và budget cho frontend.
- `apps/frontend/app/learn/page.tsx`: submit/retry nhận budget từ config; không đổi apiRequest toàn cục.
- `.env.example`: chỉ thêm hướng dẫn commented; không sửa `.env` hay cấu hình runtime web chính.
- `local_model_testing/profiles/local-medical.json`: profile được lưu để chủ động chạy lại.
- Harness: chuẩn bị run mới, điều tra offline, trace token/EOS, giới hạn 4 generation, live BE
  child app/rollback và kiểm cleanup. Không đổi inference primitive, prompt, sampling hay guard.

**10 test timeout/logging đạt** và frontend `npm run typecheck` đạt. Test bao gồm response sau
deadline cũ nhưng trong deadline local, timeout đúng stage, cancellation bị bỏ qua nhưng output
muộn không được lưu, không retry/fallback, default production/mock giữ nguyên, DTO budget đúng,
tracer không đổi arguments/output và cap generation 4. Profile chặn batch/smoke/Teaching model.
JUnit ở `deadline-tests.xml`; lệnh Docker CPU của bộ test cũng đã chạy thành công trong đợt này.

## 3. Điều tra artifact cũ trước generation

`investigation.json` và ba file `investigation/<case_id>.json` được tạo khi **0 generation mới**.
Mỗi file chứa question + phiên bản bằng frozen SHA, answer, rubric, evidence/refs, payload
sau mapping, messages, chat template dựng lại, raw completion, parsed output và expected.

Đã kiểm hash manual-review-notes trỏ đúng medical-batch cũ; hash input/expected, raw riêng và
batch khớp nhau. Raw JSON bằng parsed output, parser không viết lại kết quả. Prompt/template
hash và token count dựng lại khớp metadata cũ: lần lượt 1265/1186/1177 input token.
Không có prediction cache trong runner; mỗi payload được truyền trực tiếp vào generate.
Đây là token-only reconstruction, không load/gọi language model.

Run cũ không lưu token IDs thật hoặc finish_reason nên không khẳng định EOS cũ. Output
199/226/227 token đều dưới cap 1200, input dưới 4096 và tổng context dưới 8192; không có
dấu hiệu truncation. Run mới đã ghi actual decoded prompt, token fingerprint và EOS thật.

| Case cũ | Đối chiếu | Phân loại nguyên nhân |
| --- | --- | --- |
| CASE01 sai rõ | Answer “xương trụ, không phạm khớp”; criterion “xương quay”; evidence distal radius/intra-articular. Raw vẫn chấm tiêu chí quay 1 điểm và đặt hai claim vào correct_points. | Lỗi ngữ nghĩa trong completion so với evidence/rubric. Không thấy lỗi mapping/parser/token loss; nguyên nhân nội tại training/reasoning chưa được xác định. |
| XR01 sai rõ | Answer phủ nhận gãy, grid 1/1. Evidence annotation fracture, tâm ở 2/2. Raw tổng 0 đúng nhưng correct_points lại ghi nhận gãy; claim grid sai bị coi là thiếu. | Completion mâu thuẫn về nghĩa; numerical contract không bắt được. |
| XR01 không liên quan | Câu nghe nhạc có mặt nguyên vẹn trong payload/raw. Điểm 0 và thiếu hai tiêu chí rõ ràng; model còn cho câu đó vào incorrect_points. | Chính sách expected/prompt về off-topic còn mơ hồ. Sở thích nghe nhạc không xác minh được từ evidence; không đủ cơ sở gán toàn bộ hiện tượng thành lỗi reasoning chuyên môn. |

XR evidence là mô tả văn bản của annotation gốc và vị trí lưới tính từ box; đủ hỗ trợ hai tiêu chí
đang hỏi, không hỗ trợ suy diễn subtype/điều trị. Model không đọc ảnh. Question không có revision
riêng nên dùng exercise ID/rubric ID và frozen payload SHA để xác định đúng phiên bản.

**Đề xuất riêng cho case off-topic:** làm rõ khác biệt “không liên quan” và “claim bị evidence bác bỏ”,
cùng cách đặt sufficient_evidence. Không sửa expected cũ, không thêm luật nghe nhạc hoặc từ khóa xương.

Validator hiện có kiểm strict JSON/schema, IDs/order không trùng, điểm trong miền, tổng và refs
thuộc request. Nó không phải bộ chấm lại chuyên môn. Muốn kiểm nghĩa tốt hơn cần specification
và tập review chuyên gia độc lập; không coi keyword matching là đã giải quyết mâu thuẫn clinical.
Đợt này không thêm semantic guard, không sửa điểm/output và không gọi LLM judge.

## 4. Live backend → Medical thật → Teaching mock

Dùng child app ASGI với **snapshot source mới** trong run, cùng code auth/router/snapshot/
HTTPProvider/validator và PostgreSQL thật. Private process giữ profile local; process BE port
8000 đang phục vụ web không bị restart hay đổi provider. Đây không phải browser E2E/replay.
Snapshot cũng mang bản source Medical validator/Teaching guard nguyên trạng.

Medical cùng adapter/hash cũ, NF4/double quant/float16, batch 1, greedy, output cap 1200;
không smoke thêm, không load Teaching. `/ready` 200 sau **375,52 s**, trong hạn load 1200 s.

| Case mới | HTTP/attempt | Calls Medical/Teaching mock | Wall / generation | Điểm expected / actual |
| --- | --- | --- | --- | --- |
| CASE01 đầy đủ | 200 / completed | 1 / 1 | 29,64 / 29,47 s | 2 / 2 |
| XR01 đầy đủ | 200 / completed | 1 / 1 | 19,75 / 19,66 s | 2 / 2 |
| CASE01 sai rõ | 200 / completed | 1 / 1 | 17,89 / 17,81 s | 0 / **1** |
| XR01 sai rõ | 200 / completed | 1 / 1 | 20,99 / 20,92 s | 0 / 0, nhưng correct_points vẫn mâu thuẫn |

Hai case chẩn đoán được chọn trước để kiểm lại hai lỗi rõ dưới mapping HTTP thực và thu token/EOS;
không gọi lại case để chọn output đẹp. **Tổng 4/4 generation, không retry, không gọi Teaching model.**

Mỗi case có đúng một Medical HTTP và một Teaching mock, metadata phân biệt rõ. Kết quả được
lưu trong transaction, GET detail/history khớp; POST cùng idempotency key trả cùng ID mà không
tăng calls. Sau đó rollback và xác nhận tất cả attempt test không còn. Không cập nhật mastery.

Điểm lưu ý về bằng chứng deadline: profile thực tế đúng read=90/outer=115/request=155, nhưng
**cả bốn request mới tình cờ đều dưới 30 s**. Vì vậy không nói đã có live request >30 s được cứu
trong run mới; test controlled provider chứng minh nhánh vượt deadline cũ vẫn được nhận trong
deadline local. Không cố làm model chậm hay phát sinh thêm generation để tạo bằng chứng đẹp.

Actual payload cả bốn case bằng frozen payload về nội dung JSON; raw bằng parsed, student answer
có mặt trong actual decoded prompt. Cả bốn dừng ở **EOS**, không chạm cap; generated token
lần lượt **197, 220, 199, 235**. Không thấy thiếu text hoặc trộn request. Khác thứ tự key JSONB
có thể làm rendered prompt bytes khác batch cũ dù nội dung JSON bằng nhau; không đổi builder
đã khóa hoặc suy ra đây là nguyên nhân lỗi nếu chưa có kiểm chứng đối chứng.

Hai lỗi rõ tái hiện trong raw và parsed mới: sửa timeout/plumbing không làm model tự chấm đúng.
Không coi HTTP 200/completed hay 3/4 điểm khớp là chứng nhận chất lượng chuyên môn.

## 5. Teaching — chỉ phân tích output cũ

MedicalEvaluation cũ được đưa nguyên vẹn vào Teaching: cả hai claim ở correct_points nhưng
criterion thứ hai lại 0 điểm. Teaching chuyển “không phạm khớp” sang corrections/missing,
vi phạm alignment với những danh sách đó. Đầu vào đang tự mâu thuẫn nên chưa đủ căn cứ kết luận
lỗi alignment này là lỗi độc lập trên đầu vào Medical nhất quán. Không chỉnh Medical để nối thành công.
Fixture thiếu evidence cũ cũng cho thấy raw thiếu cảnh báo và guard có bổ sung; không nạp/gọi
Teaching hoặc dùng một model khác làm judge trong đợt này.

## 6. Cleanup và tính toàn vẹn

Medical Docker/WSL PID **22264** đã dừng; cổng 8101 trống. 8102 chưa được mở. Không còn
container/worker của đợt thử giữ GPU. RAM khả dụng **6,48 → 6,59 GiB**; VRAM dùng
**1165 → 1167 MiB** tại lần đo audit; app nền vẫn dùng GPU/RAM nên không kỳ vọng bằng 0.
FE/BE/PostgreSQL/Neo4j và provider mock của web chính giữ nguyên. Không thay DB/VPN/route/KG.

Mọi file của run cũ và 55 file nguồn/dữ liệu đóng băng giữ nguyên hash. Giữ weights,
adapter, venv/cache trên đĩa. Config profile còn để bật chủ động; không tạo autostart/daemon/task.

## 7. Chạy lại

Các lệnh chạy trong root repo; cần Docker Desktop/GPU đã sẵn có. Không dùng `.ps1` nếu máy
vẫn chặn execution policy. Chuỗi dưới tạo run mới, không ghi đè kết quả cũ:

```powershell
$py = '.\.venv-local-models\Scripts\python.exe'
$docker = 'C:/Program Files/Docker/Docker/resources/bin/docker.exe'
& $py -m local_model_testing.prepare_local_profile
$env:LOCAL_MODEL_TEST_RUN_ID = (& $py -c "from local_model_testing.common import REPORT_BASE,read; print(read(REPORT_BASE/'active-run.json')['run_id'])")

# Offline/tokenizer only, không GPU generation.
& $docker run --rm --mount "type=bind,source=$PWD,target=/workspace" --mount type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv -w /workspace -e LOCAL_MODEL_TEST_RUN_ID=$env:LOCAL_MODEL_TEST_RUN_ID -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 --entrypoint /opt/local-models-venv/bin/python medresident-tutor-backend:latest -m local_model_testing.investigate

# CPU tests; global backend dependencies + pytest trong venv inference.
& $docker run --rm --mount "type=bind,source=$PWD,target=/workspace" --mount type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv -w /workspace -e DEBUG=false -e 'PYTHONPATH=/workspace:/workspace/apps/backend:/usr/local/lib/python3.12/site-packages' --entrypoint /opt/local-models-venv/bin/python medresident-tutor-backend:latest -m pytest local_model_testing/tests/test_local_deadlines.py local_model_testing/tests/test_http_trace.py -q --junitxml=data/local-model-tests/runs/$env:LOCAL_MODEL_TEST_RUN_ID/deadline-tests.xml

# Tự bật Medical, đợi ready, tối đa 4 generation qua BE, rồi tự stop/finally.
& $py -m local_model_testing.run_local_profile
& $py -m local_model_testing.finish_local_profile

# Ở terminal khác: đọc cùng run ID rồi stop đúng container có ownership.
& $py -m local_model_testing.launch stop
```

Các primitive investigate/tests/run_live/stop đã thực chạy; helper chuẩn bị run được gom lại
từ các bước đã dùng trong đợt này. Bật profile cho web lâu dài cần rebuild source BE/FE mới và
cấu hình provider rõ ràng; đợt này chỉ kiểm child app biệt lập, không chuyển web chính sang model.

Kết quả máy đọc: `profile-summary.json`, `live-profile.json`, `generation-budget.json`,
`http-generations/`, `http-token-traces/`, `investigation.json`. Lỗi đã sửa ở code là phân lớp
deadline và bảo vệ output trả muộn; lỗi semantic Medical và chính sách off-topic vẫn cần xử lý
ở bước review/model specification tiếp theo, ngoài phạm vi run này.
