"""
CoderX — Autonomous Agent Loop
Vòng lặp tự hành: Reason → Act → Observe → Repeat until DONE.
Bot tự quyết định mọi thứ, không cần user confirm từng bước.
"""
import asyncio
import time
from pathlib import Path
from typing import Callable, Optional
from rich.console import Console

from executor.antigravity import AntigravityExecutor
from executor.shell import ShellExecutor
from llm.agent_brain import (
    Action, ActionType, AgentBrain, AgentIteration,
    AgentState, Decision, Observation,
)
from workspace.monitor import WorkspaceMonitor
from config import config


class AutonomousAgent:
    """
    Agent tự hành hoàn toàn.

    Vòng lặp:
    1. REASON  — ChatGPT phân tích state, quyết định next action
    2. ACT     — Thực thi action (Antigravity hoặc Shell)
    3. OBSERVE — Thu thập kết quả, cập nhật state
    4. REPEAT  — Cho đến khi COMPLETE / STUCK / FAILED / max iterations
    """

    def __init__(self, notify: Optional[Callable] = None):
        self.brain = AgentBrain()
        self.antigravity = AntigravityExecutor()
        self.notify = notify
        self.console = Console()
        # Live status — có thể đọc từ bên ngoài bất kỳ lúc nào
        self.live: dict = {
            "phase": "idle",        # idle | reasoning | acting | observing
            "iteration": 0,
            "max_iterations": config.MAX_ITERATIONS,
            "current_action": "",  # Mô tả ngắn action đang chạy
            "last_thought": "",    # Reasoning mới nhất của Brain
            "last_result": "",     # Kết quả observation mới nhất
            "started_at": None,    # float timestamp
            "task_goal": "",
            "last_log": "",        # Bản tin log mới nhất gửi qua notify
        }

    async def _say(self, msg: str):
        self.live["last_log"] = msg
        cleaned_msg = msg.replace("*", "").replace("_", "").replace("`", "")
        self.console.print(f"[dim]\[Agent][/dim] {cleaned_msg}")
        if self.notify:
            await self.notify(msg)

    async def run(self, task_goal: str, workspace: str) -> AgentState:
        """
        Entry point. Chạy agent cho đến khi hoàn thành hoặc đạt giới hạn.
        Returns AgentState cuối cùng với toàn bộ lịch sử.
        """
        self.live["task_goal"]   = task_goal
        self.live["started_at"]  = time.time()
        self.live["phase"]       = "starting"

        state = AgentState(task_goal=task_goal, workspace=workspace)
        monitor = WorkspaceMonitor(workspace)
        monitor.start()

        await self._say(
            f"🤖 *CoderX Agent khởi động*\n"
            f"🎯 Mục tiêu: _{task_goal}_\n"
            f"📁 Workspace: `{workspace}`\n"
            f"🔄 Tối đa {config.MAX_ITERATIONS} vòng lặp"
        )

        try:
            for iteration in range(1, config.MAX_ITERATIONS + 1):
                self.live["iteration"] = iteration
                await self._say(f"\n━━━ *Vòng {iteration}/{config.MAX_ITERATIONS}* ━━━")

                # ── REASON ────────────────────────────────────────────────────
                self.live["phase"] = "reasoning"
                snapshot = self._snapshot_workspace(workspace)
                state.workspace_files = snapshot.split("\n") if snapshot else []

                await self._say(f"🧠 *Đang phân tích bước {iteration}...*")
                action, decision, confidence, decision_reason = await self.brain.reason(
                    state, snapshot
                )
                self.live["last_thought"] = action.reasoning[:300]

                await self._say(
                    f"💭 **Suy nghĩ:** _{action.reasoning}_\n"
                    f"🎯 **Hành động:** {action.title} (tin cậy: {confidence}%)\n"
                    f"📝 {decision_reason}"
                )

                # ── Early exit: task already done ─────────────────────────────
                if decision == Decision.COMPLETE:
                    state.final_decision = Decision.COMPLETE
                    await self._say(
                        f"✅ *Agent xác nhận HOÀN THÀNH* (confidence: {confidence}%)\n"
                        f"_{decision_reason}_"
                    )
                    break

                if decision in (Decision.STUCK, Decision.FAILED):
                    state.final_decision = decision
                    await self._say(
                        f"🚫 *Agent dừng* — {decision.upper()}\n"
                        f"_{decision_reason}_"
                    )
                    break

                # ── ACT ───────────────────────────────────────────────────────
                self.live["phase"]          = "acting"
                self.live["current_action"] = action.title
                observation = await self._execute_action(
                    action, workspace, monitor, iteration
                )

                # ── Record iteration ──────────────────────────────────────────
                self.live["phase"]       = "observing"
                self.live["last_result"] = observation.summary[:200]
                agent_iter = AgentIteration(
                    iteration=iteration,
                    action=action,
                    observation=observation,
                    decision=decision,
                    decision_reason=decision_reason,
                    confidence=confidence,
                )
                state.iterations.append(agent_iter)

                # ── Log observation ───────────────────────────────────────────
                status_icon = "✅" if observation.status in ("done", "idle_done") else "⚠️"
                files_info = ""
                if observation.files_changed:
                    top = [Path(f).name for f in observation.files_changed[:4]]
                    files_info = f"\n  📁 {', '.join(top)}"

                await self._say(
                    f"{status_icon} *Kết quả:* {observation.summary[:200]}"
                    + files_info
                )

            else:
                # Reached max iterations
                state.final_decision = Decision.STUCK
                await self._say(
                    f"⚠️ Đã đạt giới hạn {config.MAX_ITERATIONS} vòng lặp."
                )

        finally:
            monitor.stop()
            self.live["phase"] = "idle"
            self.live["current_action"] = ""

        # ── Final Report ──────────────────────────────────────────────────────
        report = await self.brain.generate_final_report(state)
        state.final_summary = report

        icon_map = {
            Decision.COMPLETE: "🎉",
            Decision.STUCK: "😓",
            Decision.FAILED: "❌",
        }
        icon = icon_map.get(state.final_decision, "📋")

        await self._say(
            f"\n{icon} *Báo cáo cuối:*\n{report}\n\n"
            f"📊 Tổng: {len(state.iterations)} vòng lặp | "
            f"Kết quả: {state.final_decision.upper()}"
        )

        return state

    async def _execute_action(
        self,
        action: Action,
        workspace: str,
        monitor: WorkspaceMonitor,
        iteration: int,
    ) -> Observation:
        """Thực thi một action, trả về observation."""

        if action.type == ActionType.SHELL:
            return await self._act_shell(action, workspace)

        elif action.type == ActionType.ANTIGRAVITY:
            return await self._act_antigravity(action, workspace, monitor, iteration)

        else:  # OBSERVE
            return Observation(
                action=action,
                status="done",
                summary="Observed current state without taking action",
            )

    async def _act_antigravity(
        self,
        action: Action,
        workspace: str,
        monitor: WorkspaceMonitor,
        iteration: int,
    ) -> Observation:
        """Gọi Antigravity Agent và đợi kết quả."""
        prompt_preview = action.prompt[:150] + "..." if len(action.prompt) > 150 else action.prompt
        await self._say(
            f"🚀 *Khởi chạy Antigravity Agent*\n"
            f"💬 Yêu cầu: _{prompt_preview}_\n"
            f"📂 Files đính kèm: `{', '.join(action.relevant_files) or 'none'}`"
        )

        success, msg = await self.antigravity.run(
            prompt=action.prompt,
            workspace=workspace,
            mode="agent",
            context_files=action.relevant_files,
        )

        if not success:
            return Observation(
                action=action,
                status="error",
                summary=f"Failed to call Antigravity: {msg}",
            )

        await self._say(
            f"⏳ Antigravity Agent đang chạy...\n"
            f"_(Tối đa {config.STEP_TIMEOUT//60} phút — "
            f"idle {config.STEP_IDLE_TIMEOUT}s không có changes → tự sang bước tiếp)_"
        )

        result = await monitor.wait_for_step_done(
            step_id=iteration,
            progress_callback=self._say,
        )

        status = result["status"]

        # ── done / idle_done: all good ────────────────────────────────────────
        if status in ("done", "idle_done"):
            icon = "✅" if status == "done" else "💤"
            await self._say(f"{icon} Antigravity xong ({result['elapsed']:.0f}s)")

        # ── cancelled_continue: timeout but NOT an error ──────────────────────
        elif status == "cancelled_continue":
            await self._say(
                f"⚡ Bước đã chạy hơn {config.STEP_TIMEOUT//60} phút — "
                f"tự cancel, chuyển tiếp. Brain sẽ đánh giá lại."
            )

        # ── git_confirm: ask user, wait for answer ────────────────────────────
        elif status == "git_confirm":
            git_cmd = result.get("git_command", "")
            await self._ask_git_confirm(workspace, git_cmd)
            # Return with special status so Brain knows to check git_confirmed.json
            result["summary"] = f"Git confirm requested: {git_cmd}"

        return Observation(
            action=action,
            status=status,
            summary=result["summary"],
            files_changed=result["files_changed"],
            elapsed=result["elapsed"],
        )

    async def _ask_git_confirm(
        self,
        workspace: str,
        git_command: str,
    ) -> None:
        """Thông báo cho user qua notify, yêu cầu confirm git."""
        await self._say(
            f"⚠️ *[GIT CONFIRM]*\n"
            f"Lệnh: `{git_command}`\n"
            f"Gửi *YES* để xác nhận hoặc *NO* để bỏ qua.\n"
            f"_(Tự bỏ qua sau {config.GIT_CONFIRM_TIMEOUT//60} phút nếu không trả lời)_"
        )
        # Bot handler sẽ pick up reply và ghi git_confirmed.json
        # Agent Brain sẽ check file này trong lần lặp tiếp theo

    async def _act_shell(self, action: Action, workspace: str) -> Observation:
        """Chạy shell command."""
        cmd = action.shell_command or ""
        await self._say(f"🖥️ `{cmd}`")

        shell = ShellExecutor(workspace)
        success, stdout, stderr = await shell.run(cmd)

        output = (stdout or stderr or "").strip()
        truncated = output[:600]

        if success:
            await self._say(f"✅ Shell done\n```\n{truncated}\n```")
        else:
            await self._say(f"❌ Shell failed\n```\n{truncated}\n```")

        return Observation(
            action=action,
            status="done" if success else "error",
            summary=truncated,
            shell_output=output,
        )

    def _snapshot_workspace(self, workspace: str) -> str:
        """Liệt kê files trong workspace để cho ChatGPT biết trạng thái hiện tại."""
        path = Path(workspace)
        lines = []

        def walk(p: Path, prefix: str = "", depth: int = 0):
            if depth > 3:
                return
            try:
                items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
                for item in items:
                    if item.name.startswith(".") or item.name in ("node_modules", "__pycache__", "venv"):
                        continue
                    lines.append(f"{prefix}{'📁' if item.is_dir() else '📄'} {item.name}")
                    if item.is_dir() and depth < 2:
                        walk(item, prefix + "  ", depth + 1)
            except PermissionError:
                pass

        walk(path)
        return "\n".join(lines[:60]) if lines else "Empty workspace"
