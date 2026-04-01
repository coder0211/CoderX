"""
CoderX — Main Orchestration Pipeline
Điều phối toàn bộ: ChatGPT Plan → Step Runner → Native Tools → Report
"""
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Optional

from executor.shell import ShellExecutor
from llm.planner import ExecutionPlan, Step, StepType, TaskPlanner
from orchestrator.agent_loop import AutonomousAgent
from orchestrator.memory_manager import MemoryManager
from workspace.monitor import WorkspaceMonitor
from config import config


@dataclass
class StepResult:
    step_id: int
    step_type: str
    title: str
    status: str          # done | idle_timeout | timeout | error | skipped
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    shell_output: str = ""


class Pipeline:
    """
    Pipeline thực thi một ExecutionPlan:
    - Chạy từng Step theo thứ tự (tôn trọng depends_on)
    - Gọi Native Tools hoặc Shell tùy step type
    - Monitor completion qua file changes
    - Gửi progress updates qua callback
    """

    def __init__(self, progress_callback: Optional[Callable] = None):
        self.planner = TaskPlanner()
        self.progress_callback = progress_callback

    async def _notify(self, message: str):
        if self.progress_callback:
            await self.progress_callback(message)

    async def run_task(
        self,
        user_request: str,
        workspace: str,
    ) -> tuple[ExecutionPlan, list[StepResult], str]:
        """
        Entry point chính: nhận yêu cầu → plan → execute → return results.
        """
        # 0. Đồng bộ MCP workspace
        await self._sync_mcp_workspace(workspace)

        # 1. Lập kế hoạch
        await self._notify("🧠 *ChatGPT đang phân tích và lập kế hoạch...*")
        plan = await self.planner.plan(user_request, workspace)

        await self._notify(
            f"📋 *Kế hoạch:* {plan.task_summary}\n"
            f"📌 *{plan.total_steps} steps:*\n"
            + "\n".join(
                f"  {i+1}. [{s.type.upper()}] {s.title}"
                for i, s in enumerate(plan.steps)
            )
        )

        # 2. Khởi động bộ nhớ & file monitor
        memory = MemoryManager(workspace)
        memory.reset_with_goal(user_request)
        
        monitor = WorkspaceMonitor(workspace)
        monitor.start()

        results: list[StepResult] = []

        try:
            for step in plan.steps:
                result = await self._execute_step(step, workspace, monitor, results)
                results.append(result)

                # Ghi vào bộ nhớ
                memory.append_decision(step.id, step.title, result.status, result.summary)

                # Tìm cách commit nếu thành công
                if result.status == "done":
                    await self._git_commit(step, workspace)

                # Nếu step thất bại nghiêm trọng, hỏi ChatGPT tạo fix step
                if result.status in ("error", "timeout") and step.type != StepType.FIX:
                    await self._notify(
                        f"⚠️ Step {step.id} gặp vấn đề. 🔧 Đang tạo fix step..."
                    )
                    # Corrected method call from refine_step to review_and_refine
                    # We pass the plan and the result to get an updated plan
                    project_map = monitor.get_snapshot() # Assuming monitor can give snapshot
                    plan = await self.planner.review_and_refine(plan, {
                        "id": step.id,
                        "type": step.type,
                        "status": result.status,
                        "summary": result.summary
                    }, project_map)
                    
                    # The loop will continue with the updated plan steps
                    # Note: This logic assumes plan.steps is updated in place or returned

        finally:
            monitor.stop()

        # 3. Tổng kết
        summary = await self.planner.summarize_results(plan, [
            {
                "id": r.step_id,
                "type": r.step_type,
                "status": r.status,
                "summary": r.summary,
            }
            for r in results
        ])

        return plan, results, summary

    async def _execute_step(
        self,
        step: Step,
        workspace: str,
        monitor: WorkspaceMonitor,
        previous_results: list[StepResult],
    ) -> StepResult:
        """Chạy một step đơn lẻ."""
        await self._notify(
            f"\n🔨 *Step {step.id}/{step.type.upper()}*: {step.title}"
        )

        if step.type == StepType.SHELL:
            return await self._run_shell_step(step, workspace)
        else:
            return await self._run_native_step(step, workspace, monitor)

    async def _run_native_step(
        self,
        step: Step,
        workspace: str,
        monitor: WorkspaceMonitor,
    ) -> StepResult:
        """Gọi native agent cho một coding/modify step."""
        agent = AutonomousAgent(notify=self.progress_callback)
        state = await agent.run(step.prompt, workspace)

        status = state.final_state.value
        summary = state.final_summary

        all_changed = set()
        for it in state.iterations:
            all_changed.update(it.observation.files_changed)

        return StepResult(
            step_id=step.id,
            step_type=step.type,
            title=step.title,
            status=status,
            summary=summary,
            files_changed=list(all_changed),
            elapsed=0.0, # Could calculate from iterations if needed
        )

    async def _run_shell_step(self, step: Step, workspace: str) -> StepResult:
        """Chạy shell command."""
        shell = ShellExecutor(workspace)
        cmd = step.shell_command or ""

        await self._notify(f"  🖥️ `{cmd}`")
        success, stdout, stderr = await shell.run(cmd)

        output = stdout or stderr
        truncated = output[:500] if len(output) > 500 else output

        if success:
            await self._notify(f"  ✅ Done\n```\n{truncated}\n```")
        else:
            await self._notify(f"  ❌ Failed\n```\n{truncated}\n```")

        return StepResult(
            step_id=step.id,
            step_type=step.type,
            title=step.title,
            status="done" if success else "error",
            summary=truncated,
            shell_output=output,
        )

    async def _sync_mcp_workspace(self, workspace: str):
        """Đảm bảo mcp.json đồng bộ với workspace hiện tại."""
        from mcp_client.tools_bridge import get_mcp_bridge
        import os

        abs_ws = os.path.abspath(os.path.expanduser(workspace))
        bridge = get_mcp_bridge()
        registry = bridge._registry # Truy cập nội bộ registry
        
        # 1. Tìm server 'filesystem'
        fs_server = registry.get("filesystem")
        if not fs_server:
            return

        # 2. Kiểm tra args (giả định path là arg cuối cùng)
        current_args = fs_server.args
        if not current_args or current_args[-1] != abs_ws:
            await self._notify(f"🔄 *Đồng bộ Workspace:* Cập nhật MCP server root ({abs_ws})...")
            
            # Cập nhật trong bộ nhớ
            new_args = list(current_args)
            if not any("@modelcontextprotocol/server-filesystem" in a for a in new_args):
                # Dự phòng nếu args trống
                new_args = ["-y", "@modelcontextprotocol/server-filesystem", abs_ws]
            else:
                new_args[-1] = abs_ws
            
            registry.update_server_args("filesystem", new_args)
            registry.save_to_file()
            
            # Yêu cầu bridge restart
            await bridge.startup(force_restart=True)
        else:
            # Ngay cả khi ko đổi mcp.json, vẫn cần đảm bảo bridge đã nạp abs_ws vào bộ lọc
            bridge.workspace_root = abs_ws
            await bridge.startup()

    async def _git_commit(self, step: Step, workspace: str):
        """Tự động commit kết quả sau mỗi bước thành công."""
        shell = ShellExecutor(workspace)
        # Kiểm tra xem có phải repo git không
        # success is the first, stdout is second
        success, stdout, _ = await shell.run("git rev-parse --is-inside-work-tree")
        if not success or stdout.strip() != "true":
            return

        msg = f"[CoderX] Step {step.id}: {step.title}"
        await shell.run("git add .")
        success, _, _ = await shell.run(f'git commit -m "{msg}"')
        if success:
            await self._notify(f"  📦 *Auto-commit:* `{msg}`")
