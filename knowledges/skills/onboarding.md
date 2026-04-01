# Skill: Project Onboarding

## Mục đích
Hướng dẫn CoderX tự động "khám phá" và hiểu kiến trúc của một repository mới mà không cần user giải thích.

## Quy trình Onboarding

### 1. Khám phá tổng quan (Snapshot)
- Bot tự liệt kê file tree cấp 1-2.
- Nhận diện các file "key" (README.md, package.json, requirements.txt, .env.example, Makefile, docker-compose.yml).

### 2. Phân tích kiến trúc thông qua Native Tools
Giao nhiệm vụ cho CoderX với prompt:
```
Explore this repository and analyze:
1. Main tech stack (Language, Frameworks, DB).
2. Project structure (Entry points, routes, logic, models).
3. How to run/test the project.
4. Key coding conventions (Linters, naming styles).

Write a comprehensive summary into `.coderx/onboarding.md`.
```

### 3. Lưu trữ tri thức
- File `.coderx/onboarding.md` sẽ được CoderX đọc và đưa vào context cho mọi task sau này.

## Khi nào chạy Onboard
- Khi user gửi lệnh `/onboard`.
- Khi bot phát hiện workspace mới mà chưa có folder `.coderx/`.

## Native Agent Instructions for Onboard
- Sử dụng Terminal để `cat` các file config.
- Sử dụng File tree để crawl folders.
- Sử dụng Browser nếu cần tra cứu một config/framework lạ có trong project.
- Output phải là Tiếng Việt hoặc Song ngữ (Anh-Việt).
