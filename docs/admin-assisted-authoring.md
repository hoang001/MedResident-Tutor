# Admin nhập câu hỏi, AI đề xuất đáp án và tiêu chí

Luồng trên `/admin/questions`:

1. Chọn **Tạo câu hỏi mới**. Bấm ô **Học phần** để mở danh sách từ curriculum trong KG; gõ tên có/không dấu hoặc mã môn để lọc. Các học phần chuyên ngành được ưu tiên trước; vẫn có thể nhập nhãn khác.
2. Nhập nội dung câu hỏi. Chủ đề là tùy chọn; tên bộ tiêu chí và điểm tối đa có giá trị mặc định, có thể sửa trước khi tạo đề xuất.
3. Bấm **Tìm nguồn và đề xuất đáp án**. Backend tìm căn cứ qua KG và sách bằng luồng hybrid hiện có, rồi gọi tác vụ authoring. KG không có liên kết phù hợp sẽ có lý do fallback trong trace; hệ thống không tự giả lập KG đã đóng góp.
4. Đáp án, tiêu chí và liên kết nguồn được điền vào form. Mở các đoạn nguồn để đối chiếu; chỉnh trực tiếp đáp án/tiêu chí nếu cần. Đề xuất chưa tạo câu hỏi hay ghi nguồn mới vào PostgreSQL.
5. Tích xác nhận đã đối chiếu, bấm **Duyệt và lưu nháp**. Lúc này mới đồng bộ các đoạn nguồn được dùng và lưu câu hỏi. Backend yêu cầu `proposal_reviewed=true` nếu có proposal token và ghi nhận admin đã duyệt bản đề xuất.
6. **Phát hành câu hỏi** là bước riêng sau lưu. Lịch sử phiên bản cũ được giữ; phát hành trong ứng dụng không xác nhận chuyên gia y khoa phê duyệt.

Đổi câu hỏi/học phần/chủ đề/tổng điểm sau khi AI tạo đề xuất yêu cầu tìm và đề xuất lại. Sửa đáp án/tiêu chí làm bỏ xác nhận duyệt cũ; admin xác nhận lại sau chỉnh sửa. Lỗi model giữ nội dung đang soạn và không tự retry, tự lưu hoặc tự phát hành.

## Serving cùng RunPod

`POST /authoring/propose` dùng cùng process, API key, port 8000 và GPU lock với Medical/Teaching. Authoring tái sử dụng base Qwen3 đã nạp, tạm tắt Medical LoRA bằng context manager và khôi phục adapter khi kết thúc hoặc lỗi. Không nạp model thứ ba hay tạo service/port khác. Cơ chế chạy base inference với `disable_adapter()` được mô tả trong [PEFT documentation](https://huggingface.co/docs/peft/package_reference/peft_model#peft.PeftModel.disable_adapter).

Prompt và contract authoring-v1 được chuyển nguyên nội dung sang `services/medical/medical_service/authoring_contract.py` để backend và service import cùng nguồn. Medical/Teaching prompts, training, adapters và locked evaluation sets được giữ nguyên.

Đầu vào serving: `version`, `system`, `scope`, `evidence`. Chỉ nhận đúng authoring-v1 prompt/contract; yêu cầu 1–3 nguồn, không trùng ID, tối đa 6.000 ký tự evidence, kiểm tra token/context. Đầu ra là `proposal`, `model_metadata`, `timing`; proposal phải qua strict JSON/schema, tham chiếu source IDs và tổng điểm. Không trả raw generation khi lỗi. Các kiểm tra kỹ thuật không đảm bảo nội dung lâm sàng đúng; bước admin đối chiếu nguồn vẫn cần thiết.

## Cấu hình

Sau khi deploy bản service có `/authoring/propose`, cấu hình `.env` gốc:

```dotenv
AUTHORING_PROVIDER=runpod
MODEL_CALLS_ENABLED=true
RUNPOD_POD_ID=<POD_ID_HIEN_TAI>
MODEL_SERVICE_BASE_URL=
MODEL_SERVICE_API_KEY=<KEY_CHUNG_CUA_SERVICE>
```

Không cần điền thêm authoring API key hoặc model alias cho provider `runpod`. URL được ghép bằng Pod ID hoặc origin override giống Medical/Teaching. Không tự dùng URL/key authoring hay LLM cũ làm fallback. Request authoring không giới hạn read timeout; connection/write/pool vẫn có giới hạn. Không retry tự động.

Áp dụng `.env` bằng recreate backend từ thư mục repo, mỗi lệnh một dòng:

```powershell
docker compose -f docker-compose.yml -f docker-compose.authoring.yml up -d --no-deps --force-recreate backend
```

Khởi động service trên Pod bằng script hiện có (cần key đã nạp an toàn):

```bash
cd /root/MedResident-Tutor && bash scripts/runpod/start_model_service.sh
```

## Kiểm thử

- CPU service: contract, auth, không lộ raw output/key, shared GPU lock và khôi phục Medical adapter khi authoring thành công/lỗi; không dùng GPU trong unit tests.
- Backend: shared client, proposal scope, explicit review, lưu phiên bản/approved package.
- PostgreSQL riêng cho test: từ chối lưu AI proposal chưa xác nhận, không tạo câu hỏi khi bị từ chối, lưu bản admin đã sửa và danh tính admin sau xác nhận; không tự phát hành.
- Browser suite `authoring-assisted`: autocomplete, keyboard/mobile, preview không lưu, chỉnh sửa làm bỏ xác nhận, duyệt/lưu với source mapping và giữ bản đang soạn khi lỗi. Suite này dùng response tổng hợp; không được coi là bằng chứng model live.
- Kiểm tra thật và ảnh ở `data/authoring/admin-assisted-20261118/` (ignored). Trạng thái deploy và kết quả inference thật được báo riêng sau khi thực hiện.
