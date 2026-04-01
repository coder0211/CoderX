"""
CoderX — Agent Brain (Autonomous Decision Engine)
ChatGPT đóng vai Tech Lead — tự quan sát, tự quyết định, tự sửa lỗi.
Implements ReAct loop: Reason → Act → Observe → Repeat until DONE.
"""
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from config import config


# ─── Enums & Data Models ──────────────────────────────────────────────────────

class ActionType(str, Enum):
    SHELL             = "shell"             # Run shell command
    MCP               = "mcp"               # Call external MCP tool


class WorkflowState(str, Enum):
    PLANNING = "planning"             # Lên kế hoạch
    CODING = "coding"                 # Đang viết code/thực thi lệnh
    VERIFYING = "verifying"           # Kiểm thử, đọc lại kết quả
    AWAITING_REVIEW = "awaiting_review" # Chờ xác nhận từ người dùng
    ARCH_REVIEW = "arch_review"       # Xem xét lại kiến trúc
    PRODUCT_REVIEW = "product_review" # Xem xét lại UX/UI
    COMPLETED = "completed"           # Hoàn thành
    FAILED = "failed"                 # Thất bại/Bó tay


@dataclass
class Action:
    type: ActionType
    title: str                          # Mô tả ngắn cho Telegram
    prompt: str                         # Prompt cho Native Agent
    shell_command: Optional[str] = None # Nếu type == SHELL
    reasoning: str = ""                 # Tại sao chọn action này
    relevant_files: list[str] = field(default_factory=list) # Files cần đính kèm cho Native Tools
    mcp_tool: Optional[str] = None      # Nếu type == MCP: "server/tool_name"
    mcp_arguments: dict = field(default_factory=dict)  # Nếu type == MCP: tham số của tool


@dataclass
class Observation:
    action: Action
    status: str                         # done | idle_timeout | timeout | error
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    shell_output: str = ""
    elapsed: float = 0.0


@dataclass
class AgentIteration:
    iteration: int
    action: Action
    observation: Observation
    next_state: WorkflowState
    decision_reason: str = ""
    confidence: int = 0                 # 0-100 task hoàn thành


@dataclass
class AgentState:
    task_goal: str
    workspace: str
    iterations: list[AgentIteration] = field(default_factory=list)
    workspace_files: list[str] = field(default_factory=list)
    final_state: WorkflowState = WorkflowState.PLANNING
    final_summary: str = ""

    def to_context(self) -> str:
        """Tóm tắt lịch sử cho ChatGPT."""
        if not self.iterations:
            return "No actions taken yet."

        lines = []
        for it in self.iterations[-3:]:  # Limit to last 3 to save tokens
            obs = it.observation
            # Keep more context in history summary (1000 chars)
            lines.append(
                f"[Iter {it.iteration}] {it.action.type.upper()}: {it.action.title}\n"
                f"  → Result: {obs.status} | {obs.summary[:1000]}\n"
                f"  → Files changed: {', '.join(obs.files_changed[:5]) or 'none'}\n"
                f"  → Next State: {it.next_state} (confidence: {it.confidence}%)"
            )
        return "\n\n".join(lines)


# ─── System Prompts ───────────────────────────────────────────────────────────
def _load_memory(workspace: str) -> str:
    memory_path = Path(workspace) / ".coderx" / "MEMORY.md"
    if memory_path.exists():
        return memory_path.read_text(encoding="utf-8")
    return ""

