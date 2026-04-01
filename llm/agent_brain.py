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
    OBSERVE           = "observe"           # Observe only
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
        for it in self.iterations[-5:]:  # Only last 5 to avoid token overflow
            obs = it.observation
            lines.append(
                f"[Iter {it.iteration}] {it.action.type.upper()}: {it.action.title}\n"
                f"  → Result: {obs.status} | {obs.summary[:200]}\n"
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

## Your Current Persona: Autonomous Developer
You are **CoderX**, a world-class autonomous senior software engineer. Your goal is to solve the **Current Mission** independently using your available tools. You do not delegate tasks to others; you perform them yourself.

## Your Atomic Toolset
You have direct access to the environment via:
1. **MCP Tools** (type="mcp"):
   - `filesystem/list_dir`: See directory contents.
   - `filesystem/read_file`: Read source code for context.
   - `filesystem/write_file`: Create or update files.
   - `filesystem/move_file`: Refactor project structure.
2. **Shell** (type="shell"):
   - Run tests (`pytest`, `npm test`).
   - Install dependencies (`pip`, `npm`).
   - Build and check types (`npm run build`, `mypy`).
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
- `action.type`: MUST be one of exactly: "shell", "observe", "mcp".

{{
  "reasoning": "Your analysis. Use this to provide architectural or UX feedback if needed.",
  "next_state": "planning | coding | verifying | arch_review | product_review | awaiting_review | completed | failed",
  "confidence": 0-100,
  "decision_reason": "Why you made this decision (Vietnamese OK)",
  "action": {{
    "type": "shell | observe | mcp",
    "title": "Short title for this action (Vietnamese OK)",
    "reasoning": "Why this specific action",
    "prompt": "Specific description of what you are trying to achieve (English)",
    "shell_command": "The actual shell command to run if type=shell",
    "mcp_tool": "qualified tool name if type=mcp",
    "mcp_arguments": {{}}
  }}
}}

## Guidelines for Success:
- **Think before you act**: Always read the files you intend to modify first.
- **Atomic steps**: One action at a time. Don't try to solve the whole mission in one iteration.
- **Verification**: After writing code, use the Shell to run tests or linting to verify your work.
- **Self-Correction**: If a Shell command or MCP tool fails, analyze the error and fix it in the next iteration.
- **Completeness**: Only mark as 'completed' when you have verified that the requirements are met.

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

        data = json.loads(raw)
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
