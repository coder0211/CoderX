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
    ANTIGRAVITY = "antigravity"   # Gọi Antigravity Agent để code
    SHELL = "shell"               # Chạy shell command
    OBSERVE = "observe"           # Chỉ quan sát, không làm gì mới
    MCP = "mcp"                   # Gọi tool từ external MCP server


class WorkflowState(str, Enum):
    PLANNING = "planning"             # Lên kế hoạch
    CODING = "coding"                 # Đang viết code/thực thi lệnh
    VERIFYING = "verifying"           # Kiểm thử, đọc lại kết quả
    AWAITING_REVIEW = "awaiting_review" # Chờ xác nhận từ người dùng
    COMPLETED = "completed"           # Hoàn thành
    FAILED = "failed"                 # Thất bại/Bó tay


@dataclass
class Action:
    type: ActionType
    title: str                          # Mô tả ngắn cho Telegram
    prompt: str                         # Prompt gửi Antigravity / desc hành động
    shell_command: Optional[str] = None # Nếu type == SHELL
    reasoning: str = ""                 # Tại sao chọn action này
    relevant_files: list[str] = field(default_factory=list) # Files cần đính kèm cho Antigravity
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
def build_reason_prompt(state: AgentState, workspace_snapshot: str, mcp_tools_summary: str = "") -> str:
    soul   = _load_soul()
    skills = _load_skills()
    iteration = len(state.iterations) + 1
    mcp_section = f"\n{mcp_tools_summary}\n" if mcp_tools_summary else ""
    return f"""You are CoderX — an autonomous AI developer hired by Eric Nguyen to build his projects.
{soul}

## Antigravity Agent Capabilities
You are controlling the Antigravity Agent. It is extremely powerful and can:
- Read/Edit multiple files simultaneously.
- Use a **Browser** to research docs, find libraries, or test web UIs.
- Use a **Terminal** to run tests, build projects, or debug.
- Self-correct errors by observing tool output.

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
1. REASON: What is the current state? What needs to be done next?
2. NEXT STATE: Should you move to 'coding', 'verifying', 'awaiting_review', or are you 'completed'?
3. ACTION: What single action to take to achieve this state?

Respond with JSON only. Field definitions:
- `next_state`: MUST be one of exactly: "planning", "coding", "verifying", "awaiting_review", "completed", "failed".
- `action.type`: MUST be one of exactly: "antigravity", "shell", "observe", "mcp". This is separate from `next_state`.

{{
  "reasoning": "Your analysis of current state and what needs to be done",
  "next_state": "planning | coding | verifying | awaiting_review | completed | failed",
  "confidence": 0-100,
  "decision_reason": "Why you made this decision",
  "action": {{
    "type": "antigravity | shell | observe | mcp",
    "title": "Short title for this action (Vietnamese OK)",
    "reasoning": "Why this specific action",
    "prompt": "Full detailed prompt for Antigravity agent (English, very specific)",
    "relevant_files": ["list", "of", "relative", "paths", "to", "attach"],
    "shell_command": null,
    "mcp_tool": null,
    "mcp_arguments": {{}}
  }}
}}

Rules for Antigravity Prompts:
- Be VERY specific. Give context, requirements, and expected behavior.
- ENCOURAGE the agent to use its Browser or Terminal if helpful (e.g. "Check documentation on [URL] if unsure").
- **VERIFICATION**: You MUST verify the results of previous actions in the workspace. Do not assume success if the monitor says 'idle_done'.
- **CRITICAL**: If you just requested a file/folder to be created, and it is NOT visible in the "Workspace State" (current files) above, the action FAILED or is still pending. **DO NOT** mark as 'complete' until you see the evidence in the snapshot.
- **Important**: Identify up to 10 most relevant files from the Workspace State above and list them in "relevant_files". These will be pre-opened for the agent.
- End prompts with: "When done, create `.coderx/step_{iteration}_done.json` with {{\"status\":\"done\",\"summary\":\"...\",\"files_changed\":[...]}}"

MCP Rules (type="mcp"):
- Use MCP when you need to call an external tool (filesystem, GitHub, DB, search, etc.).
- Set `mcp_tool` to the qualified name: "server_name/tool_name" (e.g. "filesystem/read_file").
- Set `mcp_arguments` to the tool's required parameters as a JSON object.
- Only use MCP tools that are listed in the Available MCP Tools section of this prompt.

Shell Rules:
- Only npm/pip/git/pytest/python/node/go/ls/cat/mkdir allowed.
- For git: follow Git Skill (safe auto, risky confirm).

Observation States:
- 'cancelled_continue': Antigravity timed out (15min) — check what was done and continue.
- 'idle_done': No file changes detected for 60s. **WARNING**: This may mean the agent finished OR it got stuck/failed to signal. You MUST verify the work now via the snapshot.
- 'git_confirm': User asked to confirm push — check git_confirmed.json.
- 'done': Agent explicitly signaled completion. Still, verify via snapshot.
"""


def _load_soul() -> str:
    soul_path = Path(__file__).parent.parent / "knowledges" / "SOUL.md"
    if soul_path.exists():
        return soul_path.read_text()
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
        action = Action(
            type=ActionType(action_data.get("type", "antigravity")),
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
