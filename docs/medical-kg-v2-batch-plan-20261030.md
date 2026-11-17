# Kế hoạch chạy theo batch sau thử nghiệm trật khớp vai

Chưa chạy toàn sách. Kết quả và các blocker được ghi trong [báo cáo đợt thử](medical-kg-v2-shoulder-trial-20261030.md). Pipeline hiện đủ để chạy các batch kiểm chứng nhỏ; chưa đủ để gọi toàn bộ output là KG hoàn chỉnh.

## Điều kiện trước khi chạy rộng

1. Sửa các lỗi validator đã tái hiện: verb “Vận dụng”, dòng heading có nội dung thật, biên câu của qualifier guard. Phân biệt alias do model ghép với cặp tên có thật trong nguồn. Thêm chặn content chỉ là tên dù block không được đánh dấu heading.
2. Kiểm soát mất nội dung ở cấp mục: yêu cầu output incomplete khi thiếu chỉ định/chống chỉ định/câu theo dõi, không chỉ khi JSON bị cắt. Đợt này nhiều nội dung bị bỏ dù không cửa sổ nào chạm 12 node/16 cạnh.
3. Kiểm riêng hướng MANAGED_BY và EVALUATED_BY; không chữa cạnh bằng đảo chiều vô điều kiện. Không tạo Skill thực hành chỉ vì nguồn mô tả tư thế/thao tác.
4. Bổ sung audit transport có error type gốc và latency cho từng lần thất bại, không ghi credential/body nhạy cảm. Giữ checkpoint thành công; kiểm tra cấu hình timeout và tình trạng endpoint trước đợt mới. Hai lỗi LLMError hiện không đủ dữ liệu để khẳng định timeout.
5. Chạy lại hai cửa sổ chưa có raw, đặc biệt nhóm 5 câu hỏi thật; chưa có kết luận thực nghiệm SampleQuestion của đợt này.
6. Thiết kế resolver/staging xuyên batch. Không để registry gate che số lượng extraction, không bulk-approve candidate. Chưa phải thay registry y khoa bằng LLM confidence tự khai.

Các lỗi cục bộ có thể đưa vào hàng chờ: số bước Kocher mâu thuẫn OCR/PDF tại PDF92, ảnh/bảng chưa đọc được và các heading OCR hỏng. Các mục độc lập khác có thể chạy khi đã đánh dấu rõ phạm vi loại trừ, thay vì đợi sửa sạch toàn sách. Embedding tìm ứng viên, giao diện duyệt identity và tối ưu concurrency là cải tiến sau; không phải điều kiện để chạy batch nhỏ an toàn.

## Chia mục và kiểm soát sức chứa

- Bắt đầu từ mục lục được đối chiếu PDF; OCR hiện có 169 và 532 trang. Bộ dò `Bài <số>` thấy 31 marker trong sách 2021, không phải bằng chứng rằng có đúng 31 chương. Sách 2006 cần bộ dò tiêu đề/mục lục riêng.
- Mỗi scope shard tối đa 6 cửa sổ, mỗi sách tối đa 20 trang được chọn theo guard của `prepare`; CLI hiện không có lệnh full-corpus. Mặc định concurrency 1. Mỗi request timeout ≤60 giây, shard tổng budget ≤360 giây, attempts 1.
- Chia một cửa sổ theo mục có nghĩa: định nghĩa; dấu hiệu/chẩn đoán; chỉ định và chống chỉ định; quy trình và theo dõi; mục tiêu; câu hỏi. Không cắt bullet có điều kiện/ngoại lệ khỏi câu cha. Đoạn qua trang chỉ nối sau khi kiểm mục tiếp tục và ranh giới mục mới.
- Context heading và định nghĩa dùng làm tham chiếu; tránh yêu cầu model trích lại mọi subtype trong mọi cửa sổ. Giữ reference tới concept ứng viên, nhưng chưa tự merge chỉ theo tên.
- Giữ trọn câu hỏi, case, options và câu con trong một nhóm atomic; nếu vượt byte guard thì đưa vào queue riêng, không truncate hay chia mất ngữ cảnh. Answer chỉ lấy ở phần đáp án thật.
- Giữ nguyên giới hạn 12 node/16 cạnh trong phép đo hiện tại. Sau này nếu raw chạm một trong hai giới hạn hoặc finish_reason=length, đánh dấu incomplete. Kể cả không chạm giới hạn, đối chiếu checklist nội dung: thiếu ý thì tách lại mục với context có kiểm soát. Cửa sổ tiếp nối phải có phạm vi/bullet chưa xử lý cụ thể, không dùng lời nhắc chung “viết tiếp”.
- Mỗi prompt/schema/input mới có fingerprint mới và run/output mới. Không ghép raw từ hai cấu hình thành một run. Ngân sách retry được tính ngoài cache, ghi vào ledger tổng cho cả đợt; guard hiện tại là theo mỗi invocation, không phải quota chung của mọi lần gọi CLI.

## Checkpoint, lỗi và tổng hợp

