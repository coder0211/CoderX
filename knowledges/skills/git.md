# Skill: Git Operations

## Purpose
Guide CoderX to use Git safely — automating routine operations, and asking for confirmation when there is risk.

## Risk Classification

### ✅ AUTOMATIC — No confirmation needed
These commands are safe; the bot runs them autonomously:
```bash
git status
git log --oneline -10
git diff
git diff --staged
git add <specific-files>      # only add explicitly specified files
git commit -m "<message>"    # after files have been staged
git pull                      # fast-forward pull
git stash
git stash pop
git branch                    # list branches
git checkout <existing-branch>
git fetch
```

### ⚠️ ASK FIRST — Requires user confirmation
Commands that may cause data loss or affect the remote:
```bash
git push                      # ⚠️ Ask: "Push to origin/branch?"
git push --force              # ⚠️ Ask: "Force push — are you sure?"
git reset --hard              # ⚠️ Ask: "Discard all uncommitted changes?"
git clean -fd                 # ⚠️ Ask: "Delete untracked files?"
git branch -D <branch>        # ⚠️ Ask: "Delete branch <name>?"
git rebase                    # ⚠️ Ask: "Rebase onto <branch>?"
git merge <branch>            # ⚠️ Ask if not feature → main
```

### 🚫 NEVER AUTOMATE
```bash
git push --force-with-lease   # still requires confirmation
git reset --hard HEAD~N       # dangerous — deletes commits
git reflog expire             # deletes history
```

## Commit Message Convention

Use Conventional Commits:
```
feat: add user authentication
fix: resolve null pointer in order processing
refactor: extract payment logic to service
test: add unit tests for user model
docs: update API documentation
chore: update dependencies
```

## Git Workflow

### 1. After finishing a feature
```
shell: git status
shell: git add src/features/new-feature/
shell: git commit -m "feat: implement <feature-name>"
[ASK USER]: git push origin feature/new-feature?
```

### 2. Before starting a new task
```
shell: git status  ← check for uncommitted changes
shell: git pull    ← update to latest code
```

### 3. When there is a conflict
→ Report to user. Do not attempt to self-resolve complex conflicts.

## When the bot needs to ask the user
Send a Telegram message in this format:
```
⚠️ [GIT CONFIRM]
Command: `git push origin main`
Reason: Pushing code to remote main branch
Continue? Reply YES/NO
```
Bot waits up to 5 minutes. If no reply → SKIP git step and report.

## Git Prompt Template for CoderX
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
