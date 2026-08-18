# Hướng dẫn sử dụng `curriculum_map.json`

## 1. Mục đích của file

`curriculum_map.json` là bản đồ chương trình đào tạo dùng chung cho pipeline xây dựng dataset của MedResident Tutor.

File này trả lời các câu hỏi:

- Dataset đang phục vụ chuyên ngành nào?
- Mỗi mẫu thuộc học phần nào?
- Học phần nằm ở Round và năm đào tạo nào?
- Học phần là bắt buộc hay tự chọn?
- Số tín chỉ lý thuyết và thực hành là bao nhiêu?
- Nhóm học phần nào là nền tảng, chuyên ngành hoặc thực hành nâng cao?

File này **không chứa kiến thức y khoa để chấm đúng/sai**.

## 2. Vai trò trong pipeline train model

### 2.1. Đối với Medical Model

`curriculum_map.json` chỉ được dùng để:

- gắn metadata `course_code`, `round`, `year`, `course_name`;
- lọc và thống kê dữ liệu theo học phần;
- kiểm tra mẫu có nằm trong phạm vi chương trình hay không;
- tổ chức dataset theo tiến trình đào tạo.

Không được dùng file này làm `evidence` chuyên môn.  
Tên học phần như “Chấn thương chỉnh hình chi trên” không đủ để suy ra chẩn đoán, chỉ định, cơ chế, kỹ thuật hoặc đáp án y khoa.

Bằng chứng chuyên môn của Medical Model phải đến từ:

- `source_units.jsonl`;
- giáo trình;
- hướng dẫn quy trình;
- tài liệu chuyên môn có nguồn và trang cụ thể.

### 2.2. Đối với Teaching Model

Có thể dùng metadata của chương trình để điều chỉnh mức độ phản hồi, ví dụ:

- Round 1: ưu tiên giải thích nền tảng và cấp cứu;
- Round 2: đánh giá kiến thức chuyên ngành;
- Round 3: phản hồi theo định hướng thực hành lâm sàng nâng cao.

Tuy nhiên Teaching Model vẫn chỉ được giải thích dựa trên output của Medical Model và bằng chứng đã cung cấp. Không được tự thêm kiến thức từ tên học phần.

## 3. Cách liên kết với các file dataset khác

### `source_units.jsonl`

Mỗi đơn vị kiến thức phải có thêm:

```json
{
  "knowledge_id": "ORTHO_B21CN7_KU_0001",
  "course_code": "B21CN7",
  "curriculum_group_id": "ORTHO_SPECIALTY_ROUND_2"
}
```

### `qa_items.jsonl`

Mỗi câu hỏi phải kế thừa học phần từ đơn vị kiến thức:

```json
{
  "question_id": "ORTHO_B21CN7_Q_0001",
  "course_code": "B21CN7",
  "knowledge_ids": ["ORTHO_B21CN7_KU_0001"]
}
```

### `student_answer_cases.jsonl`

Mỗi biến thể câu trả lời phải giữ nguyên `question_id` và `course_code` của câu hỏi gốc.

### `medical_train.jsonl` và `teaching_train.jsonl`

Có thể giữ metadata chương trình ở cấp mẫu để:

- phân tích độ phủ;
- tạo split theo học phần;
- kiểm tra mất cân bằng dữ liệu;
- đánh giá hiệu năng theo Round hoặc năm đào tạo.

Không đưa toàn bộ `curriculum_map.json` vào từng prompt huấn luyện. Chỉ trích các trường metadata cần thiết.

## 4. Ý nghĩa các trường chính

| Trường | Ý nghĩa |
|---|---|
| `program` | Thông tin chương trình, cơ sở đào tạo và phạm vi chuyên ngành |
| `scope.primary_specialty_block` | Tổng quan khối Chấn thương chỉnh hình 40 tín chỉ |
| `course_groups` | Phân nhóm học phần theo Round và vai trò |
| `course_code` | Khóa liên kết chính giữa chương trình và các file dataset |
| `role_in_dataset` | Vai trò của nhóm học phần trong dataset |
| `selection_rule` | Quy tắc bắt buộc hoặc chọn học phần |
| `content_outline` | Đề cương nội dung; hiện để `null` vì nguồn chưa cung cấp |
| `learning_outcomes` | Chuẩn đầu ra; hiện để `null` vì nguồn chưa cung cấp |
| `prerequisites` | Học phần tiên quyết; hiện để `null` vì nguồn chưa cung cấp |
| `source_status` | Mức độ đã xác minh của thông tin |

## 5. Quy tắc bắt buộc cho code xử lý dữ liệu

1. Không nhận mẫu có `course_code` không tồn tại trong `curriculum_map.json`.
2. Không tự tạo nội dung chuyên môn từ `course_name`.
3. Không cộng B21CN1 vào 40 tín chỉ của khối 3.2.1.
4. Round 2 phải gồm 4 học phần bắt buộc, tổng 24 tín chỉ.
5. Round 3 có 8 học phần tự chọn, mỗi học phần 4 tín chỉ; người học chọn 4 học phần, tổng 16 tín chỉ.
6. Khi `content_outline`, `learning_outcomes` hoặc `prerequisites` là `null`, phải hiểu là nguồn chưa cung cấp, không phải là không tồn tại.
7. Mọi nội dung y khoa dùng để tạo câu hỏi hoặc chấm điểm phải truy được về tài liệu và trang cụ thể.

## 6. Cách dùng khi chia train/validation/test

Không chia ngẫu nhiên theo từng câu trả lời giả lập.

Tất cả biến thể của cùng một `question_id` phải nằm trong cùng một split. Có thể dùng `course_code` để kiểm tra độ phủ, nhưng không nên để toàn bộ một học phần chỉ xuất hiện trong train nếu mục tiêu là đánh giá tổng quát trong cùng phạm vi chương trình.

Khuyến nghị khóa nhóm khi chia dữ liệu:

```text
group_key = question_id
```

Nếu có nhiều câu hỏi được sinh từ cùng một tình huống lâm sàng hoặc cùng một đoạn nguồn gần như giống nhau, nên dùng khóa nhóm rộng hơn:

```text
group_key = source_case_id hoặc source_unit_cluster_id
```

## 7. Trạng thái dữ liệu hiện tại

File hiện đầy đủ đối với phần học phần Chấn thương chỉnh hình nhìn thấy trong ảnh:

- B21CN1;
- B21CN7 đến B21CN18;
- thông tin Round, năm, loại học phần và tín chỉ;
- quy tắc chọn 4 trong 8 học phần Round 3.

Các trường sau chưa có căn cứ và được để `null`:

- số quyết định;
- ngày ban hành;
- đề cương chi tiết;
- chuẩn đầu ra;
- học phần tiên quyết.

Khi có văn bản đầy đủ, chỉ cập nhật các trường này sau khi đối chiếu nguồn; không đổi `course_code` hoặc cấu trúc liên kết nếu không có lý do bắt buộc.
