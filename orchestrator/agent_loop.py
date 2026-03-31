"""
CoderX — Autonomous Agent Loop
Vòng lặp tự hành: Reason → Act → Observe → Repeat until DONE.
Bot tự quyết định mọi thứ, không cần user confirm từng bước.
"""
import asyncio
import time
from pathlib import Path
from typing import Callable, Optional
from orchestrator.logger import log, log_agent, console

from executor.antigravity import AntigravityExecutor
from executor.shell import ShellExecutor
from llm.agent_brain import (
    Action, ActionType, AgentBrain, AgentIteration,
    AgentState, WorkflowState, Observation,
)
from mcp_client.tools_bridge import get_mcp_bridge
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
        # MCP bridge — kết nối tới external MCP servers
        self.mcp = get_mcp_bridge() if config.MCP_ENABLED else None
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

    async def _say(self, msg: str, silent: bool = True):
        """Log ra terminal, và tùy chọn gửi qua Telegram."""
        self.live["last_log"] = msg
        log_agent(msg)
        if self.notify and not silent:
            await self.notify(msg)

    async def run(self, task_goal: str, workspace: str) -> AgentState:
        """
        Entry point. Chạy agent cho đến khi hoàn thành hoặc đạt giới hạn.
        Returns AgentState cuối cùng với toàn bộ lịch sử.
        """
        self.live["task_goal"]   = task_goal
        self.live["started_at"]  = time.time()
        self.live["phase"]       = "starting"

        # Log absolute path for transparency
        abs_ws = Path(workspace).absolute()
        log(f"Working Workspace: [cyan]{abs_ws}[/cyan]", category="Workspace", style="bold yellow")

        state = AgentState(task_goal=task_goal, workspace=workspace)
        monitor = WorkspaceMonitor(workspace)
        monitor.start()

        # ── MCP bridge ────────────────────────────────────────────────────
        # Bridge được khởi động từ main.py — chỉ cần kiểm tra và log
        if self.mcp and self.mcp.is_ready():
            n_tools = len(self.mcp.list_tools())
            servers = self.mcp._manager.connected_servers if self.mcp._manager else []
            await self._say(
                f"🔧 *MCP Tools sẵn sàng:* {n_tools} tools từ {servers}",
                silent=True,
            )

        await self._say(
            f"🔥 *Tiến trình chạy ngầm bắt đầu*\n"
            f"🎯 Mục tiêu: _{task_goal}_\n"
            f"📁 Workspace: `{workspace}`\n"
            f"_(Em sẽ tự bơi trong tối đa {config.MAX_ITERATIONS} bước nhé!)_",
            silent=True
        )

        import builtins
        current_state = WorkflowState.PLANNING
        iteration = 0

        try:
            while current_state not in (WorkflowState.COMPLETED, WorkflowState.FAILED):
                iteration += 1
                if iteration > config.MAX_ITERATIONS:
                    state.final_state = WorkflowState.FAILED
                    await self._say(
                        f"⚠️ Đã đạt giới hạn {config.MAX_ITERATIONS} vòng lặp.",
                        silent=False
                    )
                    break

                self.live["iteration"] = iteration
                self.live["phase"] = current_state.value

                await self._say(f"\n━━━ *Vòng {iteration} | State: {current_state.value.upper()}* ━━━", silent=True)

                # ── REASON ────────────────────────────────────────────────────
                snapshot = self._snapshot_workspace(workspace)
                state.workspace_files = snapshot.split("\n") if snapshot else []

                await self._say(f"🧠 *Đang phân tích bước {iteration}...*", silent=True)
                action, next_state, confidence, decision_reason = await self.brain.reason(
                    state, snapshot,
                    mcp_tools_summary=self.mcp.tools_summary() if self.mcp and self.mcp.is_ready() else "",
                )
                self.live["last_thought"] = action.reasoning[:300]

                await self._say(
                    f"💭 **Suy nghĩ:** _{action.reasoning}_\n"
                    f"🎯 **Hành động tiếp theo:** {action.title} \n"
                    f"👉 **Chuyển sang State:** {next_state.value.upper()} (tin cậy: {confidence}%)\n"
                    f"📝 {decision_reason}",
                    silent=True
                )

                # ── Early exit: task already done ─────────────────────────────
                if next_state == WorkflowState.COMPLETED:
                    state.final_state = WorkflowState.COMPLETED
                    await self._say(
                        f"✅ *Xong rồi anh ơi!* (độ tự tin: {confidence}%)\n"
                        f"_{decision_reason}_",
                        silent=False
                    )
                    break

                if next_state == WorkflowState.FAILED:
                    state.final_state = WorkflowState.FAILED
                    await self._say(
                        f"🚫 *Sorry anh, em bị kẹt rùi* — FAILED\n"
                        f"_{decision_reason}_",
                        silent=False
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
                    next_state=next_state,
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
                    + files_info,
                    silent=True
                )
                
                # Update current state to the state decided by the brain
                current_state = next_state
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log(f"💥 Agent Loop Crashed: {e}\n{tb}", category="FATAL", style="bold red")
            await self._say(f"❌ *Lỗi hệ thống tạch cmnr sếp ơi:* {e}", silent=False)
            state.final_state = WorkflowState.FAILED
            state.final_summary = f"Crashed -> {e}"

        finally:
            monitor.stop()
            self.live["phase"] = "idle"
            self.live["current_action"] = ""

        # ── Final Report ──────────────────────────────────────────────────────
        try:
            report = await self.brain.generate_final_report(state)
            state.final_summary = report
        except Exception as report_err:
            log(f"Could not generate final report: {report_err}", category="WARN", style="yellow")
            report = state.final_summary or "Chưa có báo cáo tổng kết vì lỗi mạng/hệ thống."

        icon_map = {
            WorkflowState.COMPLETED: "🎉",
            WorkflowState.FAILED: "❌",
        }
        icon = icon_map.get(state.final_state, "📋")

        await self._say(
            f"\n{icon} *Báo cáo tổng kết của em:*\n{report}\n\n"
            f"📊 Mất {len(state.iterations)} bước | "
            f"Trạng thái: {state.final_state.value.upper()}",
            silent=False
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

        if action.type in (ActionType.ANTIGRAVITY_AGENT, ActionType.ANTIGRAVITY_ASK, ActionType.ANTIGRAVITY_EDIT):
            # Map action type back to CLI mode
            mode_map = {
                ActionType.ANTIGRAVITY_AGENT: "agent",
                ActionType.ANTIGRAVITY_ASK:   "ask",
                ActionType.ANTIGRAVITY_EDIT:  "edit",
            }
            mode = mode_map.get(action.type, "agent")
            return await self._act_antigravity(action, workspace, monitor, iteration, mode=mode)

        elif action.type == ActionType.SHELL:
            return await self._act_shell(action, workspace)

        elif action.type == ActionType.MCP:
            return await self._act_mcp(action)

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
        mode: str = "agent",
    ) -> Observation:
        """Gọi Antigravity Agent và đợi kết quả."""
        prompt_preview = action.prompt[:150] + "..." if len(action.prompt) > 150 else action.prompt
        await self._say(
            f"🚀 *Khởi chạy Antigravity Agent*\n"
            f"💬 Yêu cầu: _{prompt_preview}_\n"
            f"📂 Files đính kèm: `{', '.join(action.relevant_files) or 'none'}`",
            silent=True
        )

        success, msg = await self.antigravity.run(
            prompt=action.prompt,
            workspace=workspace,
            mode=mode,
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
            f"idle {config.STEP_IDLE_TIMEOUT}s không có changes → tự sang bước tiếp)_",
            silent=True
        )

        result = await monitor.wait_for_step_done(
            step_id=iteration,
            progress_callback=self._say,
        )

        status = result["status"]

        # ── done / idle_done: all good ────────────────────────────────────────
        if status in ("done", "idle_done"):
            icon = "✅" if status == "done" else "💤"
            await self._say(f"{icon} Antigravity xong ({result['elapsed']:.0f}s)", silent=True)

        # ── cancelled_continue: timeout but NOT an error ──────────────────────
        elif status == "cancelled_continue":
            await self._say(
                f"⚡ Bước đã chạy hơn {config.STEP_TIMEOUT//60} phút — "
                f"tự cancel, chuyển tiếp. Brain sẽ đánh giá lại.",
                silent=True
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
            f"_(Tự bỏ qua sau {config.GIT_CONFIRM_TIMEOUT//60} phút nếu không trả lời)_",
            silent=False
        )
        # Bot handler sẽ pick up reply và ghi git_confirmed.json
        # Agent Brain sẽ check file này trong lần lặp tiếp theo

    async def _act_shell(self, action: Action, workspace: str) -> Observation:
        """Chạy shell command."""
        cmd = action.shell_command or ""
        await self._say(f"🖥️ `{cmd}`", silent=True)

        shell = ShellExecutor(workspace)
        success, stdout, stderr = await shell.run(cmd)

        output = (stdout or stderr or "").strip()
        truncated = output[:600]

        if success:
            await self._say(f"✅ Shell done\n```\n{truncated}\n```", silent=True)
        else:
            await self._say(f"❌ Shell failed\n```\n{truncated}\n```", silent=True)

        return Observation(
            action=action,
            status="done" if success else "error",
            summary=truncated,
            shell_output=output,
        )

    async def _act_mcp(self, action: Action) -> Observation:
        """
        Gọi một MCP tool từ external server.

        action.mcp_tool      : vd "filesystem/read_file"
        action.mcp_arguments : dict hoặc JSON string các tham số
        """
        tool_name = getattr(action, "mcp_tool", "") or ""
        arguments = getattr(action, "mcp_arguments", {}) or {}

        if not tool_name:
            return Observation(
                action=action,
                status="error",
                summary="MCP action is missing 'mcp_tool' field.",
            )

        if not self.mcp or not self.mcp.is_ready():
            return Observation(
                action=action,
                status="error",
                summary="MCP bridge is not ready. Check MCP_ENABLED and MCP_SERVER_* in .env",
            )

        await self._say(f"🔧 *MCP Tool:* `{tool_name}`", silent=True)

        try:
            result = await asyncio.wait_for(
                self.mcp.execute(tool_name, arguments),
                timeout=config.MCP_TOOL_TIMEOUT,
            )
            truncated = result[:800]
            await self._say(f"✅ MCP OK\n```\n{truncated}\n```", silent=True)
            return Observation(action=action, status="done", summary=truncated)

        except asyncio.TimeoutError:
            msg = f"MCP tool '{tool_name}' timed out after {config.MCP_TOOL_TIMEOUT}s"
            await self._say(f"⏰ {msg}", silent=True)
            return Observation(action=action, status="error", summary=msg)

        except Exception as e:
            msg = f"MCP tool '{tool_name}' error: {e}"
            await self._say(f"❌ {msg}", silent=True)
            return Observation(action=action, status="error", summary=msg)

    def _snapshot_workspace(self, workspace: str) -> str:
        """Liệt kê files trong workspace để cho ChatGPT biết trạng thái hiện tại."""
        path = Path(workspace)
        lines = []

        def walk(p: Path, prefix: str = "", depth: int = 0):
            if depth > 4:
                return
            try:
                items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
                for item in items:
                    if item.name.startswith(".") or item.name in ("node_modules", "__pycache__", "venv"):
                        continue
                    lines.append(f"{prefix}{'📁' if item.is_dir() else '📄'} {item.name}")
                    if item.is_dir() and depth < 3:
                        walk(item, prefix + "  ", depth + 1)
            except PermissionError:
                pass

        walk(path)
        return "\n".join(lines[:200]) if lines else "Empty workspace"
