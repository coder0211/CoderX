# Skill: Git Operations

## Mục đích
Hướng dẫn CoderX sử dụng Git an toàn — tự động hóa các thao tác thông thường, hỏi xác nhận khi có rủi ro.

## Phân loại theo rủi ro

### ✅ TỰ ĐỘNG — Không cần hỏi
Các lệnh này an toàn, bot tự chạy:
```bash
git status
git log --oneline -10
git diff
git diff --staged
git add <specific-files>     # chỉ add files đã được chỉ định rõ
git commit -m "<message>"   # sau khi đã add
git pull                     # fast-forward pull
git stash
git stash pop
git branch                   # list branches
git checkout <existing-branch>
git fetch
```

### ⚠️ HỎI TRƯỚC — Cần confirm từ user
Các lệnh có thể gây mất data hoặc ảnh hưởng remote:
```bash
git push                     # ⚠️ Hỏi: "Push to origin/branch?"
git push --force             # ⚠️ Hỏi: "Force push — có chắc không?"
git reset --hard             # ⚠️ Hỏi: "Xóa tất cả uncommitted changes?"
git clean -fd                # ⚠️ Hỏi: "Xóa untracked files?"
git branch -D <branch>       # ⚠️ Hỏi: "Xóa branch <name>?"
git rebase                   # ⚠️ Hỏi: "Rebase onto <branch>?"
git merge <branch>           # ⚠️ Hỏi nếu không phải feature → main
```

### 🚫 KHÔNG BAO GIỜ TỰ ĐỘNG
```bash
git push --force-with-lease  # vẫn cần confirm
git reset --hard HEAD~N      # nguy hiểm — xóa commits
git reflog expire            # xóa history
```

## Commit Message Convention

Dùng Conventional Commits:
```
feat: add user authentication
fix: resolve null pointer in order processing
refactor: extract payment logic to service
test: add unit tests for user model
docs: update API documentation
chore: update dependencies
```

## Workflow khi cần Git

### 1. Sau khi code xong một tính năng
```
shell: git status
shell: git add src/features/new-feature/
shell: git commit -m "feat: implement <feature-name>"
[HỎI USER]: git push origin feature/new-feature?
```

### 2. Trước khi bắt đầu task mới
```
shell: git status  ← check có uncommitted changes không
shell: git pull    ← update code mới nhất
```

### 3. Khi có conflict
→ Báo user, không tự resolve conflict phức tạp

## Khi bot cần hỏi user
Gửi message Telegram theo format:
```
⚠️ [GIT CONFIRM]
Lệnh: `git push origin main`
Lý do: Đẩy code lên remote branch main
Có tiếp tục không? Trả lời YES/NO
```
Bot đợi tối đa 5 phút. Nếu không có trả lời → SKIP git step, báo cáo.

## Khi tạo Git prompt cho Antigravity
```
Git operations for this task:

Safe to run automatically:
- git status (check current state)
- git add [specific files listed above]
- git commit -m "type: description"

STOP and wait before running:
- Any push commands
- Any destructive operations (reset, clean, force)

If you need to push, create `.coderx/git_confirm_needed.json` with:
{"command": "git push ...", "reason": "why this is needed"}

When done: create `.coderx/step_{id}_done.json`
```
