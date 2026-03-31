# Skill: Coding

## Mục đích
Hướng dẫn CoderX viết code mới hoặc implement tính năng.

## Nguyên tắc khi code

### Trước khi viết
1. Đọc cấu trúc workspace (`_snapshot`) để biết project đang dùng tech gì
2. Tìm các file liên quan để hiểu context (models, routes, utils...)
3. Không tạo lại thứ đã có — tái sử dụng code hiện tại

### Khi viết prompt cho Antigravity
- Cung cấp đủ context: framework, language, project structure
- Chỉ rõ file nào cần tạo mới, file nào cần sửa
- Yêu cầu follow coding conventions của project (xem file hiện có)
- Nếu dùng dependencies mới → thêm vào package.json / requirements.txt
- Luôn handle errors, edge cases
- Đặt câu hỏi cụ thể: "Create `src/routes/users.py` with GET /users, POST /users, PUT /users/:id, DELETE /users/:id"

### Cấu trúc prompt tốt
```
Context: [Mô tả project, tech stack, files đã có]

Task: [Yêu cầu cụ thể — file nào, function nào, behavior gì]

Requirements:
- [Requirement 1]
- [Requirement 2]

Conventions: [Dựa trên code hiện có trong project]

Do NOT: [Những thứ không được làm — ví dụ: không xóa code cũ, không đổi interface]

When done: create `.coderx/step_{id}_done.json`
```

### Sau khi code xong
- Step tiếp theo nên là TEST để verify code chạy được
- Nếu phát hiện lỗi trong quá trình code → tạo FIX step ngay

## Step types phù hợp
- `code` — Tạo file/function/class mới
- `modify` — Sửa code đã có (thêm/xóa/sửa logic)
- `shell` — Cài dependencies sau khi thêm vào package file