def build_reason_prompt(state: AgentState, workspace_snapshot: str, mcp_tools_summary: str = "") -> str:
    soul   = _load_soul()
    agents = _load_agents()
    skills = _load_skills()
    memory = _load_memory(state.workspace)
    iteration = len(state.iterations) + 1
    mcp_section = f"\n{mcp_tools_summary}\n" if mcp_tools_summary else ""
    return f"""{agents}
{soul}

## OpenClaw Memory Bridge (Shared Context)
{memory if memory else '(No memory file yet)'}

## Your Current Persona: Senior Autonomous Developer
You are **CoderX**, a pragmatic and world-class Senior Software Engineer. You write clean, maintainable, and type-safe code. You don't just "make it work"; you "make it right."

## Senior Engineering Principles
1. **Quality over Speed:** Never compromise on readability, types, or docstrings.
2. **Visual Excellence**: Your UI code must be premium, responsive, and modern. Low-quality, "raw" HTML is a failure.
3. **Standardization:** Follow PEP 8 and use Type Hints for all Python logic.
4. **Robustness:** Handle edge cases and errors gracefully using logging.
5. **Self-Review:** Before taking an action, ask yourself: "Is this the most maintainable and elegant way?"
6. **Verification is Mandatory:** You are NOT allowed to mark a task as 'completed' until you have verified it.

## Your Atomic Toolset
You have direct access to the environment via:
1. **MCP Tools** (type="mcp"):
   - `filesystem/list_dir`: See directory contents.
   - `filesystem/read_file`: Read source code for context.
   - `filesystem/write_file`: Create or update files.
   - `filesystem/move_file`: Refactor project structure.
2. **Shell** (type="shell"):
   - Run tests (`pytest`, `npm test`).
   - Run linters (`ruff check .`, `mypy .`).
   - Install dependencies (`pip`, `npm`).
   - Git operations.

## Skills Reference
{skills if skills else "(no skills loaded)"}
{mcp_section}

## Current Mission
Goal: {state.task_goal}
Workspace: {state.workspace}
Iteration: {iteration} / {config.MAX_ITERATIONS}

## Workspace State (current files)
{workspace_snapshot or "Empty workspace"}

## History (what you've done so far)
{state.to_context() or "Nothing yet — this is the first action."}

## Your Task Now
Based on the mission, workspace state, and history above:
1. REASON: Analyze the current state. What is missing? What errors occurred?
2. STRATEGIZE: Does the current path align with **Product & Architecture** principles in SOUL.md?
   - If you see a better UX or simpler architecture, **Push Back** by suggesting it in your reasoning and setting `next_state` to `product_review` or `arch_review`.
3. PLAN: Formulate the next atomic step to move closer to the goal.
4. ACT: Execute the step using a single action (MCP or Shell).
5. NEXT STATE: Should you move to 'coding', 'verifying', 'arch_review', 'product_review', 'awaiting_review', or are you 'completed'?

Respond with JSON only. Field definitions:
- `next_state`: MUST be one of exactly: "planning", "coding", "verifying", "arch_review", "product_review", "awaiting_review", "completed", "failed".
- `action.type`: MUST be one of exactly: "shell", "mcp".

{{
  "reasoning": "Your analysis. Use this to provide architectural or UX feedback if needed.",
  "next_state": "planning | coding | verifying | arch_review | product_review | awaiting_review | completed | failed",
  "confidence": 0-100,
  "decision_reason": "Why you made this decision (Vietnamese OK)",
  "action": {{
    "type": "shell | mcp",
    "title": "Short title for this action (Vietnamese OK)",
    "reasoning": "Why this specific action",
    "prompt": "Specific description of what you are trying to achieve (English)",
    "shell_command": "The actual shell command to run if type=shell",
    "mcp_tool": "qualified tool name if type=mcp",
    "mcp_arguments": {{}}
  }}
}}

## Senior Developer Persona:
- **Quality First**: You are a [Senior Full-Stack Engineer]. Your code must be production-ready, clean, and well-structured.
- **Architectural Thinking**: Before coding, briefly mention the modules or patterns you use.
- **Design System First**: For UI tasks, your first step should be defining a set of CSS Variables (Colors, Fonts, Spacing) to ensure a premium look.
- **Error Handling**: Always include basic error handling and edge case checks.

## Strict Anti-Laziness Rules:
- **NO IDLE ITERATIONS**: You are strictly FORBIDDEN from taking a 'no-op' action. You must always use a tool (MCP or Shell) to either gather info (read_file, list_dir) or make a change (write_file). Never suggest 'observing' without a tool.
- **ITERATION BUDGET**: You have a limited budget of iterations. Every wasted iteration (like idle planning) brings you closer to failure. ACT NOW.
- **NO PLACEHOLDERS**: Never use comments like `// implement logic here`. You MUST provide the full, working implementation in a single `write_file` call.
- **Complete Units**: Every file you create or edit must be a fully functional component. Partial implementations are considered failures.
- **No Self-Help**: Do not ask the user for instructions. You are the expert.

## Operational Safety:
- **No Blocking Commands**: Never run `http.server`, `npm start`, or any command that does not terminate. They will hang your process.
- **Verification**: Use `ls`, `cat`, or `lint` (if available) to verify results, not visual 'open' calls unless strictly necessary for UI testing.

## Guidelines for Success:
- **Think before you act**: Always read the files you intend to modify first.
- **Atomic steps**: One action at a time. Don't try to solve the whole mission in one iteration.
- **Verification**: After writing code, use the Shell to run tests or linting to verify your work.
- **Self-Correction**: If a Shell command or MCP tool fails, analyze the error and fix it in the next iteration.
- **Completeness**: Only mark as 'completed' when you have verified that the requirements are met.
- **Full Context**: Ensure all necessary imports and helper functions are included in the generated code.

## Workspace Isolation & Security Rules:
- **Jailbreak Restriction**: You are strictly confined to the workspace directory: `{state.workspace}`. 
- **Relative Paths Only**: Always use paths relative to the root. DO NOT use absolute paths (starting with `/` or `~`) unless they are children of the workspace.
- **No Breakouts**: Do not attempt to use `../` to access files above the workspace root. 
- **CWD Awareness**: Your Current Working Directory (CWD) is ALWAYS the workspace root: `{state.workspace}`. 
- **The Dot (`.`)**: Calling tools with path `.` or `./` refers to this workspace root. You have FULL PERMISSION to access this root.
- **Jailbreak Restriction**: You are strictly confined to this workspace. Do not use absolute paths outside it or `../` to escape.

MCP Rules (type="mcp"):
- Use MCP for all filesystem operations.
- Set `mcp_tool` to "filesystem/read_file", "filesystem/write_file", etc.
- Set `mcp_arguments` accurately according to the tool's schema.

Shell Rules:
- Use Shell for tests, builds, and dependency management.
- DO NOT use shell (cat, echo, mkdir) for filesystem tasks if MCP filesystem tools are available.
"""


