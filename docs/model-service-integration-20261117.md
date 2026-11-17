# Tích hợp Medical + Teaching service — 17/11/2026

Báo cáo kiểm chứng của lượt tích hợp trước. Các lệnh triển khai hiện tại và thay
đổi tiếp theo được ghi trong [GitHub deployment](runpod-github-deploy.md).

Đã triển khai code backend và service unified, giữ kiến trúc nghiệp vụ hiện có.
Medical trên Pod hiện tại đã gọi thành công bằng key mới. Teaching cần deploy
code mới lên Pod trước khi bật luồng web thật.

## Kết quả gọi thật

| Kiểm tra | Kết quả |
|---|---|
| `/health` qua client backend trong Docker | HTTP 200, `healthy` |
| `/ready` qua client backend trong Docker | HTTP 200, `ready` của bản Medical-only |
| OpenAPI | Chỉ có health, ready, medical/evaluate; chưa có teaching/feedback |
| Medical, đúng **1 request** tổng hợp | HTTP 200, contract hợp lệ, điểm 1/1 |
| Model báo về | `Qwen/Qwen3-4B-Instruct-2507`, Medical LoRA, NF4 4-bit |
| Adapter weights | Hash trùng adapter Medical local đã khóa |
| Tổng thời gian | 9,877 giây |
| Thời gian inference service báo | 8,843 giây |
| Tokens service báo | 625 input / 102 generated |
| Thời điểm phản hồi | 11:25:13 ngày 17/11/2026, giờ Việt Nam |

Đầu ra Medical xác định đúng nhãn Alpha từ evidence tổng hợp, không có ý sai/thiếu,
criterion `SYNTHETIC_C` đạt 1/1, evidence ref `SYNTHETIC_SU`. Đây là kiểm tra
giao thức và serving, không phải đánh giá chất lượng lâm sàng hoặc locked test.
Không gửi inference Teaching khi endpoint chưa tồn tại. Không ghi probe vào
practice_attempts của web. Probe Windows trước đó nhận 403 không JSON; kết quả
Docker/client mới xác nhận kết nối và key Medical thành công.

## Files thay đổi

| Nhóm | Files và mục đích |
|---|---|
| Backend config | `.env.example`, `apps/backend/app/core/config.py`: bốn biến MODEL_SERVICE, timeout cho provider runpod |
| HTTP client | `apps/backend/app/ai/model_service.py`: async httpx, typed result, X-API-Key, strict validation, ánh xạ lỗi, không retry/fallback |
| Probe CLI | `apps/backend/app/ai/check_model_service.py`: GET health/ready, chỉ in trạng thái/thời gian/mã lỗi |
| Orchestration | `apps/backend/app/modules/practice/providers.py`, `service.py`: provider runpod, lịch sử cố định, lỗi upstream được lưu theo stage |
| Service chung | `services/medical/medical_service/app.py`, `config.py`, `runner.py`: mở rộng factory/config/artifact checker sẵn có, readiness cả hai, khóa GPU chung |
| Teaching | `services/medical/medical_service/teaching.py`, `unified.py`: loader local-only và route strict Teaching V1 |
| Khởi động | `services/medical/start-runpod.sh`, `runpod.env.example`, `.gitattributes`: một port/worker, env mẫu, LF trên Windows |
| Dependency | `services/medical/pyproject.toml`: khai báo Pydantic dùng trực tiếp; `validation.py` chỉ thêm dòng trắng theo formatter |
| Ví dụ | `services/medical/examples/medical-request.json`, `build_teaching_request.py`: fixture tổng hợp và giữ nguyên anchor Medical thực tế |
| Tests mới | `apps/backend/tests/test_model_service.py`, `apps/backend/postgres_tests/test_model_service.py`, `services/medical/tests/test_unified.py` |
| Regression cũ | `apps/backend/postgres_tests/test_question_bank_migration.py`: so sánh toàn bộ trường cũ sau upgrade và kiểm tra trường structured_result mới có default NULL; không sửa migration |
| Docs | `docs/unified-model-service.md`, báo cáo này, cùng các liên kết cập nhật ở `docs/local-practice.md`, `docs/runpod-model-api.md`, `services/medical/README.md` |

File riêng `.env` gốc đã có URL/key mới do người dùng điền, không được Git theo dõi.
Không thay key, không dùng key cũ làm fallback, không hard-code Pod URL vào source
production. Không sửa frontend hoặc schema DB cho integration này.

## Architecture sau thay đổi

```text
FE → FastAPI → evidence từ retrieval/approved package
             → ModelServiceClient → RunPod /medical/evaluate
             → persist MedicalEvaluation
             → lịch sử học viên đã chụp trong snapshot
             → ModelServiceClient → RunPod /teaching/feedback
             → persist TeachingFeedback → FE
```

