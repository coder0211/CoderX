# Skill: Refactoring

## Purpose
Guide CoderX to refactor code — improving structure without changing behavior.

## Golden Rule
> **Never change behavior when refactoring.**
> Tests must pass before and after the refactor.

## When to Refactor
- Code smell: function > 50 lines, class > 300 lines
- Duplication: same logic appears 3+ times
- God class: 1 class doing too many things
- Magic numbers: unnamed numbers/strings
- Deep nesting: if/for nesting > 3 levels
- Long parameter list: function takes > 4 params

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

## Refactor Prompt Template
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

## Priority Order
1. Fix bugs before refactoring
2. Write tests before refactoring (if none exist)
3. Refactor in small pieces, commit frequently
4. Review after refactoring
