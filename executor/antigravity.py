"""
CoderX — Antigravity CLI Executor
Gọi `antigravity chat --mode agent` với prompt, mở đúng workspace.
"""
import asyncio
import os
import subprocess
from pathlib import Path

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
        self.cli = config.ANTIGRAVITY_CLI
        self._current_workspace: str | None = None

    def is_running(self) -> bool:
        """Check xem Antigravity process có đang chạy không."""
        result = subprocess.run(
            ["pgrep", "-f", "Antigravity.app"],
            capture_output=True,
        )
        return result.returncode == 0

    async def ensure_open(self, workspace: str) -> None:
        """Đảm bảo Antigravity đang mở với đúng workspace."""
        if not self.is_running():
            # Mở Antigravity
            subprocess.Popen(
                ["open", "/Applications/Antigravity.app"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(3)  # Đợi app khởi động

        # Mở workspace nếu chưa mở hoặc workspace thay đổi
        if workspace != self._current_workspace:
            proc = await asyncio.create_subprocess_exec(
                self.cli,
                "--reuse-window",
                workspace,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            self._current_workspace = workspace
            await asyncio.sleep(1)  # Đợi workspace load

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
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # CLI return ngay sau khi mở chat GUI
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=15, 
            )
            output = stdout.decode() if stdout else (stderr.decode() if stderr else "")
            return True, output
        except asyncio.TimeoutError:
            return True, "Chat opened with context in Antigravity"
        except Exception as e:
            return False, str(e)
