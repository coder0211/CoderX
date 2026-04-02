# Skill: Planning (PLANNING State)

## Purpose
Guide CoderX to execute the PLANNING step substantively — no idle loops, no meaningless iterations.

## Golden Rule
> **PLANNING is not "thinking inside your head". PLANNING means using a tool to gather information and form a concrete plan.**

---

## What PLANNING should do

In the `planning` state, the action MUST be one of:
1. **`filesystem/list_dir`** — to understand the project structure
2. **`filesystem/read_file`** — to read important files (README, config, main entry point)
3. **`shell: find . -name "*.py" | head -20`** — to quickly discover files

**NOT allowed**: Using PLANNING to "think" without calling a tool. Every iteration must have exactly 1 action.

---

## Output of PLANNING

After 1-2 PLANNING iterations, your `reasoning` must be able to answer:
- [ ] **Project structure**: Is this a Python/JS/web project? Where is the entry point?
- [ ] **Existing code**: Are there any existing files related to the task?
- [ ] **Dependencies**: What framework does the project use? Is there a `requirements.txt`/`package.json`?
- [ ] **Task scope**: Do we need to create new files or modify existing ones?

---

## Example of good PLANNING

```
Iteration 1 - PLANNING:
  action: filesystem/list_dir (path: ".")
  next_state: reading
  reasoning: "Need to inspect the project structure before starting"

Iteration 2 - READING:
  action: filesystem/read_file (path: "src/api/routes.py")
  next_state: coding
  reasoning: "Structure known, need to read current routes before adding an endpoint"
```

## Example of bad PLANNING (AVOID)

```
❌ Iteration 1 - PLANNING:
  action: shell "echo 'Starting planning...'"
  reasoning: "Planning in progress"  ← Meaningless, wastes an iteration
```

---

## When to exit PLANNING

Exit PLANNING as soon as you know:
- Which files to read/create/modify
- The overall approach

**Perfect PLANNING is not required** — move to READING, then adjust as needed.

## Maximum PLANNING iterations
- Simple task (create 1 file): **1 PLANNING iteration** is enough
- Complex task (multiple files, refactor): **maximum 2 PLANNING iterations**
- Still in PLANNING after 3 iterations: **force transition to READING**
