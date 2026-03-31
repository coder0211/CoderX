"""
CoderX — ChatGPT Task Planner
"Tech Lead" — phân tích task, chia thành steps nhỏ cho Antigravity thực thi
"""
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from openai import AsyncOpenAI

from config import config


class StepType(str, Enum):
    CODE = "code"         # Viết / tạo code mới
    MODIFY = "modify"     # Sửa code hiện có
    TEST = "test"         # Viết & chạy tests
    FIX = "fix"           # Sửa bugs / lỗi
    REVIEW = "review"     # Review & cải thiện code
    REFACTOR = "refactor" # Tái cấu trúc code
    DOCS = "docs"         # Viết documentation
    SHELL = "shell"       # Chạy shell command (không dùng Antigravity)


@dataclass
class Step:
    id: int
    type: StepType
    title: str                    # Mô tả ngắn gọn cho Telegram
    prompt: str                   # Prompt đầy đủ gửi cho Antigravity
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
3. **Viết prompt chi tiết** cho từng step — Antigravity Agent sẽ đọc và thực hiện
4. **Đảm bảo** có bước test và kiểm tra sau mỗi phần code quan trọng

Quy tắc khi tạo steps:
- Mỗi step phải đủ nhỏ để Antigravity thực hiện trong 1 lần gọi (5-15 phút)
- Step type: code | modify | test | fix | review | refactor | docs | shell
- Prompt phải TIẾNG ANH, rất cụ thể, bao gồm: context, yêu cầu, output mong đợi
- Prompt phải kết thúc bằng: "When done, create `.coderx/step_{id}_done.json` with {\"status\": \"done\", \"summary\": \"what you did\", \"files_changed\": []}"
- Steps type "shell" chỉ dùng cho: npm install, pip install, git operations, etc.
- Luôn có ít nhất 1 step test (nếu task có code)

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
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.conversation_history: list[dict] = []

    async def plan(
        self,
        user_request: str,
        workspace: str,
        context: str = "",
    ) -> ExecutionPlan:
        """
        Phân tích yêu cầu và tạo execution plan với các steps nhỏ.
        """
        user_content = f"Workspace hiện tại: {workspace}\n\n"
        if context:
            user_content += f"Context bổ sung:\n{context}\n\n"
        user_content += f"Yêu cầu: {user_request}"

        self.conversation_history.append({"role": "user", "content": user_content})

        response = await self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.conversation_history,
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        self.conversation_history.append({"role": "assistant", "content": raw})

        plan_data = json.loads(raw)
        return self._parse_plan(plan_data, workspace)

    async def refine_step(
        self,
        step: Step,
        error_output: str,
        workspace: str,
    ) -> Step:
        """
        Khi 1 step thất bại, nhờ ChatGPT tạo prompt sửa lỗi.
        """
        user_content = (
            f"Step {step.id} ({step.type}) gặp lỗi:\n\n"
            f"Original prompt:\n{step.prompt}\n\n"
            f"Error/Output:\n{error_output}\n\n"
            f"Hãy tạo một step FIX để giải quyết lỗi này."
        )

        response = await self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.conversation_history,
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        fix_data = json.loads(raw)

        # Tạo fix step
        fix_steps = fix_data.get("steps", [])
        if fix_steps:
            s = fix_steps[0]
            return Step(
                id=step.id,
                type=StepType.FIX,
                title=s.get("title", f"Fix step {step.id}"),
                prompt=s.get("prompt", ""),
                depends_on=step.depends_on,
                expected_files=s.get("expected_files", []),
            )
        return step

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
            # Inject done-marker instruction vào prompt nếu chưa có
            prompt = s.get("prompt", "")
            step_id = s.get("id", len(steps) + 1)
            if ".coderx/step_" not in prompt:
                prompt += (
                    f'\n\nIMPORTANT: When you have completed all tasks above, '
                    f'create the file `.coderx/step_{step_id}_done.json` '
                    f'with content: {{"status": "done", "summary": "brief summary of what you did", '
                    f'"files_changed": ["list of files you created or modified"]}}'
                )

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
