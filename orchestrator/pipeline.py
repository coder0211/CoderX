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
    ) -> tuple[ExecutionPlan, list[StepResult]]:
        """
        Entry point chính: nhận yêu cầu → plan → execute → return results.
        """
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

        # 2. Khởi động file monitor
        monitor = WorkspaceMonitor(workspace)
        monitor.start()

        results: list[StepResult] = []

        try:
            for step in plan.steps:
                result = await self._execute_step(step, workspace, monitor, results)
                results.append(result)

                # Nếu step thất bại nghiêm trọng, hỏi ChatGPT tạo fix step
                if result.status in ("error", "timeout") and step.type != StepType.FIX:
                    await self._notify(
                        f"⚠️ Step {step.id} gặp vấn đề. 🔧 Đang tạo fix step..."
                    )
                    fix_step = await self.planner.refine_step(step, result.summary, workspace)
                    fix_result = await self._execute_step(fix_step, workspace, monitor, results)
                    results.append(fix_result)

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
