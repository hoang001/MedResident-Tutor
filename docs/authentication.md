# Đăng ký và đăng nhập

- Trên `/login`, bấm **Đăng ký** để mở `/register`.
- Đăng ký bằng họ tên, email, mật khẩu 8–128 ký tự và xác nhận mật khẩu.
- Backend lưu tài khoản LEARNER trong `users`; mật khẩu được salt/hash bằng Argon2id, không lưu mật khẩu gốc. API không trả hash. Đăng ký xong tự đăng nhập.
- Email trùng được báo lỗi; tài khoản bị khóa không đăng nhập được.

## Bật Google / Gmail

1. Trong Google Cloud Console / Google Auth Platform, cấu hình consent screen và tạo OAuth Client ID loại **Web application**.
2. Thêm Authorized JavaScript origin: `http://localhost:3000`. Nếu dùng chế độ Testing, thêm tài khoản Google của bạn vào Test users.
3. Đặt `GOOGLE_CLIENT_ID=<client-id>.apps.googleusercontent.com` trong `.env`.
4. Chạy `docker compose up -d --force-recreate backend`. Không cần client secret, không cần rebuild frontend: Client ID được lấy từ backend lúc chạy.
5. Mở lại `/login`, bấm nút Google, chọn tài khoản Gmail hoặc Google Workspace.

Hướng dẫn chính thức: https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid

Backend dùng google-auth xác minh chữ ký, audience, issuer, thời hạn và nonce gắn với cookie HttpOnly 5 phút. Lưu Google `sub` trong `users.google_subject`, tạo LEARNER khi đăng nhập lần đầu. Không lưu mật khẩu Google; cột hash của tài khoản Google chứa hash của chuỗi ngẫu nhiên không được cung cấp cho người dùng. Email đã đăng ký bằng mật khẩu phải tiếp tục dùng mật khẩu hiện có; chưa hỗ trợ liên kết hai phương thức. Chưa có xác minh email cho đăng ký bằng mật khẩu hoặc chức năng quên mật khẩu.

Migration bổ sung: `20261027_0005`. Chạy `docker compose run --rm backend alembic upgrade head` trước khi chạy backend mới. Không xóa DB hay volume.
