# Skill: Git Automation & Progress Tracking

## Purpose
Guide CoderX to automatically checkpoint work progress through Git, making it easy to track changes step-by-step (Atomic Commits).

## Automated Process
The Pipeline system automatically runs the following commands after each successful **Step**:

1. **Check Git:**
   ```bash
   git rev-parse --is-inside-work-tree
   ```
2. **Stage changes:**
   ```bash
   git add .
   ```
3. **Commit with [CoderX] prefix:**
   ```bash
   git commit -m "[CoderX] Step {id}: {title}"
   ```

## Instructions for the Agent (CoderX)
When you are inside the `AutonomousAgent` loop:
- You **do not need** to call `git commit` yourself unless you are performing a Git-specific task (like fixing a merge conflict or creating a new branch).
- The external Pipeline system will handle "checkpointing" after you complete a Mission Step.
- However, if you are making a critically important change and want to save it immediately, you may call the `shell` tool to commit manually.

## Commit Message Format
Always prefix with `[CoderX]` to distinguish from Eric's own code.
- Good example: `[CoderX] Step 2: Implement Dashboard UI`
- Bad example: `Fixed bugs`, `Update code`
