# Skill: Senior Coding Standards — CoderX Edition

## Mục đích
Nâng tầm CoderX từ việc "viết code chạy được" thành "viết code Senior": duy trì, mở rộng và bảo mật.

## 1. Nguyên tắc Chung (Core Principles)
- **KISS (Keep It Simple, Stupid):** Đừng làm phức tạp hóa vấn đề. Giải pháp đơn giản nhất thường là giải pháp tốt nhất.
- **DRY (Don't Repeat Yourself):** Tránh lặp lại logic. Sử dụng hàm và module để tái sử dụng.
- **YAGNI (You Ain't Gonna Need It):** Đừng xây dựng những thứ chưa cần tới.
- **SOLID:** Áp dụng cho các thiết kế Class và Module lớn.

## 2. Tiêu chuẩn Python (Pythonic Seniority)
- **Type Hints:** Luôn sử dụng type hints cho tất cả các hàm và biến (trừ trường hợp cực kỳ đơn giản).
- **Docstrings:** Mọi hàm/class phải có docstring theo chuẩn Google hoặc NumPy. Giải thích cả THỜI ĐIỂM và TẠI SAO, thay vì chỉ mô tả CÁI GÌ.
- **Logging:** Sử dụng module `logging` thay vì `print`. Không dùng `try/except: pass` mà không ghi log lỗi.
- **Naming:** Tuân thủ PEP 8 (`snake_case` cho hàm/biến, `PascalCase` cho class).

## 3. Quy trình Tự Phê bình (Self-Critique)
Trước khi coi là "Hoàn thành", CoderX phải tự hỏi:
1. "Nếu Eric đọc code này trong 6 tháng tới, anh ấy có hiểu ngay không?"
2. "Tôi đã xử lý các trường hợp biên (edge cases) chưa?"
3. "Có chỗ nào có thể tối ưu hiệu suất hoặc bộ nhớ không?"
4. "Code này có dễ viết Test không?"

## 4. Cưỡng chế Kiểm tra (Verification)
- **Linter:** Ưu tiên dùng `ruff` để dọn dẹp code rác và import dư thừa.
- **Type Checker:** Dùng `mypy` để đảm bảo an toàn về kiểu dữ liệu.
- **Tests:** Viết `pytest` cho các logic nghiệp vụ quan trọng.

---
**Ghi chú:** Code không có Type hints và Docstrings mặc định bị coi là "Junior" và cần được Refactor ngay lập tức.
