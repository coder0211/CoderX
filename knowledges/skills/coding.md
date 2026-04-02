# Skill: Coding (Native)

## Purpose
Guide CoderX to independently write code, fix bugs, and complete features using available tools (MCP Filesystem, Shell).

## Operating Principle
You do not delegate to another agent. You are the one executing directly.

### 4-Step Process: READ → PLAN → WRITE → VERIFY

#### 1. READ (Understand Context)
- Always use `mcp` → `filesystem/list_dir` to view the directory structure.
- Use `mcp` → `filesystem/read_file` to read the content of relevant files (models, existing logic).
- **Never edit a file without reading it first.**

#### 2. PLAN (Formulate approach)
- Identify the specific function/class/logic that needs to change.
- Ensure compliance with the project's coding style.

#### 3. WRITE (Execute)
- Use `mcp` → `filesystem/write_file` to create new or update existing files.
- When updating, write the entire new file content (full replacement) to avoid syntax errors.
- Handle errors and edge cases directly in the code.

#### 4. VERIFY (Validate)
- Use `shell` to run validation commands:
  - `pytest` / `npm test`: Run unit tests.
  - `python script_name.py`: Run the script directly.
  - `mypy` / `eslint`: Check for static errors.
- If VERIFY fails → return to step 1 to analyze the error and fix.

## Action Prompt Hints (Internal Thought)
When performing an `mcp` or `shell` action, clearly describe what you're doing:
- "Reading the content of config.py to check settings..."
- "Updating error handling logic in api/routes.py..."
- "Running the test suite to ensure the new feature doesn't break existing logic..."

## Completion Criteria
- Code has been successfully written to disk.
- Validation/test commands from VERIFY return a successful result (exit code 0).
- No leftover logic or junk files remain.
