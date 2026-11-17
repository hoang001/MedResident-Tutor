<!-- generated: retrieval-confirmation-20261111 -->
# Bản nháp phần thực nghiệm — MedResident-Tutor

Trạng thái: **Đã thực hiện 12/12 attempt; 12 API evaluation hợp lệ, 6/6 cặp đầy đủ.** Đây là bản nháp từ artifact lưu trên máy, chưa phải kết quả thử nghiệm lâm sàng hoặc nghiên cứu hiệu quả học tập.

## 1. Mục tiêu và câu hỏi nghiên cứu

Thực nghiệm khảo sát ba câu hỏi: adapter V1 thay đổi mức khớp điểm với reference như thế nào khi giữ evidence cố định; Teaching phản hồi có bám Medical và learner context theo các proxy đã định hay không; đường backend có thực sự truy xuất evidence từ corpus/KG và đưa đúng evidence vào Medical không. Chất lượng nội dung và tính đúng của điều phối là hai trục riêng. Không đặt ngưỡng accuracy để chọn hoặc chạy lại output đẹp.

Phân biệt phạm vi: pilot local ngày09/11; benchmark chính ngày10/11; nhóm development tích hợp ngày11/11. Các điểm backend structured/V2 chấm xác định không phải điểm LLM. Benchmark chính dùng evidence tham chiếu cố định; nhóm tích hợp dùng evidence truy xuất lại. Teaching thật thuộc benchmark cũ, Teaching của nhóm tích hợp là mock có nhãn. Nhóm tích hợp chạy FastAPI ASGI/router/service/HTTP trong child riêng, chưa phải browser E2E.

## 2. Phần cứng, phần mềm, model và adapter

Máy local: Microsoft Windows 11 Pro, CPU `Intel(R) Core(TM) i5-14400F` (10 lõi/16 logical processors, đo khi bàn giao), RAM vật lý 15.76 GiB; GPU ghi nhận `NVIDIA GeForce RTX 5060, 8151 MiB, 1304 MiB, 6592 MiB, 616.92`. Thứ tự thông số GPU là tên, tổng VRAM, VRAM dùng/trống và driver. Runtime benchmark là Linux/Docker Python3.12; phiên bản package lấy từ metadata của worker, không suy từ môi trường máy chủ.

Medical: Qwen/Qwen3-4B-Instruct-2507, adapter Medical V1 được cung cấp, SHA256 `cafcf7b7e3793ee7e09149a614f4289912609641d020d9b8c38d69684141e5a8`. Teaching: Qwen/Qwen2.5-7B-Instruct cùng adapter Teaching V1 của benchmark. Giữ NF4 double quant, float16, greedy decoding, seed42, input4096/context8192; Medical cap1200 và Teaching cap1600 token. Medical packages: `{'torch': '2.10.0+cu128', 'transformers': '4.57.6', 'peft': '0.21.2', 'accelerate': '1.15.0', 'bitsandbytes': '0.50.2'}`.

Metadata base/adapter Medical chỉ khác `adapter_enabled` và `adapter_sha256`; base revision, tokenizer/chat-template/system-prompt hash, quantization, decoding và dataset manifest trùng. Có 199 cặp có hash prompt thực tế cùng nhau; 1 cặp không đủ telemetry do interruption. Không gán sự vắng mặt telemetry là đã xác minh.

## 3. Dữ liệu, reference, split và provenance

Manifest chính chứa50câu từ10chủ đề, mỗi câu có5 biến thể trả lời tổng hợp. Development có10câu/2chủ đề, tương ứng50input Medical đã chuẩn bị; test có40câu/8chủ đề, tương ứng200input cho mỗi cấu hình. Số prepared không đồng nghĩa số đã chạy: các attempt development thực tế được ledger lưu riêng. Teaching test có60input với context none/recurring/improving; payload Medical đầu vào Teaching là reference chuẩn bị sẵn, không lấy tùy tiện output Medical của từng nhánh.

