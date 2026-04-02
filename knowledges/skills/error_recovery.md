# Skill: Error Recovery

## Purpose
Guide CoderX to handle failed actions gracefully — without giving up or looping pointlessly.

## Golden Rule
> **Every error is data, not failure. But the same error repeated 3 times = failed.**

---

## Error Classification and Handling

### 🔴 Immediate Fatal Errors (set `next_state: failed`)
Cannot be self-fixed:
- **Missing secret / API key**: `OPENAI_API_KEY not set`
- **System permission denied**: File outside workspace
- **Network unreachable**: External service down
- **Disk full**: `No space left on device`

### 🟡 Environment Errors (Recoverable)
Can be fixed with shell commands:
```bash
# Dependency not installed
pip install package_name
npm install package_name

# Directory doesn't exist
mkdir -p path/to/dir

# Wrong Python version
python3 instead of python

# Node modules missing
npm install
```

### 🟢 Code Errors (Common — fix using the Debugging skill)
- Syntax error → read the file, fix the exact line
- Import error → check module/file name
- Logic error → read test failure, trace back the logic

---

## Recovery Decision Tree

```
Action failed?
    │
    ├─ Observation.status == "error"
    │       │
    │       ├─ First time seeing this error?
    │       │       YES → next_state: reading (analyze error output more carefully)
    │       │       NO  → next_state: coding (apply fix)
    │       │
    │       └─ Same error repeated 3 times?
    │               YES → next_state: failed
    │               NO  → continue
    │
    └─ Observation.status == "done" but output is wrong?
            → next_state: reading (analyze output, understand why it's wrong)
```

---

## Specific Recovery Techniques

### When MCP filesystem/write_file fails
```bash
# Check access permissions
ls -la path/to/dir

# Verify workspace path is correct
pwd
```

### When a shell command exits with code ≠ 0
Always read both stdout and stderr.
```bash
# Run with stderr redirect to see complete error
command 2>&1 | head -50
```

### When a test fails
- Read the **test output**, not the source code
- Find the `FAILED` or `AssertionError` line
- Debug from the test failure back to the code

---

## Escape Hatch (When you cannot fix it)

If you've tried 3 different approaches and still failing:
1. Set `next_state: failed`
2. In `reasoning`, clearly document:
   - **Root cause** — your best assessment
   - **What was tried** — list the 3 approaches attempted
   - **What's needed** — information or conditions required to fix it

This is not failure — this is accurate reporting so the user can take action.