Mỗi shard có scope manifest, checklist nguồn lập trước generate, prompt/schema/taxonomy snapshot, input hash và checkpoint. Resume cùng scope/code/model/config để dùng lại phần thành công. Plain `--resume` sẽ gọi lại cửa sổ đã thất bại; phải tính những request đó vào ngân sách đợt mới.

Lưu `failed-batches.json` gồm scope/window ID, loại lỗi gốc đã che bí mật, latency, request count, hash cấu hình và lý do chạy lại. Lỗi OCR/nguồn vào queue nguồn; schema/capacity vào queue chia lại; lỗi transport vào queue dịch vụ. Không retry liên tục và không thay prompt ngay trong batch đang chạy.

Hợp nhất graph staging theo candidate ID trùng hoàn toàn trước; semantic duplicate vẫn là proposal. Khi dùng cùng canonical UUID, gộp content theo nguồn/locator, không overwrite content sách trước; giữ riêng các phát biểu khác phiên bản/điều kiện. Edge remap giữ toàn bộ nguồn và điều kiện, không gộp theo mỗi triple. Registry update cần cơ chế ghi tuần tự và kiểm xung đột; không cấp ID mới theo tên ở mỗi batch. LLM resolver có thể đề xuất same/different/broader/uncertain với chứng cứ, rule gate kiểm scope/type, chỉ trường hợp rõ mới được tự chấp nhận sau đánh giá resolver riêng.

Chạy schema, locator/raw trace, unique ID/reference, domain/range, chu trình, overlap duplicates, canonical remap và loader JSON round-trip trên từng shard và graph tổng. Staging và canonical có thống kê riêng. Không tự import Neo4j.

## Ước lượng từ dữ liệu thật

Xem `data/knowledge-extraction/v2/shoulder-20261030/audit/batch-inventory.json`. Sáu cửa sổ thử có 929–2.221 byte nội dung, trung vị 1.363,5 byte, chưa tính metadata/prompt/schema. OCR toàn bộ có 303.338 byte cho sách 2006 và 1.158.504 byte cho sách 2021.

| Sách | Request thấp | Trung tâm | Cao |
|---|---:|---:|---:|
| 2006 | 91 | 222 | 435 |
| 2021 | 348 | 850 | 1.663 |
| Tổng | 439 | 1.072 | 2.098 |

Đây chỉ là ngoại suy dung lượng: thấp dùng cửa sổ lớn nhất ×1,5; cao dùng cửa sổ nhỏ nhất ×0,75. Sai số rất lớn vì OCR còn trang đầu, tài liệu tham khảo, mô tả ảnh và bảng; chia theo ý có thể tăng request, lọc nhiễu có thể giảm. Chưa có scope shard đầy đủ đã xác minh nên đây không phải dự toán cam kết.

Bốn response thành công mất trung bình 25,889 giây. 1.072 request ở tốc độ đó tương đương khoảng 7,7 giờ gọi model tuần tự, **chưa tính lỗi, retry, kiểm nguồn và identity**. Khoảng 439–2.098 request với cùng trung bình là khoảng 3,2–15,1 giờ; nếu mỗi request chạm timeout cấu hình 60 giây thì khoảng 7,3–35 giờ trước retry. Mẫu 6 request có 2 lỗi nên không đủ để ước lượng độ ổn định dịch vụ. Không ước lượng tiền khi chưa có đơn giá; 4 response đã trả 34.637 token, usage hai request lỗi không có.

## Lệnh đã kiểm tra theo CLI thực tế

Lệnh tiếp theo không gọi mạng, xem payload hiện có:

```powershell
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
& $py -m knowledge_pipeline.kg_v2 loader-dry-run --output data/knowledge-extraction/v2/shoulder-20261030/staging
```

Đã chuẩn bị scope chỉ gồm hai cửa sổ thất bại; `prepare` nội bộ xác nhận đủ 2 cửa sổ, không rejection. Lệnh generate dưới đây dành cho **đợt request tiếp theo**, chưa thực thi, sau khi xử lý blocker và bố trí ngân sách mới:

```powershell
& $py -m knowledge_pipeline.kg_v2 prepare --scope knowledge_pipeline/kg_v2/shoulder-retry-scope-20261030.json --output data/knowledge-extraction/v2/shoulder-retry-next
& $py -m knowledge_pipeline.kg_v2 extract --scope knowledge_pipeline/kg_v2/shoulder-retry-scope-20261030.json --output data/knowledge-extraction/v2/shoulder-retry-next --max-calls 2 --timeout 60 --total-seconds 120
# Cùng cấu hình, nếu cần: chỉ gọi lại phần chưa có checkpoint, vẫn cần budget cho lỗi cũ.
& $py -m knowledge_pipeline.kg_v2 extract --scope knowledge_pipeline/kg_v2/shoulder-retry-scope-20261030.json --output data/knowledge-extraction/v2/shoulder-retry-next --max-calls 2 --timeout 60 --total-seconds 120 --resume
```

Để chạy toàn sách sau khi đã tạo và kiểm các shard thật, áp dụng cùng cú pháp trên từng scope, mỗi output riêng; không bỏ guard 6 cửa sổ. Chưa cung cấp một lệnh full-corpus giả vì CLI và scope toàn sách chưa sẵn sàng.