Reference và rubric do Codex đối chiếu đoạn nguồn của hai sách2006/2021, có source ID, trang PDF, locator/hash. `human_reviewed=false`, `clinician_approved=false`: đối chiếu nguồn không đồng nghĩa bác sĩ đã duyệt. Câu trả lời tổng hợp không phải bài làm người học thật. Nguồn còn nguy cơ OCR/khác phiên bản; không diễn giải điểm cao thành an toàn lâm sàng.

Đã xác minh hash toàn bộ dataset manifest và payload của checkpoint khi có telemetry: {'True': 400}. Cùng sample IDs, cùng rubric/evidence/expected cho hai cấu hình; CSV `medical-paired.csv` giữ hash riêng từng thành phần. Một interruption không có raw/prompt đầy đủ, giữ lỗi đó trong mẫu số. Không chạy lại locked benchmark và không thay dữ liệu nguồn.

Audit trùng lặp gốc dùng normalized exact matching và SequenceMatcher trên các file training có sẵn, không chứng minh hết nhiễm paraphrase. Provenance dữ liệu huấn luyện adapter chưa đầy đủ (`adapter_training_provenance_incomplete` trong leakage-audit); split theo chủ đề trong benchmark không đồng nghĩa đã chứng minh độc lập với toàn bộ dữ liệu training của adapter. Đây là giới hạn của diễn giải tổng quát hóa.

## 4. Cấu hình đối chứng

| Nhóm | Các nhánh | Evidence và đường chạy |
| --- | --- | --- |
| Benchmark Medical chính | base / adapter | Cùng evidence tham chiếu cố định; batch model local, không đánh giá HTTP |
| Benchmark Teaching chính | base / adapter; raw / guarded | Cùng Medical reference và learner context; guard xác định hậu xử lý |
| Retrieval cũ | vector / hybrid | TF-IDF ký tự,50câu, graph snapshot offline; không phải semantic encoder mới |
| Tích hợp mới | cùng Medical adapter, vector / hybrid | Sáu input từ3câu, semantic E5 local; hybrid live Neo4j; Teaching mock |

Run tích hợp trước đã đóng:12request gồm1timeout,10HTTP429,1completed và2generation. Run xác nhận mới `retrieval-confirmation-20261111` có thư mục/manifest/category riêng, lineage tới run cũ, cùng corpus/encoder/mapping/expected. Không lấy output cũ để lấp ô thiếu của run mới. Cả hai nhánh mới dùng cùng source scope, encoder, threshold0.75, top3, tối đa6000ký tự; hybrid giữ0.85semantic+0.15KG, không reranker. Không tuning theo điểm Medical.

Vector chỉ dùng semantic retrieval trong source scope có metadata đã kiểm, không gọi KG để chọn/boost. Số12Cypher của run cũ là6hybrid×2, vector0. Source scope dùng chung từ metadata/mapping tĩnh, không lấy kết quả truy vấn KG để lọc riêng vector. Concept IDs có thể xuất hiện trong trace vector như metadata; điều đó không chứng minh vector đã dùng KG. Audit/readiness queries được tách riêng khỏi query retrieval và latency.

## 5. Metric và mẫu số

Exact total là số output contract-valid có tổng bằng reference chia toàn bộ200mẫu dự kiến. Exact criterion vector dùng cùng mẫu số; đã đối chiếu thêm theo criterion ID và không phát hiện khác với metric gốc. Schema-valid và contract-valid là hai mức khác nhau: JSON đúng schema vẫn có thể sai tổng điểm so với điểm criteria. Lỗi schema/runtime nằm trong mẫu số agreement, nhưng không được gán điểm0.

MAE chuẩn hóa là trung bình `abs(predicted_total-reference_total)/max_score` trên output có số điểm contract-valid; công bố n và coverage riêng, không suy điểm cho mẫu lỗi. Wrong-criterion award rate dùng số criterion được đánh dấu sai mà model vẫn cho điểm chia số criterion sai thực sự được chấm; planned80, observed67/79 khác nhau do lỗi. Teaching dùng proxy lexical/alignment/context, không phải accuracy sư phạm. Retrieval Hit@5 và coverage là proxy trùng đoạn nguồn, semantic relevance chuyên gia là N/A. Khoảng tin cậy chênh lệch dùng1000 paired bootstrap theo8cụm chủ đề, seed42, giữ các biến thể của một cụm cùng nhau; không coi200biến thể là200người học độc lập.

