"""
CoderX — ChatGPT Task Planner
Senior Tech Lead: analyzes tasks and breaks them into discrete steps for the AutonomousAgent to execute.
"""
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from openai import AsyncOpenAI

from config import config
from prompts.loader import load_prompt


class StepType(str, Enum):
    CODE = "code"         # Create/implement code via MCP
    CREATE = "create"
    IMPLEMENT = "implement"
    BUILD = "build"
    MODIFY = "modify"     # Edit existing code via MCP
    EDIT = "edit"
    TEST = "test"         # Write/Run tests via Shell
    FIX = "fix"           # Fix bugs via Shell/MCP
    REVIEW = "review"     # Code analysis
    REFACTOR = "refactor" # Code cleanup
    DOCS = "docs"         # Documentation
    SHELL = "shell"       # Native shell commands


@dataclass
class Step:
    id: int
    type: StepType
    title: str                    # Mô tả ngắn gọn cho Telegram
    prompt: str                   # Hướng dẫn chi tiết cho bước này
    depends_on: list[int] = field(default_factory=list)
    shell_command: Optional[str] = None  # Nếu type == SHELL
    expected_files: list[str] = field(default_factory=list)  # Files dự kiến được tạo
    context: str = ""             # Context thêm từ steps trước


@dataclass
class ExecutionPlan:
    task_summary: str
    workspace: str
    steps: list[Step]
    strategy_analysis: str = ""
    total_steps: int = 0

    def __post_init__(self):
        self.total_steps = len(self.steps)





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
        # Thử sửa lỗi dấu phẩy thừa (trailing commas) nếu cần
        import re
        text = re.sub(r',\s*([\]}])', r'\1', text)
        return json.loads(text)


class TaskPlanner:
    def __init__(self):
        from llm.client import get_openai_client
        self.client = get_openai_client()
        self.conversation_history: list[dict] = []
        self._agents = self._load_agents()

    def _load_agents(self) -> str:
        from pathlib import Path
        agents_path = Path(__file__).parent.parent / "knowledges" / "AGENTS.md"
        if agents_path.exists():
            return agents_path.read_text()
        return ""

    async def plan(
        self,
        user_request: str,
        workspace: str,
        context: str = "",
    ) -> ExecutionPlan:
        """
        Phân tích yêu cầu và tạo execution plan với các steps nhỏ.
        """
        # Load memory automatically if not provided
        if not context:
            context = self._load_memory(workspace)

        system_prompt = load_prompt("planner_system") + (
            f"\n\n{self._agents}\n\n## Your Current Persona: Orchestrator (OpenClaw Style)\n"
            "You are currently acting as the **Orchestrator**. Your goal is to map out the strategy for the team."
        )

        user_content = f"Workspace: {workspace}\n\n"
        if context:
            user_content += f"Context (Long-Term Memory):\n{context}\n\n"
        user_content += f"Task: {user_request}"

        self.conversation_history.append({"role": "user", "content": user_content})

        response = await self.client.chat.completions.create(
            model=config.SMART_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *self.conversation_history,
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        self.conversation_history.append({"role": "assistant", "content": raw})

        plan_data = safe_json_loads(raw)
        return self._parse_plan(plan_data, workspace)

    def _load_memory(self, workspace: str) -> str:
        from pathlib import Path
        memory_path = Path(workspace) / ".coderx" / "MEMORY.md"
        if memory_path.exists():
            return memory_path.read_text(encoding="utf-8")
        return ""

    async def review_and_refine(
        self,
        plan: ExecutionPlan,
        latest_result: dict,
        project_map: str,
    ) -> ExecutionPlan:
        """
        Review lại plan sau mỗi bước và điều chỉnh nếu cần.
        """
        user_content = (
            f"Bản đồ Project hiện tại:\n{project_map}\n\n"
            f"Kết quả bước vừa xong:\n{json.dumps(latest_result, indent=2)}\n\n"
            f"Dựa trên tình hình hiện tại, hãy cập nhật các bước TIẾP THEO của plan. "
            f"Chỉ trả về JSON các bước còn lại từ ID {latest_result['id'] + 1} trở đi."
        )

        response = await self.client.chat.completions.create(
            model=config.SMART_MODEL,
            messages=[
                {"role": "system", "content": review_system},
                *self.conversation_history,
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        # Truncate history to save context cost
        if len(self.conversation_history) > 6:
            # Keep first message (initial context) + last 4 messages (2 rounds)
            self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-4:]

        raw = response.choices[0].message.content
        data = safe_json_loads(raw)
        
        # Merge new steps into the existing plan
        new_steps_data = data.get("steps", [])
        new_steps = []

        # Keep completed steps
        for s in plan.steps:
            if s.id <= latest_result["id"]:
                new_steps.append(s)

        # Add new/adjusted steps
        for s_data in new_steps_data:
            s_id = s_data.get("id")
            if s_id > latest_result["id"]:
                new_steps.append(self._parse_step(s_data))
        
        plan.steps = new_steps
        plan.total_steps = len(new_steps)
        return plan

    def _parse_step(self, s: dict) -> Step:
        return Step(
            id=s.get("id", 0),
            type=StepType(s.get("type", "code")),
            title=s.get("title", f"Step"),
            prompt=s.get("prompt", ""),
            depends_on=s.get("depends_on", []),
            shell_command=s.get("shell_command"),
            expected_files=s.get("expected_files", []),
        )

    async def summarize_results(
        self,
        plan: ExecutionPlan,
        step_results: list[dict],
    ) -> str:
        """
        Tổng hợp kết quả các steps thành báo cáo cho người dùng.
        """
        results_text = "\n".join(
            f"Step {r['id']} ({r['type']}): {r['status']} — {r.get('summary', '')}"
            for r in step_results
        )

        system_prompt = load_prompt("planner_summarize")
        user_content = (
            f"Task: {plan.task_summary}\n\n"
            f"Step results:\n{results_text}\n\n"
            "Write a concise 3-5 line summary report."
        )

        response = await self.client.chat.completions.create(
            model=config.FAST_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
        )

        return response.choices[0].message.content

    def _parse_plan(self, data: dict, default_workspace: str) -> ExecutionPlan:
        steps_data = data.get("steps", [])
        steps = []
        for i, s_data in enumerate(steps_data):
            step = self._parse_step(s_data)
            # Auto-fix IDs if missing or zero (ensure sequence starts at 1)
            if step.id == 0:
                step.id = i + 1
            steps.append(step)

        workspace = data.get("workspace") or default_workspace
        return ExecutionPlan(
            task_summary=data.get("task_summary", ""),
            workspace=workspace,
            steps=steps,
            strategy_analysis=data.get("strategy_analysis", ""),
        )