Provider `runpod` lưu execution_mode `http` theo constraint hiện có, đồng thời
ghi provider identity `runpod` vào metadata. Legacy provider `http` và mock vẫn
còn để giữ tương thích; lỗi runpod không tự chuyển mock. Teaching không nhận
evidence/rubric, không tạo điểm. Reload không gọi model, retry Teaching giữ nguyên
Medical và context. Không ghi mastery/learning_results từ các kiểm tra này.

## Config và lệnh chạy

`.env` web duy nhất: `C:\WORKS\STUDY\MedResident-Tutor\.env`.

```dotenv
MODEL_SERVICE_BASE_URL=https://example-8000.proxy.runpod.net
MODEL_SERVICE_API_KEY=<KEY_SERVICE_DO_NGUOI_DUNG_DIEN>
MODEL_SERVICE_CONNECT_TIMEOUT_SECONDS=10
MODEL_SERVICE_READ_TIMEOUT_SECONDS=120
```

Backend đã được recreate và kiểm tra lại: provider **mock**, model calls **false**,
authoring **off**, key mới đã vào container; backend health và trang login đều 200.
Chưa tự bật runpod khi service thực tế còn thiếu Teaching.

```powershell
# Repo gốc, Docker Desktop đang chạy.
docker compose -f docker-compose.yml -f docker-compose.authoring.yml up -d --no-deps --force-recreate backend
docker compose exec backend python -m app.ai.check_model_service
```

Trên Pod sau khi chuyển code mới lên, cài dependencies và export env/hash đã xác minh:

```bash
cd /root/MedResident-Tutor
bash services/medical/start-runpod.sh
```

Lệnh đầy đủ provision env/venv, các đường dẫn base/adapter, bốn endpoint, hai ví dụ
curl Medical/Teaching và builder lấy đúng Medical response đều ở
[hướng dẫn unified](unified-model-service.md). Service dùng
`medical_service.unified:app`, port 8000, workers 1. Script không tự tải models.

Chỉ sau khi service unified load cả hai, cả hai endpoint được kiểm tra, mới đặt
`PRACTICE_PROVIDER=runpod`, `MODEL_CALLS_ENABLED=true` và recreate backend.

## Verification

- Backend unit/regression: **128 passed**; focused HTTP boundary **21 passed**
  nằm trong tập trên, đã chạy lại sau chỉnh import.
- Service CPU/fake runner/Torch stub: **60 passed**.
- PostgreSQL integration/regression: **53 passed** trong lượt tổng cuối
  (126,73s), gồm bài mới và 52 regression. Tổng ba bộ: **241 passed**.
- Ruff pass; bash syntax pass; hai JSON ví dụ được validator chính thức chấp nhận,
  builder giữ nguyên MedicalEvaluation của phản hồi thật.
- **52 protected files** của Medical/Teaching source và adapter được so SHA-256:
  không đổi. Không retrain, không download/load model trên local, không chạy
  locked evaluation datasets, không chỉnh prompt/generation đã khóa.
- Đối chiếu count + hash nội dung toàn bộ bảng PostgreSQL web trước/sau các lượt
  kiểm tra: không đổi. Tests chỉ dùng DB riêng `medresident_test_model_service_20261117`.
- Kiểm tra các file Git có thể theo dõi: không chứa key thật hoặc Pod URL tạm;
  `.env` được ignore. Secret không in vào terminal/log/report.

Log/JUnit và phản hồi probe đã che secret nằm trong
`data/authoring/unified-model-service-20261117/` (ignored). Source changes hiện ở
working tree local, chưa commit/push trong task này.

## Phần cần kiểm chứng trên Pod

1. Deploy code mới, thay lệnh bootstrap riêng nếu đang chạy entrypoint Medical-only.
   Không thể cập nhật tiến trình Pod chỉ bằng HTTP inference API hiện có.
2. Provision đúng Teaching V1 và các hash; kiểm tra nạp cả hai model trên GPU thật.
3. Test Teaching và một lượt web đầy đủ sau khi bật provider mới. Kiểm tra chất
   lượng JSON, mức dùng VRAM và thời gian thực tế; tests offline không chứng minh
   chất lượng của hai model trên dữ liệu học viên.
4. RunPod HTTP proxy giới hạn Cloudflare 100 giây theo
   [tài liệu chính thức](https://docs.runpod.io/pods/configuration/expose-ports).
   Backend read timeout 120s không gỡ giới hạn đó. Chưa có job API/streaming; không
   tự retry khi proxy timeout trong lúc GPU vẫn chạy.

Learner context hiện chỉ có lịch sử số đếm, chưa suy luận mastery. Retrieval strategy
và phạm vi nguồn giữ nguyên cấu hình hiện có; chưa tự bật hybrid/Neo4j cho mọi câu.
