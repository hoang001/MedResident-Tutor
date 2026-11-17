# KG draft — bàn giao 30/10/2026

Đã triển khai và chạy kiểm chứng: **37 node, 25 cạnh; 23/37 ý nguồn; 5/5 câu hỏi**. Chi tiết: [report.md](../data/knowledge-extraction/v2/draft-delivery-20261030/report.md), [review.html](../data/knowledge-extraction/v2/draft-delivery-20261030/review.html).

Có 171 review item (gồm audit sửa trường, identity và nội dung cần đối chiếu), 1 rejected OCR; không phải dữ liệu đã duyệt. Sáu request mới mất 198,076 giây chờ; 3 thành công, 3 timeout. 56 test + 2 subtest và lint qua. Không ghi Neo4j.

Lệnh batch và resume nằm trong report. Scope chương PDF89–92 sách 2006 có 9 cửa sổ/3 shard; kết quả thực thi và khôi phục nằm dưới đây.

Chương này sau đó đã được chạy: [báo cáo thực thi và khôi phục](../data/knowledge-extraction/v2/chapter-shoulder-2006-recovered/report.md), [bản review](../data/knowledge-extraction/v2/chapter-shoulder-2006-recovered/aggregate/review.html). Có 35 node/19 cạnh; 9 cửa sổ được xử lý, trong đó 3 cửa sổ khôi phục một phần từ JSON sai schema. Code draft đã sửa để giữ record hợp lệ thay vì bỏ cả response; record hỏng và cạnh liên quan nằm trong queue. Dùng `kg_v2 recover --input-run <batch-cũ> --output <thư-mục-mới>` để khôi phục batch cũ offline; không gọi LLM hoặc ghi đè output nguồn.
