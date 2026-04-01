"""
CoderX — ChatGPT Task Planner
"Tech Lead" — phân tích task, chia thành steps nhỏ cho Native Agent thực thi
"""
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from openai import AsyncOpenAI

from config import config


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


SYSTEM_PROMPT = """Bạn là một Senior Software Architect kiêm Tech Lead & Product Manager.
Khi nhận yêu cầu từ người dùng, nhiệm vụ của bạn là:

1. **Phân tích Chiến lược (Strategy Analysis)**: Đánh giá yêu cầu về mặt UX và Kiến trúc. 
   - Nếu yêu cầu làm UI quá phức tạp -> Đề xuất phương án tối giản.
   - Nếu yêu cầu về tech gây lãng phí/over-engineering -> Đề xuất giải pháp bền vững.
2. **Chia nhỏ** thành các bước (steps) độc lập, rõ ràng.
3. **Tiêu chuẩn Senior**: Các bước coding PHẢI bao gồm viết Type Hints và Docstrings.
4. **Quy trình bắt buộc**: Mỗi khi có code mới, PHẢI có bước chạy linter (`ruff check`, `mypy`) và viết test (`pytest`).
5. **Refactor**: Luôn có 1 bước review/refactor sau khi code đã chạy được.
6. **Không viết tắt**: Các bước coding PHẢI yêu cầu viết toàn bộ nội dung file (Full File), không được phép dùng placeholder.

Quy tắc:
- Step type: code | modify | test | fix | review | refactor | docs | shell
- Luôn ưu tiên dùng `test` step để verify.
- Trả về JSON format (không thêm text khác).

{
  "strategy_analysis": "Phân tích Pro/Con về UX và Architecture của yêu cầu này (Tiếng Việt)",
  "task_summary": "Mô tả ngắn gọn task",
  "workspace": "...",
  "steps": [...]
}"""


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

        system_prompt = f"{self._agents}\n\n{SYSTEM_PROMPT}\n\n## Your Current Persona: Orchestrator (OpenClaw Style)\nYou are currently acting as the **Orchestrator**. Your goal is to map out the strategy for the team."
        
        user_content = f"Workspace hiện tại: {workspace}\n\n"
        if context:
            user_content += f"Context (Long-Term Memory):\n{context}\n\n"
        user_content += f"Yêu cầu: {user_request}"

        self.conversation_history.append({"role": "user", "content": user_content})

        response = await self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *self.conversation_history,
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        self.conversation_history.append({"role": "assistant", "content": raw})

        plan_data = json.loads(raw)
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
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": f"{self._agents}\n\n{SYSTEM_PROMPT}\n\n## Your Current Persona: Orchestrator (Strategy Review Mode)"},
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
        data = json.loads(raw)
        
        # Merge các bước mới vào plan hiện tại
        new_steps_data = data.get("steps", [])
        new_steps = []
        
        # Giữ lại các bước đã xong
        for s in plan.steps:
            if s.id <= latest_result['id']:
                new_steps.append(s)
        
        # Thêm các bước mới/điều chỉnh
        for s_data in new_steps_data:
            s_id = s_data.get("id")
            if s_id > latest_result['id']:
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

        response = await self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là Tech Lead. Tóm tắt kết quả công việc bằng tiếng Việt, ngắn gọn, rõ ràng.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Task: {plan.task_summary}\n\n"
                        f"Kết quả từng step:\n{results_text}\n\n"
                        "Viết báo cáo tổng kết ngắn gọn (3-5 dòng)."
                    ),
                },
            ],
            temperature=0.5,
        )

        return response.choices[0].message.content

    def _parse_plan(self, data: dict, default_workspace: str) -> ExecutionPlan:
        steps = []
        for s in data.get("steps", []):
            steps.append(self._parse_step(s))

        workspace = data.get("workspace") or default_workspace
        return ExecutionPlan(
            task_summary=data.get("task_summary", ""),
            workspace=workspace,
            steps=steps,
            strategy_analysis=data.get("strategy_analysis", ""),
        )
