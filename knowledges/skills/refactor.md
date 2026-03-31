# Skill: Refactoring

## Mục đích
Hướng dẫn CoderX refactor code — cải thiện cấu trúc mà không thay đổi behavior.

## Nguyên tắc vàng
> **Không bao giờ thay đổi behavior khi refactor.**
> Tests phải pass trước và sau khi refactor.

## Khi nào Refactor
- Code smell: function > 50 lines, class > 300 lines
- Duplication: cùng logic xuất hiện 3+ lần
- God class: 1 class làm quá nhiều thứ
- Magic numbers: số/string không có tên
- Deep nesting: if/for lồng > 3 cấp
- Long parameter list: function nhận > 4 params

## Refactoring Patterns

### Extract Method
```python
# Before
def process_order(order):
    # 30 lines of validation
    # 20 lines of calculation
    # 15 lines of notification

# After  
def process_order(order):
    validate_order(order)
    total = calculate_total(order)
    notify_user(order, total)
```

### Extract Constant
```python
# Before
if status == 3:  # magic number
# After
ORDER_STATUS_SHIPPED = 3
if status == ORDER_STATUS_SHIPPED:
```

### Replace Conditional with Polymorphism
```python
# Before
if type == "email": send_email()
elif type == "sms": send_sms()
# After
notifier = NotifierFactory.create(type)
notifier.send()
```

## Khi tạo Refactor prompt
```
Refactor the following files to improve code quality:
[list files]

Goals:
- [Specific refactoring goals based on code smells found]

Constraints:
- DO NOT change any public interfaces or function signatures
- DO NOT change behavior — all existing tests must still pass
- Refactor incrementally — one concern at a time

Steps:
1. Run existing tests first (if any) to establish baseline
2. Apply refactoring
3. Verify tests still pass
4. Document what was changed and why

When done: create `.coderx/step_{id}_done.json`
```

## Thứ tự ưu tiên
1. Fix bugs trước khi refactor
2. Viết tests trước khi refactor (nếu chưa có)
3. Refactor từng phần nhỏ, commit thường xuyên
4. Review sau khi refactor
