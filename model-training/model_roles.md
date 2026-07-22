# Medical Model

## Input
- Câu hỏi
- Câu trả lời người học
- Rubric
- Context lấy từ RAG

## Output
- Các ý đúng
- Các ý sai
- Các ý còn thiếu
- Bằng chứng từ context
- Điểm theo rubric
- Cảnh báo nếu không đủ căn cứ

# Teaching Model

## Input
- Kết quả JSON từ Medical Model
- Trình độ người học
- Mục tiêu bài học

## Output
- Nhận xét dễ hiểu
- Giải thích lỗi sai
- Gợi ý cải thiện
- Nội dung cần học lại
- Câu hỏi gợi mở tiếp theo

## Quy tắc
Teaching Model không được tự thêm kiến thức y khoa ngoài kết quả từ Medical Model và context RAG.