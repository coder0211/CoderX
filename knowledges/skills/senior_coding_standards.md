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

## 3. Thẩm mỹ & UX (Visual Excellence)
CoderX không chỉ code để chạy, mà còn code để "đẹp". Mọi giao diện web phải đạt chuẩn:
- **Hệ thống Design Token**: Sử dụng CSS Variables cho màu sắc, khoảng cách (spacing), và typography để đảm bảo sự nhất quán.
- **Bố cục hiện đại**: Tuyệt đối sử dụng Flexbox và Grid. Tranh bố cục "thô" hoặc dùng float/table để dàn trang.
- **Typography cao cấp**: Luôn tích hợp Google Fonts (ví dụ: Inter, Outfit, Roboto). Tránh dùng font mặc định của trình duyệt. 
- **Bảng màu tinh tế**: Sử dụng các bảng màu hài hòa (HSL-based), có độ tương phản cao và hỗ trợ Dark Mode nếu cần.
- **Trải nghiệm mượt mà**: Thêm các hiệu ứng chuyển đổi (transitions) khi hover, micro-animations nhẹ nhàng, và bo góc (border-radius) hợp lý để tạo cảm giác hiện đại.
- **Responsive là mặc định**: Giao diện phải hiển thị tốt dường như trên mọi thiết bị (Mobile First approach).
- **Tuyệt đối không dùng HTML "trơ"**: Một senior không bao giờ viết HTML mà không có CSS đi kèm để làm nó trông chuyên nghiệp hơn.

## 4. Kiểm soát Vận hành (Operational Safety)
- **Chặn lệnh treo máy**: Không bao giờ chạy các lệnh interactive liên tục (`npm start`, `watch`) trong shell tool trừ khi có cơ chế nền.
- **Normalize paths**: Luôn sử dụng đường dẫn tương đối từ gốc project để tránh lỗi "Access Denied".

---
*Mọi hành vi vi phạm tiêu chuẩn trên sẽ bị coi là lỗi Seniority.*
