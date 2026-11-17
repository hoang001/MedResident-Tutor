# Thử nghiệm mở rộng kg_v2 sang trật khớp vai — 30/10/2026

Đã gọi LLM thật, không chạy lại gãy xương hở. Kết luận: pipeline chạy được ở mức staging có audit, nhưng **chưa nên chạy toàn bộ hai sách với kỳ vọng giữ đủ kiến thức**. Các blocker quan sát được là lỗi dịch vụ chưa đủ diagnostics, mất chỉ định/chống chỉ định và câu theo dõi, validator loại nhầm nội dung, model đảo chiều quan hệ và nội dung chỉ là tên lọt qua validator. Đây là kiểm fidelity theo sách, không phải duyệt chuyên môn y khoa.

Đợt này có 6 request mới, 4 raw JSON hợp lệ và 2 lỗi không có HTTP response. Staging có 14 node/4 cạnh; graph canonical có 0/0 vì chưa resolve identity. Không bulk-approve hay sửa registry để làm đẹp kết quả. Đã xuất staging đầy đủ, riêng từng sách và toàn đợt.

## A. Trạng thái, phạm vi và cấu hình đã khóa

Đã đọc CLI, taxonomy/schema, context/validation/registry, các báo cáo gần nhất và cấu hình qua `Settings.from_env`. Không tìm thấy AGENTS.md áp dụng trong repo và các thư mục cha đã kiểm. Không sửa hoặc chạy locked Medical/Teaching test, không lấy dữ liệu locked test làm input. Topic mới được chọn trực tiếp từ mục lục/OCR hai sách.

Mốc cũ `context-delivery-20261029` có 14 node/13 cạnh và **đã import Neo4j**, theo `audit/neo4j-import-report.json` và trao đổi trước đó; không mặc định thông tin “chưa import” trong yêu cầu là trạng thái mới nhất. Đợt này không kết nối/đọc/ghi Neo4j.

Nguồn OCR là hai file có sẵn trong `data/graduate/`; PDF là `data/raw-source/data-20261020T074653Z-1-001/data/Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi.pdf` và `data/raw-source/DVC.005844.pdf`. Hash PDF/OCR được xác minh bằng adapter hiện có. Không OCR lại.

Endpoint `http://10.8.0.1:4000/v1/chat/completions`, model `vtllm/gemma-4-26b`, file cấu hình `.env` gốc. Code đọc file trực tiếp, không lấy key terminal làm fallback. Không ghi/in secret. Attempts 1, concurrency 1, max 6 request, timeout cấu hình 60 giây/request, tổng budget cấu hình 360 giây, max output 8.192 token, prompt byte guard 70.000. Prompt/taxonomy/schema giữ nguyên suốt đợt.

Trước generate chỉ bổ sung telemetry HTTP/token usage, cache-hit counter và cảnh báo raw chạm 12 node/16 cạnh vào pipeline; thêm test tương ứng. Không thay prompt hay schema để thích nghi với kết quả. `pre-generation-lock.json` ghi hash code/prompt/schema/scope trước request đầu; `manifest.json` có fingerprint đầy đủ. `source-checklist-before-generation.json` có 37 ý, được ghi trước khi xem output LLM.

Sách 2006: `SRC_ORTHO_EMERGENCY_001`; sách 2021: `SRC_ORTHO_TEXTBOOK_001`. Trang in chỉ điền cho 8 trang thực sự đã xem ảnh, không áp dụng offset suy đoán cho toàn sách. Mở rộng context: PDF89/254 cho heading và nhận diện chủ đề, PDF91 heading điều trị trước PDF92. Phần điều trị 2021 nối PDF262→263 sau khi kiểm ảnh. Không chọn cả chương; không lấy lưu đồ ảnh tại PDF262, mô tả ảnh AI hoặc tài liệu tham khảo vào input.


| Cửa sổ | Sách | Mục | PDF / trang in đã kiểm | Mục đích |
| --- | --- | --- | --- | --- |
| 2006-diagnosis | 2006 | 5. Chẩn đoán trật khớp vai | 89/88, 91/90 | Clinical findings and X-ray across three directions; preserve posterior false-negative warning. |
| 2006-treatment | 2006 | 7.1. Điều trị trật khớp vai mới | 89/88, 91/90, 92/91 | Reduction and immobilization with exceptions; hold Kocher numbering discrepancy, not repair it. |
| 2021-objectives | 2021 | Bài 19 / Mục tiêu và đại cương | 254/271 | Shared shoulder concept with separate source content; retain all three cognitive objectives. |
| 2021-apprehension | 2021 | 2.3.2. Nghiệm pháp e sợ | 254/271, 259/276 | DiagnosticMethod, indication, patient/examiner position and stopping criterion; do not infer practical Skill. |
| 2021-conservative | 2021 | 5.2. Điều trị bảo tồn | 254/271, 262/279, 263/280 | Verified cross-page indications, contraindications and post-reduction monitoring. Preserve contradictory timing statements as written. |
| 2021-questions | 2021 | Câu hỏi lượng giá Bài 19 | 254/271, 269/286 | Five real open-ended questions, no printed answer; assess completeness, ABOUT and ASSESSES if source supports. |


Tổng: 8 trang PDF chọn đọc/đối chiếu, 64 lượt block trong 6 cửa sổ, 50 block cấu trúc duy nhất; 37 block/ý được chọn làm checklist (35 block nguồn, trong đó định nghĩa được tách thành 3 ý). Chỉ đếm trang được chọn làm nguồn, không coi metadata/hash toàn file là đọc toàn bộ sách vào model.

## B. Kết quả extraction theo sách


