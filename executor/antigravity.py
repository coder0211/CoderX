"""
CoderX — Antigravity CLI Executor
Gọi `antigravity chat --mode agent` với prompt, mở đúng workspace.
"""
import asyncio
import os
import subprocess
import shutil
from pathlib import Path
from orchestrator.logger import log

from config import config


class AntigravityExecutor:
    """
    Wrapper cho Antigravity CLI.
    Mỗi lần gọi run() sẽ:
    1. Đảm bảo Antigravity đang chạy
    2. Mở workspace đúng
    3. Gọi `antigravity chat --mode agent "<prompt>"`
    """

    def __init__(self):
        # Ưu tiên bản 'antigravity' trong PATH nếu có
        path_cli = shutil.which("antigravity")
        if path_cli:
            self.cli = path_cli
            log(f"Using Antigravity CLI from PATH: [green]{self.cli}[/green]", category="Executor")
        else:
            self.cli = config.ANTIGRAVITY_CLI
            log(f"Using Antigravity CLI from config: [green]{self.cli}[/green]", category="Executor")

        self._current_workspace: str | None = None

    def is_running(self) -> bool:
        """
        Check xem Antigravity (app bundle) có đang chạy không.
        Trên macOS, Antigravity chạy qua Electron nên không có process tên
        chính xác là 'Antigravity'. Ta check qua app bundle path hoặc
        language_server_macos_arm (chỉ chạy khi Antigravity đang mở).
        """
        # Check language_server_macos_arm — chỉ xuất hiện khi Antigravity đang mở workspace
        result = subprocess.run(
            ["pgrep", "-f", "Antigravity.app/Contents/Resources/app/extensions"],
            capture_output=True,
        )
        if result.returncode == 0:
            return True

        # Fallback: check Antigravity app bundle đang chạy qua Electron framework
        result = subprocess.run(
            ["pgrep", "-f", "Antigravity.app/Contents/Frameworks"],
            capture_output=True,
        )
        return result.returncode == 0

    async def ensure_open(self, workspace: str) -> None:
        """Đảm bảo Antigravity đang mở với đúng workspace."""
        if not self.is_running():
            log("Antigravity is not running. Launching...", category="Executor", style="yellow")
            subprocess.Popen(
                ["open", "/Applications/Antigravity.app"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(5)  # Đợi app khởi động đủ lâu
        else:
            log("Antigravity is already running.", category="Executor", style="dim")

        # Mở workspace nếu chưa mở hoặc workspace thay đổi
        if workspace != self._current_workspace:
            log(f"Opening workspace: [cyan]{workspace}[/cyan]", category="Executor")
            proc = await asyncio.create_subprocess_exec(
                self.cli,
                "--reuse-window",
                workspace,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            self._current_workspace = workspace
            await asyncio.sleep(2)  # Đợi workspace load xong
        else:
            log(f"Workspace already open: [cyan]{workspace}[/cyan]", category="Executor", style="dim")

    async def run(
        self,
        prompt: str,
        workspace: str,
        mode: str = "agent",
        context_files: list[str] = None,
        step_id: int | None = None,
    ) -> tuple[bool, str]:
        """
        Gọi Antigravity chat với prompt và context files.

        Args:
            prompt: Yêu cầu gửi cho Antigravity Agent
            workspace: Đường dẫn workspace
            mode: 'agent' | 'ask' | 'edit'
            context_files: Danh sách các file đính kèm (relative paths)
            step_id: ID bước hiện tại — dùng để inject done-marker instruction vào prompt

        Returns:
            (success, message)
        """
        # Verify CLI path tồn tại (self.cli có thể là path từ PATH hoặc config)
        if not os.path.exists(self.cli):
            # Thử find lại qua PATH
            found = shutil.which("antigravity")
            if found and os.path.exists(found):
                self.cli = found
                log(f"CLI re-resolved to: [green]{self.cli}[/green]", category="Executor")
            else:
                return False, f"Antigravity CLI not found at: {self.cli} (also not in PATH)"

        await self.ensure_open(workspace)

        # Inject done-marker instruction vào cuối prompt nếu có step_id
        # Đây là cơ chế duy nhất để agent_loop.py biết Antigravity đã xong
        final_prompt = prompt
        if step_id is not None:
            done_marker = (
                f"\n\n---\n"
                f"CRITICAL INSTRUCTION: When you have fully completed ALL tasks above, "
                f"you MUST create the file `.coderx/step_{step_id}_done.json` "
                f"in the workspace root with this exact content:\n"
                f'{{"status": "done", "summary": "brief summary of what you accomplished", '
                f'"files_changed": ["list", "of", "files", "you", "modified"]}}\n'
                f"This file is how the orchestrator knows you are finished. Do NOT skip this step."
            )
            if f".coderx/step_{step_id}_done.json" not in final_prompt:
                final_prompt = prompt + done_marker

        cmd = [
            self.cli,
            "chat",
            "--mode", mode,
            "--reuse-window",
            "--maximize",  # Tối đa hóa cửa sổ cho agent
        ]

        # Thêm context files
        if context_files:
            for f in context_files:
                cmd.extend(["--add-file", f])

        cmd.append("-")  # Dùng STDIN để an toàn với prompt dài/multiline

        try:
            log(f"Executing chat command in [cyan]{workspace}[/cyan] ...", category="Executor")
            if step_id is not None:
                log(f"Step ID: [yellow]{step_id}[/yellow] — done marker injected into prompt", category="Executor")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # CLI của Antigravity (VS Code-based GUI) thường thoát ngay sau khi
            # route prompt vào panel. Ta dùng timeout ngắn để bắt lỗi tức thì.
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=final_prompt.encode('utf-8')),
                    timeout=10,
                )
                stdout_text = stdout.decode('utf-8').strip() if stdout else ""
                stderr_text = stderr.decode('utf-8').strip() if stderr else ""
                output = stdout_text or stderr_text or "Prompt delivered to Antigravity GUI"

                if proc.returncode not in (None, 0):
                    return False, f"CLI Error (code {proc.returncode}): {output}"

                log(f"Prompt delivered ✓ ({len(final_prompt)} chars)", category="Executor", style="green")
                return True, output

            except asyncio.TimeoutError:
                # Bình thường — CLI đang giữ stdin open, prompt đã được route vào GUI
                proc.stdin.close()  # Đóng stdin để CLI thoát
                log("CLI still running (GUI mode) — prompt was sent", category="Executor", style="dim")
                return True, "Prompt delivered to Antigravity (GUI session active)"

        except Exception as e:
            log(f"Error calling Antigravity: {e}", category="Executor", style="bold red")
            return False, str(e)
