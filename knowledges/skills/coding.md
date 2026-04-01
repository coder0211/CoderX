# Skill: Coding (Native)

## Mục đích
Hướng dẫn CoderX tự mình viết code, sửa lỗi và hoàn thiện tính năng bằng cách sử dụng các công cụ có sẵn (MCP Filesystem, Shell).

## Nguyên tắc hoạt động
Bạn không gửi yêu cầu cho agent khác. Bạn là người trực tiếp thực thi.

### Quy trình 4 bước: READ → PLAN → WRITE → VERIFY

#### 1. READ (Tìm hiểu Context)
- Luôn dùng `mcp` -> `filesystem/list_dir` để xem cấu trúc thư mục.
- Dùng `mcp` -> `filesystem/read_file` để đọc nội dung các file liên quan (models, logic hiện tại). 
- **Không bao giờ sửa file khi chưa đọc nó.**

#### 2. PLAN (Lên phương án)
- Xác định cụ thể function/class/logic cần thay đổi.
- Đảm bảo tuân thủ coding style của project.

#### 3. WRITE (Thực thi)
- Dùng `mcp` -> `filesystem/write_file` để tạo mới hoặc cập nhật file.
- Khi cập nhật, hãy viết toàn bộ nội dung file mới (full replacements) để tránh lỗi cú pháp.
- handle errors và edge cases ngay trong code.

#### 4. VERIFY (Kiểm chứng)
- Dùng `shell` để chạy lệnh kiểm tra:
  - `pytest` / `npm test`: Chạy unit tests.
  - `python script_name.py`: Chạy thử script.
  - `mypy` / `eslint`: Kiểm tra lỗi tĩnh.
- Nếu VERIFY thất bại -> Quay lại bước 1 để phân tích lỗi và fix.

## Gợi ý cho Action Prompt (Internal Thought)
Khi bạn thực hiện một action `mcp` hoặc `shell`, hãy mô tả rõ:
- "Đang đọc nội dung file config.py để kiểm tra settings..."
- "Cập nhật logic xử lý lỗi trong api/routes.py..."
- "Chạy bộ test để đảm bảo feature mới không làm hỏng logic cũ..."

## Tiêu chuẩn Hoàn thành
- Code đã được ghi xuống đĩa thành công.
- Các lệnh check/test ở bước VERIFY trả về kết quả thành công (exit code 0).
- Không để lại logic thừa hoặc file rác.