| Chỉ số | 2006 | 2021 | Toàn đợt |
| --- | --- | --- | --- |
| Trang / window / block lượt (duy nhất) | 3 / 2 / 24 (22) | 5 / 4 / 40 (28) | 8 / 6 / 64 (50) |
| Request thật / JSON hợp lệ / lỗi | 2 / 1 / 1 | 4 / 3 / 1 | 6 / 4 / 2 |
| Raw node / edge occurrences | 7 / 7 | 23 / 19 | 30 / 26 |
| Candidate staging unique node / edge | 5 / 0 | 9 / 4 | 14 / 4 |
| Bị loại node / edge occurrences | 2 / 7 | 12 / 15 | 14 / 22 |
| Canonical node / edge | 0 / 0 | 0 / 0 | 0 / 0 |
| Chỉ bị identity gate giữ node / edge | 5 / 0 | 9 / 4 | 14 / 4 |
| Ý nguồn giữ đầy đủ / đã kiểm | 2 / 14 | 5 / 23 | 7 / 37 |
| Câu hỏi đầy đủ / trong phạm vi | 0 / 0 (không có) | 0 / 5 | 0 / 5 |



Raw occurrence và node unique khác nhau: 16 node occurrence qua validator được dedupe chính xác thành 14 candidate. Hai occurrence overlap đã được gộp theo cùng ID; vẫn còn một cặp định nghĩa tái diễn khác biên quote chưa resolve. Không có semantic merge tự động.


| Node type | Raw 2006 | Raw 2021 | Staging 2006 | Staging 2021 |
| --- | --- | --- | --- | --- |
| Condition | 4 | 12 | 4 | 3 |
| Finding | 0 | 1 | 0 | 0 |
| DiagnosticMethod | 0 | 1 | 0 | 0 |
| Intervention | 3 | 4 | 1 | 3 |
| Skill | 0 | 5 | 0 | 3 |
| SampleQuestion | 0 | 0 | 0 | 0 |


| Edge type | Raw 2006 | Raw 2021 | Staging 2006 | Staging 2021 |
| --- | --- | --- | --- | --- |
| IS_A | 3 | 9 | 0 | 2 |
| MANAGED_BY | 3 | 4 | 0 | 0 |
| APPLIES_TO | 1 | 5 | 0 | 2 |
| EVALUATED_BY | 0 | 1 | 0 | 0 |



HTTP/token theo request; các hàng lỗi không có status hoặc latency được trả/ghi đủ, không gán HTTP 0 hay tự kết luận timeout:


| Window | HTTP | Latency giây | Prompt / completion / total token | Kết quả |
| --- | --- | --- | --- | --- |
| 2006-diagnosis | không có response | không được ghi | không có | LLMError; raw không có |
| 2006-treatment | 200 | 31.021 | 6236 / 2919 / 9155 | stop; schema passed |
| 2021-objectives | 200 | 27.178 | 4430 / 4288 / 8718 | stop; schema passed |
| 2021-apprehension | 200 | 32.172 | 4014 / 2870 / 6884 | stop; schema passed |
| 2021-conservative | 200 | 13.185 | 7676 / 2204 / 9880 | stop; schema passed |
| 2021-questions | không có response | không được ghi | không có | LLMError; raw không có |


Bốn response HTTP 200 có tổng 103,556 giây; 22.356 prompt + 12.281 completion = 34.637 token. Hai lần lỗi không có usage. Cache hit lượt đầu 0, retry 0; không gọi checker LLM. Chưa có đơn giá xác nhận nên chi phí để null. Không đủ diagnostics để phân biệt ReadTimeout, ConnectError hay lỗi transport khác ở hai request; **số timeout xác nhận là chưa biết**, không phải đã xác nhận 0. Prompt của cả sáu request đều dưới byte guard (14.289–22.404 byte), nên không phải bị chặn bởi giới hạn prompt này.

## C. Toàn bộ candidate node được xuất staging

Không thêm status/confidence/model vào node. UUID canonical chưa cấp; các ID dưới đây là candidate, không được gọi là canonical. 14/14 node có quote khớp nguồn và type phù hợp ở mức định danh. Điều đó không bảo đảm đủ nội dung: 9/14 có nội dung thực chất, 3/14 chỉ có danh sách nhắc tới, 2/14 chỉ có tên phương pháp và chưa đạt yêu cầu nội dung. Nội dung Nắn trật còn thiếu câu kiểm tra sau nắn. Các vấn đề này nằm trong audit, không sửa graph bằng tay.


