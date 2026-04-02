# Skill: Code Review

## Purpose
Guide CoderX to review code systematically — finding bugs, security issues, and improving quality.

## Review Checklist

### 1. Correctness
- [ ] Does the logic match the requirements?
- [ ] Are edge cases handled?
- [ ] Is error handling complete?
- [ ] No off-by-one errors?

### 2. Security
- [ ] Input validation / sanitization?
- [ ] SQL injection / XSS / CSRF risks?
- [ ] No secrets hardcoded in the code?
- [ ] Auth/Authorization correct?

### 3. Performance
- [ ] N+1 query issues?
- [ ] Unnecessary loops / computations?
- [ ] Memory leaks?
- [ ] Missing database indexes?

### 4. Code Quality
- [ ] Naming is clear, no confusing abbreviations?
- [ ] Functions are small enough, single responsibility?
- [ ] Duplication — can it be extracted?
- [ ] Dead code to remove?
- [ ] Comments where necessary?

### 5. Tests
- [ ] Are there unit tests?
- [ ] Test coverage sufficient for happy path and edge cases?
- [ ] Do the tests pass?

## Review Prompt Template
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

## Expected Output
- File `.coderx/review_report.md` with a list of issues
- CRITICAL/HIGH issues fixed directly
- Summary of issue counts by severity

## When to use
- After coding a new feature
- Before merging / committing
- When the user explicitly requests a review
