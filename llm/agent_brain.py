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
from prompts.loader import load_prompt


# ─── Enums & Data Models ──────────────────────────────────────────────────────

class ActionType(str, Enum):
    SHELL             = "shell"             # Run shell command
    MCP               = "mcp"               # Call external MCP tool


class WorkflowState(str, Enum):
    PLANNING       = "planning"       # Lên kế hoạch, chia nhỏ nhiệm vụ
    READING        = "reading"        # Đọc file/context — BẮT BUỘC trước CODING
    CODING         = "coding"         # Viết code, tạo file, sửa lỗi
    VERIFYING      = "verifying"      # Chạy test/lint — BẮT BUỘC trước COMPLETED
    ARCH_REVIEW    = "arch_review"    # Pushback: đề xuất thay đổi kiến trúc
    PRODUCT_REVIEW = "product_review" # Pushback: đề xuất thay đổi UX/UI
    COMPLETED      = "completed"      # CHỈ vào được từ VERIFYING
    FAILED         = "failed"         # Bó tay hoàn toàn


# ─── State Machine Transition Table ──────────────────────────────────────────
# Enforced at runtime in agent_loop.py — LLM không thể bypass
TRANSITION_TABLE: dict[WorkflowState, frozenset] = {
    WorkflowState.PLANNING:       frozenset({
        WorkflowState.READING, WorkflowState.CODING,
        WorkflowState.ARCH_REVIEW, WorkflowState.FAILED,
    }),
    WorkflowState.READING:        frozenset({
        WorkflowState.CODING, WorkflowState.PLANNING,
        WorkflowState.ARCH_REVIEW, WorkflowState.FAILED,
    }),
    WorkflowState.CODING:         frozenset({
        WorkflowState.VERIFYING, WorkflowState.READING, WorkflowState.CODING,
        WorkflowState.ARCH_REVIEW, WorkflowState.PRODUCT_REVIEW, WorkflowState.FAILED,
    }),
    WorkflowState.VERIFYING:      frozenset({
        WorkflowState.COMPLETED, WorkflowState.CODING,
        WorkflowState.READING, WorkflowState.FAILED,
    }),
    WorkflowState.ARCH_REVIEW:    frozenset({
        WorkflowState.PLANNING, WorkflowState.CODING, WorkflowState.FAILED,
    }),
    WorkflowState.PRODUCT_REVIEW: frozenset({
        WorkflowState.PLANNING, WorkflowState.CODING, WorkflowState.FAILED,
    }),
    WorkflowState.COMPLETED:      frozenset(),  # terminal
    WorkflowState.FAILED:         frozenset(),  # terminal
}


def validate_transition(
    current: WorkflowState,
    proposed: WorkflowState,
    has_verified: bool,
) -> tuple[WorkflowState, Optional[str]]:
    """
    Kiểm tra và sửa state transition nếu vi phạm rules.
    Returns (corrected_state, warning_message | None).
    """
    allowed = TRANSITION_TABLE.get(current, frozenset())

    # Hard gate 1: COMPLETED chỉ đạt được sau khi đã VERIFYING ít nhất 1 lần
    if proposed == WorkflowState.COMPLETED and not has_verified:
        return WorkflowState.VERIFYING, (
            "⚠️ [StateMachine] COMPLETED bị chặn — chưa VERIFYING. "
            "Buộc chuyển → VERIFYING."
        )

    # Hard gate 2: Transition không hợp lệ theo bảng
    if proposed not in allowed:
        fallback = WorkflowState.CODING
        allowed_names = ", ".join(s.value for s in allowed) or "none (terminal)"
        return fallback, (
            f"⚠️ [StateMachine] Invalid transition {current.value!r} → {proposed.value!r}. "
            f"Allowed: [{allowed_names}]. Fallback → {fallback.value!r}."
        )

    return proposed, None


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
            # Keep more context in history summary (1000 chars# ─── Knowledge Loaders ──────────────────────────────────────────────────
def _load_memory(workspace: str) -> str:
    memory_path = Path(workspace) / ".coderx" / "MEMORY.md"
    if memory_path.exists():
        return memory_path.read_text(encoding="utf-8")
    return ""


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
    """Load all skills from knowledges/skills/ and inject into the system prompt."""
    skills_dir = Path(__file__).parent.parent / "knowledges" / "skills"
    if not skills_dir.exists():
        return ""
    skill_texts = []
    for skill_file in sorted(skills_dir.glob("*.md")):
        content = skill_file.read_text().strip()
        skill_name = skill_file.stem.upper()
        skill_texts.append(f"### Skill: {skill_name}\n{content}")
    return "\n\n---\n\n".join(skill_texts) if skill_texts else ""


def build_reason_prompt(state: AgentState, workspace_snapshot: str, mcp_tools_summary: str = "") -> str:
    """Build the full system prompt for the agent's REASON phase.

    Loads the template from prompts/agent_reason.md and injects runtime variables.
    """
    return load_prompt(
        "agent_reason",
        agents=_load_agents(),
        soul=_load_soul(),
        memory=_load_memory(state.workspace) or "(No memory file yet)",
        skills=_load_skills() or "(no skills loaded)",
        mcp_section=f"\n{mcp_tools_summary}\n" if mcp_tools_summary else "",
        task_goal=state.task_goal,
        workspace=state.workspace,
        iteration=len(state.iterations) + 1,
        max_iterations=config.MAX_ITERATIONS,
        workspace_snapshot=workspace_snapshot or "Empty workspace",
        history=state.to_context() or "Nothing yet — this is the first action.",
    )


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
            model=config.SMART_MODEL,
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
        """Generate a final completion report using the agent_final_report prompt."""
        history = "\n".join(
            f"- [{it.iteration}] {it.action.title}: {it.observation.status} — {it.observation.summary[:100]}"
            for it in state.iterations
        )
        all_files: set[str] = set()
        for it in state.iterations:
            all_files.update(it.observation.files_changed)

        system_prompt = load_prompt("agent_final_report")
        user_content = (
            f"Task: {state.task_goal}\n\n"
            f"Outcome: {state.final_state.value}\n\n"
            f"Action history:\n{history}\n\n"
            f"Files created/modified: {', '.join(all_files) or 'none'}\n\n"
            "Write a 3-5 line report."
        )

        response = await self.client.chat.completions.create(
            model=config.FAST_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
        )
        return response.choices[0].message.content
