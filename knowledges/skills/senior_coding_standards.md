# CoderX Senior Coding Standards

Đây là bộ tiêu chuẩn bắt buộc cho mọi Developer Agent tại CoderX. Mục tiêu là tạo ra mã nguồn chất lượng cao, dễ bảo trì và vận hành mượt mà.

## 1. Nguyên tắc "Không Giữ Chỗ" (No Placeholders)
- **TUYỆT ĐỐI CẤM** sử dụng các comment như `// logic goes here`, `/* TODO */`, hay `# implement later`.
- Mọi file được tạo hoặc chỉnh sửa phải **HOÀN THIỆN** và **CHẠY ĐƯỢC NGAY**.
- Nếu nhiệm vụ quá lớn, hãy chia nhỏ thành các module nhưng mỗi module phải đầy đủ logic của nó.

## 2. Kiến trúc & Cấu trúc (Architecture)
- **Tách biệt mối quan tâm (Separation of Concerns)**: HTML cho cấu trúc, CSS cho giao diện, JS cho logic.
- **Biến & Hằng số**: Đặt tên có ý nghĩa, sử dụng `const` và `let` thay vì `var`.
- **Error Handling**: Sử dụng `try-catch` cho các thao tác rủi ro (network, file I/O).

## 3. Thẩm mỹ & UX (UX/UI)
- Sử dụng Google Fonts (với dự án web) để tạo cảm giác cao cấp.
- Luôn đảm bảo tính **Responsive** (chạy được trên cả màn hình điện thoại và máy tính).
- Thêm các hiệu ứng chuyển cảnh (transitions) hoặc micro-animations để tăng trải nghiệm người dùng.

## 4. Kiểm soát Vận hành (Operational Safety)
- **Chặn lệnh treo máy**: Không bao giờ chạy các lệnh interactive liên tục (`npm start`, `watch`) trong shell tool trừ khi có cơ chế nền.
- **Normalize paths**: Luôn sử dụng đường dẫn tương đối từ gốc project để tránh lỗi "Access Denied".

---
*Mọi hành vi vi phạm tiêu chuẩn trên sẽ bị coi là lỗi Seniority.*
