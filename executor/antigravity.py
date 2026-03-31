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
    ) -> tuple[bool, str]:
        """
        Gọi Antigravity chat với prompt và context files.

        Args:
            prompt: Yêu cầu gửi cho Antigravity Agent
            workspace: Đường dẫn workspace
            mode: 'agent' | 'ask' | 'edit'
            context_files: Danh sách các file đính kèm (relative paths)

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

        cmd.append(prompt)

        try:
            log(f"Executing chat command in [cyan]{workspace}[/cyan] ...", category="Executor")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            # CLI return ngay sau khi mở chat GUI
            # Nhưng ta vẫn communicate để xem có lỗi tức thì không
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=10, 
                )
                output = stdout.decode() if stdout else (stderr.decode() if stderr else "")
                
                if proc.returncode != 0 and proc.returncode is not None:
                    return False, f"CLI Error (code {proc.returncode}): {output}"
                
                return True, output
            except asyncio.TimeoutError:
                # Đây là trường hợp bình thường nếu CLI không chịu thoát (tùy version)
                return True, "Chat opened (timeout waiting for CLI exit)"

        except Exception as e:
            log(f"Error calling Antigravity: {e}", category="Executor", style="bold red")
            return False, str(e)