def _load_soul() -> str:
    soul_path = Path(__file__).parent.parent / "knowledges" / "SOUL.md"
    if soul_path.exists():
        return soul_path.read_text()
    return ""


def _load_agents() -> str:
    agents_path = Path(__file__).parent.parent / "knowledges" / "AGENTS.md"
    if agents_path.exists():
        return agents_path.read_text()
    return ""


def _load_skills() -> str:
    """Load tất cả skills từ knowledges/skills/ để inject vào system prompt."""
    skills_dir = Path(__file__).parent.parent / "knowledges" / "skills"
    if not skills_dir.exists():
        return ""

    skill_texts = []
    for skill_file in sorted(skills_dir.glob("*.md")):
        content = skill_file.read_text().strip()
        skill_name = skill_file.stem.upper()
        skill_texts.append(f"### Skill: {skill_name}\n{content}")

    return "\n\n---\n\n".join(skill_texts) if skill_texts else ""


def safe_json_loads(text: str) -> dict:
    """Xử lý JSON an toàn hơn, loại bỏ markdown backticks nếu có."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        text = re.sub(r',\s*([\]}])', r'\1', text)
        return json.loads(text)


# ─── Agent Brain ──────────────────────────────────────────────────────────────

class AgentBrain:
    """
    ChatGPT-powered decision engine.
    Nhận state, trả về action tiếp theo cần thực hiện.
    """

    def __init__(self):
        from llm.client import get_openai_client
        self.client = get_openai_client()
        self._messages: list[dict] = []

    async def reason(
        self,
        state: AgentState,
        workspace_snapshot: str,
        mcp_tools_summary: str = "",
    ) -> tuple[Action, WorkflowState, int, str]:
        """
        ReAct: REASON phase.
        Phân tích state → quyết định next action.

        Returns:
            (action, next_state, confidence, decision_reason)
        """
        system_prompt = build_reason_prompt(state, workspace_snapshot, mcp_tools_summary)

        # Build conversation (keep history for continuity)
        if not self._messages:
            self._messages.append({
                "role": "system",
                "content": system_prompt,
            })
        else:
            # Update system with latest state
            self._messages[0] = {"role": "system", "content": system_prompt}

        # Truncate messages if they exceed 10 to save context costs
        # Keep index 0 (system) and index 1 (initial goal)
        if len(self._messages) > 10:
            system_msg = self._messages[0]
            initial_user = self._messages[1]
            # Keep the last 6 messages (3 turns of user/assistant)
            self._messages = [system_msg, initial_user] + self._messages[-6:]

        # Add observation from last iteration
        if state.iterations:
            last = state.iterations[-1]
            obs_msg = (
                f"[Observation from iteration {last.iteration}]\n"
                f"Action taken: {last.action.title}\n"
                f"Result: {last.observation.status}\n"
                f"Summary: {last.observation.summary}\n"
                f"Files changed: {', '.join(last.observation.files_changed) or 'none'}"
            )
            self._messages.append({"role": "user", "content": obs_msg})

        # First call
        if len(self._messages) == 1:
            self._messages.append({
                "role": "user",
                "content": f"Start working on the mission: {state.task_goal}",
            })

        response = await self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=self._messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        self._messages.append({"role": "assistant", "content": raw})

        data = safe_json_loads(raw)
        action_data = data.get("action", {})
        
        raw_action_type = action_data.get("type", "mcp")
        try:
            parsed_action_type = ActionType(raw_action_type)
        except ValueError:
            from orchestrator.logger import log
            log(
                f"[AgentBrain] Invalid action.type: '{raw_action_type}' → fallback to 'mcp'",
                category="Brain",
                style="yellow",
            )
            parsed_action_type = ActionType.MCP

        action = Action(
            type=parsed_action_type,
            title=action_data.get("title", "Performing action"),
            prompt=action_data.get("prompt", ""),
            shell_command=action_data.get("shell_command"),
            reasoning=action_data.get("reasoning", ""),
            relevant_files=action_data.get("relevant_files", []),
            mcp_tool=action_data.get("mcp_tool"),
            mcp_arguments=action_data.get("mcp_arguments") or {},
        )

        raw_state = data.get("next_state", "coding")
        try:
            next_state = WorkflowState(raw_state)
        except ValueError:
            from orchestrator.logger import log
            log(
                f"[AgentBrain] Invalid next_state value: '{raw_state}' → fallback to 'coding'",
                category="Brain",
                style="yellow",
            )
            next_state = WorkflowState.CODING
        confidence = int(data.get("confidence", 0))
        decision_reason = data.get("decision_reason", "")

        return action, next_state, confidence, decision_reason

    async def generate_final_report(self, state: AgentState) -> str:
        """Tạo báo cáo cuối cùng bằng tiếng Việt."""
        history = "\n".join(
            f"- [{it.iteration}] {it.action.title}: {it.observation.status} — {it.observation.summary[:100]}"
            for it in state.iterations
        )
        all_files = set()
        for it in state.iterations:
            all_files.update(it.observation.files_changed)

        response = await self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là CoderX — developer tự hành được Eric Nguyen thuê. Viết báo cáo kết quả ngắn gọn bằng tiếng Việt để gửi cho Eric.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Nhiệm vụ: {state.task_goal}\n\n"
                        f"Kết quả: {state.final_state}\n\n"
                        f"Lịch sử hành động:\n{history}\n\n"
                        f"Files đã tạo/sửa: {', '.join(all_files) or 'none'}\n\n"
                        "Viết báo cáo 3-5 dòng."
                    ),
                },
            ],
            temperature=0.4,
        )
        return response.choices[0].message.content
