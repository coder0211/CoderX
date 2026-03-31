"""
CoderX — OpenClaw-Style Orchestrator
High-level loop: Plan -> Review -> Delegate to AgentExecutor (Antigravity).
"""
import asyncio
import time
import os
from pathlib import Path
from typing import Callable, Optional, List

from llm.planner import TaskPlanner, ExecutionPlan, Step
from orchestrator.agent_loop import AutonomousAgent
from orchestrator.logger import log_orchestrator, log_queue

class OpenClawOrchestrator:
    """
    Hệ điều phối cấp cao (OpenClaw style).
    Quản lý luồng công việc phức tạp qua nhiều bước.
    """

    def __init__(self, notify: Optional[Callable] = None):
        self.planner = TaskPlanner()
        self.notify = notify
        self.current_plan: Optional[ExecutionPlan] = None
        self.step_results: List[dict] = []
        self._running: bool = False

    async def _say(self, msg: str, silent: bool = False):
        """Gửi thông báo tới Telegram / Logs."""
        log_orchestrator(msg)
        if self.notify and not silent:
            await self.notify(msg)

    def _update_project_map(self, workspace: str) -> str:
        """
        Tạo bản đồ project (.coderx/PROJECT_MAP.md) để orient agent.
        """
        log_orchestrator(f"Updating project map in {workspace}...")
        coderx_dir = Path(workspace) / ".coderx"
        coderx_dir.mkdir(exist_ok=True)
        
        map_path = coderx_dir / "PROJECT_MAP.md"
        
        lines = ["# 🗺️ Project Map (Auto-generated)\n"]
        lines.append(f"Last updated: {time.ctime()}\n")
        lines.append("## 📂 File Structure\n")
        
        def walk(p: Path, prefix: str = "", depth: int = 0):
            if depth > 4: return
            try:
                items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
                for item in items:
                    if item.name.startswith(".") and item.name != ".coderx": continue
                    if item.name in ("node_modules", "__pycache__", "venv", "dist", "build"): continue
                    
                    icon = "📁" if item.is_dir() else "📄"
                    lines.append(f"{prefix}{icon} {item.name}")
                    
                    if item.is_dir():
                        walk(item, prefix + "  ", depth + 1)
            except Exception: pass

        walk(Path(workspace))
        
        content = "\n".join(lines)
        map_path.write_text(content)
        return content

    async def run(self, task_goal: str, workspace: str):
        """
        Luồng chính: Lập kế hoạch -> Thực thi từng bước -> Báo cáo.
        """
        self._running = True
        try:
            # 0. Khởi tạo Project Map (OpenClaw signature feature)
            project_map = self._update_project_map(workspace)

            # 1. Lập kế hoạch (OpenClaw style)
            await self._say("📝 *Đang phân tích dự án và lập kế hoạch tổng thể...*", silent=False)
            plan = await self.planner.plan(task_goal, workspace, context=f"PROJECT MAP:\n{project_map}")
            self.current_plan = plan

            # Thông báo kế hoạch cho user
            plan_desc = "\n".join([f"{s.id}. {s.title}" for s in plan.steps])
            await self._say(
                f"📋 *Lộ trình thực hiện:*\n{plan_desc}\n\n"
                f"_(Em bắt đầu bước 1 ngay đây anh nhé!)_",
                silent=False
            )

            # 2. Thực thi từng bước
            for step in plan.steps:
                if not self._running:
                    break

                await self._say(f"\n🚀 *Bắt đầu Bước {step.id}/{plan.total_steps}:* _{step.title}_", silent=False)
                
                # Gọi Antigravity Agent thực thi một step
                agent = AutonomousAgent(notify=self.notify)
                agent_state = await agent.run(step.prompt, workspace)

                # Thu thập kết quả step (Artifact)
                status = agent_state.final_state.value
                summary = agent_state.final_summary
                
                result = {
                    "id": step.id,
                    "type": step.type,
                    "status": status,
                    "summary": summary
                }
                self.step_results.append(result)
                
                # Cập nhật context & Project Map sau mỗi bước
                project_map = self._update_project_map(workspace)
                
                await self._say(f"💡 *Chiến thuật tiếp theo:* Đã cập nhật bản đồ project, chuẩn bị bước tiếp theo...", silent=True)

                # Chiến thuật "Review & Refine" (OpenClaw style)
                if status == "done":
                    await self._say(f"🔍 *Đang đánh giá kết quả và tinh chỉnh chiến thuật...*", silent=True)
                    plan = await self.planner.review_and_refine(plan, result, project_map)
                    self.current_plan = plan
                    
                    # Nếu có thay đổi lớn hoặc thêm steps, có thể thông báo ở đây
                    await self._say(f"💡 *Strategy Update:* Lộ trình đã được tối ưu hóa dựa trên thực tế.", silent=True)

                if status == "failed":
                    await self._say(f"⚠️ *Bước {step.id} thất bại:* {summary}\nĐang tính toán phương án sửa lỗi...", silent=False)
                    # Tự động tạo fix step
                    # plan = await self.planner.review_and_refine(plan, result, project_map)
                    break

            # 3. Báo cáo tổng kết
            final_report = await self.planner.summarize_results(plan, self.step_results)
            await self._say(f"\n🏁 *Hoàn tất nhiệm vụ!*\n{final_report}", silent=False)

        except Exception as e:
            import traceback
            log_orchestrator(f"Orchestrator Error: {e}\n{traceback.format_exc()}")
            await self._say(f"❌ *Lỗi hệ thống điều phối:* {e}", silent=False)
        finally:
            self._running = False
            self.current_plan = None
            self.step_results = []