## 6. Kết quả Medical với evidence cố định

| Cấu hình | N dự kiến | Schema hợp lệ | Contract hợp lệ | Exact total | Exact vector | MAE chuẩn hóa (n) |
| --- | --- | --- | --- | --- | --- | --- |
| medical_base | 200 | 200/200 | 187/200 | 74.5% | 74.5% | 0.1016 (187) |
| medical_adapter | 200 | 199/200 | 199/200 | 75.5% | 75.5% | 0.1256 (199) |

Các giá trị được tính lại từ checkpoint/raw/expected, không nhập bảng thủ công. Đã parse/validate lại399raw Medical bằng validator V1, kết quả trùng cờ schema/contract và parsed gốc;1interruption không có raw. Exact vector theo criterion ID không làm đổi metric gốc, vì vậy không sửa revision metric lịch sử.

| Kết quả trên cùng mẫu | Số mẫu |
| --- | --- |
| Cả hai đúng | 120 |
| Chỉ adapter đúng | 31 |
| Chỉ base đúng | 29 |
| Cả hai không đúng/không hợp lệ | 20 |

Adapter trừ base là **1.0 điểm phần trăm** về exact total. Khoảng paired cluster bootstrap95% là [-6.0; 7.5] điểm phần trăm, bao gồm0; không kết luận cải thiện đáng kể. Adapter có contract-valid rate cao hơn nhưng MAE trên mẫu hợp lệ cao hơn; mẫu số MAE khác nhau nên phải đọc cùng coverage. Wrong-criterion awards: base 13/67, adapter 38/79. Đây là tín hiệu cần phân tích nội dung, không được che bằng chênh lệch trung bình nhỏ.

![Medical với evidence cố định](../../data/evaluation/runs/retrieval-confirmation-20261111/figures/medical-fixed-evidence.svg)

![Kết quả so sánh trên cùng mẫu](../../data/evaluation/runs/retrieval-confirmation-20261111/figures/medical-paired-outcomes.svg)

CSV `medical-by-group.csv` cung cấp lỗi theo8chủ đề và5loại trả lời. Biểu đồ tách grade mismatch khi contract-valid với lỗi contract/runtime; không quy lỗi hạ tầng thành kiến thức sai.

![Lỗi theo loại trả lời](../../data/evaluation/runs/retrieval-confirmation-20261111/figures/medical-errors-by-answer-type.svg)

## 7. Teaching và retrieval đã có

| Cấu hình | Giai đoạn | N | Schema hợp lệ | Alignment proxy | Context proxy (n) |
| --- | --- | --- | --- | --- | --- |
| teaching_base | raw | 60 | 100.0% | 6.7% | 22.5% (40) |
| teaching_base | guarded | 60 | 100.0% | 23.3% | 65.0% (40) |
| teaching_adapter | raw | 60 | 100.0% | 30.0% | 67.5% (40) |
| teaching_adapter | guarded | 60 | 100.0% | 35.0% | 90.0% (40) |

Đã tái tạo120raw Teaching, parsed, guard và proxy từ artifact cũ; kết quả tổng hợp trùng metrics gốc. Guard là hàm xác định, không phải inference mới; proxy được cải thiện sau guard không chứng minh model tự sửa được Medical hoặc dạy hiệu quả. Review trực tiếp của Codex có12mẫu/cấu hình/giai đoạn Teaching,40mẫu/cấu hình Medical; không phải hội đồng bác sĩ hoặc nghiên cứu người dùng. Các nội dung không có đánh giá ngữ nghĩa chắc chắn giữ unknown/N/A.

| Chế độ offline | N | Hit@5 proxy | Coverage nguồn đầy đủ proxy | Semantic relevance bác sĩ |
| --- | --- | --- | --- | --- |
| vector | 50 | 90.0% | 68.0% | N/A |
| hybrid | 50 | 90.0% | 80.0% | N/A |

