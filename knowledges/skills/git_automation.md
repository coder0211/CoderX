# Skill: Git Automation & Progress Tracking

## Mục đích
Hướng dẫn CoderX cách tự động lưu trữ tiến trình công việc thông qua Git, giúp Eric dễ dàng theo dõi các thay đổi theo từng bước (Atomic Commits).

## Quy trình Tự động
Hệ thống Pipeline sẽ tự động thực hiện các lệnh sau sau mỗi **Step** thành công:

1. **Kiểm tra Git:** 
   ```bash
   git rev-parse --is-inside-work-tree
   ```
2. **Stage thay đổi:**
   ```bash
   git add .
   ```
3. **Commit với prefix [CoderX]:**
   ```bash
   git commit -m "[CoderX] Step {id}: {title}"
   ```

## Hướng dẫn cho Agent (CoderX)
Khi bạn đang ở trong `AutonomousAgent` loop:
- Bạn **không cần** tự gọi `git commit` trừ khi bạn đang thực hiện một task chuyên biệt về Git (như sửa lỗi merge, tạo branch mới).
- Hệ thống Pipeline bên ngoài sẽ lo việc "chụp ảnh" (checkpoint) sau khi bạn hoàn thành một Mission Step.
- Tuy nhiên, nếu bạn thấy mình đang thực hiện một thay đổi cực kỳ quan trọng và muốn "lưu" ngay lập tức, bạn có thể gọi tool `shell` để commit thủ công.

## Định dạng Commit Message
Luôn bắt đầu bằng `[CoderX]` để phân biệt với code của Eric.
- Ví dụ tốt: `[CoderX] Step 2: Triển khai giao diện Dashboard`
- Ví dụ xấu: `Fixed bugs`, `Update code`
