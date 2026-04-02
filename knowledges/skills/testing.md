# Skill: Testing & Verification (VERIFYING State)

## Purpose
Guide CoderX to perform VERIFYING substantively — must run a tool, not just "mentally review" the work.

## Golden Rule
> **VERIFYING is the ONLY state that leads to COMPLETED. Take it seriously.**

---

## What VERIFYING should do

In the `verifying` state, the action MUST be a **shell command**. No MCP write operations.

### By project type:

#### Python project
```bash
# 1. Syntax check (fastest)
python -m py_compile path/to/file.py

# 2. Import check
python -c "import module_name"

# 3. Run tests
pytest tests/ -v --tb=short

# 4. Type check (if mypy is available)
mypy src/ --ignore-missing-imports

# 5. Lint
ruff check .
```

#### JavaScript / Node.js project
```bash
# 1. Syntax check
node --check src/index.js

# 2. Run tests
npm test

# 3. Lint
npx eslint src/

# 4. Build check (if applicable)
npm run build 2>&1 | tail -20
```

#### HTML/CSS/Static
```bash
# 1. Check file exists and is not empty
wc -l index.html

# 2. Basic HTML structure check
grep -c "</html>" index.html  # must equal 1

# 3. Check CSS variables are defined
grep "var(--" index.css | wc -l
```

#### Bash script
```bash
bash -n script.sh  # syntax check only, does not execute
shellcheck script.sh  # if available
```

---

## Decision after VERIFYING

| Result | next_state | Action |
|---|---|---|
| All tests pass, exit 0 | `completed` | Report success |
| Syntax error | `coding` | Fix the exact failing line |
| Test failure | `reading` | Read test output, find the file to fix |
| Command not found | `coding` | Install the missing dependency first |

---

## Anti-patterns (DO NOT do these)
- ❌ Set `next_state: completed` without running any shell command
- ❌ Use `cat file.py` as "verification" — that is READING, not VERIFYING
- ❌ Ignore error output and continue writing new code

---

## Minimal Verification (when no test suite exists)

If the project has no test suite, the minimum VERIFYING is:

```bash
# Python: successful import
python -c "from module import MainClass; print('OK')"

# JS: node doesn't crash
node -e "require('./src/index')" 2>&1

# Any: file exists and is not empty
test -s path/to/output/file && echo "OK" || echo "EMPTY/MISSING"
```

Only after the command above exits with code 0 → may set `next_state: completed`.