| ID | Type | Name | Nguồn / locator | Đối chiếu |
| --- | --- | --- | --- | --- |
| CAND2_20764ea7355bed995019d75d | Condition | Trật khớp vai | 2006 PDF89 / LOC2_ff298974ae7724562f9e7743 | Content and type consistent with the cited book; this is source fidelity, not clinical expert approval. |
| CAND2_2ea1ec233383640da2b1123c | Intervention | Phương pháp Hypocrat | 2006 PDF92 / LOC2_7d3513bb453b02c3632e2991 | Content and type consistent with the cited book; this is source fidelity, not clinical expert approval. |
| CAND2_39d742b8bdcbcd070295d80c | Condition | Trật khớp vai tái diễn | 2021 PDF254 / LOC2_2027448a1a99f70948e24723 | Same recurrent-shoulder definition has two candidate identities because quote boundaries differ. Merge proposal only; no registry mutation. |
| CAND2_54632b1e2dae7c6232b1fb6e | Condition | Trật khớp vai | 2021 PDF254 / LOC2_a0d401aa3828ad5cdd8adc11 | Content and type consistent with the cited book; this is source fidelity, not clinical expert approval. |
| CAND2_5a082c611d29cdb6ffe28348 | Skill | Minh họa các bước cơ bản của phẫu thuật Latarjet | 2021 PDF254 / LOC2_937e86af9deb5bd2d6835f3f | Content and type consistent with the cited book; this is source fidelity, not clinical expert approval. |
| CAND2_6494a47648397aa491351bf8 | Intervention | Phẫu thuật Bankart | 2021 PDF254 / LOC2_4f9e3f4ad38b48993814cc2e | Content is just the intervention name in an objective. Fails substantive-content fidelity despite passing the current heading-only validator. |
| CAND2_68533c638eb40b474d866375 | Condition | Trật khớp vai cũ | 2006 PDF89 / LOC2_d4eee1b5c768d5369b37c153 | Only an enumeration establishes existence; no separate definition, diagnostic criteria or treatment. Thin content, not a false medical assertion. |
| CAND2_70bb4c7adefa938af367320a | Skill | Minh họa các bước cơ bản của phẫu thuật Bankart | 2021 PDF254 / LOC2_937e86af9deb5bd2d6835f3f | Content and type consistent with the cited book; this is source fidelity, not clinical expert approval. |
| CAND2_719af0fbee84379d751dfe0a | Intervention | Nắn trật | 2021 PDF263 / LOC2_75feb240b557406c98336fee | Quotes anesthesia and gentle reduction but omits the next independent sentence requiring post-reduction stability checking, and all indication/contraindication bullets. |
| CAND2_c10a0c900613c0f5aaa751bf | Condition | Trật khớp vai tái diễn | 2021 PDF254 / LOC2_fed9e81e48c965731493ecfd | Same recurrent-shoulder definition has two candidate identities because quote boundaries differ. Merge proposal only; no registry mutation. |
| CAND2_c8bbf7c0d37ddc10fde4cf2c | Condition | Trật khớp vai mới | 2006 PDF89 / LOC2_d4eee1b5c768d5369b37c153 | Only an enumeration establishes existence; no separate definition, diagnostic criteria or treatment. Thin content, not a false medical assertion. |
| CAND2_ca81dbeb736cef2dfc886fb8 | Condition | Trật khớp vai tái diễn | 2006 PDF89 / LOC2_d4eee1b5c768d5369b37c153 | Only an enumeration establishes existence; no separate definition, diagnostic criteria or treatment. Thin content, not a false medical assertion. |
| CAND2_d37b461f60fd7b84769788a3 | Skill | Phân tích cơ chế, đặc điểm tổn thương giải phẫu trong trật khớp vai | 2021 PDF254 / LOC2_652d3edf82672e4608c4e6f4 | Content and type consistent with the cited book; this is source fidelity, not clinical expert approval. |
| CAND2_fc56309649c0baf3cd0f56b3 | Intervention | Phẫu thuật Latarjet | 2021 PDF254 / LOC2_a828d04e5e9429c1a77e70f1 | Content is just the intervention name in an objective. Fails substantive-content fidelity despite passing the current heading-only validator. |


## D. Toàn bộ cạnh staging và kiểm tra raw

Cả 4/4 cạnh staging có hướng/type và nguồn hỗ trợ; 2 cạnh IS_A là cùng một ý tái diễn với hai candidate/biên quote, không phải hai tri thức độc lập. Hai APPLIES_TO có nguồn là mục tiêu Minh họa, không chứng nhận kỹ năng phẫu thuật thực hành. Target Intervention của chúng vẫn có content quá mỏng như mục C.


| ID | Từ | Loại | Đến | Condition | Bằng chứng ngắn / locator |
| --- | --- | --- | --- | --- | --- |
| KG2E_3e849b0a70cac327d86a24fd | Trật khớp vai tái diễn | IS_A | Trật khớp vai | None | Về tần suất có trật khớp vai tái diễn, là tình trạng trật khớp vai cùng bên từ lần 2 … / LOC2_fed9e81e48c965731493ecfd |
| KG2E_7142da01fb474045f8a07263 | Minh họa các bước cơ bản của phẫu thuật Latarjet | APPLIES_TO | Phẫu thuật Latarjet | None | Minh họa được các bước cơ bản của phẫu thuật Bankart và phẫu thuật Latarjet trong điề… / LOC2_937e86af9deb5bd2d6835f3f |
| KG2E_85e5653e6b33edbe1fcd3f81 | Trật khớp vai tái diễn | IS_A | Trật khớp vai | None | Trật khớp vai là tình trạng mất tiếp xúc của diện khớp ổ chảo và chỏm xương cánh tay.… / LOC2_a0d401aa3828ad5cdd8adc11 |
| KG2E_908d387c89e358e9f9f9ce1e | Minh họa các bước cơ bản của phẫu thuật Bankart | APPLIES_TO | Phẫu thuật Bankart | None | Minh họa được các bước cơ bản của phẫu thuật Bankart và phẫu thuật Latarjet trong điề… / LOC2_937e86af9deb5bd2d6835f3f |



Đã đối chiếu cả 26 raw edge occurrence, không chỉ 4 cạnh sống sót: 16/26 có quan hệ phù hợp nguồn về type/hướng; 9/26 sai domain/range hoặc hướng, 1/26 dựa vào Skill thực hành không có yêu cầu nguồn rõ. Một số cạnh có ý nguồn hợp lệ vẫn bị loại dây chuyền vì endpoint bị chặn. Đây không phải tỷ lệ chính xác toàn hệ thống: chỉ là 26 đề xuất thực sự có raw của mẫu nhỏ, không gồm hai cửa sổ thất bại. Chi tiết `raw-fidelity-review.json` liệt kê toàn bộ 30 raw node và 26 raw edge; `rejected.json` giữ nguyên candidate bị loại.