Đã tính lại proxy từ100record retrieval lưu sẵn (50câu×2), source spans và provenance; không rank lại hoặc gọi Neo4j/LLM. Corpus retrieval cũ1554chunk, TF-IDF char_wb3–5; khác corpus semantic971cửa sổ của nhóm mới. Coverage tăng từ68% lên80% là proxy phủ đầy đoạn tham chiếu, không đồng nghĩa coverage y khoa thực. Không gộp kết quả hai hệ retrieval thành một accuracy.

![Retrieval offline và proxy](../../data/evaluation/runs/retrieval-confirmation-20261111/figures/retrieval-offline-proxies.svg)

## 8. Nhóm tích hợp development sau vá harness

Đã thực hiện 12/12 attempt; 12 API evaluation hợp lệ, 6/6 cặp đầy đủ.

Preflight mới có12request đi qua FastAPI/router/service và HTTPProvider với transport stub được gắn nhãn, không gọi model. Cấu hình được quan sát tại client thực: read600s, deadline orchestration625s, caller ASGI không đặt timeout30s; production/mock mặc định giữ nguyên.24 test CPU liên quan đã PASS, gồm kiểm readiness vẫn200 khi service lock đang bận và khi caller cancel mà runner chưa dừng. Batch concurrency1, thứ tự mỗi input vector rồi hybrid, cặp đầu ST_CLOSE correct. Readiness/load deadline1200s tách với inference. Timeout/busy/OOM/lỗi điều phối dừng batch; lỗi output schema giữ raw và chỉ tiếp tục nếu lock/generation đã rảnh. Không retry vì điểm sai, không warm-up/smoke generation.

