# Skill: Debugging

## Purpose
Guide CoderX to handle errors systematically when a shell command or MCP tool returns an error.

## Golden Rule
> **Read the error first. Don't guess. Don't rewrite entire files without knowing the root cause.**

---

## 5-Step Debug Process: READ ERROR → LOCATE → ISOLATE → FIX → RE-VERIFY

### 1. READ ERROR (Analyze the error)
Extract precisely:
- **Error type**: `SyntaxError`, `ImportError`, `TypeError`, `ModuleNotFoundError`...
- **File + line number**: Always present in Python tracebacks
- **Message**: The specific error content

```
# Example traceback:
  File "app.py", line 42, in <module>
    from utils import helper   ← THIS is the location of the error
ImportError: cannot import name 'helper'
```

### 2. LOCATE (Find the cause)
- Use `filesystem/read_file` to read the failing file at the exact line number.
- Do NOT read the entire project — only read files directly related to the error.

### 3. ISOLATE (Determine root cause)
Common causes by error type:

| Error | Common Root Cause |
|---|---|
| `ImportError` / `ModuleNotFoundError` | Wrong module name, not installed, circular import |
| `SyntaxError` | Missing `:`, unclosed bracket, wrong indentation |
| `AttributeError` | Object is None, wrong attribute name, wrong type |
| `TypeError` | Wrong number of args, wrong type passed |
| `KeyError` | Dict key doesn't exist — use `.get()` instead |
| `FileNotFoundError` | Wrong path — check relative vs absolute |
| `PermissionError` | Workspace isolation violated |
| Exit code ≠ 0 | Read stderr, not just stdout |

### 4. FIX (Apply the fix)
- **Minimal surgery**: Only fix the exact line/function causing the error.
- If a full file rewrite is needed: read the file completely first, then write it back.
- **Do NOT** fix multiple files in one iteration — one fix at a time.

### 5. RE-VERIFY (Confirm the fix)
- Re-run the exact command that failed earlier.
- If a different error appears → repeat from step 1.
- **Maximum 3 debug cycles for the same issue** — if still failing → set `next_state: failed`.

---

## Anti-patterns (DO NOT do these)
- ❌ Delete failing code without understanding why
- ❌ Add `try/except` to silence errors without fixing the root cause
- ❌ Rewrite the entire file because of one failing line
- ❌ Guess the cause without reading the error message

## When to set `next_state: failed`
- The same error appears 3 times after 3 different fix attempts
- Error is caused by the environment (permission, missing binary) and cannot be self-fixed
- Error requires information from the user (API key, config secret)