| Window | Raw edge | Từ | Loại | Đến | Đối chiếu nguồn |
| --- | --- | --- | --- | --- | --- |
| 2021-apprehension | edge_1 | Trật khớp vai sớm | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-apprehension | edge_2 | Trật khớp vai muộn | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-apprehension | edge_3 | Trật khớp vai tái diễn | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-apprehension | edge_4 | Nghiệm pháp e sợ | EVALUATED_BY | Mất vững phía trước khớp vai | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2021-apprehension | edge_5 | Thực hiện nghiệm pháp e sợ | APPLIES_TO | Nghiệm pháp e sợ | Source describes test position but does not explicitly require a practical skill. |
| 2021-objectives | edge_1 | Trật khớp vai sớm | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-objectives | edge_2 | Trật khớp vai muộn | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-objectives | edge_3 | Trật khớp vai tái diễn | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-objectives | edge_4 | Phân tích cơ chế, đặc điểm tổn thương giải phẫu trong trật khớp vai | APPLIES_TO | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-objectives | edge_5 | Vận dụng nguyên tắc điều trị trật khớp vai | APPLIES_TO | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-objectives | edge_6 | Minh họa các bước cơ bản của phẫu thuật Bankart | APPLIES_TO | Phẫu thuật Bankart | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-objectives | edge_7 | Minh họa các bước cơ bản của phẫu thuật Latarjet | APPLIES_TO | Phẫu thuật Latarjet | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-objectives | edge_8 | Phẫu thuật Bankart | MANAGED_BY | Trật khớp vai tái diễn | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2021-objectives | edge_9 | Phẫu thuật Latarjet | MANAGED_BY | Trật khớp vai tái diễn | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2006-treatment | edge_1 | Trật khớp vai mới | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2006-treatment | edge_2 | Trật khớp vai cũ | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2006-treatment | edge_3 | Trật khớp vai tái diễn | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2006-treatment | edge_4 | Phương pháp Hypocrat | MANAGED_BY | Trật khớp vai | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2006-treatment | edge_5 | Phương pháp Kocher | MANAGED_BY | Trật khớp vai | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2006-treatment | edge_6 | Bất động bằng băng Desault | MANAGED_BY | Trật khớp vai | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2006-treatment | edge_7 | Phương pháp Kocher | APPLIES_TO | Trật khớp vai tái diễn | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2021-conservative | edge_1 | Trật khớp vai sớm | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-conservative | edge_2 | Trật khớp vai muộn | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-conservative | edge_3 | Trật khớp vai tái diễn | IS_A | Trật khớp vai | Hỗ trợ ý quan hệ; chưa đồng nghĩa export |
| 2021-conservative | edge_4 | Nắn trật | MANAGED_BY | Trật khớp vai | Wrong direction/endpoint types; not accepted as the proposed relation. |
| 2021-conservative | edge_5 | Bất động khớp vai | MANAGED_BY | Trật khớp vai | Wrong direction/endpoint types; not accepted as the proposed relation. |


## E. Độ phủ nội dung, điều kiện và câu hỏi

Checklist khóa trước generate có 37 ý: 7 giữ đầy đủ ở node; 11 không có raw do request thất bại; 5 giữ ngoài đánh giá tin cậy vì cấu trúc/số thứ tự Kocher; 5 bị chặn ở validation hoặc quan hệ cần thiết; 8 không được model đưa vào content/edge; 1 chỉ giữ một phần text. Status là nguyên nhân chính theo đối chiếu trace, có thể có nhiều yếu tố đồng thời. Các ý đã giữ staging vẫn bị identity gate giữ ngoài canonical, được ghi riêng trong audit. Không tính 14 candidate node như 14 ý nguồn đầy đủ.

Quan trọng: model bỏ toàn bộ nhóm chống chỉ định PDF263 và hầu hết chỉ định PDF262–263. Node Nắn trật lấy hai câu đầu nhưng bỏ “Sau nắn trật luôn kiểm tra lại độ vững của khớp vai” (PDF263, block `SBLOCK2_fe1789f1f5cee72b003006f5`). Đây là omission dù quote đã lấy không bị sửa. Các mốc <3 tuần/>3 tuần, từ lần 2 trở lên/thường >10 lần còn nguyên trong content định nghĩa đã giữ. Hai nội dung bất động có số tuần/tuổi bị validator chặn; không được tuyên bố số liệu của chúng đã được graph bảo toàn.

Không cập nhật chỉ dẫn sách bằng kiến thức ngoài: PDF262 ghi sau 24 giờ vẫn có thể nắn, PDF263 ghi >1 tuần không còn chỉ định nắn kín. Những câu này được giữ trong source checklist đúng nguồn, không tự hòa giải thành một guideline mới. Source scope không có đáp án; model không có output câu hỏi nên chưa kiểm được options/câu con/answer/explanation bằng LLM ở đợt này.


