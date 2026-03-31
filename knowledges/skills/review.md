# Skill: Code Review

## Mục đích
Hướng dẫn CoderX review code một cách có hệ thống — tìm bugs, security issues, và cải thiện chất lượng.

## Checklist Review

### 1. Correctness
- [ ] Logic đúng với yêu cầu?
- [ ] Edge cases được handle?
- [ ] Error handling đầy đủ?
- [ ] Không có off-by-one errors?

### 2. Security
- [ ] Input validation / sanitization?
- [ ] SQL injection / XSS / CSRF risks?
- [ ] Secrets không hardcode trong code?
- [ ] Auth/Authorization đúng?

### 3. Performance
- [ ] N+1 query issues?
- [ ] Unnecessary loops / computations?
- [ ] Memory leaks?
- [ ] Missing indexes (database)?

### 4. Code Quality
- [ ] Naming rõ ràng, không abbreviation khó hiểu?
- [ ] Functions đủ nhỏ, single responsibility?
- [ ] Duplication — có thể extract không?
- [ ] Dead code cần xóa?
- [ ] Comments ở những chỗ cần thiết?

### 5. Tests
- [ ] Có unit tests?
- [ ] Test coverage đủ cho happy path và edge cases?
- [ ] Tests có chạy pass không?

## Khi tạo Review prompt
```
Review the following files for bugs, security issues, and code quality:
[list files]

Focus on:
1. Logic errors and edge cases
2. Security vulnerabilities  
3. Performance issues
4. Code quality and maintainability

For each issue found:
- File + line number (if possible)
- Severity: CRITICAL | HIGH | MEDIUM | LOW
- Description
- Suggested fix

Then:
- Apply fixes for CRITICAL and HIGH severity issues directly
- Create a review_report.md in .coderx/ with all findings

When done: create `.coderx/step_{id}_done.json`
```

## Output mong đợi
- File `.coderx/review_report.md` với danh sách issues
- Các CRITICAL/HIGH issues được fix trực tiếp
- Summary số issues theo severity

## Khi nào dùng
- Sau khi code một tính năng mới
- Trước khi merge / commit
- Khi user yêu cầu review cụ thể