| Input | Nhánh | Reference | API vector | Medical HTTP | Attempt | Lỗi |
| --- | --- | --- | --- | --- | --- | --- |
| KGR_DEV_ST_CLOSE__correct | vector | [1, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_ST_CLOSE__correct | hybrid | [1, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_ST_CLOSE__mixed | vector | [1, 0] | [1, 0] | 200 | teaching_failed | {'code': 'TEACHING_ALIGNMENT_INVALID', 'stage': 'teaching'} |
| KGR_DEV_ST_CLOSE__mixed | hybrid | [1, 0] | [1, 0] | 200 | teaching_failed | {'code': 'TEACHING_ALIGNMENT_INVALID', 'stage': 'teaching'} |
| KGR_DEV_AMP_STUMP__correct | vector | [1, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_AMP_STUMP__correct | hybrid | [1, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_AMP_STUMP__mixed | vector | [0, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_AMP_STUMP__mixed | hybrid | [0, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_FX_RADIO__correct | vector | [1, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_FX_RADIO__correct | hybrid | [1, 1] | [1, 1] | 200 | completed | N/A |
| KGR_DEV_FX_RADIO__mixed | vector | [0, 1] | [0, 1] | 200 | teaching_failed | {'code': 'TEACHING_ALIGNMENT_INVALID', 'stage': 'teaching'} |
| KGR_DEV_FX_RADIO__mixed | hybrid | [0, 1] | [1, 1] | 200 | completed | N/A |

| Nhánh mới | Attempt | Medical API hợp lệ | Khớp vector/reference | MAE chuẩn hóa (n) | Practice completed | Teaching mock bị guard |
| --- | --- | --- | --- | --- | --- | --- |
| vector | 6 | 6 | 5/6 | 0.0833 (6) | 4 | 2 |
| hybrid | 6 | 6 | 4/6 | 0.1667 (6) | 5 | 1 |

Các lỗi timeout/HTTP429 mới: {}; lỗi guard Teaching mock: {'TEACHING_ALIGNMENT_INVALID': 3}. Medical API hợp lệ không đồng nghĩa practice hoàn tất cả Teaching. So sánh cặp về điểm: {'vector_1_hybrid_1': 4, 'vector_0_hybrid_0': 1, 'vector_1_hybrid_0': 1}. Số mẫu nhỏ và có hai câu trả lời cho mỗi câu hỏi, không dùng các tỉ lệ này để suy ra tổng quát hóa hoặc lợi ích của KG. Trong nhóm quan sát, hybrid có nguồn rõ hơn cho câu X-quang nhưng không cải thiện điểm chấm; không tiếp tục tuning hoặc chạy lại.

![Sáu cặp Medical mới; dấu sao là lỗi guard Teaching mock](../../data/evaluation/runs/retrieval-confirmation-20261111/figures/integration-medical-pairs.svg)

Số mới: practice attempts duy nhất 12; practice submit POST kể cả kiểm idempotency 24; Medical HTTP attempts 12; generation bắt đầu/kết thúc 12/12; raw trả về 12; Medical API evaluation hợp lệ 12; practice completed 9; cặp đầy đủ 6/6. HTTP200 của practice không thay được attempt completed/Medical evaluation. Kết quả thiếu là N/A, không mượn raw run cũ hoặc gán0. Sáu input thuộc ba câu chỉ là nhóm kiểm chứng tích hợp nhỏ, không gộp với benchmark200mẫu.

Các số query mới: vector→KG 0, hybrid→KG 12, semantic queries 12. Server IDs/hash khớp 12, chưa có proof 0, mismatch 0. File `trace-example.json` chỉ được tạo khi run mới có trace; trạng thái chưa chạy không được gọi là end-to-end mới đã xác nhận. Teaching của nhóm này hoàn toàn mock, không nạp model Teaching.

Ngoài số query retrieval có 1 Cypher kiểm tra kết nối trước load, tách khỏi ranking và latency retrieval. Generation latency mới median/P95: 24.8515/30.7969 giây; tổng token input/output 32720/2899; load 222.6899 giây. Peak VRAM của worker mới chỉ được công bố theo telemetry trong integration-metrics.json, không cộng với RSS hoặc suy thành RAM Windows.

## 9. Phân tích lỗi và tính toàn vẹn tiếng Việt

**Run mới, attempt556, hybrid:** học viên viết “Chỉ lấy đúng ổ gãy, không được đưa khớp trên hay khớp dưới vào phim. Hai tư thế cần có là thẳng và nghiêng.”. Rubric C1 yêu cầu lấy khớp trên/dưới; evidence trang PDF14 ghi “phim X quang phải lấy hết khớp trên và dưới ổ gãy, đủ hai tư thế thẳng và nghiêng”. Model cho [1, 1] thay vì [0, 1]; lý do C1 là “Student answer correctly states the criterion and supports it with the evidence.”. Đây là lỗi phủ định/gán nội dung trong Medical khi đoạn nguồn đã có quy tắc rõ; không sửa ranking/KG để ép điểm. Vector trên cùng input được báo riêng ở bảng, không đủ để suy hybrid kém hơn nói chung. Có 3 output sai vector điểm trong nhóm mới và 3 output khớp điểm nhưng cùng một nhãn nằm trong cả incorrect_points/missing_points. Chẩn đoán Teaching mock offline tái hiện {'learning_priority_valid': 3}: fixture tạo learning_priority trùng focus khi echo hai danh sách đó; guard đã chặn. Đây là tái hiện hàm xác định sau run, không phải inference mới và không thay raw/API result. Điểm đúng không bảo đảm các danh sách phản hồi đúng ngữ nghĩa; review nguồn của Codex chưa phải duyệt bác sĩ.

Có 30 ví dụ trong review Medical lưu sẵn có tổng đúng nhưng còn lỗi nội dung/policy; đây là số ví dụ trong tập review, không suy ra tỉ lệ trên200mẫu. Ví dụ `medical_base/MRB1_03_04__mixed` có tổng điểm khớp reference nhưng review Codex ghi: CT credited and false MRI claim rejected, score 1/2 correct. Model also duplicates the addressed-but-incorrect MRI criterion in missing_points, contrary to the new benchmark policy.

Ví dụ phủ định đã quan sát ở run tích hợp cũ, attempt544 (không dùng làm kết quả của run mới): học viên viết “Chỉ lấy đúng ổ gãy, không được đưa khớp trên hay khớp dưới vào phim. Hai tư thế cần có là thẳng và nghiêng.” Rubric yêu cầu lấy khớp trên/dưới và hai tư thế; evidence2021 trang PDF14 nêu trực tiếp quy tắc. Model cho[1,1] thay vì reference[0,1] và nói học viên đã nêu C1 đúng. Với evidence có quy tắc rõ, lỗi gán phát biểu/phủ định nằm ở Medical; Teaching mock không chứng minh sửa được lỗi đó. Raw/prompt/trace giữ nguyên. Nếu output mới tái hiện hoặc không tái hiện, bảng mới báo đúng, không chạy lại để chọn kết quả.

Lỗi điều phối run cũ do HTTP read600s được đặt trong provider nhưng router còn deadline30s; server vẫn sinh sau khi caller bỏ chờ, dẫn tới10HTTP429. Lỗi này tách với lỗi nội dung. Bản vá dùng một local profile cho các lớp, ghi trạng thái cancel vào ledger, dừng batch khi hạ tầng lỗi và kiểm service lock thực. Kiểm chứng inference sau vá được công bố theo trạng thái hiện tại, không coi CPU test là bằng chứng inference.

Audit encoding phát hiện dấu `?` literal trong một số notes của `source-coverage-review.json`, `model-output-review.json` và phần notes được chèn vào report cũ. Nguyên nhân là Unicode trong here-string đi qua pipe PowerShell với encoding cũ; không thể khôi phục chữ đã mất bằng đổi encoding. File đề/rubric và raw gốc được đọc UTF-8 còn nguyên, không có U+FFFD; chúng được giữ theo hash. Bản mới dùng template UTF-8 và dữ liệu nguồn còn nguyên, không đoán lại chữ y khoa bị mất. Chi tiết ở `utf8-audit.json`; báo cáo/notes cũ giữ nguyên.

## 10. Thời gian, bộ nhớ và hạn chế

| Medical | Median/P95 giây | Input/output tokens cuối | Peak VRAM allocated/reserved GiB | Peak RSS GiB |
| --- | --- | --- | --- | --- |
| medical_base | 19.94/26.44 | 239500/74816 | 2.83/2.89 | 4.7749 |
| medical_adapter | 21.70/25.96 | 238150/47447 | 3.01/3.23 | 4.7610 |

Latency trên là generation latency của test checkpoint cũ, không phải HTTP end-to-end; tokens là test samples có telemetry, interruption có thể thiếu. Peak memory lấy từ process segment cuối đã lưu, không cộng các peak và không coi RSS Linux/WSL là RAM Windows. Benchmark adapter có recovery segment, giữ riêng ở nguồn; thời gian wall window chứa cả thời gian idle/recovery không được diễn giải là throughput thuần. Bản draft không thêm telemetry khi không có dữ liệu.

Hạn chế: reference và review chưa được bác sĩ duyệt; dữ liệu tổng hợp/ít chủ đề; source OCR và phiên bản cũ; proxy Teaching/retrieval không phải adjudication; không có nghiên cứu người dùng hoặc kết quả học tập; không đánh giá đọc ảnh X-quang; nhóm tích hợp chỉ3câu; phần lớn web vẫn giữ provider mock và bài prelinked. Graph source provenance không đảm bảo model dùng đúng phủ định/ngoại lệ. Không coi graph mở/health200 là runtime KG proof. Không dùng một điểm accuracy để kết luận hệ thống sẵn sàng học tập chính thức.

Ledger chung hiện có 556attempt, baseline run mới 544; cap mới12, ceiling chung800 giữ nguyên. Không sửa raw/expected/row lịch sử, không chạy lại locked benchmark, không train/thử adapter khác. Cleanup hiện đã xác nhận bằng cleanup.json; weights, adapters, cache và venv được giữ, không tự nạp model lần sau. Web/DB/Neo4j/provider hiện có giữ nguyên.

Nguồn bảng/biểu đồ: `offline/benchmark-verification.json`, các CSV `offline/medical-*`, `teaching-per-sample.csv`, `retrieval-per-question.csv`, `integration-metrics.json`, `integration-per-sample.csv`; toàn bộ nằm trong thư mục run mới. Dữ liệu số trong bảng/biểu đồ do script tính từ artifact, không nhập bằng tay. Xem `report.md` trong run mới cho lệnh và đường dẫn bàn giao.
