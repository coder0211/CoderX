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
    total_steps: int = 0

    def __post_init__(self):
        self.total_steps = len(self.steps)


SYSTEM_PROMPT = """Bạn là một Senior Software Architect kiêm Tech Lead.
Khi nhận yêu cầu từ người dùng, nhiệm vụ của bạn là:

1. **Phân tích** yêu cầu kỹ thuật một cách toàn diện
2. **Chia nhỏ** thành các bước (steps) độc lập, rõ ràng, có thứ tự hợp lý
3. **Viết hướng dẫn chi tiết** cho từng step — CoderX sẽ tự thực hiện bằng công cụ MCP/Shell
4. **Đảm bảo** có bước test và kiểm tra sau mỗi phần code quan trọng

Quy tắc khi tạo steps:
- Step type: code | modify | test | fix | review | refactor | docs | shell
- Prompt phải TIẾNG ANH, rõ ràng, bao gồm: mục tiêu, yêu cầu, các file liên quan
- Luôn ưu tiên dùng `test` step để verify sau khi code.

Trả về JSON theo format sau (chỉ JSON, không thêm text khác):
{
  "task_summary": "Mô tả ngắn gọn task bằng tiếng Việt",
  "workspace": "path/to/workspace hoặc để trống nếu dùng default",
  "steps": [
    {
      "id": 1,
      "type": "code",
      "title": "Tạo cấu trúc project",
      "prompt": "Create the project structure for...",
      "depends_on": [],
      "shell_command": null,
      "expected_files": ["src/main.py", "requirements.txt"]
    }
  ]
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
        system_prompt = f"{self._agents}\n\n{SYSTEM_PROMPT}\n\n## Your Current Persona: Orchestrator (OpenClaw Style)\nYou are currently acting as the **Orchestrator**. Your goal is to map out the strategy for the team."
        
        user_content = f"Workspace hiện tại: {workspace}\n\n"
        if context:
            user_content += f"Context bổ sung:\n{context}\n\n"
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
                new_steps.append(self._parse_step(s_data, len(new_steps) + 1))
        
        plan.steps = new_steps
        plan.total_steps = len(new_steps)
        return plan

        return Step(
            id=step_id,
            type=StepType(s.get("type", "code")),
            title=s.get("title", f"Step {step_id}"),
            prompt=prompt,
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
            prompt = s.get("prompt", "")
            step_id = s.get("id", len(steps) + 1)
            steps.append(
                Step(
                    id=step_id,
                    type=StepType(s.get("type", "code")),
                    title=s.get("title", f"Step {step_id}"),
                    prompt=prompt,
                    depends_on=s.get("depends_on", []),
                    shell_command=s.get("shell_command"),
                    expected_files=s.get("expected_files", []),
                )
            )

        workspace = data.get("workspace") or default_workspace
        return ExecutionPlan(
            task_summary=data.get("task_summary", ""),
            workspace=workspace,
            steps=steps,
        )