| Ý nguồn | PDF / in | Đoạn ngắn | Block / offset corrected | Kết quả |
| --- | --- | --- | --- | --- |
| SRC_CHECK_001 | 89/88 | Trật khớp vai hay gặp nhất ở người trẻ khoẻ, tuổi từ 20-40 tuổi, chiếm 60% tổn… | SBLOCK2_83d82dcb32d9421f1bb4f2aa [470:635] | Đã giữ trong node |
| SRC_CHECK_002 | 91/90 | Bệnh nhân đến khám, tay lành đỡ tay đau, nhìn thấy vai bên trật ngắn hơn, bờ v… | SBLOCK2_ac9a41d661f0baea47b1cddc [89:406] | Không có raw: request lỗi |
| SRC_CHECK_003 | 91/90 | Chụp X quang xem chỏm trật và xem có gãy bong mấu động lớn | SBLOCK2_b2b1678122918393cc0351bd [407:465] | Không có raw: request lỗi |
| SRC_CHECK_004 | 91/90 | Cánh tay quặt ngược lên trời, khuỷu gấp nhọn, bàn tay sờ đầu | SBLOCK2_0b7f2bd117c544bfefb22ae0 [496:556] | Không có raw: request lỗi |
| SRC_CHECK_005 | 91/90 | X quang: chỏm xương trật xuống dưới ổ chảo | SBLOCK2_0bfd1fb54fcb1ae0350b0a51 [557:599] | Không có raw: request lỗi |
| SRC_CHECK_006 | 91/90 | Cánh tay khép, cẳng tay như dán chặt, nằm ngang trước lồng ngực, cổ bàn tay ru… | SBLOCK2_9623c4936b6c3229f0a7ce23 [626:783] | Không có raw: request lỗi |
| SRC_CHECK_007 | 91/90 | X quang phim thẳng, đọc không kỹ dễ tưởng khớp vai bình thường. Phim nghiêng t… | SBLOCK2_a43dde6439a68905bb6aaec4 [784:892] | Không có raw: request lỗi |
| SRC_CHECK_008 | 92/91 | • Phương pháp Hypocrat: bệnh nhân nằm ngửa, người nắn ngồi bên cạnh, độn gót c… | SBLOCK2_00c1d7e82901dea5619cee28 [11:271] | Đã giữ trong node |
| SRC_CHECK_009 | 92/91 | • Phương pháp Kocher: (4 thì) không dùng cho nắn trật lần đầu, vì làm hỏng phầ… | SBLOCK2_2f3dc97f68abab110d7b1baa [272:454] | Giữ ngoài: OCR/cấu trúc nguồn |
| SRC_CHECK_010 | 92/91 | – Thì 1: khuỷu gấp 90° kéo thẳng cánh tay | SBLOCK2_7cb48d04b01bc9f84226688f [455:496] | Giữ ngoài: OCR/cấu trúc nguồn |
| SRC_CHECK_011 | 92/91 | – Thì 2: ép khuỷu vào thân | SBLOCK2_912a2870111fe1228db64074 [497:523] | Giữ ngoài: OCR/cấu trúc nguồn |
| SRC_CHECK_012 | 92/91 | – Thì 3: xoay cánh tay ra ngoài bằng cách đưa cẳng tay ra ngoài tối đa. | SBLOCK2_a130bee6180418fd05864f75 [524:595] | Giữ ngoài: OCR/cấu trúc nguồn |
| SRC_CHECK_013 | 92/91 | – Thì 4: đưa cánh tay lên trên và vào trong, bàn tay sờ được tai đối diện | SBLOCK2_c225debf67d3c85657bb0e1d [596:669] | Giữ ngoài: OCR/cấu trúc nguồn |
| SRC_CHECK_014 | 92/91 | 7.1.3. Bất động: bất động bằng băng Desault để 3-4 tuần. Bệnh nhân trên 40 tuổ… | SBLOCK2_a797d98c07c48c2de4e03b69 [670:802] | Bị chặn validation |
| SRC_CHECK_015 | 254/271 | Trật khớp vai là tình trạng mất tiếp xúc của diện khớp ổ chảo và chỏm xương cá… | SBLOCK2_ff1e2e6759b76e601d676249 [497:582] | Đã giữ trong node |
| SRC_CHECK_016 | 254/271 | Về thời gian có trật khớp vai sớm (cấp tính, < 3 tuần) và trật khớp vai muộn (… | SBLOCK2_ff1e2e6759b76e601d676249 [583:681] | Đã giữ trong node |
| SRC_CHECK_017 | 254/271 | Về tần suất có trật khớp vai tái diễn, là tình trạng trật khớp vai cùng bên từ… | SBLOCK2_ff1e2e6759b76e601d676249 [682:841] | Đã giữ trong node |
| SRC_CHECK_018 | 254/271 | 1. Phân tích được cơ chế, đặc điểm tổn thương giải phẫu trong trật khớp vai và… | SBLOCK2_dbd6b5693f002acc8518cea9 [79:218] | Đã giữ trong node |
| SRC_CHECK_019 | 254/271 | 2. Vận dụng được nguyên tắc điều trị trật khớp vai đối với các trường hợp trật… | SBLOCK2_2b3a21c53cb5670050b85164 [219:328] | Bị chặn validation |
| SRC_CHECK_020 | 254/271 | 3. Minh họa được các bước cơ bản của phẫu thuật Bankart và phẫu thuật Latarjet… | SBLOCK2_4ccf51aeeb9f793c8ef9c295 [329:446] | Đã giữ trong node |
| SRC_CHECK_021 | 259/276 | Đánh giá tình trạng mất vững phía trước của khớp vai. Bệnh nhân ngồi hoặc nằm … | SBLOCK2_b6230b8a620ea97942050bef [239:521] | Bị chặn validation |
| SRC_CHECK_022 | 262/279 | - Trật khớp vai mới (thời gian < 3 tuần): | SBLOCK2_897d777e60cbb86032745e06 [110:151] | Bỏ sót trong output model |
| SRC_CHECK_023 | 262/279 | + Trật khớp vai lần đầu, nắn trật cấp cứu càng sớm càng tốt. | SBLOCK2_409839423f5aabd43bce3dac [152:212] | Bị chặn validation |
| SRC_CHECK_024 | 262/279 | + Nắn trật sau 24 giờ vẫn có thể tuy nhiên khả năng thành công giảm và có nguy… | SBLOCK2_60dd185c256d32e2cb939999 [213:305] | Bỏ sót trong output model |
| SRC_CHECK_025 | 263/280 | + Trật > 1 tuần các gân cơ đã co rút nên không còn chỉ định nắn trật kín. | SBLOCK2_65c83fbe5937f2637ad3c1f6 [0:73] | Bỏ sót trong output model |
| SRC_CHECK_026 | 263/280 | - Trật vai tái diễn nhưng bệnh nhân chưa đủ điều kiện phẫu thuật hoặc đang tro… | SBLOCK2_6aebf79e3ca339a9d3bd4e78 [74:221] | Bỏ sót trong output model |
| SRC_CHECK_027 | 263/280 | - Trật khớp vai đơn thuần, không kèm gãy xương phải phẫu thuật. | SBLOCK2_420e93faa4267575179b40a0 [222:285] | Bỏ sót trong output model |
| SRC_CHECK_028 | 263/280 | - Nắn trật lần đầu thất bại. | SBLOCK2_2d535dcb37d5f3ff5dd4749d [308:336] | Bỏ sót trong output model |
| SRC_CHECK_029 | 263/280 | - Trật hở. | SBLOCK2_e3fef199e4345c3b4088be97 [337:347] | Bỏ sót trong output model |
| SRC_CHECK_030 | 263/280 | - Trật mạn tính với chức năng khớp vai kém và đau nhiều. | SBLOCK2_3fe6b926793a803fe5cd4b57 [348:404] | Bỏ sót trong output model |
| SRC_CHECK_031 | 263/280 | Nên lựa chọn vô cảm bằng gây mê hoặc gây tê ở khớp, kết hợp sử dụng thuốc giãn… | SBLOCK2_fe1789f1f5cee72b003006f5 [430:688] | Chỉ giữ một phần text |
| SRC_CHECK_032 | 263/280 | Thời gian bất động khớp vai sau nắn là từ 2-5 tuần, và có thể cân nhắc rút ngắ… | SBLOCK2_46b45c967fd37806442ade76 [689:1047] | Bị chặn validation |
| SRC_CHECK_033 | 269/286 | Câu 1. Trình bày đặc điểm giải phẫu các hệ thống giữ khớp vai? | SBLOCK2_cc1ec47712cddf7e24091e5b [1571:1633] | Không có raw: request lỗi |
| SRC_CHECK_034 | 269/286 | Câu 2. Trình bày cơ chế và đặc điểm các tổn thương thường gặp của trật khớp va… | SBLOCK2_823e3678dc61e63c29d36bbe [1634:1728] | Không có raw: request lỗi |
| SRC_CHECK_035 | 269/286 | Câu 3. Trình bày chẩn đoán xác định của trật khớp vai tái diễn? | SBLOCK2_5cd83707fe5809903d45685c [1729:1792] | Không có raw: request lỗi |
| SRC_CHECK_036 | 269/286 | Câu 4. Trình bày nguyên tắc điều trị phẫu thuật trật khớp vai tái diễn? | SBLOCK2_fa57ac5e93474b232397de91 [1793:1864] | Không có raw: request lỗi |
| SRC_CHECK_037 | 269/286 | Câu 5. Trình bày nguyên tắc điều trị bảo tồn trật khớp vai cấp tính và một số … | SBLOCK2_0cba20a528878bb1f78eb07a [1865:1979] | Không có raw: request lỗi |


Ba ví dụ đọc được:

1. **Cụm kiến thức:** “trật khớp vai tái diễn … cùng bên từ lần 2 trở lên (thường > 10 lần)” — PDF254/in271, `LOC2_fed9e81e48c965731493ecfd`. Candidate tái diễn `IS_A` candidate Trật khớp vai; định nghĩa chung giữ riêng câu về <3/>3 tuần. Không merge sang sách 2006 chỉ vì cùng tên.
2. **Skill:** “Minh họa … phẫu thuật Bankart và phẫu thuật Latarjet” — PDF254/in271, `LOC2_937e86af9deb5bd2d6835f3f`. Hai Skill cognitive `APPLIES_TO` hai tên Intervention. Quan hệ có nguồn; nội dung phương pháp mới chỉ là tên, chưa có bước phẫu thuật trong scope này.
3. **Câu hỏi thật nhưng chưa có node:** “Câu 3. Trình bày chẩn đoán xác định của trật khớp vai tái diễn?” — PDF269/in286, block `SBLOCK2_5cd83707fe5809903d45685c` (ID đầy đủ trong checklist `SRC_CHECK_035`). Có 5 câu nguồn, trích đủ **0/5** do cửa sổ request lỗi. Không tạo SampleQuestion hoặc ABOUT/ASSESSES thay model; ví dụ này là nguồn cần kiểm lại, không phải một kết quả thành công.

## F. OCR, lỗi, nguyên nhân và ảnh hưởng

Đã xem ảnh đủ 8 trang được chọn tại `audit/pdf-review`. Có 26 patch OCR riêng, với hash PDF/OCR/ảnh, before/after và offset raw. Ví dụ PDF91 “tay lạnh”→“tay lành”, “chòm”→“chỏm”, “ổ chỏ”→“ổ chảo”; PDF254 “ở chỏm và chỏm”→“ổ chảo và chỏm”; PDF263 “5.2.2. Chẩn đoán”→“5.2.2. Chống chỉ định”, “Trật hò”→“Trật hở”. Chỉ chép lại chữ thấy rõ trên ảnh, không sửa số/đơn vị/phủ định hoặc kiến thức sách.

PDF92 OCR ghi Thì 3, ảnh PDF in lặp Thì 2. Không đổi số theo kiến thức về Kocher; đánh dấu unresolved và giữ ngoài node phương pháp, cùng 5 ý/bước của cụm này trong bảng độ phủ. Không có patch số liệu. Truy vết candidate source corrected→raw đã kiểm; OCR gốc không thay đổi.

Các nguyên nhân chính:

- **Model, ảnh hưởng cao:** mọi MANAGED_BY raw bị đảo Intervention→Condition; EVALUATED_BY dùng DiagnosticMethod→Finding, không phù hợp taxonomy hiện tại. Tạo một practical Skill từ mô tả khám mà không có yêu cầu năng lực. Bỏ chỉ định/chống chỉ định và câu theo dõi; tạo Intervention có content chỉ là tên.
- **Validator, ảnh hưởng cao:** không nhận verb “Vận dụng”; dòng `7.1.3. Bất động: …` có hướng dẫn thật nhưng bị xem chỉ là heading; qualifier guard quét sang câu kế tiếp sau một quote kết thúc bằng dấu chấm nên có false positive. Chặn alias ở cả trường hợp model ghép tên dài lẫn cặp tên có sẵn (Apprehension test/cấp tính/mạn tính); cần phân biệt hai nhóm, không bỏ kiểm alias toàn bộ.
- **Validator bảo thủ, ảnh hưởng cục bộ:** tên Finding rút gọn bỏ “của” không khớp liên mạch nên bị loại; ba IS_A từ câu “Có thể gặp…” bị chặn modality. Không nới theo khoảng cách cùng trang.
- **Chunking, ảnh hưởng cao:** definition context lặp tạo nhiều subtype chiếm output; riêng đoạn chỉ định qua trang không được model giữ. Không có raw nào chạm 12 node/16 cạnh hay finish_reason=length, nên chưa có bằng chứng mất do hard cap lần này. Không chạm cap vẫn không đồng nghĩa đầy đủ.
- **Identity, ảnh hưởng cao khi xuất canonical:** 14 node/4 cạnh qua kiểm kỹ thuật vẫn bị giữ ngoài canonical. Registry không sai/không bị đổi; scope mới chưa có binding. Có duplicate tái diễn do biên quote, chưa có merge sai vì không có merge.
- **Dịch vụ/telemetry, ảnh hưởng cao:** hai cửa sổ không có raw, gồm toàn bộ câu hỏi. HTTP/latency/cause gốc của lỗi transport chưa được audit đủ; không suy lỗi database, VPN hoặc route.

36 record rejection dưới đây là occurrence, không phải 36 khái niệm khác nhau. Riêng 15 dangling là lỗi dây chuyền, không cộng như 15 lỗi nguồn độc lập.


| Lý do validator | Số record |
| --- | --- |
| unresolved_ocr_affects_meaning | 1 |
| title_only_content_is_not_medical_description | 1 |
| edge_loses_modality | 3 |
| invalid_relationship_end_types | 4 |
| dangling_edge_or_rejected_node | 15 |
| quote_omits_condition_negation_or_numeric_context | 2 |
| alias_equivalence_not_supported | 7 |
| skill_name_needs_action_and_object | 1 |
| name_not_supported | 1 |
| skill_has_no_explicit_basis | 1 |


| Window | Kind | Local ID | Type | Reason |
| --- | --- | --- | --- | --- |
| 2006-treatment | node | node_phuong_phap_kocher | Intervention | unresolved_ocr_affects_meaning |
| 2006-treatment | node | node_bat_dong_desault | Intervention | title_only_content_is_not_medical_description |
| 2006-treatment | edge | edge_1 | IS_A | edge_loses_modality |
| 2006-treatment | edge | edge_2 | IS_A | edge_loses_modality |
| 2006-treatment | edge | edge_3 | IS_A | edge_loses_modality |
| 2006-treatment | edge | edge_4 | MANAGED_BY | invalid_relationship_end_types |
| 2006-treatment | edge | edge_5 | MANAGED_BY | dangling_edge_or_rejected_node |
| 2006-treatment | edge | edge_6 | MANAGED_BY | dangling_edge_or_rejected_node |
| 2006-treatment | edge | edge_7 | APPLIES_TO | dangling_edge_or_rejected_node |
| 2021-objectives | node | node_trat_khop_vai | Condition | quote_omits_condition_negation_or_numeric_context |
| 2021-objectives | node | node_trat_khop_vai_som | Condition | alias_equivalence_not_supported |
| 2021-objectives | node | node_trat_khop_vai_muon | Condition | alias_equivalence_not_supported |
| 2021-objectives | node | node_van_dung_nguyen_tac_dieu_tri | Skill | skill_name_needs_action_and_object |
| 2021-objectives | edge | edge_1 | IS_A | dangling_edge_or_rejected_node |
| 2021-objectives | edge | edge_2 | IS_A | dangling_edge_or_rejected_node |
| 2021-objectives | edge | edge_3 | IS_A | dangling_edge_or_rejected_node |
| 2021-objectives | edge | edge_4 | APPLIES_TO | dangling_edge_or_rejected_node |
| 2021-objectives | edge | edge_5 | APPLIES_TO | dangling_edge_or_rejected_node |
| 2021-objectives | edge | edge_8 | MANAGED_BY | invalid_relationship_end_types |
| 2021-objectives | edge | edge_9 | MANAGED_BY | invalid_relationship_end_types |
| 2021-apprehension | node | node_trat_khop_vai_som | Condition | alias_equivalence_not_supported |
| 2021-apprehension | node | node_trat_khop_vai_muon | Condition | alias_equivalence_not_supported |
| 2021-apprehension | node | node_mat_vung_phia_truoc | Finding | name_not_supported |
| 2021-apprehension | node | node_nghiem_phap_e_so | DiagnosticMethod | alias_equivalence_not_supported |
| 2021-apprehension | node | skill_thuc_hien_nghiem_phap_e_so | Skill | skill_has_no_explicit_basis |
| 2021-apprehension | edge | edge_1 | IS_A | dangling_edge_or_rejected_node |
| 2021-apprehension | edge | edge_2 | IS_A | dangling_edge_or_rejected_node |
| 2021-apprehension | edge | edge_4 | EVALUATED_BY | dangling_edge_or_rejected_node |
| 2021-apprehension | edge | edge_5 | APPLIES_TO | dangling_edge_or_rejected_node |
| 2021-conservative | node | node_trat_khop_vai_cap_tinh | Condition | alias_equivalence_not_supported |
| 2021-conservative | node | node_trat_khop_vai_man_tinh | Condition | alias_equivalence_not_supported |
| 2021-conservative | node | node_bat_dong_khop_vai | Intervention | quote_omits_condition_negation_or_numeric_context |
| 2021-conservative | edge | edge_1 | IS_A | dangling_edge_or_rejected_node |
| 2021-conservative | edge | edge_2 | IS_A | dangling_edge_or_rejected_node |
| 2021-conservative | edge | edge_4 | MANAGED_BY | invalid_relationship_end_types |
| 2021-conservative | edge | edge_5 | MANAGED_BY | dangling_edge_or_rejected_node |


## G. Kiểm chứng kỹ thuật và bảo toàn

- 4 raw JSON qua đúng schema đã khóa; raw thất bại không được thay bằng fixture/mock.
- Graph staging toàn đợt và từng sách qua schema, unique node/edge ID, endpoint references, domain/range, chu trình phân cấp và loader JSON serialization round-trip. Audit kiểm locator khớp corrected page và offset raw gốc. Các ID chưa resolve vẫn là CAND2 trong staging.
- Resume cùng fingerprint/code/config dùng 4 cache thành công, graph và candidate graph giữ nguyên. Vì đã hết 6 request, dùng client chặn mạng để dừng 2 cửa sổ chưa có cache trước HTTP: **0 request mới**. Đây là kiểm resume offline có guard, không tuyên bố plain CLI resume sẽ không gọi lại lỗi cũ. `audit/resume-verification.json` ghi giới hạn này.
- Test liên quan: `pytest knowledge_pipeline/tests document_toolkit/test_toolkit.py -q`: **79 passed, 2 subtests passed**. Ruff check + format check cho kg_v2 và hai file test qua. Có test HTTP mock cho telemetry/capacity/cache; đó chỉ là unit test, không trộn vào kết quả extraction thật.
- 331 file snapshot (OCR, output cũ và registry) giữ nguyên hash. Không sửa API/practice/database nghiệp vụ, PostgreSQL, VPN/route, .env; không chạy locked model test. Không commit/push. Không có Neo4j read/write.

## H. So với mẫu gãy xương hở

Mẫu cũ chứng minh được heading–bullet, một hệ thống phân loại với 6 mức và IS_A con, cùng một mục xử trí có nội dung. Mẫu mới cho thấy schema vẫn biểu diễn được định nghĩa, thời gian/tần suất và Skill nhận thức. Nhưng xử lý chẩn đoán, chỉ định/chống chỉ định và câu hỏi **chưa được chứng minh thành công**: request chẩn đoán 2006/câu hỏi 2021 lỗi; nghiệm pháp bị validation loại; xử trí bị sai hướng cạnh và thiếu nội dung. Không thể suy khả năng chạy hai sách từ số node hoặc JSON hợp lệ của mẫu cũ.

## I. Kết luận mở rộng và bàn giao

Có thể tiếp tục batch nhỏ có staging và fidelity checklist. Các blocker cần sửa trước full-corpus: mất điều kiện/contraindication/theo dõi, false-positive validator, content chỉ là tên lọt qua, hướng quan hệ và diagnostics lỗi. Đợt câu hỏi cần kiểm lại trước khi đánh giá SampleQuestion. OCR lỗi cục bộ có thể đưa vào hàng chờ, không cần chờ sửa toàn bộ sách mới chạy các mục độc lập. Resolver tự động và concurrency cao hơn là cải tiến sau; không dùng chúng để che lỗi extraction.

Đường dẫn output:

- Toàn bộ candidate: `data/knowledge-extraction/v2/shoulder-20261030/staging/{graph.json,nodes.jsonl,edges.jsonl}`.
- Theo sách: `by-book/2006/staging/`, `by-book/2021/staging/` trong cùng output.
- Graph canonical tại root `graph.json`, `nodes.jsonl`, `edges.jsonl` là 0/0; không dùng làm thước đo extraction.
- Audit: source manifest/checklist trước generate, lock, raw/checkpoint, request metrics, locators, patches/issues/ảnh, fidelity-review, raw-fidelity-review, coverage-evaluation, evaluation-summary và resume-verification.

## J. Kế hoạch và lệnh tiếp theo

Xem [kế hoạch batch và ước lượng](medical-kg-v2-batch-plan-20261030.md): chia theo mục, continuation có chứng cứ, max 6 window/shard, concurrency 1, checkpoint, queue lỗi, capacity/coverage gates, resolver qua batch và giữ provenance từng sách. Ước lượng trung tâm 1.072 request (dải rất thô 439–2.098), khoảng 7,7 giờ ở latency thành công trung bình, chưa gồm lỗi/retry/review. Đây không phải cam kết full-corpus.

Lệnh tiếp theo được khuyến nghị, không gọi model và không ghi Neo4j:

```powershell
$py = "$env:TEMP/medresident-extraction-venv/Scripts/python.exe"
& $py -m knowledge_pipeline.kg_v2 loader-dry-run --output data/knowledge-extraction/v2/shoulder-20261030/staging
```

Đã chuẩn bị `knowledge_pipeline/kg_v2/shoulder-retry-scope-20261030.json` cho đúng hai window lỗi và kiểm prepare offline. Lệnh generate đợt mới nằm trong batch plan; chưa thực thi vì ngân sách 6 request hiện tại đã dùng hết.
