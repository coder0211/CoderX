import os
from pathlib import Path
from datetime import datetime
from typing import List
from llm.planner import ExecutionPlan, Step

class PlanManager:
    """
    Quản lý lộ trình thực hiện (.coderx/PLAN.md).
    Giúp User và Agent theo dõi tiến độ công việc theo thời gian thực.
    """

    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.coderx_dir = self.workspace / ".coderx"
        self.plan_file = self.coderx_dir / "PLAN.md"
        self._ensure_exists()

    def _ensure_exists(self):
        """Đảm bảo thư mục .coderx tồn tại."""
        self.coderx_dir.mkdir(parents=True, exist_ok=True)

    def initialize_plan(self, plan: ExecutionPlan):
        """Khởi tạo file PLAN.md từ ExecutionPlan."""
        content = [
            "# 📋 CoderX Roadmap (Active Plan)",
            f"**Mục tiêu:** {plan.task_summary}",
            f"**Workspace:** `{plan.workspace}`",
            f"**Cập nhật lần cuối:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "## 🛣️ Các bước thực hiện\n"
        ]
        
        for step in plan.steps:
            content.append(f"- [ ] **Bước {step.id}:** {step.title}")
            content.append(f"  - *Mô tả:* {step.prompt[:200]}...")
            
        self.plan_file.write_text("\n".join(content), encoding="utf-8")

    def update_step_status(self, step_id: int, status: str, summary: str = ""):
        """Cập nhật trạng thái của một bước trong PLAN.md."""
        if not self.plan_file.exists():
            return

        lines = self.plan_file.read_text(encoding="utf-8").split("\n")
        new_lines = []
        
        icon = "✅" if status in ("completed", "done", "idle_done") else ("❌" if status == "failed" else "⏳")
        check = "x" if status in ("completed", "done", "idle_done") else " "
        
        for line in lines:
            if line.startswith(f"- [ ] **Bước {step_id}:**") or line.startswith(f"- [x] **Bước {step_id}:**"):
                # Cập nhật line chính
                title = line.split(":**")[1].strip()
                new_lines.append(f"- [{check}] **Bước {step_id}:** {title} {icon}")
            else:
                new_lines.append(line)
        
        # Thêm log tóm tắt xuống cuối file nếu cần (dạng history mini)
        new_lines.append(f"\n> **Update Step {step_id} ({status}):** {summary[:150]}...")
        
        self.plan_file.write_text("\n".join(new_lines), encoding="utf-8")

    def write_implementation_strategy(self, strategy_text: str):
        """Ghi bản thiết kế chi tiết vào .coderx/IMPLEMENTATION_PLAN.md."""
        impl_plan_path = self.coderx_dir / "IMPLEMENTATION_PLAN.md"
        content = (
            "# 🏗️ Strategic Implementation Plan\n"
            "Bản thiết kế này được CoderX lập ra trước khi thực hiện dự án.\n\n"
            f"**Thời gian:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "---\n\n"
            f"{strategy_text}"
        )
        impl_plan_path.write_text(content, encoding="utf-8")

    def get_plan_context(self) -> str:
        """Trả về nội dung PLAN.md để làm context cho agent."""
        if self.plan_file.exists():
            return self.plan_file.read_text(encoding="utf-8")
        return ""
